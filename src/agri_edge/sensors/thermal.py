"""Radiometric thermal helpers for water-stress style scoring.

Hardware-blocked without a radiometric thermal camera. Synthetic arrays are
fine for Demo / unit tests. This module never talks to the flight controller.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import numpy as np

EPS = 1e-6


def canopy_stats(
    temp_c: np.ndarray,
    mask: Optional[np.ndarray] = None,
) -> dict[str, float]:
    """Return mean/std/p5/p95 canopy temperature in °C."""
    arr = np.asarray(temp_c, dtype=np.float64)
    if arr.size == 0:
        raise ValueError("temp_c is empty")
    if mask is not None:
        m = np.asarray(mask, dtype=bool)
        if m.shape != arr.shape:
            raise ValueError("mask shape must match temp_c")
        arr = arr[m]
        if arr.size == 0:
            raise ValueError("mask selected no pixels")
    return {
        "mean_c": float(np.mean(arr)),
        "std_c": float(np.std(arr)),
        "p5_c": float(np.percentile(arr, 5)),
        "p95_c": float(np.percentile(arr, 95)),
        "n": int(arr.size),
    }


def cwsi(canopy_c: float, twet_c: float, tdry_c: float) -> float:
    """Classic CWSI = (Tc - Twet) / (Tdry - Twet), clipped to [0, 1].

    Fails closed (raises) if the wet/dry span is ~0 — an unasked question is
    not a stress score of zero.
    """
    denom = float(tdry_c) - float(twet_c)
    if abs(denom) < EPS:
        raise ValueError("tdry_c - twet_c too small; cannot compute CWSI")
    raw = (float(canopy_c) - float(twet_c)) / denom
    return float(np.clip(raw, 0.0, 1.0))


def thermal_stress_features(
    temp_c: np.ndarray,
    *,
    twet_c: Optional[float] = None,
    tdry_c: Optional[float] = None,
    mask: Optional[np.ndarray] = None,
    frame_id: str = "demo",
    validated_locally: bool = False,
) -> list[dict[str, Any]]:
    """Build GeoJSON-ready property dicts for a thermal frame.

    If twet/tdry are omitted, CWSI is omitted (null) rather than invented.
    """
    stats = canopy_stats(temp_c, mask=mask)
    props: dict[str, Any] = {
        "kind": "thermal_stress",
        "frame_id": frame_id,
        "validated_locally": bool(validated_locally),
        "temp_mean_c": stats["mean_c"],
        "temp_std_c": stats["std_c"],
        "temp_p5_c": stats["p5_c"],
        "temp_p95_c": stats["p95_c"],
        "n_pixels": stats["n"],
        "cwsi": None,
        "source": "radiometric_thermal",
        "hardware": "required_for_field_claims",
    }
    if twet_c is not None and tdry_c is not None:
        props["cwsi"] = cwsi(stats["mean_c"], twet_c, tdry_c)
        props["twet_c"] = float(twet_c)
        props["tdry_c"] = float(tdry_c)
    return [props]


def features_to_geojson(
    features: list[Mapping[str, Any]],
    *,
    lon: float = 0.0,
    lat: float = 0.0,
) -> dict[str, Any]:
    """Wrap thermal feature props as a Point FeatureCollection (centroid placeholder)."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": dict(p),
            }
            for p in features
        ],
    }
