"""Tests for parallel-line coverage planning.

`coverage_gaps` is the important one, and it is deliberately an *independent*
measure rather than a restatement of the planner: it samples the field on a grid
and asks how much of it lies further than half a swath from any line. That is how
the real bug in this module was found -- lines placed exactly on the boundary
vanished (the half-open crossing rule yields nothing for an edge lying along the
line) and the spacing stretched past the requested value, leaving 11.9% of a
rectangle unflown while the planner reported a tidy set of lines.
"""

import math

import numpy as np
import pytest

from agri_edge.geo.coverage import (
    CoveragePlan,
    FlightLine,
    best_heading,
    clip_line_to_polygon,
    coverage_gaps,
    plan_coverage,
)

# 400 m x 150 m, long axis east-west.
FIELD = np.array([[0.0, 0.0], [400.0, 0.0], [400.0, 150.0], [0.0, 150.0]])

# A U: horizontal lines must break into two runs across the notch.
U_FIELD = np.array([
    [0.0, 0.0], [300.0, 0.0], [300.0, 250.0], [200.0, 250.0],
    [200.0, 100.0], [100.0, 100.0], [100.0, 250.0], [0.0, 250.0],
])


def line_offsets(plan, heading_deg=0.0):
    """The perpendicular offset of each distinct pass."""
    idx = 1 if heading_deg == 0.0 else 0
    return sorted({round(ln.start[idx], 3) for ln in plan.lines})


class TestClipping:
    def test_a_convex_row_is_one_run(self):
        assert clip_line_to_polygon(75.0, FIELD, 0.0, 400.0) == [(0.0, 400.0)]

    def test_a_notch_splits_the_row(self):
        """The whole reason this returns a list. Flying the gap would record
        ground as covered that the camera never saw."""
        runs = clip_line_to_polygon(150.0, U_FIELD, 0.0, 300.0)
        assert len(runs) == 2
        assert runs[0] == (0.0, 100.0)
        assert runs[1] == (200.0, 300.0)

    def test_a_line_outside_the_polygon_yields_nothing(self):
        assert clip_line_to_polygon(500.0, FIELD, 0.0, 400.0) == []


class TestSpacing:
    def test_spacing_is_the_effective_swath_not_the_footprint(self):
        """37.5 m swath at 20% overlap must space lines 30 m apart."""
        plan = plan_coverage(FIELD, swath_m=37.5, overlap=0.2, heading_deg=0.0)
        offsets = line_offsets(plan)
        gaps = [b - a for a, b in zip(offsets, offsets[1:])]
        assert all(g == pytest.approx(30.0) for g in gaps), gaps

    def test_spacing_never_exceeds_the_request(self):
        """The bug: distributing n lines across the span gives span/(n-1), which
        is LARGER than the requested spacing and opens a gap between every pass."""
        for span in (100.0, 137.0, 151.0, 200.0):
            poly = np.array([[0.0, 0.0], [300.0, 0.0], [300.0, span], [0.0, span]])
            plan = plan_coverage(poly, swath_m=25.0, overlap=0.2)
            offsets = line_offsets(plan)
            for a, b in zip(offsets, offsets[1:]):
                assert b - a <= 20.0 + 1e-6, f"span {span}: spacing {b - a}"

    def test_no_line_sits_exactly_on_the_boundary(self):
        """A line along an edge produces no intersections and silently vanishes."""
        plan = plan_coverage(FIELD, swath_m=37.5, overlap=0.2)
        for off in line_offsets(plan):
            assert 0.0 < off < 150.0, off

    def test_overlap_of_zero_spaces_by_the_full_swath(self):
        plan = plan_coverage(FIELD, swath_m=30.0, overlap=0.0)
        offsets = line_offsets(plan)
        assert offsets[1] - offsets[0] == pytest.approx(30.0)


