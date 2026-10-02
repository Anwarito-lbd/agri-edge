"""Abstract MQTT transport for the ingest path.

Ops ingest depends on this tiny interface, never on paho-mqtt directly, so:

* tests run against `InMemoryBroker` (no Mosquitto, no sockets, no threads);
* `paho-mqtt` is imported lazily inside `PahoTransport.connect()` and nowhere
  else, keeping the Pi runtime's dependency boundary (numpy + PyYAML) intact;
* the transport can be swapped (MQTT / HTTP / LoRa gateway) without touching the
  domain code -- the Ops Station is transport-agnostic (spec section 117).

SAFETY: this module moves bytes. It never interprets a topic as a command. The
ingest side only subscribes; the only publisher in the tree is the synthetic
simulator, and `assert_publishable` refuses anything that looks like an
actuator or flight command.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable, Protocol, runtime_checkable

from agri_edge.iot.mqtt_topics import FORBIDDEN_SEGMENTS, topic_matches

MessageHandler = Callable[[str, bytes], None]

# Leaves that are commands. Ingest never subscribes to these and the simulator
# publisher refuses to emit them.
_COMMAND_LEAVES = frozenset({"set", "cmd", "command"})


def assert_publishable(topic: str) -> None:
    """Refuse topics that would carry a command (irrigation/set, arm, mission...)."""
    segs = [s for s in topic.strip("/").lower().split("/") if s]
    bad = [s for s in segs if s in FORBIDDEN_SEGMENTS or s in _COMMAND_LEAVES]
    if bad:
        raise ValueError(f"refusing to publish to command-like topic {topic!r} ({bad})")


@runtime_checkable
class MqttTransport(Protocol):
    """Minimal pub/sub surface the ingest + simulator need."""

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def subscribe(self, pattern: str, handler: MessageHandler) -> None: ...

    def publish(self, topic: str, payload: bytes, *, qos: int = 0, retain: bool = False) -> None: ...


class InMemoryBroker:
    """Synchronous in-process broker for tests and loopback demos.

    Delivery is immediate and in subscription order, which makes ingest tests
    deterministic. `retained` mimics MQTT retained messages (delivered to new
    subscribers); `log` records every publish so a test can assert exactly what
    went over the "wire".
    """

    def __init__(self) -> None:
        self._subs: list[tuple[str, MessageHandler]] = []
        self.retained: dict[str, bytes] = {}
        self.log: list[tuple[str, bytes]] = []
        self._lock = threading.RLock()

    def subscribe(self, pattern: str, handler: MessageHandler) -> None:
        with self._lock:
            self._subs.append((pattern, handler))
            replay = [(t, p) for t, p in self.retained.items() if topic_matches(pattern, t)]
        for t, p in replay:
            handler(t, p)

    def publish(self, topic: str, payload: bytes, *, retain: bool = False) -> int:
        with self._lock:
            self.log.append((topic, payload))
            if retain:
                self.retained[topic] = payload
            targets = [h for pat, h in self._subs if topic_matches(pat, topic)]
        for h in targets:
            h(topic, payload)
        return len(targets)


class InMemoryTransport:
    """`MqttTransport` bound to an `InMemoryBroker`."""

    def __init__(self, broker: InMemoryBroker | None = None) -> None:
        self.broker = broker or InMemoryBroker()
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def subscribe(self, pattern: str, handler: MessageHandler) -> None:
        self.broker.subscribe(pattern, handler)

    def publish(self, topic: str, payload: bytes, *, qos: int = 0, retain: bool = False) -> None:
        self.broker.publish(topic, payload, retain=retain)


class PahoTransport:
    """Real MQTT via paho-mqtt (imported lazily; optional extra).

    Credentials come from the environment (`MQTT_USERNAME` / `MQTT_PASSWORD`),
    never from code or config. The local `ground_iot` Mosquitto is anonymous for
    laptop demos only.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        *,
        client_id: str = "",
        keepalive: int = 30,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.keepalive = keepalive
        self.username = username if username is not None else os.environ.get("MQTT_USERNAME")
        self.password = password if password is not None else os.environ.get("MQTT_PASSWORD")
        self._client: Any = None
        self._subs: list[tuple[str, MessageHandler]] = []
        self._lock = threading.RLock()
        self._connected = threading.Event()

    def _dispatch(self, _client: Any, _userdata: Any, msg: Any) -> None:
        topic = str(msg.topic)
        payload = bytes(msg.payload)
        with self._lock:
            handlers = [h for pat, h in self._subs if topic_matches(pat, topic)]
        for h in handlers:
            h(topic, payload)

    def _on_connect(self, client: Any, _userdata: Any, _flags: Any, *_rest: Any) -> None:
        # (re)subscribe on every connect so a broker restart does not silence us
        with self._lock:
            patterns = sorted({pat for pat, _ in self._subs})
        for pat in patterns:
            client.subscribe(pat, qos=1)
        self._connected.set()

    def connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as e:  # pragma: no cover - exercised only without paho
            raise ImportError("paho-mqtt is required for live MQTT: pip install paho-mqtt") from e
        api = getattr(mqtt, "CallbackAPIVersion", None)
        if api is not None:
            client = mqtt.Client(api.VERSION2, client_id=self.client_id)
        else:  # pragma: no cover - paho < 2
            client = mqtt.Client(client_id=self.client_id)
        if self.username:
            client.username_pw_set(self.username, self.password or None)
        client.on_message = self._dispatch
        client.on_connect = self._on_connect
        client.connect(self.host, self.port, keepalive=self.keepalive)
        client.loop_start()
        self._client = client

    def wait_connected(self, timeout_s: float = 5.0) -> bool:
        return self._connected.wait(timeout_s)

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._connected.clear()

    def subscribe(self, pattern: str, handler: MessageHandler) -> None:
        with self._lock:
            self._subs.append((pattern, handler))
        if self._client is not None and self._connected.is_set():
            self._client.subscribe(pattern, qos=1)

    def publish(self, topic: str, payload: bytes, *, qos: int = 0, retain: bool = False) -> None:
        if self._client is None:
            raise RuntimeError("call connect() first")
        assert_publishable(topic)
        info = self._client.publish(topic, payload, qos=qos, retain=retain)
        if qos > 0:
            info.wait_for_publish(timeout=5.0)
