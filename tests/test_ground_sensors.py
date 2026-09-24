"""Ground sensors: per-device credentials, LoRaWAN payloads (C encoder, JS and
Python decoders agreeing), the ChirpStack bridge, ESPHome configs against the
contract, and silent-device detection."""

from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from agri_edge.iot import lorawan
from agri_edge.iot.mqtt_topics import parse_topic
from agri_edge.iot.provision import (
    Device,
    acl_block,
    load_registry,
    mosquitto_hash,
    provision,
    revoke,
    verify_mosquitto_hash,
)
from agri_edge.ops.device_watch import check as check_devices
from agri_edge.ops.ingest import ingest
from agri_edge.ops.store import OpsStore

ROOT = Path(__file__).resolve().parents[1]
LORA = ROOT / "ground_iot" / "lorawan"
ESPHOME = ROOT / "ground_iot" / "firmware" / "esphome"


# -- credentials -------------------------------------------------------------------


def test_mosquitto_hash_format_and_verification():
    h = mosquitto_hash("correct horse", salt=b"\x00" * 12)
    parts = h.split("$")
    assert parts[1] == "7" and parts[2] == "101"
    assert len(base64.b64decode(parts[3])) == 12 and len(base64.b64decode(parts[4])) == 64
    assert verify_mosquitto_hash("correct horse", h)
    assert not verify_mosquitto_hash("wrong", h)


def _paths(tmp_path):
    base_acl = (ROOT / "ground_iot" / "mosquitto" / "acl").read_text(encoding="utf-8")
    (tmp_path / "acl").write_text(base_acl, encoding="utf-8")
    return {"passwd": tmp_path / "passwd", "acl": tmp_path / "acl", "registry": tmp_path / "devices.json"}


def test_a_device_can_only_write_its_own_zone(tmp_path):
    paths = _paths(tmp_path)
    pw = provision(Device("soil-01", "farm", "z1", "soil"), **paths)
    assert len(pw) >= 32
    acl = paths["acl"].read_text()
    assert "user soil-01\ntopic write agriedge/farm/farm/zone/z1/soil\n" in acl
    assert "zone/z2" not in acl.split("user soil-01")[1]
    line = next(ln for ln in paths["passwd"].read_text().splitlines() if ln.startswith("soil-01:"))
    assert verify_mosquitto_hash(pw, line.split(":", 1)[1])
    assert pw not in paths["passwd"].read_text() and pw not in paths["registry"].read_text()


def test_a_valve_node_reads_commands_but_cannot_send_them():
    block = acl_block(Device("valve-z1", "farm", "z1", "valve"))
    assert "topic read agriedge/farm/farm/zone/z1/irrigation/set" in block
    assert "topic write agriedge/farm/farm/zone/z1/irrigation/set" not in block


def test_rotation_replaces_and_revocation_removes(tmp_path):
    paths = _paths(tmp_path)
    d = Device("soil-01", "farm", "z1", "soil")
    first = provision(d, **paths)
    second = provision(Device("soil-01", "farm", "z1", "soil"), **paths)
    assert first != second
    assert paths["acl"].read_text().count("user soil-01") == 1
    assert paths["passwd"].read_text().count("soil-01:") == 1
    assert revoke("soil-01", **paths)
    assert "soil-01" not in paths["acl"].read_text() + paths["passwd"].read_text()
    assert load_registry(paths["registry"]) == {}


def test_the_whole_acl_still_lets_only_nodered_command_irrigation(tmp_path):
    paths = _paths(tmp_path)
    provision(Device("valve-z1", "farm", "z1", "valve"), **paths)
    provision(Device("soil-01", "farm", "z1", "soil"), **paths)
    user, writers = None, set()
    for ln in paths["acl"].read_text().splitlines():
        ln = ln.strip()
        if ln.startswith("user "):
            user = ln.split()[1]
        elif ln.startswith("topic ") and user:
            parts = ln.split()
            if parts[1] in ("write", "readwrite") and (parts[2].endswith("irrigation/set") or parts[2].endswith("#")):
                writers.add(user)
    assert writers == {"nodered"}


