"""Read-only view over the treatment decision engine's event log (Ops UI, master-spec #9).

STATUS: SIMULATED / IMPLEMENTED (read-only dashboard). Nothing here can cause an
actuation, by construction:

* The view holds a *copy* of the engine's event log and *immutable snapshots* of its
  arming state, geofence summary, mission state and actuator health. It is never given
  the engine, the actuator or any callable that can reach them, so even a bug in this
  module or in the page has nothing to call.
* The module imports the decision package for its types and reason codes only. It
  never calls `process`, `evaluate` or `execute` (`tests/test_ops_decisions.py` checks
  that statically).
* The HTTP surface is GET only (`/api/ops/decisions`, `/ops/decisions.html`). There is
  no POST route for it, and the page has no form, button or fetch with a method.

DEMO DATA
---------
`seed_demo_decisions` runs a *synthetic* scenario through a real
`TreatmentDecisionEngine` with a `SimulatedActuator` (the engine refuses anything else)
and attaches the resulting log. Every event is `simulated=True`; none was applied to a
field. The demo's `validated_locally=True` detections are a synthetic assumption used to
exercise the gates -- no real model is locally validated.
"""

from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from agri_edge.decision import engine as E
from agri_edge.decision.engine import ArmingState, TreatmentEventLog

READ_ONLY = True
STATUS = "SIMULATED"
MAX_RECENT = 200

# Reason code -> the gate that raises it (stable; asserted complete by the tests).
REASON_TO_GATE: dict[str, str] = {
    E.NOT_OPERATOR_ARMED: "operator_armed",
    E.ARM_EXPIRED: "operator_armed",
    E.NOT_PAYLOAD_ARMED: "payload_armed",
    E.CONFIDENCE_BELOW_THRESHOLD: "confidence",
    E.MODEL_NOT_VALIDATED: "model_validated",
    E.POSITION_INVALID: "position",
    E.POSITION_UNCERTAIN: "position",
    E.POSE_INVALID: "pose",
    E.POSE_STALE: "pose",
    E.GEOFENCE_UNSET: "geofence",
    E.GEOFENCE_NOT_EVALUATED: "geofence",
    E.OUTSIDE_TREATMENT_GEOFENCE: "geofence",
    E.ACTUATOR_UNHEALTHY: "actuator",
    E.ACTUATOR_STALE_HEARTBEAT: "actuator",
    E.MISSION_STATE_NOT_PERMITTED: "mission_state",
    E.COMMAND_MISSING: "command",
    E.COMMAND_EXPIRED: "command",
    E.COMMAND_INVALID: "command",
    E.COMMAND_REPLAYED: "command",
    E.ENGINE_ERROR: "engine_error",
}

DEFINITIONS = {
    "treated": "every gate passed; ONE simulated actuation was recorded (no real hardware).",
    "skipped": "the engine declined (fail closed); includes the geofence refusals below.",
    "outside_geofence": "subset of skipped: OUTSIDE_TREATMENT_GEOFENCE was among the reasons.",
    "refused_other_gate": "skipped minus outside_geofence: declined for a non-geofence reason.",
    "refusals_by_gate": "counts reason codes per gate; one skipped event can fail several gates.",
    "detected": "detections evaluated (each yields exactly one treated-or-skipped outcome).",
}


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


@dataclass(frozen=True)
class GeofenceSummary:
    configured: bool = False
    origin_lat: Optional[float] = None
    origin_lon: Optional[float] = None
    vertices: int = 0
    holes: int = 0
    treatment_buffer_m: Optional[float] = None
    area_ha: Optional[float] = None


@dataclass(frozen=True)
class ActuatorSnapshot:
    simulated: bool = True
    healthy: bool = False
    fault_code: Optional[str] = None
    heartbeat_ts: float = 0.0


@dataclass
class DecisionView:
    """Everything the decisions page may show. Plain data only -- no engine handle."""

    events: list = field(default_factory=list)          # copies of TreatmentEvent dicts
    arming: Optional[ArmingState] = None
    geofence: GeofenceSummary = field(default_factory=GeofenceSummary)
    mission_state: str = "UNKNOWN"
    actuator: ActuatorSnapshot = field(default_factory=ActuatorSnapshot)
    source: str = "none"                                # "demo" | "engine" | "none"


def geofence_summary(geofence: Any, origin: Optional[tuple[float, float]]) -> GeofenceSummary:
    if geofence is None:
        return GeofenceSummary(configured=False)
    try:
        return GeofenceSummary(
            configured=True,
            origin_lat=float(origin[0]) if origin else None,
            origin_lon=float(origin[1]) if origin else None,
            vertices=int(len(geofence.boundary)),
            holes=int(len(geofence.holes)),
            treatment_buffer_m=float(geofence.treatment_buffer_m),
            area_ha=round(float(geofence.area_ha), 4),
        )
    except Exception:  # noqa: BLE001 -- a broken geofence is reported as unconfigured
        return GeofenceSummary(configured=False)


