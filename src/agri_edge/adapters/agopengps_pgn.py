"""AgOpenGPS / AgIO PGN frame parser -- PURE, READ-ONLY, no sockets (stdlib `struct` only).

STATUS: IMPLEMENTED against the public field list; layouts are PARTLY UNVERIFIED.

SOURCE
------
Frame layout and field lists come from the AgOpenGPS-Official/Boards `PGN.md`
(https://github.com/AgOpenGPS-Official/Boards/blob/main/PGN.md), retrieved 2026-10-02:

    0x80 0x81 <src> <pgn> <len> <data * len> <crc>      crc = (sum of bytes 2..n-2) mod 256

That document gives field NAMES, ORDER and BYTE WIDTHS, but not signedness, scale factors
(except where it says "x100" / "* 100" / "* 10") or float width. What this module assumes
beyond the document, each marked UNVERIFIED:

* little-endian (Arduino/C# default; the community Wireshark dissector reads other PGNs
  with `le_uint`, which is supportive but is not a spec);
* longitude/latitude are IEEE-754 doubles, heading/speed/roll/altitude are IEEE-754 floats;
* angles that can be negative (steer angle, roll, pitch, yaw rate) are signed 16-bit;
* speed units are NOT stated, so `speed_raw` is exposed unconverted.

No packet in this repo was captured from a real AgOpenGPS install. The test packets are
constructed from the field list above and are labelled SIMULATED. Treat every decoded
number as SIMULATED until a capture from a real AgIO has been compared against it.

READ-ONLY BY CONSTRUCTION
-------------------------
This module only DECODES bytes it is handed. It cannot build, encode or send a frame, and
nothing in it knows a socket exists. PGN 254 ("Steer Data", AOG -> steer module) is a
steering COMMAND on the wire; here it is decoded purely as an observation and is never
re-emitted, replayed or used as an input to anything that moves.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Optional

STATUS = "IMPLEMENTED (field layout partly UNVERIFIED; packets SIMULATED)"
PREAMBLE = b"\x80\x81"
MAX_DATA_LEN = 255

PGN_MACHINE_DATA = 239        # 0xEF
PGN_FROM_AUTOSTEER = 253      # 0xFD
PGN_STEER_DATA = 254          # 0xFE  (AOG -> steer module: observed only)
PGN_FROM_IMU = 211            # 0xD3
PGN_GPS_MAIN = 214            # 0xD6

# PGN -> exact data length, per PGN.md ("Len" column; 51 is decimal: 8+8+4*5+2+1+2*2+2*4)
EXPECTED_LEN = {
    PGN_GPS_MAIN: 51,
    PGN_STEER_DATA: 8,
    PGN_FROM_AUTOSTEER: 8,
    PGN_FROM_IMU: 8,
    PGN_MACHINE_DATA: 8,
}


class PgnParseError(ValueError):
    """The bytes are not a valid AgOpenGPS frame (or not a plausible one)."""


@dataclass(frozen=True)
class AogFrame:
    src: int
    pgn: int
    data: bytes


@dataclass(frozen=True)
class GpsMainAntenna:
    """PGN 214 'Main Antenna'. Units marked UNVERIFIED are exposed raw."""

    longitude_deg: float
    latitude_deg: float
    heading_dual_deg: float
    heading_true_deg: float
    speed_raw: float              # unit UNVERIFIED
    roll_deg: float               # UNVERIFIED unit/sign convention
    altitude_m: float
    satellites: int
    fix_quality: int              # NMEA GGA quality values (0 none, 1 GPS, 2 DGPS, 4 RTK fix, 5 RTK float)
    hdop: float                   # raw / 100 (the document says "x100")
    age_s: float                  # raw / 100 (the document says "x100")
    imu_heading_raw: int
    imu_roll_raw: int
    imu_pitch_raw: int
    imu_yaw_rate_raw: int
    simulated: bool = True        # decoded from packets nobody has verified against a real AOG


@dataclass(frozen=True)
class SteerDataObserved:
    """PGN 254 as OBSERVED on the wire. This is a command to a steer module; never act on it."""

    speed_raw: int
    status: int                   # raw status byte; meaning UNVERIFIED
    steer_angle_raw: int          # signed; the AOG convention is deg*100 (UNVERIFIED)
    xte_raw: int
    sections_mask: int            # SC1to8 | SC9to16 << 8
    simulated: bool = True


@dataclass(frozen=True)
class FromAutosteer:
    """PGN 253, reported BY the steer module."""

    steer_angle_deg: float        # document: "ActualSteerAngle * 100" -> raw / 100
    imu_heading_raw: int
    imu_roll_raw: int
    switch: int
    pwm_display: int
    simulated: bool = True


@dataclass(frozen=True)
class ImuReport:
    """PGN 211 'From IMU'."""

    heading_raw: int
    roll_raw: int
    gyro_raw: int
    simulated: bool = True


@dataclass(frozen=True)
class MachineDataObserved:
    """PGN 239 'Machine Data' (AOG -> machine module): observed only."""

    uturn: int
    speed_x10: int
    hyd_lift: int
    tram: int
    geo_stop: int
    sections_mask: int
    simulated: bool = True


Decoded = object   # one of the dataclasses above, or None for a known-framing-but-unmodelled PGN


def crc(frame: bytes) -> int:
    """Sum of bytes 2..n-2 (src, pgn, len, data), mod 256 -- as PGN.md defines it."""
    return sum(frame[2:-1]) & 0xFF


def parse_frame(raw: bytes) -> AogFrame:
    """Validate framing + CRC. Raises PgnParseError; never returns a half-trusted frame."""
    if not isinstance(raw, (bytes, bytearray)):
        raise PgnParseError("frame must be bytes")
    raw = bytes(raw)
    if len(raw) < 6:
        raise PgnParseError("frame shorter than the 6-byte minimum")
    if raw[:2] != PREAMBLE:
        raise PgnParseError("bad preamble (expected 0x80 0x81)")
    n = raw[4]
    if len(raw) != 5 + n + 1:
        raise PgnParseError(f"length mismatch: header says {n} data bytes, frame has {len(raw) - 6}")
    if crc(raw) != raw[-1]:
        raise PgnParseError("CRC mismatch")
    exp = EXPECTED_LEN.get(raw[3])
    if exp is not None and n != exp:
        raise PgnParseError(f"PGN {raw[3]} must carry {exp} data bytes, got {n}")
    return AogFrame(src=raw[2], pgn=raw[3], data=raw[5:5 + n])


def _finite(*vals: float) -> bool:
    return all(math.isfinite(v) for v in vals)


def decode(frame: AogFrame) -> Optional[Decoded]:
    """Typed state for the PGNs we model; None for any other (valid) PGN."""
    d = frame.data
    p = frame.pgn
    if p == PGN_GPS_MAIN:
        (lon, lat, hdual, htrue, spd, roll, alt, sats, fixq, hdop, age,
         ih, ir, ip, iy) = struct.unpack("<ddfffffHBHHHhhh", d)
        if not _finite(lon, lat, hdual, htrue, spd, roll, alt):
            raise PgnParseError("non-finite value in GPS frame")
        if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
            raise PgnParseError("GPS position out of range")
        return GpsMainAntenna(lon, lat, hdual, htrue, spd, roll, alt, sats, fixq,
                              hdop / 100.0, age / 100.0, ih, ir, ip, iy)
    if p == PGN_STEER_DATA:
        spd, status, ang, xte, sc1, sc2 = struct.unpack("<HBhBBB", d)
        return SteerDataObserved(spd, status, ang, xte, sc1 | (sc2 << 8))
    if p == PGN_FROM_AUTOSTEER:
        ang, ih, ir, sw, pwm = struct.unpack("<hHhBB", d)
        return FromAutosteer(ang / 100.0, ih, ir, sw, pwm)
    if p == PGN_FROM_IMU:
        h, r, g, _z1, _z2 = struct.unpack("<HhhBB", d)
        return ImuReport(h, r, g)
    if p == PGN_MACHINE_DATA:
        ut, spd, hyd, tram, geo, _x, sc1, sc2 = struct.unpack("<BBBBBBBB", d)
        return MachineDataObserved(ut, spd, hyd, tram, geo, sc1 | (sc2 << 8))
    return None


def parse(raw: bytes) -> tuple[AogFrame, Optional[Decoded]]:
    """Frame + typed state in one call."""
    f = parse_frame(raw)
    return f, decode(f)
