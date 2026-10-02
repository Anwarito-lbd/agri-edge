"""Optional live-broker smoke test for the PahoTransport (SIMULATED).

Skips unless paho-mqtt is installed AND a broker answers on AGRIEDGE_TEST_MQTT
(default 127.0.0.1:1883 is NOT assumed -- set e.g. AGRIEDGE_TEST_MQTT=127.0.0.1:18830
against a throwaway `mosquitto -p 18830`). Uses its own unique farm id; synthetic data only.
"""
from __future__ import annotations

import os
import socket
import time
import uuid

import pytest

SPEC = os.environ.get("AGRIEDGE_TEST_MQTT", "")


def _reachable() -> bool:
    if not SPEC:
        return False
    try:
        import paho.mqtt.client  # noqa: F401
        host, port = SPEC.rsplit(":", 1)
        with socket.create_connection((host, int(port)), timeout=1):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason="no MQTT broker / paho (set AGRIEDGE_TEST_MQTT)")


def test_real_broker_roundtrip_publish_ingest_dedupe():
    from agri_edge.iot.transport import PahoTransport
    from agri_edge.ops.live_ingest import OpsIngestor
    from agri_edge.ops.mqtt_sim import publish_demo
    from agri_edge.ops.store import OpsStore

    host, port = SPEC.rsplit(":", 1)
    farm = "t" + uuid.uuid4().hex[:8]
    store = OpsStore()
    sub = PahoTransport(host, int(port), client_id="t-sub-" + farm)
    ing = OpsIngestor(store, sub)
    ing.start()
    assert sub.wait_connected(5)
    time.sleep(0.3)
    pub = PahoTransport(host, int(port), client_id="t-pub-" + farm)
    pub.connect()
    assert pub.wait_connected(5)
    try:
        publish_demo(pub, farm=farm, replay=True)
        deadline = time.time() + 5
        while time.time() < deadline and ing.stats["received"] < 14:
            time.sleep(0.05)
        assert ing.stats["accepted"] == 7 and ing.stats["duplicate"] == 7
        assert len(store.weather) == 1 and len(store.detections) == 2
        assert all(d["may_drive_treatment"] is False for d in store.detections)
        with pytest.raises(ValueError):
            pub.publish(f"agriedge/{farm}/irrigation/c1/set", b"{}")
    finally:
        pub.disconnect()
        ing.stop()
