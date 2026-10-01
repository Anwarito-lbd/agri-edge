"""FAO-56 Penman-Monteith reference evapotranspiration, daily step.

Allen, Pereira, Raes & Smith (1998), *Crop evapotranspiration*, FAO Irrigation
and Drainage Paper 56, chapter 3 (equations cited as "eq N" below).
Verified against the paper's Example 18 (Brussels, 6 July: 3.9 mm/day) in
tests/test_agronomy.py.

Daily step, so soil heat flux G = 0 (eq 42).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

GSC = 0.0820          # solar constant, MJ m-2 min-1
SIGMA = 4.903e-9      # Stefan-Boltzmann, MJ K-4 m-2 day-1


def sat_vapour_pressure(t_c: float) -> float:
    """e°(T), kPa (eq 11)."""
    return 0.6108 * math.exp(17.27 * t_c / (t_c + 237.3))


def atmospheric_pressure(elevation_m: float) -> float:
    """kPa (eq 7)."""
    return 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26


def wind_at_2m(u_z: float, z_m: float = 10.0) -> float:
    """Log-profile conversion to 2 m (eq 47). Weather models report 10 m."""
    return u_z * 4.87 / math.log(67.8 * z_m - 5.42)


def extraterrestrial_radiation(lat_deg: float, doy: int) -> tuple[float, float]:
    """(Ra MJ m-2 day-1, daylight hours N) (eqs 21-25, 34)."""
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    delta = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    x = -math.tan(phi) * math.tan(delta)
    ws = math.acos(max(-1.0, min(1.0, x)))   # clipped: polar day / night
    ra = (24 * 60 / math.pi) * GSC * dr * (
        ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws)
    )
    return max(ra, 0.0), 24 / math.pi * ws


@dataclass
class DayInputs:
    """One day at one place. Give Rs, or sunshine hours, or neither (then the
    Hargreaves radiation estimate is used, eq 50)."""

    doy: int
    lat_deg: float
    elevation_m: float
    t_max: float
    t_min: float
    rh_max: float | None = None
    rh_min: float | None = None
    rh_mean: float | None = None
    t_dew: float | None = None
    u2: float = 2.0                 # FAO-56's default when wind is unknown
    rs_mj: float | None = None      # measured / modelled solar radiation
    sunshine_h: float | None = None
    krs: float = 0.16               # Hargreaves adjustment: 0.16 interior, 0.19 coastal


def actual_vapour_pressure(d: DayInputs) -> float:
    """ea, kPa, from the best humidity data available (eqs 14, 17, 19, 48)."""
    if d.t_dew is not None:
        return sat_vapour_pressure(d.t_dew)
    if d.rh_max is not None and d.rh_min is not None:
        return (sat_vapour_pressure(d.t_min) * d.rh_max / 100
                + sat_vapour_pressure(d.t_max) * d.rh_min / 100) / 2
    if d.rh_mean is not None:
        es = (sat_vapour_pressure(d.t_max) + sat_vapour_pressure(d.t_min)) / 2
        return d.rh_mean / 100 * es
    return sat_vapour_pressure(d.t_min)   # eq 48: Tdew ~ Tmin without humidity data


def et0_penman_monteith(d: DayInputs) -> float:
    """ET0, mm/day (eq 6)."""
    if d.t_max < d.t_min:
        raise ValueError(f"t_max {d.t_max} < t_min {d.t_min}")
    t_mean = (d.t_max + d.t_min) / 2
    gamma = 0.665e-3 * atmospheric_pressure(d.elevation_m)
    es = (sat_vapour_pressure(d.t_max) + sat_vapour_pressure(d.t_min)) / 2
    ea = min(actual_vapour_pressure(d), es)
    delta = 4098 * sat_vapour_pressure(t_mean) / (t_mean + 237.3) ** 2

    ra, n_daylight = extraterrestrial_radiation(d.lat_deg, d.doy)
    if d.rs_mj is not None:
        rs = d.rs_mj
    elif d.sunshine_h is not None:
        rs = (0.25 + 0.50 * min(d.sunshine_h, n_daylight) / n_daylight) * ra if n_daylight else 0.0
    else:
        rs = d.krs * math.sqrt(max(d.t_max - d.t_min, 0.0)) * ra
    rso = (0.75 + 2e-5 * d.elevation_m) * ra
    rns = (1 - 0.23) * rs
    ratio = min(rs / rso, 1.0) if rso > 0 else 0.0
    rnl = SIGMA * ((d.t_max + 273.16) ** 4 + (d.t_min + 273.16) ** 4) / 2 \
        * (0.34 - 0.14 * math.sqrt(ea)) * (1.35 * ratio - 0.35)
    rn = rns - rnl
    num = 0.408 * delta * rn + gamma * 900 / (t_mean + 273) * d.u2 * (es - ea)
    den = delta + gamma * (1 + 0.34 * d.u2)
    return max(num / den, 0.0)


def et0_hargreaves(doy: int, lat_deg: float, t_max: float, t_min: float) -> float:
    """Hargreaves ET0, mm/day (eq 52). Temperature-only fallback."""
    ra, _ = extraterrestrial_radiation(lat_deg, doy)
    t_mean = (t_max + t_min) / 2
    return max(0.0023 * (t_mean + 17.8) * math.sqrt(max(t_max - t_min, 0.0)) * 0.408 * ra, 0.0)
