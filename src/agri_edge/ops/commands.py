"""Command confirmation helpers (§152). Never bypass safety gates."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

from .types import new_id, utcnow


ALLOWED_COMMANDS = frozenset({
    "irrigation/set",  # ground MQTT only
    "ack_alert",
    "resolve_alert",
    "escalate_alert",
})

FORBIDDEN = frozenset({
    "mavlink_write",
    "arm",
    "pump_unrestricted",
    "greenhouse_actuator_auto",
    "dock_service",
})


@dataclass
class CommandConfirmation:
    confirmation_id: str
    command: str
    confirmed: bool
    reason: str
    requires_human: bool = True
    channel: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def confirm_command(command: str, *, human_confirmed: bool = False, actor: str = "operator") -> CommandConfirmation:
    if command in FORBIDDEN or any(f in command for f in FORBIDDEN):
        return CommandConfirmation(
            confirmation_id=new_id("cmd_"),
            command=command,
            confirmed=False,
            reason="Forbidden by safety policy",
            requires_human=True,
        )
    if command not in ALLOWED_COMMANDS:
        return CommandConfirmation(
            confirmation_id=new_id("cmd_"),
            command=command,
            confirmed=False,
            reason="Unknown command",
            requires_human=True,
        )
    if not human_confirmed:
        return CommandConfirmation(
            confirmation_id=new_id("cmd_"),
            command=command,
            confirmed=False,
            reason="Human confirmation required",
            requires_human=True,
            channel="mqtt_ground_only" if command == "irrigation/set" else None,
        )
    return CommandConfirmation(
        confirmation_id=new_id("cmd_"),
        command=command,
        confirmed=True,
        reason=f"Confirmed by {actor} at {utcnow().isoformat()}",
        requires_human=True,
        channel="mqtt_ground_only" if command == "irrigation/set" else "ops_api",
    )
