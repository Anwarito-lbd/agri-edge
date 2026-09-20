"""The airframe geometry, and the two claims in it that were wrong.

Most of these are ordinary arithmetic checks. The ones that earned their keep:

* the optics here must agree with `geo/georeference.py` and with
  `training/motion_budget.py`, because a disagreement puts every weed in the
  wrong place AND puts a leg in the corner of the frame;
* landing-gear azimuth was first claimed to be worth 40% of the clearance
  radius. For a symmetric four-leg gear it is worth nothing -- a rotation that
  takes two legs off the long axis puts the other two onto it;
* the worst rotation was then guessed as 45 deg. It is about 37 deg, the
  pyramid's own diagonal, and it costs 25%.

Both wrong claims came from reasoning about one leg. Both were caught by a test
that evaluates all four.
"""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mechanical"))

from airframe_spec import (  # noqa: E402
    Airframe,
    Battery,
    MassBudget,
    Propulsion,
    RotorGeometry,
    blade_pass_hz,
    clearance_radius_m,
    coverage_ha_per_h,
    endurance_min,
    field_of_view,
    gsd_m_per_px,
    ground_footprint_m,
    isolator_static_sag_mm,
    isolator_stiffness_n_per_mm,
    leg_positions,
    max_exposure_s,
    motor_positions,
    summary,
    worst_case_clearance_radius_m,
)


class TestOptics:
    def test_the_three_half_angles_are_ordered(self):
        """Short axis < long axis < diagonal. Quoting one FOV for a rectangular
        sensor is the shortcut that puts landing gear in the corners."""
        f = field_of_view()
        assert f.half_height_deg < f.half_width_deg < f.half_diagonal_deg

    def test_footprint_matches_the_pipeline(self):
        """46.8 x 35.1 m at 30 m. `geo/georeference.py` computes the same frame
        footprint from the same sensor; if these two ever disagree, one of them
        is putting detections in the wrong place."""
        w, h = ground_footprint_m(30.0)
        assert w == pytest.approx(46.8, abs=0.1)
        assert h == pytest.approx(35.1, abs=0.1)

    def test_gsd_matches_the_pipeline(self):
        assert gsd_m_per_px(30.0) * 100 == pytest.approx(1.155, abs=0.005)

    def test_clearance_is_a_rectangle_not_an_ellipse(self):
        """An ellipse through the same axes would UNDER-state the corners, which
        is the direction that puts a part in frame while the maths says fine."""
        drop = 0.2
        corner_az = math.degrees(math.atan2(
            math.tan(math.radians(field_of_view().half_height_deg)),
            math.tan(math.radians(field_of_view().half_width_deg))))
        assert clearance_radius_m(drop, corner_az) == pytest.approx(
            worst_case_clearance_radius_m(drop), rel=1e-6)

    def test_short_axis_is_the_cheapest_azimuth(self):
        drop = 0.2
        assert (clearance_radius_m(drop, 90.0)
                < clearance_radius_m(drop, 0.0)
                < worst_case_clearance_radius_m(drop))

    def test_a_single_item_saves_about_40_percent_on_the_short_axis(self):
        """The claim the module makes for ONE boom or antenna. It holds."""
        drop = 0.2
        saving = 1 - clearance_radius_m(drop, 90.0) / worst_case_clearance_radius_m(drop)
        assert 0.35 < saving < 0.45

    def test_clearance_scales_linearly_with_depth(self):
        assert clearance_radius_m(0.4, 30.0) == pytest.approx(
            2 * clearance_radius_m(0.2, 30.0))


