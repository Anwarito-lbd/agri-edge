"""Where to fly: parallel-line coverage over a field boundary.

The aircraft had no idea where to go. This turns a field polygon into an ordered
set of flight lines that cover it, which is the missing piece between "we have a
boundary" and "we have a mission".

WHY NOT Fields2Cover
--------------------
The research report recommends it, it is BSD-3, and it is genuinely good. It is
also a C++ library with Python bindings and a build chain, on a project whose Pi
runtime deliberately installs with numpy and PyYAML alone. Boustrophedon coverage
of a polygon is about 150 lines of geometry; a build dependency to avoid writing
them would cost more than it saves. Revisit it if headland optimisation or
multi-vehicle allocation is ever needed -- those are where it really earns its
keep.

THE ONE THING THAT ACTUALLY MATTERS HERE
----------------------------------------
**Line spacing must use the EFFECTIVE swath, not the camera footprint.** Overlap
is not waste: too little and the passes leave untreated or unphotographed strips
between them. Those strips are invisible on the day and show up weeks later as
stripes in the crop, by which time nobody can prove what caused them. Sidelap is
the cheapest insurance in the whole operation.

Everything is in local metres about a field origin, never degrees --
`geofence.project_to_local` does that conversion. See its docstring for why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .geofence import point_in_polygon, polygon_area_m2


def _rotate(points: np.ndarray, deg: float) -> np.ndarray:
    """Rotate points about the origin by `deg` (counter-clockwise)."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.column_stack([
        points[:, 0] * c - points[:, 1] * s,
        points[:, 0] * s + points[:, 1] * c,
    ])


def clip_line_to_polygon(
    y: float, poly: np.ndarray, x_min: float, x_max: float
) -> list[tuple[float, float]]:
    """Intersect a horizontal line at height `y` with a polygon.

    Returns [(x_start, x_end), ...] -- **a list**, because a concave field
    produces several disjoint runs on one line. A notch, a slough, an L-shaped
    quarter: treating those as one run would fly the aircraft straight across the
    gap and record it as covered.

    Vertices lying exactly on the line are the classic degenerate case. The
    half-open rule `(y1 > y) != (y2 > y)` counts each crossing once, so a vertex
    touching the line does not produce a doubled or missing intersection.
    """
    xs: list[float] = []
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xs.append((x2 - x1) * (y - y1) / (y2 - y1) + x1)

    xs.sort()
    runs = []
    for a, b in zip(xs[0::2], xs[1::2]):
        a, b = max(a, x_min), min(b, x_max)
        if b > a:
            runs.append((a, b))
    return runs


@dataclass
class FlightLine:
    """One pass, in local metres."""

    start: tuple[float, float]
    end: tuple[float, float]

    @property
    def length_m(self) -> float:
        return float(math.dist(self.start, self.end))


@dataclass
class CoveragePlan:
    lines: list[FlightLine] = field(default_factory=list)
    swath_m: float = 0.0
    overlap: float = 0.0
    heading_deg: float = 0.0
    area_ha: float = 0.0

    @property
    def line_distance_m(self) -> float:
        """Distance flown ON the lines. Excludes turns -- see `total_distance_m`."""
        return sum(ln.length_m for ln in self.lines)

    @property
    def turn_distance_m(self) -> float:
        """Distance flown BETWEEN lines.

        Counted separately because it is pure overhead: no data is collected and
        no product applied, yet on a short-lined field it can rival the useful
        distance. That ratio is what decides the flight heading.
        """
        return sum(
            math.dist(self.lines[i].end, self.lines[i + 1].start)
            for i in range(len(self.lines) - 1)
        )

    @property
    def total_distance_m(self) -> float:
        return self.line_distance_m + self.turn_distance_m

    def estimate_duration_s(self, speed_ms: float, turn_penalty_s: float = 4.0) -> float:
        """Flight time at a constant speed, plus a fixed cost per turn.

        `turn_penalty_s` covers decelerating, turning and accelerating again,
        which a constant-speed model misses entirely. 4 s is a placeholder for a
        small multirotor; **measure it** on the aircraft before planning a
        battery around this number.
        """
        if speed_ms <= 0:
            raise ValueError("speed_ms must be > 0")
        turns = max(0, len(self.lines) - 1)
        return self.total_distance_m / speed_ms + turns * turn_penalty_s

    def as_dict(self) -> dict:
        return {
            "lines": len(self.lines),
            "heading_deg": round(self.heading_deg, 1),
            "swath_m": self.swath_m,
            "overlap": self.overlap,
            "effective_swath_m": round(self.swath_m * (1.0 - self.overlap), 2),
            "area_ha": round(self.area_ha, 2),
            "line_distance_m": round(self.line_distance_m),
            "turn_distance_m": round(self.turn_distance_m),
            "total_distance_m": round(self.total_distance_m),
        }


