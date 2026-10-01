"""Subscribe the ops station to the farm's MQTT bus.

Every message on `agriedge/#` goes through `ops/ingest.py` -- the same function
`POST /api/ops/ingest` uses. Started by `serve()` when AGRIEDGE_MQTT_HOST is set;
credentials come from MQTT_USERNAME / MQTT_PASSWORD (the broker's `agriedge`
user, which the ACL allows to read and nothing else).

Needs paho-mqtt (the `mqtt` extra).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from .ingest import IngestError, ingest
from .store import OpsStore

log = logging.getLogger(__name__)


def handle_message(store: OpsStore, lock: threading.Lock, topic: str, payload: bytes) -> bool:
    """One MQTT message. Returns whether it was accepted. Never raises: a bad
    message from one device must not stop the subscriber for all of them."""
    try:
        with lock:
            ingest(store, topic, payload)
        return True
    except IngestError as exc:
        log.warning("rejected %s: %s", topic, exc)
    except Exception:  # noqa: BLE001
        log.exception("ingest failed for %s", topic)
    return False


def start_subscriber(store: OpsStore, lock: threading.Lock) -> Any:  # pragma: no cover - needs a broker
    host = os.environ.get("AGRIEDGE_MQTT_HOST")
    if not host:
        return None
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise RuntimeError("AGRIEDGE_MQTT_HOST is set but paho-mqtt is missing: "
                           "pip install 'agri-edge[mqtt]'") from exc

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="agri-edge-ops")
    user = os.environ.get("MQTT_USERNAME")
    if user:
        client.username_pw_set(user, os.environ.get("MQTT_PASSWORD"))
    if os.environ.get("AGRIEDGE_MQTT_TLS") == "1":
        client.tls_set()

    def on_connect(c, _userdata, _flags, reason_code, _props=None):
        # Subscribe here, not once after connect: paho reconnects on its own and
        # a subscription made outside on_connect is lost with the session.
        log.info("MQTT connected (%s); subscribing to agriedge/#", reason_code)
        c.subscribe("agriedge/#", qos=1)

    def on_message(_c, _userdata, msg):
        handle_message(store, lock, msg.topic, bytes(msg.payload))

    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.connect_async(host, int(os.environ.get("AGRIEDGE_MQTT_PORT", "1883")), keepalive=30)
    client.loop_start()
    return client
