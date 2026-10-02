"""Treatment decision engine -- master spec Rule 3 gate. SIMULATION ONLY.

STATUS: SIMULATED. There is no real pump, valve, nozzle or motor behind this code
and none may be attached to it. `SimulatedActuator` records commands in a list; that
is all it does. The engine refuses to be constructed with anything whose
`simulated` attribute is not exactly `True`, so wiring in hardware later means
*deliberately* changing this module and its tests, not passing a different object.

RULE 3 (docs/MASTER_IMPLEMENTATION_SPEC.md): "payload safety independent of AI
confidence alone." A treatment may be commanded only if EVERY gate passes:

    1  operator armed          a human armed the system, and the arm has not expired
    2  payload armed           the payload interlock is separately armed
    3  confidence threshold    detection confidence >= threshold (a *necessary* condition)
    4  model validated         the detection's model is `validated_locally` (existing rule)
    5  position valid          a finite, in-range, georeferenced position with bounded
                               uncertainty -- not null-island, not a default
    6  pose valid              the vehicle pose is finite, in range, level enough, FRESH
    7  treatment geofence      the position -- recomputed HERE from lat/lon, not read from
                               the detection's own `in_treatment_zone` flag -- is inside
                               the treatment boundary with margin >= its uncertainty
    8  actuator healthy        healthy, no fault, heartbeat recent
    9  mission state permits   mission is TREATMENT_ACTIVE (not planned/paused/aborted/unknown)
    10 command not expired     a human-issued command exists, is unexpired, has a short TTL,
                               and has not been used before (one command, one actuation)

Anything else -- a missing input, a wrong type, NaN, an exception inside a gate -- is a
refusal. All failing gates are reported, not just the first, so a refusal explains itself.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
* AI output alone can never actuate. A `Detection` carries no authority: its own
  `may_drive_treatment` / `in_treatment_zone` fields are not read as permission. The
  arming state and the command are separate, human-originated objects the model
  cannot construct.
* No path to MAVLink, GPIO, serial, MQTT or the network. Imports are stdlib + numpy
  (via geo) only; `tests/test_decision_engine.py` asserts it.
* Not an independent safety layer. The research report is explicit that the treatment
  interlock belongs on the payload controller's own MCU. A green result from this
  module is necessary, never sufficient.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, Protocol, runtime_checkable

import numpy as np

from agri_edge.geo.geofence import TreatmentGeofence, project_to_local
from agri_edge.geo.georef import VehiclePose, validate_pose

SIMULATION_ONLY = True
ENGINE_ALGORITHM_VERSION = "treatment-gate-1.0.0"

# --- reason codes (stable strings; they land in logs and analytics) ----------
NOT_OPERATOR_ARMED = "NOT_OPERATOR_ARMED"
NOT_PAYLOAD_ARMED = "NOT_PAYLOAD_ARMED"
ARM_EXPIRED = "ARM_EXPIRED"
CONFIDENCE_BELOW_THRESHOLD = "CONFIDENCE_BELOW_THRESHOLD"
MODEL_NOT_VALIDATED = "MODEL_NOT_VALIDATED"
POSITION_INVALID = "POSITION_INVALID"
POSITION_UNCERTAIN = "POSITION_UNCERTAIN"
POSE_INVALID = "POSE_INVALID"
POSE_STALE = "POSE_STALE"
GEOFENCE_UNSET = "GEOFENCE_UNSET"
GEOFENCE_NOT_EVALUATED = "GEOFENCE_NOT_EVALUATED"
OUTSIDE_TREATMENT_GEOFENCE = "OUTSIDE_TREATMENT_GEOFENCE"
ACTUATOR_UNHEALTHY = "ACTUATOR_UNHEALTHY"
ACTUATOR_STALE_HEARTBEAT = "ACTUATOR_STALE_HEARTBEAT"
MISSION_STATE_NOT_PERMITTED = "MISSION_STATE_NOT_PERMITTED"
COMMAND_MISSING = "COMMAND_MISSING"
COMMAND_EXPIRED = "COMMAND_EXPIRED"
COMMAND_INVALID = "COMMAND_INVALID"
COMMAND_REPLAYED = "COMMAND_REPLAYED"
ENGINE_ERROR = "ENGINE_ERROR"

GATES = (
    "operator_armed", "payload_armed", "confidence", "model_validated", "position",
    "pose", "geofence", "actuator", "mission_state", "command",
)


class MissionState(str, Enum):
    IDLE = "IDLE"
    PLANNED = "PLANNED"
    TREATMENT_ACTIVE = "TREATMENT_ACTIVE"   # the only state that permits treatment
    PAUSED = "PAUSED"
    ABORTED = "ABORTED"
    COMPLETE = "COMPLETE"
    FAULT = "FAULT"


PERMITTING_STATES = frozenset({MissionState.TREATMENT_ACTIVE})


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# ---------------------------------------------------------------------------
# human-originated inputs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArmingState:
    """Who armed what, and until when. Built by an operator console, never by a model.

    Both flags must be exactly `True` (not truthy) and `expires_at` must be in the
    future: an arm that nobody renews lapses, which is the safe direction.
    """

    operator_armed: bool = False
    payload_armed: bool = False
    armed_by: str = ""
    armed_at: float = 0.0
    expires_at: float = 0.0


@dataclass(frozen=True)
class TreatmentCommand:
    """An authorisation to treat ONE target, issued by the operator/mission layer."""

    command_id: str
    issued_at: float
    expires_at: float
    issued_by: str = ""
    mission_id: str = ""


@dataclass(frozen=True)
class ActuatorHealth:
    healthy: bool = False
    heartbeat_ts: float = 0.0
    fault_code: Optional[str] = None
    simulated: bool = True


@runtime_checkable
class ActuatorPort(Protocol):
    simulated: bool

    def health(self) -> ActuatorHealth: ...

    def execute(self, record: dict) -> None: ...


class SimulatedActuator:
    """Records commands. Does nothing else -- there is nothing to do nothing *to*.

    `inject_fault` / `set_heartbeat` let tests exercise the unhealthy paths.
    """

    simulated = True
    real = False

    def __init__(self, *, now_fn: Callable[[], float] = time.time) -> None:
        self._now = now_fn
        self.commands: list[dict] = []
        self.fault_code: Optional[str] = None
        self._heartbeat: Optional[float] = None   # None -> "beats now"
        self.healthy_flag = True

    def inject_fault(self, code: Optional[str]) -> None:
        self.fault_code = code

    def set_heartbeat(self, ts: Optional[float]) -> None:
        self._heartbeat = ts

    def health(self) -> ActuatorHealth:
        hb = self._now() if self._heartbeat is None else self._heartbeat
        return ActuatorHealth(healthy=self.healthy_flag, heartbeat_ts=hb,
                              fault_code=self.fault_code, simulated=True)

    def execute(self, record: dict) -> None:
        self.commands.append(dict(record, simulated=True))


# ---------------------------------------------------------------------------
# results + event log
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    gates: dict[str, bool] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)
    algorithm_version: str = ENGINE_ALGORITHM_VERSION
    simulated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed, "reasons": list(self.reasons), "gates": dict(self.gates),
            "detail": dict(self.detail), "algorithm_version": self.algorithm_version,
            "simulated": True,
        }


@dataclass
class TreatmentEvent:
    event_id: str
    ts: float
    kind: str                     # detected | treated | skipped | outside_geofence
    detection_id: str = ""
    command_id: str = ""
    label: str = ""
    confidence: float = 0.0
    lat: Optional[float] = None
    lon: Optional[float] = None
    reasons: list[str] = field(default_factory=list)
    simulated: bool = True

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class TreatmentEventLog:
    """Append-only record of every decision, feeding ops treatment analytics.

    `outside_geofence` is a *subset* of `skipped` (a refusal whose reasons include
    OUTSIDE_TREATMENT_GEOFENCE); both counts are kept because "we declined to spray
    the ditch" and "we declined because the pump was faulted" are different stories.
    """

    def __init__(self) -> None:
        self.events: list[TreatmentEvent] = []
        self._published = 0

    def append(self, ev: TreatmentEvent) -> None:
        self.events.append(ev)

    def counts(self) -> dict[str, Any]:
        detected = sum(1 for e in self.events if e.kind == "detected")
        treated = sum(1 for e in self.events if e.kind == "treated")
        skipped = sum(1 for e in self.events if e.kind in ("skipped", "outside_geofence"))
        outside = sum(1 for e in self.events if e.kind == "outside_geofence")
        by_reason: dict[str, int] = {}
        for e in self.events:
            if e.kind in ("skipped", "outside_geofence"):
                for r in e.reasons:
                    by_reason[r] = by_reason.get(r, 0) + 1
        return {"detected": detected, "treated": treated, "skipped": skipped,
                "outside_geofence": outside, "skip_reasons": by_reason, "simulated": True}

    def publish_to_store(self, store: Any) -> int:
        """Append not-yet-published events to `store.vision_events` (ops §133 analytics).

        Mapping: detected -> weed_detected; treated -> treated; skipped / outside_geofence ->
        skipped (reason = first/all reason codes). Every event is synthetic=True: nothing
        here was applied to a real field.
        """
        from agri_edge.ops.schema import VisionTreatmentEvent

        n = 0
        for e in self.events[self._published:]:
            kind = {"detected": "weed_detected", "treated": "treated"}.get(e.kind, "skipped")
            store.vision_events.append(VisionTreatmentEvent(
                event_id=e.event_id, ts=_iso(e.ts), kind=kind,
                lat=e.lat if e.lat is not None else 0.0,
                lon=e.lon if e.lon is not None else 0.0,
                confidence=e.confidence, reason=",".join(e.reasons), synthetic=True))
            n += 1
        self._published = len(self.events)
        return n


def _iso(ts: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# the engine
# ---------------------------------------------------------------------------

@dataclass
class EngineConfig:
    confidence_threshold: float = 0.85
    max_position_uncertainty_m: float = 1.0
    max_command_ttl_s: float = 30.0
    max_command_future_skew_s: float = 1.0
    max_heartbeat_age_s: float = 2.0
    max_pose_age_s: float = 1.0
    max_tilt_deg: float = 15.0
    permitted_states: frozenset = PERMITTING_STATES

    def __post_init__(self) -> None:
        if not _finite(self.confidence_threshold) or not 0.0 < self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be in (0, 1]; 0 would disable the gate")
        for n in ("max_position_uncertainty_m", "max_command_ttl_s", "max_heartbeat_age_s",
                  "max_pose_age_s"):
            v = getattr(self, n)
            if not _finite(v) or v <= 0:
                raise ValueError(f"{n} must be a positive finite number")


class TreatmentDecisionEngine:
    def __init__(
        self,
        actuator: ActuatorPort,
        geofence: Optional[TreatmentGeofence],
        geofence_origin: Optional[tuple[float, float]],
        config: Optional[EngineConfig] = None,
        *,
        log: Optional[TreatmentEventLog] = None,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        if getattr(actuator, "simulated", None) is not True or getattr(actuator, "real", False):
            raise ValueError(
                "TreatmentDecisionEngine is SIMULATION ONLY: it accepts only an actuator with "
                "simulated=True. Real hardware is BLOCKED-HARDWARE and needs a separate, "
                "reviewed payload-controller interlock."
            )
        self.actuator = actuator
        self.geofence = geofence
        self.geofence_origin = geofence_origin
        self.config = config or EngineConfig()
        self.log = log or TreatmentEventLog()
        self._now = now_fn
        self._used_commands: set[str] = set()
        self._seq = 0

    # -- gate evaluation (pure; never raises) ----------------------------------
    def evaluate(
        self,
        detection: Any,
        *,
        arming: Optional[ArmingState],
        command: Optional[TreatmentCommand],
        pose: Optional[VehiclePose],
        mission_state: Any,
    ) -> Decision:
        now = self._now()
        gates = {g: False for g in GATES}
        reasons: list[str] = []
        detail: dict[str, Any] = {}

        def fail(gate: str, *codes: str) -> None:
            gates[gate] = False
            for c in codes:
                if c not in reasons:
                    reasons.append(c)

        checks: list[tuple[str, Callable[[], None]]] = [
            ("operator_armed", lambda: self._g_operator(arming, now, gates, fail)),
            ("payload_armed", lambda: self._g_payload(arming, now, gates, fail)),
            ("confidence", lambda: self._g_conf(detection, gates, fail)),
            ("model_validated", lambda: self._g_validated(detection, gates, fail)),
            ("position", lambda: self._g_position(detection, gates, fail, detail)),
            ("pose", lambda: self._g_pose(pose, now, gates, fail)),
            ("geofence", lambda: self._g_geofence(detection, gates, fail, detail)),
            ("actuator", lambda: self._g_actuator(now, gates, fail)),
            ("mission_state", lambda: self._g_mission(mission_state, gates, fail)),
            ("command", lambda: self._g_command(command, now, gates, fail)),
        ]
        for gate, fn in checks:
            try:
                fn()
            except Exception as exc:  # fail closed on ANY error inside a gate
                fail(gate, ENGINE_ERROR)
                detail[f"{gate}_error"] = f"{type(exc).__name__}: {exc}"
        allowed = all(gates.values()) and not reasons
        if not allowed and not reasons:      # defensive: a failed gate must explain itself
            reasons.append(ENGINE_ERROR)
        return Decision(allowed=allowed, reasons=reasons, gates=gates, detail=detail)

    # -- the gates -----------------------------------------------------------
    @staticmethod
    def _arm_live(arming: Optional[ArmingState], now: float) -> bool:
        return (arming is not None and _finite(arming.expires_at) and arming.expires_at > now)

    def _g_operator(self, arming, now, gates, fail) -> None:
        if arming is None or arming.operator_armed is not True:
            return fail("operator_armed", NOT_OPERATOR_ARMED)
        if not self._arm_live(arming, now):
            return fail("operator_armed", ARM_EXPIRED)
        if not arming.armed_by:
            return fail("operator_armed", NOT_OPERATOR_ARMED)   # anonymous arm is no arm
        gates["operator_armed"] = True

    def _g_payload(self, arming, now, gates, fail) -> None:
        if arming is None or arming.payload_armed is not True:
            return fail("payload_armed", NOT_PAYLOAD_ARMED)
        if not self._arm_live(arming, now):
            return fail("payload_armed", ARM_EXPIRED)
        gates["payload_armed"] = True

    def _g_conf(self, det, gates, fail) -> None:
        c = _get(det, "confidence")
        if not _finite(c) or not 0.0 <= c <= 1.0 or c < self.config.confidence_threshold:
            return fail("confidence", CONFIDENCE_BELOW_THRESHOLD)
        gates["confidence"] = True

    @staticmethod
    def _g_validated(det, gates, fail) -> None:
        if _get(det, "validated_locally") is not True:
            return fail("model_validated", MODEL_NOT_VALIDATED)
        gates["model_validated"] = True

    def _g_position(self, det, gates, fail, detail) -> None:
        lat = _get(det, "world_lat") if _get(det, "world_lat") is not None else _get(det, "lat")
        lon = _get(det, "world_lon") if _get(det, "world_lon") is not None else _get(det, "lon")
        status = _get(det, "georef_status")
        if not (_finite(lat) and _finite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return fail("position", POSITION_INVALID)
        if lat == 0 and lon == 0:
            return fail("position", POSITION_INVALID)
        if status != "OK":      # includes FLAGGED_*, REJECTED_*, None (never georeferenced)
            return fail("position", POSITION_INVALID)
        unc = _get(det, "position_uncertainty_m")
        if not _finite(unc) or unc < 0 or unc > self.config.max_position_uncertainty_m:
            detail["position_uncertainty_m"] = unc
            return fail("position", POSITION_UNCERTAIN)
        gates["position"] = True

    def _g_pose(self, pose, now, gates, fail) -> None:
        chk = validate_pose(pose, now=now, max_age_s=self.config.max_pose_age_s,
                            max_tilt_deg=self.config.max_tilt_deg)
        if not chk.valid:
            return fail("pose", POSE_STALE if chk.stale else POSE_INVALID)
        gates["pose"] = True

    def _g_geofence(self, det, gates, fail, detail) -> None:
        if self.geofence is None or self.geofence_origin is None:
            return fail("geofence", GEOFENCE_UNSET)
        if not gates.get("position"):
            # Position failed above; do not compute a geofence answer from a bad
            # position. Still a refusal -- but not counted as "outside geofence".
            return fail("geofence", GEOFENCE_NOT_EVALUATED)
        lat = _get(det, "world_lat") if _get(det, "world_lat") is not None else _get(det, "lat")
        lon = _get(det, "world_lon") if _get(det, "world_lon") is not None else _get(det, "lon")
        xy = project_to_local(np.array([lat]), np.array([lon]), self.geofence_origin)[0]
        pt = (float(xy[0]), float(xy[1]))
        margin = self.geofence.treatment_margin_m(pt)
        detail["geofence_margin_m"] = round(margin, 3)
        unc = _get(det, "position_uncertainty_m")
        # Inside the treatment boundary AND clear of it by at least the position error:
        # a point that *might* be across the line is treated as across it.
        if not self.geofence.may_treat(pt) or not _finite(unc) or margin < unc:
            return fail("geofence", OUTSIDE_TREATMENT_GEOFENCE)
        gates["geofence"] = True

    def _g_actuator(self, now, gates, fail) -> None:
        h = self.actuator.health()
        if h.healthy is not True or h.fault_code:
            return fail("actuator", ACTUATOR_UNHEALTHY)
        if not _finite(h.heartbeat_ts) or now - h.heartbeat_ts > self.config.max_heartbeat_age_s \
                or h.heartbeat_ts - now > 1.0:
            return fail("actuator", ACTUATOR_STALE_HEARTBEAT)
        gates["actuator"] = True

    def _g_mission(self, state, gates, fail) -> None:
        try:
            st = state if isinstance(state, MissionState) else MissionState(state)
        except ValueError:
            return fail("mission_state", MISSION_STATE_NOT_PERMITTED)
        if st not in self.config.permitted_states:
            return fail("mission_state", MISSION_STATE_NOT_PERMITTED)
        gates["mission_state"] = True

    def _g_command(self, cmd, now, gates, fail) -> None:
        if cmd is None:
            return fail("command", COMMAND_MISSING)
        if not cmd.command_id or not _finite(cmd.issued_at) or not _finite(cmd.expires_at):
            return fail("command", COMMAND_INVALID)
        if not cmd.issued_by:
            return fail("command", COMMAND_INVALID)          # authorisation needs an author
        ttl = cmd.expires_at - cmd.issued_at
        if ttl <= 0 or ttl > self.config.max_command_ttl_s \
                or cmd.issued_at - now > self.config.max_command_future_skew_s:
            return fail("command", COMMAND_INVALID)
        if cmd.expires_at <= now:
            return fail("command", COMMAND_EXPIRED)
        if cmd.command_id in self._used_commands:
            return fail("command", COMMAND_REPLAYED)
        gates["command"] = True

    # -- action ----------------------------------------------------------------
    def process(
        self,
        detection: Any,
        *,
        arming: Optional[ArmingState],
        command: Optional[TreatmentCommand],
        pose: Optional[VehiclePose],
        mission_state: Any,
    ) -> Decision:
        """Evaluate, then (only if every gate passed) record ONE simulated actuation."""
        dec = self.evaluate(detection, arming=arming, command=command, pose=pose,
                            mission_state=mission_state)
        now = self._now()
        self._seq += 1
        det_id = str(_get(detection, "detection_id") or _get(detection, "id") or f"det_{self._seq}")
        label = str(_get(detection, "label") or "")
        conf = _get(detection, "confidence")
        conf = float(conf) if _finite(conf) else 0.0
        lat = _get(detection, "world_lat") if _get(detection, "world_lat") is not None else _get(detection, "lat")
        lon = _get(detection, "world_lon") if _get(detection, "world_lon") is not None else _get(detection, "lon")
        lat = float(lat) if _finite(lat) else None
        lon = float(lon) if _finite(lon) else None
        cid = command.command_id if command is not None and isinstance(command.command_id, str) else ""

        def ev(kind: str, reasons: Optional[list[str]] = None) -> TreatmentEvent:
            return TreatmentEvent(event_id=f"te_{self._seq}_{kind}", ts=now, kind=kind,
                                  detection_id=det_id, command_id=cid, label=label,
                                  confidence=conf, lat=lat, lon=lon, reasons=reasons or [])

        self.log.append(ev("detected"))
        if not dec.allowed:
            kind = "outside_geofence" if OUTSIDE_TREATMENT_GEOFENCE in dec.reasons else "skipped"
            self.log.append(ev(kind, list(dec.reasons)))
            return dec
        # All gates passed. Consume the command BEFORE actuating so a re-entrant or
        # repeated call cannot fire twice, then record on the simulated actuator.
        self._used_commands.add(command.command_id)  # type: ignore[union-attr]
        self.actuator.execute({
            "command_id": command.command_id,  # type: ignore[union-attr]
            "detection_id": det_id, "label": label, "confidence": conf,
            "lat": lat, "lon": lon, "ts": now,
            "mission_id": command.mission_id,  # type: ignore[union-attr]
            "armed_by": arming.armed_by if arming else "",
        })
        self.log.append(ev("treated"))
        return dec


def _get(obj: Any, key: str) -> Any:
    """Read a field from a Detection object or a dict, tolerating anything else."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
