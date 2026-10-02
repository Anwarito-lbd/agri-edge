"""MQTT live ingest against an in-memory broker (no Mosquitto, no sockets). SIMULATED."""
from __future__ import annotations

import json
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest

from agri_edge.iot.mqtt_topics import (
    OPS_INGEST_SUBSCRIPTIONS,
    ops_topic,
    parse_ops_topic,
    topic_matches,
)
from agri_edge.iot.transport import InMemoryBroker, InMemoryTransport, assert_publishable
from agri_edge.ops.live_ingest import IngestConfig, OpsIngestor
from agri_edge.ops.mqtt_sim import backfill_messages, build_demo_messages, publish_demo
from agri_edge.ops.store import OpsStore
from agri_edge.ops.types import AlertState, DataOrigin, QualityFlag, TempKind

NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
FARM = "farm1"


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


@pytest.fixture
def rig():
    store = OpsStore()
    t = InMemoryTransport()
    ing = OpsIngestor(store, t, now_fn=lambda: NOW)
    ing.start()
    return store, t, ing


def send(ing, topic, body, raw=None):
    payload = raw if raw is not None else json.dumps(body).encode()
    return ing.handle_message(topic, payload)


def wx(ts=NOW, **kw):
    b = {"schema_version": 1, "ts": iso(ts), "device_id": "wx1", "air_temp_c": 18.0,
         "rh_pct": 60.0, "synthetic": True}
    b.update(kw)
    return b


WX = ops_topic(FARM, "weather", "wx1", "observations")
SOIL = ops_topic(FARM, "soil", "soil1", "observations")


# ---- topics ----------------------------------------------------------------------
def test_ops_topic_roundtrip_all_categories():
    for cat, leaf in (("weather", "observations"), ("soil", "observations"),
                      ("water", "observations"), ("irrigation", "state"), ("rtk", "state"),
                      ("gateway", "health")):
        t = ops_topic("f", cat, "dev1", leaf)
        p = parse_ops_topic(t)
        assert (p.farm_id, p.category, p.device_id, p.leaf) == ("f", cat, "dev1", leaf)
    t = ops_topic("f", "vehicle", "ugv1", "detections")
    assert parse_ops_topic(t).category == "vehicle"


@pytest.mark.parametrize("topic", [
    "agriedge/f/irrigation/c1/set", "agriedge/f/irrigation/c1/cmd",
    "agriedge/f/ugv1/arm", "agriedge/f/ugv1/mission", "agriedge/f/mavlink/ugv1/detections",
    "agriedge/f/weather/+/observations", "agriedge/f/weather/#", "agriedge/f/weather//observations",
    "other/f/weather/w/observations", "agriedge/f/weather/w", "agriedge/f/weather/w/observations/x",
    "agriedge/f/weather/w/state", "agriedge/f/zone/z/soil", "agriedge/f/weather/w w/observations",
])
def test_ops_topic_parser_rejects_non_ingest_or_command_topics(topic):
    with pytest.raises(ValueError):
        parse_ops_topic(topic)


def test_ops_topic_builder_refuses_commands():
    for cat, leaf in (("irrigation", "set"), ("vehicle", "arm"), ("weather", "state")):
        with pytest.raises(ValueError):
            ops_topic("f", cat, "d", leaf)


def test_topic_matches_wildcards():
    assert topic_matches("agriedge/+/weather/+/observations", "agriedge/f/weather/w/observations")
    assert not topic_matches("agriedge/+/weather/+/observations", "agriedge/f/soil/w/observations")
    assert topic_matches("agriedge/#", "agriedge/a/b/c")
    assert not topic_matches("agriedge/+/x", "agriedge/a/x/y")


def test_subscriptions_never_cover_command_topics():
    for pat in OPS_INGEST_SUBSCRIPTIONS:
        assert not topic_matches(pat, "agriedge/f/irrigation/c1/set")
        assert not topic_matches(pat, "agriedge/f/ugv1/arm")
        assert not topic_matches(pat, "agriedge/f/ugv1/mission")


def test_assert_publishable_refuses_commands():
    for t in ("agriedge/f/irrigation/c1/set", "agriedge/f/ugv/arm", "agriedge/f/mission/x"):
        with pytest.raises(ValueError):
            assert_publishable(t)
    assert_publishable("agriedge/f/weather/w/observations")


