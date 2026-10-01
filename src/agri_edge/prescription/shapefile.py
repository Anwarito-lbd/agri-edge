"""ESRI polygon shapefile writer, standard library only.

One polygon per applicable cell, with RATE and UNIT attributes, in WGS84
(EPSG:4326, .prj included). Outer rings are written clockwise, as the
shapefile specification requires (GeoJSON is the opposite).

Spec: ESRI Shapefile Technical Description (1998); dBase III for the .dbf.
"""

from __future__ import annotations

import struct
from datetime import date

WGS84_PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
             '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')
SHAPE_POLYGON = 5


def _signed_area(ring: list[tuple[float, float]]) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1])) / 2


def _clockwise(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    ring = ring[:-1] if ring[0] == ring[-1] else ring
    if _signed_area(ring) > 0:          # counter-clockwise -> reverse
        ring = ring[::-1]
    return ring + [ring[0]]


def _header(file_len_words: int, bbox: tuple[float, float, float, float]) -> bytes:
    return (struct.pack(">i5ii", 9994, 0, 0, 0, 0, 0, file_len_words)
            + struct.pack("<ii4d4d", 1000, SHAPE_POLYGON, *bbox, 0.0, 0.0, 0.0, 0.0))


def write(polygons: list[list[tuple[float, float]]], records: list[dict],
          fields: list[tuple[str, str, int, int]]) -> dict[str, bytes]:
    """polygons: outer rings of (x=lon, y=lat); fields: (name, 'N'|'C', length, decimals).
    Returns {'.shp': ..., '.shx': ..., '.dbf': ..., '.prj': ..., '.cpg': ...}."""
    if len(polygons) != len(records):
        raise ValueError("one record per polygon")
    rings = [_clockwise(list(p)) for p in polygons]
    xs = [x for r in rings for x, _ in r] or [0.0]
    ys = [y for r in rings for _, y in r] or [0.0]
    bbox = (min(xs), min(ys), max(xs), max(ys))

    shp_recs, shx_recs, offset = [], [], 50
    for i, ring in enumerate(rings, start=1):
        rx = [x for x, _ in ring]
        ry = [y for _, y in ring]
        content = struct.pack("<i4dii", SHAPE_POLYGON, min(rx), min(ry), max(rx), max(ry), 1, len(ring))
        content += struct.pack("<i", 0)
        content += b"".join(struct.pack("<2d", x, y) for x, y in ring)
        words = len(content) // 2
        shp_recs.append(struct.pack(">ii", i, words) + content)
        shx_recs.append(struct.pack(">ii", offset, words))
        offset += 4 + words
    shp_body = b"".join(shp_recs)
    shp = _header(50 + len(shp_body) // 2, bbox) + shp_body
    shx = _header(50 + 4 * len(rings), bbox) + b"".join(shx_recs)
    return {".shp": shp, ".shx": shx, ".dbf": _dbf(records, fields),
            ".prj": WGS84_PRJ.encode("ascii"), ".cpg": b"UTF-8"}


def _dbf(records: list[dict], fields: list[tuple[str, str, int, int]]) -> bytes:
    today = date.today()
    rec_size = 1 + sum(f[2] for f in fields)
    header_size = 32 + 32 * len(fields) + 1
    out = struct.pack("<BBBBIHH20x", 0x03, today.year - 1900, today.month, today.day,
                      len(records), header_size, rec_size)
    for name, ftype, length, dec in fields:
        if len(name) > 10:
            raise ValueError(f"dBase field names are at most 10 characters: {name}")
        out += struct.pack("<11sc4xBB14x", name.encode("ascii"), ftype.encode("ascii"), length, dec)
    out += b"\x0d"
    for rec in records:
        row = b" "
        for name, ftype, length, dec in fields:
            v = rec.get(name)
            if ftype == "N":
                s = "" if v is None else f"{float(v):.{dec}f}"
                if len(s) > length:
                    raise ValueError(f"{name}={v} does not fit N({length},{dec})")
                row += s.rjust(length).encode("ascii")
            else:
                row += str(v or "").encode("utf-8")[:length].ljust(length)
        out += row
    return out + b"\x1a"
