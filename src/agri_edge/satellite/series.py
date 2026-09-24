"""Per-field time series, change detection, and where the drone should go.

CHANGE DETECTION
----------------
A field's NDVI moves for reasons nobody needs to scout: green-up, senescence,
haze the atmospheric correction missed, a slightly different sun angle. Those
move the whole field together. What deserves a visit is a patch that moves
*differently from the rest of the field*.

So for each 50 m cell: delta = latest - baseline (median of the previous 1-3
clear scenes within ~5 weeks). The field's own median delta is subtracted,
leaving the cell's residual. A cell is flagged when its residual is below both
an absolute floor (0.08 NDVI) and 3 robust standard deviations (MAD) of the
field's residuals, and it had real canopy at baseline (NDVI >= 0.3 -- bare
soil NDVI is noise).

Flagged cells are grouped into connected patches, and each patch gets a drone
coverage plan (geo/coverage.py), so a scouting flight covers the patches
rather than the farm.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from ..geo.coverage import best_heading, plan_coverage
from .field import Boundary, cell_polygon

SCHEMA = """CREATE TABLE IF NOT EXISTS sat_obs (
    field_id TEXT NOT NULL,
    scene_id TEXT NOT NULL,
    date TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (field_id, scene_id)
)"""


def save(db: str, field_id: str, obs: dict) -> None:
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    try:
        con.execute(SCHEMA)
        con.execute("INSERT OR REPLACE INTO sat_obs(field_id, scene_id, date, payload) VALUES (?,?,?,?)",
                    (field_id, obs["scene_id"], obs["date"], json.dumps(obs)))
        con.commit()
    finally:
        con.close()


def load(db: str, field_id: str) -> list[dict]:
    if not Path(db).exists():
        return []
    con = sqlite3.connect(db)
    try:
        con.execute(SCHEMA)
        rows = con.execute("SELECT payload FROM sat_obs WHERE field_id=? ORDER BY date",
                           (field_id,)).fetchall()
    finally:
        con.close()
    return [json.loads(r[0]) for r in rows]


def known_scenes(db: str, field_id: str) -> set[str]:
    return {o["scene_id"] for o in load(db, field_id)}


@dataclass
class FlaggedCell:
    cell: str
    baseline: float
    latest: float
    delta: float
    residual: float
    polygon: dict


@dataclass
class ChangeReport:
    field_id: str
    status: str                         # ok | flagged | insufficient
    latest_date: str | None = None
    baseline_dates: list[str] = field(default_factory=list)
    field_shift: float | None = None
    threshold: float | None = None
    cells_compared: int = 0
    flagged: list[FlaggedCell] = field(default_factory=list)
    patches: list[dict] = field(default_factory=list)
    why: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["flagged"] = [f.__dict__ for f in self.flagged]
        return d

    def geojson(self) -> dict:
        feats = [{"type": "Feature", "id": f.cell, "geometry": f.polygon,
                  "properties": {"kind": "ndvi_decline", "delta": f.delta, "residual": f.residual,
                                 "baseline": f.baseline, "latest": f.latest,
                                 "latest_date": self.latest_date}} for f in self.flagged]
        feats += [{"type": "Feature", "id": f"patch-{i}", "geometry": p["polygon"],
                   "properties": {"kind": "scout_patch", **{k: v for k, v in p.items() if k != "polygon"}}}
                  for i, p in enumerate(self.patches)]
        return {"type": "FeatureCollection", "features": feats}


def detect_change(field_id: str, observations: list[dict], boundary: Boundary, *,
                  cell_m: float = 50.0, min_drop: float = 0.08, k_mad: float = 3.0,
                  min_canopy: float = 0.3, baseline_window_days: int = 35,
                  min_gap_days: int = 3, swath_m: float = 30.0) -> ChangeReport:
    usable = sorted((o for o in observations if o.get("usable")), key=lambda o: o["date"])
    rep = ChangeReport(field_id, "insufficient")
    if len(usable) < 2:
        rep.why.append(f"{len(usable)} clear scene(s) so far; change needs at least two.")
        return rep
    latest = usable[-1]
    t_latest = date.fromisoformat(latest["date"])
    base = [o for o in usable[:-1]
            if t_latest - timedelta(days=baseline_window_days) <= date.fromisoformat(o["date"])
            <= t_latest - timedelta(days=min_gap_days)][-3:]
    rep.latest_date = latest["date"]
    if not base:
        rep.why.append(f"No clear scene between {min_gap_days} and {baseline_window_days} days "
                       f"before {latest['date']} to compare against.")
        return rep
    rep.baseline_dates = [o["date"] for o in base]
    base_cells: dict[str, list[float]] = {}
    for o in base:
        for c in o["cells"]:
            base_cells.setdefault(c["cell"], []).append(c["ndvi"])
    latest_cells = {c["cell"]: c["ndvi"] for c in latest["cells"]}
    common = sorted(set(base_cells) & set(latest_cells))
    rep.cells_compared = len(common)
    if len(common) < 5:
        rep.why.append(f"Only {len(common)} cells clear in both; need 5 to tell a patch from the field.")
        return rep

    b = np.array([float(np.median(base_cells[c])) for c in common])
    lt = np.array([latest_cells[c] for c in common])
    delta = lt - b
    shift = float(np.median(delta))
    resid = delta - shift
    mad = float(np.median(np.abs(resid - np.median(resid)))) * 1.4826
    thr = max(min_drop, k_mad * mad)
    rep.field_shift, rep.threshold = round(shift, 4), round(thr, 4)
    flag = (resid <= -thr) & (b >= min_canopy)
    for c, bb, ll, dd, rr, f in zip(common, b, lt, delta, resid, flag):
        if f:
            rep.flagged.append(FlaggedCell(c, round(float(bb), 4), round(float(ll), 4),
                                           round(float(dd), 4), round(float(rr), 4),
                                           cell_polygon(boundary, c, cell_m)))
    rep.why.append(f"Compared {len(common)} cells: {latest['date']} against the median of "
                   f"{', '.join(rep.baseline_dates)}.")
    rep.why.append(f"The field as a whole moved {shift:+.3f} NDVI; cells are judged against that, "
                   "so green-up or senescence does not trigger a visit.")
    if rep.flagged:
        rep.status = "flagged"
        rep.why.append(f"{len(rep.flagged)} cell(s) fell at least {thr:.3f} NDVI more than the field "
                       f"(larger of {min_drop} and {k_mad} MADs).")
        rep.patches = _patches(rep.flagged, boundary, cell_m, swath_m)
    else:
        rep.status = "ok"
        rep.why.append("No cell declined meaningfully faster than the field.")
    return rep


def _patches(flagged: list[FlaggedCell], boundary: Boundary, cell_m: float, swath_m: float) -> list[dict]:
    """Connected groups of flagged cells, each with a scouting coverage plan."""
    ids: dict[tuple[int, int], FlaggedCell] = {}
    for f in flagged:
        i_s, j_s = f.cell.split("_")
        ids[(int(i_s), int(j_s))] = f
    seen: set[tuple[int, int]] = set()
    out: list[dict[str, Any]] = []
    for start in ids:
        if start in seen:
            continue
        stack, group = [start], []
        seen.add(start)
        while stack:
            i, j = stack.pop()
            group.append((i, j))
            for nb in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if nb in ids and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        i0 = min(g[0] for g in group) * cell_m
        i1 = (max(g[0] for g in group) + 1) * cell_m
        j0 = min(g[1] for g in group) * cell_m
        j1 = (max(g[1] for g in group) + 1) * cell_m
        rect_m = np.array([[i0, j0], [i1, j0], [i1, j1], [i0, j1]], dtype=np.float64)
        plan = plan_coverage(rect_m, swath_m=swath_m, overlap=0.2,
                             heading_deg=best_heading(rect_m, swath_m))
        from ..geo.georeference import local_to_geographic

        ring = []
        for e, n in [(i0, j0), (i1, j0), (i1, j1), (i0, j1), (i0, j0)]:
            lat, lon = local_to_geographic(n, e, boundary.origin)
            ring.append([round(lon, 7), round(lat, 7)])
        worst = min(ids[g].residual for g in group)
        out.append({
            "cells": len(group),
            "area_ha": round(len(group) * cell_m * cell_m / 10_000, 2),
            "worst_residual": worst,
            "polygon": {"type": "Polygon", "coordinates": [ring]},
            "mission": {**plan.as_dict(), "est_duration_s": round(plan.estimate_duration_s(8.0))},
        })
    out.sort(key=lambda p: float(p["worst_residual"]))
    return out
