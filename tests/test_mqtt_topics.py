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
