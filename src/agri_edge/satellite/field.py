"""One scene, one field: cloud mask, NDVI / NDRE, field and per-cell statistics.

Pure numpy. Input bands are reflectance arrays already resampled onto one grid
of pixel centres given as lon/lat arrays (see `reader.py`), so everything here
is testable with synthetic arrays and runs without GDAL.

Cells are fixed squares in a local metric frame anchored at the south-west
corner of the field's bounding box, so the same cell id means the same patch
of ground in every scene -- which is what makes a per-cell time series possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..geo.geofence import project_to_local
from ..geo.georeference import local_to_geographic

# Sentinel-2 L2A scene classification (SCL): 4 vegetation, 5 not vegetated.
# Everything else -- no data, saturated, dark, cloud shadow, water, unclassified,
# cloud (medium/high), cirrus, snow -- is excluded. Unclassified (7) is dropped on
# purpose: it clusters at cloud edges, where NDVI is quietly wrong.
VALID_SCL = (4, 5)


@dataclass
class Boundary:
    outer: list[tuple[float, float]]                      # (lon, lat)
    holes: list[list[tuple[float, float]]] = field(default_factory=list)

    @classmethod
    def from_geojson(cls, geom: dict) -> "Boundary":
        if geom.get("type") == "Feature":
            geom = geom.get("geometry") or {}
        if geom.get("type") != "Polygon":
            raise ValueError("field boundary must be a GeoJSON Polygon")
        rings = [[(float(p[0]), float(p[1])) for p in ring] for ring in geom["coordinates"]]
        if not rings or len(rings[0]) < 4:
            raise ValueError("polygon needs an outer ring of at least 4 positions")
        return cls(rings[0], rings[1:])

    @property
    def origin(self) -> tuple[float, float]:
        """(lat, lon) of the bounding box's south-west corner."""
        return min(p[1] for p in self.outer), min(p[0] for p in self.outer)

    @property
    def bbox(self) -> list[float]:
        lons = [p[0] for p in self.outer]
        lats = [p[1] for p in self.outer]
        return [min(lons), min(lats), max(lons), max(lats)]


def points_in_polygon(x: np.ndarray, y: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Even-odd rule, vectorised over points. `ring` is (N, 2)."""
    inside = np.zeros(x.shape, dtype=bool)
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        cond = (y1 > y) != (y2 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (x2 - x1) * (y - y1) / (y2 - y1) + x1
        inside ^= cond & (x < xint)
    return inside


def _local(b: Boundary, lats: np.ndarray, lons: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    en = project_to_local(lats.ravel(), lons.ravel(), b.origin)
    return en[:, 0].reshape(lats.shape), en[:, 1].reshape(lats.shape)


def field_mask(b: Boundary, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    e, n = _local(b, lats, lons)

    def ring_local(ring):
        return project_to_local([p[1] for p in ring], [p[0] for p in ring], b.origin)

    mask = points_in_polygon(e, n, ring_local(b.outer))
    for hole in b.holes:
        mask &= ~points_in_polygon(e, n, ring_local(hole))
    return mask


def normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (a - b) / (a + b)
    out[~np.isfinite(out)] = np.nan
    return out


@dataclass
class CellStat:
    cell: str
    ndvi: float
    valid_fraction: float
    n: int


@dataclass
class FieldObservation:
    scene_id: str
    date: str
    valid_fraction: float
    ndvi_mean: float | None
    ndvi_median: float | None
    ndvi_p10: float | None
    ndvi_p90: float | None
    ndre_mean: float | None
    cells: list[CellStat] = field(default_factory=list)
    usable: bool = False

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["cells"] = [c.__dict__ for c in self.cells]
        return d


def observe(scene_id: str, date: str, bands: dict[str, np.ndarray], lats: np.ndarray,
            lons: np.ndarray, boundary: Boundary, *, cell_m: float = 50.0,
            min_valid_fraction: float = 0.6, min_cell_valid: float = 0.6) -> FieldObservation:
    """Statistics for one scene over one field.

    A scene counts (`usable`) only if at least `min_valid_fraction` of the field
    is clear: a field half under cloud is a different sample of ground than the
    last one, and its mean would move for that reason alone.
    """
    red, nir, re_, scl = (np.asarray(bands[k], dtype=np.float64) for k in ("red", "nir", "rededge", "scl"))
    inside = field_mask(boundary, lats, lons)
    clear = np.isin(scl.astype(np.int64), VALID_SCL) & np.isfinite(red) & np.isfinite(nir)
    ndvi = normalized_difference(nir, red)
    ndre = normalized_difference(nir, re_)
    good = inside & clear & np.isfinite(ndvi)
    n_in = int(inside.sum())
    vf = float(good.sum() / n_in) if n_in else 0.0
    obs = FieldObservation(scene_id, date, round(vf, 3), None, None, None, None, None)
    if not good.any():
        return obs
    v = ndvi[good]
    obs.ndvi_mean = round(float(v.mean()), 4)
    obs.ndvi_median = round(float(np.median(v)), 4)
    obs.ndvi_p10 = round(float(np.percentile(v, 10)), 4)
    obs.ndvi_p90 = round(float(np.percentile(v, 90)), 4)
    r = ndre[good & np.isfinite(ndre)]
    obs.ndre_mean = round(float(r.mean()), 4) if r.size else None
    obs.usable = vf >= min_valid_fraction

    e, n = _local(boundary, lats, lons)
    ci = np.floor(e / cell_m).astype(np.int64)
    cj = np.floor(n / cell_m).astype(np.int64)
    for i, j in {(int(a), int(b)) for a, b in zip(ci[inside], cj[inside])}:
        in_cell = inside & (ci == i) & (cj == j)
        g = good & in_cell
        n_cell = int(in_cell.sum())
        if n_cell < 4:
            continue
        frac = float(g.sum() / n_cell)
        if frac < min_cell_valid:
            continue
        obs.cells.append(CellStat(f"{i}_{j}", round(float(ndvi[g].mean()), 4), round(frac, 3), int(g.sum())))
    obs.cells.sort(key=lambda c: c.cell)
    return obs


def cell_polygon(boundary: Boundary, cell: str, cell_m: float = 50.0) -> dict:
    """GeoJSON Polygon of a cell id, in lon/lat."""
    i, j = (int(x) for x in cell.split("_"))
    corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1), (i, j)]
    ring = []
    for ci, cj in corners:
        lat, lon = local_to_geographic(cj * cell_m, ci * cell_m, boundary.origin)
        ring.append([round(lon, 7), round(lat, 7)])
    return {"type": "Polygon", "coordinates": [ring]}
