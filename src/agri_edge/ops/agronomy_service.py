"""The ops station's view of agronomy: fields, weather, and recommendations.

Glue between the store (fields, station weather, soil probes) and the pure
models in `agri_edge.agronomy`. Weather comes from Open-Meteo (cached an hour;
a stale cache beats nothing when the farm's link drops) merged with the farm's
own station days, which win wherever they are complete.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import date, datetime, timezone
from typing import Callable, Optional

from ..agronomy.crops import get_crop
from ..agronomy.engine import FieldProfile, assess_field
from ..agronomy.gdd import accumulate
from ..agronomy.weather import WeatherSeries, fetch_open_meteo, merge_station, station_days
from .store import OpsStore

log = logging.getLogger(__name__)

WEATHER_TTL_S = 3600.0
_cache: dict[tuple[float, float], WeatherSeries] = {}
_cache_lock = threading.Lock()
# Replaceable for tests and for an offline station: (lat, lon) -> WeatherSeries.
weather_provider: Callable[[float, float], WeatherSeries] = fetch_open_meteo


# -- fields ------------------------------------------------------------------------


def _init(store: OpsStore) -> None:
    if not hasattr(store, "fields"):
        store.fields = {}  # type: ignore[attr-defined]
        if store.sqlite_path:
            con = sqlite3.connect(store.sqlite_path)
            try:
                con.execute("CREATE TABLE IF NOT EXISTS fields (field_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
                for (payload,) in con.execute("SELECT payload FROM fields"):
                    try:
                        prof = FieldProfile(**json.loads(payload)).validate()
                        store.fields[prof.field_id] = prof  # type: ignore[attr-defined]
                    except (TypeError, ValueError):
                        log.warning("skipping invalid stored field: %s", payload[:120])
                con.commit()
            finally:
                con.close()


def list_fields(store: OpsStore) -> list[FieldProfile]:
    _init(store)
    return list(store.fields.values())  # type: ignore[attr-defined]


def upsert_field(store: OpsStore, data: dict) -> FieldProfile:
    _init(store)
    allowed = set(FieldProfile.__dataclass_fields__)
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown field attribute(s): {', '.join(sorted(unknown))}")
    try:
        prof = FieldProfile(**data).validate()
    except TypeError as exc:
        raise ValueError(f"field profile incomplete: {exc}") from None
    store.fields[prof.field_id] = prof  # type: ignore[attr-defined]
    if store.sqlite_path:
        con = sqlite3.connect(store.sqlite_path)
        try:
            con.execute("CREATE TABLE IF NOT EXISTS fields (field_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            con.execute("INSERT OR REPLACE INTO fields(field_id, payload) VALUES (?, ?)",
                        (prof.field_id, json.dumps(prof.to_dict())))
            con.commit()
        finally:
            con.close()
    return prof


# -- weather -----------------------------------------------------------------------


def weather_for(store: OpsStore, lat: float, lon: float, elevation_m: float) -> WeatherSeries:
    key = (round(lat, 2), round(lon, 2))
    with _cache_lock:
        cached = _cache.get(key)
    if cached is None or time.time() - cached.fetched_at > WEATHER_TTL_S:
        try:
            fresh = weather_provider(lat, lon)
            with _cache_lock:
                _cache[key] = fresh
            cached = fresh
        except Exception as exc:  # noqa: BLE001 - offline is normal on a farm
            log.warning("weather fetch failed (%s); using %s", exc,
                        "stale cache" if cached else "station data only")
    series = cached or WeatherSeries(lat, lon, elevation_m, provider="station-only")
    measured = [o for o in store.weather if not o.synthetic]
    if measured:
        series = merge_station(_copy(series), station_days(measured, lat, elevation_m))
    return series


def _copy(ws: WeatherSeries) -> WeatherSeries:
    return WeatherSeries(ws.lat, ws.lon, ws.elevation_m, list(ws.days), list(ws.hours),
                         ws.fetched_at, ws.provider)


def clear_weather_cache() -> None:
    with _cache_lock:
        _cache.clear()


# -- soil probes -----------------------------------------------------------------


def probe_vwc(store: OpsStore, zone_ids: Optional[list[str]] = None) -> dict[date, float]:
    """Daily root-zone volumetric water content (m3/m3) from the store's probes.

    The last reading of each day at each depth, averaged across depths. Only
    real readings of usable quality count; a BAD or STUCK probe must not reset
    the water balance.
    """
    latest: dict[tuple[date, str, float], tuple[str, float]] = {}
    for o in store.soil:
        if o.synthetic or o.moisture_pct is None:
            continue
        if o.quality.value not in ("GOOD", "QUESTIONABLE", "LOW_BATTERY", "WEAK_SIGNAL"):
            continue
        if zone_ids and o.zone_id not in zone_ids:
            continue
        try:
            d = datetime.fromisoformat(o.ts).date()
        except ValueError:
            continue
        k = (d, o.probe_id, o.depth_cm)
        if k not in latest or o.ts > latest[k][0]:
            latest[k] = (o.ts, o.moisture_pct / 100.0)
    by_day: dict[date, list[float]] = {}
    for (d, _, _), (_, v) in latest.items():
        by_day.setdefault(d, []).append(v)
    return {d: sum(v) / len(v) for d, v in by_day.items()}


# -- assessment ------------------------------------------------------------------


def assess(store: OpsStore, field_id: str, today: Optional[date] = None,
           zone_ids: Optional[list[str]] = None) -> dict:
    _init(store)
    prof = store.fields.get(field_id)  # type: ignore[attr-defined]
    if prof is None:
        raise KeyError(f"unknown field {field_id}")
    today = today or datetime.now(timezone.utc).date()
    ws = weather_for(store, prof.lat, prof.lon, prof.elevation_m)
    return assess_field(prof, ws, today, probe_vwc=probe_vwc(store, zone_ids) or None)


def all_recommendations(store: OpsStore, today: Optional[date] = None) -> list[dict]:
    recs: list[dict] = []
    for prof in list_fields(store):
        try:
            recs += assess(store, prof.field_id, today)["recommendations"]
        except Exception as exc:  # noqa: BLE001 - one field's failure must not hide the rest
            recs.append({"field_id": prof.field_id, "kind": "data", "priority": 2,
                         "title": "Assessment failed", "action": "Check the field profile.",
                         "why": [f"{type(exc).__name__}: {exc}"], "missing": [],
                         "confidence": "low", "sources": [], "data": {}})
    return sorted(recs, key=lambda r: r["priority"])


def season_summary(store: OpsStore, field_id: str, today: Optional[date] = None) -> dict:
    _init(store)
    prof = store.fields[field_id]  # type: ignore[attr-defined]
    today = today or datetime.now(timezone.utc).date()
    ws = weather_for(store, prof.lat, prof.lon, prof.elevation_m)
    s = accumulate(get_crop(prof.crop), date.fromisoformat(prof.seeded),
                   [(d.date, d.t_max, d.t_min) for d in ws.days if d.date < today])
    return s.to_dict()
