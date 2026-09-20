"""MQTT topic helpers for ground IoT (Mosquitto / Node-RED).

Aircraft MAVLink is out of scope here. Irrigation commands are ground actuators
only — never bridge them to the flight stack.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TOPIC_PREFIX = "agriedge"

_ZONE_RE = re.compile(
    r"^agriedge/farm/(?P<farm>[^/]+)/zone/(?P<zone>[^/]+)/(?P<kind>.+)$"
)

ALLOWED_KINDS = frozenset(
    {
        "soil",
        "weather",
        "status",
        "irrigation/set",
        "irrigation/status",
    }
)

# Matched as whole path segments only (so "farm" does not trip "arm").
FORBIDDEN_SEGMENTS = frozenset(
    {
        "mavlink",
        "arm",
        "mode",
        "mission",
        "rtl",
        "aircraft",
        "pixhawk",
        "disarm",
    }
)


@dataclass(frozen=True)
class ParsedTopic:
    farm_id: str
    zone_id: str
    kind: str

    def is_irrigation_command(self) -> bool:
        return self.kind == "irrigation/set"


def _segments(topic: str) -> list[str]:
    return [s for s in topic.strip().strip("/").lower().split("/") if s]


def _reject_forbidden_segments(topic: str) -> None:
    for seg in _segments(topic):
        if seg in FORBIDDEN_SEGMENTS:
            raise ValueError(f"forbidden topic segment {seg!r}: {topic}")
        # kind may be multi-segment e.g. irrigation/set — already split


def zone_topic(farm_id: str, zone_id: str, kind: str) -> str:
    """Build a canonical zone topic."""
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"unsupported kind {kind!r}; allowed={sorted(ALLOWED_KINDS)}")
    topic = f"{TOPIC_PREFIX}/farm/{farm_id}/zone/{zone_id}/{kind}"
    _reject_forbidden_segments(topic)
    return topic


def parse_topic(topic: str) -> ParsedTopic:
    """Parse a topic or raise ValueError."""
    t = topic.strip().strip("/")
    _reject_forbidden_segments(t)
    m = _ZONE_RE.match(t)
    if not m:
        raise ValueError(f"unrecognized topic: {topic}")
    kind = m.group("kind")
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"unsupported kind in topic: {kind}")
    return ParsedTopic(
        farm_id=m.group("farm"),
        zone_id=m.group("zone"),
        kind=kind,
    )


def assert_not_flight_command(topic: str) -> None:
    """Explicit guard for bridges — irrigation/set is OK; arm/mode is not."""
    parse_topic(topic)
