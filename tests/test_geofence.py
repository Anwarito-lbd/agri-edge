"""Tests for the flight/treatment geofence split and the spray rate maths.

The property that matters most is the asymmetry: **everywhere treatment is
allowed, flight must also be allowed, and the reverse must not hold.** If those
two boundaries ever coincide, the safety argument for having two of them is gone
and a headland turn sprays past the field edge.

The rate equation is checked against the worked example in the research report
rather than against whatever the code currently returns.
"""

import math

import numpy as np
import pytest

from agri_edge.geo.geofence import (
    TreatmentGeofence,
    coverage_rate_ha_h,
    distance_to_boundary_m,
    point_in_polygon,
    polygon_area_m2,
    project_to_local,
    shrink_polygon,
    spray_flow_l_min,
)

# A 200 m x 100 m rectangular field, counter-clockwise, in local metres.
FIELD = np.array([[0.0, 0.0], [200.0, 0.0], [200.0, 100.0], [0.0, 100.0]])


class TestProjection:
    def test_origin_maps_to_zero(self):
        out = project_to_local([49.8951], [-97.1384], (49.8951, -97.1384))
        assert out[0] == pytest.approx([0.0, 0.0], abs=1e-6)

    def test_one_degree_of_latitude_is_about_111_km(self):
        out = project_to_local([50.0], [-97.0], (49.0, -97.0))
        assert out[0, 1] == pytest.approx(111_195, rel=0.01)

    def test_longitude_shrinks_with_latitude(self):
        """The whole reason not to buffer in degrees.

        A degree of longitude is ~111 km at the equator and ~72 km on the
        Canadian Prairies. A buffer specified in degrees would be a different
        distance in each direction, and a different distance on every farm.
        """
        equator = project_to_local([0.0], [1.0], (0.0, 0.0))[0, 0]
        prairie = project_to_local([50.0], [1.0], (50.0, 0.0))[0, 0]
        assert prairie < equator
        assert prairie / equator == pytest.approx(math.cos(math.radians(50)), rel=1e-6)

    def test_north_east_signs(self):
        out = project_to_local([49.9], [-97.0], (49.8, -97.1))
        assert out[0, 0] > 0 and out[0, 1] > 0   # east and north positive


class TestPolygonGeometry:
    def test_area_of_known_rectangle(self):
        assert abs(polygon_area_m2(FIELD)) == pytest.approx(20_000.0)

    def test_area_sign_follows_winding(self):
        assert polygon_area_m2(FIELD) > 0
        assert polygon_area_m2(FIELD[::-1]) < 0

    def test_containment(self):
        assert point_in_polygon((100.0, 50.0), FIELD) is True
        assert point_in_polygon((-1.0, 50.0), FIELD) is False
        assert point_in_polygon((100.0, 150.0), FIELD) is False

    @pytest.mark.parametrize(
        "point,expected",
        [((100.0, 50.0), 50.0), ((10.0, 50.0), 10.0), ((100.0, 5.0), 5.0),
         ((100.0, 150.0), 50.0)],   # outside: unsigned distance to the edge
    )
    def test_distance_to_boundary(self, point, expected):
        assert distance_to_boundary_m(point, FIELD) == pytest.approx(expected)

    def test_duplicated_vertex_does_not_produce_nan(self):
        """A zero-length edge divides by zero and a nan poisons the minimum."""
        poly = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
        d = distance_to_boundary_m((5.0, 5.0), poly)
        assert math.isfinite(d) and d == pytest.approx(5.0)

    def test_shrink_reduces_area(self):
        inner = shrink_polygon(FIELD, 10.0)
        assert abs(polygon_area_m2(inner)) < abs(polygon_area_m2(FIELD))
        # 180 x 80 = 14,400
        assert abs(polygon_area_m2(inner)) == pytest.approx(14_400.0, rel=0.02)

    def test_zero_buffer_is_identity(self):
        assert np.allclose(shrink_polygon(FIELD, 0.0), FIELD)


