"""Multispectral vegetation indices (NDVI / NDRE / GNDVI / OSAVI).

Expects reflectance-like float bands in [0, 1] or digital numbers on a common
scale. Without a multispectral camera this is Demo/synthetic only. Reuses the
same fail-closed mindset as calibration: missing bands raise, they do not
silently become zero vigour.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np

EPS = 1e-6

IndexName = str


def _as_f32(a: np.ndarray) -> np.ndarray:
    return np.asarray(a, dtype=np.float32)


def _safe_div(num: np.ndarray, den: np.ndarray) -> np.ndarray:
    den = np.where(np.abs(den) < EPS, np.nan, den)
    out = num / den
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    nir, red = _as_f32(nir), _as_f32(red)
    return _safe_div(nir - red, nir + red)


def ndre(nir: np.ndarray, red_edge: np.ndarray) -> np.ndarray:
    nir, re = _as_f32(nir), _as_f32(red_edge)
    return _safe_div(nir - re, nir + re)


def gndvi(nir: np.ndarray, green: np.ndarray) -> np.ndarray:
    nir, green = _as_f32(nir), _as_f32(green)
    return _safe_div(nir - green, nir + green)


def osavi(nir: np.ndarray, red: np.ndarray, soil: float = 0.16) -> np.ndarray:
    """OSAVI = (NIR - R) / (NIR + R + L) with L default 0.16."""
    nir, red = _as_f32(nir), _as_f32(red)
    return _safe_div(nir - red, nir + red + float(soil))


_DISPATCH = {
    "ndvi": lambda b: ndvi(b["nir"], b["red"]),
    "ndre": lambda b: ndre(b["nir"], b["red_edge"]),
    "gndvi": lambda b: gndvi(b["nir"], b["green"]),
    "osavi": lambda b: osavi(b["nir"], b["red"]),
}

_REQUIRED = {
    "ndvi": ("nir", "red"),
    "ndre": ("nir", "red_edge"),
    "gndvi": ("nir", "green"),
    "osavi": ("nir", "red"),
}


def index_map(bands: Mapping[str, np.ndarray], name: IndexName) -> np.ndarray:
    """Compute a named index from a band dict. Raises if bands are missing."""
    key = name.lower().strip()
    if key not in _DISPATCH:
        raise ValueError(f"unknown index {name!r}; expected one of {sorted(_DISPATCH)}")
    need = _REQUIRED[key]
    missing = [k for k in need if k not in bands]
    if missing:
        raise ValueError(f"index {key} missing bands: {missing}")
    return _DISPATCH[key](bands)


def index_summary(index: np.ndarray, mask: np.ndarray | None = None) -> dict[str, float]:
    arr = np.asarray(index, dtype=np.float64)
    if mask is not None:
        arr = arr[np.asarray(mask, dtype=bool)]
    if arr.size == 0:
        raise ValueError("empty index summary")
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "p5": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95)),
    }
