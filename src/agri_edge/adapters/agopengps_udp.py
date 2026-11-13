"""Receive-only UDP listener + read-only AgOpenGPS adapter.

STATUS: IMPLEMENTED; tested over LOOPBACK with SIMULATED packets only. Never pointed at a
real AgIO / AgOpenGPS install, so which port and which interface a given install uses is
UNVERIFIED. (PGN.md and AgOpenGPS forum threads say AgIO listens on UDP 9999 and modules
listen on 8888; a real setup may differ -- the port is a parameter, not an assumption.)

READ-ONLY BY CONSTRUCTION
-------------------------
* The socket is bound and only ever `recvfrom`'d. This module contains no `send`,
  `sendto`, `connect` or broadcast call, and `tests/test_agopengps.py` asserts that by
  walking the AST. Nothing agri-edge produces can reach AgOpenGPS or a steering module.
* `engage`, `set_steer_angle`, `set_speed`, `command_steer`, and any other attribute
  that smells like a command, raise `GuidanceCommandRefused`. There is no flag that
  enables them. Engaging steering needs the SafetySupervisor and an independent hardware
  interlock; both are BLOCKED-HARDWARE.
* `GuidanceState.engaged` is ALWAYS False: agri-edge never engages anything. What AgOpenGPS
  itself reports (e.g. the PGN 254 status byte) is available as `observed`, as raw data
  with no authority.
* Binding is opt-in: `connect()` opens nothing unless the adapter was built with
  `allow_network=True`, and the default bind address is loopback.
* Malformed / oversized / CRC-bad datagrams are counted and dropped; they never raise out of
  the receive loop and never update state.
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .agopengps import GuidanceCommandRefused, GuidanceState, GuidanceTrack
from .agopengps_pgn import (
    PGN_FROM_AUTOSTEER,
    PGN_FROM_IMU,
    PGN_GPS_MAIN,
    PGN_MACHINE_DATA,
    PGN_STEER_DATA,
    parse,
)

ADAPTER_STATUS = "IMPLEMENTED (loopback/SIMULATED packets only)"
DEFAULT_PORT = 9999                 # UNVERIFIED for any given install
DEFAULT_BIND = "127.0.0.1"
MAX_DATAGRAM = 512                  # largest known frame is 57 bytes; anything bigger is junk
DEFAULT_STALE_S = 2.0

_SLOT = {
    PGN_GPS_MAIN: "gps", PGN_STEER_DATA: "steer_data", PGN_FROM_AUTOSTEER: "from_autosteer",
    PGN_FROM_IMU: "imu", PGN_MACHINE_DATA: "machine",
}


@dataclass(frozen=True)
class ObservedGuidance:
    """Latest decoded frame per PGN, with receive times. All values SIMULATED/UNVERIFIED."""

    gps: Any = None
    steer_data: Any = None          # an AOG -> steer-module COMMAND, observed only
    from_autosteer: Any = None
    imu: Any = None
    machine: Any = None
    last_rx: float = 0.0
    frames_ok: int = 0
    frames_rejected: int = 0
    frames_unmodelled: int = 0


class AgOpenGpsUdpListener:
    """Bind a UDP socket and fold valid frames into typed state. Never transmits."""

    def __init__(self, port: int = DEFAULT_PORT, bind: str = DEFAULT_BIND, *,
                 now_fn: Callable[[], float] = time.time) -> None:
        self.port = int(port)
        self.bind = bind
        self._now = now_fn
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {}
        self._rx_at: dict[str, float] = {}
        self._ok = self._bad = self._other = 0
        self._last_rx = 0.0
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # -- state ---------------------------------------------------------------------
    def feed(self, datagram: bytes) -> bool:
        """Process one datagram. True if it was a valid frame. Never raises."""
        if len(datagram) > MAX_DATAGRAM:
            with self._lock:
                self._bad += 1
            return False
        try:
            frame, decoded = parse(datagram)
        except Exception:      # noqa: BLE001 -- a bad packet must not kill the loop
            with self._lock:
                self._bad += 1
            return False
        with self._lock:
            now = self._now()
            self._last_rx = now
            self._ok += 1
            slot = _SLOT.get(frame.pgn)
            if decoded is None or slot is None:
                self._other += 1
            else:
                self._state[slot] = decoded
                self._rx_at[slot] = now
        return True

    def observed(self) -> ObservedGuidance:
        with self._lock:
            return ObservedGuidance(
                last_rx=self._last_rx, frames_ok=self._ok, frames_rejected=self._bad,
                frames_unmodelled=self._other, **dict(self._state))

    def age_s(self) -> Optional[float]:
        with self._lock:
            return (self._now() - self._last_rx) if self._last_rx else None

    # -- socket --------------------------------------------------------------------
    def start(self) -> int:
        """Bind and start the receive thread. Returns the bound port (useful with port=0)."""
        if self._sock is not None:
            return self.port
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.bind((self.bind, self.port))
        self._sock = s
        self.port = s.getsockname()[1]
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="agopengps-rx", daemon=True)
        self._thread.start()
        return self.port

    def _run(self) -> None:
        s = self._sock
        assert s is not None
        while not self._stop.is_set():
            try:
                data, _addr = s.recvfrom(MAX_DATAGRAM + 1)
            except socket.timeout:
                continue
            except OSError:
                break
            self.feed(data)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
        self._thread = None


class AgOpenGpsReadOnlyAdapter:
    """GuidanceAdapter over the listener. Observes; never commands."""

    name = "agopengps_udp_readonly"
    status = ADAPTER_STATUS
    simulated = True        # no real AgOpenGPS install has ever been observed

    _REFUSED = frozenset({"engage", "set_steer_angle", "set_speed", "command_steer", "steer",
                          "send", "write", "send_pgn", "set_section", "set_sections", "disengage"})

    def __init__(self, *, allow_network: bool = False, port: int = DEFAULT_PORT,
                 bind: str = DEFAULT_BIND, stale_after_s: float = DEFAULT_STALE_S,
                 listener: Optional[AgOpenGpsUdpListener] = None) -> None:
        self.allow_network = bool(allow_network)
        self.stale_after_s = float(stale_after_s)
        self.listener = listener or AgOpenGpsUdpListener(port, bind)
        self._track: Optional[GuidanceTrack] = None
        self.loaded: list[str] = []

    def connect(self) -> bool:
        """Open the receive socket -- only with allow_network=True. Else False, opens nothing."""
        if not self.allow_network:
            return False
        self.listener.start()
        return True

    def close(self) -> None:
        self.listener.stop()

    def observed(self) -> ObservedGuidance:
        return self.listener.observed()

    def get_state(self) -> GuidanceState:
        age = self.listener.age_s()
        fresh = age is not None and age <= self.stale_after_s
        return GuidanceState(
            connected=bool(fresh),
            engaged=False,                  # agri-edge never engages; see module docstring
            track_id=self._track.track_id if self._track else None,
            cross_track_error_m=None,       # PGN xte scale is UNVERIFIED -> not invented here
            source="agopengps_udp" if fresh else "none",
            simulated=True,
        )

    def load_track(self, track: GuidanceTrack) -> dict:
        """Memory only. Nothing is sent to AgOpenGPS (this adapter cannot transmit)."""
        if len(track.points) < 2:
            return {"ok": False, "reason": "track_needs_two_points", "status": "REJECTED"}
        for lat, lon in track.points:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return {"ok": False, "reason": "point_out_of_range", "status": "REJECTED"}
        self._track = track
        self.loaded.append(track.track_id)
        return {"ok": True, "status": "SIMULATED", "track_id": track.track_id,
                "note": "stored in memory only; this adapter cannot transmit to AgOpenGPS"}

    # -- everything that could steer is refused --------------------------------------
    def engage(self) -> Any:
        raise GuidanceCommandRefused("engage refused: guidance is observe-only (BLOCKED-HARDWARE)")

    def set_steer_angle(self, *_a: Any, **_k: Any) -> Any:
        raise GuidanceCommandRefused("set_steer_angle refused (BLOCKED-HARDWARE)")

    def set_speed(self, *_a: Any, **_k: Any) -> Any:
        raise GuidanceCommandRefused("set_speed refused (BLOCKED-HARDWARE)")

    def command_steer(self, *_a: Any, **_k: Any) -> Any:
        raise GuidanceCommandRefused("command_steer refused (BLOCKED-HARDWARE)")

    def __getattr__(self, item: str) -> Any:
        # Only reached for attributes that do not exist: any command-shaped name is a
        # loud refusal rather than an AttributeError someone might paper over.
        if item in self._REFUSED or item.startswith(("send", "set_", "command_", "write")):
            def _refused(*_a: Any, **_k: Any) -> Any:
                raise GuidanceCommandRefused(f"{item} refused: guidance is observe-only")
            return _refused
        raise AttributeError(item)
