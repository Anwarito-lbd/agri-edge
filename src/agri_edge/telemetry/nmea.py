"""Position from a USB / serial GNSS receiver, for walking a field with the
camera on a pole -- no aircraft, no autopilot.

This is how local training data gets collected before anything flies: the
Pi, the camera and a C$30 u-blox receiver on a 2 m pole, walked along the
field. Sentences parsed: GGA (fix, position, altitude, satellites, HDOP) and
RMC (speed, course). Checksums are verified; a sentence that fails is dropped.

ATTITUDE, STATED PLAINLY
------------------------
A pole has no IMU. Roll and pitch are reported as 0 (the pole is held
vertical, the camera looks straight down) and heading as the course over
ground while walking faster than 0.5 m/s, otherwise None -- so a standing
operator's frames are captured for labelling but not georeferenced, which is
what the georeference does with an unknown heading (F9). `alt_rel_m` is the
pole height, not the GNSS altitude.
"""

from __future__ import annotations

import threading
import time
from dataclasses import replace
from typing import Any

from .mavlink_link import (
    GPS_FIX_2D,
    GPS_FIX_3D,
    GPS_FIX_DGPS,
    GPS_FIX_NONE,
    GPS_FIX_RTK_FIXED,
    GPS_FIX_RTK_FLOAT,
    TelemetrySnapshot,
    TelemetrySource,
)

# GGA fix quality -> the MAVLink fix types the rest of the pipeline speaks.
# 6 is dead reckoning: a position the receiver is guessing, reported as 2D so the
# 3D-fix QA gate refuses it.
_GGA_FIX = {0: GPS_FIX_NONE, 1: GPS_FIX_3D, 2: GPS_FIX_DGPS, 4: GPS_FIX_RTK_FIXED,
            5: GPS_FIX_RTK_FLOAT, 6: GPS_FIX_2D}
KNOTS_TO_MS = 0.514444


def checksum_ok(sentence: str) -> bool:
    s = sentence.strip()
    if not s.startswith("$") or "*" not in s:
        return False
    body, _, given = s[1:].partition("*")
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(given[:2], 16)
    except ValueError:
        return False


def _deg(value: str, hemi: str) -> float | None:
    if not value:
        return None
    dot = value.index(".")
    deg = float(value[: dot - 2]) + float(value[dot - 2:]) / 60.0
    return -deg if hemi in ("S", "W") else deg


def parse(sentence: str) -> dict[str, Any] | None:
    """One NMEA sentence -> fields, or None if unknown / corrupt."""
    if not checksum_ok(sentence):
        return None
    f = sentence.strip()[1:].split("*")[0].split(",")
    kind = f[0][2:]
    try:
        if kind == "GGA" and len(f) >= 10:
            q = int(f[6] or 0)
            return {"type": "GGA", "lat": _deg(f[2], f[3]), "lon": _deg(f[4], f[5]),
                    "fix_type": _GGA_FIX.get(q, GPS_FIX_NONE), "satellites": int(f[7] or 0),
                    "hdop": float(f[8]) if f[8] else 99.9,
                    "alt_msl_m": float(f[9]) if f[9] else None}
        if kind == "RMC" and len(f) >= 9:
            return {"type": "RMC", "valid": f[2] == "A",
                    "speed_ms": float(f[7]) * KNOTS_TO_MS if f[7] else None,
                    "course_deg": float(f[8]) if f[8] else None}
    except (ValueError, IndexError):
        return None
    return None


class NmeaTelemetry(TelemetrySource):
    """Read-only, like every telemetry source: nothing is ever written to the receiver."""

    def __init__(self, port: str, baud: int = 9600, pole_height_m: float = 2.0,
                 min_heading_speed_ms: float = 0.5):
        self.port, self.baud = port, baud
        self.pole_height_m = pole_height_m
        self.min_heading_speed_ms = min_heading_speed_ms
        self._snap = TelemetrySnapshot()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._serial: Any = None

    def feed(self, sentence: str, now: float | None = None) -> None:
        """Fold one sentence into the snapshot. Split out for testing."""
        d = parse(sentence)
        if d is None:
            return
        now = time.time() if now is None else now
        with self._lock:
            s = self._snap
            if d["type"] == "GGA" and d["lat"] is not None:
                s = replace(s, timestamp=now, link_timestamp=now, attitude_timestamp=now,
                            lat=d["lat"], lon=d["lon"], alt_msl_m=d["alt_msl_m"],
                            alt_rel_m=self.pole_height_m, fix_type=d["fix_type"],
                            satellites=d["satellites"], hdop=d["hdop"], roll_deg=0.0, pitch_deg=0.0)
            elif d["type"] == "RMC" and d["valid"]:
                heading = d["course_deg"] if (d["speed_ms"] or 0) >= self.min_heading_speed_ms else None
                s = replace(s, link_timestamp=now, groundspeed_ms=d["speed_ms"], yaw_deg=heading)
            self._snap = s

    def start(self) -> None:  # pragma: no cover - needs a receiver
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("pole capture needs pyserial: pip install pyserial") from exc
        self._serial = serial.Serial(self.port, self.baud, timeout=1.0)
        self._thread = threading.Thread(target=self._loop, daemon=True, name="nmea")
        self._thread.start()

    def _loop(self) -> None:  # pragma: no cover
        while not self._stop.is_set():
            line = self._serial.readline().decode("ascii", errors="replace")
            if line:
                self.feed(line)

    def stop(self) -> None:  # pragma: no cover
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self._serial:
            self._serial.close()

    def snapshot(self) -> TelemetrySnapshot:
        with self._lock:
            return self._snap
