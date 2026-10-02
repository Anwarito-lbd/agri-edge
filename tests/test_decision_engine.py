"""Rule 3 treatment gate -- SIMULATION ONLY. Every gate must fail closed.

Style: a known-good baseline that PASSES every gate, then (a) one mutation per gate
that must flip the result to a refusal naming that gate's reason, (b) exhaustive
pairs/subsets of mutations (never allowed once any gate is broken), (c) seeded random
fuzzing of every input including NaN/inf/wrong types (never allowed unless the input
is genuinely good, never raises).
"""
from __future__ import annotations

import ast
import itertools
import math
import random
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from agri_edge.decision import engine as E
from agri_edge.decision import (
    ActuatorHealth,
    ArmingState,
    EngineConfig,
    MissionState,
    SimulatedActuator,
    TreatmentCommand,
    TreatmentDecisionEngine,
    TreatmentEventLog,
)
from agri_edge.geo.geofence import TreatmentGeofence
from agri_edge.geo.georef import VehiclePose
from agri_edge.inference.engine import Detection

NOW = 2_000_000.0
ORIGIN = (49.8951, -97.1384)
M_PER_DEG_LAT = 111_320.0
# 200 m x 200 m field in local metres, 10 m treatment buffer
FIELD = np.array([[-100.0, -100.0], [100.0, -100.0], [100.0, 100.0], [-100.0, 100.0]])


def latlon(east_m, north_m):
    lat = ORIGIN[0] + north_m / M_PER_DEG_LAT
    lon = ORIGIN[1] + east_m / (M_PER_DEG_LAT * math.cos(math.radians(ORIGIN[0])))
    return lat, lon


def good_detection(**kw):
    lat, lon = latlon(0.0, 0.0)
    d = Detection(label="weed", confidence=0.95, bbox=(0.4, 0.4, 0.6, 0.6),
                  validated_locally=True)
    d.world_lat = d.lat = lat
    d.world_lon = d.lon = lon
    d.position_uncertainty_m = 0.3
    d.georef_status = "OK"
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def good_pose(**kw):
    base = dict(lat=ORIGIN[0], lon=ORIGIN[1], alt_agl_m=30.0, heading_deg=0.0,
                timestamp=NOW, h_acc_m=0.02)
    base.update(kw)
    return VehiclePose(**base)


def good_arming(**kw):
    base = dict(operator_armed=True, payload_armed=True, armed_by="alice",
                armed_at=NOW - 5, expires_at=NOW + 60)
    base.update(kw)
    return ArmingState(**base)


def good_command(cid="cmd1", **kw):
    base = dict(command_id=cid, issued_at=NOW - 1, expires_at=NOW + 10, issued_by="alice",
                mission_id="m1")
    base.update(kw)
    return TreatmentCommand(**base)


def make_engine(actuator=None, **cfg):
    act = actuator or SimulatedActuator(now_fn=lambda: NOW)
    eng = TreatmentDecisionEngine(
        act, TreatmentGeofence(FIELD, treatment_buffer_m=10.0), ORIGIN,
        EngineConfig(**cfg), now_fn=lambda: NOW)
    return eng, act


def baseline_inputs():
    return dict(detection=good_detection(), arming=good_arming(), command=good_command(),
                pose=good_pose(), mission_state=MissionState.TREATMENT_ACTIVE)


def run(eng, inputs):
    return eng.process(inputs["detection"], arming=inputs["arming"], command=inputs["command"],
                       pose=inputs["pose"], mission_state=inputs["mission_state"])


# ---- mutations: each breaks exactly one gate -------------------------------------
def _mut_operator(i, act):  i["arming"] = replace(i["arming"], operator_armed=False)
def _mut_payload(i, act):   i["arming"] = replace(i["arming"], payload_armed=False)
def _mut_conf(i, act):      i["detection"].confidence = 0.5
def _mut_validated(i, act): i["detection"].validated_locally = False
def _mut_position(i, act):
    i["detection"].world_lat = None
    i["detection"].lat = None
def _mut_pose(i, act):      i["pose"] = good_pose(alt_agl_m=0.0)
def _mut_geofence(i, act):
    lat, lon = latlon(95.0, 0.0)          # inside the field but inside the 10 m buffer
    d = i["detection"]
    d.world_lat = d.lat = lat
    d.world_lon = d.lon = lon
def _mut_actuator(i, act):  act.inject_fault("PUMP_OVERCURRENT")
def _mut_mission(i, act):   i["mission_state"] = MissionState.PAUSED
def _mut_command(i, act):   i["command"] = good_command(expires_at=NOW - 0.1)


