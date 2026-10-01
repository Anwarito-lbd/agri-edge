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
_VEHICLE_RE = re.compile(
    r"^agriedge/farm/(?P<farm>[^/]+)/vehicle/(?P<vehicle>[^/]+)/(?P<kind>.+)$"
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

# What a scouting vehicle REPORTS. There is deliberately no vehicle kind that
# carries a command: the companion computer's link to the aircraft is read-only,
# and nothing on this bus may become a way around that.
VEHICLE_KINDS = frozenset({"detections", "health"})

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
    # Set for vehicle topics, where zone_id is "".
    vehicle_id: str | None = None

    def is_irrigation_command(self) -> bool:
        return self.vehicle_id is None and self.kind == "irrigation/set"

    @property
    def is_vehicle(self) -> bool:
        return self.vehicle_id is not None


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


def vehicle_topic(farm_id: str, vehicle_id: str, kind: str) -> str:
    """Build a canonical vehicle report topic."""
    if kind not in VEHICLE_KINDS:
        raise ValueError(f"unsupported vehicle kind {kind!r}; allowed={sorted(VEHICLE_KINDS)}")
    topic = f"{TOPIC_PREFIX}/farm/{farm_id}/vehicle/{vehicle_id}/{kind}"
    _reject_forbidden_segments(topic)
    return topic


def parse_topic(topic: str) -> ParsedTopic:
    """Parse a topic or raise ValueError."""
    t = topic.strip().strip("/")
    _reject_forbidden_segments(t)
    v = _VEHICLE_RE.match(t)
    if v:
        if v.group("kind") not in VEHICLE_KINDS:
            raise ValueError(f"unsupported vehicle kind in topic: {v.group('kind')}")
        return ParsedTopic(farm_id=v.group("farm"), zone_id="",
                           kind=v.group("kind"), vehicle_id=v.group("vehicle"))
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