class TestTreatmentGeofence:
    def test_treatment_is_strictly_inside_flight(self):
        """The core invariant. If these ever coincide, two fences buy nothing."""
        fence = TreatmentGeofence(FIELD, treatment_buffer_m=10.0)
        near_edge = (100.0, 3.0)
        assert fence.may_fly(near_edge) is True
        assert fence.may_treat(near_edge) is False

    def test_centre_permits_both(self):
        fence = TreatmentGeofence(FIELD, treatment_buffer_m=10.0)
        assert fence.may_fly((100.0, 50.0)) is True
        assert fence.may_treat((100.0, 50.0)) is True

    def test_treatment_implies_flight_everywhere_on_a_grid(self):
        """Exhaustive: no point may ever be treatable but not flyable."""
        fence = TreatmentGeofence(FIELD, treatment_buffer_m=15.0)
        for x in np.linspace(-20, 220, 25):
            for y in np.linspace(-20, 120, 15):
                if fence.may_treat((x, y)):
                    assert fence.may_fly((x, y)), f"({x}, {y}) treatable but not flyable"

    def test_outside_the_field_is_never_treatable(self):
        fence = TreatmentGeofence(FIELD, treatment_buffer_m=10.0)
        for p in [(-5.0, 50.0), (250.0, 50.0), (100.0, -5.0), (100.0, 200.0)]:
            assert fence.may_treat(p) is False
            assert fence.may_fly(p) is False

    def test_margin_is_negative_before_the_boolean_flips(self):
        """A planner needs lead time to close a valve, not a cliff edge."""
        fence = TreatmentGeofence(FIELD, treatment_buffer_m=10.0)
        assert fence.treatment_margin_m((100.0, 50.0)) == pytest.approx(40.0)
        assert fence.treatment_margin_m((100.0, 10.0)) == pytest.approx(0.0)
        assert fence.treatment_margin_m((100.0, 4.0)) == pytest.approx(-6.0)
        assert fence.treatment_margin_m((100.0, -5.0)) < 0

    def test_zero_buffer_makes_the_two_fences_agree_inside(self):
        """Documents the degenerate case rather than pretending it is prevented."""
        fence = TreatmentGeofence(FIELD, treatment_buffer_m=0.0)
        assert fence.may_treat((100.0, 1.0)) is True

    def test_negative_buffer_is_rejected(self):
        with pytest.raises(ValueError, match="inverts"):
            TreatmentGeofence(FIELD, treatment_buffer_m=-5.0)

    @pytest.mark.parametrize("bad", [np.zeros((2, 2)), np.zeros((4, 3)), np.zeros(4)])
    def test_malformed_boundary_is_rejected(self, bad):
        with pytest.raises(ValueError, match="METRES|shape"):
            TreatmentGeofence(bad)

    def test_area_reported_in_hectares(self):
        assert TreatmentGeofence(FIELD).area_ha == pytest.approx(2.0)


class TestSprayMaths:
    def test_matches_the_reports_worked_example(self):
        """20 L/ha at 8 m/s with an 8 m swath = 7.68 L/min."""
        assert spray_flow_l_min(20.0, 8.0, 8.0) == pytest.approx(7.68)

    def test_flow_scales_linearly(self):
        base = spray_flow_l_min(20.0, 5.0, 8.0)
        assert spray_flow_l_min(40.0, 5.0, 8.0) == pytest.approx(2 * base)
        assert spray_flow_l_min(20.0, 10.0, 8.0) == pytest.approx(2 * base)

    def test_zero_speed_means_zero_flow(self):
        """Stationary means no ground is being covered, so no product is due."""
        assert spray_flow_l_min(20.0, 0.0, 8.0) == 0.0

    @pytest.mark.parametrize("args", [(-1.0, 5.0, 8.0), (20.0, -1.0, 8.0), (20.0, 5.0, -1.0)])
    def test_negative_inputs_are_rejected(self, args):
        with pytest.raises(ValueError):
            spray_flow_l_min(*args)

    def test_coverage_matches_the_hand_computed_rate(self):
        """37.5 m effective swath at 5 m/s = 67.5 ha/h, as in the airframe brief."""
        assert coverage_rate_ha_h(5.0, 46.8, overlap=0.2) == pytest.approx(67.4, rel=0.01)

    def test_overlap_reduces_coverage(self):
        assert coverage_rate_ha_h(5.0, 40.0, 0.3) < coverage_rate_ha_h(5.0, 40.0, 0.0)

    def test_full_overlap_is_rejected(self):
        with pytest.raises(ValueError):
            coverage_rate_ha_h(5.0, 40.0, overlap=1.0)
