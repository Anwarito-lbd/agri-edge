"""Soil/weather quality & bad-data detection (§86, §126)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .types import QualityFlag


IMPOSSIBLE_SOIL_MOISTURE = (-1.0, 100.5)
IMPOSSIBLE_AIR_TEMP_C = (-80.0, 70.0)
STUCK_EPS = 1e-6
JUMP_MOISTURE_PCT = 40.0  # sudden jump threshold
JUMP_TEMP_C = 25.0
LOW_BATTERY_PCT = 15.0
WEAK_SIGNAL_RSSI = -95.0


@dataclass
class QualityResult:
    flag: QualityFlag
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"flag": self.flag.value, "reasons": list(self.reasons)}


def check_impossible_moisture(moisture_pct: Optional[float]) -> Optional[str]:
    if moisture_pct is None:
        return None
    lo, hi = IMPOSSIBLE_SOIL_MOISTURE
    if moisture_pct < lo or moisture_pct > hi:
        return f"impossible_moisture:{moisture_pct}"
    return None


def check_impossible_air_temp(temp_c: Optional[float]) -> Optional[str]:
    if temp_c is None:
        return "missing_air_temp"
    lo, hi = IMPOSSIBLE_AIR_TEMP_C
    if temp_c < lo or temp_c > hi:
        return f"impossible_air_temp:{temp_c}"
    return None


def check_stuck(values: Sequence[float], eps: float = STUCK_EPS) -> Optional[str]:
    if len(values) < 3:
        return None
    if max(values) - min(values) <= eps:
        return "stuck_sensor"
    return None


def check_jump(prev: Optional[float], curr: Optional[float], threshold: float) -> Optional[str]:
    if prev is None or curr is None:
        return None
    if abs(curr - prev) >= threshold:
        return f"jump:{prev}->{curr}"
    return None


def check_battery(battery_pct: Optional[float]) -> Optional[str]:
    if battery_pct is None:
        return None
    if battery_pct < LOW_BATTERY_PCT:
        return f"low_battery:{battery_pct}"
    return None


def check_signal(rssi: Optional[float]) -> Optional[str]:
    if rssi is None:
        return None
    if rssi < WEAK_SIGNAL_RSSI:
        return f"weak_signal:{rssi}"
    return None


def check_cal_overdue(days_since_cal: Optional[float], max_days: float = 365.0) -> Optional[str]:
    if days_since_cal is None:
        return None
    if days_since_cal > max_days:
        return f"cal_overdue:{days_since_cal}d"
    return None


def evaluate_soil_reading(
    moisture_pct: Optional[float],
    *,
    history: Sequence[float] = (),
    prev_moisture: Optional[float] = None,
    battery_pct: Optional[float] = None,
    signal_rssi: Optional[float] = None,
    days_since_cal: Optional[float] = None,
) -> QualityResult:
    reasons: list[str] = []
    for fn, args in (
        (check_impossible_moisture, (moisture_pct,)),
    ):
        r = fn(*args)
        if r:
            reasons.append(r)
    if moisture_pct is None:
        reasons.append("missing")
    r = check_stuck(list(history) + ([moisture_pct] if moisture_pct is not None else []))
    if r:
        reasons.append(r)
    r = check_jump(prev_moisture, moisture_pct, JUMP_MOISTURE_PCT)
    if r:
        reasons.append(r)
    for r in (
        check_battery(battery_pct),
        check_signal(signal_rssi),
        check_cal_overdue(days_since_cal),
    ):
        if r:
            reasons.append(r)

    if not reasons:
        return QualityResult(QualityFlag.GOOD, [])
    bad_keys = ("impossible", "stuck", "jump", "missing")
    if any(any(k in x for k in bad_keys) for x in reasons):
        # stuck/jump -> STUCK/JUMP specific when sole cause
        if any("stuck" in x for x in reasons):
            return QualityResult(QualityFlag.STUCK, reasons)
        if any("jump" in x for x in reasons) and not any("impossible" in x for x in reasons):
            return QualityResult(QualityFlag.JUMP, reasons)
        if any(x == "missing" or x.startswith("missing") for x in reasons) and len(reasons) == 1:
            return QualityResult(QualityFlag.MISSING, reasons)
        return QualityResult(QualityFlag.BAD, reasons)
    if any("cal_overdue" in x for x in reasons):
        return QualityResult(QualityFlag.CAL_OVERDUE, reasons)
    if any("low_battery" in x for x in reasons):
        return QualityResult(QualityFlag.LOW_BATTERY, reasons)
    if any("weak_signal" in x for x in reasons):
        return QualityResult(QualityFlag.WEAK_SIGNAL, reasons)
    return QualityResult(QualityFlag.QUESTIONABLE, reasons)


def evaluate_weather_reading(
    air_temp_c: Optional[float],
    rh_pct: Optional[float] = None,
    *,
    history_temps: Sequence[float] = (),
    prev_temp: Optional[float] = None,
) -> QualityResult:
    reasons: list[str] = []
    r = check_impossible_air_temp(air_temp_c)
    if r:
        reasons.append(r)
    if rh_pct is not None and (rh_pct < 0 or rh_pct > 100.5):
        reasons.append(f"impossible_rh:{rh_pct}")
    if air_temp_c is not None:
        r = check_stuck(list(history_temps) + [air_temp_c])
        if r:
            reasons.append(r)
        r = check_jump(prev_temp, air_temp_c, JUMP_TEMP_C)
        if r:
            reasons.append(r)
    if not reasons:
        return QualityResult(QualityFlag.GOOD, [])
    if any("impossible" in x or "stuck" in x or "jump" in x for x in reasons):
        return QualityResult(QualityFlag.BAD, reasons)
    return QualityResult(QualityFlag.QUESTIONABLE, reasons)
