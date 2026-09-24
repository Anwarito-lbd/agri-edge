"""Rate grids, in a local metric frame, clipped to where treatment is allowed.

Two sources:

* **Spot spray from detections.** A cell is ON when enough georeferenced
  detections fall in it -- or within their own position error of it: a weed
  placed to +/- 3 m next to a cell edge may be in the neighbour, so the
  neighbour is switched on too. Wider coverage is the safe error for a weed;
  a missed weed is the failure the farmer is paying to avoid.
* **Variable rate from zones.** Per-cell values (e.g. the satellite NDVI cells)
  split into quantile zones, one rate per zone.

Either way a cell is applied only if its whole footprint lies inside the
treatment boundary, outside every hole, beyond the buffer (TreatmentGeofence
at the cell centre with the half-diagonal as position error), and its rate is
clamped to the SafetyConstraints limits.

`validated` is True only if the grid was clipped to a treatment boundary AND,
for detection-sourced grids, every detection came from a model that has been
validated on local imagery. That flag is what the approval gate checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import numpy as np

from ..geo.geofence import TreatmentGeofence, project_to_local
from ..geo.georeference import _EARTH_R_M, local_to_geographic
from ..ops.types import new_id
from ..ops.vra import SafetyConstraints


@dataclass
class DetectionPoint:
    lat: float
    lon: float
    label: str = "weed"
    confidence: float = 1.0
    position_error_m: float = 0.0
    model: tuple[str, str] | None = None        # (name, version)


@dataclass
class RateGrid:
    prescription_id: str
    field_id: str
    product: str
    unit: str                         # L/ha | kg/ha
    source: str                       # detections | zones
    cell_m: float
    origin: tuple[float, float]       # (lat, lon) of cell (0, 0)'s south-west corner
    rates: np.ndarray                 # (rows, cols), row 0 = south; 0 = off
    applicable: np.ndarray            # (rows, cols) bool: inside the treatment area
    constraints: SafetyConstraints = field(default_factory=SafetyConstraints)
    validated: bool = False
    issues: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved: bool = False
    approved_by: str | None = None
    approved_at: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def rows(self) -> int:
        return int(self.rates.shape[0])

    @property
    def cols(self) -> int:
        return int(self.rates.shape[1])

    def cell_latlon(self, r: int, c: int) -> list[tuple[float, float]]:
        """Corners (lat, lon), SW, SE, NE, NW."""
        pts = []
        for de, dn in ((0, 0), (1, 0), (1, 1), (0, 1)):
            pts.append(local_to_geographic((r + dn) * self.cell_m, (c + de) * self.cell_m, self.origin))
        return pts

    @property
    def cell_deg(self) -> tuple[float, float]:
        """(north size, east size) of a cell in degrees at the grid origin, with
        the same spherical model `local_to_geographic` uses, so a degree grid
        and the metre grid describe the same cells."""
        lat0 = self.origin[0]
        return (math.degrees(self.cell_m / _EARTH_R_M),
                math.degrees(self.cell_m / (_EARTH_R_M * math.cos(math.radians(lat0)))))

    def summary(self) -> dict:
        on = self.rates > 0
        cell_ha = self.cell_m * self.cell_m / 10_000
        return {
            "prescription_id": self.prescription_id, "field_id": self.field_id,
            "product": self.product, "unit": self.unit, "source": self.source,
            "cell_m": self.cell_m, "rows": self.rows, "cols": self.cols,
            "cells_on": int(on.sum()), "treated_ha": round(float(on.sum()) * cell_ha, 4),
            "applicable_ha": round(float(self.applicable.sum()) * cell_ha, 4),
            "total_product": round(float((self.rates * cell_ha).sum()), 2),
            "validated": self.validated, "issues": list(self.issues),
            "approved": self.approved, "approved_by": self.approved_by,
            "approved_at": self.approved_at, "created_at": self.created_at,
            "notes": list(self.notes),
        }

    def geojson(self) -> dict:
        feats = []
        for r in range(self.rows):
            for c in range(self.cols):
                if not self.applicable[r, c]:
                    continue
                ring = [[round(lon, 7), round(lat, 7)] for lat, lon in self.cell_latlon(r, c)]
                ring.append(ring[0])
                feats.append({"type": "Feature", "id": f"{r}_{c}",
                              "geometry": {"type": "Polygon", "coordinates": [ring]},
                              "properties": {"rate": float(self.rates[r, c]), "unit": self.unit}})
        return {"type": "FeatureCollection", "features": feats}


def _frame(boundary_lonlat: list[tuple[float, float]], cell_m: float):
    lats = [p[1] for p in boundary_lonlat]
    lons = [p[0] for p in boundary_lonlat]
    origin = (min(lats), min(lons))
    ring = project_to_local(lats, lons, origin)
    cols = max(1, math.ceil(ring[:, 0].max() / cell_m))
    rows = max(1, math.ceil(ring[:, 1].max() / cell_m))
    return origin, ring, rows, cols


def _applicable(fence: TreatmentGeofence, rows: int, cols: int, cell_m: float) -> np.ndarray:
    half_diag = cell_m * math.sqrt(2) / 2
    ok = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        for c in range(cols):
            centre = ((c + 0.5) * cell_m, (r + 0.5) * cell_m)
            ok[r, c] = fence.may_treat(centre, position_error_m=half_diag)
    return ok


def _fence(boundary: dict, buffer_m: float, origin, ring) -> TreatmentGeofence:
    holes = []
    for h in boundary["coordinates"][1:]:
        holes.append(project_to_local([p[1] for p in h], [p[0] for p in h], origin))
    return TreatmentGeofence(ring, buffer_m, holes_m=holes)


def _ring(boundary: dict) -> list[tuple[float, float]]:
    if boundary.get("type") != "Polygon":
        raise ValueError("treatment boundary must be a GeoJSON Polygon")
    ring = [(float(p[0]), float(p[1])) for p in boundary["coordinates"][0]]
    if ring and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        raise ValueError("treatment boundary needs at least 3 distinct vertices")
    return ring


def spot_spray(field_id: str, boundary: dict, detections: Iterable[DetectionPoint], *,
               rate: float, product: str = "herbicide", unit: str = "L/ha", cell_m: float = 6.0,
               buffer_m: float = 10.0, min_count: int = 1, min_confidence: float = 0.3,
               validated_models: set[tuple[str, str]] | frozenset = frozenset(),
               constraints: SafetyConstraints | None = None) -> RateGrid:
    """On/off grid at sprayer-section resolution (`cell_m`, e.g. 6 m sections)."""
    constraints = constraints or SafetyConstraints()
    ring_ll = _ring(boundary)
    origin, ring, rows, cols = _frame(ring_ll, cell_m)
    fence = _fence(boundary, buffer_m, origin, ring)
    applicable = _applicable(fence, rows, cols, cell_m)
    counts = np.zeros((rows, cols), dtype=np.int64)
    dets = [d for d in detections if d.confidence >= min_confidence]
    models = {d.model for d in dets}
    for d in dets:
        e, n = project_to_local([d.lat], [d.lon], origin)[0]
        err = max(d.position_error_m, 0.0)
        c0, c1 = int(math.floor((e - err) / cell_m)), int(math.floor((e + err) / cell_m))
        r0, r1 = int(math.floor((n - err) / cell_m)), int(math.floor((n + err) / cell_m))
        for r in range(max(r0, 0), min(r1, rows - 1) + 1):
            for c in range(max(c0, 0), min(c1, cols - 1) + 1):
                counts[r, c] += 1
    clamped = min(max(rate, constraints.min_rate_l_ha), constraints.max_rate_l_ha)
    rates = np.where((counts >= min_count) & applicable, clamped, 0.0)
    g = RateGrid(new_id("rx_"), field_id, product, unit, "detections", cell_m, origin, rates,
                 applicable, constraints)
    if clamped != rate:
        g.notes.append(f"rate {rate} clamped to {clamped} by the safety constraints")
    outside = int(((counts >= min_count) & ~applicable).sum())
    if outside:
        g.notes.append(f"{outside} cell(s) with detections lie outside the treatment area "
                       "(boundary, hole or buffer) and stay off")
    unvalidated = sorted(f"{m[0]} v{m[1]}" if m else "unknown model"
                         for m in models if m not in validated_models)
    if unvalidated:
        g.issues.append("detections from a model not validated on local imagery: "
                        + ", ".join(unvalidated))
    if not dets:
        g.issues.append("no detections above the confidence threshold")
    g.validated = not g.issues
    return g


def variable_rate(field_id: str, boundary: dict, cell_values: dict[tuple[float, float], float],
                  rates_by_zone: list[float], *, product: str = "nitrogen", unit: str = "kg/ha",
                  cell_m: float = 20.0, buffer_m: float = 5.0,
                  constraints: SafetyConstraints | None = None,
                  invert: bool = False) -> RateGrid:
    """Quantile zones of a per-location value -> one rate per zone.

    `cell_values` maps (lat, lon) sample points (e.g. satellite cell centres) to
    a value. Zone 0 is the lowest values; `invert=True` gives the LOWEST values
    the HIGHEST rate (e.g. more nitrogen where vigour is low).
    """
    constraints = constraints or SafetyConstraints()
    if not rates_by_zone:
        raise ValueError("rates_by_zone must not be empty")
    ring_ll = _ring(boundary)
    origin, ring, rows, cols = _frame(ring_ll, cell_m)
    fence = _fence(boundary, buffer_m, origin, ring)
    applicable = _applicable(fence, rows, cols, cell_m)
    sums = np.zeros((rows, cols))
    n = np.zeros((rows, cols))
    for (lat, lon), v in cell_values.items():
        e, nn = project_to_local([lat], [lon], origin)[0]
        c, r = int(e // cell_m), int(nn // cell_m)
        if 0 <= r < rows and 0 <= c < cols and np.isfinite(v):
            sums[r, c] += v
            n[r, c] += 1
    have = n > 0
    vals = np.where(have, sums / np.maximum(n, 1), np.nan)
    k = len(rates_by_zone)
    known = vals[have & applicable]
    edges = np.quantile(known, np.linspace(0, 1, k + 1)[1:-1]) if known.size else np.array([])
    zones = np.digitize(np.nan_to_num(vals, nan=0.0), edges) if edges.size else np.zeros_like(vals, dtype=int)
    if invert:
        zones = (k - 1) - zones
    lo, hi = constraints.min_rate_l_ha, constraints.max_rate_l_ha
    zone_rates = np.array([min(max(r, lo), hi) for r in rates_by_zone])
    rates = np.where(have & applicable, zone_rates[zones], 0.0)
    g = RateGrid(new_id("rx_"), field_id, product, unit, "zones", cell_m, origin, rates,
                 applicable, constraints)
    if any(r != z for r, z in zip(rates_by_zone, zone_rates)):
        g.notes.append("one or more zone rates clamped by the safety constraints")
    missing = int((applicable & ~have).sum())
    if missing:
        g.notes.append(f"{missing} applicable cell(s) had no data and are left at 0")
    if not have.any():
        g.issues.append("no values fell inside the field")
    g.validated = not g.issues
    return g
