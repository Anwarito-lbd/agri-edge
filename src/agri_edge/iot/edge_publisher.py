"""Live reports from the aircraft: what it found, and how it is.

WHY
---
Until this module the pipeline's output went only to the spool, so the ops
station never saw a detection unless someone uploaded a spool afterwards. Here
each processed frame becomes one small message on
`agriedge/farm/{farm}/vehicle/{vehicle}/detections`, and periodic health on
`.../health` (topic contract: `iot/mqtt_topics.py`).

WHAT IT MUST NEVER DO
---------------------
* Block or break capture. Every failure is counted and swallowed; the spool is
  the durable record and uploads whatever the live link missed.
* Carry a command. The vehicle topic subtree is report-only by construction
  (`VEHICLE_KINDS`), matching the read-only MAVLink contract.

DEPENDENCIES
------------
The HTTP transport is standard library. MQTT needs `paho-mqtt` (the `mqtt`
extra), imported only when that transport is chosen, so the Pi runtime still
installs with numpy + PyYAML alone.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from .mqtt_topics import vehicle_topic

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1


def detections_message(metadata: dict, vehicle_id: str) -> dict:
    """One frame's sidecar -> the `detections` payload.

    Only georeferenced detections become GeoJSON features: a detection without a
    position cannot be put on a map, and inventing one is exactly what the
    georeference refuses to do. The unplaced count is still reported so the
    dashboard can say "12 found, 3 could not be located".
    """
    telem = metadata.get("telemetry") or {}
    model = metadata.get("model") or {}
    dets = metadata.get("detections") or []
    features = []
    unplaced = 0
    for i, d in enumerate(dets):
        if d.get("lat") is None or d.get("lon") is None:
            unplaced += 1
            continue
        props = {k: d.get(k) for k in ("label", "confidence", "source_label",
                                       "position_error_m", "in_treatment_zone",
                                       "validated_locally", "may_drive_treatment")
                 if d.get(k) is not None}
        features.append({
            "type": "Feature",
            "id": f"{metadata.get('sequence', 0)}-{i}",
            "geometry": {"type": "Point", "coordinates": [d["lon"], d["lat"]]},
            "properties": props,
        })
    captured = metadata.get("captured_at")
    return {
        "schema_version": SCHEMA_VERSION,
        "ts": _iso(captured) if isinstance(captured, (int, float)) else None,
        "device_id": vehicle_id,
        "site": metadata.get("site"),
        "field_id": metadata.get("field_id"),
        "frame": {
            "sequence": metadata.get("sequence"),
            "lat": telem.get("lat"),
            "lon": telem.get("lon"),
            "alt_rel_m": telem.get("alt_rel_m"),
            "qa_passed": (metadata.get("qa") or {}).get("passed"),
            "inference_error": metadata.get("inference_error"),
        },
        "model": {"name": model.get("name"), "version": model.get("version"),
                  "validated_locally": model.get("validated_locally")} if model else None,
        "unplaced": unplaced,
        "detections": {"type": "FeatureCollection", "features": features},
    }


def health_message(vehicle_id: str, stats: dict, telemetry: Any = None,
                   spool_stats: dict | None = None) -> dict:
    t = telemetry
    return {
        "schema_version": SCHEMA_VERSION,
        "ts": _iso(time.time()),
        "device_id": vehicle_id,
        "battery_pct": getattr(t, "battery_pct", None),
        "fix": getattr(t, "fix_name", None),
        "satellites": getattr(t, "satellites", None),
        "stats": dict(stats),
        "spool": dict(spool_stats or {}),
    }


def _iso(epoch: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()


class Transport(Protocol):
    def send(self, topic: str, payload: dict) -> None: ...
    def close(self) -> None: ...


class HttpTransport:
    """POST {topic, payload} to the ops API's /api/ops/ingest."""

    def __init__(self, endpoint: str, token: str | None = None, timeout_s: float = 3.0):
        self.url = endpoint.rstrip("/") + "/api/ops/ingest"
        self.token = token
        self.timeout_s = timeout_s

    def send(self, topic: str, payload: dict) -> None:
        body = json.dumps({"topic": topic, "payload": payload}).encode("utf-8")
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "agri-edge/0.1"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            resp.read()

    def close(self) -> None:
        pass


class MqttTransport:  # pragma: no cover - needs a broker; exercised in the ground_iot stack
    """Publish with paho-mqtt, QoS 1, reconnecting in paho's own loop thread."""

    def __init__(self, host: str, port: int = 1883, username: str | None = None,
                 password: str | None = None, tls: bool = False, client_id: str = ""):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("MQTT publishing needs paho-mqtt: pip install 'agri-edge[mqtt]'") from exc
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if username:
            self._client.username_pw_set(username, password)
        if tls:
            self._client.tls_set()
        self._client.reconnect_delay_set(min_delay=1, max_delay=60)
        self._client.connect_async(host, port, keepalive=30)
        self._client.loop_start()

    def send(self, topic: str, payload: dict) -> None:
        info = self._client.publish(topic, json.dumps(payload), qos=1)
        if info.rc != 0:
            raise RuntimeError(f"publish failed rc={info.rc}")

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


@dataclass
class PublishStats:
    sent: int = 0
    errors: int = 0
    last_error: str | None = None

    def as_dict(self) -> dict:
        return {"sent": self.sent, "errors": self.errors, "last_error": self.last_error}


class EdgePublisher:
    """Best-effort reporter. `publish_*` never raises."""

    def __init__(self, transport: Transport, farm_id: str, vehicle_id: str):
        self.transport = transport
        self.farm_id = farm_id
        self.vehicle_id = vehicle_id
        self.stats = PublishStats()
        self._det_topic = vehicle_topic(farm_id, vehicle_id, "detections")
        self._health_topic = vehicle_topic(farm_id, vehicle_id, "health")

    def publish_frame(self, metadata: dict) -> bool:
        return self._send(self._det_topic, lambda: detections_message(metadata, self.vehicle_id))

    def publish_health(self, stats: dict, telemetry: Any = None, spool_stats: dict | None = None) -> bool:
        return self._send(self._health_topic,
                          lambda: health_message(self.vehicle_id, stats, telemetry, spool_stats))

    def _send(self, topic: str, build) -> bool:
        try:
            self.transport.send(topic, build())
        except Exception as exc:  # noqa: BLE001 - the link is optional; capture is not
            self.stats.errors += 1
            self.stats.last_error = f"{type(exc).__name__}: {exc}"
            log.debug("publish to %s failed: %s", topic, exc)
            return False
        self.stats.sent += 1
        return True

    def close(self) -> None:
        try:
            self.transport.close()
        except Exception:  # noqa: BLE001
            pass


def build_publisher(cfg) -> EdgePublisher | None:
    """From a PublishConfig. None when disabled. Credentials from the environment."""
    if not getattr(cfg, "enabled", False):
        return None
    if cfg.transport == "http":
        transport: Transport = HttpTransport(cfg.endpoint, os.environ.get("OPS_API_TOKEN"),
                                             cfg.timeout_s)
    elif cfg.transport == "mqtt":
        transport = MqttTransport(cfg.mqtt_host, cfg.mqtt_port,
                                  os.environ.get("MQTT_USERNAME"),
                                  os.environ.get("MQTT_PASSWORD"),
                                  tls=cfg.mqtt_tls, client_id=f"agri-edge-{cfg.vehicle_id}")
    else:
        raise ValueError(f"publish.transport must be http or mqtt, got {cfg.transport!r}")
    return EdgePublisher(transport, cfg.farm_id, cfg.vehicle_id)