class TestLegClearanceAzimuth:
    """The correction. Four legs 90 degrees apart cannot all dodge the long axis."""

    def test_rotating_the_sensor_never_helps(self):
        """A rotation that takes two legs off the long axis puts the other two
        on it, and the one it moves towards the corner gets worse faster than
        the one it moves towards the short axis gets better. Aligned is the
        strict minimum.

        The first version of this module evaluated only the nominal leg and so
        claimed a 40% saving that does not exist for a symmetric four."""
        aligned = Airframe(sensor_yaw_vs_gear_deg=0.0).leg_clearance()["required_m"]
        for yaw in range(1, 90):
            turned = Airframe(
                sensor_yaw_vs_gear_deg=float(yaw)
            ).leg_clearance()["required_m"]
            assert turned >= aligned - 1e-12, yaw

    def test_the_worst_rotation_is_the_corner_azimuth_not_45_degrees(self):
        """A second wrong guess, caught the same way. The pyramid is widest on
        its diagonal, which for a 4:3 sensor is about 37 deg -- so that is where
        a leg is most expensive, and 45 deg is already on the way back down."""
        fov = field_of_view()
        corner = math.degrees(math.atan2(
            math.tan(math.radians(fov.half_height_deg)),
            math.tan(math.radians(fov.half_width_deg))))
        assert 35.0 < corner < 39.0

        required = lambda y: Airframe(  # noqa: E731
            sensor_yaw_vs_gear_deg=y).leg_clearance()["required_m"]
        worst = max(range(0, 91), key=lambda y: required(float(y)))
        assert abs(worst - corner) <= 1.0
        assert required(float(worst)) > required(45.0)

    def test_the_penalty_for_rotating_is_about_a_quarter(self):
        aligned = Airframe(sensor_yaw_vs_gear_deg=0.0).leg_clearance()["required_m"]
        worst = max(Airframe(sensor_yaw_vs_gear_deg=float(y)
                             ).leg_clearance()["required_m"] for y in range(0, 91))
        assert 1.20 < worst / aligned < 1.30

    def test_aligned_gear_is_bound_by_the_long_axis(self):
        af = Airframe(sensor_yaw_vs_gear_deg=0.0)
        legs = af.leg_clearance()
        assert legs["required_m"] == pytest.approx(
            clearance_radius_m(af.lens_drop_below_legs_m, 0.0))

    def test_all_four_legs_are_evaluated(self):
        assert len(Airframe().leg_clearance()["required_per_leg_m"]) == 4

    def test_the_requirement_is_the_worst_leg_not_the_first(self):
        legs = Airframe(sensor_yaw_vs_gear_deg=20.0).leg_clearance()
        assert legs["required_m"] == pytest.approx(max(legs["required_per_leg_m"]))

    def test_short_legs_put_nothing_in_frame(self):
        """With the lens below the feet the pyramid never reaches them."""
        af = Airframe(leg_height_m=0.080)
        assert af.lens_drop_below_legs_m < 0
        assert af.leg_clearance()["in_frame"] is False

    def test_a_wide_enough_gear_clears_at_any_rotation(self):
        af = Airframe(leg_span_radius_m=0.260)
        for yaw in range(0, 91, 5):
            assert not Airframe(
                leg_span_radius_m=0.260, sensor_yaw_vs_gear_deg=float(yaw)
            ).leg_clearance()["in_frame"]
        assert af.leg_clearance()["margin_m"] > 0

    def test_a_narrow_gear_is_caught(self):
        assert Airframe(leg_span_radius_m=0.060).leg_clearance()["in_frame"] is True


class TestObstruction:
    def test_anything_above_the_lens_is_safe(self):
        out = Airframe().obstruction_check("antenna", 0.02, -0.05)
        assert out["above_lens"] is True and out["in_frame"] is False

    def test_the_boom_azimuth_decides_it(self):
        """The 40% that IS claimable: one item, put on the short axis."""
        af = Airframe()
        on_long = af.obstruction_check("boom", 0.13, 0.20, azimuth_deg=0.0)
        on_short = af.obstruction_check("boom", 0.13, 0.20, azimuth_deg=90.0)
        assert on_long["in_frame"] is True
        assert on_short["in_frame"] is False


class TestRotors:
    def test_tip_gap_from_wheelbase_and_prop(self):
        r = RotorGeometry(wheelbase_m=0.650, prop_diameter_in=15.0)
        assert r.adjacent_motor_spacing_m == pytest.approx(0.4596, abs=1e-3)
        assert r.tip_gap_m * 1000 == pytest.approx(79, abs=1)

    def test_overlapping_discs_report_a_negative_gap(self):
        """Silently clamping to zero would hide the one thing worth knowing."""
        assert RotorGeometry(wheelbase_m=0.450, prop_diameter_in=18.0).tip_gap_m < 0

    def test_largest_prop_that_fits_leaves_the_requested_gap(self):
        r = RotorGeometry(wheelbase_m=0.650)
        biggest = RotorGeometry(wheelbase_m=0.650, prop_diameter_in=r.max_prop_diameter_in())
        assert biggest.tip_gap_fraction == pytest.approx(0.10, abs=1e-6)

    def test_blade_pass_counts_blades_not_shafts(self):
        """Out by a factor of two is how a mount gets designed for a frequency
        that is not there."""
        assert blade_pass_hz(4600, blades=2) == pytest.approx(153.3, abs=0.1)
        assert blade_pass_hz(4600, blades=3) == 1.5 * blade_pass_hz(4600, blades=2)

    def test_motor_positions_sit_on_the_wheelbase_circle(self):
        af = Airframe()
        for x, y, _ in motor_positions(af):
            assert math.hypot(x, y) == pytest.approx(af.rotors.arm_radius_m)

    def test_legs_sit_between_the_arms(self):
        af = Airframe()
        arm_az = {45.0, 135.0, 225.0, 315.0}
        for x, y, _ in leg_positions(af):
            az = math.degrees(math.atan2(y, x)) % 360.0
            assert min(abs(az - a) for a in arm_az) > 40.0


