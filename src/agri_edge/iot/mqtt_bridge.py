"""Optional Mosquitto bridge stub (paho-mqtt optional)."""

from __future__ import annotations

from typing import Any, Callable

from agri_edge.iot.mqtt_topics import ParsedTopic, parse_topic


class MqttBridge:
    """Subscribe to agriedge/# and dispatch parsed topics to a callback."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 1883,
        on_message: Callable[[ParsedTopic, bytes], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_message = on_message
        self._client: Any = None

    def connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as e:
            raise ImportError(
                "paho-mqtt is required for live MQTT; pip install paho-mqtt"
            ) from e

        def _on_msg(_client: Any, _userdata: Any, msg: Any) -> None:
            try:
                parsed = parse_topic(msg.topic)
            except ValueError:
                return
            if self.on_message:
                self.on_message(parsed, bytes(msg.payload))

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_message = _on_msg
        client.connect(self.host, self.port, keepalive=30)
        client.subscribe("agriedge/#")
        self._client = client

    def loop_forever(self) -> None:
        if self._client is None:
            raise RuntimeError("call connect() first")
        self._client.loop_forever()
