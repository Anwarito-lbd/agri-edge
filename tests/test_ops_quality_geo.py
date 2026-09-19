"""Quality, geo, gateway, vra, irrigation tests."""
from agri_edge.ops.geo import demo_farm_geojson, default_map_assets, filter_by_time_range, TIME_RANGES
from agri_edge.ops.gateway import OfflineGateway, TRANSPORT_NOTE
from agri_edge.ops.vra import make_demo_prescription, validate_prescription, feedback_map_stub
from agri_edge.ops.irrigation import rule_based_irrigation
from agri_edge.ops.commands import confirm_command
from agri_edge.ops.quality import evaluate_weather_reading
from agri_edge.ops.types import QualityFlag


def test_geojson_standard():
    fc = demo_farm_geojson()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) >= 3
    assert all(f.get("properties", {}).get("synthetic") for f in fc["features"])


def test_layer_enable_disable_time():
    assets = default_map_assets()
    assert any(a.enabled for a in assets)
    assets[0].enabled = False
    filtered = filter_by_time_range([a for a in assets if a.enabled], "now")
    assert isinstance(filtered, list)
    assert "hour" in TIME_RANGES


def test_gateway_sync_no_dupe():
    gw = OfflineGateway()
    m1 = gw.enqueue("t", {"obs_id": "x1"}, idempotency_key="x1")
    m2 = gw.enqueue("t", {"obs_id": "x1"}, idempotency_key="x1")
    assert m1.msg_id == m2.msg_id
    r = gw.sync()
    assert r["synced"] >= 1
    assert TRANSPORT_NOTE


def test_vra_constraints():
    rx = make_demo_prescription()
    rx.cells.append({"lat": 1, "lon": 2, "rate_l_ha": 999})
    result = validate_prescription(rx, wind_ms=10)
    assert result["ok"] is False
    assert result.get("auto_apply", result.get("auto_apply")) is False
    fb = feedback_map_stub(rx.prescription_id)
    assert fb["stub"] is False
    assert fb["commanded"]["type"] == "FeatureCollection"
    assert len(fb["commanded"]["features"]) >= 1


def test_irrigation_no_auto():
    rec = rule_based_irrigation(moisture_pct=10.0)
    assert rec.auto_execute is False
    assert rec.action == "suggest_irrigate"
    frost = rule_based_irrigation(moisture_pct=10.0, frost_level="light")
    assert frost.action == "none"


def test_command_forbidden():
    c = confirm_command("arm", human_confirmed=True)
    assert c.confirmed is False
    ok = confirm_command("irrigation/set", human_confirmed=True)
    assert ok.confirmed is True
    assert ok.channel == "mqtt_ground_only"


def test_weather_quality_impossible():
    q = evaluate_weather_reading(999.0)
    assert q.flag == QualityFlag.BAD