MUTATIONS = {
    "operator_armed": (_mut_operator, E.NOT_OPERATOR_ARMED),
    "payload_armed": (_mut_payload, E.NOT_PAYLOAD_ARMED),
    "confidence": (_mut_conf, E.CONFIDENCE_BELOW_THRESHOLD),
    "model_validated": (_mut_validated, E.MODEL_NOT_VALIDATED),
    "position": (_mut_position, E.POSITION_INVALID),
    "pose": (_mut_pose, E.POSE_INVALID),
    "geofence": (_mut_geofence, E.OUTSIDE_TREATMENT_GEOFENCE),
    "actuator": (_mut_actuator, E.ACTUATOR_UNHEALTHY),
    "mission_state": (_mut_mission, E.MISSION_STATE_NOT_PERMITTED),
    "command": (_mut_command, E.COMMAND_EXPIRED),
}


def test_every_gate_has_a_mutation():
    assert set(MUTATIONS) == set(E.GATES)


def test_baseline_treats_exactly_once_on_the_simulated_actuator():
    eng, act = make_engine()
    dec = run(eng, baseline_inputs())
    assert dec.allowed and dec.reasons == [] and all(dec.gates.values())
    assert dec.simulated is True
    assert len(act.commands) == 1 and act.commands[0]["simulated"] is True
    assert eng.log.counts()["treated"] == 1


@pytest.mark.parametrize("gate", E.GATES)
def test_each_gate_failing_alone_refuses_with_explicit_reason(gate):
    mut, reason = MUTATIONS[gate]
    eng, act = make_engine()
    inp = baseline_inputs()
    mut(inp, act)
    dec = run(eng, inp)
    assert dec.allowed is False
    assert reason in dec.reasons
    assert dec.gates[gate] is False
    assert act.commands == []
    c = eng.log.counts()
    assert c["treated"] == 0 and c["skipped"] == 1


@pytest.mark.parametrize("n", [2, 3])
def test_any_combination_of_broken_gates_never_actuates(n):
    for combo in itertools.combinations(sorted(MUTATIONS), n):
        eng, act = make_engine()
        inp = baseline_inputs()
        for g in combo:
            MUTATIONS[g][0](inp, act)
        dec = run(eng, inp)
        assert dec.allowed is False, combo
        assert act.commands == [], combo
        for g in combo:
            assert dec.gates[g] is False, (combo, g)
            assert MUTATIONS[g][1] in dec.reasons or (
                g == "geofence" and E.GEOFENCE_NOT_EVALUATED in dec.reasons), (combo, g)


def test_all_gates_broken_reports_every_reason():
    eng, act = make_engine()
    inp = baseline_inputs()
    for g in sorted(MUTATIONS, key=lambda g: g == "position"):   # position last: it clears lat/lon
        MUTATIONS[g][0](inp, act)
    dec = run(eng, inp)
    assert not dec.allowed and act.commands == []
    assert not any(dec.gates.values())
    assert len(dec.reasons) >= 9


# ---- specific boundary behaviour -------------------------------------------------

def test_confidence_threshold_is_inclusive_and_necessary_not_sufficient():
    eng, act = make_engine(confidence_threshold=0.85)
    inp = baseline_inputs()
    inp["detection"] = good_detection(confidence=0.85)
    assert run(eng, inp).allowed
    # confidence 1.0 does NOT rescue a broken gate (AI alone cannot actuate)
    eng2, act2 = make_engine()
    inp2 = baseline_inputs()
    inp2["detection"] = good_detection(confidence=1.0, validated_locally=False)
    assert not run(eng2, inp2).allowed and act2.commands == []


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.5, float("nan"), float("inf"), "0.9", None])
def test_bad_confidence_values_refused(bad):
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["detection"] = good_detection(confidence=bad)
    assert not run(eng, inp).allowed and act.commands == []


def test_config_cannot_disable_the_confidence_gate():
    for bad in (0.0, -1.0, 1.01, float("nan")):
        with pytest.raises(ValueError):
            EngineConfig(confidence_threshold=bad)


def test_expired_arm_refuses_even_though_flags_are_true():
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["arming"] = good_arming(expires_at=NOW - 1)
    dec = run(eng, inp)
    assert not dec.allowed and E.ARM_EXPIRED in dec.reasons and act.commands == []


def test_anonymous_arm_refused():
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["arming"] = good_arming(armed_by="")
    assert not run(eng, inp).allowed


def test_truthy_but_not_true_arm_flag_refused():
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["arming"] = good_arming(operator_armed=1)  # type: ignore[arg-type]
    assert not run(eng, inp).allowed and act.commands == []


