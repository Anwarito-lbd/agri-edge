"""Prescriptions in the ops station: build, approve, export.

Spot-spray grids come from the station's georeferenced detections inside the
field; variable-rate grids from the field's latest clear satellite scene.
Approval and export go through `prescription.export`, which refuses anything
unvalidated, anything without a calm measured wind, and any export of an
unapproved grid.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from ..ai.validation import validated_models
from ..prescription.export import approve, export_zip
from ..prescription.grid import DetectionPoint, RateGrid, spot_spray, variable_rate
from ..satellite import series as sat_series
from ..satellite.field import Boundary
from . import agronomy_service, satellite_service
from .store import OpsStore

_lock = threading.Lock()


def _registry(store: OpsStore) -> dict[str, dict[str, Any]]:
    if not hasattr(store, "prescriptions"):
        store.prescriptions = {}  # type: ignore[attr-defined]
        if store.sqlite_path:
            con = sqlite3.connect(store.sqlite_path)
            try:
                con.execute("CREATE TABLE IF NOT EXISTS prescriptions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
                for (payload,) in con.execute("SELECT payload FROM prescriptions"):
                    rec = _from_json(json.loads(payload))
                    store.prescriptions[rec["grid"].prescription_id] = rec  # type: ignore[attr-defined]
                con.commit()
            finally:
                con.close()
    return store.prescriptions  # type: ignore[attr-defined]


def _to_json(rec: dict) -> dict:
    g: RateGrid = rec["grid"]
    return {"field_name": rec["field_name"], "boundary": rec["boundary"],
            "grid": {**{k: v for k, v in g.__dict__.items()
                        if k not in ("rates", "applicable", "constraints")},
                     "rates": g.rates.tolist(), "applicable": g.applicable.tolist(),
                     "constraints": g.constraints.to_dict()}}


def _from_json(d: dict) -> dict:
    from ..ops.vra import SafetyConstraints

    gd = dict(d["grid"])
    gd["rates"] = np.array(gd["rates"], dtype=np.float64)
    gd["applicable"] = np.array(gd["applicable"], dtype=bool)
    gd["origin"] = tuple(gd["origin"])
    gd["constraints"] = SafetyConstraints(**gd["constraints"])
    return {"field_name": d["field_name"], "boundary": d["boundary"], "grid": RateGrid(**gd)}


def _persist(store: OpsStore, rec: dict) -> None:
    if not store.sqlite_path:
        return
    con = sqlite3.connect(store.sqlite_path)
    try:
        con.execute("CREATE TABLE IF NOT EXISTS prescriptions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        con.execute("INSERT OR REPLACE INTO prescriptions(id, payload) VALUES (?, ?)",
                    (rec["grid"].prescription_id, json.dumps(_to_json(rec))))
        con.commit()
    finally:
        con.close()


def _field(store: OpsStore, field_id: str):
    prof = next((f for f in agronomy_service.list_fields(store) if f.field_id == field_id), None)
    if prof is None:
        raise KeyError(f"unknown field {field_id}")
    if not prof.boundary:
        raise ValueError(f"field {field_id} has no boundary")
    return prof


def build(store: OpsStore, body: dict) -> dict:
    prof = _field(store, str(body.get("field_id") or ""))
    source = body.get("source")
    if source == "detections":
        days = int(body.get("days", 14))
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        dets = [DetectionPoint(r["lat"], r["lon"], r.get("label", "weed"),
                               float(r.get("confidence") or 0.0),
                               float(r.get("position_error_m") or 0.0),
                               (str(r.get("model_name")), str(r.get("model_version"))))
                for r in store.detections
                if r.get("lat") is not None and not r.get("synthetic") and str(r.get("ts", "")) >= since]
        labels = body.get("labels")
        if labels:
            dets = [d for d in dets if d.label in set(labels)]
        g = spot_spray(prof.field_id, prof.boundary, dets, rate=float(body["rate"]),
                       product=str(body.get("product", "herbicide")), unit=str(body.get("unit", "L/ha")),
                       cell_m=float(body.get("cell_m", 6.0)), buffer_m=float(body.get("buffer_m", 10.0)),
                       min_confidence=float(body.get("min_confidence", 0.3)),
                       validated_models=validated_models())
    elif source == "satellite":
        obs = [o for o in sat_series.load(satellite_service.db_path(store), prof.field_id) if o.get("usable")]
        if not obs:
            raise ValueError("no clear satellite scene for this field yet")
        latest = obs[-1]
        from ..satellite.field import cell_polygon

        b = Boundary.from_geojson(prof.boundary)
        values = {}
        for c in latest["cells"]:
            ring = cell_polygon(b, c["cell"])["coordinates"][0]
            lon = sum(p[0] for p in ring[:4]) / 4
            lat = sum(p[1] for p in ring[:4]) / 4
            values[(lat, lon)] = c["ndvi"]
        g = variable_rate(prof.field_id, prof.boundary, values,
                          [float(r) for r in body["rates_by_zone"]],
                          product=str(body.get("product", "nitrogen")), unit=str(body.get("unit", "kg/ha")),
                          cell_m=float(body.get("cell_m", 20.0)), buffer_m=float(body.get("buffer_m", 5.0)),
                          invert=bool(body.get("invert", True)))
        g.notes.append(f"zones from the Sentinel-2 scene of {latest['date']}")
    else:
        raise ValueError("source must be 'detections' or 'satellite'")
    rec = {"grid": g, "boundary": prof.boundary, "field_name": prof.name}
    with _lock:
        _registry(store)[g.prescription_id] = rec
        _persist(store, rec)
    return g.summary()


def get(store: OpsStore, rx_id: str) -> dict:
    with _lock:
        rec = _registry(store).get(rx_id)
    if rec is None:
        raise KeyError(f"unknown prescription {rx_id}")
    return rec


def listing(store: OpsStore) -> list[dict]:
    with _lock:
        return [r["grid"].summary() for r in _registry(store).values()]


def approve_rx(store: OpsStore, rx_id: str, actor: str, wind_ms: float | None) -> dict:
    rec = get(store, rx_id)
    with _lock:
        out = approve(rec["grid"], actor, wind_ms)
        _persist(store, rec)
    store.add_audit(actor, "rx_approve", rx_id, str(out["approved"]))
    return {**out, "prescription": rec["grid"].summary()}


def export(store: OpsStore, rx_id: str, fmt: str) -> bytes:
    rec = get(store, rx_id)
    return export_zip(rec["grid"], rec["boundary"], fmt, field_name=rec["field_name"])
