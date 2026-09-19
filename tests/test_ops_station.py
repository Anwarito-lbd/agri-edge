"""Core Ops Station tests (§160–162)."""
from __future__ import annotations

from agri_edge.ops.store import reset_store
from agri_edge.ops.simulate import seed_demo
from agri_edge.ops.types import DeviceType, TempKind, TypedTemperature, DataOrigin, QualityFlag
from agri_edge.ops.derived import dewpoint_c, vpd_kpa, gdd_stub, frost_risk, derive_from_weather
from agri_edge.ops.quality import evaluate_soil_reading, evaluate_weather_reading
from agri_edge.ops.alerts import AlertEngine
from agri_edge.ops.types import AlertSeverity, AlertState


def test_seed_demo_synthetic():
    store = reset_store()
    result = seed_demo(store)
    assert result["synthetic"] is True
    assert store.simulation_mode is True
    assert all(d.synthetic for d in store.devices.values())
    assert all(w.synthetic for w in store.weather)
    assert DeviceType.WEATHER_STATION in {d.device_type for d in store.devices.values()}


def test_typed_temperature_not_bare():
    t = TypedTemperature(value_c=12.0, kind=TempKind.SOIL, origin=DataOrigin.MEASURED)
    d = t.to_dict()
    assert d["kind"] == "soil"
    assert "value_c" in d


def test_derived_dew_vpd_gdd_frost():
    td = dewpoint_c(20.0, 50.0)
    assert td.origin == DataOrigin.DERIVED
    assert td.algorithm_version
    assert td.kind == TempKind.DEWPOINT
    v = vpd_kpa(20.0, 50.0)
    assert v["origin"] == "DERIVED"
    assert v["vpd_kpa"] > 0
    g = gdd_stub(10, 22, base_c=10)
    assert g["gdd"] == 6.0
    fr = frost_risk(-1.0)
    assert fr["auto_irrigate"] is False
    assert fr["frost_level"] in ("light", "hard")


def test_quality_impossible_stuck_jump_battery():
    bad = evaluate_soil_reading(150.0)
    assert bad.flag == QualityFlag.BAD
    stuck = evaluate_soil_reading(20.0, history=[20.0, 20.0, 20.0])
    assert stuck.flag == QualityFlag.STUCK
    jump = evaluate_soil_reading(60.0, prev_moisture=10.0)
    assert jump.flag == QualityFlag.JUMP
    batt = evaluate_soil_reading(25.0, battery_pct=5.0)
    assert batt.flag == QualityFlag.LOW_BATTERY
    miss = evaluate_soil_reading(None)
    assert miss.flag == QualityFlag.MISSING


def test_alert_dedupe_ack_resolve_escalate():
    eng = AlertEngine()
    t = TypedTemperature(value_c=-1.0, kind=TempKind.AIR)
    a1 = eng.evaluate_temperature(t, device_id="wx1", synthetic=True)
    a2 = eng.evaluate_temperature(t, device_id="wx1", synthetic=True)
    assert a1 is not None and a2 is not None
    assert a1.alert_id == a2.alert_id  # dedupe
    eng.ack(a1.alert_id, "op")
    assert eng.list_alerts()[0].state == AlertState.ACKNOWLEDGED
    eng.escalate(a1.alert_id, "op")
    assert eng.list_alerts()[0].state == AlertState.ESCALATED
    assert eng.list_alerts()[0].severity in (AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY)
    eng.resolve(a1.alert_id, "op")
    assert eng.list_alerts()[0].state == AlertState.RESOLVED


def test_multi_depth_soil():
    store = reset_store()
    seed_demo(store)
    depths = {s.depth_cm for s in store.soil}
    assert 10.0 in depths and 30.0 in depths and 60.0 in depths


def test_overview_banner():
    store = reset_store()
    seed_demo(store)
    ov = store.overview()
    assert ov["banner"] == "SIMULATION"
    assert ov["device_count"] >= 3