@pytest.mark.parametrize("state", [s for s in MissionState if s != MissionState.TREATMENT_ACTIVE]
                         + ["TREATMENT_ACTIVE ", "unknown", None, 7])
def test_only_treatment_active_permits(state):
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["mission_state"] = state
    assert not run(eng, inp).allowed and act.commands == []


def test_mission_state_accepts_the_string_value_of_the_permitting_state():
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["mission_state"] = "TREATMENT_ACTIVE"
    assert run(eng, inp).allowed


def test_command_replay_refused():
    eng, act = make_engine()
    assert run(eng, baseline_inputs()).allowed
    second = run(eng, baseline_inputs())            # same command_id
    assert not second.allowed and E.COMMAND_REPLAYED in second.reasons
    assert len(act.commands) == 1


@pytest.mark.parametrize("cmd", [
    None,
    good_command(expires_at=NOW - 0.001),
    good_command(expires_at=NOW),
    good_command(issued_at=NOW + 100, expires_at=NOW + 110),   # from the future
    good_command(expires_at=NOW + 3600),                       # TTL far too long
    good_command(issued_at=NOW, expires_at=NOW - 5),           # negative TTL
    good_command(cid=""),
    good_command(issued_by=""),
    good_command(expires_at=float("nan")),
])
def test_bad_commands_refused(cmd):
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["command"] = cmd
    dec = run(eng, inp)
    assert not dec.allowed and act.commands == []
    assert any(r.startswith("COMMAND_") for r in dec.reasons)


@pytest.mark.parametrize("pose_kw,code", [
    (dict(timestamp=NOW - 30), E.POSE_STALE),
    (dict(timestamp=0.0), E.POSE_STALE),
    (dict(roll_deg=20.0), E.POSE_INVALID),            # beyond the engine's 15 deg limit
    (dict(lat=float("nan")), E.POSE_INVALID),
    (dict(heading_deg=float("nan")), E.POSE_INVALID),
])
def test_bad_pose_refused(pose_kw, code):
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["pose"] = good_pose(**pose_kw)
    dec = run(eng, inp)
    assert not dec.allowed and code in dec.reasons and act.commands == []


def test_missing_pose_refused():
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["pose"] = None
    assert not run(eng, inp).allowed and act.commands == []


@pytest.mark.parametrize("kw", [
    dict(georef_status=None), dict(georef_status="FLAGGED_UNCERTAINTY_HIGH"),
    dict(georef_status="REJECTED_POSE_STALE"),
    dict(world_lat=0.0, lat=0.0, world_lon=0.0, lon=0.0),
    dict(world_lat=float("nan"), lat=float("nan")),
    dict(world_lon=500.0, lon=500.0),
    dict(position_uncertainty_m=None), dict(position_uncertainty_m=5.0),
    dict(position_uncertainty_m=float("nan")), dict(position_uncertainty_m=-1.0),
])
def test_bad_position_refused(kw):
    eng, act = make_engine()
    inp = baseline_inputs()
    inp["detection"] = good_detection(**kw)
    dec = run(eng, inp)
    assert not dec.allowed and act.commands == []
    assert E.POSITION_INVALID in dec.reasons or E.POSITION_UNCERTAIN in dec.reasons


def test_detection_own_geofence_flag_is_not_trusted():
    """in_treatment_zone=True on the detection does not override the engine's own check."""
    eng, act = make_engine()
    lat, lon = latlon(500.0, 500.0)    # far outside the field
    d = good_detection(world_lat=lat, lat=lat, world_lon=lon, lon=lon,
                       in_treatment_zone=True)
    assert d.may_drive_treatment is True      # the old flag says yes...
    inp = baseline_inputs()
    inp["detection"] = d
    dec = run(eng, inp)
    assert not dec.allowed and E.OUTSIDE_TREATMENT_GEOFENCE in dec.reasons   # ...the engine says no
    assert act.commands == []


def test_may_drive_treatment_alone_never_actuates():
    """AI output alone can never trigger actuation: no arming, no command, no mission."""
    eng, act = make_engine()
    d = good_detection(in_treatment_zone=True)
    assert d.may_drive_treatment is True
    dec = eng.process(d, arming=None, command=None, pose=None, mission_state=None)
    assert not dec.allowed and act.commands == []
    assert {E.NOT_OPERATOR_ARMED, E.NOT_PAYLOAD_ARMED, E.COMMAND_MISSING}.issubset(dec.reasons)