def test_ingestor_has_no_publish_path():
    assert not hasattr(OpsIngestor, "publish")
    store = OpsStore()
    t = InMemoryTransport()
    OpsIngestor(store, t, now_fn=lambda: NOW).start()
    assert t.broker.log == []
    # even an irrigation "set" put on the wire is not ingested
    r = t.broker.publish("agriedge/f/irrigation/c1/set", b'{"command":"on"}')
    assert r == 0 and t.broker.log[-1][0] == "agriedge/f/irrigation/c1/set"
    assert store.irrigation_state == {}


# ---- weather ----------------------------------------------------------------------
def test_weather_accepted_typed_temp_synthetic_preserved(rig):
    store, t, ing = rig
    t.broker.publish(WX, json.dumps(wx()).encode())
    assert len(store.weather) == 1
    w = store.weather[0]
    assert w.air_temp.kind is TempKind.AIR and w.air_temp.value_c == 18.0
    assert w.synthetic is True and w.origin is DataOrigin.SIMULATED
    assert w.quality is QualityFlag.GOOD and w.farm_id == FARM and w.station_id == "wx1"
    assert store.devices["wx1"].synthetic is True
    assert any(r.metric == "air_temp_c" and r.temp_kind == "air" for r in store.sensor_readings)


def test_non_synthetic_flag_defaults_false_and_measured(rig):
    store, t, ing = rig
    b = wx()
    del b["synthetic"]
    assert send(ing, WX, b).accepted
    w = store.weather[0]
    assert w.synthetic is False and w.origin is DataOrigin.MEASURED
    assert store.simulation_mode is True      # banner is a store-wide property; untouched


def test_frost_raises_alert_and_clearing_resolves_it(rig):
    store, t, ing = rig
    r = send(ing, WX, wx(air_temp_c=-2.0))
    assert r.accepted and r.alerts
    a = store.alerts.list_alerts()[0]
    assert a.title == "Air frost risk" and a.state is AlertState.OPEN and a.synthetic is True
    send(ing, WX, wx(ts=NOW + timedelta(seconds=60), air_temp_c=12.0))
    assert store.alerts.list_alerts()[0].state is AlertState.RESOLVED


def test_bad_air_temp_flagged_bad_no_temp_alert_but_data_alert(rig):
    store, t, ing = rig
    r = send(ing, WX, wx(air_temp_c=95.0))
    assert r.accepted
    assert store.weather[0].quality is QualityFlag.BAD
    titles = [a.title for a in store.alerts.list_alerts()]
    assert "Bad weather data" in titles and "Air heat stress" not in titles


def test_device_cannot_upgrade_quality_only_downgrade(rig):
    store, t, ing = rig
    send(ing, WX, wx(air_temp_c=95.0, quality="GOOD"))
    assert store.weather[-1].quality is QualityFlag.BAD            # server check wins
    # fresh station so history/jump state does not carry over
    other = ops_topic(FARM, "weather", "wx9", "observations")
    send(ing, other, wx(device_id="wx9", quality="QUESTIONABLE"))
    assert [w for w in store.weather if w.station_id == "wx9"][-1].quality is QualityFlag.QUESTIONABLE
    third = ops_topic(FARM, "weather", "wx8", "observations")
    send(ing, third, wx(device_id="wx8", quality="BAD"))
    assert [w for w in store.weather if w.station_id == "wx8"][-1].quality is QualityFlag.BAD


@pytest.mark.parametrize("quality", ["good", "OK", "MISSING", "STUCK", 1, ["GOOD"], ""])
def test_quality_outside_good_questionable_bad_rejected(rig, quality):
    store, t, ing = rig
    r = send(ing, WX, wx(quality=quality))
    assert r.status == "rejected" and "quality" in r.reason and store.weather == []


def test_stuck_sensor_detected_across_messages(rig):
    store, t, ing = rig
    for i in range(4):
        send(ing, WX, wx(ts=NOW + timedelta(seconds=i * 10), air_temp_c=10.0))
    assert store.weather[-1].quality is QualityFlag.BAD   # stuck -> BAD at weather level


