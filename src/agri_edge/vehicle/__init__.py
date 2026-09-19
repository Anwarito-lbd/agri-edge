"""VehicleAdapter — fail-closed companion interface to the flight stack.

MAVLink companion remains read-only by default. Command methods exist only
behind VehicleAdapter + safety stubs and **fail closed** unless explicitly
armed for SITL/sim. Never wire YOLO/LLM → motors.
"""
from .adapter import (
    CommandResult,
    VehicleAdapter,
    VehicleState,
)
from .ardupilot import ArduPilotAdapter
from .safety import SafetySupervisor, SafetyDecision

__all__ = [
    "CommandResult",
    "VehicleAdapter",
    "VehicleState",
    "ArduPilotAdapter",
    "SafetySupervisor",
    "SafetyDecision",
]
