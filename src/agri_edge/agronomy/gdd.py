"""Growing degree days over a season, and the growth stage they imply."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .crops import Crop


def daily_gdd(t_max: float, t_min: float, base_c: float, cap_c: float) -> float:
    """Modified average method: temperatures are clipped to [base, cap] before
    averaging, so a hot day does not count past the point development stops and
    a cold night does not subtract."""
    hi = min(max(t_max, base_c), cap_c)
    lo = min(max(t_min, base_c), cap_c)
    return max((hi + lo) / 2 - base_c, 0.0)


@dataclass
class SeasonGDD:
    crop: str
    seeded: str
    through: str | None
    gdd: float
    days: int
    stage_bbch: int
    stage_name: str
    next_stage: str | None
    gdd_to_next: float | None
    estimated: bool = True        # thresholds are regional defaults, not calibrated

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def accumulate(crop: Crop, seeded: date, days: list[tuple[date, float, float]]) -> SeasonGDD:
    """Sum daily GDD from the seeding date. `days` = (date, t_max, t_min), any order."""
    total, n, last = 0.0, 0, None
    for d, tmax, tmin in sorted(days):
        if d < seeded:
            continue
        total += daily_gdd(tmax, tmin, crop.base_c, crop.cap_c)
        n += 1
        last = d
    current, nxt = crop.stage(total)
    return SeasonGDD(
        crop=crop.key, seeded=seeded.isoformat(), through=last.isoformat() if last else None,
        gdd=round(total, 1), days=n, stage_bbch=current.bbch, stage_name=current.name,
        next_stage=nxt.name if nxt else None,
        gdd_to_next=round(nxt.gdd - total, 1) if nxt else None,
    )
