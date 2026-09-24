"""Satellite baseline inside the ops station.

Observations live in the station's SQLite file (or AGRIEDGE_SAT_DB). A refresh
does network I/O and needs rasterio, so it runs in a background thread and the
API answers 202; reading the stored series and change report never touches the
network.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from ..satellite import ATTRIBUTION
from ..satellite.service import field_summary, update_field
from . import agronomy_service
from .store import OpsStore

log = logging.getLogger(__name__)
_running: dict[str, threading.Thread] = {}
_last: dict[str, dict] = {}
_lock = threading.Lock()


def db_path(store: OpsStore) -> str:
    return os.environ.get("AGRIEDGE_SAT_DB") or store.sqlite_path or "data/satellite.sqlite"


def _boundary(store: OpsStore, field_id: str) -> dict:
    prof = next((f for f in agronomy_service.list_fields(store) if f.field_id == field_id), None)
    if prof is None:
        raise KeyError(f"unknown field {field_id}")
    if not prof.boundary:
        raise ValueError(f"field {field_id} has no boundary; add a GeoJSON Polygon to it")
    return prof.boundary


def summary(store: OpsStore, field_id: str) -> dict:
    out = field_summary(db_path(store), field_id, _boundary(store, field_id))
    out["attribution"] = ATTRIBUTION
    out["refresh"] = status(field_id)
    return out


def status(field_id: str) -> dict[str, Any]:
    with _lock:
        t = _running.get(field_id)
        last = _last.get(field_id)
    return {"running": bool(t and t.is_alive()), "last": last}


def refresh(store: OpsStore, field_id: str, **kw) -> bool:
    """Start a background update. False if one is already running."""
    boundary = _boundary(store, field_id)
    db = db_path(store)
    with _lock:
        t = _running.get(field_id)
        if t and t.is_alive():
            return False

        def run() -> None:
            try:
                res = update_field(db, field_id, boundary, **kw)
                result = {k: res[k] for k in ("searched", "added", "failed")}
                result["status"] = res["change"]["status"]
            except Exception as exc:  # noqa: BLE001
                log.exception("satellite refresh failed for %s", field_id)
                result = {"error": f"{type(exc).__name__}: {exc}"}
            with _lock:
                _last[field_id] = result

        t = threading.Thread(target=run, name=f"sat-{field_id}", daemon=True)
        _running[field_id] = t
        t.start()
    return True


def scouting_recommendations(store: OpsStore) -> list[dict]:
    """A recommendation per flagged patch: this is how the satellite sends the drone."""
    recs = []
    for prof in agronomy_service.list_fields(store):
        if not prof.boundary:
            continue
        try:
            ch = field_summary(db_path(store), prof.field_id, prof.boundary)["change"]
        except Exception:  # noqa: BLE001
            continue
        if ch["status"] != "flagged":
            continue
        for p in ch["patches"]:
            m = p["mission"]
            recs.append({
                "field_id": prof.field_id, "kind": "scouting", "priority": 2,
                "title": f"Scout a {p['area_ha']:.1f} ha patch the satellite flagged",
                "action": f"Fly the patch: {m['lines']} lines, about {m['total_distance_m']} m "
                          f"and {m['est_duration_s'] // 60 + 1} min at 8 m/s.",
                "why": ch["why"] + [f"Worst cell fell {abs(p['worst_residual']):.2f} NDVI more "
                                    "than the rest of the field."],
                "missing": ["cause unknown until someone looks: water, disease, pest, "
                            "herbicide injury or a sensor artefact"],
                "confidence": "medium", "sources": ["sentinel-2"], "data": p,
            })
    return recs
