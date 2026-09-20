"""The airframe, as numbers the software already depends on.

WHY THIS IS CODE AND NOT A DRAWING
----------------------------------
`docs/progress-report-and-airframe-brief.html` states twelve mechanical
requirements, and every one of them came out of something the software measures
or enforces. A drawing of the aircraft that is not derived from those numbers can
drift away from them silently -- someone shortens a leg, and six months later a
fifth of every frame has a landing gear in the corner.

So the geometry lives here, one module, and both the Blender model
(`mechanical/blender_airframe.py`) and the interactive view are generated from
it. Change a number here and the model changes with it.

THE THREE THINGS THIS ACTUALLY DECIDES
--------------------------------------
1. **What the camera can see past the aircraft.** Brief item 09. The lens looks
   through a rectangular pyramid, not a cone: 30.3 deg off nadir along the short
   axis, 38.0 deg along the long one, 44.3 deg at the corners.

   For a SINGLE thing sticking down -- a boom, an antenna, the rangefinder --
   azimuth is worth 40% of the clearance radius, so put it on the short axis.

   For a symmetric FOUR-leg gear it is worth nothing at all: a rotation that
   takes two legs off the long axis puts the other two onto it. Aligned with
   the sensor axes is the strict minimum, and turning the sensor costs up to
   25% at about 37 deg, which is where the pyramid's diagonal lies. Both of
   those were guessed wrong first -- 40% saving, then 45 deg as the worst case
   -- and both were caught by evaluating all four legs instead of one.

2. **Whether the propellers fit.** Tip gap falls straight out of wheelbase and
   prop diameter, and a quad whose discs nearly touch loses thrust and gains
   vibration at exactly the frequency the camera mount is trying to reject.

3. **Whether the mount rejects the propellers.** Brief item 04. Blade-pass
   frequency is prop RPM over 60 times the blade count, and the isolator has to
   sit well below it. This is the one mechanical failure that looks like a
   software bug: sharp on the bench, smeared only in the air, only at some
   throttle settings.

WHAT THIS IS NOT
----------------
It is not a structural analysis. Nothing here says the arms are stiff enough or
the plate will not crack -- that is a real engineering question and this module
does not pretend to answer it. It sizes and checks *clearances, budgets and
frequencies*, which are the parts the software has an opinion about.

Every mass below is an ESTIMATE until the part is on a scale. Brief item 02 is
explicit about that, and `MassBudget.weighed` tracks which ones have been.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Optics -- these come from the sensor datasheet, and are the same constants
# src/agri_edge/geo/georeference.py projects detections with. A disagreement
# between the two would put every weed in the wrong place AND put a leg in the
# frame, so they are stated once and imported.
# ---------------------------------------------------------------------------

SENSOR_WIDTH_MM = 7.4       # IMX708, Pi Camera Module 3
FOCAL_LENGTH_MM = 4.74
IMAGE_WIDTH_PX = 4056
IMAGE_HEIGHT_PX = 3040


@dataclass(frozen=True)
class FieldOfView:
    """Half-angles of the viewing pyramid, in degrees, measured from nadir.

    Three different numbers because the sensor is a rectangle. Quoting one FOV
    for a camera is the shortcut that puts landing gear in the corners.
    """

    half_width_deg: float      # along the image's long axis
    half_height_deg: float     # along the image's short axis
    half_diagonal_deg: float   # the corners -- the worst case


def field_of_view(
    sensor_width_mm: float = SENSOR_WIDTH_MM,
    focal_length_mm: float = FOCAL_LENGTH_MM,
    image_width_px: int = IMAGE_WIDTH_PX,
    image_height_px: int = IMAGE_HEIGHT_PX,
) -> FieldOfView:
    """Half-angles from the sensor dimensions. Square pixels assumed."""
    sensor_height_mm = sensor_width_mm * image_height_px / image_width_px
    hw = math.atan(sensor_width_mm / 2.0 / focal_length_mm)
    hh = math.atan(sensor_height_mm / 2.0 / focal_length_mm)
    hd = math.atan(
        math.hypot(sensor_width_mm / 2.0, sensor_height_mm / 2.0) / focal_length_mm
    )
    return FieldOfView(math.degrees(hw), math.degrees(hh), math.degrees(hd))


def clearance_radius_m(
    drop_below_lens_m: float, azimuth_deg: float, fov: FieldOfView | None = None
) -> float:
    """Radius at which the view pyramid sits, `drop` metres below the lens.

    Anything closer to the optical axis than this, at that azimuth and that
    depth, is IN THE PICTURE. Legs, booms, antennas, wires, the rangefinder --
    all of them.

    `azimuth_deg` is measured in the image's own frame: 0 along the long axis,
    90 along the short axis. The pyramid is widest at its corners (about 37 deg
    azimuth for a 4:3 sensor, not 45) and narrowest along the short axis, and
    the difference between those two placements is over 40% of the radius.

    That 40% is claimable for ONE item -- a boom, an antenna, the rangefinder --
    by putting it on the short axis, and `camera_geometry.yaw_offset_deg` in
    config/pi.yaml makes the rotation free. It is NOT claimable for a symmetric
    four-leg gear, where a rotation that moves two legs off the long axis moves
    the other two onto it. See `Airframe.leg_clearance`.
    """
    fov = fov or field_of_view()
    a = drop_below_lens_m * math.tan(math.radians(fov.half_width_deg))
    b = drop_below_lens_m * math.tan(math.radians(fov.half_height_deg))
    c = math.cos(math.radians(azimuth_deg))
    s = math.sin(math.radians(azimuth_deg))
    # Distance from the axis to the rectangle's edge along this bearing. The
    # rectangle, not an ellipse -- an ellipse would under-state the corners.
    along_w = abs(a / c) if abs(c) > 1e-12 else math.inf
    along_h = abs(b / s) if abs(s) > 1e-12 else math.inf
    return min(along_w, along_h)


def worst_case_clearance_radius_m(
    drop_below_lens_m: float, fov: FieldOfView | None = None
) -> float:
    """The corner of the pyramid -- what a leg must clear at an unknown azimuth."""
    fov = fov or field_of_view()
    return drop_below_lens_m * math.tan(math.radians(fov.half_diagonal_deg))


def ground_footprint_m(agl_m: float, fov: FieldOfView | None = None) -> tuple[float, float]:
    """(width, height) of one frame on the ground. The swath, before overlap."""
    fov = fov or field_of_view()
    return (
        2.0 * agl_m * math.tan(math.radians(fov.half_width_deg)),
        2.0 * agl_m * math.tan(math.radians(fov.half_height_deg)),
    )


def gsd_m_per_px(agl_m: float, image_width_px: int = IMAGE_WIDTH_PX) -> float:
    """Ground sample distance. What one pixel covers."""
    return ground_footprint_m(agl_m)[0] / image_width_px


# ---------------------------------------------------------------------------
# Rotor geometry
# ---------------------------------------------------------------------------

IN_TO_M = 0.0254


@dataclass(frozen=True)
class RotorGeometry:
    """A quad in X layout. Wheelbase is motor shaft to motor shaft, diagonal."""

    wheelbase_m: float = 0.650
    prop_diameter_in: float = 15.0
    blades: int = 2

    @property
    def prop_diameter_m(self) -> float:
        return self.prop_diameter_in * IN_TO_M

    @property
    def arm_radius_m(self) -> float:
        return self.wheelbase_m / 2.0

    @property
    def adjacent_motor_spacing_m(self) -> float:
        """Centre-to-centre of two neighbouring motors on an X quad."""
        return self.wheelbase_m / math.sqrt(2.0)

    @property
    def tip_gap_m(self) -> float:
        """Air between two neighbouring discs. Negative means they overlap."""
        return self.adjacent_motor_spacing_m - self.prop_diameter_m

    @property
    def tip_gap_fraction(self) -> float:
        """Gap as a fraction of prop diameter. Below ~0.10 the rotors interfere:
        thrust drops, and the loss arrives as noise and vibration at blade-pass
        frequency -- which is the one frequency the camera mount cannot absorb."""
        return self.tip_gap_m / self.prop_diameter_m

    @property
    def disc_area_m2(self) -> float:
        return 4.0 * math.pi * (self.prop_diameter_m / 2.0) ** 2

    def max_prop_diameter_in(self, min_gap_fraction: float = 0.10) -> float:
        """Largest prop this wheelbase takes at a given tip-gap fraction."""
        return self.adjacent_motor_spacing_m / (1.0 + min_gap_fraction) / IN_TO_M


def blade_pass_hz(rpm: float, blades: int = 2) -> float:
    """The frequency a blade passes any fixed point. Brief item 04.

    Not the motor's electrical frequency and not the shaft frequency -- this is
    what the airframe is actually shaken at, and it is `blades` times higher
    than the shaft. Getting this wrong by a factor of two is how a mount ends up
    designed to reject a frequency that is not there.
    """
    return rpm / 60.0 * blades


def isolator_stiffness_n_per_mm(
    isolated_mass_kg: float, target_hz: float, mounts: int = 4
) -> float:
    """Per-mount spring rate for a chosen suspension frequency.

    f = (1/2*pi) * sqrt(k/m), solved for k. A mount only attenuates above about
    1.4x its own natural frequency, and is WORSE than rigid below that -- so
    `target_hz` must sit well under the lowest blade-pass frequency the aircraft
    will ever produce, which is hover, not full throttle.
    """
    if isolated_mass_kg <= 0 or target_hz <= 0 or mounts <= 0:
        raise ValueError("mass, frequency and mount count must be positive")
    k_total = isolated_mass_kg * (2.0 * math.pi * target_hz) ** 2
    return k_total / mounts / 1000.0


def isolator_static_sag_mm(
    isolated_mass_kg: float, k_per_mount_n_per_mm: float, mounts: int = 4
) -> float:
    """How far the plate settles under 1 g. A sanity check on the rate above:
    a few tenths of a millimetre is right; several millimetres means the plate
    will also swing several millimetres in a gust, and the brief asks for
    'damped from the frame, but not free to swing'."""
    k_total = k_per_mount_n_per_mm * mounts * 1000.0
    return isolated_mass_kg * 9.81 / k_total * 1000.0


# ---------------------------------------------------------------------------
# Mass, thrust, endurance
# ---------------------------------------------------------------------------


@dataclass
class MassItem:
    name: str
    grams: float
    group: str = "airframe"
    weighed: bool = False    # False = estimate. Brief item 02.
    note: str = ""


# The starting build. Every `weighed=False` is a guess, and the brief is blunt
# about sizing an aircraft against a scale rather than against a sentence.
# Replace these with measurements as parts arrive; the model regenerates.
BASELINE_MASS: list[MassItem] = [
    MassItem("Carbon frame, 650 class", 700, "airframe"),
    MassItem("Motors, 4x 3508-class", 400, "propulsion"),
    MassItem("ESCs, 4-in-1", 120, "propulsion"),
    MassItem("Propellers, 4x 15in", 80, "propulsion"),
    MassItem("Flight controller", 40, "avionics"),
    MassItem("GNSS / RTK rover", 60, "avionics", note="Stage 4 in the hardware plan"),
    MassItem("Telemetry radio", 30, "avionics"),
    MassItem("RC receiver", 15, "avionics"),
    MassItem("Battery, 6S 10 Ah", 1250, "energy"),
    MassItem("Raspberry Pi 5, 8 GB", 46, "payload"),
    MassItem("Hailo AI HAT+ 26 TOPS", 30, "payload"),
    MassItem("Active cooler", 22, "payload"),
    MassItem("Camera Module 3 + ribbon", 14, "payload"),
    MassItem("Payload enclosure", 120, "payload", note="light-coloured, brief item 05"),
    MassItem("5 V / 6 A regulator + bulk caps", 45, "payload", note="brief item 06"),
    MassItem("Downward rangefinder", 35, "payload", note="brief item 09 -- AGL, not AGH"),
    MassItem("Environment sensor + boom", 25, "payload", note="brief item 07"),
    MassItem("Landing gear", 220, "airframe"),
    MassItem("Wiring, fasteners, damping", 180, "airframe"),
]


@dataclass
class MassBudget:
    items: list[MassItem] = field(default_factory=lambda: list(BASELINE_MASS))

    @property
    def total_g(self) -> float:
        return sum(i.grams for i in self.items)

    @property
    def total_kg(self) -> float:
        return self.total_g / 1000.0

    def by_group(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for i in self.items:
            out[i.group] = out.get(i.group, 0.0) + i.grams
        return out

    @property
    def estimated_fraction(self) -> float:
        """Share of the all-up mass that has never been on a scale.

        Reported rather than hidden. An aircraft sized against a budget that is
        90% estimate has an unquantified margin, and the honest response is to
        weigh things, not to add a fudge factor.
        """
        if self.total_g == 0:
            return 0.0
        return sum(i.grams for i in self.items if not i.weighed) / self.total_g

    def group_of(self, name: str) -> float:
        return self.by_group().get(name, 0.0)


@dataclass(frozen=True)
class Propulsion:
    """Measured or manufacturer thrust, per motor, at full throttle."""

    max_thrust_per_motor_g: float = 2200.0
    motors: int = 4
    # Grams of thrust per watt near hover. Falls with disc loading; 8-10 is
    # typical for a 15in prop at this scale. MEASURE IT -- endurance is linear
    # in this number and manufacturer figures are optimistic.
    hover_efficiency_g_per_w: float = 9.0

    def total_thrust_g(self) -> float:
        return self.max_thrust_per_motor_g * self.motors

    def thrust_to_weight(self, mass_g: float) -> float:
        return self.total_thrust_g() / mass_g

    def hover_throttle_fraction(self, mass_g: float) -> float:
        """Share of available thrust used just to stay up.

        Above ~0.60 there is no authority left for wind or a climb, which on a
        survey aircraft shows up as the controller unable to hold altitude in
        gusts -- and altitude error is ground-resolution error.
        """
        return mass_g / self.total_thrust_g()

    def hover_power_w(self, mass_g: float, avionics_w: float = 30.0) -> float:
        """Electrical power to hover, including the compute payload.

        The Pi 5 plus the Hailo HAT is a real load, roughly 15 W, and it is on
        for the whole flight. `avionics_w` covers it plus the flight controller,
        radios and the camera.
        """
        return mass_g / self.hover_efficiency_g_per_w + avionics_w


@dataclass(frozen=True)
class Battery:
    cells: int = 6
    capacity_ah: float = 10.0
    nominal_v_per_cell: float = 3.7
    # Never plan to the full pack. Below ~20% remaining the voltage sags, the
    # available thrust falls with it, and cell life drops sharply.
    usable_fraction: float = 0.80

    @property
    def nominal_v(self) -> float:
        return self.cells * self.nominal_v_per_cell

    @property
    def energy_wh(self) -> float:
        return self.nominal_v * self.capacity_ah

    @property
    def usable_wh(self) -> float:
        return self.energy_wh * self.usable_fraction


def endurance_min(usable_wh: float, hover_power_w: float, cruise_penalty: float = 0.10) -> float:
    """Minutes in the air. `cruise_penalty` covers forward flight, climb and the
    fact that a survey is not a hover -- 10% is a starting figure, not a
    measurement."""
    if hover_power_w <= 0:
        raise ValueError("hover power must be positive")
    return usable_wh / (hover_power_w * (1.0 + cruise_penalty)) * 60.0


# ---------------------------------------------------------------------------
# What the mission asks of the aircraft
# ---------------------------------------------------------------------------


def coverage_ha_per_h(agl_m: float, ground_speed_ms: float, overlap: float = 0.20) -> float:
    """Area rate. Ties the airframe directly to the business case.

    Matches `geo/coverage.py`'s effective swath: the sideways overlap between
    flight lines is what stops a gap opening when the aircraft drifts, and it is
    paid for in coverage.
    """
    swath, _ = ground_footprint_m(agl_m)
    effective = swath * (1.0 - overlap)
    return effective * ground_speed_ms * 3600.0 / 10_000.0


def hectares_per_battery(
    agl_m: float, ground_speed_ms: float, survey_minutes: float, overlap: float = 0.20
) -> float:
    return coverage_ha_per_h(agl_m, ground_speed_ms, overlap) * survey_minutes / 60.0


def max_exposure_s(agl_m: float, ground_speed_ms: float, blur_px: float = 1.0) -> float:
    """Longest exposure holding motion smear under `blur_px`. Brief, flight envelope.

    Duplicated deliberately from training/motion_budget.py in its simplest form,
    because this is the number that decides whether the airframe can fly the
    speed the coverage figure above assumes. They must agree; a test checks it.
    """
    return blur_px * gsd_m_per_px(agl_m) / ground_speed_ms


# ---------------------------------------------------------------------------
# The assembled design, and its own verdict on itself
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Airframe:
    rotors: RotorGeometry = field(default_factory=RotorGeometry)
    propulsion: Propulsion = field(default_factory=Propulsion)
    battery: Battery = field(default_factory=Battery)

    # Layout, metres. Origin is the centre of the top plate, z up, x forward.
    body_width_m: float = 0.180
    body_length_m: float = 0.220
    plate_gap_m: float = 0.045          # between top and bottom plate
    arm_diameter_m: float = 0.025
    motor_height_m: float = 0.050
    # The payload plate hangs under the body on isolators; the lens sits under it.
    payload_drop_m: float = 0.060
    lens_drop_from_payload_m: float = 0.035
    leg_span_radius_m: float = 0.260    # foot radius from the optical axis
    leg_height_m: float = 0.255         # foot to the underside of the bottom plate
    # Where the first leg sits, measured from the nose. 0 puts the legs between
    # the arms, which is the usual quad layout.
    leg_azimuth_deg: float = 0.0
    # How the sensor's LONG axis is turned relative to the gear. 0 aligns it
    # with a pair of legs, and 0 is the best value -- see leg_clearance. The
    # worst is about 37 deg, the pyramid's own diagonal.
    sensor_yaw_vs_gear_deg: float = 0.0

    isolated_mass_kg: float = 0.320
    isolator_target_hz: float = 35.0
    hover_rpm: float = 4600.0
    full_throttle_rpm: float = 6800.0

    survey_agl_m: float = 30.0
    survey_speed_ms: float = 5.0
    survey_overlap: float = 0.20

    @property
    def lens_drop_below_legs_m(self) -> float:
        """How far the lens sits above the feet. The pyramid is measured from
        the lens, so this is the depth at which a leg either is or is not in
        the picture."""
        return self.leg_height_m - self.payload_drop_m - self.lens_drop_from_payload_m

    def leg_clearance(self) -> dict:
        """Does the landing gear stay out of frame? Brief item 09.

        Evaluates **all four legs**, not the one on the nominal azimuth. That
        distinction is the whole answer: with legs 90 deg apart and a rectangular
        pyramid, rotating the sensor moves two legs towards the short axis and
        the other two towards the corner at the same time, and the corner side
        loses faster than the short side gains.

        Aligned with the sensor axes is the strict minimum; the worst rotation
        is the pyramid's diagonal, near 37 deg, and it costs about 25%.

        Azimuth still matters enormously for a *single* item hanging below the
        lens. That is `obstruction_check`, and it is where the 40% is.
        """
        drop = self.lens_drop_below_legs_m
        per_leg = [
            (j * 90.0 - self.sensor_yaw_vs_gear_deg,
             clearance_radius_m(drop, j * 90.0 - self.sensor_yaw_vs_gear_deg))
            for j in range(4)
        ]
        needed = max(r for _, r in per_leg)
        needed_worst = worst_case_clearance_radius_m(drop)
        return {
            "lens_height_above_feet_m": drop,
            "leg_radius_m": self.leg_span_radius_m,
            "required_m": needed,
            "required_per_leg_m": [r for _, r in per_leg],
            "binding_leg_azimuth_deg": max(per_leg, key=lambda t: t[1])[0] % 360.0,
            "required_worst_azimuth_m": needed_worst,
            "margin_m": self.leg_span_radius_m - needed,
            "in_frame": self.leg_span_radius_m < needed,
        }

    def obstruction_check(
        self, name: str, radius_m: float, drop_below_lens_m: float, azimuth_deg: float = 0.0
    ) -> dict:
        """Is this part in the picture? Ask it of anything below the lens.

        Legs are the obvious one, but the parts that actually get missed are the
        rangefinder, the environment sensor's boom (brief item 07 wants it out in
        clean air, which pushes it outward and downward -- straight towards the
        pyramid), antenna whips, and the wiring loom that was tidy at assembly
        and has sagged by the tenth flight.

        Anything ABOVE the lens plane is safe and returns a negative drop, which
        this reports rather than silently passing.
        """
        if drop_below_lens_m <= 0:
            return {
                "name": name, "above_lens": True, "in_frame": False,
                "required_m": 0.0, "margin_m": math.inf,
            }
        required = clearance_radius_m(drop_below_lens_m, azimuth_deg)
        return {
            "name": name,
            "above_lens": False,
            "required_m": required,
            "radius_m": radius_m,
            "margin_m": radius_m - required,
            "in_frame": radius_m < required,
        }

    def vibration(self) -> dict:
        """Brief item 04, as three frequencies that must not collide."""
        bpf_hover = blade_pass_hz(self.hover_rpm, self.rotors.blades)
        bpf_full = blade_pass_hz(self.full_throttle_rpm, self.rotors.blades)
        k = isolator_stiffness_n_per_mm(self.isolated_mass_kg, self.isolator_target_hz)
        return {
            "blade_pass_hover_hz": bpf_hover,
            "blade_pass_full_hz": bpf_full,
            "isolator_target_hz": self.isolator_target_hz,
            "isolation_ratio": bpf_hover / self.isolator_target_hz,
            "isolator_k_n_per_mm_each": k,
            "static_sag_mm": isolator_static_sag_mm(self.isolated_mass_kg, k),
            # Below 1.4 the mount amplifies instead of attenuating. Aim for 3+.
            "adequate": bpf_hover / self.isolator_target_hz >= 3.0,
            "frame_mode_should_exceed_hz": bpf_full,
        }

    def performance(self, mass: MassBudget | None = None) -> dict:
        mass = mass or MassBudget()
        g = mass.total_g
        power = self.propulsion.hover_power_w(g)
        mins = endurance_min(self.battery.usable_wh, power)
        # Leave three minutes for takeoff, transit and the landing approach.
        survey_mins = max(0.0, mins - 3.0)
        return {
            "auw_kg": g / 1000.0,
            "thrust_to_weight": self.propulsion.thrust_to_weight(g),
            "hover_throttle_fraction": self.propulsion.hover_throttle_fraction(g),
            "hover_power_w": power,
            "endurance_min": mins,
            "survey_min": survey_mins,
            "coverage_ha_h": coverage_ha_per_h(
                self.survey_agl_m, self.survey_speed_ms, self.survey_overlap
            ),
            "ha_per_battery": hectares_per_battery(
                self.survey_agl_m, self.survey_speed_ms, survey_mins, self.survey_overlap
            ),
            "max_exposure_ms": max_exposure_s(self.survey_agl_m, self.survey_speed_ms) * 1000.0,
            "gsd_cm_px": gsd_m_per_px(self.survey_agl_m) * 100.0,
            "swath_m": ground_footprint_m(self.survey_agl_m)[0],
            "estimated_fraction": mass.estimated_fraction,
        }

    def checks(self, mass: MassBudget | None = None) -> list[tuple[str, bool, str]]:
        """(label, pass, detail). The design arguing with itself.

        Deliberately fails loudly rather than clamping: a design that quietly
        adjusts itself to pass is a design nobody learns anything from.
        """
        perf = self.performance(mass)
        legs = self.leg_clearance()
        vib = self.vibration()
        out = [
            (
                "Under 25 kg (Transport Canada small RPAS)",
                perf["auw_kg"] < 25.0,
                f"{perf['auw_kg']:.2f} kg all-up",
            ),
            (
                "Thrust-to-weight at least 2.0",
                perf["thrust_to_weight"] >= 2.0,
                f"{perf['thrust_to_weight']:.2f}:1",
            ),
            (
                "Hover under 60% of available thrust",
                perf["hover_throttle_fraction"] <= 0.60,
                f"{perf['hover_throttle_fraction']*100:.0f}% at hover",
            ),
            (
                "Propeller tip gap at least 10% of diameter",
                self.rotors.tip_gap_fraction >= 0.10,
                f"{self.rotors.tip_gap_m*1000:.0f} mm "
                f"({self.rotors.tip_gap_fraction*100:.0f}%)",
            ),
            (
                "Landing gear outside the view pyramid",
                not legs["in_frame"],
                f"feet at {legs['leg_radius_m']*1000:.0f} mm, worst leg needs "
                f"{legs['required_m']*1000:.0f} mm "
                f"({legs['required_worst_azimuth_m']*1000:.0f} mm at a pyramid corner)",
            ),
            (
                "Isolator at least 3x below blade-pass",
                vib["adequate"],
                f"{vib['blade_pass_hover_hz']:.0f} Hz at hover vs "
                f"{vib['isolator_target_hz']:.0f} Hz mount "
                f"({vib['isolation_ratio']:.1f}x)",
            ),
            (
                "Exposure achievable at survey speed",
                perf["max_exposure_ms"] >= 1.5,
                f"{perf['max_exposure_ms']:.1f} ms for 1 px of smear at "
                f"{self.survey_speed_ms:.0f} m/s",
            ),
        ]
        return out


def motor_positions(af: Airframe) -> list[tuple[float, float, float]]:
    """Four motor shafts, X layout, nose between two of them. z is the top plate."""
    r = af.rotors.arm_radius_m
    return [
        (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), 0.0)
        for a in (45.0, 135.0, 225.0, 315.0)
    ]


def leg_positions(af: Airframe) -> list[tuple[float, float, float]]:
    """Feet, between the arms rather than under them."""
    r = af.leg_span_radius_m
    base = af.leg_azimuth_deg
    return [
        (r * math.cos(math.radians(base + a)), r * math.sin(math.radians(base + a)),
         -af.leg_height_m - af.plate_gap_m)
        for a in (0.0, 90.0, 180.0, 270.0)
    ]


def summary(af: Airframe | None = None, mass: MassBudget | None = None) -> dict:
    """Everything the model and the interactive view are drawn from."""
    af = af or Airframe()
    mass = mass or MassBudget()
    fov = field_of_view()
    return {
        "fov": {
            "half_width_deg": fov.half_width_deg,
            "half_height_deg": fov.half_height_deg,
            "half_diagonal_deg": fov.half_diagonal_deg,
        },
        "rotors": {
            "wheelbase_mm": af.rotors.wheelbase_m * 1000.0,
            "prop_diameter_in": af.rotors.prop_diameter_in,
            "adjacent_spacing_mm": af.rotors.adjacent_motor_spacing_m * 1000.0,
            "tip_gap_mm": af.rotors.tip_gap_m * 1000.0,
            "tip_gap_pct": af.rotors.tip_gap_fraction * 100.0,
            "max_prop_in": af.rotors.max_prop_diameter_in(),
        },
        "mass_g": mass.total_g,
        "mass_by_group": mass.by_group(),
        "performance": af.performance(mass),
        "legs": af.leg_clearance(),
        "vibration": af.vibration(),
        "checks": [
            {"label": label, "pass": ok, "detail": detail}
            for label, ok, detail in af.checks(mass)
        ],
    }


def _print_sheet() -> None:
    af = Airframe()
    mass = MassBudget()
    s = summary(af, mass)
    p = s["performance"]

    print("AGRI-EDGE SCOUTING QUAD -- derived specification")
    print("=" * 66)
    print("\nOPTICS (IMX708 / Camera Module 3)")
    print(f"  half-angle, long axis      {s['fov']['half_width_deg']:6.1f} deg")
    print(f"  half-angle, short axis     {s['fov']['half_height_deg']:6.1f} deg")
    print(f"  half-angle, corners        {s['fov']['half_diagonal_deg']:6.1f} deg  <- what a leg must clear")
    print(f"  swath at {af.survey_agl_m:.0f} m AGL          {p['swath_m']:6.1f} m")
    print(f"  ground sample distance     {p['gsd_cm_px']:6.3f} cm/px")

    print("\nROTORS")
    r = s["rotors"]
    print(f"  wheelbase                  {r['wheelbase_mm']:6.0f} mm")
    print(f"  propeller                  {r['prop_diameter_in']:6.1f} in")
    print(f"  adjacent motor spacing     {r['adjacent_spacing_mm']:6.0f} mm")
    print(f"  tip gap                    {r['tip_gap_mm']:6.0f} mm ({r['tip_gap_pct']:.0f}%)")
    print(f"  largest prop that fits     {r['max_prop_in']:6.1f} in")

    print("\nMASS")
    for group, grams in sorted(s["mass_by_group"].items(), key=lambda kv: -kv[1]):
        print(f"  {group:<24} {grams:6.0f} g")
    print(f"  {'ALL-UP':<24} {s['mass_g']:6.0f} g")
    print(f"  never weighed              {p['estimated_fraction']*100:6.0f}%  <- brief item 02")

    print("\nFLIGHT")
    print(f"  thrust-to-weight           {p['thrust_to_weight']:6.2f} :1")
    print(f"  throttle at hover          {p['hover_throttle_fraction']*100:6.0f} %")
    print(f"  hover power                {p['hover_power_w']:6.0f} W")
    print(f"  endurance                  {p['endurance_min']:6.1f} min")
    print(f"  coverage at {af.survey_speed_ms:.0f} m/s         {p['coverage_ha_h']:6.1f} ha/h")
    print(f"  per battery                {p['ha_per_battery']:6.1f} ha")
    print(f"  longest exposure           {p['max_exposure_ms']:6.1f} ms")

    print("\nCAMERA CLEARANCE (brief item 09)")
    legs = s["legs"]
    print(f"  lens above the feet        {legs['lens_height_above_feet_m']*1000:6.0f} mm")
    print(f"  legs at                    {legs['leg_radius_m']*1000:6.0f} mm radius")
    print(f"  pyramid needs (worst leg)  {legs['required_m']*1000:6.0f} mm")
    print(f"  pyramid needs, at a corner {legs['required_worst_azimuth_m']*1000:6.0f} mm")
    print(f"  margin                     {legs['margin_m']*1000:6.0f} mm")

    print("\nVIBRATION (brief item 04)")
    v = s["vibration"]
    print(f"  blade pass, hover          {v['blade_pass_hover_hz']:6.0f} Hz")
    print(f"  blade pass, full throttle  {v['blade_pass_full_hz']:6.0f} Hz")
    print(f"  isolator target            {v['isolator_target_hz']:6.0f} Hz")
    print(f"  spring rate, each of 4     {v['isolator_k_n_per_mm_each']:6.2f} N/mm")
    print(f"  static sag                 {v['static_sag_mm']:6.2f} mm")
    print(f"  frame modes must exceed    {v['frame_mode_should_exceed_hz']:6.0f} Hz")

    print("\nCHECKS")
    for c in s["checks"]:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['label']:<44} {c['detail']}")
    print()


if __name__ == "__main__":
    _print_sheet()
