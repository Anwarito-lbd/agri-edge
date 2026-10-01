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


class TestGeoJSONLoading:
    """Reading a field boundary from what mapping tools actually export."""

    LAT, LON = 49.8951, -97.1384
    D = 200.0 / 111320.0            # ~200 m, expressed in degrees of latitude

    def _ring(self):
        la, lo, d = self.LAT, self.LON, self.D
        return [[lo - d, la - d], [lo + d, la - d], [lo + d, la + d],
                [lo - d, la + d], [lo - d, la - d]]

    def _write(self, tmp_path, obj, name="f.geojson"):
        import json
        p = tmp_path / name
        p.write_text(json.dumps(obj), encoding="utf-8")
        return p

    def test_bare_polygon(self, tmp_path):
        from agri_edge.geo.geofence import load_boundary_geojson
        p = self._write(tmp_path, {"type": "Polygon", "coordinates": [self._ring()]})
        ring, _ = load_boundary_geojson(p)
        assert len(ring) == 4          # closing vertex dropped

    def test_feature_and_featurecollection_both_work(self, tmp_path):
        """All three shapes are what real exports look like."""
        from agri_edge.geo.geofence import load_boundary_geojson
        geom = {"type": "Polygon", "coordinates": [self._ring()]}
        feat = {"type": "Feature", "properties": {}, "geometry": geom}
        for obj in (feat, {"type": "FeatureCollection", "features": [feat]}):
            ring, _ = load_boundary_geojson(self._write(tmp_path, obj))
            assert len(ring) == 4

    def test_geojson_is_longitude_first(self, tmp_path):
        """[lon, lat]. Reversed puts the field in the wrong hemisphere."""
        from agri_edge.geo.geofence import load_boundary_geojson
        p = self._write(tmp_path, {"type": "Polygon", "coordinates": [self._ring()]})
        _, origin = load_boundary_geojson(p)
        assert origin[0] == pytest.approx(self.LAT - self.D)   # a latitude
        assert origin[1] == pytest.approx(self.LON - self.D)   # a longitude

    def test_area_reflects_the_longitude_cosine(self, tmp_path):
        """The reason everything downstream is in metres.

        The ring spans the same number of DEGREES north-south and east-west, but
        at 49.9 N a degree of longitude is only cos(49.9) = 0.64 as wide. So the
        field is 400 m x 258 m, not square -- which is invisible if you work in
        degrees and obvious once projected.
        """
        from agri_edge.geo.geofence import TreatmentGeofence, load_boundary_geojson
        ring, _ = load_boundary_geojson(
            self._write(tmp_path, {"type": "Polygon", "coordinates": [self._ring()]}))
        assert TreatmentGeofence(ring).area_ha == pytest.approx(10.3, rel=0.05)

    def test_a_line_is_rejected(self, tmp_path):
        """A treatment boundary must be an area."""
        from agri_edge.geo.geofence import load_boundary_geojson
        p = self._write(tmp_path, {"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
        with pytest.raises(ValueError, match="Polygon"):
            load_boundary_geojson(p)

    def test_a_degenerate_ring_is_rejected(self, tmp_path):
        from agri_edge.geo.geofence import load_boundary_geojson
        p = self._write(tmp_path, {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]})
        with pytest.raises(ValueError, match="at least 4"):
            load_boundary_geojson(p)

    def test_gating_near_the_edge(self, tmp_path):
        """Inside the field but within the buffer: fly yes, treat no."""
        from agri_edge.geo.geofence import (
            TreatmentGeofence, load_boundary_geojson, project_to_local,
        )
        ring, origin = load_boundary_geojson(
            self._write(tmp_path, {"type": "Polygon", "coordinates": [self._ring()]}))
        gf = TreatmentGeofence(ring, treatment_buffer_m=10.0)

        def at(lat, lon):
            e, n = project_to_local([lat], [lon], origin)[0]
            return gf.may_fly((e, n)), gf.may_treat((e, n))

        assert at(self.LAT, self.LON) == (True, True)                      # centre
        assert at(self.LAT - self.D + 5 / 111320, self.LON) == (True, False)   # 5 m in
        assert at(self.LAT - self.D + 50 / 111320, self.LON) == (True, True)   # 50 m in
        assert at(self.LAT - self.D - 20 / 111320, self.LON) == (False, False)  # outside


class TestHolesAndPositionError:
    """Audit 24 Sept, F14: holes in a treatment boundary were ignored, so
    treatment was permitted inside a slough or yard site cut out of the field,
    and a detection's own position error never reduced the buffer."""

    HOLE = np.array([[80.0, 30.0], [120.0, 30.0], [120.0, 70.0], [80.0, 70.0]])

    def _fence(self, buffer=10.0):
        from agri_edge.geo.geofence import TreatmentGeofence
        return TreatmentGeofence(FIELD, treatment_buffer_m=buffer, holes_m=[self.HOLE])

    def test_no_treatment_inside_a_hole(self):
        assert not self._fence().may_treat((100.0, 50.0))

    def test_no_treatment_within_the_buffer_of_a_hole(self):
        assert not self._fence().may_treat((125.0, 50.0))     # 5 m outside the hole

    def test_treatment_clear_of_the_hole_is_allowed(self):
        assert self._fence().may_treat((40.0, 50.0))

    def test_flight_over_a_hole_is_fine(self):
        assert self._fence().may_fly((100.0, 50.0))

    def test_position_error_comes_out_of_the_buffer(self):
        fence = self._fence()
        point = (40.0, 14.0)                                  # 14 m from the edge, buffer 10
        assert fence.may_treat(point, position_error_m=3.0)
        assert not fence.may_treat(point, position_error_m=5.0)

    def test_loader_keeps_holes(self, tmp_path):
        import json

        from agri_edge.geo.geofence import load_treatment_boundary

        la, lo, d = 49.9, -97.1, 200.0 / 111320.0
        outer = [[lo - d, la - d], [lo + d, la - d], [lo + d, la + d], [lo - d, la + d], [lo - d, la - d]]
        h = d / 4
        hole = [[lo - h, la - h], [lo + h, la - h], [lo + h, la + h], [lo - h, la + h], [lo - h, la - h]]
        p = tmp_path / "f.geojson"
        p.write_text(json.dumps({"type": "Polygon", "coordinates": [outer, hole]}), encoding="utf-8")
        ring, holes, _ = load_treatment_boundary(p)
        assert len(ring) == 4 and len(holes) == 1 and len(holes[0]) == 4


def test_pipeline_refuses_treatment_inside_a_boundary_hole(tmp_path):
    """End to end through the runner's fence loading."""
    import json

    from agri_edge.config import Config
    from agri_edge.inference.engine import Detection
    from agri_edge.pipeline.runner import Pipeline

    la, lo, d = 50.0, -104.0, 300.0 / 111320.0
    outer = [[lo - 2 * d, la - d], [lo + 2 * d, la - d], [lo + 2 * d, la + d],
             [lo - 2 * d, la + d], [lo - 2 * d, la - d]]
    h = d / 3
    hole = [[lo - h, la - h], [lo + h, la - h], [lo + h, la + h], [lo - h, la + h], [lo - h, la - h]]
    p = tmp_path / "zone.geojson"
    p.write_text(json.dumps({"type": "Polygon", "coordinates": [outer, hole]}), encoding="utf-8")

    cfg = Config()
    cfg.treatment_zone.boundary_geojson = p
    pipe = Pipeline.__new__(Pipeline)
    pipe.cfg = cfg
    in_hole = Detection("weed", 0.9, (0, 0, 1, 1), validated_locally=True)
    in_hole.lat, in_hole.lon, in_hole.position_error_m = la, lo, 1.0
    clear = Detection("weed", 0.9, (0, 0, 1, 1), validated_locally=True)
    clear.lat, clear.lon, clear.position_error_m = la, lo + 1.5 * d, 1.0
    pipe._check_treatment_zone([in_hole, clear])
    assert in_hole.in_treatment_zone is False
    assert clear.in_treatment_zone is True
