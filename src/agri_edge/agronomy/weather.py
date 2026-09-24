"""Weather for agronomy: forecast + recent past, and the farm's own station.

Sources, in order of trust for any past day:
  1. the farm's weather station (ops store observations), when it has a full day;
  2. Open-Meteo (https://open-meteo.com), which serves Environment and Climate
     Change Canada's GEM model via `models=gem_seamless`. Free, no key, and the
     only network call here. Past days come from the same API (`past_days`).

Future days are always the forecast. Each day records its source, so every
recommendation built on it can say what it rests on.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable

from .et0 import DayInputs, et0_penman_monteith, wind_at_2m

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = ("temperature_2m", "relative_humidity_2m", "precipitation",
               "wind_speed_10m", "shortwave_radiation")
DAILY_VARS = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum",
              "relative_humidity_2m_max", "relative_humidity_2m_min",
              "shortwave_radiation_sum", "wind_speed_10m_mean")


@dataclass
class Hour:
    time: datetime
    temp_c: float | None
    rh_pct: float | None
    precip_mm: float | None
    wind10_ms: float | None = None


@dataclass
class Day:
    date: date
    t_max: float
    t_min: float
    precip_mm: float = 0.0
    rh_max: float | None = None
    rh_min: float | None = None
    u2: float | None = None
    rs_mj: float | None = None
    source: str = "forecast"          # station | model | forecast
    et0_mm: float | None = None

    def with_et0(self, lat: float, elevation_m: float) -> "Day":
        self.et0_mm = round(et0_penman_monteith(DayInputs(
            doy=self.date.timetuple().tm_yday, lat_deg=lat, elevation_m=elevation_m,
            t_max=self.t_max, t_min=self.t_min, rh_max=self.rh_max, rh_min=self.rh_min,
            u2=self.u2 if self.u2 is not None else 2.0, rs_mj=self.rs_mj,
        )), 2)
        return self


@dataclass
class WeatherSeries:
    lat: float
    lon: float
    elevation_m: float
    days: list[Day] = field(default_factory=list)
    hours: list[Hour] = field(default_factory=list)
    fetched_at: float = 0.0
    provider: str = ""

    def past(self, today: date) -> list[Day]:
        return [d for d in self.days if d.date < today]

    def ahead(self, today: date, n: int = 7) -> list[Day]:
        return [d for d in self.days if today <= d.date][:n]

    def hours_between(self, start: datetime, end: datetime) -> list[Hour]:
        return [h for h in self.hours if start <= h.time < end]


def parse_open_meteo(payload: dict, today: date | None = None) -> WeatherSeries:
    """Open-Meteo JSON -> WeatherSeries. Days before `today` are 'model' (the
    model's own recent past), today onwards 'forecast'."""
    today = today or datetime.now(timezone.utc).date()
    ws = WeatherSeries(lat=float(payload["latitude"]), lon=float(payload["longitude"]),
                       elevation_m=float(payload.get("elevation") or 0.0),
                       fetched_at=time.time(), provider="open-meteo")
    h = payload.get("hourly") or {}
    for i, t in enumerate(h.get("time") or []):
        ws.hours.append(Hour(
            time=datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
            if "+" not in t else datetime.fromisoformat(t),
            temp_c=_at(h, "temperature_2m", i), rh_pct=_at(h, "relative_humidity_2m", i),
            precip_mm=_at(h, "precipitation", i), wind10_ms=_at(h, "wind_speed_10m", i),
        ))
    d = payload.get("daily") or {}
    for i, t in enumerate(d.get("time") or []):
        tmax, tmin = _at(d, "temperature_2m_max", i), _at(d, "temperature_2m_min", i)
        if tmax is None or tmin is None:
            continue
        day = date.fromisoformat(t)
        w10 = _at(d, "wind_speed_10m_mean", i)
        ws.days.append(Day(
            date=day, t_max=tmax, t_min=tmin, precip_mm=_at(d, "precipitation_sum", i) or 0.0,
            rh_max=_at(d, "relative_humidity_2m_max", i), rh_min=_at(d, "relative_humidity_2m_min", i),
            u2=wind_at_2m(w10) if w10 is not None else None,
            rs_mj=_at(d, "shortwave_radiation_sum", i),
            source="model" if day < today else "forecast",
        ).with_et0(ws.lat, ws.elevation_m))
    return ws


def _at(block: dict, key: str, i: int) -> float | None:
    vals = block.get(key)
    if not vals or i >= len(vals) or vals[i] is None:
        return None
    return float(vals[i])


def open_meteo_url(lat: float, lon: float, past_days: int = 30, forecast_days: int = 7,
                   model: str = "gem_seamless") -> str:
    q = {
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "hourly": ",".join(HOURLY_VARS), "daily": ",".join(DAILY_VARS),
        "past_days": str(past_days), "forecast_days": str(forecast_days),
        "wind_speed_unit": "ms", "timezone": "UTC", "models": model,
    }
    return OPEN_METEO_URL + "?" + urllib.parse.urlencode(q)


def fetch_open_meteo(lat: float, lon: float, *, past_days: int = 30, forecast_days: int = 7,
                     timeout_s: float = 10.0) -> WeatherSeries:  # pragma: no cover - network
    req = urllib.request.Request(open_meteo_url(lat, lon, past_days, forecast_days),
                                 headers={"User-Agent": "agri-edge/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return parse_open_meteo(json.loads(resp.read().decode("utf-8")))


def station_days(observations: Iterable, lat: float, elevation_m: float,
                 min_samples: int = 12) -> dict[date, Day]:
    """Daily summaries from the farm's own station (ops WeatherObservation).

    A day needs `min_samples` temperature readings to count: a station that
    reported twice cannot be said to know that day's maximum. Bad-quality
    readings are left out."""
    by_day: dict[date, list] = {}
    for o in observations:
        if getattr(o, "air_temp", None) is None or getattr(o, "quality", None) is None:
            continue
        if o.quality.value not in ("GOOD", "QUESTIONABLE", "LOW_BATTERY", "WEAK_SIGNAL"):
            continue
        try:
            d = datetime.fromisoformat(o.ts).date()
        except ValueError:
            continue
        by_day.setdefault(d, []).append(o)
    out: dict[date, Day] = {}
    for d, obs in by_day.items():
        if len(obs) < min_samples:
            continue
        temps = [o.air_temp.value_c for o in obs]
        rhs = [o.rh_pct for o in obs if o.rh_pct is not None]
        winds = [o.wind_ms for o in obs if o.wind_ms is not None]
        solar = [o.solar_wm2 for o in obs if o.solar_wm2 is not None]
        out[d] = Day(
            date=d, t_max=max(temps), t_min=min(temps),
            precip_mm=sum(o.precip_mm or 0.0 for o in obs),
            rh_max=max(rhs) if rhs else None, rh_min=min(rhs) if rhs else None,
            # Station anemometers sit near 2 m; FAO-56 wants 2 m.
            u2=sum(winds) / len(winds) if winds else None,
            # Mean W/m2 over the samples x 86400 s -> MJ/m2, only with good coverage.
            rs_mj=(sum(solar) / len(solar)) * 0.0864 if len(solar) >= min_samples else None,
            source="station",
        ).with_et0(lat, elevation_m)
    return out


def merge_station(series: WeatherSeries, station: dict[date, Day]) -> WeatherSeries:
    """Replace model days with the farm's own measured days where they exist."""
    series.days = [station.get(d.date, d) if d.source != "forecast" else d for d in series.days]
    known = {d.date for d in series.days}
    series.days += [d for k, d in station.items() if k not in known]
    series.days.sort(key=lambda d: d.date)
    return series