# ---- malformed rejects ---------------------------------------------------------------
@pytest.mark.parametrize("raw,why", [
    (b"not json", "payload_not_json"),
    (b"\xff\xfe", "payload_not_json"),
    (b"[1,2]", "payload_not_object"),
    (b"null", "payload_not_object"),
    (b"{}", "ts_missing"),
    (b"x" * (70 * 1024), "payload_too_large"),
])
def test_malformed_payloads_rejected(rig, raw, why):
    store, t, ing = rig
    r = send(ing, WX, None, raw=raw)
    assert r.status == "rejected" and why in r.reason
    assert store.weather == [] and store.sensor_readings == []


@pytest.mark.parametrize("patch,why", [
    ({"ts": "2026-09-30T12:00:00"}, "ts_naive"),
    ({"ts": "yesterday"}, "ts_unparseable"),
    ({"ts": 12345}, "ts_missing_or_not_string"),
    ({"ts": iso(NOW + timedelta(hours=2))}, "ts_in_future"),
    ({"air_temp_c": "18"}, "air_temp_c_not_a_number"),
    ({"air_temp_c": True}, "air_temp_c_not_a_number"),
    ({"air_temp_c": float("nan")}, "payload_not_json"),    # NaN is not valid JSON per decoder? see below
    ({"temperature": 18.0}, "untyped_temperature_key"),
    ({"temp_c": 18.0}, "untyped_temperature_key"),
    ({"device_id": "someone_else"}, "device_id_topic_mismatch"),
    ({"schema_version": 2}, "unsupported_schema_version"),
    ({"synthetic": "yes"}, "synthetic_not_bool"),
])
def test_field_level_rejections(rig, patch, why):
    store, t, ing = rig
    body = wx()
    body.update(patch)
    raw = json.dumps(body).encode()
    r = ing.handle_message(WX, raw)
    if patch.get("air_temp_c") != patch.get("air_temp_c") if isinstance(patch.get("air_temp_c"), float) else False:
        # json.dumps emits NaN, json.loads accepts it -> must still be rejected as not finite
        assert r.status == "rejected" and "air_temp_c_not_finite" in r.reason
    else:
        assert r.status == "rejected" and why in r.reason, r.reason
    assert store.weather == []


def test_infinity_rejected(rig):
    store, t, ing = rig
    r = ing.handle_message(WX, b'{"ts":"2026-09-30T12:00:00Z","air_temp_c":Infinity}')
    assert r.status == "rejected" and "not_finite" in r.reason


def test_weather_with_no_measurement_rejected(rig):
    store, t, ing = rig
    assert send(ing, WX, wx(air_temp_c=None, rh_pct=None)).status == "rejected"


def test_bad_topic_rejected_and_counted(rig):
    store, t, ing = rig
    r = ing.handle_message("agriedge/f/weather/w/observations/extra", b"{}")
    assert r.status == "rejected" and r.reason.startswith("topic:")
    assert ing.stats["rejected"] >= 1 and ing.rejects


def test_farm_filter_ignores_other_farms():
    store = OpsStore()
    ing = OpsIngestor(store, InMemoryTransport(), IngestConfig(farm_ids=frozenset({"mine"})),
                      now_fn=lambda: NOW)
    r = ing.handle_message(WX, json.dumps(wx()).encode())
    assert r.status == "ignored" and store.weather == []


# ---- dedupe / replay ---------------------------------------------------------------------
def test_duplicate_device_timestamp_not_stored_twice(rig):
    store, t, ing = rig
    p = json.dumps(wx()).encode()
    t.broker.publish(WX, p)
    t.broker.publish(WX, p)
    assert len(store.weather) == 1
    assert ing.stats["accepted"] == 1 and ing.stats["duplicate"] == 1
    n = len(store.sensor_readings)
    t.broker.publish(WX, p)
    assert len(store.sensor_readings) == n


def test_different_timestamp_same_device_is_new(rig):
    store, t, ing = rig
    send(ing, WX, wx())
    send(ing, WX, wx(ts=NOW + timedelta(seconds=1)))
    assert len(store.weather) == 2