def test_geofence_margin_must_exceed_position_uncertainty():
    eng, act = make_engine()
    # 5 m inside the 10 m buffer line: margin ~5 m
    lat, lon = latlon(85.0, 0.0)
    far = good_detection(world_lat=lat, lat=lat, world_lon=lon, lon=lon, position_uncertainty_m=0.5)
    inp = baseline_inputs()
    inp["detection"] = far
    assert run(eng, inp).allowed
    eng2, act2 = make_engine()
    lat, lon = latlon(89.5, 0.0)     # 0.5 m inside the buffer line, uncertainty 1.0
    close = good_detection(world_lat=lat, lat=lat, world_lon=lon, lon=lon, position_uncertainty_m=1.0)
    inp2 = baseline_inputs()
    inp2["detection"] = close
    dec = run(eng2, inp2)
    assert not dec.allowed and E.OUTSIDE_TREATMENT_GEOFENCE in dec.reasons
    assert dec.detail["geofence_margin_m"] < 1.0


def test_no_geofence_configured_refuses():
    act = SimulatedActuator(now_fn=lambda: NOW)
    eng = TreatmentDecisionEngine(act, None, None, now_fn=lambda: NOW)
    dec = run(eng, baseline_inputs())
    assert not dec.allowed and E.GEOFENCE_UNSET in dec.reasons and act.commands == []


def test_actuator_stale_heartbeat_and_fault_and_unhealthy():
    for setup, code in (
        (lambda a: a.set_heartbeat(NOW - 60), E.ACTUATOR_STALE_HEARTBEAT),
        (lambda a: a.inject_fault("X"), E.ACTUATOR_UNHEALTHY),
        (lambda a: setattr(a, "healthy_flag", False), E.ACTUATOR_UNHEALTHY),
        (lambda a: a.set_heartbeat(NOW + 60), E.ACTUATOR_STALE_HEARTBEAT),
    ):
        eng, act = make_engine()
        setup(act)
        dec = run(eng, baseline_inputs())
        assert not dec.allowed and code in dec.reasons and act.commands == []


def test_exception_inside_a_gate_fails_closed():
    class Boom(SimulatedActuator):
        def health(self):
            raise RuntimeError("bus error")

    eng, act = make_engine(actuator=Boom(now_fn=lambda: NOW))
    dec = run(eng, baseline_inputs())
    assert not dec.allowed and E.ENGINE_ERROR in dec.reasons and act.commands == []
    assert "actuator_error" in dec.detail


# ---- simulation-only enforcement --------------------------------------------------

def test_engine_refuses_non_simulated_actuator():
    class RealPump:
        simulated = False
        def health(self): return ActuatorHealth(True, NOW)
        def execute(self, r): raise AssertionError("must never be called")

    with pytest.raises(ValueError, match="SIMULATION ONLY"):
        TreatmentDecisionEngine(RealPump(), None, None)

    class Lying(RealPump):
        simulated = True
        real = True
    with pytest.raises(ValueError):
        TreatmentDecisionEngine(Lying(), None, None)

    class NoFlag:
        def health(self): return ActuatorHealth(True, NOW)
        def execute(self, r): pass
    with pytest.raises(ValueError):
        TreatmentDecisionEngine(NoFlag(), None, None)


def test_simulated_actuator_only_records():
    a = SimulatedActuator()
    assert a.simulated is True and a.real is False
    a.execute({"x": 1})
    assert a.commands == [{"x": 1, "simulated": True}]


def test_decision_package_has_no_hardware_or_network_imports():
    forbidden = {"serial", "socket", "pymavlink", "RPi", "gpiozero", "smbus", "smbus2",
                 "paho", "requests", "urllib", "http", "asyncio", "subprocess", "ctypes",
                 "spidev", "can", "pigpio"}
    root = Path(E.__file__).parent
    for py in root.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            assert not (set(names) & forbidden), (py.name, names)
    assert E.SIMULATION_ONLY is True


# ---- seeded fuzz ("property-style") -----------------------------------------------

JUNK = [None, float("nan"), float("inf"), float("-inf"), -1, 0, 1e18, "x", "", [], {}, True, False,
        object()]


def _fuzz_detection(rng):
    d = good_detection()
    for attr in ("confidence", "validated_locally", "world_lat", "world_lon", "lat", "lon",
                 "position_uncertainty_m", "georef_status"):
        if rng.random() < 0.35:
            setattr(d, attr, rng.choice(JUNK))
    return d


