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


# ---------------------------------------------------------------------------
# Operations Station topics (docs/MQTT_CONTRACT.md, section "Operations Station")
#
#   agriedge/{farm}/weather/{station}/observations
#   agriedge/{farm}/soil/{station}/observations
#   agriedge/{farm}/water/{station}/observations
#   agriedge/{farm}/irrigation/{controller}/state      (STATE only -- never a command)
#   agriedge/{farm}/rtk/{station}/state
#   agriedge/{farm}/gateway/{gateway}/health
#   agriedge/{farm}/{vehicle}/detections               (vehicle -> ops, read path)
#
# This parser is for the INGEST (subscribe) side. It accepts only leaves that
# carry data toward the Ops Station, so `irrigation/{c}/set`, `.../arm`,
# `.../mission` and friends all fail to parse. Commands are not ingestible.
# ---------------------------------------------------------------------------

_OPS_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")

OPS_CATEGORY_LEAVES: dict[str, frozenset[str]] = {
    "weather": frozenset({"observations"}),
    "soil": frozenset({"observations"}),
    "water": frozenset({"observations"}),
    "irrigation": frozenset({"state", "events"}),
    "rtk": frozenset({"state"}),
    "gateway": frozenset({"health"}),
}
VEHICLE_LEAVES = frozenset({"detections", "telemetry"})

# Subscription filters the live ingest uses (MQTT wildcards; `+` = one level).
OPS_INGEST_SUBSCRIPTIONS: tuple[str, ...] = (
    "agriedge/+/weather/+/observations",
    "agriedge/+/soil/+/observations",
    "agriedge/+/water/+/observations",
    "agriedge/+/irrigation/+/state",
    "agriedge/+/rtk/+/state",
    "agriedge/+/gateway/+/health",
    "agriedge/+/+/detections",
)


@dataclass(frozen=True)
class OpsTopic:
    farm_id: str
    category: str  # weather|soil|water|irrigation|rtk|gateway|vehicle
    device_id: str
    leaf: str


def ops_topic(farm_id: str, category: str, device_id: str, leaf: str) -> str:
    """Build a canonical Ops topic (publisher side). Raises on anything that is not data."""
    if category == "vehicle":
        if leaf not in VEHICLE_LEAVES:
            raise ValueError(f"unsupported vehicle leaf {leaf!r}")
        topic = f"{TOPIC_PREFIX}/{farm_id}/{device_id}/{leaf}"
    else:
        if leaf not in OPS_CATEGORY_LEAVES.get(category, frozenset()):
            raise ValueError(f"unsupported leaf {leaf!r} for category {category!r}")
        topic = f"{TOPIC_PREFIX}/{farm_id}/{category}/{device_id}/{leaf}"
    parse_ops_topic(topic)  # validates ids + forbidden segments
    return topic


def parse_ops_topic(topic: str) -> OpsTopic:
    """Parse an Ops ingest topic or raise ValueError."""
    t = topic.strip().strip("/")
    _reject_forbidden_segments(t)
    parts = t.split("/")
    if len(parts) < 4 or parts[0] != TOPIC_PREFIX:
        raise ValueError(f"unrecognized ops topic: {topic}")
    for seg in parts[1:]:
        if seg in ("+", "#") or not seg:
            raise ValueError(f"wildcard or empty segment in concrete topic: {topic}")
    if len(parts) == 4:
        _, farm, vehicle, leaf = parts
        if leaf not in VEHICLE_LEAVES:
            raise ValueError(f"unsupported vehicle leaf in topic: {topic}")
        category, device = "vehicle", vehicle
    elif len(parts) == 5:
        _, farm, category, device, leaf = parts
        if leaf not in OPS_CATEGORY_LEAVES.get(category, frozenset()):
            raise ValueError(f"unsupported ops category/leaf in topic: {topic}")
    else:
        raise ValueError(f"unrecognized ops topic: {topic}")
    for ident in (farm, device):
        if not _OPS_ID_RE.match(ident):
            raise ValueError(f"invalid identifier {ident!r} in topic: {topic}")
    return OpsTopic(farm_id=farm, category=category, device_id=device, leaf=leaf)


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT wildcard match: `+` one level, `#` the rest (must be last)."""
    pp, tp = pattern.split("/"), topic.split("/")
    for i, seg in enumerate(pp):
        if seg == "#":
            return i == len(pp) - 1
        if i >= len(tp):
            return False
        if seg != "+" and seg != tp[i]:
            return False
    return len(pp) == len(tp)
