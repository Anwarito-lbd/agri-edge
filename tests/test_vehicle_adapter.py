"""VehicleAdapter fail-closed command surface."""
from __future__ import annotations

from agri_edge.vehicle import (
    ArduPilotAdapter,
    CommandResult,
    SafetySupervisor,
    VehicleAdapter,
    VehicleState,
)


def test_default_supervisor_blocks_commands():
    adapter = ArduPilotAdapter(sitl=True)  # allow_commands defaults False
    assert adapter.connect() is True
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
