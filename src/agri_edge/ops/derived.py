"""Derived agronomic values (§84, §135–137). Always origin=DERIVED + algorithm_version."""
from __future__ import annotations

import math
from typing import Any, Optional

from .types import (
    ALGORITHM_VERSION,
    DataOrigin,
    TempKind,
    TypedTemperature,
    QualityFlag,
)


def dewpoint_c(air_temp_c: float, rh_pct: float) -> TypedTemperature:
    """Magnus approximation."""
    rh = max(0.01, min(100.0, rh_pct))
    a, b = 17.27, 237.7
    alpha = ((a * air_temp_c) / (b + air_temp_c)) + math.log(rh / 100.0)
    td = (b * alpha) / (a - alpha)
    return TypedTemperature(
        value_c=round(td, 3),
        kind=TempKind.DEWPOINT,
        origin=DataOrigin.DERIVED,
        algorithm_version=ALGORITHM_VERSION,
        quality=QualityFlag.GOOD,
    )


def vpd_kpa(air_temp_c: float, rh_pct: float) -> dict[str, Any]:
    """Vapour pressure deficit (kPa)."""
    # Tetens
    es = 0.6108 * math.exp((17.27 * air_temp_c) / (air_temp_c + 237.3))
    ea = es * (max(0.0, min(100.0, rh_pct)) / 100.0)
    vpd = max(0.0, es - ea)
    return {
        "vpd_kpa": round(vpd, 4),
        "origin": DataOrigin.DERIVED.value,
        "algorithm_version": ALGORITHM_VERSION,
    }


def gdd_stub(t_min_c: float, t_max_c: float, base_c: float = 10.0) -> dict[str, Any]:
    """§84 GDD stub — simple average method."""
    t_avg = (t_min_c + t_max_c) / 2.0
    gdd = max(0.0, t_avg - base_c)
    return {
        "gdd": round(gdd, 3),
        "base_c": base_c,
        "origin": DataOrigin.DERIVED.value,
        "algorithm_version": ALGORITHM_VERSION,
        "method": "avg_stub",
    }


def frost_risk(air_temp_c: float, dewpoint_c_val: Optional[float] = None) -> dict[str, Any]:
    """Recommend-only frost flag (§136) — no auto irrigate."""
    level = "none"
    if air_temp_c <= -2:
        level = "hard"
    elif air_temp_c <= 0:
        level = "light"
    elif air_temp_c <= 2:
        level = "watch"
    rec = []
    if level in ("light", "hard", "watch"):
        rec.append("Consider frost protection measures (manual). Do NOT auto-irrigate.")
    return {
        "frost_level": level,
        "air_temp_c": air_temp_c,
        "dewpoint_c": dewpoint_c_val,
        "recommendations": rec,
        "auto_irrigate": False,
        "origin": DataOrigin.DERIVED.value,
        "algorithm_version": ALGORITHM_VERSION,
    }


def heat_stress(air_temp_c: float, rh_pct: Optional[float] = None) -> dict[str, Any]:
    """§137 heat workflow — recommend only."""
    level = "none"
    if air_temp_c >= 38:
        level = "extreme"
    elif air_temp_c >= 32:
        level = "high"
    elif air_temp_c >= 28:
        level = "moderate"
    rec = []
    if level != "none":
        rec.append("Review livestock/crop heat protocols. No automatic irrigation from this rule.")
    return {
        "heat_level": level,
        "air_temp_c": air_temp_c,
        "rh_pct": rh_pct,
        "recommendations": rec,
        "auto_irrigate": False,
        "origin": DataOrigin.DERIVED.value,
        "algorithm_version": ALGORITHM_VERSION,
    }


def derive_from_weather(air_temp_c: float, rh_pct: float) -> dict[str, Any]:
    td = dewpoint_c(air_temp_c, rh_pct)
    return {
        "dewpoint": td.to_dict(),
        "vpd": vpd_kpa(air_temp_c, rh_pct),
        "frost": frost_risk(air_temp_c, td.value_c),
        "heat": heat_stress(air_temp_c, rh_pct),
        "origin": DataOrigin.DERIVED.value,
        "algorithm_version": ALGORITHM_VERSION,
    }