def attach_decision_source(
    store: Any,
    log: TreatmentEventLog,
    *,
    arming: Optional[ArmingState] = None,
    geofence: Any = None,
    geofence_origin: Optional[tuple[float, float]] = None,
    mission_state: Any = None,
    actuator_health: Any = None,
    source: str = "engine",
) -> DecisionView:
    """Snapshot an engine's log and state onto the ops store (copies only)."""
    ms = getattr(mission_state, "value", mission_state)
    act = ActuatorSnapshot()
    if actuator_health is not None:
        act = ActuatorSnapshot(
            simulated=getattr(actuator_health, "simulated", True) is True,
            healthy=getattr(actuator_health, "healthy", False) is True,
            fault_code=getattr(actuator_health, "fault_code", None),
            heartbeat_ts=float(getattr(actuator_health, "heartbeat_ts", 0.0) or 0.0),
        )
    view = DecisionView(
        events=[copy.deepcopy(e.to_dict()) for e in list(log.events)],
        arming=arming,
        geofence=geofence_summary(geofence, geofence_origin),
        mission_state=str(ms) if ms is not None else "UNKNOWN",
        actuator=act,
        source=source,
    )
    store.decision_view = view
    return view


# ---------------------------------------------------------------------------
# the read-only report
# ---------------------------------------------------------------------------

def decisions_report(store: Any, *, limit: int = 50, now: Optional[float] = None) -> dict[str, Any]:
    """Counts, per-gate refusal reasons, recent decisions and the safety-state readout."""
    now = time.time() if now is None else now
    limit = max(1, min(int(limit), MAX_RECENT))
    view: Optional[DecisionView] = getattr(store, "decision_view", None)
    if view is None:
        view = DecisionView()
    events = list(view.events)

    detected = sum(1 for e in events if e.get("kind") == "detected")
    treated = sum(1 for e in events if e.get("kind") == "treated")
    skipped_ev = [e for e in events if e.get("kind") in ("skipped", "outside_geofence")]
    outside = sum(1 for e in events if e.get("kind") == "outside_geofence")

    by_gate: dict[str, dict[str, int]] = {}
    by_reason: dict[str, int] = {}
    for e in skipped_ev:
        for r in e.get("reasons") or []:
            by_reason[r] = by_reason.get(r, 0) + 1
            gate = REASON_TO_GATE.get(r, "unmapped")
            g = by_gate.setdefault(gate, {})
            g[r] = g.get(r, 0) + 1
    gate_totals = {g: sum(rs.values()) for g, rs in by_gate.items()}

    outcomes = [e for e in events if e.get("kind") in ("treated", "skipped", "outside_geofence")]
    recent = [
        {
            "event_id": e.get("event_id"), "ts": e.get("ts"), "outcome":
            "treated" if e.get("kind") == "treated" else "skipped",
            "kind": e.get("kind"), "detection_id": e.get("detection_id"),
            "label": e.get("label"), "confidence": e.get("confidence"),
            "lat": e.get("lat"), "lon": e.get("lon"),
            "reasons": list(e.get("reasons") or []),
            "gates_failed": sorted({REASON_TO_GATE.get(r, "unmapped")
                                    for r in (e.get("reasons") or [])}),
            "simulated": True,
        }
        for e in reversed(outcomes[-limit:])
    ]

    a = view.arming
    arm_live = bool(a is not None and a.operator_armed is True and a.payload_armed is True
                    and _finite(a.expires_at) and a.expires_at > now and bool(a.armed_by))
    heartbeat_age = (now - view.actuator.heartbeat_ts) if view.actuator.heartbeat_ts else None
    state = {
        "operator_armed": bool(a and a.operator_armed is True),
        "payload_armed": bool(a and a.payload_armed is True),
        "armed_by": a.armed_by if a else "",
        "arm_expires_at": a.expires_at if a else None,
        "arm_seconds_remaining": (round(max(0.0, a.expires_at - now), 1)
                                  if a and _finite(a.expires_at) else None),
        "arm_live": arm_live,
        "arm_note": ("armed and unexpired" if arm_live else
                     "NOT armed (or the arm has lapsed): the engine refuses every treatment"),
        "geofence": {
            "configured": view.geofence.configured,
            "origin_lat": view.geofence.origin_lat, "origin_lon": view.geofence.origin_lon,
            "vertices": view.geofence.vertices, "holes": view.geofence.holes,
            "treatment_buffer_m": view.geofence.treatment_buffer_m,
            "area_ha": view.geofence.area_ha,
            "note": ("treatment boundary is the field inset by the buffer" if view.geofence.configured
                     else "NO geofence: every treatment is refused (GEOFENCE_UNSET)"),
        },
        "mission_state": view.mission_state,
        "mission_permits_treatment": view.mission_state == E.MissionState.TREATMENT_ACTIVE.value,
        "actuator": {
            "simulated": view.actuator.simulated, "healthy": view.actuator.healthy,
            "fault_code": view.actuator.fault_code,
            "heartbeat_age_s": round(heartbeat_age, 1) if heartbeat_age is not None else None,
        },
    }
    return {
        "simulation": getattr(store, "simulation_mode", True),
        "banner": "SIMULATION" if getattr(store, "simulation_mode", True) else None,
        "status": STATUS,
        "read_only": READ_ONLY,
        "source": view.source,
        "counts": {
            "detected": detected, "treated": treated, "skipped": len(skipped_ev),
            "outside_geofence": outside, "refused_other_gate": len(skipped_ev) - outside,
        },
        "definitions": DEFINITIONS,
        "refusals_by_gate": {"totals": gate_totals, "reasons": by_gate, "by_reason": by_reason},
        "recent": recent,
        "state": state,
        "safety_note": ("Read-only. This page cannot arm, command or actuate. Treatment needs "
                        "operator+payload arm, validated model, position, pose, geofence, "
                        "actuator health, mission state and a one-shot command; the actuator "
                        "here is simulated."),
    }