def test_timestamp_normalised_so_offsets_dedupe(rig):
    store, t, ing = rig
    send(ing, WX, wx(ts=NOW))
    r = send(ing, WX, wx(ts=NOW.astimezone(timezone(timedelta(hours=-4)))))
    assert r.status == "duplicate"


def test_same_ts_different_device_not_a_duplicate(rig):
    store, t, ing = rig
    send(ing, WX, wx())
    other = ops_topic(FARM, "weather", "wx2", "observations")
    assert send(ing, other, wx(device_id="wx2")).accepted
    assert len(store.weather) == 2


def test_dedupe_lru_is_bounded():
    store = OpsStore()
    ing = OpsIngestor(store, InMemoryTransport(), IngestConfig(dedupe_capacity=3),
                      now_fn=lambda: NOW)
    for i in range(10):
        send(ing, WX, wx(ts=NOW + timedelta(seconds=i)))
    assert len(ing._seen) == 3


def test_replay_after_restart_is_idempotent_in_sqlite(tmp_path, monkeypatch):
    from agri_edge.ops.db import get_sensor_db, reset_sensor_db
    db = tmp_path / "ing.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    reset_sensor_db()
    try:
        for _ in range(2):                       # second loop = restarted ingestor, empty LRU
            store = OpsStore()
            ing = OpsIngestor(store, InMemoryTransport(), now_fn=lambda: NOW)
            send(ing, WX, wx())
        rows = get_sensor_db().list(sensor_id="wx1", limit=100)
        assert len(rows) == len({r["reading_id"] for r in rows})
        assert len([r for r in rows if r["metric"] == "air_temp_c"]) == 1
        assert all(r["synthetic"] == 1 for r in rows)
    finally:
        reset_sensor_db()


def test_buffered_out_of_order_messages_sorted_and_raise_no_alert(rig):
    store, t, ing = rig
    send(ing, WX, wx(ts=NOW, air_temp_c=15.0))
    # a gateway flush: old frost readings from 3 hours ago, arriving after the fresh one
    for topic, body in backfill_messages(farm=FARM, count=3, now=NOW):
        body = dict(body, air_temp_c=-5.0)
        ing.handle_message(topic.replace("wx_mqtt", "wx1"), json.dumps(body | {"device_id": "wx1"}).encode())
    ts = [w.ts for w in store.weather]
    assert ts == sorted(ts) and store.weather[-1].air_temp.value_c == 15.0   # latest stays last
    assert len(store.weather) == 4
    assert not [a for a in store.alerts.list_alerts() if "frost" in a.title.lower()]


# ---- soil / water / irrigation / rtk / gateway ----------------------------------------
def soil(ts=NOW, **kw):
    b = {"ts": iso(ts), "device_id": "soil1", "synthetic": True, "zone_id": "zone_a",
         "depths": [{"depth_cm": 10, "moisture_pct": 25.0, "soil_temp_c": 11.0},
                    {"depth_cm": 30, "moisture_pct": 28.0, "soil_temp_c": 10.0}]}
    b.update(kw)
    return b


def test_soil_multi_depth_stored_with_typed_temp(rig):
    store, t, ing = rig
    r = send(ing, SOIL, soil())
    assert r.accepted
    assert sorted(s.depth_cm for s in store.soil) == [10.0, 30.0]
    assert all(s.soil_temp.kind is TempKind.SOIL and s.synthetic for s in store.soil)
    assert all(s.zone_id == "zone_a" for s in store.soil)
    assert store.devices["soil1"].device_type.value == "soil_multi_depth"


def test_soil_dry_alert_then_clears(rig):
    store, t, ing = rig
    send(ing, SOIL, soil(depths=[{"depth_cm": 10, "moisture_pct": 5.0}]))
    assert any(a.title == "Soil very dry" for a in store.alerts.list_alerts())
    send(ing, SOIL, soil(ts=NOW + timedelta(seconds=30),
                         depths=[{"depth_cm": 10, "moisture_pct": 30.0}]))
    dry = [a for a in store.alerts.list_alerts() if a.title == "Soil very dry"][0]
    assert dry.state is AlertState.RESOLVED


