"""LoRaWAN field nodes onto the farm's MQTT contract.

Wi-Fi reaches a few hundred metres from the yard; LoRaWAN reaches the far
quarter. Nodes send compact binary uplinks (ground_iot/lorawan/PAYLOAD.md)
through a gateway to ChirpStack (run unmodified, from upstream's
chirpstack-docker). This bridge subscribes to ChirpStack's MQTT integration,
decodes each uplink, looks the device up in the registry
(`iot/provision.py`, devices.json), and republishes it on the contract topic
`agriedge/farm/{farm}/zone/{zone}/{soil|weather}` -- so the ops station,
Node-RED and everything else see a LoRa probe exactly as they see a Wi-Fi one.

A device not in the registry is dropped: an unknown node must not be able to
put readings into a field just by being in radio range.

The decoder here mirrors `chirpstack_codec.js` and the C encoder in
`ground_iot/lorawan/firmware/`; tests/test_lorawan.py holds all three together.
"""

from __future__ import annotations

import base64
import json
import logging
import struct
from typing import Any

from .mqtt_topics import zone_topic

log = logging.getLogger(__name__)

PORT_SOIL, PORT_WEATHER = 1, 2


class PayloadError(ValueError):
    pass


def _scaled(v: int, missing: int, k: float) -> float | None:
    return None if v == missing else v / k


def decode(fport: int, data: bytes) -> dict[str, Any]:
    if len(data) < 2 or data[0] != 1:
        raise PayloadError("unsupported payload version")
    battery = None if data[1] == 0xFF else float(data[1])
    if fport == PORT_SOIL:
        n = data[2] if len(data) > 2 else -1
        if n < 0 or len(data) != 3 + 5 * n:
            raise PayloadError("soil payload length mismatch")
        depths = []
        for k in range(n):
            depth, moist, temp = struct.unpack_from(">BHh", data, 3 + 5 * k)
            depths.append({"depth_cm": depth, "moisture_pct": _scaled(moist, 0xFFFF, 10),
                           "temp_c": _scaled(temp, 0x7FFF, 10)})
        return {"kind": "soil", "battery_pct": battery, "depths": depths}
    if fport == PORT_WEATHER:
        if len(data) != 16:
            raise PayloadError("weather payload length mismatch")
        t, rh, p, w, wd, rain, sol = struct.unpack_from(">hBHHHHH", data, 2)
        return {"kind": "weather", "battery_pct": battery,
                "air_temp_c": _scaled(t, 0x7FFF, 10), "rh_pct": None if rh == 0xFF else rh / 2,
                "pressure_hpa": _scaled(p, 0xFFFF, 10), "wind_ms": _scaled(w, 0xFFFF, 10),
                "wind_dir_deg": _scaled(wd, 0xFFFF, 1), "precip_mm": _scaled(rain, 0xFFFF, 10),
                "solar_wm2": _scaled(sol, 0xFFFF, 1)}
    raise PayloadError(f"unknown fPort {fport}")


def to_contract(event: dict, registry: dict[str, dict]) -> tuple[str, dict] | None:
    """ChirpStack v4 `event/up` JSON -> (contract topic, payload), or None to drop."""
    info = event.get("deviceInfo") or {}
    dev_eui = str(info.get("devEui") or "").lower()
    device = next((d for d in registry.values()
                   if d.get("transport") == "lorawan" and str(d.get("dev_eui") or "").lower() == dev_eui),
                  None)
    if device is None:
        log.warning("uplink from unregistered devEUI %s dropped", dev_eui or "?")
        return None
    raw = event.get("data")
    if not raw:
        return None
    decoded = decode(int(event.get("fPort") or 0), base64.b64decode(raw))
    kind = decoded.pop("kind")
    if kind != {"soil": "soil", "weather": "weather", "valve": None}.get(device["kind"]):
        log.warning("device %s is registered as %s but sent %s; dropped",
                    device["device_id"], device["kind"], kind)
        return None
    rx = event.get("rxInfo") or []
    payload = {"device_id": device["device_id"], **{k: v for k, v in decoded.items() if v is not None}}
    if kind == "soil":
        payload["depths"] = [{k: v for k, v in d.items() if v is not None} for d in decoded["depths"]]
    if rx:
        payload["rssi"] = max(float(r.get("rssi", -200)) for r in rx)
    if event.get("time"):
        payload["ts"] = event["time"]
    return zone_topic(device["farm"], device["zone"], kind), payload


def run_bridge(registry_path: str) -> None:  # pragma: no cover - needs brokers
    """ChirpStack MQTT (CHIRPSTACK_MQTT_HOST) -> farm broker (AGRIEDGE_MQTT_HOST).

    Publishes with the credentials in MQTT_USERNAME / MQTT_PASSWORD; give it a
    user whose ACL allows writing soil/weather for the LoRa zones.
    """
    import os
    from pathlib import Path

    import paho.mqtt.client as mqtt

    from .provision import load_registry

    registry = load_registry(Path(registry_path))
    out = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="agri-edge-lorawan-out")
    if os.environ.get("MQTT_USERNAME"):
        out.username_pw_set(os.environ["MQTT_USERNAME"], os.environ.get("MQTT_PASSWORD"))
    out.connect(os.environ.get("AGRIEDGE_MQTT_HOST", "127.0.0.1"), 1883, 30)
    out.loop_start()

    src = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="agri-edge-lorawan-in")

    def on_connect(c, *_a):
        c.subscribe("application/+/device/+/event/up", qos=1)

    def on_message(_c, _u, msg):
        try:
            res = to_contract(json.loads(msg.payload), registry)
        except (PayloadError, ValueError, KeyError) as exc:
            log.warning("bad uplink on %s: %s", msg.topic, exc)
            return
        if res:
            out.publish(res[0], json.dumps(res[1]), qos=1)

    src.on_connect = on_connect
    src.on_message = on_message
    src.connect(os.environ.get("CHIRPSTACK_MQTT_HOST", "127.0.0.1"), 1883, 30)
    src.loop_forever()


if __name__ == "__main__":  # pragma: no cover
    import sys

    logging.basicConfig(level=logging.INFO)
    run_bridge(sys.argv[1] if len(sys.argv) > 1 else "ground_iot/mosquitto/devices.json")
