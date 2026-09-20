"""VehicleAdapter protocol and shared types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class VehicleState:
    """Normalized vehicle snapshot (read path)."""

    connected: bool = False
    mode: str = "UNKNOWN"
    armed: bool = False
    lat: float | None = None
    lon: float | None = None
    alt_m: float | None = None
    heading_deg: float | None = None
    groundspeed_mps: float | None = None
    battery_pct: float | None = None
    sitl: bool = False
    # True when these numbers were invented rather than measured. Separate from
    # `sitl`: a SITL flight produces real MAVLink from a simulated vehicle,
    # which is a different thing from this adapter making a state up because it
    # could not connect to anything.
    simulated: bool = False
    source: str = "none"


@dataclass(frozen=True)
class CommandResult:
    """Outcome of a vehicle command. Fail-closed: ok=False by default."""

    ok: bool = False
    command: str = ""
    reason: str = "fail_closed"
    status: str = "BLOCKED"  # OK | BLOCKED | SIMULATED | BLOCKED-HARDWARE
    details: dict = field(default_factory=dict)


@runtime_checkable
class VehicleAdapter(Protocol):
    """Abstraction over FC companion link. Commands must fail closed."""

    name: str

    def connect(self) -> bool:
        """True only if a real vehicle link was established.

        False means the adapter is usable but simulated. It is not an error and
        does not raise -- but it must never be reported as a connection.
        """
        ...

    def close(self) -> None:
        ...

    def get_state(self) -> VehicleState:
        ...

    def arm(self) -> CommandResult:
        ...

    def disarm(self) -> CommandResult:
        ...

    def set_mode(self, mode: str) -> CommandResult:
        ...

    def upload_mission(self, waypoints: list[dict]) -> CommandResult:
        ...
