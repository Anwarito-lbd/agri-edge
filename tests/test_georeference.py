"""Tests for projecting a detection's pixels onto the ground.

Most of these check the maths against a value computed by hand from the
geometry, not against whatever the code returns. Two deserve calling out:

* **The tilt test.** The naive "GSD times pixel offset" shortcut is correct only
  at exactly zero tilt. `test_tilt_moves_the_frame_centre` shows what the
  shortcut would miss at 10 degrees — the QA gate's *pass* threshold — which is
  the whole reason this uses ray-plane intersection instead.
* **The refusal tests.** A pixel aimed at the horizon, or a missing altitude, has
  no ground position. Returning a plausible number there would be fabrication,
  so these assert that nothing is returned at all.
"""

import math

import pytest

from agri_edge.geo.geofence import project_to_local
from agri_edge.geo.georeference import (
    IMX708,
    CameraIntrinsics,
    CameraMount,
    frame_footprint,
    georeference_detections,
    ground_error_estimate_m,
    local_to_geographic,
    off_nadir_deg,
    pixel_ray_ned,
    pixel_to_ground,
)
from agri_edge.inference.engine import Detection
from agri_edge.telemetry.mavlink_link import TelemetrySnapshot

LAT, LON, ALT = 49.8951, -97.1384, 30.0
M_PER_DEG_LAT = 111_320.0


def north_east_m(point, origin=(LAT, LON)):
    """(lat, lon) -> metres north/east of the origin."""
    east, north = project_to_local([point[0]], [point[1]], origin)[0]
    return north, east


class TestIntrinsics:
    # Until 24 Sept 2026 these pinned 7.4 mm across 4056 px: the IMX708's
    # DIAGONAL and the HQ camera's resolution. The tests agreed with the code
    # because both came from the same wrong numbers; the datasheet FOV did not
    # (66 deg horizontal, 75 deg diagonal -- the old HFOV here was 76).

    def test_focal_px_is_derived_from_the_datasheet_numbers(self):
        # 4.74 mm focal / 6.45 mm active width across 4608 px (1.4 um pixels)
        assert IMX708.focal_px == pytest.approx(4.74 * 4608 / 6.45)
        assert IMX708.focal_px == pytest.approx(4.74 / 0.0014, rel=0.001)

    def test_gsd_matches_gsd_calculator(self):
        """0.886 cm/px at 30 m (the old, wrong figure was 1.155)."""
        assert IMX708.gsd_m(30.0) * 100 == pytest.approx(0.886, abs=0.001)

    def test_hfov_is_close_to_the_datasheet(self):
        # Datasheet: 66 deg. 68.5 from nominal focal length; the difference is
        # the lens's real focal length, which a checkerboard calibration fixes.
        assert IMX708.hfov_deg == pytest.approx(68.5, abs=0.5)

    @pytest.mark.parametrize("kw", [
        {"sensor_width_mm": 0}, {"focal_length_mm": -1}, {"image_width_px": 0},
    ])
    def test_nonsense_intrinsics_are_rejected(self, kw):
        base = dict(sensor_width_mm=7.4, focal_length_mm=4.74,
                    image_width_px=4056, image_height_px=3040)
        base.update(kw)
        with pytest.raises(ValueError):
            CameraIntrinsics(**base)


