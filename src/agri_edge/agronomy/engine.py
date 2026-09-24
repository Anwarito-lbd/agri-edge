"""One field, assessed: stage, water, disease, frost -> ranked recommendations.

Every recommendation carries its evidence (`why`), what it could not see
(`missing`), how much to trust it (`confidence`) and where its data came from
(`sources`). Nothing here actuates anything: a recommendation is text for a
person, and an irrigation or spray decision stays theirs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from . import disease, frost
from .crops import get_crop
from .gdd import accumulate
from .soils import get_soil
from .water_balance import advise, run_balance
from .weather import WeatherSeries


@dataclass
class FieldProfile:
    field_id: str
    name: str
    crop: str                     # key in crops.CROPS
    seeded: str                   # ISO date
    soil: str                     # key in soils.SOILS
    lat: float
    lon: float
    elevation_m: float = 500.0
    irrigated: bool = False
    boundary: dict | None = None  # GeoJSON Polygon, optional

    def validate(self) -> "FieldProfile":
        get_crop(self.crop)
        get_soil(self.soil)
        date.fromisoformat(self.seeded)
        if not (-90 <= self.lat <= 90 and -180 <= self.lon <= 180):
            raise ValueError(f"lat/lon out of range: {self.lat}, {self.lon}")
        if not self.field_id or "/" in self.field_id or len(self.field_id) > 64:
            raise ValueError("field_id must be 1-64 characters without '/'")
        return self

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Recommendation:
    field_id: str
    kind: str                     # irrigation | disease | frost | stage | scouting | data
    priority: int                 # 1 act now, 2 this week, 3 for information
    title: str
    action: str
    why: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    confidence: str = "medium"    # low | medium | high
    sources: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


PRIORITY_BY_LEVEL = {"high": 1, "damaging": 1, "moderate": 2, "frost": 2}


def assess_field(profile: FieldProfile, ws: WeatherSeries, today: date,
                 probe_vwc: dict[date, float] | None = None) -> dict:
    crop = get_crop(profile.crop)
    soil = get_soil(profile.soil)
    seeded = date.fromisoformat(profile.seeded)
    past_days = [(d.date, d.t_max, d.t_min) for d in ws.days if d.date < today]
    season = accumulate(crop, seeded, past_days)
    sources = sorted({d.source for d in ws.days if d.date < today}) or ["none"]
    recs: list[Recommendation] = []

    def rec(**kw) -> None:
        recs.append(Recommendation(field_id=profile.field_id, sources=list(sources), **kw))

    missing_since = (today - seeded).days - season.days
    if season.days == 0:
        rec(kind="data", priority=2, title="No weather since seeding",
            action="Connect a weather station or check the forecast service.",
            why=["Growth stage, water use and disease risk all need daily weather."],
            confidence="low")
    elif missing_since > 3:
        rec(kind="data", priority=3, title=f"{missing_since} days of weather missing since seeding",
            action="Thermal time is underestimated; the stage may be later than shown.",
            why=[f"Weather covers {season.days} of {(today - seeded).days} days since seeding."],
            confidence="low")

    rec(kind="stage", priority=3,
        title=f"{crop.name}: BBCH {season.stage_bbch} ({season.stage_name})",
        action=(f"Next: {season.next_stage} in about {season.gdd_to_next:.0f} GDD."
                if season.next_stage else "Season complete."),
        why=[f"{season.gdd:.0f} growing degree days (base {crop.base_c:.0f} C) since seeding "
             f"on {profile.seeded}."],
        missing=["stage thresholds are regional defaults; confirm stage in the field"],
        confidence="medium", data=season.to_dict())

    balance = run_balance(crop, soil, seeded, ws.days, probe_vwc=probe_vwc)
    water = advise(balance, today)
    if profile.irrigated and water.action in ("irrigate", "wait"):
        rec(kind="irrigation", priority=1 if water.days_until_stress in (0, 1) else 2,
            title=(f"Irrigate {water.amount_mm:.0f} mm" if water.action == "irrigate"
                   else "Irrigation due, but rain is forecast"),
            action=water.why[-1], why=water.why[:-1], confidence=water.confidence,
            missing=[] if probe_vwc else ["no soil probe in this field; depletion is modelled"],
            data=water.to_dict())
    elif not profile.irrigated and water.action == "irrigate":
        rec(kind="irrigation", priority=3, title="Dryland crop entering water stress",
            action="No irrigation on this field; expect reduced growth. Consider it in "
                   "yield expectations and input decisions.",
            why=water.why[:-1], confidence=water.confidence, data=water.to_dict())

    for risk in disease.assess(profile.crop, ws, today, season.stage_bbch):
        if risk.in_window and risk.level in ("moderate", "high"):
            rec(kind="disease", priority=PRIORITY_BY_LEVEL[risk.level],
                title=f"{risk.disease.capitalize()} risk {risk.level}",
                action=risk.action, why=risk.why, missing=risk.missing,
                confidence="medium", data=risk.to_dict())

    fr = frost.assess(profile.crop, ws, today, season.stage_bbch)
    if fr.level in ("frost", "damaging"):
        rec(kind="frost", priority=PRIORITY_BY_LEVEL[fr.level],
            title=f"Frost {fr.min_forecast_c:.1f} C forecast on {fr.on}",
            action=fr.action, why=fr.why, confidence="medium", data=fr.to_dict())

    recs.sort(key=lambda r: r.priority)
    return {
        "field": profile.to_dict(),
        "today": today.isoformat(),
        "season": season.to_dict(),
        "water": water.to_dict(),
        "balance_tail": [b.to_dict() for b in balance[-14:]],
        "diseases": [r.to_dict() for r in disease.assess(profile.crop, ws, today, season.stage_bbch)],
        "frost": fr.to_dict(),
        "recommendations": [r.to_dict() for r in recs],
        "weather_sources": sources,
        "calibrated": False,
    }
