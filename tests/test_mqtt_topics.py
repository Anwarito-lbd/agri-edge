"""Tests for MQTT topic contract (no broker required)."""

import pytest

from agri_edge.iot.mqtt_topics import parse_topic, zone_topic


def test_zone_topic_soil():
    t = zone_topic("1", "1", "soil")
    assert t == "agriedge/farm/1/zone/1/soil"
    p = parse_topic(t)
    assert p.farm_id == "1" and p.zone_id == "1" and p.kind == "soil"


def test_irrigation_set_ok():
    t = zone_topic("1", "2", "irrigation/set")
    p = parse_topic(t)
    assert p.is_irrigation_command() is True


def test_rejects_mavlink_arm_language():
    with pytest.raises(ValueError):
        parse_topic("agriedge/farm/1/zone/1/mavlink/arm")
    with pytest.raises(ValueError):
        zone_topic("1", "1", "arm")


def test_unknown_kind():
    with pytest.raises(ValueError):
        parse_topic("agriedge/farm/1/zone/1/unknown")


def test_vehicle_report_topics():
    from agri_edge.iot.mqtt_topics import vehicle_topic

    t = vehicle_topic("f1", "scout1", "detections")
    assert t == "agriedge/farm/f1/vehicle/scout1/detections"
    p = parse_topic(t)
    assert p.is_vehicle and p.vehicle_id == "scout1" and p.kind == "detections"
    assert not p.is_irrigation_command()


def test_vehicle_topics_carry_no_commands():
    """The vehicle subtree is report-only; the companion link is read-only."""
    from agri_edge.iot.mqtt_topics import vehicle_topic

    for kind in ("command", "mission", "irrigation/set", "arm", "set"):
        with pytest.raises(ValueError):
            vehicle_topic("f1", "scout1", kind)
        with pytest.raises(ValueError):
            parse_topic(f"agriedge/farm/f1/vehicle/scout1/{kind}")