class TestIsolator:
    def test_stiffness_reproduces_the_target_frequency(self):
        m, f, n = 0.32, 35.0, 4
        k = isolator_stiffness_n_per_mm(m, f, n)
        back = math.sqrt(k * n * 1000.0 / m) / (2 * math.pi)
        assert back == pytest.approx(f)

    def test_a_softer_mount_sags_further(self):
        soft = isolator_stiffness_n_per_mm(0.32, 15.0)
        stiff = isolator_stiffness_n_per_mm(0.32, 60.0)
        assert isolator_static_sag_mm(0.32, soft) > isolator_static_sag_mm(0.32, stiff)

    def test_nonsense_inputs_raise(self):
        for args in [(0.0, 35.0), (0.32, 0.0), (0.32, -5.0)]:
            with pytest.raises(ValueError):
                isolator_stiffness_n_per_mm(*args)

    def test_the_baseline_mount_clears_hover_blade_pass(self):
        v = Airframe().vibration()
        assert v["isolation_ratio"] >= 3.0 and v["adequate"] is True

    def test_frame_modes_are_compared_against_full_throttle(self):
        """Not hover. The frame has to stay clear at the top of the range."""
        v = Airframe().vibration()
        assert v["frame_mode_should_exceed_hz"] == v["blade_pass_full_hz"]


class TestMassAndFlight:
    def test_baseline_is_a_few_kilograms_not_a_few_hundred(self):
        assert 2.5 < MassBudget().total_kg < 5.0

    def test_nothing_has_been_weighed_yet(self):
        """Brief item 02. The day this stops being 100% is the day the number
        means something."""
        assert MassBudget().estimated_fraction == 1.0

    def test_groups_sum_to_the_total(self):
        m = MassBudget()
        assert sum(m.by_group().values()) == pytest.approx(m.total_g)

    def test_hover_fraction_and_thrust_to_weight_are_consistent(self):
        p, g = Propulsion(), MassBudget().total_g
        assert p.hover_throttle_fraction(g) == pytest.approx(1.0 / p.thrust_to_weight(g))

    def test_endurance_falls_when_the_payload_grows(self):
        b = Battery()
        light = endurance_min(b.usable_wh, Propulsion().hover_power_w(3000))
        heavy = endurance_min(b.usable_wh, Propulsion().hover_power_w(6000))
        assert heavy < light

    def test_never_plan_to_the_whole_pack(self):
        b = Battery()
        assert b.usable_wh < b.energy_wh

    def test_zero_power_raises_rather_than_returning_infinity(self):
        with pytest.raises(ValueError):
            endurance_min(100.0, 0.0)


class TestMission:
    def test_coverage_matches_the_published_figure(self):
        """67 ha/h at 30 m and 5 m/s with 20% overlap, as the progress report
        states. The report and this module must not drift apart."""
        assert coverage_ha_per_h(30.0, 5.0) == pytest.approx(67.4, abs=0.5)

    def test_overlap_is_paid_for_in_coverage(self):
        assert coverage_ha_per_h(30.0, 5.0, 0.40) < coverage_ha_per_h(30.0, 5.0, 0.20)

    def test_exposure_budget_matches_motion_budget(self):
        """2.3 ms at 30 m and 5 m/s -- the same figure training/motion_budget.py
        prints. Two implementations of one number must agree."""
        assert max_exposure_s(30.0, 5.0) * 1000 == pytest.approx(2.3, abs=0.1)

    def test_flying_faster_shortens_the_exposure_proportionally(self):
        assert max_exposure_s(30.0, 10.0) == pytest.approx(max_exposure_s(30.0, 5.0) / 2)

    def test_flying_higher_lengthens_it(self):
        """Higher means coarser ground sampling, so a given smear costs fewer
        pixels. This is why the altitude and speed limits are one decision."""
        assert max_exposure_s(60.0, 5.0) > max_exposure_s(30.0, 5.0)


class TestChecks:
    def test_the_baseline_design_passes_every_check(self):
        for label, ok, detail in Airframe().checks():
            assert ok, f"{label}: {detail}"

    def test_checks_fail_loudly_rather_than_clamping(self):
        """A design that quietly adjusts itself to pass teaches nobody anything."""
        bad = Airframe(rotors=RotorGeometry(wheelbase_m=0.450, prop_diameter_in=18.0))
        failed = [label for label, ok, _ in bad.checks() if not ok]
        assert "Propeller tip gap at least 10% of diameter" in failed

    def test_every_check_carries_a_number(self):
        for _, _, detail in Airframe().checks():
            assert any(ch.isdigit() for ch in detail)

    def test_summary_is_serialisable_and_complete(self):
        s = summary()
        for key in ("fov", "rotors", "mass_g", "performance", "legs", "vibration", "checks"):
            assert key in s
        assert len(s["checks"]) == len(Airframe().checks())