def plan_coverage(
    boundary_m: np.ndarray,
    swath_m: float,
    overlap: float = 0.2,
    heading_deg: float = 0.0,
    inset_m: float = 0.0,
) -> CoveragePlan:
    """Parallel-line (boustrophedon) coverage of a field.

    `heading_deg` is the direction the lines run, measured counter-clockwise from
    east in the local frame. `best_heading` will pick one for you.

    Lines alternate direction so the aircraft serpentines rather than flying back
    to the same side every time -- which would roughly double the distance.

    `inset_m` pulls the first and last line in from the boundary. Useful when the
    camera footprint is wider than the swath and you would rather not photograph
    the neighbour's field.
    """
    if swath_m <= 0:
        raise ValueError("swath_m must be > 0")
    if not 0.0 <= overlap < 1.0:
        raise ValueError(f"overlap must be in [0, 1), got {overlap}")

    poly = np.asarray(boundary_m, dtype=np.float64)
    if poly.ndim != 2 or poly.shape[1] != 2 or len(poly) < 3:
        raise ValueError(f"boundary must be (N, 2) metres, got shape {poly.shape}")

    # THE line that matters: space by the effective swath, not the raw footprint.
    spacing = swath_m * (1.0 - overlap)

    # Work in a frame where the lines are horizontal, then rotate back.
    rot = _rotate(poly, -heading_deg)
    x_min, y_min = rot.min(axis=0)
    x_max, y_max = rot.max(axis=0)

    y_lo, y_hi = y_min + inset_m, y_max - inset_m
    if y_hi <= y_lo:
        return CoveragePlan(swath_m=swath_m, overlap=overlap, heading_deg=heading_deg,
                            area_ha=abs(polygon_area_m2(poly)) / 10_000.0)

    # Lines are INSET from the boundary and spaced EXACTLY `spacing` apart.
    #
    # Two bugs live here, and an earlier version had both. Putting a line exactly
    # on the boundary yields nothing: the half-open crossing rule that keeps
    # vertices from double-counting means an edge lying along the line produces
    # no intersection, so that pass silently vanishes. And distributing n lines
    # evenly across the span gives a step of span/(n-1), which is LARGER than the
    # requested spacing -- opening a gap between every pair of passes.
    #
    # Centring the set instead fixes both: exact spacing, and a half-gap of
    # padding at each edge that the swath's own width covers.
    span = y_hi - y_lo
    n_lines = max(1, int(math.ceil(span / spacing)))
    offset = (span - (n_lines - 1) * spacing) / 2.0
    ys = [y_lo + offset + i * spacing for i in range(n_lines)]

    lines: list[FlightLine] = []
    flip = False
    for y in ys:
        runs = clip_line_to_polygon(y, rot, x_min, x_max)
        if flip:
            runs = [(b, a) for a, b in reversed(runs)]
        for a, b in runs:
            seg = _rotate(np.array([[a, y], [b, y]]), heading_deg)
            lines.append(FlightLine((seg[0, 0], seg[0, 1]), (seg[1, 0], seg[1, 1])))
        flip = not flip

    return CoveragePlan(
        lines=lines,
        swath_m=swath_m,
        overlap=overlap,
        heading_deg=heading_deg,
        area_ha=abs(polygon_area_m2(poly)) / 10_000.0,
    )


def best_heading(
    boundary_m: np.ndarray, swath_m: float, overlap: float = 0.2, step_deg: float = 5.0
) -> float:
    """Search headings for the least total distance.

    Fields are rarely square, and flying across the short axis means many short
    lines and many turns. On a long narrow field the difference between the best
    and worst heading is substantial -- which is battery, and battery is flight
    time.

    Minimises total distance rather than line count, because line count ignores
    turns and turns are what actually hurt.
    """
    best, best_cost = 0.0, float("inf")
    for deg in np.arange(0.0, 180.0, step_deg):
        plan = plan_coverage(boundary_m, swath_m, overlap, float(deg))
        if not plan.lines:
            continue
        if plan.total_distance_m < best_cost:
            best, best_cost = float(deg), plan.total_distance_m
    return best


def coverage_gaps(
    plan: CoveragePlan, boundary_m: np.ndarray, samples: int = 60
) -> float:
    """Fraction of the field further than half a swath from any flight line.

    An independent check on the planner rather than a restatement of it: it
    samples the field on a grid and measures distance to the nearest line. If the
    spacing arithmetic is wrong, this notices, and it notices in the units that
    matter -- how much of the field goes unseen.
    """
    poly = np.asarray(boundary_m, dtype=np.float64)
    if not plan.lines:
        return 1.0

    x_min, y_min = poly.min(axis=0)
    x_max, y_max = poly.max(axis=0)
    half = plan.swath_m / 2.0

    starts = np.array([ln.start for ln in plan.lines])
    ends = np.array([ln.end for ln in plan.lines])
    seg = ends - starts
    seg_len2 = np.maximum(np.einsum("ij,ij->i", seg, seg), 1e-12)

    inside = missed = 0
    for x in np.linspace(x_min, x_max, samples):
        for y in np.linspace(y_min, y_max, samples):
            if not point_in_polygon((x, y), poly):
                continue
            inside += 1
            rel = np.array([x, y]) - starts
            t = np.clip(np.einsum("ij,ij->i", rel, seg) / seg_len2, 0.0, 1.0)
            closest = starts + t[:, None] * seg
            if np.min(np.linalg.norm(closest - np.array([x, y]), axis=1)) > half:
                missed += 1

    return missed / inside if inside else 1.0
