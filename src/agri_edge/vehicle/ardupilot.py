"""ArduPilotAdapter -- wraps the SITL / read-only MAVLink scaffolding.

Telemetry is read-only, through `agri_edge.telemetry.mavlink_link`. Commands go
through SafetySupervisor and fail closed unless allow_commands + SITL.

THE BUG THIS FILE USED TO HAVE
------------------------------
The telemetry path imported `agri_edge.mavlink.connection` and
`agri_edge.mavlink.telemetry`. Neither exists -- the real reader has always been
`agri_edge.telemetry.mavlink_link.MavlinkTelemetry`. Both imports sat inside a
bare `except Exception`, so the ModuleNotFoundError was swallowed, the adapter
fell through to simulation, and `connect()` returned True anyway.

The result was an adapter that reported `connected=True` at latitude 45.0,
longitude -75.0 with no aircraft, no autopilot and no radio. Only the `source`
field said "simulated", and nothing was obliged to read it. An audit found it by
calling `connect()` with a dead UDP endpoint and watching it succeed.

So two things changed, and they are the point of the module now:

* the import names the module that exists, and an ImportError from it is logged
  rather than silently absorbed into the simulated branch;
* **`connect()` returns whether a real vehicle link was established.** Simulated
  operation is still available and still useful, but it is no longer disguised
  as a connection. `VehicleState.connected` now means a real link; `simulated`
  says which mode produced the numbers.

That distinction matters because the spec's default failure policy is
"uncertain position -> application OFF". A fabricated position that claims to be
connected is exactly the input that defeats it.
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
      * get_state / connect -- IMPLEMENTED when pymavlink + a live endpoint are
        present; otherwise SIMULATED, and `connect()` returns False to say so
      * arm/disarm/set_mode/upload_mission -- fail closed unless the supervisor
        allows them, and even then SIMULATED only
      * Physical FC command path -- BLOCKED-HARDWARE, never emitted
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
        self._real_link = False
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
        """Open a real link if one is there. Returns whether it is.

        Falling back to simulation is fine and does not raise; reporting that
        fallback as a connection is not. A caller that checks the return value
        of `connect()` is entitled to believe it.
        """
        try:
            from agri_edge.telemetry.mavlink_link import MavlinkTelemetry

            link = MavlinkTelemetry(self.connection_string)
            # Blocks until a heartbeat arrives or the timeout expires; raises if
            # pymavlink is missing or nothing is talking on that endpoint.
            link.start()
            self._conn = link
            self._real_link = True
            log.info("ArduPilotAdapter connected to %s", self.connection_string)
            return True
        except Exception as exc:
            log.info(
                "ArduPilotAdapter running SIMULATED: no MAVLink link on %s (%s: %s)",
                self.connection_string, type(exc).__name__, exc,
            )
            self._conn = None
            self._real_link = False
            self._simulated = VehicleState(
                    connected=False,
                mode=self._mode_sim,
                armed=self._armed_sim,
                # A plausible-looking position is the dangerous part of a
                # simulated state, so it stays None. Callers that need a
                # position get nothing rather than a number from Ottawa.
                lat=None,
                lon=None,
                alt_m=None,
                heading_deg=None,
                groundspeed_mps=0.0,
                battery_pct=100.0,
                sitl=self.sitl,
                simulated=True,
                source="simulated",
            )
            return False

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
            # Simulated. `connected` stays False and `simulated` stays True so
            # that neither a caller reading the flag nor one reading the string
            # can mistake this for a vehicle.
            return VehicleState(
                connected=False,
                mode=self._mode_sim,
                armed=self._armed_sim,
                lat=self._simulated.lat,
                lon=self._simulated.lon,
                alt_m=self._simulated.alt_m,
                heading_deg=self._simulated.heading_deg,
                groundspeed_mps=self._simulated.groundspeed_mps,
                battery_pct=self._simulated.battery_pct,
                sitl=self.sitl,
                simulated=True,
                source="simulated",
            )
        # Read-only. Never send set_* from here -- MavlinkTelemetry has no
        # write surface at all, and a test asserts that.
        try:
            snap = self._conn.snapshot()
        except Exception as exc:
            # A link that stops answering is a degraded link, not a simulated
            # one, and must not be reported as either connected or simulated.
            log.warning("MAVLink snapshot failed (%s); reporting disconnected", exc)
            return VehicleState(
                connected=False, mode=self._mode_sim, armed=self._armed_sim,
                sitl=self.sitl, source="mavlink-lost",
            )

        return VehicleState(
            connected=True,
            mode=self._mode_sim,
            armed=self._armed_sim,
            # has_position is False without a 3D fix, and an unfixed lat/lon is
            # worse than none: it looks like a position.
            lat=snap.lat if snap.has_position else None,
            lon=snap.lon if snap.has_position else None,
            alt_m=snap.alt_rel_m,
            heading_deg=snap.yaw_deg,
            groundspeed_mps=snap.groundspeed_ms,
            battery_pct=snap.battery_pct,
            sitl=self.sitl,
            source="mavlink",
        )

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
