"""Disease-risk windows for three prairie / Canadian crops.

These are **decision-support indices built from published weather criteria**,
simplified, and not calibrated on this farm. Each result lists the evidence
it used, so an agronomist can see why it says what it says and overrule it.

* Sclerotinia stem rot, canola -- risk exists only during flowering (petals
  carry the infection); driven by moisture over the preceding two weeks and
  humid, mild conditions. After the Canola Council of Canada / provincial
  sclerotinia risk checklists (weather portion only; field history and
  crop density are not known to this system and are named as missing).
* Fusarium head blight, wheat -- infection window from heading through
  flowering; driven by hours of high humidity at 15-30 C in the preceding
  week (the variable the Manitoba/Saskatchewan FHB risk maps are built on).
* Late blight, potato -- Hutton criteria (UK AHDB, 2017): two consecutive days
  each with minimum temperature >= 10 C and at least 6 hours with RH >= 90 %.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from .weather import Hour, WeatherSeries

LEVELS = ("none", "low", "moderate", "high")


@dataclass
class DiseaseRisk:
    disease: str
    crop: str
    level: str                      # none | low | moderate | high
    in_window: bool
    why: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    action: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time(0), tzinfo=timezone.utc)


def _humid_hours(hours: list[Hour], rh: float = 90.0, t_lo: float | None = None,
                 t_hi: float | None = None) -> int:
    n = 0
    for h in hours:
        if h.rh_pct is None or h.rh_pct < rh:
            continue
        if t_lo is not None and (h.temp_c is None or h.temp_c < t_lo):
            continue
        if t_hi is not None and (h.temp_c is None or h.temp_c > t_hi):
            continue
        n += 1
    return n


def sclerotinia_canola(ws: WeatherSeries, today: date, bbch: int) -> DiseaseRisk:
    r = DiseaseRisk("sclerotinia stem rot", "canola", "none", in_window=60 <= bbch <= 69,
                    missing=["field history of sclerotinia", "crop density / canopy closure"])
    if not r.in_window:
        r.why.append(f"Crop at BBCH {bbch}: infection needs petals, so risk applies only "
                     "during flowering (BBCH 60-69).")
        return r
    rain14 = sum(d.precip_mm for d in ws.days if today - timedelta(days=14) <= d.date < today)
    humid7 = _humid_hours(ws.hours_between(_day_start(today - timedelta(days=7)), _day_start(today)),
                          rh=90.0, t_lo=10.0, t_hi=30.0)
    rain_ahead = sum(d.precip_mm for d in ws.ahead(today, 5))
    score = 0
    score += 2 if rain14 > 30 else 1 if rain14 >= 10 else 0
    score += 2 if humid7 > 40 else 1 if humid7 >= 15 else 0
    score += 1 if rain_ahead >= 10 else 0
    r.level = "high" if score >= 4 else "moderate" if score >= 2 else "low"
    r.why += [
        f"Crop is flowering (BBCH {bbch}).",
        f"{rain14:.0f} mm of rain in the last 14 days (under 10 low, over 30 high).",
        f"{humid7} hours with RH >= 90 % at 10-30 C in the last 7 days.",
        f"{rain_ahead:.0f} mm of rain forecast over the next 5 days.",
    ]
    r.action = ({"high": "Fungicide timing decision is due: 20-50 % bloom is the usual window. "
                         "Check the field and the risk checklist today.",
                 "moderate": "Scout the field and complete the full risk checklist before bloom "
                             "passes 50 %.",
                 "low": "Weather does not favour infection now; re-check after rain."}[r.level])
    return r


def fhb_wheat(ws: WeatherSeries, today: date, bbch: int) -> DiseaseRisk:
    r = DiseaseRisk("fusarium head blight", "wheat", "none", in_window=55 <= bbch <= 69,
                    missing=["previous crop / residue", "variety resistance rating"])
    if not r.in_window:
        r.why.append(f"Crop at BBCH {bbch}: the infection window is heading to flowering "
                     "(BBCH 55-69).")
        return r
    hours7 = ws.hours_between(_day_start(today - timedelta(days=7)), _day_start(today))
    humid = _humid_hours(hours7, rh=90.0, t_lo=15.0, t_hi=30.0)
    rain_days = sum(1 for d in ws.days if today - timedelta(days=7) <= d.date < today
                    and d.precip_mm >= 1.0)
    r.level = "high" if humid >= 20 else "moderate" if humid >= 10 else "low"
    if rain_days >= 3 and r.level == "low":
        r.level = "moderate"
    r.why += [
        f"Crop is heading/flowering (BBCH {bbch}).",
        f"{humid} hours with RH >= 90 % at 15-30 C in the last 7 days "
        "(under 10 low, 20 or more high).",
        f"{rain_days} day(s) with rain in the last 7 days.",
    ]
    r.action = ({"high": "Conditions favour infection: a fungicide at early anthesis is the "
                         "usual response. Confirm crop stage in the field.",
                 "moderate": "Watch the forecast; decide at early anthesis.",
                 "low": "Weather does not favour infection now."}[r.level])
    return r


def late_blight_potato(ws: WeatherSeries, today: date, bbch: int) -> DiseaseRisk:
    r = DiseaseRisk("late blight", "potato", "none", in_window=bbch >= 9,
                    missing=["local blight reports", "cull pile / volunteer management"])
    if not r.in_window:
        r.why.append("Before emergence there is no foliage to infect.")
        return r

    def hutton_day(d: date) -> tuple[bool, float | None, int]:
        hrs = ws.hours_between(_day_start(d), _day_start(d + timedelta(days=1)))
        temps = [h.temp_c for h in hrs if h.temp_c is not None]
        if len(temps) < 18:
            return False, None, 0
        tmin = min(temps)
        humid = _humid_hours(hrs, rh=90.0)
        return tmin >= 10.0 and humid >= 6, tmin, humid

    window = [today - timedelta(days=i) for i in range(7, 0, -1)] + \
             [today + timedelta(days=i) for i in range(0, 3)]
    flags = [(d, *hutton_day(d)) for d in window]
    periods = [flags[i][0] for i in range(1, len(flags)) if flags[i][1] and flags[i - 1][1]]
    past = [d for d in periods if d < today]
    future = [d for d in periods if d >= today]
    near = [f[0] for f in flags if f[1] and f[0] < today]
    if past:
        r.level = "high"
        r.why.append(f"Hutton period ended {past[-1]}: two consecutive days with min >= 10 C "
                     "and >= 6 h at RH >= 90 %.")
        r.action = "Protect the crop now if not recently sprayed, and scout for lesions."
    elif future:
        r.level = "moderate"
        r.why.append(f"The forecast meets the Hutton criteria around {future[0]}.")
        r.action = "Plan protection ahead of the forecast humid spell."
    elif near:
        r.level = "low"
        r.why.append(f"{len(near)} single qualifying day(s) in the last week, but no two in a row.")
        r.action = "No Hutton period yet; keep watching."
    else:
        r.level = "low"
        r.why.append("No day in the last week met the Hutton temperature and humidity criteria.")
        r.action = "No action from weather alone."
    return r


def assess(crop_key: str, ws: WeatherSeries, today: date, bbch: int) -> list[DiseaseRisk]:
    if crop_key == "canola":
        return [sclerotinia_canola(ws, today, bbch)]
    if crop_key == "spring_wheat":
        return [fhb_wheat(ws, today, bbch)]
    if crop_key == "potato":
        return [late_blight_potato(ws, today, bbch)]
    return []
