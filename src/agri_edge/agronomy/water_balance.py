"""Root-zone soil water balance and the irrigation decision (FAO-56 chapter 8).

Replaces the ops station's old rule -- "moisture below 20 %, add 10 mm" --
which knew nothing about the crop, the soil, the weather or the rain coming.

Daily depletion (eq 85):

    Dr[i] = Dr[i-1] - Pe[i] - I[i] + ETc_adj[i]        (clipped to [0, TAW])

    TAW = 1000 (theta_fc - theta_wp) Zr      total available water, mm
    RAW = p * TAW                            readily available water
    Ks  = (TAW - Dr) / (TAW - RAW) when Dr > RAW, else 1     (eq 84)
    ETc_adj = Ks * Kc * ET0

Simplifications, stated so nobody mistakes this for more:
* single crop coefficient, no separate soil evaporation (FAO-56 ch. 6 not 7);
* effective rain: rain below 0.2 ET0 is taken as intercepted and lost, and
  runoff is ignored (flat prairie fields; wrong on slopes);
* no capillary rise.

Soil probes correct the model: a probe reading in the root zone resets the
depletion to what the probe says, so the model only has to carry the days
between readings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .crops import Crop
from .soils import Soil
from .weather import Day


@dataclass
class DayBalance:
    date: str
    gdd: float
    kc: float
    zr_m: float
    et0: float
    etc: float
    rain: float
    rain_eff: float
    irrigation: float
    depletion_mm: float
    taw_mm: float
    raw_mm: float
    ks: float
    source: str
    probe_reset: bool = False

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class IrrigationAdvice:
    action: str                      # irrigate | wait | none | no-data
    amount_mm: float
    depletion_mm: float
    raw_mm: float
    taw_mm: float
    days_until_stress: int | None
    why: list[str] = field(default_factory=list)
    confidence: str = "medium"

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def effective_rain(rain: float, et0: float) -> float:
    return rain if rain >= 0.2 * et0 else 0.0


def run_balance(
    crop: Crop,
    soil: Soil,
    seeded: date,
    days: list[Day],
    *,
    initial_depletion_frac: float = 0.3,
    irrigation: dict[date, float] | None = None,
    probe_vwc: dict[date, float] | None = None,
) -> list[DayBalance]:
    """Walk the season day by day. `probe_vwc` is volumetric water content
    (m3/m3, root-zone average) by date."""
    from .gdd import daily_gdd

    irrigation = irrigation or {}
    probe_vwc = probe_vwc or {}
    out: list[DayBalance] = []
    gdd = 0.0
    dr: float | None = None
    for d in sorted(days, key=lambda x: x.date):
        if d.date < seeded:
            continue
        gdd += daily_gdd(d.t_max, d.t_min, crop.base_c, crop.cap_c)
        zr = crop.root_depth_m(gdd)
        taw = 1000 * soil.available * zr
        raw = crop.p * taw
        if dr is None:
            dr = initial_depletion_frac * taw
        kc = crop.kc(gdd)
        et0 = d.et0_mm or 0.0
        ks = 1.0 if dr <= raw else max(0.0, (taw - dr) / (taw - raw))
        etc = ks * kc * et0
        pe = effective_rain(d.precip_mm, et0)
        irr = irrigation.get(d.date, 0.0)
        dr = min(max(dr - pe - irr + etc, 0.0), taw)
        reset = False
        if d.date in probe_vwc:
            dr = min(max(1000 * (soil.theta_fc - probe_vwc[d.date]) * zr, 0.0), taw)
            reset = True
        out.append(DayBalance(
            date=d.date.isoformat(), gdd=round(gdd, 1), kc=round(kc, 3), zr_m=round(zr, 3),
            et0=round(et0, 2), etc=round(etc, 2), rain=round(d.precip_mm, 1), rain_eff=round(pe, 1),
            irrigation=irr, depletion_mm=round(dr, 1), taw_mm=round(taw, 1), raw_mm=round(raw, 1),
            ks=round(ks, 3), source=d.source, probe_reset=reset,
        ))
    return out


def advise(balance: list[DayBalance], today: date, *, efficiency: float = 0.8,
           rain_wait_frac: float = 0.6) -> IrrigationAdvice:
    """Decide from the balance: today's depletion and the forecast days after.

    * Past RAW today -> the crop is already stressed: irrigate the depletion.
    * Will pass RAW within the forecast -> irrigate before it does, unless the
      forecast rain before then covers most of the deficit.
    * Otherwise -> none, with the day stress is expected if it is in range.
    """
    past = [b for b in balance if date.fromisoformat(b.date) < today]
    ahead = [b for b in balance if date.fromisoformat(b.date) >= today]
    if not past:
        return IrrigationAdvice("no-data", 0.0, 0.0, 0.0, 0.0, None,
                                ["No weather history since seeding, so no water balance yet."],
                                confidence="low")
    now = past[-1]
    why = [
        f"Root zone is {now.zr_m:.2f} m deep; it holds {now.taw_mm:.0f} mm the crop can use, "
        f"of which the first {now.raw_mm:.0f} mm come out without stress (p = "
        f"{now.raw_mm / now.taw_mm:.2f})." if now.taw_mm else "Root zone not established.",
        f"Estimated depletion yesterday: {now.depletion_mm:.0f} mm"
        + (" (reset from a soil probe reading)." if now.probe_reset else
           f" (water balance; ET0 {now.et0:.1f} mm, Kc {now.kc:.2f})."),
    ]
    stressed_on = next((b for b in ahead if b.depletion_mm > b.raw_mm), None)
    rain_ahead = sum(b.rain_eff for b in ahead[:3])
    confidence = "high" if any(b.probe_reset for b in past[-7:]) else "medium"
    if not any(b.source == "station" for b in past[-7:]):
        why.append("Recent days come from the weather model, not a station on this farm.")
    if now.depletion_mm > now.raw_mm:
        gross = now.depletion_mm / efficiency
        why.append(f"Depletion is past the {now.raw_mm:.0f} mm stress threshold: the crop is "
                   f"already water-limited (Ks {now.ks:.2f}).")
        if rain_ahead >= rain_wait_frac * now.depletion_mm:
            why.append(f"But {rain_ahead:.0f} mm of rain is forecast in the next 3 days, enough "
                       "to refill most of it. Wait, and re-check after the rain.")
            return IrrigationAdvice("wait", 0.0, now.depletion_mm, now.raw_mm, now.taw_mm, 0,
                                    why, confidence)
        why.append(f"Apply {now.depletion_mm:.0f} mm net ({gross:.0f} mm gross at "
                   f"{efficiency:.0%} efficiency) to refill to field capacity.")
        return IrrigationAdvice("irrigate", round(gross, 1), now.depletion_mm, now.raw_mm,
                                now.taw_mm, 0, why, confidence)
    if stressed_on is not None:
        n = (date.fromisoformat(stressed_on.date) - today).days
        if rain_ahead >= rain_wait_frac * stressed_on.depletion_mm:
            why.append(f"Stress expected in {n} day(s), but {rain_ahead:.0f} mm of rain is "
                       "forecast before then. Wait.")
            return IrrigationAdvice("wait", 0.0, now.depletion_mm, now.raw_mm, now.taw_mm, n,
                                    why, confidence)
        gross = stressed_on.depletion_mm / efficiency
        why.append(f"At the forecast ET the crop reaches stress in {n} day(s) "
                   f"({stressed_on.date}); irrigate before then.")
        return IrrigationAdvice("irrigate", round(gross, 1), now.depletion_mm, now.raw_mm,
                                now.taw_mm, n, why, confidence)
    why.append("No stress expected within the forecast.")
    return IrrigationAdvice("none", 0.0, now.depletion_mm, now.raw_mm, now.taw_mm, None,
                            why, confidence)
