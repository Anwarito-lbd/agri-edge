"""Soil water constants: FAO-56 Table 19 (mid-range values), m3/m3."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Soil:
    key: str
    theta_fc: float     # field capacity
    theta_wp: float     # wilting point

    @property
    def available(self) -> float:
        return self.theta_fc - self.theta_wp


SOILS: dict[str, Soil] = {s.key: s for s in (
    Soil("sand", 0.12, 0.045),
    Soil("loamy_sand", 0.14, 0.06),
    Soil("sandy_loam", 0.23, 0.10),
    Soil("loam", 0.25, 0.12),
    Soil("silt_loam", 0.29, 0.15),
    Soil("silt", 0.32, 0.17),
    Soil("silty_clay_loam", 0.34, 0.21),
    Soil("silty_clay", 0.36, 0.23),
    Soil("clay", 0.36, 0.22),
)}


def get_soil(key: str) -> Soil:
    try:
        return SOILS[key]
    except KeyError:
        raise ValueError(f"unknown soil {key!r}; known: {sorted(SOILS)}") from None
