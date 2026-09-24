"""Frost risk from the forecast, weighed against how exposed the crop is now.

Damage thresholds are approximate air temperatures (screen height, ~1.5 m)
from prairie extension guidance; the crop canopy on a clear, calm night can be
2-3 C colder than the screen, which is why the watch level starts above zero.

There is no frost-protection *action* the system can take for field crops.
The old ops rule blocked irrigation on a frost watch; that was neither a
protection nor a decision anyone asked for. This module warns, explains and
suggests checks -- nothing is actuated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .weather import WeatherSeries

# (crop, BBCH range) -> air temperature at which damage becomes likely, C.
SENSITIVITY: dict[str, list[tuple[int, int, float, str]]] = {
    "canola": [(0, 13, -3.0, "cotyledon to 3-leaf seedlings"),
               (14, 59, -4.0, "rosette / bolting"),
               (60, 79, -2.0, "flowering and early pods"),
               (80, 99, -3.0, "ripening seed")],
    "spring_wheat": [(0, 29, -5.0, "seedling / tillering (growing point below ground)"),
                     (30, 54, -3.0, "stem elongation"),
                     (55, 69, -1.5, "heading and flowering"),
                     (70, 99, -2.5, "grain fill")],
    "potato": [(0, 8, -2.0, "sprouts below ground"),
               (9, 99, -1.0, "foliage")],
}


@dataclass
class FrostRisk:
    level: str                  # none | watch | frost | damaging
    min_forecast_c: float | None
    on: str | None
    damage_threshold_c: float | None
    stage_note: str
    why: list[str] = field(default_factory=list)
    action: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def threshold(crop_key: str, bbch: int) -> tuple[float | None, str]:
    for lo, hi, t, note in SENSITIVITY.get(crop_key, []):
        if lo <= bbch <= hi:
            return t, note
    return None, "no sensitivity data for this crop/stage"


def assess(crop_key: str, ws: WeatherSeries, today: date, bbch: int, horizon_days: int = 3) -> FrostRisk:
    ahead = ws.ahead(today, horizon_days)
    t_dmg, note = threshold(crop_key, bbch)
    if not ahead:
        return FrostRisk("none", None, None, t_dmg, note, ["No forecast available."], "")
    coldest = min(ahead, key=lambda d: d.t_min)
    tmin = coldest.t_min
    if t_dmg is not None and tmin <= t_dmg:
        level = "damaging"
    elif tmin <= 0.0:
        level = "frost"
    elif tmin <= 2.0:
        level = "watch"
    else:
        level = "none"
    why = [f"Forecast minimum {tmin:.1f} C on {coldest.date} (next {horizon_days} days)."]
    if t_dmg is not None:
        why.append(f"At this stage ({note}) damage is likely at about {t_dmg:.1f} C.")
    if level in ("watch", "frost"):
        why.append("Canopy can run 2-3 C colder than the forecast on a clear, calm night.")
    action = {
        "damaging": "Expect frost damage. Check the field 3-5 days after the event before "
                    "any reseeding or insurance decision; damage is not visible at once.",
        "frost": "Frost is likely but below the damage level for this stage. Check the "
                 "low spots of the field afterwards.",
        "watch": "Near-freezing night forecast. No action; watch the updated forecast.",
        "none": "",
    }[level]
    return FrostRisk(level, round(tmin, 1), coldest.date.isoformat(), t_dmg, note, why, action)
