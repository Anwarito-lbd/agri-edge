"""Builds tests/fixtures/agopengps_samples.json.  SIMULATED.

These packets are CONSTRUCTED from the field list in AgOpenGPS-Official/Boards PGN.md
(retrieved 2026-10-02): preamble 0x80 0x81, src, pgn, len, data, crc = sum(bytes[2:-1]) & 0xFF.
Byte order, float widths and signedness are assumptions (see adapters/agopengps_pgn.py).
No packet here was captured from a real AgOpenGPS or AgIO. Regenerate with:

    python tests/fixtures/make_agopengps_samples.py
"""
from __future__ import annotations

import json
import struct
from pathlib import Path


def frame(src: int, pgn: int, data: bytes) -> bytes:
    body = bytes([src, pgn, len(data)]) + data
    return b"\x80\x81" + body + bytes([sum(body) & 0xFF])


def gps(lon, lat, hdual, htrue, spd, roll, alt, sats, fixq, hdop_x100, age_x100,
        ih=0, ir=0, ip=0, iy=0) -> bytes:
    return frame(0x7C, 214, struct.pack("<ddfffffHBHHHhhh", lon, lat, hdual, htrue, spd, roll,
                                        alt, sats, fixq, hdop_x100, age_x100, ih, ir, ip, iy))


def steer_data(speed, status, angle, xte, sc1, sc2) -> bytes:
    return frame(0x7F, 254, struct.pack("<HBhBBB", speed, status, angle, xte, sc1, sc2))


def from_autosteer(angle_x100, ih, ir, sw, pwm) -> bytes:
    return frame(0x7E, 253, struct.pack("<hHhBB", angle_x100, ih, ir, sw, pwm))


def from_imu(h, r, g) -> bytes:
    return frame(0x79, 211, struct.pack("<HhhBB", h, r, g, 0, 0))


def machine(ut, spd10, hyd, tram, geo, sc1, sc2) -> bytes:
    return frame(0x7F, 239, bytes([ut, spd10, hyd, tram, geo, 0, sc1, sc2]))


SAMPLES = {
    "gps_rtk_fix": gps(-97.1384, 49.8951, 90.0, 91.5, 5.25, 1.5, 238.4, 18, 4, 85, 120),
    "gps_no_fix": gps(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 9999, 9999),
    "steer_data": steer_data(75, 1, -1234, 130, 0b00000101, 0b00000010),
    "from_autosteer": from_autosteer(-1234, 900, -50, 1, 77),
    "from_imu": from_imu(1800, -25, 7),
    "machine": machine(0, 52, 1, 0, 0, 0xFF, 0x00),
    "hello_unmodelled": frame(0x7F, 200, bytes([126, 0, 0])),
}

if __name__ == "__main__":
    out = {
        "provenance": "SIMULATED: constructed from PGN.md field list; not captured from real AgOpenGPS",
        "source": "https://github.com/AgOpenGPS-Official/Boards/blob/main/PGN.md",
        "packets": {k: v.hex() for k, v in SAMPLES.items()},
    }
    Path(__file__).with_name("agopengps_samples.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("wrote", len(SAMPLES), "packets")
