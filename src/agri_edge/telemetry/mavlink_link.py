"""Read-only MAVLink telemetry from the autopilot.

SAFETY CONTRACT
---------------
This module is deliberately incapable of commanding the aircraft. It sends
nothing to the autopilot except the heartbeat required for the link to be
considered alive, and it exposes no method that could arm, disarm, change mode,
upload a mission or trigger a failsafe.

The reason is the architecture the whole system rests on: the Pixhawk owns
attitude stabilisation, navigation and failsafes; the Raspberry Pi owns
perception and data management. If a neural-network process stalls the Pi or the
SD card fails, the aircraft must still fly its geofence, lost-link, battery and
return-to-home logic correctly. A companion computer that can command the vehicle
puts that guarantee at the mercy of a Linux userspace process.

If a future mission genuinely requires commanded flight (e.g. event-triggered
orbit), it belongs in a separate, explicitly named module with its own review --
not as an addition here.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Optional

# MAVLink GPS_FIX_TYPE values we care about.
GPS_FIX_NONE = 0
GPS_FIX_2D = 2
GPS_FIX_3D = 3
GPS_FIX_DGPS = 4
GPS_FIX_RTK_FLOAT = 5
GPS_FIX_RTK_FIXED = 6

FIX_TYPE_NAMES = {
    0: "no-gps",
    1: "no-fix",
    2: "2d",
    3: "3d",
    4: "dgps",
    5: "rtk-float",
    6: "rtk-fixed",
}


@dataclass(frozen=True)
class TelemetrySnapshot:
    """An immutable view of vehicle state at a moment in time.

    Immutable because it gets attached to captured images as provenance. A
    snapshot that could be mutated after the fact is not provenance.
    """

    timestamp: float = 0.0
    lat: float | None = None
    lon: float | None = None
    alt_msl_m: float | None = None
    alt_rel_m: float | None = None
    roll_deg: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None
    groundspeed_ms: float | None = None
    fix_type: int = GPS_FIX_NONE
    satellites: int = 0
    hdop: float = 99.9
    battery_pct: float | None = None

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None and self.fix_type >= GPS_FIX_3D

    @property
    def fix_name(self) -> str:
        return FIX_TYPE_NAMES.get(self.fix_type, f"unknown-{self.fix_type}")

    @property
    def is_rtk_fixed(self) -> bool:
        return self.fix_type == GPS_FIX_RTK_FIXED

    def age_s(self, now: float | None = None) -> float:
        return (now if now is not None else time.time()) - self.timestamp


class TelemetrySource:
    """Interface for anything that can supply a TelemetrySnapshot."""

    def start(self) -> None:  # pragma: no cover - trivial
        pass

    def stop(self) -> None:  # pragma: no cover - trivial
        pass

    def snapshot(self) -> TelemetrySnapshot:
        raise NotImplementedError


class SimulatedTelemetry(TelemetrySource):
    """Deterministic telemetry for bench work and tests.

    Flies a straight line east at constant altitude so that captured frames have
    plausible, monotonically changing positions.
    """

    def __init__(
        self,
        start_lat: float = 50.4452,     # Near Saskatoon, SK
        start_lon: float = -104.6189,
        alt_rel_m: float = 100.0,
        groundspeed_ms: float = 10.0,
        fix_type: int = GPS_FIX_RTK_FIXED,
    ):
        self._lat = start_lat
        self._lon = start_lon
        self._alt = alt_rel_m
        self._speed = groundspeed_ms
        self._fix = fix_type
        self._t0 = time.time()

    def snapshot(self) -> TelemetrySnapshot:
        now = time.time()
        elapsed = now - self._t0
        # ~111,320 m per degree of longitude at the equator, scaled by latitude.
        import math

        m_per_deg_lon = 111_320.0 * math.cos(math.radians(self._lat))
        lon = self._lon + (self._speed * elapsed) / m_per_deg_lon
        return TelemetrySnapshot(
            timestamp=now,
            lat=self._lat,
            lon=lon,
            alt_msl_m=self._alt + 500.0,
            alt_rel_m=self._alt,
            roll_deg=0.0,
            pitch_deg=0.0,
            yaw_deg=90.0,
            groundspeed_ms=self._speed,
            fix_type=self._fix,
            satellites=18,
            hdop=0.7,
            battery_pct=max(0.0, 100.0 - elapsed * 0.5),
        )


class MavlinkTelemetry(TelemetrySource):
    """Live read-only telemetry from a Pixhawk/Cube over MAVLink.

    Requires the optional `mavlink` extra (pymavlink). Runs a background reader
    thread and keeps only the latest snapshot -- the pipeline wants current state,
    not a backlog.
    """

    def __init__(self, connection: str, source_system: int = 200, heartbeat_timeout_s: float = 5.0):
        self._connection_str = connection
        self._source_system = source_system
        self._heartbeat_timeout_s = heartbeat_timeout_s
        # Any, not a pymavlink type: pymavlink is an optional extra, so the
        # annotation cannot name a class that may not be installed. Left
        # unannotated it inferred as None and every use of it was a mypy
        # error.
        self._conn: Any = None
        self._snapshot = TelemetrySnapshot()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        try:
            from pymavlink import mavutil
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "pymavlink is required for live telemetry. "
                "Install with: pip install 'agri-edge[mavlink]'"
            ) from exc

        self._conn = mavutil.mavlink_connection(
            self._connection_str, source_system=self._source_system
        )

        # pymavlink's wait_heartbeat RETURNS None on timeout -- it does not
        # raise. Ignoring the return value means start() succeeds against a
        # bound UDP socket with no vehicle on the other end, and every snapshot
        # afterwards is an empty TelemetrySnapshot: fix_type NONE, lat and lon
        # None, hdop 99.9. Those are the right values, but "started" then means
        # nothing, and ArduPilotAdapter.connect() was reporting a link on the
        # strength of it.
        #
        # Started means a vehicle is talking. Anything else raises.
        heartbeat = self._conn.wait_heartbeat(timeout=self._heartbeat_timeout_s)
        if heartbeat is None:
            self._conn.close()
            self._conn = None
            raise ConnectionError(
                f"No MAVLink heartbeat on {self._connection_str} within "
                f"{self._heartbeat_timeout_s:.0f}s. Nothing is transmitting "
                "there -- check the autopilot is powered, the radio is linked, "
                "and the endpoint and baud rate are right."
            )

        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, name="mavlink-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._conn is not None:
            self._conn.close()

    def _read_loop(self) -> None:  # pragma: no cover - requires a live link
        while not self._stop.is_set():
            msg = self._conn.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue
            self._ingest(msg.get_type(), msg.to_dict())

    def _ingest(self, msg_type: str, d: dict) -> None:
        """Fold one MAVLink message into the current snapshot.

        Split out from the read loop so it can be unit-tested without a vehicle.
        """
        with self._lock:
            s = self._snapshot
            now = time.time()

            if msg_type == "GLOBAL_POSITION_INT":
                s = replace(
                    s,
                    timestamp=now,
                    lat=d["lat"] / 1e7,
                    lon=d["lon"] / 1e7,
                    alt_msl_m=d["alt"] / 1000.0,
                    alt_rel_m=d["relative_alt"] / 1000.0,
                    yaw_deg=d.get("hdg", 0) / 100.0 if d.get("hdg", 0) != 65535 else s.yaw_deg,
                )
            elif msg_type == "GPS_RAW_INT":
                s = replace(
                    s,
                    timestamp=now,
                    fix_type=d.get("fix_type", GPS_FIX_NONE),
                    satellites=d.get("satellites_visible", 0),
                    hdop=d.get("eph", 9999) / 100.0,
                )
            elif msg_type == "ATTITUDE":
                import math

                s = replace(
                    s,
                    timestamp=now,
                    roll_deg=math.degrees(d["roll"]),
                    pitch_deg=math.degrees(d["pitch"]),
                    yaw_deg=math.degrees(d["yaw"]),
                )
            elif msg_type == "VFR_HUD":
                s = replace(s, timestamp=now, groundspeed_ms=d.get("groundspeed"))
            elif msg_type == "SYS_STATUS":
                remaining = d.get("battery_remaining", -1)
                if remaining >= 0:
                    s = replace(s, timestamp=now, battery_pct=float(remaining))

            self._snapshot = s

    def snapshot(self) -> TelemetrySnapshot:
        with self._lock:
            return self._snapshot


def build_telemetry_source(cfg, simulated: bool = False) -> TelemetrySource:
    if simulated:
        return SimulatedTelemetry()
    return MavlinkTelemetry(
        connection=cfg.connection,
        source_system=cfg.source_system,
        heartbeat_timeout_s=cfg.heartbeat_timeout_s,
    )