class TestNadir:
    def test_centre_pixel_lands_directly_below(self):
        got = pixel_to_ground(0.5, 0.5, IMX708, LAT, LON, ALT, yaw_deg=0.0)
        n, e = north_east_m(got)
        assert n == pytest.approx(0.0, abs=0.01)
        assert e == pytest.approx(0.0, abs=0.01)

    def test_footprint_matches_the_analytic_ground_width(self):
        """(sensor/focal) * altitude, independently computed."""
        fp = frame_footprint(IMX708, LAT, LON, ALT, yaw_deg=0.0)
        ne = [north_east_m(p) for p in fp]
        width = max(e for _, e in ne) - min(e for _, e in ne)
        height = max(n for n, _ in ne) - min(n for n, _ in ne)
        expect_w = (6.45 / 4.74) * ALT
        assert width == pytest.approx(expect_w, rel=0.01)
        assert height == pytest.approx(expect_w * 2592 / 4608, rel=0.01)

    def test_top_of_frame_is_forward_when_heading_north(self):
        """Top of image points at the nose; nose points north."""
        n, e = north_east_m(pixel_to_ground(0.5, 0.0, IMX708, LAT, LON, ALT, yaw_deg=0.0))
        assert n > 5.0, "top of frame must land NORTH of the aircraft"
        assert e == pytest.approx(0.0, abs=0.1)

    def test_right_of_frame_is_east_when_heading_north(self):
        n, e = north_east_m(pixel_to_ground(1.0, 0.5, IMX708, LAT, LON, ALT, yaw_deg=0.0))
        assert e > 5.0, "right of frame must land EAST of the aircraft"
        assert n == pytest.approx(0.0, abs=0.1)

    def test_heading_east_rotates_the_frame(self):
        """Same pixel, aircraft turned 90 deg: forward is now east."""
        n, e = north_east_m(pixel_to_ground(0.5, 0.0, IMX708, LAT, LON, ALT, yaw_deg=90.0))
        assert e > 5.0
        assert n == pytest.approx(0.0, abs=0.1)

    def test_scale_is_linear_in_altitude(self):
        _, e30 = north_east_m(pixel_to_ground(1.0, 0.5, IMX708, LAT, LON, 30.0, 0.0))
        _, e60 = north_east_m(pixel_to_ground(1.0, 0.5, IMX708, LAT, LON, 60.0, 0.0))
        assert e60 == pytest.approx(2 * e30, rel=1e-6)


class TestTilt:
    def test_tilt_moves_the_frame_centre(self):
        """The reason this is not "GSD times pixel offset".

        A 10 degree pitch at 30 m slides the centre of the frame 30*tan(10) =
        5.29 m along the ground. The naive shortcut says the centre pixel is
        always directly below the aircraft, so it would be 5.3 m wrong -- on a
        frame the QA gate passes, since its threshold is 10 degrees.
        """
        n, e = north_east_m(
            pixel_to_ground(0.5, 0.5, IMX708, LAT, LON, ALT, yaw_deg=0.0, pitch_deg=10.0)
        )
        assert n == pytest.approx(ALT * math.tan(math.radians(10.0)), abs=0.05)
        assert n == pytest.approx(5.29, abs=0.05)
        assert e == pytest.approx(0.0, abs=0.05)

    def test_roll_right_swings_the_view_LEFT(self):
        """The sign that is easy to get backwards, so it is stated explicitly.

        Positive roll drops the right wing. That tilts the aircraft's *belly* --
        and with it a belly-mounted camera's boresight -- to the LEFT. Roll right
        90 degrees and the camera is looking due west while still heading north.

        So a +10 degree roll while heading north displaces the frame centre 5.29 m
        WEST, not east. Getting this backwards mirrors an entire flight about the
        track, which looks perfectly plausible frame by frame.
        """
        n, e = north_east_m(
            pixel_to_ground(0.5, 0.5, IMX708, LAT, LON, ALT, yaw_deg=0.0, roll_deg=10.0)
        )
        assert e == pytest.approx(-ALT * math.tan(math.radians(10.0)), abs=0.05)
        assert e < 0, "positive roll must displace WEST when heading north"
        assert n == pytest.approx(0.0, abs=0.05)

    def test_pitch_up_swings_the_view_FORWARD(self):
        """The companion sign. Nose up tilts the belly forward, so a +10 degree
        pitch heading north displaces NORTH. Opposite handedness to roll, which
        is why both are pinned separately."""
        n, e = north_east_m(
            pixel_to_ground(0.5, 0.5, IMX708, LAT, LON, ALT, yaw_deg=0.0, pitch_deg=10.0)
        )
        assert n > 0, "positive pitch must displace NORTH when heading north"
        assert n == pytest.approx(ALT * math.tan(math.radians(10.0)), abs=0.05)

    def test_tilt_composes_with_heading(self):
        """Pitched forward while heading east must displace east, not north."""
        n, e = north_east_m(
            pixel_to_ground(0.5, 0.5, IMX708, LAT, LON, ALT, yaw_deg=90.0, pitch_deg=10.0)
        )
        assert e == pytest.approx(ALT * math.tan(math.radians(10.0)), abs=0.05)
        assert n == pytest.approx(0.0, abs=0.05)

    def test_a_roll_and_pitch_of_equal_size_are_perpendicular(self):
        """Independent check that the two axes are not being conflated."""
        _, e_roll = north_east_m(
            pixel_to_ground(0.5, 0.5, IMX708, LAT, LON, ALT, 0.0, roll_deg=10.0))
        n_pitch, _ = north_east_m(
            pixel_to_ground(0.5, 0.5, IMX708, LAT, LON, ALT, 0.0, pitch_deg=10.0))
        assert abs(e_roll) == pytest.approx(abs(n_pitch), abs=0.02)

    def test_a_ray_above_the_horizon_is_refused(self):
        """Extreme tilt puts part of the frame on the sky. There is no ground
        position, and inventing one would be fabrication."""
        with pytest.raises(ValueError, match="horizon"):
            pixel_to_ground(0.5, 0.0, IMX708, LAT, LON, ALT, yaw_deg=0.0, pitch_deg=80.0)

    @pytest.mark.parametrize("alt", [0.0, -5.0])
    def test_nonpositive_altitude_is_refused(self, alt):
        with pytest.raises(ValueError, match="altitude_agl_m"):
            pixel_to_ground(0.5, 0.5, IMX708, LAT, LON, alt, yaw_deg=0.0)


