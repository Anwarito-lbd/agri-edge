"""Real data into the ops store: one path for MQTT and HTTP.

WHY
---
Until 24 Sept 2026 the ops station showed only `seed_demo()` data: no route
accepted a reading, `persist_sensor` was never called, and `MqttBridge` was
wired to nothing. This module is the single door real data comes through.
`ingest(store, topic, payload)` takes a topic from the contract in
`iot/mqtt_topics.py` and a JSON payload (docs/MQTT_CONTRACT.md), and the same
function serves the MQTT subscriber (`ops/mqtt_ingest.py`) and
`POST /api/ops/ingest`, so the two cannot drift apart.

RULES
-----
* **Reports only.** `irrigation/set` is a command; the ops station records
  what valves *report* (`irrigation/status`) and never accepts a command
  through its ingest door.
* **Nothing arriving here can authorise treatment.** A vehicle's detections
  keep the edge's own treatment flag as `edge_may_drive_treatment`; the ops
  row's `may_drive_treatment` is always False (same rule as F2).
* **Bad data is kept, and flagged.** Readings are quality-checked
  (`ops/quality.py`) and stored with their flag -- discarding them would hide a
  failing probe.
* **Durable.** With a SQLite path, every accepted message is appended to an
  ingest log and replayed on startup, so a restart does not empty the station.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from ..iot.mqtt_topics import ParsedTopic, parse_topic
from .quality import evaluate_soil_reading, evaluate_weather_reading
from .schema import DeviceHealth, SensorReading
from .store import OpsStore
from .types import (
    DataOrigin,
    Device,
    DeviceType,
    QualityFlag,
    SoilObservation,
    TempKind,
    TypedTemperature,
    WeatherObservation,
    new_id,
    utcnow,
)


class IngestError(ValueError):
    """A message that cannot be accepted. Served as 400."""


# -- helpers -------------------------------------------------------------------


def _num(payload: dict, key: str, *, lo: float | None = None, hi: float | None = None) -> Optional[float]:
    """A finite number or None. Out-of-range values are returned, not clipped --
    the quality checks flag them, and a clipped value would hide a fault."""
    v = payload.get(key)
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise IngestError(f"{key} must be a number, got {v!r}") from None
    v = float(v)
    if not math.isfinite(v):
        raise IngestError(f"{key} must be finite, got {v}")
    return v


def _ts(payload: dict) -> tuple[str, bool]:
    """(ISO timestamp, trusted).

    No `ts` at all is normal for a simple sensor on a live link: the receive
    time is used and trusted. A `ts` that is unparseable, or more than 10
    minutes in the future (a device with no RTC that never synced), is replaced
    by the receive time and marked untrusted -- the device is wrong about when.
    """
    raw = payload.get("ts")
    now = utcnow()
    if raw is None:
        return now.isoformat(), True
    if isinstance(raw, str):
        try:
            t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if (t - now).total_seconds() <= 600:
                return t.astimezone(timezone.utc).isoformat(), True
        except ValueError:
            pass
    return now.isoformat(), False


def _device_id(payload: dict, fallback: str) -> str:
    d = payload.get("device_id")
    if d is None:
        return fallback
    d = str(d)
    if not d or len(d) > 64 or "/" in d:
        raise IngestError(f"device_id must be 1-64 characters without '/', got {d!r}")
    return d


def _touch_device(store: OpsStore, device_id: str, dtype: DeviceType, farm_id: str,
                  zone_id: Optional[str], ts: str, payload: dict) -> Device:
    dev = store.devices.get(device_id)
    if dev is None:
        dev = Device(device_id=device_id, device_type=dtype, name=device_id,
                     farm_id=farm_id, zone_id=zone_id, synthetic=False)
        store.devices[device_id] = dev
    dev.last_seen = ts
    bat = _num(payload, "battery_pct")
    rssi = _num(payload, "rssi")
    if bat is not None:
        dev.battery_pct = bat
    if rssi is not None:
        dev.signal_rssi = rssi
    for key in ("lat", "lon"):
        v = _num(payload, key)
        if v is not None:
            setattr(dev, key, v)
    return dev


def _reading(store: OpsStore, sensor_id: str, ts: str, metric: str, value: float,
             unit: str, farm_id: str, quality: QualityFlag, depth_cm: Optional[float] = None,
             temp_kind: Optional[str] = None) -> None:
    store.persist_sensor(SensorReading(
        reading_id=new_id("rd_"), sensor_id=sensor_id, ts=ts, metric=metric, value=value,
        unit=unit, quality=quality, origin=DataOrigin.MEASURED, depth_cm=depth_cm,
        temp_kind=temp_kind, synthetic=False, farm_id=farm_id,
    ))


# -- per kind ------------------------------------------------------------------


def _soil(store: OpsStore, t: ParsedTopic, p: dict) -> dict:
    ts, trusted = _ts(p)
    dev_id = _device_id(p, f"soil-{t.zone_id}")
    dev = _touch_device(store, dev_id, DeviceType.SOIL_PROBE, t.farm_id, t.zone_id, ts, p)
    layers = p.get("depths")
    if layers is None:
        layers = [p]
    elif not isinstance(layers, list) or not layers:
        raise IngestError("depths must be a non-empty list")
    else:
        dev.device_type = DeviceType.SOIL_MULTI_DEPTH
    stored = []
    for layer in layers:
        if not isinstance(layer, dict):
            raise IngestError("each depth must be an object")
        moisture = _num(layer, "moisture_pct")
        temp = _num(layer, "temp_c")
        depth = _num(layer, "depth_cm")
        depth = 10.0 if depth is None else depth
        prev = next((o.moisture_pct for o in reversed(store.soil)
                     if o.probe_id == dev_id and o.depth_cm == depth), None)
        q = evaluate_soil_reading(moisture, prev_moisture=prev,
                                  battery_pct=dev.battery_pct, signal_rssi=dev.signal_rssi)
        flag = q.flag if trusted else (q.flag if q.flag != QualityFlag.GOOD else QualityFlag.QUESTIONABLE)
        soil_temp = TypedTemperature(temp, TempKind.SOIL) if temp is not None else None
        obs = SoilObservation(
            obs_id=new_id("so_"), probe_id=dev_id, ts=ts, depth_cm=depth,
            moisture_pct=moisture,
            soil_temp=soil_temp,
            ec_ds_m=_num(layer, "ec_ds_m"), quality=flag, synthetic=False,
            farm_id=t.farm_id, zone_id=t.zone_id,
        )
        store.soil.append(obs)
        if moisture is not None:
            _reading(store, dev_id, ts, "soil_moisture", moisture, "%", t.farm_id, flag, depth)
        if temp is not None and soil_temp is not None:
            _reading(store, dev_id, ts, "soil_temp", temp, "C", t.farm_id, flag, depth, "soil")
            store.alerts.evaluate_temperature(soil_temp, device_id=dev_id, farm_id=t.farm_id)
        stored.append({"depth_cm": depth, "quality": flag.value, "reasons": q.reasons})
    return {"kind": "soil", "device_id": dev_id, "layers": stored, "ts_trusted": trusted}


def _weather(store: OpsStore, t: ParsedTopic, p: dict) -> dict:
    ts, trusted = _ts(p)
    dev_id = _device_id(p, f"wx-{t.zone_id}")
    _touch_device(store, dev_id, DeviceType.WEATHER_STATION, t.farm_id, t.zone_id, ts, p)
    temp = _num(p, "air_temp_c")
    rh = _num(p, "rh_pct")
    prev = next((w.air_temp.value_c for w in reversed(store.weather)
                 if w.station_id == dev_id and w.air_temp), None)
    q = evaluate_weather_reading(temp, rh, prev_temp=prev)
    flag = q.flag if trusted else (q.flag if q.flag != QualityFlag.GOOD else QualityFlag.QUESTIONABLE)
    obs = WeatherObservation(
        obs_id=new_id("wo_"), station_id=dev_id, ts=ts,
        air_temp=TypedTemperature(temp, TempKind.AIR) if temp is not None else None,
        rh_pct=rh, wind_ms=_num(p, "wind_ms"), wind_dir_deg=_num(p, "wind_dir_deg"),
        precip_mm=_num(p, "precip_mm"), pressure_hpa=_num(p, "pressure_hpa"),
        solar_wm2=_num(p, "solar_wm2"), quality=flag, synthetic=False, farm_id=t.farm_id,
    )
    store.persist_weather(obs)
    for metric, unit in (("air_temp_c", "C"), ("rh_pct", "%"), ("wind_ms", "m/s"),
                         ("precip_mm", "mm"), ("solar_wm2", "W/m2")):
        v = _num(p, metric)
        if v is not None:
            _reading(store, dev_id, ts, metric, v, unit, t.farm_id, flag)
    if obs.air_temp is not None and flag in (QualityFlag.GOOD, QualityFlag.QUESTIONABLE):
        store.alerts.evaluate_temperature(obs.air_temp, device_id=dev_id, farm_id=t.farm_id)
    return {"kind": "weather", "device_id": dev_id, "quality": flag.value,
            "reasons": q.reasons, "ts_trusted": trusted}


def _health(store: OpsStore, dev_id: str, dtype: DeviceType, farm_id: str,
            zone_id: Optional[str], p: dict) -> dict:
    ts, _ = _ts(p)
    _touch_device(store, dev_id, dtype, farm_id, zone_id, ts, p)
    uptime = _num(p, "uptime_s")
    store.health[dev_id] = DeviceHealth(
        device_id=dev_id, ts=ts, online=True, battery_pct=_num(p, "battery_pct"),
        signal_rssi=_num(p, "rssi"), uptime_s=uptime,
        firmware=str(p["firmware"])[:64] if p.get("firmware") else None,
        error_code=str(p["error_code"])[:64] if p.get("error_code") else None,
        synthetic=False,
    )
    return {"kind": "health", "device_id": dev_id}


def _irrigation_status(store: OpsStore, t: ParsedTopic, p: dict) -> dict:
    ts, _ = _ts(p)
    dev_id = _device_id(p, f"valve-{t.zone_id}")
    _touch_device(store, dev_id, DeviceType.VALVE, t.farm_id, t.zone_id, ts, p)
    for metric, unit in (("valve_open_pct", "%"), ("flow_lpm", "L/min")):
        v = _num(p, metric)
        if v is not None:
            _reading(store, dev_id, ts, metric, v, unit, t.farm_id, QualityFlag.GOOD)
    return {"kind": "irrigation/status", "device_id": dev_id}


def _vehicle_detections(store: OpsStore, t: ParsedTopic, p: dict) -> dict:
    ts, _ = _ts(p)
    vehicle = t.vehicle_id or "vehicle"
    _touch_device(store, vehicle, DeviceType.SCOUT_DRONE, t.farm_id, None, ts, {})
    fc = p.get("detections") or {}
    feats = fc.get("features") if isinstance(fc, dict) else None
    if not isinstance(feats, list):
        raise IngestError("detections must be a GeoJSON FeatureCollection")
    frame = p.get("frame") or {}
    model = p.get("model") or {}
    added = 0
    for f in feats:
        geom = (f or {}).get("geometry") or {}
        coords = geom.get("coordinates")
        if geom.get("type") != "Point" or not isinstance(coords, list) or len(coords) < 2:
            raise IngestError("each detection must be a GeoJSON Point")
        lon, lat = float(coords[0]), float(coords[1])
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise IngestError(f"coordinates out of range: {coords}")
        props = f.get("properties") or {}
        store.persist_detection({
            # Deterministic, so a replayed or re-sent message upserts rather
            # than duplicating.
            "detection_id": f"{vehicle}-{ts}-{f.get('id', added)}",
            "ts": ts,
            "label": str(props.get("label", "unknown"))[:64],
            "confidence": float(props.get("confidence") or 0.0),
            "bbox": [0, 0, 0, 0],
            "lat": lat,
            "lon": lon,
            "position_error_m": props.get("position_error_m"),
            "source_label": props.get("source_label"),
            "model_name": model.get("name"),
            "model_version": model.get("version"),
            "farm_id": t.farm_id,
            "mission_id": p.get("field_id"),
            "frame_id": str(frame.get("sequence")),
            "vehicle_id": vehicle,
            # The ops station never authorises treatment. What the edge computed
            # is kept for the record under a name nothing downstream trusts.
            "edge_may_drive_treatment": bool(props.get("may_drive_treatment")),
            "validated_locally": False,
            "may_drive_treatment": False,
            "synthetic": False,
        })
        added += 1
    return {"kind": "detections", "vehicle_id": vehicle, "added": added,
            "unplaced": int(p.get("unplaced") or 0)}


# -- entry points --------------------------------------------------------------


def ingest(store: OpsStore, topic: str, payload: Any, *, log: bool = True) -> dict:
    """Accept one message. Raises IngestError (-> 400) for anything malformed."""
    try:
        t = parse_topic(topic)
    except ValueError as exc:
        raise IngestError(str(exc)) from None
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise IngestError("payload is not JSON") from None
    if not isinstance(payload, dict):
        raise IngestError("payload must be a JSON object")
    if t.is_irrigation_command():
        # A command, not a report. Recorded nowhere, refused loudly.
        raise IngestError("irrigation/set is a command; the ops ingest accepts reports only")

    if t.is_vehicle:
        if t.kind == "detections":
            result = _vehicle_detections(store, t, payload)
        else:
            result = _health(store, t.vehicle_id or "vehicle", DeviceType.SCOUT_DRONE,
                             t.farm_id, None, payload)
    elif t.kind == "soil":
        result = _soil(store, t, payload)
    elif t.kind == "weather":
        result = _weather(store, t, payload)
    elif t.kind == "status":
        result = _health(store, _device_id(payload, f"dev-{t.zone_id}"), DeviceType.UNKNOWN,
                         t.farm_id, t.zone_id, payload)
    elif t.kind == "irrigation/status":
        result = _irrigation_status(store, t, payload)
    else:  # pragma: no cover - parse_topic admits nothing else
        raise IngestError(f"unhandled kind {t.kind}")

    store.live_messages += 1
    if log and store.sqlite_path:
        _append_log(store.sqlite_path, topic, payload)
    return {"accepted": True, "topic": topic, **result}


def _append_log(path: str, topic: str, payload: dict) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("INSERT INTO ingest_log(received_at, topic, payload) VALUES (?, ?, ?)",
                    (utcnow().isoformat(), topic, json.dumps(payload)))
        con.commit()
    finally:
        con.close()


def replay_ingest_log(store: OpsStore) -> int:
    """Rebuild the in-memory state from the durable log. Returns messages replayed.

    A message that no longer validates (the rules tightened since it was
    accepted) is skipped rather than aborting the startup."""
    if not store.sqlite_path:
        return 0
    con = sqlite3.connect(store.sqlite_path)
    try:
        rows = con.execute("SELECT topic, payload FROM ingest_log ORDER BY id").fetchall()
    finally:
        con.close()
    n = 0
    store.replaying = True
    try:
        for topic, payload in rows:
            try:
                ingest(store, topic, json.loads(payload), log=False)
                n += 1
            except (IngestError, ValueError):
                continue
    finally:
        store.replaying = False
    return n


def detections_geojson(store: OpsStore, limit: int = 2000) -> dict:
    """Georeferenced detections as a map layer, newest first."""
    feats = []
    for row in reversed(store.detections[-limit:]):
        if row.get("lat") is None or row.get("lon") is None:
            continue
        props = {k: row.get(k) for k in ("label", "confidence", "ts", "vehicle_id",
                                         "position_error_m", "model_name", "synthetic")}
        feats.append({"type": "Feature", "id": row.get("detection_id"),
                      "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
                      "properties": props})
    return {"type": "FeatureCollection", "features": feats}