@pytest.mark.parametrize("dev", [
    Device("Soil 01", "farm", "z1", "soil"),
    Device("soil-01", "farm/../x", "z1", "soil"),
    Device("nodered", "farm", "z1", "soil"),
    Device("soil-01", "farm", "z1", "sprayer"),
    Device("lora-01", "farm", "z1", "soil", transport="lorawan", dev_eui="nothex"),
])
def test_bad_devices_are_refused(tmp_path, dev):
    with pytest.raises(ValueError):
        provision(dev, **_paths(tmp_path))


# -- LoRaWAN payloads: C == JS == Python --------------------------------------------

C_MAIN = r"""
#include <math.h>
#include <stdio.h>
#include "agriedge_payload.h"
static void hex(const uint8_t *b, size_t n) { for (size_t i = 0; i < n; i++) printf("%02x", b[i]); printf("\n"); }
int main(void) {
    uint8_t buf[64];
    ae_depth_t d[2] = {{10, 23.4f, 12.5f}, {30, NAN, -3.2f}};
    hex(buf, ae_encode_soil(buf, sizeof buf, 81.0f, d, 2));
    hex(buf, ae_encode_weather(buf, sizeof buf, NAN, -7.4f, 63.5f, 1013.2f, 4.2f, 270.0f, 1.4f, NAN));
    return 0;
}
"""


@pytest.fixture(scope="module")
def c_payloads(tmp_path_factory):
    cc = shutil.which("cc") or shutil.which("gcc")
    if cc is None:
        pytest.skip("no C compiler")
    d = tmp_path_factory.mktemp("c")
    (d / "main.c").write_text(C_MAIN)
    exe = d / "enc"
    subprocess.run([cc, "-std=c99", "-Wall", "-Werror", "-I", str(LORA / "firmware"),
                    str(d / "main.c"), str(LORA / "firmware" / "agriedge_payload.c"),
                    "-lm", "-o", str(exe)], check=True)
    soil, weather = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.split()
    return bytes.fromhex(soil), bytes.fromhex(weather)


def _js(fport, data):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    script = (f"const c=require({json.dumps(str(LORA / 'chirpstack_codec.js'))});"
              f"process.stdout.write(JSON.stringify(c.decodeUplink({{fPort:{fport},bytes:{list(data)}}})))")
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True,
                                     check=True).stdout)


def test_soil_payload_agrees_across_c_js_and_python(c_payloads):
    soil, _ = c_payloads
    py = lorawan.decode(1, soil)
    assert py == {"kind": "soil", "battery_pct": 81.0, "depths": [
        {"depth_cm": 10, "moisture_pct": 23.4, "temp_c": 12.5},
        {"depth_cm": 30, "moisture_pct": None, "temp_c": -3.2}]}
    assert _js(1, soil)["data"] == py


def test_weather_payload_agrees_across_c_js_and_python(c_payloads):
    _, weather = c_payloads
    py = lorawan.decode(2, weather)
    assert py["battery_pct"] is None and py["solar_wm2"] is None
    assert py["air_temp_c"] == -7.4 and py["rh_pct"] == 63.5 and py["pressure_hpa"] == 1013.2
    assert py["wind_ms"] == 4.2 and py["wind_dir_deg"] == 270 and py["precip_mm"] == 1.4
    assert _js(2, weather)["data"] == py


@pytest.mark.parametrize("fport,data", [(1, b"\x02\x50\x00"), (1, b"\x01\x50\x02\x0a"), (9, b"\x01\x00")])
def test_malformed_payloads_are_refused(fport, data):
    with pytest.raises(lorawan.PayloadError):
        lorawan.decode(fport, data)
    assert "errors" in _js(fport, data)


# -- ChirpStack -> contract -> ops station ------------------------------------------


