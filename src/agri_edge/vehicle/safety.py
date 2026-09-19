"""Safety supervisor stubs — fail closed for all actuation-adjacent commands."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str
    status: str = "BLOCKED"  # OK | BLOCKED | SIMULATED | BLOCKED-HARDWARE


class SafetySupervisor:
    """Deterministic gate in front of VehicleAdapter command methods.

    Rules (MVP stubs):
      * allow_commands must be explicitly True (SITL / bench only)
      * require_sitl: reject if adapter is not marked SITL
      * never allow when validated_locally-style treatment flags are involved here
        (treatment is a separate stack; this gate is flight-command only)
    """

    def __init__(
        self,
        *,
        allow_commands: bool = False,
        require_sitl: bool = True,
        label: str = "default",
    ) -> None:
        self.allow_commands = allow_commands
        self.require_sitl = require_sitl
        self.label = label

    def check_command(self, command: str, *, sitl: bool = False) -> SafetyDecision:
        if not self.allow_commands:
            return SafetyDecision(
                False,
                f"commands disabled on supervisor '{self.label}' (fail closed)",
                "BLOCKED",
            )
        if self.require_sitl and not sitl:
            return SafetyDecision(
                False,
                "require_sitl=True and vehicle is not SITL — fail closed",
                "BLOCKED-HARDWARE",
            )
        return SafetyDecision(True, f"allowed in SIMULATED/SITL context: {command}", "SIMULATED")
