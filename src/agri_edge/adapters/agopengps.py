"""GuidanceAdapter interface + AgOpenGPS stub.

STATUS: SIMULATED / stub. AgOpenGPS (GPL-3.0) is an external tractor-guidance
application; agri-edge would talk to it only across a process boundary (its UDP
PGN messages), never by linking its code. This stub performs **no I/O at all**: it
holds a track and a state in memory so the interface and its safety stance can be
tested.

SAFETY STANCE, encoded in the interface
---------------------------------------
Guidance output steers a vehicle, so the adapter is **read/plan only** toward the
rest of agri-edge:

* `get_state()` and `load_track()` are fine;
* anything that would *engage* steering (`engage`, `set_steer_angle`, `set_speed`,
  `command_steer`) raises `GuidanceCommandRefused` -- there is no flag that enables
  it. Engaging a real steering loop is BLOCKED-HARDWARE and needs the SafetySupervisor
  + an independent steering interlock, none of which exist yet.
* An AI/YOLO result never reaches this interface; it has no method that accepts one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

ADAPTER_STATUS = "SIMULATED"


class GuidanceCommandRefused(RuntimeError):
    """Any actuation-adjacent guidance command. Always raised by the stub."""


@dataclass(frozen=True)
class GuidanceTrack:
    """An A-B (or curve) line in WGS-84, as the planner would hand to guidance."""

    track_id: str
    points: tuple[tuple[float, float], ...]    # (lat, lon)
    swath_m: float = 0.0
    synthetic: bool = True


@dataclass(frozen=True)
class GuidanceState:
    connected: bool = False
    engaged: bool = False
    track_id: Optional[str] = None
    cross_track_error_m: Optional[float] = None
    source: str = "none"
    simulated: bool = True


@runtime_checkable
class GuidanceAdapter(Protocol):
    name: str

    def connect(self) -> bool: ...

    def close(self) -> None: ...

    def get_state(self) -> GuidanceState: ...

    def load_track(self, track: GuidanceTrack) -> dict: ...

    def engage(self) -> Any: ...


class AgOpenGpsAdapterStub:
    name = "agopengps_stub"
    status = ADAPTER_STATUS
    simulated = True

    def __init__(self) -> None:
        self._track: Optional[GuidanceTrack] = None
        self.loaded: list[str] = []

    def connect(self) -> bool:
        """Never connects. False means 'simulated', exactly as the VehicleAdapter says."""
        return False

    def close(self) -> None:
        return None

    def get_state(self) -> GuidanceState:
        return GuidanceState(connected=False, engaged=False,
                             track_id=self._track.track_id if self._track else None,
                             cross_track_error_m=None, source="stub", simulated=True)

    def load_track(self, track: GuidanceTrack) -> dict:
        if len(track.points) < 2:
            return {"ok": False, "reason": "track_needs_two_points", "status": "REJECTED"}
        for lat, lon in track.points:
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                return {"ok": False, "reason": "point_out_of_range", "status": "REJECTED"}
        self._track = track
        self.loaded.append(track.track_id)
        return {"ok": True, "status": "SIMULATED", "track_id": track.track_id,
                "note": "stored in memory only; nothing was sent to AgOpenGPS"}

    # -- everything below steers a vehicle: always refused ---------------------------
    def engage(self) -> Any:
        raise GuidanceCommandRefused("engage refused: guidance output is read/plan-only (BLOCKED-HARDWARE)")

    def set_steer_angle(self, *_a: Any, **_k: Any) -> Any:
        raise GuidanceCommandRefused("set_steer_angle refused (BLOCKED-HARDWARE)")

    def set_speed(self, *_a: Any, **_k: Any) -> Any:
        raise GuidanceCommandRefused("set_speed refused (BLOCKED-HARDWARE)")

    def command_steer(self, *_a: Any, **_k: Any) -> Any:
        raise GuidanceCommandRefused("command_steer refused (BLOCKED-HARDWARE)")


