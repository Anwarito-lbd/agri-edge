"""Bring one field's satellite record up to date, and report change."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable

from . import series, stac
from .field import Boundary, observe
from .series import ChangeReport

log = logging.getLogger(__name__)


def update_field(db: str, field_id: str, boundary_geojson: dict, *,
                 start: str | None = None, end: str | None = None, max_cloud: float = 40.0,
                 search: Callable = stac.search, read: Callable | None = None,
                 cell_m: float = 50.0) -> dict:
    """Search, read new scenes, store their statistics, detect change.

    Scenes already in the series are skipped, so a daily run costs one search
    and whatever is new. A scene that fails to read is reported and skipped;
    the next run retries it.
    """
    if read is None:
        from .reader import read_field

        read = read_field
    boundary = Boundary.from_geojson(boundary_geojson)
    end = end or date.today().isoformat()
    start = start or (date.fromisoformat(end) - timedelta(days=60)).isoformat()
    scenes = search(boundary.bbox, start, end, max_cloud)
    have = series.known_scenes(db, field_id)
    added, failed = [], []
    for sc in scenes:
        if sc.scene_id in have:
            continue
        try:
            bands, lats, lons = read(sc, boundary)
            obs = observe(sc.scene_id, sc.date, bands, lats, lons, boundary, cell_m=cell_m)
        except Exception as exc:  # noqa: BLE001 - one bad scene must not stop the rest
            log.warning("scene %s failed: %s", sc.scene_id, exc)
            failed.append({"scene_id": sc.scene_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        series.save(db, field_id, obs.to_dict())
        added.append({"scene_id": sc.scene_id, "date": sc.date,
                      "valid_fraction": obs.valid_fraction, "usable": obs.usable})
    report: ChangeReport = series.detect_change(field_id, series.load(db, field_id), boundary,
                                                cell_m=cell_m)
    return {"field_id": field_id, "searched": len(scenes), "added": added, "failed": failed,
            "change": report.to_dict(), "geojson": report.geojson()}


def field_summary(db: str, field_id: str, boundary_geojson: dict, cell_m: float = 50.0) -> dict:
    """Stored series + change, no network."""
    obs = series.load(db, field_id)
    rep = series.detect_change(field_id, obs, Boundary.from_geojson(boundary_geojson), cell_m=cell_m)
    return {
        "field_id": field_id,
        "series": [{k: o[k] for k in ("date", "scene_id", "valid_fraction", "usable",
                                      "ndvi_mean", "ndvi_median", "ndvi_p10", "ndvi_p90", "ndre_mean")}
                   for o in obs],
        "change": rep.to_dict(),
        "geojson": rep.geojson(),
    }
