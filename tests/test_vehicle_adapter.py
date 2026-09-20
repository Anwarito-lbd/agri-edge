"""VehicleAdapter fail-closed command surface, and the honesty of connect().

`connect()` used to return True with no aircraft anywhere, because the
telemetry import named a module that does not exist and the ModuleNotFoundError
was swallowed by a bare `except`. The adapter then reported connected=True at
45.0, -75.0 -- a real-looking position in Ontario, invented by the fallback.

The tests below pin the corrected contract: connect() reports whether a vehicle
link exists, and a simulated state carries no position at all.
"""
from __future__ import annotations

from pathlib import Path

from agri_edge.vehicle import (
    ArduPilotAdapter,
    CommandResult,
    SafetySupervisor,
    VehicleAdapter,
    VehicleState,
)


def test_default_supervisor_blocks_commands():
    adapter = ArduPilotAdapter(sitl=True)  # allow_commands defaults False
    # False: nothing is listening. Not an error -- the adapter still works, in
    # simulation -- but it is not a connection and must not claim to be.
    assert adapter.connect() is False
    for fn in (adapter.arm, adapter.disarm):
        result = fn()
        assert isinstance(result, CommandResult)
        assert result.ok is False
        assert result.status in {"BLOCKED", "BLOCKED-HARDWARE"}
    mode = adapter.set_mode("GUIDED")
    assert mode.ok is False
    mission = adapter.upload_mission([{"lat": 1.0, "lon": 2.0, "alt": 10.0}])
    assert mission.ok is False
    state = adapter.get_state()
    assert isinstance(state, VehicleState)
    assert state.sitl is True
    adapter.close()


def test_sitl_simulated_commands_when_explicitly_allowed():
    supervisor = SafetySupervisor(allow_commands=True, require_sitl=True)
    adapter = ArduPilotAdapter(sitl=True, supervisor=supervisor)
    adapter.connect()
    arm = adapter.arm()
    assert arm.ok is True
    assert arm.status == "SIMULATED"
    assert adapter.get_state().armed is True
    mode = adapter.set_mode("AUTO")
    assert mode.ok and mode.status == "SIMULATED"
    up = adapter.upload_mission([{"lat": 45.0, "lon": -75.0, "alt": 20.0}])
    assert up.ok and up.details["count"] == 1
    adapter.disarm()
    assert adapter.get_state().armed is False
    adapter.close()


def test_non_sitl_blocked_even_when_commands_allowed():
    supervisor = SafetySupervisor(allow_commands=True, require_sitl=True)
    adapter = ArduPilotAdapter(sitl=False, supervisor=supervisor)
    adapter.connect()
    result = adapter.arm()
    assert result.ok is False
    assert result.status == "BLOCKED-HARDWARE"
    adapter.close()


def test_adapter_satisfies_protocol():
    adapter = ArduPilotAdapter()
    assert isinstance(adapter, VehicleAdapter)


# ---------------------------------------------------------------------------
# The defect an audit found: a connection that was never there
# ---------------------------------------------------------------------------


def test_connect_reports_false_when_no_vehicle_is_listening():
    """The whole finding in one line. A dead UDP port is not a vehicle."""
    adapter = ArduPilotAdapter("udpin:0.0.0.0:59997", sitl=False)
    assert adapter.connect() is False
    adapter.close()


def test_a_simulated_state_is_never_marked_connected():
    adapter = ArduPilotAdapter("udpin:0.0.0.0:59996", sitl=True)
    adapter.connect()
    state = adapter.get_state()
    assert state.connected is False
    assert state.simulated is True
    assert state.source == "simulated"
    adapter.close()


def test_a_simulated_state_carries_no_position():
    """The dangerous half of the old behaviour was not the flag, it was the
    coordinates: 45.0, -75.0 is a plausible Ontario field. Anything consuming
    it would georeference detections against a fabricated origin, and the
    spec's 'uncertain position -> application OFF' rule would never fire
    because the position did not look uncertain."""
    adapter = ArduPilotAdapter("udpin:0.0.0.0:59995", sitl=True)
    adapter.connect()
    state = adapter.get_state()
    assert state.lat is None and state.lon is None
    assert state.alt_m is None
    adapter.close()


def test_sitl_and_simulated_are_different_things():
    """A SITL flight produces genuine MAVLink from a simulated vehicle. This
    adapter inventing a state because it could not connect is not that, and
    one flag cannot mean both."""
    adapter = ArduPilotAdapter("udpin:0.0.0.0:59994", sitl=True)
    adapter.connect()
    state = adapter.get_state()
    assert state.sitl is True and state.simulated is True
    adapter.close()


def test_the_telemetry_module_it_imports_actually_exists():
    """The original bug was an import of `agri_edge.mavlink.connection`, which
    has never existed. Inside a bare `except Exception` that is invisible."""
    import importlib

    importlib.import_module("agri_edge.telemetry.mavlink_link")

    # Parse rather than grep: the module's own docstring names the dead import
    # while explaining the bug, and a substring check flags its own history.
    import ast

    src = (
        Path(__file__).resolve().parents[1]
        / "src" / "agri_edge" / "vehicle" / "ardupilot.py"
    ).read_text(encoding="utf-8")

    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)

    for name in imported:
        if name.startswith("agri_edge"):
            importlib.import_module(name)


def test_the_adapter_still_has_no_write_surface():
    """Commands are simulated and gated, and nothing here may transmit. The
    read path now goes through MavlinkTelemetry, which is read-only by
    construction -- rewiring it must not have opened a door."""
    from agri_edge.telemetry.mavlink_link import MavlinkTelemetry

    for forbidden in ("send", "arm", "set_mode", "mav", "command_long"):
        assert not hasattr(MavlinkTelemetry, forbidden), forbidden
