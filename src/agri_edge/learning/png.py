"""Minimal PNG writer (8-bit gray / RGB), standard library + numpy only.

Spool frames are raw arrays; labelling tools want images. Pillow is a training
extra the Pi does not carry, and this is twenty lines.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode(img: np.ndarray, level: int = 6) -> bytes:
    a = np.asarray(img)
    if a.dtype != np.uint8:
        a = np.clip(a, 0, 255).astype(np.uint8)
    if a.ndim == 2:
        color = 0
    elif a.ndim == 3 and a.shape[2] == 3:
        color = 2
    elif a.ndim == 3 and a.shape[2] > 3:
        a, color = np.ascontiguousarray(a[:, :, :3]), 2
    else:
        raise ValueError(f"unsupported image shape {a.shape}")
    h, w = a.shape[:2]
    raw = b"".join(b"\x00" + a[y].tobytes() for y in range(h))   # filter 0 per row
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, level))
            + _chunk(b"IEND", b""))