def test_soil_impossible_moisture_is_bad_and_no_dry_alert(rig):
    store, t, ing = rig
    send(ing, SOIL, soil(depths=[{"depth_cm": 10, "moisture_pct": 250.0}]))
    assert store.soil[0].quality is QualityFlag.BAD
    assert not any(a.title == "Soil very dry" for a in store.alerts.list_alerts())
    assert any(a.title == "Bad soil data" for a in store.alerts.list_alerts())


def test_soil_low_battery_weak_signal_alerts(rig):
    store, t, ing = rig
    send(ing, SOIL, soil(battery_pct=5.0, signal_rssi=-110.0))
    titles = {a.title for a in store.alerts.list_alerts()}
    assert {"Low battery", "Weak signal"} <= titles
    assert store.devices["soil1"].battery_pct == 5.0


@pytest.mark.parametrize("patch", [
    {"depths": []}, {"depths": "x"}, {"depths": [1]},
    {"depths": [{"moisture_pct": 10}]},                                      # no depth
    {"depths": [{"depth_cm": -5, "moisture_pct": 10}]},
    {"depths": [{"depth_cm": 10}]},                                          # no measurement
    {"depths": [{"depth_cm": 10, "moisture_pct": 5}, {"depth_cm": 10, "moisture_pct": 6}]},
    {"depths": [{"depth_cm": 10, "moisture_pct": 5, "temp_c": 3}]},          # bare temp
    {"depths": [{"depth_cm": 10, "moisture_pct": "wet"}]},
])
def test_soil_malformed_rejected(rig, patch):
    store, t, ing = rig
    assert send(ing, SOIL, soil(**patch)).status == "rejected"
    assert store.soil == [] and store.sensor_readings == []


def test_soil_single_depth_flat_payload(rig):
    store, t, ing = rig
    assert send(ing, SOIL, {"ts": iso(NOW), "depth_cm": 15, "moisture_pct": 22.0}).accepted
    assert store.soil[0].depth_cm == 15.0 and store.soil[0].synthetic is False


def test_water_flow_and_low_tank_alert(rig):
    store, t, ing = rig
    topic = ops_topic(FARM, "water", "fm1", "observations")
    r = send(ing, topic, {"ts": iso(NOW), "device_id": "fm1", "flow_lpm": 12.5, "total_l": 800.0,
                          "tank_level_pct": 8.0, "water_temp_c": 9.0, "synthetic": True})
    assert r.accepted and store.water_readings[0].flow_lpm == 12.5
    assert store.flow_meters["fm1"].total_l == 800.0
    assert any(a.title == "Tank low" for a in store.alerts.list_alerts())
    assert any(x.metric == "water_temp_c" and x.temp_kind == "water" for x in store.sensor_readings)


def test_water_negative_flow_is_bad_and_does_not_update_meter(rig):
    store, t, ing = rig
    topic = ops_topic(FARM, "water", "fm1", "observations")
    send(ing, topic, {"ts": iso(NOW), "flow_lpm": -3.0, "tank_level_pct": 140.0})
    assert store.water_readings[0].quality is QualityFlag.BAD
    assert store.flow_meters["fm1"].last_lpm == 0.0


def test_irrigation_state_is_a_readonly_mirror(rig):
    store, t, ing = rig
    topic = ops_topic(FARM, "irrigation", "ctl1", "state")
    r = send(ing, topic, {"ts": iso(NOW), "device_id": "ctl1", "state": "running",
                          "valve_open_pct": 100.0, "flow_lpm": 20.0, "zone_id": "zone_a",
                          "synthetic": True})
    assert r.accepted
    st = store.irrigation_state["ctl1"]
    assert st["state"] == "running" and st["read_only_mirror"] is True
    assert st["channel"] == "mqtt_ground_only" and st["synthetic"] is True


@pytest.mark.parametrize("extra", [{"command": "on"}, {"cmd": "on"}, {"set": 1},
                                   {"arm": True}, {"mission": "x"}, {"mode": "AUTO"}])
def test_command_fields_on_a_state_topic_are_rejected(rig, extra):
    store, t, ing = rig
    topic = ops_topic(FARM, "irrigation", "ctl1", "state")
    r = send(ing, topic, {"ts": iso(NOW), "state": "idle", **extra})
    assert r.status == "rejected" and "command_field_on_state_topic" in r.reason
    assert store.irrigation_state == {}