class TestMount:
    def test_ninety_degree_mount_swaps_the_axes(self):
        """A camera bolted on sideways. Getting this wrong rotates a whole flight."""
        straight = north_east_m(
            pixel_to_ground(0.5, 0.0, IMX708, LAT, LON, ALT, 0.0, mount=CameraMount(0.0))
        )
        rotated = north_east_m(
            pixel_to_ground(0.5, 0.0, IMX708, LAT, LON, ALT, 0.0, mount=CameraMount(90.0))
        )
        assert straight[0] > 5.0 and abs(straight[1]) < 0.1   # north
        assert rotated[1] > 5.0 and abs(rotated[0]) < 0.1     # east


class TestErrorBudget:
    def test_error_is_zero_directly_below(self):
        """Nadir: an elevation error slides you up and down, never sideways."""
        assert ground_error_estimate_m(0.5, 0.5, IMX708, ALT) == pytest.approx(0.0, abs=1e-9)

    def test_error_grows_toward_the_frame_corner(self):
        centre = ground_error_estimate_m(0.5, 0.5, IMX708, ALT)
        corner = ground_error_estimate_m(0.0, 0.0, IMX708, ALT)
        assert corner > centre
        # ~38 deg off-nadir at the corner (half the 75-76 deg diagonal FOV)
        assert corner == pytest.approx(2.0 * math.tan(math.radians(38.0)), abs=0.1)

    def test_error_scales_with_terrain_uncertainty(self):
        a = ground_error_estimate_m(0.0, 0.0, IMX708, ALT, terrain_uncertainty_m=2.0)
        b = ground_error_estimate_m(0.0, 0.0, IMX708, ALT, terrain_uncertainty_m=4.0)
        assert b == pytest.approx(2 * a)

    def test_off_nadir_is_zero_at_centre_and_large_at_corner(self):
        assert off_nadir_deg(0.5, 0.5, IMX708) == pytest.approx(0.0, abs=1e-6)
        assert off_nadir_deg(0.0, 0.0, IMX708) == pytest.approx(38.0, abs=0.5)


