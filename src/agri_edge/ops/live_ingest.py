"""Live MQTT -> Ops Station ingest (the broker path; `OpsIngestor`).

Relationship to `ops/ingest.py`: that module is the simple path used by
`POST /api/ops/ingest` and the `AGRIEDGE_MQTT_HOST` subscriber (`ops/mqtt_ingest.py`),
via `ingest(store, topic, payload)`. This module is separate and does not replace
it: it adds dedupe by (device, timestamp), quality flags, and alerts for the
broker path, on the `parse_ops_topic` scheme. See docs/operations/MQTT_INGEST.md.

STATUS: SIMULATED. Exercised against an in-memory broker in tests and (manually) a
local Mosquitto with synthetic publishers. No real sensor, gateway, radio or farm
network has ever fed it. Nothing here is VALIDATED.

PIPELINE
--------
    topic+payload -> parse topic -> parse/validate payload -> dedupe
                  -> write to OpsStore (+ DATABASE_URL backend) -> raise/resolve alerts

Subscribed topics (docs/MQTT_CONTRACT.md, "Operations Station topics"):

    agriedge/{farm}/weather/{station}/observations
    agriedge/{farm}/soil/{station}/observations
    agriedge/{farm}/water/{station}/observations
    agriedge/{farm}/irrigation/{controller}/state
    agriedge/{farm}/rtk/{station}/state
    agriedge/{farm}/gateway/{gateway}/health
    agriedge/{farm}/{vehicle}/detections

SAFETY, in the order it matters
-------------------------------
* **Subscribe-only.** This class has no publish path. Irrigation is ingested as
  *state* (a read-only mirror). A message on a state topic that carries a
  `command` / `set` field is rejected -- a command must never ride in on a data
  topic and be mistaken for state.
* **Remote claims are not trusted for actuation.** An ingested detection always
  has `may_drive_treatment=False` and `in_treatment_zone=None`, whatever the
  publisher said (the claim is kept under `payload.claimed` for the audit trail).
  Only `decision.engine` decides, from its own gates. AI output alone never
  triggers anything.
* **A device may downgrade its own data, never upgrade it.** A payload `quality`
  of GOOD/QUESTIONABLE/BAD is merged with the server-side checks by taking the
  *worse* of the two.
* **Fail loud on malformed input.** Bad JSON, wrong types, NaN/inf, naive or
  far-future timestamps, bare `temperature` keys, bad quality strings, oversized
  payloads, and a payload `device_id` that disagrees with the topic are REJECTED
  and counted; they are never coerced into a plausible reading.
* **Synthetic stays synthetic.** `synthetic: true` in a payload is carried onto
  every record it produces (origin SIMULATED). An absent flag means `false`; the
  store-wide SIMULATION banner is untouched by ingest.
* **Typed temperatures.** Only `air_temp_c`, `soil_temp_c`, `water_temp_c`,
  `canopy_temp_c` are accepted; each becomes a `TypedTemperature` with its kind.

DEDUPE
------
Key = (category, farm, device, normalised-UTC timestamp[, frame_id for detections]),
held in a bounded LRU. Record ids are also *deterministic* (hash of the same key
plus metric/depth), so a replay after the ingestor restarts is an idempotent upsert
in SQLite/PostGIS rather than a duplicate row. Out-of-order (buffered) messages are
accepted and inserted in timestamp order; they raise **no alert** when older than
`alert_max_age_s`, because a replayed frost reading from an hour ago is history,
not an emergency.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from agri_edge.iot.mqtt_topics import OPS_INGEST_SUBSCRIPTIONS, OpsTopic, parse_ops_topic
from agri_edge.iot.transport import MqttTransport

from .quality import evaluate_soil_reading, evaluate_weather_reading
from .schema import DeviceHealth, FlowMeter, RTKStation, SensorReading, WaterReading
from .store import OpsStore
from .types import (
    AlertCategory,
    AlertSeverity,
    DataOrigin,
    Device,
    DeviceType,
    QualityFlag,
    SoilObservation,
    TempKind,
    TypedTemperature,
    WeatherObservation,
)

INGEST_VERSION = "ops-ingest-1.0.0"
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_DETECTIONS_PER_MESSAGE = 500
MAX_SOIL_DEPTHS = 12

CLAIMABLE_QUALITY = {"GOOD", "QUESTIONABLE", "BAD"}
_QUALITY_RANK = {
    QualityFlag.GOOD: 0,
    QualityFlag.QUESTIONABLE: 1,
    QualityFlag.CAL_OVERDUE: 1,
    QualityFlag.LOW_BATTERY: 1,
    QualityFlag.WEAK_SIGNAL: 1,
    QualityFlag.MISSING: 2,
    QualityFlag.STUCK: 2,
    QualityFlag.JUMP: 2,
    QualityFlag.BAD: 3,
}
_BARE_TEMP_KEYS = ("temperature", "temp", "temp_c", "temperature_c")
_COMMAND_KEYS = ("command", "cmd", "set", "arm", "mode", "mission", "setpoint")

RTK_FIX_LEVELS = {"fixed": 3, "float": 2, "dgps": 1, "single": 1, "none": 0}


class IngestReject(Exception):
    """Raised inside parsing; becomes a REJECTED result with this reason."""


@dataclass
class IngestConfig:
    farm_ids: Optional[frozenset[str]] = None   # None = accept every farm
    max_future_s: float = 300.0                 # reject timestamps further ahead than this
    alert_max_age_s: float = 900.0              # older messages are stored but raise no alert
    dedupe_capacity: int = 100_000
    soil_dry_alert_pct: float = 12.0
    tank_low_alert_pct: float = 15.0
    low_battery_pct: float = 15.0
    weak_signal_rssi: float = -95.0
    dense_detections: int = 5                   # >= this many in one frame raises an alert
    dense_detection_conf: float = 0.5
    history_len: int = 4


@dataclass
class IngestResult:
    status: str                 # accepted | duplicate | rejected | ignored
    topic: str
    category: str = ""
    device_id: str = ""
    reason: str = ""
    records: int = 0
    alerts: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"


# ---------------------------------------------------------------------------
# payload helpers
# ---------------------------------------------------------------------------

def parse_ts(value: Any) -> datetime:
    """ISO-8601 with an explicit offset -> aware UTC datetime. Naive is rejected."""
    if not isinstance(value, str) or not value:
        raise IngestReject("ts_missing_or_not_string")
    s = value.strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as e:
        raise IngestReject("ts_unparseable") from e
    if dt.tzinfo is None:
        raise IngestReject("ts_naive_timezone_required")
    return dt.astimezone(timezone.utc)


def ts_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _num(p: dict, key: str, *, required: bool = False) -> Optional[float]:
    if key not in p or p[key] is None:
        if required:
            raise IngestReject(f"{key}_missing")
        return None
    v = p[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise IngestReject(f"{key}_not_a_number")
    if not math.isfinite(v):
        raise IngestReject(f"{key}_not_finite")
    return float(v)


def _opt_str(p: dict, key: str, maxlen: int = 128) -> Optional[str]:
    v = p.get(key)
    if v is None:
        return None
    if not isinstance(v, str) or len(v) > maxlen:
        raise IngestReject(f"{key}_not_a_short_string")
    return v


def _worst(*flags: QualityFlag) -> QualityFlag:
    return max(flags, key=lambda f: _QUALITY_RANK.get(f, 3))


def _det_id(*parts: Any) -> str:
    h = hashlib.sha1("|".join(str(x) for x in parts).encode("utf-8")).hexdigest()
    return h[:20]


def _insert_sorted(items: list, item: Any, key: Callable[[Any], str]) -> None:
    """Keep `items` ordered by timestamp so `[-1]` stays 'latest' after replays."""
    k = key(item)
    i = len(items)
    while i > 0 and key(items[i - 1]) > k:
        i -= 1
    items.insert(i, item)


# ---------------------------------------------------------------------------
# the ingestor
# ---------------------------------------------------------------------------

class OpsIngestor:
    def __init__(
        self,
        store: OpsStore,
        transport: Optional[MqttTransport] = None,
        config: Optional[IngestConfig] = None,
        *,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.store = store
        self.transport = transport
        self.config = config or IngestConfig()
        self.now_fn = now_fn
        self._seen: "OrderedDict[tuple, None]" = OrderedDict()
        self._hist: dict[tuple, deque] = {}
        self._lock = threading.RLock()
        self.stats: dict[str, Any] = {
            "version": INGEST_VERSION,
            "received": 0,
            "accepted": 0,
            "duplicate": 0,
            "rejected": 0,
            "ignored": 0,
            "records_written": 0,
            "by_category": {},
        }
        self.rejects: deque = deque(maxlen=50)
        store.ingest_stats = self.stats
        store.ingest_rejects = self.rejects  # type: ignore[attr-defined]

    # -- transport wiring ----------------------------------------------------
    def start(self) -> None:
        if self.transport is None:
            raise RuntimeError("no transport configured")
        self.transport.connect()
        for pattern in OPS_INGEST_SUBSCRIPTIONS:
            self.transport.subscribe(pattern, self._on_message)

    def _on_message(self, topic: str, payload: bytes) -> None:
        self.handle_message(topic, payload)

    def stop(self) -> None:
        if self.transport is not None:
            self.transport.disconnect()

    # -- entry point ---------------------------------------------------------
    def handle_message(self, topic: str, payload: bytes) -> IngestResult:
        with self._lock, self.store.lock:
            res = self._handle(topic, payload)
            self._count(res)
            return res

    def _count(self, res: IngestResult) -> None:
        s = self.stats
        s["received"] += 1
        s[res.status] = s.get(res.status, 0) + 1
        if res.accepted:
            s["records_written"] += res.records
        if res.category:
            cat = s["by_category"].setdefault(
                res.category, {"accepted": 0, "duplicate": 0, "rejected": 0, "ignored": 0}
            )
            cat[res.status] = cat.get(res.status, 0) + 1
        if res.status == "rejected":
            self.rejects.append({"topic": res.topic, "reason": res.reason})

    def _handle(self, topic: str, payload: bytes) -> IngestResult:
        try:
            ot = parse_ops_topic(topic)
        except ValueError as e:
            return IngestResult("rejected", topic, reason=f"topic:{e}")
        if self.config.farm_ids is not None and ot.farm_id not in self.config.farm_ids:
            return IngestResult("ignored", topic, ot.category, ot.device_id, "farm_not_selected")
        if ot.category == "vehicle" and ot.leaf != "detections":
            return IngestResult("ignored", topic, ot.category, ot.device_id, "leaf_not_ingested")
        if ot.category == "irrigation" and ot.leaf != "state":
            return IngestResult("ignored", topic, ot.category, ot.device_id, "leaf_not_ingested")
        try:
            body = self._decode(payload)
            dev = body.get("device_id")
            if dev is not None and dev != ot.device_id:
                raise IngestReject("device_id_topic_mismatch")
            if "schema_version" in body and body["schema_version"] != 1:
                raise IngestReject("unsupported_schema_version")
            for k in _BARE_TEMP_KEYS:
                if k in body:
                    raise IngestReject(f"untyped_temperature_key:{k}")
            dt = parse_ts(body.get("ts"))
            now = self.now_fn()
            if dt - now > timedelta(seconds=self.config.max_future_s):
                raise IngestReject("ts_in_future")
            synthetic = body.get("synthetic", False)
            if not isinstance(synthetic, bool):
                raise IngestReject("synthetic_not_bool")
            claimed_q = self._claimed_quality(body)

            key = self._dedupe_key(ot, body, dt)
            if key in self._seen:
                self._seen.move_to_end(key)
                return IngestResult("duplicate", topic, ot.category, ot.device_id, "seen")

            ctx = _Ctx(ot, body, dt, ts_iso(dt), synthetic, claimed_q,
                       fresh=(now - dt) <= timedelta(seconds=self.config.alert_max_age_s))
            handler = {
                "weather": self._weather, "soil": self._soil, "water": self._water,
                "irrigation": self._irrigation, "rtk": self._rtk,
                "gateway": self._gateway, "vehicle": self._detections,
            }[ot.category]
            n, alerts = handler(ctx)
        except IngestReject as e:
            return IngestResult("rejected", topic, ot.category, ot.device_id, str(e))

        self._seen[key] = None
        while len(self._seen) > self.config.dedupe_capacity:
            self._seen.popitem(last=False)
        return IngestResult("accepted", topic, ot.category, ot.device_id, records=n, alerts=alerts)

    # -- decoding / shared validation -----------------------------------------
    @staticmethod
    def _decode(payload: bytes) -> dict:
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise IngestReject("payload_too_large")
        try:
            body = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise IngestReject("payload_not_json") from e
        if not isinstance(body, dict):
            raise IngestReject("payload_not_object")
        return body

    @staticmethod
    def _claimed_quality(body: dict) -> QualityFlag:
        q = body.get("quality")
        if q is None:
            return QualityFlag.GOOD
        if not isinstance(q, str) or q not in CLAIMABLE_QUALITY:
            raise IngestReject("quality_not_GOOD_QUESTIONABLE_BAD")
        return QualityFlag(q)

    @staticmethod
    def _dedupe_key(ot: OpsTopic, body: dict, dt: datetime) -> tuple:
        extra = ""
        if ot.category == "vehicle":
            fid = body.get("frame_id")
            extra = str(fid) if fid is not None else ""
        return (ot.category, ot.farm_id, ot.device_id, ts_iso(dt), extra)

    def _history(self, ctx: "_Ctx", metric: str) -> deque:
        k = (ctx.ot.farm_id, ctx.ot.device_id, metric)
        return self._hist.setdefault(k, deque(maxlen=self.config.history_len))

    # -- device registry -----------------------------------------------------
    def _touch_device(self, ctx: "_Ctx", dtype: DeviceType, **updates: Any) -> Device:
        ot = ctx.ot
        d = self.store.devices.get(ot.device_id)
        if d is None:
            d = Device(device_id=ot.device_id, device_type=dtype, name=ot.device_id,
                       farm_id=ot.farm_id, synthetic=ctx.synthetic)
            self.store.devices[ot.device_id] = d
        d.meta["role"] = ot.category
        d.meta["transport"] = "mqtt"
        if ctx.fresh or d.last_seen is None or d.last_seen < ctx.ts:
            d.last_seen = ctx.ts
        d.synthetic = d.synthetic and ctx.synthetic   # one real message makes it non-synthetic
        for k, v in updates.items():
            if v is not None:
                setattr(d, k, v)
        return d

    # -- alert helpers -----------------------------------------------------
    def _alert(self, ctx: "_Ctx", sev: AlertSeverity, cat: AlertCategory, title: str,
               msg: str, key: str, out: list[str]) -> None:
        if not ctx.fresh:
            return
        a = self.store.alerts.raise_alert(
            severity=sev, category=cat, title=title, message=msg,
            source_key=f"ingest:{key}:{ctx.ot.device_id}", device_id=ctx.ot.device_id,
            farm_id=ctx.ot.farm_id, synthetic=ctx.synthetic,
            meta={"origin": "mqtt_ingest", "ts": ctx.ts},
        )
        out.append(a.alert_id)

    def _clear(self, ctx: "_Ctx", key: str) -> None:
        if ctx.fresh:
            self.store.alerts.resolve_by_source(f"ingest:{key}:{ctx.ot.device_id}", "mqtt_ingest")

    def _device_health_alerts(self, ctx: "_Ctx", battery: Optional[float],
                              rssi: Optional[float], out: list[str]) -> None:
        c = self.config
        if battery is not None and battery < c.low_battery_pct:
            self._alert(ctx, AlertSeverity.WARNING, AlertCategory.DEVICE, "Low battery",
                        f"{ctx.ot.device_id} battery {battery:.0f}%", "low_battery", out)
        elif battery is not None:
            self._clear(ctx, "low_battery")
        if rssi is not None and rssi < c.weak_signal_rssi:
            self._alert(ctx, AlertSeverity.INFO, AlertCategory.DEVICE, "Weak signal",
                        f"{ctx.ot.device_id} RSSI {rssi:.0f} dBm", "weak_signal", out)
        elif rssi is not None:
            self._clear(ctx, "weak_signal")

    def _sensor_row(self, ctx: "_Ctx", metric: str, value: float, unit: str,
                    quality: QualityFlag, *, depth_cm: Optional[float] = None,
                    temp_kind: Optional[TempKind] = None) -> SensorReading:
        r = SensorReading(
            reading_id="ing_" + _det_id(ctx.ot.farm_id, ctx.ot.device_id, metric, depth_cm, ctx.ts),
            sensor_id=ctx.ot.device_id, ts=ctx.ts, metric=metric, value=value, unit=unit,
            quality=quality,
            origin=DataOrigin.SIMULATED if ctx.synthetic else DataOrigin.MEASURED,
            depth_cm=depth_cm, temp_kind=temp_kind.value if temp_kind else None,
            synthetic=ctx.synthetic, farm_id=ctx.ot.farm_id,
        )
        self.store.persist_sensor(r)
        self.store.sensors[f"{ctx.ot.device_id}:{metric}:{depth_cm}"] = r
        return r

    # -- category handlers ---------------------------------------------------
    def _weather(self, ctx: "_Ctx") -> tuple[int, list[str]]:
        p = ctx.body
        air_c = _num(p, "air_temp_c")
        rh = _num(p, "rh_pct")
        wind = _num(p, "wind_ms")
        wdir = _num(p, "wind_dir_deg")
        precip = _num(p, "precip_mm")
        pres = _num(p, "pressure_hpa")
        solar = _num(p, "solar_wm2")
        batt = _num(p, "battery_pct")
        rssi = _num(p, "signal_rssi")
        if all(v is None for v in (air_c, rh, wind, wdir, precip, pres, solar)):
            raise IngestReject("no_weather_measurement")

        hist = self._history(ctx, "air_temp_c")
        q = evaluate_weather_reading(
            air_c, rh,
            history_temps=list(hist) if air_c is not None else (),
            prev_temp=hist[-1] if hist else None,
        )
        # evaluate_weather_reading flags a *missing* temp as QUESTIONABLE only when
        # other fields were reported; a station with no temp sensor is not "bad".
        reasons = [r for r in q.reasons if not (air_c is None and r == "missing_air_temp")]
        flag = q.flag if reasons else QualityFlag.GOOD
        extra: list[str] = []
        for name, v, lo, hi in (("wind_ms", wind, 0, 100), ("wind_dir_deg", wdir, 0, 360),
                                ("precip_mm", precip, 0, 500), ("pressure_hpa", pres, 300, 1100),
                                ("solar_wm2", solar, 0, 1500)):
            if v is not None and not (lo <= v <= hi):
                extra.append(f"impossible_{name}:{v}")
        if extra:
            flag = _worst(flag, QualityFlag.BAD)
        flag = _worst(flag, ctx.claimed_quality)

        obs = WeatherObservation(
            obs_id="wo_" + _det_id(ctx.ot.farm_id, ctx.ot.device_id, ctx.ts),
            station_id=ctx.ot.device_id, ts=ctx.ts,
            air_temp=(TypedTemperature(value_c=air_c, kind=TempKind.AIR,
                                       origin=DataOrigin.SIMULATED if ctx.synthetic else DataOrigin.MEASURED,
                                       quality=flag) if air_c is not None else None),
            rh_pct=rh, wind_ms=wind, wind_dir_deg=wdir, precip_mm=precip,
            pressure_hpa=pres, solar_wm2=solar, quality=flag,
            origin=DataOrigin.SIMULATED if ctx.synthetic else DataOrigin.MEASURED,
            synthetic=ctx.synthetic, farm_id=ctx.ot.farm_id,
        )
        self._touch_device(ctx, DeviceType.WEATHER_STATION, battery_pct=batt, signal_rssi=rssi,
                           lat=_num(p, "lat"), lon=_num(p, "lon"))
        self.store.persist_weather(obs)            # appends (+ SQLite mirror when configured)
        self.store.weather.sort(key=lambda o: o.ts)  # replays arrive out of order; keep [-1] = latest
        n = 1
        for metric, v, unit, kind in (
            ("air_temp_c", air_c, "degC", TempKind.AIR), ("rh_pct", rh, "%", None),
            ("wind_ms", wind, "m/s", None), ("wind_dir_deg", wdir, "deg", None),
            ("precip_mm", precip, "mm", None), ("pressure_hpa", pres, "hPa", None),
            ("solar_wm2", solar, "W/m2", None),
        ):
            if v is not None:
                self._sensor_row(ctx, metric, v, unit, flag, temp_kind=kind)
                n += 1
        if air_c is not None:
            hist.append(air_c)

        alerts: list[str] = []
        if (air_c is not None and obs.air_temp is not None
                and flag not in (QualityFlag.BAD, QualityFlag.STUCK, QualityFlag.JUMP)):
            if ctx.fresh:
                a = self.store.alerts.evaluate_temperature(
                    obs.air_temp, device_id=ctx.ot.device_id, farm_id=ctx.ot.farm_id,
                    synthetic=ctx.synthetic)
                if a is not None:
                    alerts.append(a.alert_id)
                else:
                    for k in ("frost", "frost_watch", "heat"):
                        self.store.alerts.resolve_by_source(
                            f"temp:air:{k}:{ctx.ot.device_id}", "mqtt_ingest")
        elif flag in (QualityFlag.BAD, QualityFlag.STUCK, QualityFlag.JUMP):
            self._alert(ctx, AlertSeverity.WARNING, AlertCategory.DEVICE, "Bad weather data",
                        f"{ctx.ot.device_id}: {', '.join(reasons + extra) or 'device-reported BAD'}",
                        "bad_data", alerts)
        else:
            self._clear(ctx, "bad_data")
        self._device_health_alerts(ctx, batt, rssi, alerts)
        return n, alerts

    def _soil(self, ctx: "_Ctx") -> tuple[int, list[str]]:
        p = ctx.body
        depths = p.get("depths")
        if depths is None:
            entries = [p]
        else:
            if not isinstance(depths, list) or not depths or len(depths) > MAX_SOIL_DEPTHS:
                raise IngestReject("depths_not_a_short_nonempty_list")
            entries = []
            for e in depths:
                if not isinstance(e, dict):
                    raise IngestReject("depth_entry_not_object")
                for k in _BARE_TEMP_KEYS:
                    if k in e:
                        raise IngestReject(f"untyped_temperature_key:{k}")
                entries.append(e)
        batt = _num(p, "battery_pct")
        rssi = _num(p, "signal_rssi")
        zone = _opt_str(p, "zone_id")
        days_cal = _num(p, "days_since_cal")

        parsed = []
        for e in entries:
            depth = _num(e, "depth_cm", required=True)
            assert depth is not None
            if not (0 < depth <= 300):
                raise IngestReject(f"depth_cm_out_of_range:{depth}")
            moist = _num(e, "moisture_pct")
            stemp = _num(e, "soil_temp_c")
            ec = _num(e, "ec_ds_m")
            ph = _num(e, "ph")
            if moist is None and stemp is None:
                raise IngestReject("no_soil_measurement")
            parsed.append((depth, moist, stemp, ec, ph))
        if len({d for d, *_ in parsed}) != len(parsed):
            raise IngestReject("duplicate_depth_in_message")

        self._touch_device(ctx, DeviceType.SOIL_MULTI_DEPTH, battery_pct=batt, signal_rssi=rssi,
                           lat=_num(p, "lat"), lon=_num(p, "lon"))
        n = 0
        alerts: list[str] = []
        worst_flag = QualityFlag.GOOD
        for depth, moist, stemp, ec, ph in parsed:
            hist = self._history(ctx, f"moisture@{depth}")
            q = evaluate_soil_reading(
                moist, history=list(hist) if moist is not None else (),
                prev_moisture=hist[-1] if hist else None,
                battery_pct=batt, signal_rssi=rssi, days_since_cal=days_cal,
            )
            reasons = [r for r in q.reasons if not (moist is None and r == "missing")]
            flag = q.flag if reasons else QualityFlag.GOOD
            if (ph is not None and not 0.0 <= ph <= 14.0) or (ec is not None and ec < 0):
                flag = _worst(flag, QualityFlag.BAD)
            flag = _worst(flag, ctx.claimed_quality)
            worst_flag = _worst(worst_flag, flag)
            origin = DataOrigin.SIMULATED if ctx.synthetic else DataOrigin.MEASURED
            obs = SoilObservation(
                obs_id="so_" + _det_id(ctx.ot.farm_id, ctx.ot.device_id, depth, ctx.ts),
                probe_id=ctx.ot.device_id, ts=ctx.ts, depth_cm=depth, moisture_pct=moist,
                soil_temp=(TypedTemperature(value_c=stemp, kind=TempKind.SOIL, origin=origin,
                                            quality=flag) if stemp is not None else None),
                ec_ds_m=ec, ph=ph, quality=flag, origin=origin, synthetic=ctx.synthetic,
                farm_id=ctx.ot.farm_id, zone_id=zone,
            )
            _insert_sorted(self.store.soil, obs, lambda o: o.ts)
            n += 1
            if moist is not None:
                self._sensor_row(ctx, "moisture_pct", moist, "%", flag, depth_cm=depth)
                hist.append(moist)
                n += 1
            if stemp is not None:
                self._sensor_row(ctx, "soil_temp_c", stemp, "degC", flag, depth_cm=depth,
                                 temp_kind=TempKind.SOIL)
                n += 1
            if flag in (QualityFlag.BAD, QualityFlag.STUCK, QualityFlag.JUMP):
                continue
            if moist is not None:
                if moist < self.config.soil_dry_alert_pct:
                    self._alert(ctx, AlertSeverity.WARNING, AlertCategory.SOIL, "Soil very dry",
                                f"{ctx.ot.device_id} @ {depth:g} cm: {moist:.1f}% "
                                f"< {self.config.soil_dry_alert_pct}%", f"dry@{depth:g}", alerts)
                else:
                    self._clear(ctx, f"dry@{depth:g}")
            if stemp is not None and ctx.fresh:
                a = self.store.alerts.evaluate_temperature(
                    TypedTemperature(value_c=stemp, kind=TempKind.SOIL),
                    device_id=ctx.ot.device_id, farm_id=ctx.ot.farm_id, synthetic=ctx.synthetic)
                if a is not None:
                    alerts.append(a.alert_id)
        if worst_flag in (QualityFlag.BAD, QualityFlag.STUCK, QualityFlag.JUMP):
            self._alert(ctx, AlertSeverity.WARNING, AlertCategory.DEVICE, "Bad soil data",
                        f"{ctx.ot.device_id}: quality {worst_flag.value}", "bad_data", alerts)
        else:
            self._clear(ctx, "bad_data")
        self._device_health_alerts(ctx, batt, rssi, alerts)
        return n, alerts

    def _water(self, ctx: "_Ctx") -> tuple[int, list[str]]:
        p = ctx.body
        flow = _num(p, "flow_lpm")
        total = _num(p, "total_l")
        level = _num(p, "tank_level_pct")
        wtemp = _num(p, "water_temp_c")
        batt = _num(p, "battery_pct")
        rssi = _num(p, "signal_rssi")
        if all(v is None for v in (flow, total, level, wtemp)):
            raise IngestReject("no_water_measurement")
        flag = QualityFlag.GOOD
        if (flow is not None and flow < 0) or (total is not None and total < 0) or \
                (level is not None and not 0.0 <= level <= 100.0):
            flag = QualityFlag.BAD
        flag = _worst(flag, ctx.claimed_quality)
        origin = DataOrigin.SIMULATED if ctx.synthetic else DataOrigin.MEASURED
        self._touch_device(ctx, DeviceType.FLOW_METER, battery_pct=batt, signal_rssi=rssi)
        n = 0
        if flow is not None or total is not None:
            wr = WaterReading(
                reading_id="wr_" + _det_id(ctx.ot.farm_id, ctx.ot.device_id, ctx.ts),
                meter_id=ctx.ot.device_id, ts=ctx.ts, flow_lpm=flow if flow is not None else 0.0,
                total_l=total, quality=flag, origin=origin, synthetic=ctx.synthetic)
            _insert_sorted(self.store.water_readings, wr, lambda o: o.ts)
            fm = self.store.flow_meters.get(ctx.ot.device_id)
            if fm is None:
                fm = FlowMeter(meter_id=ctx.ot.device_id, name=ctx.ot.device_id,
                               zone_id=_opt_str(p, "zone_id"), farm_id=ctx.ot.farm_id,
                               synthetic=ctx.synthetic)
                self.store.flow_meters[ctx.ot.device_id] = fm
            if flag != QualityFlag.BAD and (fm.last_lpm is None or ctx.fresh):
                fm.last_lpm = flow if flow is not None else fm.last_lpm
                fm.total_l = total if total is not None else fm.total_l
            n += 1
        for metric, v, unit, kind in (("flow_lpm", flow, "L/min", None), ("total_l", total, "L", None),
                                      ("tank_level_pct", level, "%", None),
                                      ("water_temp_c", wtemp, "degC", TempKind.WATER)):
            if v is not None:
                self._sensor_row(ctx, metric, v, unit, flag, temp_kind=kind)
                n += 1
        alerts: list[str] = []
        if level is not None and flag != QualityFlag.BAD:
            tank = self.store.tanks.get(ctx.ot.device_id)
            if tank is not None and ctx.fresh:
                tank.level_pct = level
            if level < self.config.tank_low_alert_pct:
                self._alert(ctx, AlertSeverity.WARNING, AlertCategory.WATER, "Tank low",
                            f"{ctx.ot.device_id} level {level:.0f}%", "tank_low", alerts)
            else:
                self._clear(ctx, "tank_low")
        self._device_health_alerts(ctx, batt, rssi, alerts)
        return n, alerts

    def _irrigation(self, ctx: "_Ctx") -> tuple[int, list[str]]:
        p = ctx.body
        for k in _COMMAND_KEYS:
            if k in p:
                raise IngestReject(f"command_field_on_state_topic:{k}")
        state = p.get("state")
        if not isinstance(state, str) or state not in {"idle", "running", "paused", "fault", "offline"}:
            raise IngestReject("state_not_in_idle_running_paused_fault_offline")
        valve = _num(p, "valve_open_pct")
        flow = _num(p, "flow_lpm")
        if valve is not None and not 0.0 <= valve <= 100.0:
            raise IngestReject("valve_open_pct_out_of_range")
        if flow is not None and flow < 0:
            raise IngestReject("flow_lpm_negative")
        batt = _num(p, "battery_pct")
        rssi = _num(p, "signal_rssi")
        zone = _opt_str(p, "zone_id")
        fault = _opt_str(p, "fault_code")
        self._touch_device(ctx, DeviceType.UNKNOWN, battery_pct=batt, signal_rssi=rssi)
        prev = self.store.irrigation_state.get(ctx.ot.device_id)
        if prev is None or prev["ts"] <= ctx.ts:
            self.store.irrigation_state[ctx.ot.device_id] = {
                "controller_id": ctx.ot.device_id, "farm_id": ctx.ot.farm_id, "ts": ctx.ts,
                "state": state, "zone_id": zone, "valve_open_pct": valve, "flow_lpm": flow,
                "fault_code": fault, "synthetic": ctx.synthetic,
                "channel": "mqtt_ground_only", "read_only_mirror": True,
            }
            v = self.store.valves.get(ctx.ot.device_id)
            if v is not None and valve is not None:
                v.open_pct = valve
        alerts: list[str] = []
        if state in ("fault", "offline"):
            self._alert(ctx, AlertSeverity.CRITICAL if state == "fault" else AlertSeverity.WARNING,
                        AlertCategory.IRRIGATION, f"Irrigation controller {state}",
                        f"{ctx.ot.device_id} reported {state}" + (f" ({fault})" if fault else ""),
                        "irrigation_state", alerts)
        else:
            self._clear(ctx, "irrigation_state")
        self._device_health_alerts(ctx, batt, rssi, alerts)
        return 1, alerts

    def _rtk(self, ctx: "_Ctx") -> tuple[int, list[str]]:
        p = ctx.body
        fix = p.get("fix_quality")
        if not isinstance(fix, str) or fix not in RTK_FIX_LEVELS:
            raise IngestReject("fix_quality_not_fixed_float_dgps_single_none")
        kind = p.get("kind", "base")
        if kind not in ("base", "rover"):
            raise IngestReject("kind_not_base_or_rover")
        lat, lon = _num(p, "lat"), _num(p, "lon")
        if (lat is None) != (lon is None):
            raise IngestReject("lat_lon_must_come_together")
        if lat is not None and lon is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise IngestReject("lat_lon_out_of_range")
        self._touch_device(ctx, DeviceType.RTK_BASE if kind == "base" else DeviceType.RTK_ROVER,
                           lat=lat, lon=lon)
        prev = self.store.rtk.get(ctx.ot.device_id)
        if prev is None or getattr(prev, "_ts", "") <= ctx.ts:
            st = RTKStation(
                station_id=ctx.ot.device_id, name=ctx.ot.device_id, kind=kind,
                lat=lat if lat is not None else (prev.lat if prev else 0.0),
                lon=lon if lon is not None else (prev.lon if prev else 0.0),
                fix_quality=fix, synthetic=ctx.synthetic)
            st._ts = ctx.ts  # type: ignore[attr-defined]
            self.store.rtk[ctx.ot.device_id] = st
        alerts: list[str] = []
        if fix != "fixed":
            sev = AlertSeverity.CRITICAL if (kind == "base" and fix == "none") else AlertSeverity.WARNING
            self._alert(ctx, sev, AlertCategory.SAFETY, "RTK not fixed",
                        f"{ctx.ot.device_id} ({kind}) fix_quality={fix}", "rtk_degraded", alerts)
        else:
            self._clear(ctx, "rtk_degraded")
        return 1, alerts

    def _gateway(self, ctx: "_Ctx") -> tuple[int, list[str]]:
        p = ctx.body
        online = p.get("online", True)
        if not isinstance(online, bool):
            raise IngestReject("online_not_bool")
        batt = _num(p, "battery_pct")
        rssi = _num(p, "signal_rssi")
        up = _num(p, "uptime_s")
        depth = _num(p, "buffer_depth")
        fw = _opt_str(p, "firmware")
        err = _opt_str(p, "error_code")
        self._touch_device(ctx, DeviceType.GATEWAY, battery_pct=batt, signal_rssi=rssi)
        prev = self.store.health.get(ctx.ot.device_id)
        if prev is None or prev.ts <= ctx.ts:
            self.store.health[ctx.ot.device_id] = DeviceHealth(
                device_id=ctx.ot.device_id, ts=ctx.ts, online=online, battery_pct=batt,
                signal_rssi=rssi, uptime_s=up, firmware=fw, error_code=err,
                synthetic=ctx.synthetic)
        alerts: list[str] = []
        if not online:
            self._alert(ctx, AlertSeverity.WARNING, AlertCategory.DEVICE, "Gateway offline",
                        f"{ctx.ot.device_id} reports offline", "offline", alerts)
        else:
            self._clear(ctx, "offline")
        if err:
            self._alert(ctx, AlertSeverity.WARNING, AlertCategory.DEVICE, "Gateway error",
                        f"{ctx.ot.device_id}: {err}", "error", alerts)
        else:
            self._clear(ctx, "error")
        if depth is not None and depth > 1000:
            self._alert(ctx, AlertSeverity.INFO, AlertCategory.DEVICE, "Gateway backlog",
                        f"{ctx.ot.device_id} buffering {depth:.0f} messages", "backlog", alerts)
        self._device_health_alerts(ctx, batt, rssi, alerts)
        return 1, alerts

    def _detections(self, ctx: "_Ctx") -> tuple[int, list[str]]:
        p = ctx.body
        items = p.get("detections")
        if items is None:
            items = [p]          # a single-detection message
        if not isinstance(items, list) or len(items) > MAX_DETECTIONS_PER_MESSAGE:
            raise IngestReject("detections_not_a_bounded_list")
        frame_id = _opt_str(p, "frame_id")
        mission_id = _opt_str(p, "mission_id")
        parsed = []
        for i, d in enumerate(items):
            if not isinstance(d, dict):
                raise IngestReject(f"detection[{i}]_not_object")
            label = d.get("label")
            if not isinstance(label, str) or not label or len(label) > 64:
                raise IngestReject(f"detection[{i}]_label_invalid")
            conf = _num(d, "confidence", required=True)
            assert conf is not None
            if not 0.0 <= conf <= 1.0:
                raise IngestReject(f"detection[{i}]_confidence_out_of_range")
            bb = d.get("bbox")
            if not isinstance(bb, (list, tuple)) or len(bb) != 4:
                raise IngestReject(f"detection[{i}]_bbox_not_4_numbers")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                   for v in bb):
                raise IngestReject(f"detection[{i}]_bbox_not_finite_numbers")
            x1, y1, x2, y2 = (float(v) for v in bb)
            if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
                raise IngestReject(f"detection[{i}]_bbox_not_normalised_xyxy")
            for k in _BARE_TEMP_KEYS:
                if k in d:
                    raise IngestReject(f"untyped_temperature_key:{k}")
            parsed.append((i, d, label, conf, [x1, y1, x2, y2]))

        self._touch_device(ctx, DeviceType.UNKNOWN)
        dev = ctx.ot.device_id
        n = 0
        high = 0
        for i, d, label, conf, bbox in parsed:
            did = d.get("detection_id") or d.get("id")
            if did is not None and not isinstance(did, str):
                raise IngestReject(f"detection[{i}]_id_not_string")
            det_id = f"{ctx.ot.farm_id}:{dev}:{did}" if did else f"{ctx.ot.farm_id}:{dev}:{ctx.ts}:{frame_id or ''}:{i}"
            row: dict[str, Any] = {
                "detection_id": det_id, "ts": ctx.ts, "label": label, "confidence": conf,
                "bbox": bbox, "farm_id": ctx.ot.farm_id, "mission_id": mission_id,
                "frame_id": frame_id,
                "model_name": _opt_str(d, "model_name") or _opt_str(p, "model_name"),
                "model_version": _opt_str(d, "model_version") or _opt_str(p, "model_version"),
                "backend": _opt_str(d, "backend") or _opt_str(p, "backend"),
                # FAIL CLOSED: remote claims never make a detection treatment-eligible.
                "validated_locally": d.get("validated_locally") is True,   # truthy strings do not count
                "may_drive_treatment": False,
                "in_treatment_zone": None,
                "synthetic": ctx.synthetic,
                "payload": {
                    "source": "mqtt", "vehicle_id": dev, "ingest_version": INGEST_VERSION,
                    "claimed": {
                        "may_drive_treatment": d.get("may_drive_treatment"),
                        "in_treatment_zone": d.get("in_treatment_zone"),
                    },
                },
            }
            self._attach_position(row, d)
            self.store.persist_detection(row)
            n += 1
            if conf >= self.config.dense_detection_conf:
                high += 1
        alerts: list[str] = []
        if high >= self.config.dense_detections:
            self._alert(ctx, AlertSeverity.INFO, AlertCategory.CROP, "Dense detections",
                        f"{dev}: {high} detections >= {self.config.dense_detection_conf} in one "
                        f"frame (decision support only)", "dense_detections", alerts)
        return n, alerts

    @staticmethod
    def _attach_position(row: dict, d: dict) -> None:
        """Carry a publisher-supplied georeference through, range-checked, or drop it."""
        keys = ("world_lat", "world_lon", "local_x", "local_y", "position_uncertainty_m")
        have = {k: d.get(k) for k in keys if d.get(k) is not None}
        lat = d.get("world_lat") if d.get("world_lat") is not None else d.get("lat")
        lon = d.get("world_lon") if d.get("world_lon") is not None else d.get("lon")
        ok = (
            isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            and not isinstance(lat, bool) and not isinstance(lon, bool)
            and math.isfinite(lat) and math.isfinite(lon)
            and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)
        )
        if lat is None and lon is None and not have:
            return
        if not ok:
            row["georef_status"] = "REJECTED_POSITION_INVALID"
            return
        assert lat is not None and lon is not None  # `ok` above implies both are finite numbers
        row["lat"] = row["world_lat"] = float(lat)
        row["lon"] = row["world_lon"] = float(lon)
        for k in ("local_x", "local_y", "position_uncertainty_m"):
            v = d.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                row[k] = float(v)
        gs = d.get("georef_status")
        row["georef_status"] = gs if isinstance(gs, str) and len(gs) <= 64 else "CLAIMED_BY_PUBLISHER"


@dataclass
class _Ctx:
    ot: OpsTopic
    body: dict
    dt: datetime
    ts: str
    synthetic: bool
    claimed_quality: QualityFlag
    fresh: bool
