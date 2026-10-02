"""Synthetic publisher for the Ops MQTT ingest (round-trip demos and tests).

Every message it builds carries `"synthetic": true`. It publishes DATA topics only
(`transport.assert_publishable` additionally refuses command-like topics), and the
payloads are invented -- they are never to be mistaken for measurements.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from agri_edge.iot.mqtt_topics import ops_topic
from agri_edge.iot.transport import MqttTransport, assert_publishable


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_demo_messages(
    *, farm: str = "demo_farm", seed: int = 7, now: Optional[datetime] = None,
    frost: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    """One of each ingestible message, deterministic for a seed. All synthetic."""
    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    ts = _iso(now)
    air = -1.5 if frost else round(17.0 + rng.uniform(-2, 2), 2)
    base = {"schema_version": 1, "ts": ts, "synthetic": True}
    msgs: list[tuple[str, dict[str, Any]]] = [
        (ops_topic(farm, "weather", "wx_mqtt", "observations"),
         {**base, "device_id": "wx_mqtt", "air_temp_c": air, "rh_pct": round(60 + rng.uniform(-8, 8), 1),
          "wind_ms": 2.4, "wind_dir_deg": 210.0, "precip_mm": 0.0, "pressure_hpa": 1012.5,
          "solar_wm2": 350.0, "battery_pct": 81.0, "signal_rssi": -72.0}),
        (ops_topic(farm, "soil", "soil_mqtt", "observations"),
         {**base, "device_id": "soil_mqtt", "zone_id": "zone_a", "battery_pct": 64.0,
          "signal_rssi": -80.0,
          "depths": [{"depth_cm": 10, "moisture_pct": 9.5, "soil_temp_c": 11.2},
                     {"depth_cm": 30, "moisture_pct": 21.0, "soil_temp_c": 10.4},
                     {"depth_cm": 60, "moisture_pct": 27.5, "soil_temp_c": 9.8}]}),
        (ops_topic(farm, "water", "fm_mqtt", "observations"),
         {**base, "device_id": "fm_mqtt", "zone_id": "zone_a", "flow_lpm": 0.0,
          "total_l": 1520.0, "tank_level_pct": 11.0, "water_temp_c": 8.5}),
        (ops_topic(farm, "irrigation", "ctl_mqtt", "state"),
         {**base, "device_id": "ctl_mqtt", "zone_id": "zone_a", "state": "idle",
          "valve_open_pct": 0.0, "flow_lpm": 0.0}),
        (ops_topic(farm, "rtk", "rtk_mqtt", "state"),
         {**base, "device_id": "rtk_mqtt", "kind": "base", "fix_quality": "float",
          "lat": 45.4, "lon": -75.7}),
        (ops_topic(farm, "gateway", "gw_mqtt", "health"),
         {**base, "device_id": "gw_mqtt", "online": True, "battery_pct": 90.0,
          "signal_rssi": -60.0, "uptime_s": 86400, "firmware": "sim-1.0", "buffer_depth": 0}),
        (ops_topic(farm, "vehicle", "ugv_mqtt", "detections"),
         {**base, "device_id": "ugv_mqtt", "frame_id": "f0001", "mission_id": "msn_sim",
          "model_name": "simulated", "model_version": "0.0.0", "backend": "simulated",
          "detections": [
              {"detection_id": "d1", "label": "weed", "confidence": 0.91,
               "bbox": [0.1, 0.1, 0.2, 0.2], "world_lat": 45.4011, "world_lon": -75.6987,
               "position_uncertainty_m": 0.8,
               # a malicious/buggy publisher claiming treatment eligibility: ignored on ingest
               "may_drive_treatment": True, "in_treatment_zone": True},
              {"detection_id": "d2", "label": "crop", "confidence": 0.62,
               "bbox": [0.5, 0.5, 0.7, 0.8]}]}),
    ]
    return msgs


def publish_demo(
    transport: MqttTransport, *, farm: str = "demo_farm", seed: int = 7,
    now: Optional[datetime] = None, frost: bool = False, replay: bool = False,
) -> int:
    """Publish the demo set. `replay=True` re-sends it verbatim (dedupe check)."""
    msgs = build_demo_messages(farm=farm, seed=seed, now=now, frost=frost)
    n = 0
    for _ in range(2 if replay else 1):
        for topic, body in msgs:
            assert_publishable(topic)
            transport.publish(topic, json.dumps(body).encode("utf-8"))
            n += 1
    return n


def backfill_messages(
    *, farm: str = "demo_farm", count: int = 3, step_s: int = 600, seed: int = 11,
    now: Optional[datetime] = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Older weather observations, as a gateway would flush after an outage."""
    now = now or datetime.now(timezone.utc)
    out = []
    for i in range(count, 0, -1):
        when = now - timedelta(seconds=step_s * i + 3600)
        out.append((ops_topic(farm, "weather", "wx_mqtt", "observations"),
                    {"schema_version": 1, "ts": _iso(when), "synthetic": True,
                     "device_id": "wx_mqtt", "air_temp_c": 15.0 + i, "rh_pct": 55.0}))
    return out