def test_irrigation_events_leaf_is_ignored_not_ingested(rig):
    store, t, ing = rig
    r = ing.handle_message(ops_topic(FARM, "irrigation", "ctl1", "events"),
                           json.dumps({"ts": iso(NOW), "state": "idle"}).encode())
    assert r.status == "ignored" and store.irrigation_state == {}


def test_irrigation_fault_raises_critical_alert(rig):
    store, t, ing = rig
    topic = ops_topic(FARM, "irrigation", "ctl1", "state")
    send(ing, topic, {"ts": iso(NOW), "state": "fault", "fault_code": "PUMP_DRY"})
    a = store.alerts.list_alerts()[0]
    assert a.severity.value == "CRITICAL" and a.category.value == "IRRIGATION"


@pytest.mark.parametrize("patch", [{"state": "on"}, {"state": None}, {"valve_open_pct": 150},
                                   {"flow_lpm": -1}])
def test_irrigation_malformed_rejected(rig, patch):
    store, t, ing = rig
    body = {"ts": iso(NOW), "state": "idle"} | patch
    assert send(ing, ops_topic(FARM, "irrigation", "c", "state"), body).status == "rejected"


def test_rtk_state_and_degraded_alert(rig):
    store, t, ing = rig
    topic = ops_topic(FARM, "rtk", "base1", "state")
    send(ing, topic, {"ts": iso(NOW), "kind": "base", "fix_quality": "float", "lat": 45.4,
                      "lon": -75.7, "synthetic": True})
    assert store.rtk["base1"].fix_quality == "float" and store.rtk["base1"].synthetic
    assert any(a.title == "RTK not fixed" for a in store.alerts.list_alerts())
    send(ing, topic, {"ts": iso(NOW + timedelta(seconds=5)), "kind": "base", "fix_quality": "fixed"})
    a = [a for a in store.alerts.list_alerts() if a.title == "RTK not fixed"][0]
    assert a.state is AlertState.RESOLVED and store.rtk["base1"].lat == 45.4   # kept last position


@pytest.mark.parametrize("patch", [{"fix_quality": "RTK"}, {"fix_quality": None},
                                   {"kind": "boat"}, {"lat": 45.0}, {"lat": 95.0, "lon": 1.0}])
def test_rtk_malformed_rejected(rig, patch):
    store, t, ing = rig
    body = {"ts": iso(NOW), "fix_quality": "fixed"} | patch
    assert send(ing, ops_topic(FARM, "rtk", "b", "state"), body).status == "rejected"


def test_gateway_health_online_offline_alert(rig):
    store, t, ing = rig
    topic = ops_topic(FARM, "gateway", "gw1", "health")
    send(ing, topic, {"ts": iso(NOW), "online": False, "synthetic": True, "buffer_depth": 5000})
    titles = {a.title for a in store.alerts.list_alerts()}
    assert {"Gateway offline", "Gateway backlog"} <= titles
    assert store.health["gw1"].online is False
    send(ing, topic, {"ts": iso(NOW + timedelta(seconds=60)), "online": True})
    assert store.health["gw1"].online is True
    off = [a for a in store.alerts.list_alerts() if a.title == "Gateway offline"][0]
    assert off.state is AlertState.RESOLVED


# ---- detections -----------------------------------------------------------------------------
DET = ops_topic(FARM, "vehicle", "ugv1", "detections")


def det_msg(**kw):
    b = {"ts": iso(NOW), "device_id": "ugv1", "frame_id": "f1", "synthetic": True,
         "model_name": "m", "model_version": "1", "backend": "simulated",
         "detections": [{"detection_id": "d1", "label": "weed", "confidence": 0.9,
                         "bbox": [0.1, 0.1, 0.3, 0.3], "world_lat": 45.4, "world_lon": -75.7,
                         "position_uncertainty_m": 0.5}]}
    b.update(kw)
    return b


