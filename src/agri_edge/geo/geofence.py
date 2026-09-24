"""Two boundaries, not one: where the aircraft may fly, and where it may treat.

THE DISTINCTION, AND WHY IT IS NOT PEDANTRY
-------------------------------------------
The reference architecture in `docs/source/research-report.md` makes this its
clearest safety point, and this codebase had no equivalent:

    FLIGHT GEOFENCE     where the aircraft may physically be
    TREATMENT GEOFENCE  where chemical or granular application may occur

They are not the same boundary and the treatment one must be **strictly inside**
the flight one. The reason is geometric: an aircraft flying the edge of a field
still has to turn around, and it will overshoot. If application were gated on the
flight boundary alone, every headland turn would spray past the field edge —
onto a neighbour's crop, a ditch, or a watercourse.

So the aircraft is allowed to fly the full boundary, and application is forced
off before it gets there. That is what lets the vehicle stay controllable while
treatment is independently disabled — the report's own framing.

WHAT THIS MODULE IS AND IS NOT
------------------------------
Pure geometry, no aircraft, no sprayer, and no dependency beyond numpy. It is
usable and testable today, which is the point of writing it before there is
hardware.

It is **not** an enforcement mechanism on its own. The report is explicit that
the treatment boundary should be enforced by the payload controller, independent
of the mission computer, so that a fault in the Linux side cannot open a valve.
This module computes and checks the boundary; something with its own MCU has to
own the interlock. Treat a green result here as necessary, never sufficient.

COORDINATES
-----------
Everything works in a **local projected frame in metres**, never in degrees.
Buffering a polygon by "0.0001 degrees" is a different distance north-south than
east-west and changes with latitude, which is exactly the class of error that
produces a spray overrun nobody can explain afterwards. `project_to_local` does
the conversion once, explicitly, at a stated origin.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

# Mean Earth radius (WGS-84 semi-major). Good to a few parts per thousand for the
# local-tangent-plane approximation used here, which is far tighter than any
# buffer distance this module deals in.
_EARTH_R_M = 6_378_137.0


def project_to_local(
    lats: np.ndarray, lons: np.ndarray, origin: tuple[float, float]
) -> np.ndarray:
    """Geographic degrees -> local ENU metres about `origin` (lat, lon).

    An equirectangular tangent-plane projection: east scales with cos(latitude),
    north does not. Accurate to well under a metre over a field-sized area, and
    the error grows with distance from the origin, so use a field-local origin.

    This exists so no caller is ever tempted to do metres-vs-degrees arithmetic
    inline. Buffering in degrees is a silent, latitude-dependent error.
    """
    lat0, lon0 = origin
    lat = np.asarray(lats, dtype=np.float64)
    lon = np.asarray(lons, dtype=np.float64)
    cos_lat0 = math.cos(math.radians(lat0))
    east = np.radians(lon - lon0) * _EARTH_R_M * cos_lat0
    north = np.radians(lat - lat0) * _EARTH_R_M
    return np.column_stack([east, north])


def polygon_area_m2(poly: np.ndarray) -> float:
    """Signed shoelace area. Positive means counter-clockwise."""
    p = np.asarray(poly, dtype=np.float64)
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def point_in_polygon(point: tuple[float, float], poly: np.ndarray) -> bool:
    """Ray-casting containment test. Points exactly on an edge are unspecified.

    Edge cases are deliberately not promised: a treatment decision must never
    hinge on a coordinate landing exactly on a boundary line, which is why
    `TreatmentGeofence` uses a buffer rather than testing the raw boundary.
    """
    p = np.asarray(poly, dtype=np.float64)
    x, y = float(point[0]), float(point[1])
    inside = False
    n = len(p)
    for i in range(n):
        x1, y1 = p[i]
        x2, y2 = p[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_cross:
                inside = not inside
    return inside


def distance_to_boundary_m(point: tuple[float, float], poly: np.ndarray) -> float:
    """Shortest distance from a point to the polygon's edge, in metres.

    Unsigned: it says how far the boundary is, not which side you are on. Callers
    combine it with `point_in_polygon`, because those are genuinely two questions
    and conflating them is how a sign error becomes a spray overrun.
    """
    p = np.asarray(poly, dtype=np.float64)
    a = p
    b = np.roll(p, -1, axis=0)
    ab = b - a
    ap = np.asarray(point, dtype=np.float64) - a
    denom = np.einsum("ij,ij->i", ab, ab)
    # A zero-length edge (duplicated vertex) would divide by zero; clamp to the
    # vertex instead of producing a nan that silently poisons the minimum.
    t = np.where(denom > 0, np.einsum("ij,ij->i", ap, ab) / np.maximum(denom, 1e-12), 0.0)
    t = np.clip(t, 0.0, 1.0)
    closest = a + t[:, None] * ab
    return float(np.min(np.linalg.norm(closest - np.asarray(point), axis=1)))


def shrink_polygon(poly: np.ndarray, buffer_m: float) -> np.ndarray:
    """Move every vertex inward by `buffer_m` along its angle bisector.

    A vertex-offset inset, not a true morphological erosion. It is correct for
    convex polygons and conservative-to-wrong on sharply concave ones, where
    offset edges can cross and produce a self-intersecting result.

    That limitation is why `TreatmentGeofence.may_treat` does NOT rely on this
    shape: it tests distance to the *original* boundary instead, which is exact
    for any polygon. The inset is provided for display and for planning a
    coverage path, where an approximate inner outline is what you want.
    """
    p = np.asarray(poly, dtype=np.float64)
    if buffer_m <= 0:
        return p.copy()

    # Orientation decides which way "inward" points.
    sign = 1.0 if polygon_area_m2(p) > 0 else -1.0
    prev_v = p - np.roll(p, 1, axis=0)
    next_v = np.roll(p, -1, axis=0) - p

    def _unit(v):
        n = np.linalg.norm(v, axis=1, keepdims=True)
        return np.divide(v, np.maximum(n, 1e-12))

    # Inward normal of each adjoining edge, averaged to get the bisector.
    u_prev, u_next = _unit(prev_v), _unit(next_v)
    n_prev = np.column_stack([-u_prev[:, 1], u_prev[:, 0]]) * sign
    n_next = np.column_stack([-u_next[:, 1], u_next[:, 0]]) * sign
    bisector = _unit(n_prev + n_next)
    # Scale so the perpendicular offset is buffer_m even at a sharp corner.
    cos_half = np.einsum("ij,ij->i", bisector, n_next)
    scale = buffer_m / np.maximum(np.abs(cos_half), 0.2)   # cap runaway at spikes
    return p + bisector * scale[:, None]


class TreatmentGeofence:
    """A flight boundary, and a strictly smaller boundary for application.

    Construct from a field polygon in local metres, with the inward buffer that
    application must respect:

        fence = TreatmentGeofence(field_poly_m, treatment_buffer_m=10.0)
        fence.may_fly((x, y))      -> inside the field at all?
        fence.may_treat((x, y))    -> inside AND at least 10 m from the edge?

    `may_treat` is deliberately the conjunction: outside the field, treatment is
    refused regardless of buffer arithmetic, so a sign error cannot authorise
    application over a neighbour's crop.
    """

    def __init__(self, boundary_m: np.ndarray, treatment_buffer_m: float = 10.0,
                 holes_m=()):
        poly = np.asarray(boundary_m, dtype=np.float64)
        if poly.ndim != 2 or poly.shape[1] != 2 or len(poly) < 3:
            raise ValueError(
                f"Boundary must be an (N, 2) array of at least 3 points in METRES, "
                f"got shape {poly.shape}. Convert with project_to_local() first -- "
                f"buffering in degrees is a latitude-dependent error."
            )
        if treatment_buffer_m < 0:
            raise ValueError(
                "treatment_buffer_m must be >= 0. A negative buffer would put the "
                "treatment boundary OUTSIDE the flight boundary, which inverts the "
                "entire safety argument."
            )
        self.boundary = poly
        self.treatment_buffer_m = float(treatment_buffer_m)
        # Areas inside the field where application is never permitted -- a
        # slough, a yard site, a well head. Each gets the same buffer as the
        # outer edge. Flight over them is fine; treatment is not.
        self.holes = [np.asarray(h, dtype=np.float64) for h in holes_m]
        for h in self.holes:
            if h.ndim != 2 or h.shape[1] != 2 or len(h) < 3:
                raise ValueError(f"Each hole must be an (N, 2) ring in metres, got {h.shape}.")

    @property
    def area_m2(self) -> float:
        return abs(polygon_area_m2(self.boundary))

    @property
    def area_ha(self) -> float:
        return self.area_m2 / 10_000.0

    def treatment_outline(self) -> np.ndarray:
        """The inner boundary, for display and path planning. See `shrink_polygon`."""
        return shrink_polygon(self.boundary, self.treatment_buffer_m)

    def may_fly(self, point: tuple[float, float]) -> bool:
        return point_in_polygon(point, self.boundary)

    def may_treat(self, point: tuple[float, float], position_error_m: float = 0.0) -> bool:
        """Inside the field, outside every hole, and at least `treatment_buffer_m`
        from all of those edges -- widened by `position_error_m`.

        The point is where we THINK the target is. A detection georeferenced to
        +/- 4 m that sits 12 m inside a 10 m buffer may really be 8 m inside it,
        so the uncertainty is spent out of the margin rather than ignored.
        """
        if position_error_m < 0:
            raise ValueError("position_error_m must be >= 0")
        return self.treatment_margin_m(point) >= position_error_m

    def treatment_margin_m(self, point: tuple[float, float]) -> float:
        """Metres of buffer remaining. Negative once application must be off.

        Useful as a continuous signal: a planner can begin closing valves as this
        approaches zero rather than waiting for the boolean to flip, which is what
        a real system needs given valve actuation time. Holes count: the margin is
        the smallest over the outer edge and every hole's edge.
        """
        d = distance_to_boundary_m(point, self.boundary)
        if not self.may_fly(point):
            d = -d
        for hole in self.holes:
            dh = distance_to_boundary_m(point, hole)
            if point_in_polygon(point, hole):
                dh = -dh
            d = min(d, dh)
        return d - self.treatment_buffer_m


def spray_flow_l_min(rate_l_ha: float, speed_m_s: float, swath_m: float) -> float:
    """Q = R x v x W x 0.006  -- litres/min from litres/hectare.

    The standard agricultural area-rate relationship, from the research report.
    The 0.006 converts m/s x m into hectares per minute (60 s/min divided by
    10,000 m^2/ha).

    Worked example from the report: 20 L/ha at 8 m/s with an 8 m swath is
    20 x 8 x 8 x 0.006 = 7.68 L/min.

    This is the **feed-forward** term only. The report is explicit that a real
    controller closes the loop on a flow meter and must never infer application
    from pump PWM, because pump output drifts with pressure, viscosity, wear and
    filter loading. Nothing here should be mistaken for that controller.
    """
    for name, value in (("rate_l_ha", rate_l_ha), ("speed_m_s", speed_m_s),
                        ("swath_m", swath_m)):
        if value < 0:
            raise ValueError(f"{name} must be >= 0, got {value}")
    return rate_l_ha * speed_m_s * swath_m * 0.006


def coverage_rate_ha_h(speed_m_s: float, swath_m: float, overlap: float = 0.0) -> float:
    """Hectares per hour at a given speed and effective swath.

    `overlap` is the fraction of the swath given up to sidelap between passes, so
    the effective swath is `swath_m * (1 - overlap)`. Sidelap is not waste: too
    little and the passes leave untreated strips that only show up as stripes in
    the crop weeks later.
    """
    if not 0.0 <= overlap < 1.0:
        raise ValueError(f"overlap must be in [0, 1), got {overlap}")
    return speed_m_s * swath_m * (1.0 - overlap) * 3600.0 / 10_000.0


def load_boundary_geojson(path, origin: tuple[float, float] | None = None):
    """Read a GeoJSON Polygon and return (local-metre ring, origin lat/lon).

    Accepts a bare Polygon, a Feature, or a FeatureCollection whose first feature
    is a Polygon -- all three are what mapping tools actually export, and
    rejecting two of them would just mean the user edits the file by hand.

    Only the OUTER ring is returned -- right for flight and coverage planning,
    WRONG for treatment: a hole (a slough, a yard site) is a place application
    must stay off. Treatment callers use `load_treatment_boundary`, which keeps
    the holes.

    The origin defaults to the first vertex, so all planning happens in metres
    about the field itself. Returns degrees nowhere.
    """
    outer, _holes, org = load_treatment_boundary(path, origin)
    return outer, org


def load_treatment_boundary(path, origin: tuple[float, float] | None = None):
    """Read a GeoJSON Polygon: (outer ring, [hole rings], origin), in local metres.

    Until 24 Sept 2026 the pipeline used the outer ring only, so treatment was
    permitted inside a boundary's holes.
    """
    import json

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    geom = data
    if data.get("type") == "FeatureCollection":
        features = data.get("features") or []
        if not features:
            raise ValueError(f"{path}: FeatureCollection has no features.")
        geom = features[0].get("geometry", {})
    elif data.get("type") == "Feature":
        geom = data.get("geometry", {})

    if geom.get("type") != "Polygon":
        raise ValueError(
            f"{path}: need a Polygon, got {geom.get('type')!r}. A treatment "
            "boundary must be an area, not a point or a line."
        )
    rings = geom.get("coordinates") or [[]]
    for ring in rings:
        if len(ring) < 4:
            raise ValueError(f"{path}: a polygon ring needs at least 4 positions.")

    def _latlon(ring):
        # GeoJSON is [lon, lat]. Reversed, the field lands in the wrong hemisphere.
        lons = [float(p[0]) for p in ring]
        lats = [float(p[1]) for p in ring]
        if ring[0] == ring[-1]:
            lons, lats = lons[:-1], lats[:-1]   # drop the repeated closing vertex
        return lats, lons

    lats, lons = _latlon(rings[0])
    org = origin or (lats[0], lons[0])
    holes = []
    for r in rings[1:]:
        hlats, hlons = _latlon(r)
        holes.append(project_to_local(hlats, hlons, org))
    return project_to_local(lats, lons, org), holes, org