def test_bridge_maps_a_registered_node_onto_its_zone_and_the_station_ingests_it(c_payloads, tmp_path):
    soil, _ = c_payloads
    paths = _paths(tmp_path)
    provision(Device("lora-soil-7", "farm", "far-quarter", "soil", transport="lorawan",
                     dev_eui="A84041000181C0DE"), **paths)
    event = {"deviceInfo": {"devEui": "a84041000181c0de"}, "fPort": 1, "time": "2026-09-24T12:00:00Z",
             "data": base64.b64encode(soil).decode(), "rxInfo": [{"rssi": -118}, {"rssi": -109}]}
    topic, payload = lorawan.to_contract(event, load_registry(paths["registry"]))
    assert topic == "agriedge/farm/farm/zone/far-quarter/soil"
    assert payload["device_id"] == "lora-soil-7" and payload["rssi"] == -109
    assert payload["depths"][1] == {"depth_cm": 30, "temp_c": -3.2}      # missing stays missing
    store = OpsStore()
    ingest(store, topic, payload)
    assert store.devices["lora-soil-7"].zone_id == "far-quarter"


def test_bridge_drops_unknown_and_mismatched_devices(c_payloads, tmp_path):
    _, weather = c_payloads
    paths = _paths(tmp_path)
    provision(Device("lora-soil-7", "farm", "z9", "soil", transport="lorawan",
                     dev_eui="A84041000181C0DE"), **paths)
    reg = load_registry(paths["registry"])
    stranger = {"deviceInfo": {"devEui": "0000000000000001"}, "fPort": 2,
                "data": base64.b64encode(weather).decode()}
    assert lorawan.to_contract(stranger, reg) is None
    wrong_kind = {**stranger, "deviceInfo": {"devEui": "A84041000181C0DE"}}
    assert lorawan.to_contract(wrong_kind, reg) is None


# -- ESPHome configs against the contract -------------------------------------------


class _AnyTagLoader(yaml.SafeLoader):
    pass


_AnyTagLoader.add_multi_constructor("!", lambda loader, suffix, node: f"<{suffix}>")

INGEST_KEYS = {"schema_version", "device_id", "battery_pct", "rssi", "depths", "depth_cm",
               "moisture_pct", "temp_c", "air_temp_c", "rh_pct", "pressure_hpa", "wind_ms",
               "wind_dir_deg", "precip_mm", "solar_wm2"}


@pytest.mark.parametrize("name,kind", [("soil-station.yaml", "soil"), ("weather-station.yaml", "weather")])
def test_esphome_configs_speak_the_contract(name, kind):
    text = (ESPHOME / name).read_text(encoding="utf-8")
    cfg = yaml.load(text, Loader=_AnyTagLoader)
    subs = cfg["substitutions"]
    for key in ("username", "password", "broker"):
        assert cfg["mqtt"][key] == "<secret>", f"mqtt {key} must come from secrets.yaml"
    topics = re.findall(r"topic: (agriedge/\S+)", text)
    assert topics
    for t in topics:
        concrete = re.sub(r"\$\{(\w+)\}", lambda m: subs[m.group(1)], t)
        assert parse_topic(concrete).kind == kind
    keys = set(re.findall(r'\b(?:root|d10|d30)\["(\w+)"\]', text))
    assert keys and keys <= INGEST_KEYS, keys - INGEST_KEYS


def test_firmware_secrets_are_not_committable():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "ground_iot/firmware/esphome/secrets.yaml" in ignore
    assert "ground_iot/mosquitto/devices.json" in ignore


# -- silent devices ------------------------------------------------------------------


def test_a_silent_registered_device_raises_an_alert():
    store = OpsStore()
    reg = {"soil-01": {"device_id": "soil-01", "kind": "soil", "zone": "z1", "farm": "farm", "interval_s": 900},
           "soil-02": {"device_id": "soil-02", "kind": "soil", "zone": "z2", "farm": "farm", "interval_s": 900}}
    ingest(store, "agriedge/farm/farm/zone/z1/soil", {"device_id": "soil-01", "moisture_pct": 20})
    now = datetime.now(timezone.utc)
    status = {s["device_id"]: s["online"] for s in check_devices(store, reg, now)}
    assert status == {"soil-01": True, "soil-02": False}
    later = {s["device_id"]: s["online"] for s in check_devices(store, reg, now + timedelta(hours=1))}
    assert later == {"soil-01": False, "soil-02": False}
    titles = {a.title for a in store.alerts.list_alerts()}
    assert {"soil-01 is silent", "soil-02 is silent"} <= titles