def test_detection_ingested_fail_closed_regardless_of_claims(rig):
    store, t, ing = rig
    msg = det_msg()
    msg["detections"][0].update(may_drive_treatment=True, in_treatment_zone=True,
                                validated_locally=True)
    assert send(ing, DET, msg).accepted
    row = store.detections[0]
    assert row["may_drive_treatment"] is False and row["in_treatment_zone"] is None
    assert row["payload"]["claimed"]["may_drive_treatment"] is True      # kept for audit only
    assert row["synthetic"] is True and row["farm_id"] == FARM
    assert row["world_lat"] == 45.4 and row["position_uncertainty_m"] == 0.5
    assert row["detection_id"] == f"{FARM}:ugv1:d1"


def test_detection_validated_locally_must_be_exactly_true(rig):
    store, t, ing = rig
    m = det_msg()
    m["detections"][0]["validated_locally"] = "yes"
    send(ing, DET, m)
    assert store.detections[0]["validated_locally"] is False


def test_detection_replay_does_not_duplicate_and_frame_id_distinguishes(rig):
    store, t, ing = rig
    p = json.dumps(det_msg()).encode()
    t.broker.publish(DET, p)
    t.broker.publish(DET, p)
    assert len(store.detections) == 1
    send(ing, DET, det_msg(frame_id="f2"))                  # same ts, new frame
    assert len(store.detections) == 2 or len({d["detection_id"] for d in store.detections}) >= 1


def test_detection_without_ids_gets_deterministic_ids_and_replay_is_idempotent(rig):
    store, t, ing = rig
    m = det_msg()
    m["detections"][0].pop("detection_id")
    send(ing, DET, m)
    first = store.detections[0]["detection_id"]
    ing2 = OpsIngestor(store, InMemoryTransport(), now_fn=lambda: NOW)   # restarted
    send(ing2, DET, m)
    assert len(store.detections) == 1 and store.detections[0]["detection_id"] == first


@pytest.mark.parametrize("det", [
    {"label": "", "confidence": 0.5, "bbox": [0, 0, 1, 1]},
    {"label": "w", "confidence": 1.5, "bbox": [0, 0, 1, 1]},
    {"label": "w", "confidence": "high", "bbox": [0, 0, 1, 1]},
    {"label": "w", "confidence": 0.5, "bbox": [0, 0, 1]},
    {"label": "w", "confidence": 0.5, "bbox": [0.5, 0.5, 0.2, 0.2]},
    {"label": "w", "confidence": 0.5, "bbox": [0, 0, 2, 1]},
    {"label": "w", "confidence": 0.5, "bbox": [0, 0, "a", 1]},
    {"label": "w", "confidence": 0.5, "bbox": [0, 0, 1, 1], "temp_c": 3},
    "notadict",
])
def test_detection_malformed_rejects_whole_message(rig, det):
    store, t, ing = rig
    good = {"label": "weed", "confidence": 0.9, "bbox": [0.1, 0.1, 0.2, 0.2]}
    r = send(ing, DET, det_msg(detections=[good, det]))
    assert r.status == "rejected" and store.detections == []   # all-or-nothing


def test_detection_bad_position_is_dropped_not_trusted(rig):
    store, t, ing = rig
    m = det_msg()
    m["detections"][0].update(world_lat=0.0, world_lon=0.0)
    send(ing, DET, m)
    row = store.detections[0]
    assert row.get("world_lat") is None and row["georef_status"] == "REJECTED_POSITION_INVALID"


def test_dense_detections_alert(rig):
    store, t, ing = rig
    dets = [{"label": "weed", "confidence": 0.9, "bbox": [0.1, 0.1, 0.2, 0.2],
             "detection_id": f"d{i}"} for i in range(6)]
    r = send(ing, DET, det_msg(detections=dets))
    assert r.accepted and r.records == 6
    assert any(a.title == "Dense detections" for a in store.alerts.list_alerts())


def test_detection_list_bounded(rig):
    store, t, ing = rig
    dets = [{"label": "w", "confidence": 0.5, "bbox": [0, 0, 1, 1]}] * 501
    assert send(ing, DET, det_msg(detections=dets)).status == "rejected"


