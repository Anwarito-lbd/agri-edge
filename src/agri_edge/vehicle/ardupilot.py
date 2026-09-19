"""ArduPilotAdapter — wraps existing SITL / read-only MAVLink scaffolding.

Default: telemetry read-only (uses agri_edge.mavlink when available).
Commands go through SafetySupervisor and fail closed unless allow_commands+SITL.
"""
from __future__ import annotations

import logging
from typing import Any

from .adapter import CommandResult, VehicleState
from .safety import SafetySupervisor

log = logging.getLogger(__name__)


class ArduPilotAdapter:
    """ArduPilot-facing VehicleAdapter.

    Status:
      * get_state / connect — IMPLEMENTED when pymavlink+endpoint available, else SIMULATED
      * arm/disarm/set_mode/upload_mission — fail closed unless supervisor allows (SIMULATED)
      * Physical FC command path — BLOCKED-HARDWARE
    """

    name = "ardupilot"

    def __init__(
        self,
        connection_string: str = "udp:127.0.0.1:14550",
        *,
        sitl: bool = True,
        supervisor: SafetySupervisor | None = None,
        simulated_state: VehicleState | None = None,
    ) -> None:
        self.connection_string = connection_string
        self.sitl = sitl
        self.supervisor = supervisor or SafetySupervisor(allow_commands=False, require_sitl=True)
        self._conn: Any = None
        self._simulated = simulated_state or VehicleState(
            connected=False,
            mode="SIMULATED",
            armed=False,
            sitl=sitl,
            source="simulated",
        )
        self._armed_sim = False
        self._mode_sim = "GUIDED" if sitl else "UNKNOWN"

    def connect(self) -> bool:
        """Best-effort connect. Falls back to simulated state without raising."""
        try:
            from agri_edge.mavlink.connection import open_connection  # type: ignore

            self._conn = open_connection(self.connection_string)
            return True
        except Exception:
            try:
                # Optional: pymavlink direct
                from pymavlink import mavutil  # type: ignore

                self._conn = mavutil.mavlink_connection(self.connection_string)
                return True
            except Exception as exc:
                log.info("ArduPilotAdapter connect SIMULATED (%s)", exc)
                self._conn = None
                self._simulated = VehicleState(
                    connected=True,
                    mode=self._mode_sim,
                    armed=self._armed_sim,
                    lat=45.0,
                    lon=-75.0,
                    alt_m=0.0,
                    heading_deg=0.0,
                    groundspeed_mps=0.0,
                    battery_pct=100.0,
                    sitl=self.sitl,
                    source="simulated",
                )
                return True  # simulated connect succeeds for software tests

    def close(self) -> None:
        if self._conn is not None:
            try:
                close = getattr(self._conn, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass
        self._conn = None

    def get_state(self) -> VehicleState:
        if self._conn is None:
            return VehicleState(
                connected=self._simulated.connected,
                mode=self._mode_sim,
                armed=self._armed_sim,
                lat=self._simulated.lat,
                lon=self._simulated.lon,
                alt_m=self._simulated.alt_m,
                heading_deg=self._simulated.heading_deg,
                groundspeed_mps=self._simulated.groundspeed_mps,
                battery_pct=self._simulated.battery_pct,
                sitl=self.sitl,
                source="simulated",
            )
        # Read-only best effort — never send set_* here
        try:
            from agri_edge.mavlink.telemetry import read_snapshot  # type: ignore

            snap = read_snapshot(self._conn)
            return VehicleState(
                connected=True,
                mode=str(snap.get("mode", self._mode_sim)),
                armed=bool(snap.get("armed", False)),
                lat=snap.get("lat"),
                lon=snap.get("lon"),
                alt_m=snap.get("alt_m"),
                heading_deg=snap.get("heading_deg"),
                groundspeed_mps=snap.get("groundspeed_mps"),
                battery_pct=snap.get("battery_pct"),
                sitl=self.sitl,
                source="mavlink",
            )
        except Exception:
            return VehicleState(connected=True, mode=self._mode_sim, armed=self._armed_sim, sitl=self.sitl, source="mavlink-partial")

    def _gate(self, command: str) -> CommandResult | None:
        decision = self.supervisor.check_command(command, sitl=self.sitl)
        if not decision.allowed:
            return CommandResult(
                ok=False,
                command=command,
                reason=decision.reason,
                status=decision.status,
            )
        return None

    def arm(self) -> CommandResult:
        blocked = self._gate("arm")
        if blocked:
            return blocked
        # SIMULATED only — do not emit MAV_CMD_COMPONENT_ARM_DISARM to hardware
        self._armed_sim = True
        return CommandResult(ok=True, command="arm", reason="simulated arm (SITL)", status="SIMULATED")

    def disarm(self) -> CommandResult:
        blocked = self._gate("disarm")
        if blocked:
            return blocked
        self._armed_sim = False
        return CommandResult(ok=True, command="disarm", reason="simulated disarm (SITL)", status="SIMULATED")

    def set_mode(self, mode: str) -> CommandResult:
        blocked = self._gate(f"set_mode:{mode}")
        if blocked:
            return blocked
        self._mode_sim = mode
        return CommandResult(
            ok=True,
            command="set_mode",
            reason=f"simulated mode={mode}",
            status="SIMULATED",
            details={"mode": mode},
        )

    def upload_mission(self, waypoints: list[dict]) -> CommandResult:
        blocked = self._gate("upload_mission")
        if blocked:
            return blocked
        if not waypoints:
            return CommandResult(ok=False, command="upload_mission", reason="empty waypoints", status="BLOCKED")
        return CommandResult(
            ok=True,
            command="upload_mission",
            reason=f"simulated upload of {len(waypoints)} waypoints (SITL)",
            status="SIMULATED",
            details={"count": len(waypoints)},
        )
