"""Adapter interface tests (SIMULATED stubs; no network, no I/O)."""
from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest

from agri_edge.adapters import (
    AgOpenGpsAdapterStub,
    FarmManagementAdapter,
    FarmOSAdapter,
    FarmOSNetworkDisabled,
    GuidanceAdapter,
    GuidanceCommandRefused,
    GuidanceTrack,
)
from agri_edge.store.farmos import sidecar_to_log

META = {
    "sequence": 3, "site": "s", "field_id": "f1",
    "telemetry": {"lat": 49.9, "lon": -97.1},
    "model": {"name": "m", "version": "1"},
    "detections": [{"label": "kochia", "lat": 49.9001, "lon": -97.1001, "position_error_m": 0.8,
                    "may_drive_treatment": False}],
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("adapter stub attempted network access")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


def test_farmos_adapter_satisfies_interface():
    a = FarmOSAdapter()
    assert isinstance(a, FarmManagementAdapter)
    assert a.name == "farmos" and a.status == "SIMULATED"
    for m in ("build_observation_log", "build_treatment_log", "queue", "flush"):
        assert callable(getattr(a, m))


def test_observation_log_reuses_existing_builder_and_is_lon_first():
    a = FarmOSAdapter(land_asset_id="L1")
    p = a.build_observation_log(META)
    assert p == sidecar_to_log(META, "L1")
    assert p["data"]["type"] == "log--observation"
    assert "MULTIPOINT((-97.1001 49.9001))" == p["data"]["attributes"]["geometry"]["value"]
    assert p["data"]["relationships"]["location"]["data"][0]["id"] == "L1"


def test_treatment_log_states_simulation_and_reasons_and_lon_first():
    a = FarmOSAdapter()
    p = a.build_treatment_log({"kind": "skipped", "detection_id": "d1", "label": "kochia",
                               "confidence": 0.9, "lat": 49.9, "lon": -97.1,
                               "reasons": ["OUTSIDE_TREATMENT_GEOFENCE"], "simulated": True})
    attrs = p["data"]["attributes"]
    assert p["data"]["type"] == "log--activity"
    notes = attrs["notes"]["value"]
    assert "SIMULATION" in notes and "OUTSIDE_TREATMENT_GEOFENCE" in notes
    assert attrs["geometry"]["value"] == "POINT(-97.1 49.9)"


def test_treatment_log_without_position_has_no_geometry():
    p = FarmOSAdapter().build_treatment_log({"kind": "detected"})
    assert "geometry" not in p["data"]["attributes"]


def test_default_adapter_never_sends():
    a = FarmOSAdapter()
    assert a.network_enabled is False
    assert a.queue(a.build_observation_log(META)) == 1
    with pytest.raises(FarmOSNetworkDisabled):
        a.flush()
    assert len(a.outbox) == 1 and a.sent_ids == []          # nothing lost, nothing sent


def test_client_alone_is_not_enough_to_send():
    class Client:
        def create_log(self, payload):
            raise AssertionError("must not be called")
    a = FarmOSAdapter(client=Client())                       # allow_network defaults False
    a.queue({"x": 1})
    with pytest.raises(FarmOSNetworkDisabled):
        a.flush()
    b = FarmOSAdapter(allow_network=True)                    # opt-in but no client
    b.queue({"x": 1})
    with pytest.raises(FarmOSNetworkDisabled):
        b.flush()


def test_explicit_opt_in_flushes_through_the_client_only():
    sent = []

    class Client:
        def create_log(self, payload):
            sent.append(payload)
            return f"id{len(sent)}"
    a = FarmOSAdapter(client=Client(), allow_network=True)
    a.queue({"a": 1})
    a.queue({"b": 2})
    assert a.network_enabled and a.flush() == ["id1", "id2"]
    assert a.outbox == [] and sent == [{"a": 1}, {"b": 2}]


def test_failed_send_keeps_the_payload_queued():
    class Client:
        n = 0
        def create_log(self, payload):
            Client.n += 1
            if Client.n == 2:
                raise OSError("down")
            return "ok"
    a = FarmOSAdapter(client=Client(), allow_network=True)
    for i in range(3):
        a.queue({"i": i})
    with pytest.raises(OSError):
        a.flush()
    assert a.outbox == [{"i": 1}, {"i": 2}] and a.sent_ids == []


def test_health_reports_no_network_by_default():
    h = FarmOSAdapter().health()
    assert h == {"adapter": "farmos", "status": "SIMULATED", "network_enabled": False, "queued": 0}


# ---- guidance --------------------------------------------------------------------
def test_agopengps_stub_satisfies_guidance_interface():
    g = AgOpenGpsAdapterStub()
    assert isinstance(g, GuidanceAdapter)
    assert g.name == "agopengps_stub" and g.status == "SIMULATED" and g.simulated is True


def test_connect_never_connects_and_state_is_simulated():
    g = AgOpenGpsAdapterStub()
    assert g.connect() is False
    s = g.get_state()
    assert s.connected is False and s.engaged is False and s.simulated is True
    assert s.cross_track_error_m is None                      # no invented number
    g.close()


def test_track_loading_is_memory_only_and_validated():
    g = AgOpenGpsAdapterStub()
    ok = g.load_track(GuidanceTrack("t1", ((49.0, -97.0), (49.001, -97.0)), swath_m=8.0))
    assert ok["ok"] and ok["status"] == "SIMULATED" and "nothing was sent" in ok["note"]
    assert g.get_state().track_id == "t1"
    assert not g.load_track(GuidanceTrack("t2", ((49.0, -97.0),)))["ok"]
    assert not g.load_track(GuidanceTrack("t3", ((95.0, -97.0), (49.0, -97.0))))["ok"]
    assert g.get_state().track_id == "t1"                    # rejected tracks do not replace it


@pytest.mark.parametrize("call", [
    lambda g: g.engage(), lambda g: g.set_steer_angle(5.0), lambda g: g.set_speed(3.0),
    lambda g: g.command_steer(angle=1), lambda g: g.set_steer_angle(), 
])
def test_every_steering_command_is_refused(call):
    g = AgOpenGpsAdapterStub()
    with pytest.raises(GuidanceCommandRefused):
        call(g)
    assert g.get_state().engaged is False


def test_adapters_import_no_network_or_hardware_modules_at_all():
    forbidden = {"socket", "urllib", "http", "requests", "serial", "pymavlink", "paho",
                 "subprocess", "asyncio", "ssl"}
    root = Path(FarmOSAdapter.__module__.replace(".", "/")).parent
    import agri_edge.adapters as pkg
    # The two modules that ARE the I/O layer are allowed their transports and are checked on
    # their own terms (tests/test_farmos_http.py, tests/test_agopengps.py). Every other module
    # in the package stays I/O-free.
    io_modules = {"farmos_http.py", "agopengps_udp.py"}
    for py in Path(pkg.__file__).parent.glob("*.py"):
        if py.name in io_modules:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            # farmos.py reaches the network only via store.farmos (explicit client)
            assert not (set(names) & forbidden), (py.name, names)
    assert root is not None