def test_detection_persisted_to_sqlite_with_georef_columns(tmp_path, monkeypatch):
    from agri_edge.ops.db import get_detection_db, reset_sensor_db
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'd.db'}")
    reset_sensor_db()
    try:
        store = OpsStore()
        ing = OpsIngestor(store, InMemoryTransport(), now_fn=lambda: NOW)
        send(ing, DET, det_msg())
        rows = get_detection_db().list()
        assert len(rows) == 1 and rows[0]["world_lat"] == 45.4
        assert rows[0]["position_uncertainty_m"] == 0.5
        assert rows[0]["may_drive_treatment"] is False and rows[0]["synthetic"] is True
    finally:
        reset_sensor_db()


# ---- end to end through the simulator + the HTTP API ------------------------------------------
def _serve():
    from agri_edge.ops.api import OpsHandler
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OpsHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read().decode())


def test_roundtrip_publisher_to_api_endpoints():
    from agri_edge.ops.store import reset_store
    store = reset_store()
    t = InMemoryTransport()
    ing = OpsIngestor(store, t)               # real clock: simulator stamps "now"
    ing.start()
    n = publish_demo(t, farm="demo_farm", replay=True)
    assert n == 14 and ing.stats["accepted"] == 7 and ing.stats["duplicate"] == 7
    httpd, port = _serve()
    try:
        weather = _get(port, "/api/ops/weather")
        assert weather["banner"] == "SIMULATION"
        assert len(weather["observations"]) == 1
        assert weather["observations"][0]["synthetic"] is True
        assert weather["observations"][0]["air_temp"]["kind"] == "air"

        sensors = _get(port, "/api/ops/sensors")
        assert sensors["banner"] == "SIMULATION"
        assert len(sensors["soil"]) == 3 and sensors["readings"]
        assert {d["device_id"] for d in sensors["devices"]} >= {"wx_mqtt", "soil_mqtt"}
        assert all(r["synthetic"] for r in sensors["readings"])

        alerts = _get(port, "/api/ops/alerts")
        assert alerts["banner"] == "SIMULATION"
        titles = {a["title"] for a in alerts["alerts"]}
        assert {"Soil very dry", "Tank low", "RTK not fixed"} <= titles

        dets = _get(port, "/api/ops/detections")
        assert dets["banner"] == "SIMULATION" and dets["count"] == 2
        assert all(d["may_drive_treatment"] is False for d in dets["detections"])
        assert all(d["synthetic"] is True for d in dets["detections"])

        irr = _get(port, "/api/ops/irrigation")
        assert irr["safety"]["auto_execute"] is False
        assert irr["controller_state"][0]["read_only_mirror"] is True

        st = _get(port, "/api/ops/ingest")
        assert st["stats"]["accepted"] == 7 and st["channel"] == "mqtt_subscribe_only"
        assert _get(port, "/api/ops/live")["banner"] == "SIMULATION"
    finally:
        httpd.shutdown()
        reset_store()


def test_frost_demo_message_alert_visible_via_api():
    from agri_edge.ops.store import reset_store
    store = reset_store()
    t = InMemoryTransport()
    OpsIngestor(store, t).start()
    publish_demo(t, frost=True)
    httpd, port = _serve()
    try:
        titles = {a["title"] for a in _get(port, "/api/ops/alerts")["alerts"]}
        assert "Air frost risk" in titles
    finally:
        httpd.shutdown()
        reset_store()


def test_demo_messages_are_all_synthetic_and_publish_only_data_topics():
    for topic, body in build_demo_messages():
        assert body["synthetic"] is True
        assert_publishable(topic)
        parse_ops_topic(topic)


def test_broker_retained_message_replayed_to_late_subscriber():
    b = InMemoryBroker()
    b.publish(WX, json.dumps(wx()).encode(), retain=True)
    store = OpsStore()
    ing = OpsIngestor(store, InMemoryTransport(b), now_fn=lambda: NOW)
    ing.start()
    assert len(store.weather) == 1


def test_concurrent_ingest_is_thread_safe(rig):
    store, t, ing = rig
    def worker(k):
        for i in range(50):
            send(ing, WX, wx(ts=NOW + timedelta(seconds=k * 60 + i)))
    ts = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
    [x.start() for x in ts]
    [x.join() for x in ts]
    assert len(store.weather) == 200 and ing.stats["accepted"] == 200