class TestCoverage:
    @pytest.mark.parametrize("heading", [0.0, 30.0, 45.0, 90.0, 135.0])
    def test_no_gaps_at_any_heading(self, heading):
        plan = plan_coverage(FIELD, swath_m=37.5, overlap=0.2, heading_deg=heading)
        assert coverage_gaps(plan, FIELD) == pytest.approx(0.0, abs=0.01)

    def test_a_concave_field_is_covered(self):
        plan = plan_coverage(U_FIELD, swath_m=30.0, overlap=0.2)
        assert coverage_gaps(plan, U_FIELD) < 0.03

    def test_too_little_overlap_leaves_gaps(self):
        """Proves the gap metric can actually fail, rather than always passing.

        A plan whose lines are spaced wider than the swath must show gaps -- if
        this returned 0% the metric would be measuring nothing.
        """
        wide = CoveragePlan(
            lines=[FlightLine((0.0, y), (400.0, y)) for y in (10.0, 140.0)],
            swath_m=20.0, overlap=0.0,
        )
        assert coverage_gaps(wide, FIELD) > 0.3

    def test_an_empty_plan_covers_nothing(self):
        assert coverage_gaps(CoveragePlan(), FIELD) == 1.0


class TestGeometry:
    def test_lines_serpentine(self):
        """Alternating direction, or the aircraft flies back across the field
        after every pass and roughly doubles the distance."""
        plan = plan_coverage(FIELD, swath_m=37.5, overlap=0.2, heading_deg=0.0)
        directions = [math.copysign(1, ln.end[0] - ln.start[0]) for ln in plan.lines]
        assert directions == [directions[0] * (-1) ** i for i in range(len(directions))]

    def test_turn_distance_is_counted_separately(self):
        plan = plan_coverage(FIELD, swath_m=37.5, overlap=0.2)
        assert plan.turn_distance_m > 0
        assert plan.total_distance_m == pytest.approx(
            plan.line_distance_m + plan.turn_distance_m)

    def test_area_is_the_field_not_the_bounding_box(self):
        assert plan_coverage(U_FIELD, 30.0).area_ha == pytest.approx(6.0, rel=0.01)

    def test_line_distance_is_at_least_the_field_width_times_passes(self):
        plan = plan_coverage(FIELD, swath_m=37.5, overlap=0.2, heading_deg=0.0)
        assert plan.line_distance_m == pytest.approx(400.0 * len(plan.lines))


class TestHeading:
    def test_best_heading_flies_the_long_axis(self):
        """A 400x150 field wants lines along the 400 m axis: fewer, longer passes
        and far fewer turns."""
        assert best_heading(FIELD, swath_m=37.5, overlap=0.2) in (0.0, 175.0, 5.0)

    def test_the_long_axis_really_is_cheaper(self):
        along = plan_coverage(FIELD, 37.5, 0.2, 0.0).total_distance_m
        across = plan_coverage(FIELD, 37.5, 0.2, 90.0).total_distance_m
        assert along < across

    def test_across_the_short_axis_costs_more_turns(self):
        assert (plan_coverage(FIELD, 37.5, 0.2, 90.0).turn_distance_m
                > plan_coverage(FIELD, 37.5, 0.2, 0.0).turn_distance_m)


class TestDuration:
    def test_duration_includes_a_turn_penalty(self):
        plan = plan_coverage(FIELD, swath_m=37.5, overlap=0.2)
        no_penalty = plan.estimate_duration_s(5.0, turn_penalty_s=0.0)
        with_penalty = plan.estimate_duration_s(5.0, turn_penalty_s=4.0)
        assert with_penalty > no_penalty
        assert with_penalty - no_penalty == pytest.approx(4.0 * (len(plan.lines) - 1))

    def test_zero_speed_is_rejected(self):
        with pytest.raises(ValueError):
            plan_coverage(FIELD, 37.5).estimate_duration_s(0.0)


class TestValidation:
    @pytest.mark.parametrize("kw", [{"swath_m": 0}, {"swath_m": -1}, {"overlap": 1.0},
                                    {"overlap": -0.1}])
    def test_nonsense_parameters_are_rejected(self, kw):
        args = {"swath_m": 30.0, **kw}
        with pytest.raises(ValueError):
            plan_coverage(FIELD, **args)

    def test_malformed_boundary_is_rejected(self):
        with pytest.raises(ValueError, match="metres|shape"):
            plan_coverage(np.zeros((2, 2)), 30.0)