class TestRoundTrip:
    def test_local_to_geographic_inverts_project_to_local(self):
        for north, east in [(0, 0), (100, -50), (-2500, 1800)]:
            lat, lon = local_to_geographic(north, east, (LAT, LON))
            back_e, back_n = project_to_local([lat], [lon], (LAT, LON))[0]
            assert back_n == pytest.approx(north, abs=0.01)
            assert back_e == pytest.approx(east, abs=0.01)

    def test_ray_is_unit_length(self):
        r = pixel_ray_ned(0.1, 0.9, IMX708, 5.0, -3.0, 40.0)
        assert float((r ** 2).sum()) == pytest.approx(1.0)


class TestGeoreferenceDetections:
    @staticmethod
    def _telem(**kw):
        base = dict(lat=LAT, lon=LON, alt_rel_m=ALT, yaw_deg=0.0,
                    roll_deg=0.0, pitch_deg=0.0)
        base.update(kw)
        return TelemetrySnapshot(**base)

    @staticmethod
    def _det(bbox=(0.45, 0.45, 0.55, 0.55)):
        return Detection(label="kochia", confidence=0.8, bbox=bbox)

    def test_detection_gains_a_position(self):
        d = self._det()
        georeference_detections([d], IMX708, self._telem())
        assert d.has_position
        assert d.lat == pytest.approx(LAT, abs=1e-4)

    def test_uses_the_bottom_edge_not_the_centre(self):
        """An object stands on the ground at the bottom of its box.

        Off-nadir, the box centre is partway up the object and projects past it.
        At nadir the two agree, so the difference shows up only when tilted --
        which is exactly when it matters.
        """
        d = self._det(bbox=(0.4, 0.2, 0.6, 0.8))
        georeference_detections([d], IMX708, self._telem())
        bottom = pixel_to_ground(0.5, 0.8, IMX708, LAT, LON, ALT, 0.0)
        assert d.lat == pytest.approx(bottom[0], abs=1e-9)

    def test_position_error_is_recorded(self):
        d = self._det(bbox=(0.0, 0.0, 0.05, 0.05))   # frame corner
        georeference_detections([d], IMX708, self._telem())
        assert d.position_error_m > 0.5

    def test_no_telemetry_means_no_position_not_a_guess(self):
        d = self._det()
        georeference_detections([d], IMX708, None)
        assert not d.has_position and d.lat is None

    def test_missing_altitude_records_why(self):
        d = self._det()
        georeference_detections([d], IMX708, self._telem(alt_rel_m=None))
        assert not d.has_position
        assert "altitude" in d.geo_error

    @pytest.mark.parametrize("field,word", [("yaw_deg", "heading"),
                                            ("roll_deg", "roll"),
                                            ("pitch_deg", "pitch")])
    def test_missing_attitude_is_refused_not_assumed(self, field, word):
        """Audit 24 Sept, F9: a missing heading became 0 (north) and missing
        roll/pitch became level, producing a rotated but plausible map."""
        d = self._det(bbox=(0.1, 0.1, 0.2, 0.2))
        georeference_detections([d], IMX708, self._telem(**{field: None}))
        assert not d.has_position
        assert word in d.geo_error

    def test_a_detection_on_the_sky_is_left_unplaced_with_a_reason(self):
        d = self._det(bbox=(0.4, 0.0, 0.6, 0.02))
        georeference_detections([d], IMX708, self._telem(pitch_deg=80.0))
        assert not d.has_position
        assert "horizon" in d.geo_error

    def test_sidecar_carries_position_only_when_it_exists(self):
        placed, unplaced = self._det(), self._det()
        georeference_detections([placed], IMX708, self._telem())
        georeference_detections([unplaced], IMX708, None)
        assert "lat" in placed.to_dict() and "lon" in placed.to_dict()
        assert "lat" not in unplaced.to_dict()

    def test_georeferencing_does_not_touch_the_safety_gate(self):
        """Knowing where something is says nothing about being allowed to spray it."""
        d = self._det()
        georeference_detections([d], IMX708, self._telem())
        assert d.validated_locally is False
        assert d.may_drive_treatment is False