def test_fuzz_never_raises_and_never_actuates_unless_genuinely_good():
    rng = random.Random(1337)
    actuations = 0
    for _ in range(1500):
        eng, act = make_engine()
        inp = baseline_inputs()
        inp["detection"] = _fuzz_detection(rng)
        if rng.random() < 0.3:
            inp["arming"] = rng.choice([None, good_arming(operator_armed=rng.choice(JUNK)),
                                        good_arming(payload_armed=rng.choice(JUNK)),
                                        good_arming(expires_at=rng.choice(JUNK + [NOW - 1]))])
        if rng.random() < 0.3:
            inp["command"] = rng.choice([None, good_command(command_id=rng.choice(JUNK)),
                                         good_command(expires_at=rng.choice(JUNK + [NOW - 1])),
                                         good_command(issued_by=rng.choice(JUNK))])
        if rng.random() < 0.3:
            inp["pose"] = rng.choice([None, good_pose(lat=rng.choice(JUNK)),
                                      good_pose(alt_agl_m=rng.choice(JUNK)),
                                      good_pose(timestamp=rng.choice(JUNK + [NOW - 99]))])
        if rng.random() < 0.3:
            inp["mission_state"] = rng.choice(JUNK + ["PAUSED", "IDLE"])
        if rng.random() < 0.2:
            act.inject_fault(rng.choice(["F", None]))
            if rng.random() < 0.5:
                act.set_heartbeat(rng.choice([NOW - 99, float("nan"), NOW + 99]))
        dec = run(eng, inp)          # must not raise
        if dec.allowed:
            actuations += 1
            # an allowed decision must be one where EVERY input really was good
            d = inp["detection"]
            assert d.confidence >= 0.85 and d.validated_locally is True
            assert d.georef_status == "OK" and d.position_uncertainty_m <= 1.0
            assert inp["arming"].operator_armed is True and inp["arming"].payload_armed is True
            assert inp["mission_state"] in (MissionState.TREATMENT_ACTIVE, "TREATMENT_ACTIVE")
            assert inp["command"].expires_at > NOW and inp["command"].command_id
            assert inp["pose"].timestamp > 0 and not act.fault_code
            assert len(act.commands) == 1
        else:
            assert act.commands == [] and dec.reasons
    assert actuations > 0     # the fuzz does include untouched-good cases


# ---- event log -> ops analytics --------------------------------------------------

def test_event_log_counts_and_feeds_ops_analytics():
    from agri_edge.ops.analytics import application_analytics
    from agri_edge.ops.store import OpsStore

    eng, act = make_engine()
    # 1 treated
    assert run(eng, baseline_inputs()).allowed
    # 2 outside geofence
    inp = baseline_inputs()
    inp["command"] = good_command("c2")
    MUTATIONS["geofence"][0](inp, act)
    run(eng, inp)
    # 3 skipped (low confidence)
    inp = baseline_inputs()
    inp["command"] = good_command("c3")
    MUTATIONS["confidence"][0](inp, act)
    run(eng, inp)

    counts = eng.log.counts()
    assert counts["detected"] == 3 and counts["treated"] == 1
    assert counts["skipped"] == 2 and counts["outside_geofence"] == 1
    assert counts["skip_reasons"][E.OUTSIDE_TREATMENT_GEOFENCE] == 1
    assert counts["simulated"] is True

    store = OpsStore()
    assert eng.log.publish_to_store(store) == len(eng.log.events)
    assert eng.log.publish_to_store(store) == 0            # idempotent per event
    assert all(e.synthetic for e in store.vision_events)
    a = application_analytics(store)
    assert a["weeds_detected"] == 3 and a["weeds_treated"] == 1 and a["weeds_skipped"] == 2
    assert a["weeds_outside_geofence"] == 1
    assert a["skip_reasons"][E.OUTSIDE_TREATMENT_GEOFENCE] == 1
    assert a["synthetic"] is True


def test_dict_detections_are_supported_but_get_no_extra_authority():
    eng, act = make_engine()
    lat, lon = latlon(0, 0)
    d = {"detection_id": "x", "label": "weed", "confidence": 0.99, "validated_locally": True,
         "world_lat": lat, "world_lon": lon, "position_uncertainty_m": 0.2, "georef_status": "OK",
         "may_drive_treatment": True, "in_treatment_zone": True}
    inp = baseline_inputs()
    inp["detection"] = d
    assert run(eng, inp).allowed
    eng2, act2 = make_engine()
    d2 = dict(d, validated_locally=False)
    inp2 = baseline_inputs()
    inp2["detection"] = d2
    assert not run(eng2, inp2).allowed and act2.commands == []


def test_log_object_is_injectable_and_shared():
    log = TreatmentEventLog()
    eng, _ = make_engine()
    eng.log = log
    run(eng, baseline_inputs())
    assert len(log.events) == 2 and replace(good_arming()).armed_by == "alice"