# ---------------------------------------------------------------------------
# synthetic demo
# ---------------------------------------------------------------------------

_DEMO_ORIGIN = (45.4010, -75.6980)
_M_PER_DEG_LAT = 111_320.0


def _ll(east_m: float, north_m: float) -> tuple[float, float]:
    lat = _DEMO_ORIGIN[0] + north_m / _M_PER_DEG_LAT
    lon = _DEMO_ORIGIN[1] + east_m / (_M_PER_DEG_LAT * math.cos(math.radians(_DEMO_ORIGIN[0])))
    return lat, lon


def seed_demo_decisions(store: Any, *, now: Optional[float] = None) -> DecisionView:
    """Run a SYNTHETIC scenario through the real (simulated-only) engine and attach it."""
    from agri_edge.decision import (
        EngineConfig,
        MissionState,
        SimulatedActuator,
        TreatmentCommand,
        TreatmentDecisionEngine,
    )
    from agri_edge.geo.geofence import TreatmentGeofence
    from agri_edge.geo.georef import VehiclePose
    from agri_edge.inference.engine import Detection

    t = time.time() if now is None else now
    field_m = np.array([[-100.0, -100.0], [100.0, -100.0], [100.0, 100.0], [-100.0, 100.0]])
    act = SimulatedActuator(now_fn=lambda: t)
    eng = TreatmentDecisionEngine(
        act, TreatmentGeofence(field_m, treatment_buffer_m=10.0), _DEMO_ORIGIN,
        EngineConfig(), now_fn=lambda: t)
    arming = ArmingState(operator_armed=True, payload_armed=True, armed_by="demo-operator",
                         armed_at=t - 30, expires_at=t + 3600)
    pose = VehiclePose(lat=_DEMO_ORIGIN[0], lon=_DEMO_ORIGIN[1], alt_agl_m=30.0,
                       heading_deg=0.0, timestamp=t, h_acc_m=0.02)
    stale_pose = VehiclePose(lat=_DEMO_ORIGIN[0], lon=_DEMO_ORIGIN[1], alt_agl_m=30.0,
                             heading_deg=0.0, timestamp=t - 60, h_acc_m=0.02)

    def det(east: float, north: float, conf: float = 0.95, validated: bool = True,
            label: str = "weed", unc: float = 0.3) -> Detection:
        d = Detection(label=label, confidence=conf, bbox=(0.4, 0.4, 0.6, 0.6),
                      validated_locally=validated)
        d.world_lat, d.world_lon = _ll(east, north)
        d.lat, d.lon = d.world_lat, d.world_lon
        d.position_uncertainty_m = unc
        d.georef_status = "OK"
        return d

    def cmd(i: int) -> TreatmentCommand:
        return TreatmentCommand(command_id=f"demo-cmd-{i}", issued_at=t - 1, expires_at=t + 10,
                                issued_by="demo-operator", mission_id="demo-mission")

    active = MissionState.TREATMENT_ACTIVE
    scenario = [
        (det(0, 0), cmd(1), pose, active),                          # treated
        (det(20, -15), cmd(2), pose, active),                       # treated
        (det(-40, 30), cmd(3), pose, active),                       # treated
        (det(95, 0), cmd(4), pose, active),                         # inside field, within buffer
        (det(300, 0), cmd(5), pose, active),                        # outside the field
        (det(10, 10, conf=0.6), cmd(6), pose, active),              # low confidence
        (det(-10, 5, validated=False), cmd(7), pose, active),       # model not locally validated
        (det(5, 5), cmd(8), stale_pose, active),                    # stale pose
        (det(5, -5), cmd(9), pose, MissionState.PAUSED),            # mission paused
        (det(30, 30, unc=5.0), cmd(10), pose, active),              # position too uncertain
        (det(1, 1), None, pose, active),                            # no command issued
        (det(60, 60), cmd(11), pose, active),                       # treated
    ]
    for d, c, p, m in scenario:
        eng.process(d, arming=arming, command=c, pose=p, mission_state=m)
    # one replay: the first command is used up
    eng.process(det(0, 0), arming=arming, command=cmd(1), pose=pose, mission_state=active)

    return attach_decision_source(
        store, eng.log, arming=arming, geofence=eng.geofence, geofence_origin=_DEMO_ORIGIN,
        mission_state=active, actuator_health=act.health(), source="demo")
