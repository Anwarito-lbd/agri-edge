"""Water models, analytics, schema coverage."""
from agri_edge.ops.schema import WaterSource, Tank, Pump, Valve, FlowMeter, WaterReading, WaterUsageEvent, GreenhouseZone
from agri_edge.ops.types import DataOrigin, QualityFlag, new_id, utcnow
from agri_edge.ops.store import reset_store
from agri_edge.ops.simulate import seed_demo
from agri_edge.ops.analytics import water_analytics, battery_analytics, energy_analytics_stub, application_analytics_stub
from agri_edge.ops.derived import heat_stress


def test_water_models():
    ws = WaterSource(source_id="w", name="well", synthetic=True)
    tk = Tank(tank_id="t", name="tank", capacity_l=1000, level_pct=50, synthetic=True)
    pu = Pump(pump_id="p", name="p", rated_lpm=50, command_channel="mqtt_ground_only", synthetic=True)
    assert pu.command_channel == "mqtt_ground_only"
    assert Valve(valve_id="v", name="v", zone_id="z", synthetic=True).to_dict()["zone_id"] == "z"
    fm = FlowMeter(meter_id="f", name="f", synthetic=True)
    wr = WaterReading(reading_id=new_id(), meter_id="f", ts=utcnow().isoformat(), flow_lpm=1.0, synthetic=True)
    assert wr.quality == QualityFlag.GOOD
    ev = WaterUsageEvent(event_id="e", zone_id="z", start_ts=utcnow().isoformat(), volume_l=10, synthetic=True)
    assert ev.volume_l == 10
    assert ws.to_dict()["synthetic"]


def test_greenhouse_not_automated():
    g = GreenhouseZone(zone_id="g", name="g", actuators_automated=True, synthetic=True)
    assert g.to_dict()["actuators_automated"] is False


def test_analytics_stubs():
    store = reset_store()
    seed_demo(store)
    assert "formula" in water_analytics(store)
    assert battery_analytics(store)["items"]
    assert energy_analytics_stub(store)["stub"] is False
    assert energy_analytics_stub(store)["mission_count"] >= 1
    assert application_analytics_stub(store)["stub"] is False
    assert application_analytics_stub(store)["weeds_detected"] >= 1


def test_heat_no_auto():
    h = heat_stress(40.0, 20.0)
    assert h["auto_irrigate"] is False
    assert h["heat_level"] == "extreme"
