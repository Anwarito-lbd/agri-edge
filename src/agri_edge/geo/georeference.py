"""Turn a detection's pixels into a position on the ground.

THE GAP THIS CLOSES
-------------------
`Detection.bbox` is normalised **image** coordinates. Until now nothing turned
that into a place, which quietly stranded three things:

* a farmOS log could record where the *aircraft* was, never where the *weed*
  was — and "there is kochia at 49.8951, -97.1384" is the actual deliverable;
* `geo/geofence.py` had no caller, because you cannot test whether a detection
  is inside a treatment boundary when the detection has no position;
* no prescription map is possible, so the map -> prescription -> approval ->
  apply chain was broken at step one.

One missing function, three stranded features.

HOW IT WORKS
------------
A pixel defines a ray out of the lens. Rotate that ray by the aircraft's
attitude, then intersect it with the ground plane. That is the whole idea, and
it is done properly rather than with the flat "GSD times pixel offset"
shortcut, because the shortcut is only correct at exactly zero tilt:

    at 30 m AGL, a 10 deg tilt moves the frame centre 5.3 m on the ground

10 degrees is the QA gate's *pass* threshold, so the shortcut would be metres
wrong on frames the pipeline considers good. Ray-plane intersection costs a few
lines more and handles tilt exactly.

WHAT IT ASSUMES, AND WHAT THAT COSTS
------------------------------------
**1. The ground is flat and level at the aircraft's height reference.** Real
terrain is not. A point whose true elevation differs by `dh` from the assumed
plane lands with a horizontal error of about `dh * tan(theta)`, where `theta` is
its off-nadir angle. Directly under the aircraft that is zero; at the frame
corner of a wide lens it is comparable to `dh` itself. Prairie fields are kind
here, hills are not. `ground_error_estimate_m` quantifies it rather than leaving
it unsaid.

**2. `altitude_agl_m` really is above *ground*.** MAVLink's `alt_rel_m` is
relative to the *home* point, which equals AGL only if the field is level with
where you took off. Flying a slope with home at the bottom inflates every
distance. A downward rangefinder fixes this and is item 09 in the airframe
brief; until then, this is the dominant systematic error on undulating ground.

**3. The camera is rigidly mounted, looking down, top of frame toward the nose.**
`CameraMount.yaw_offset_deg` handles a camera bolted on sideways. A gimbal that
moves independently of the airframe would need its own attitude and is not
modelled.

None of this makes the output useless — it makes it *specified*. A position with
a stated error budget is worth far more than a position with none.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .geofence import _EARTH_R_M


@dataclass(frozen=True)
class CameraIntrinsics:
    """Pinhole model, from numbers on the camera's datasheet.

    `focal_px` is derived rather than configured, because focal length in
    millimetres and sensor width in millimetres are what a datasheet gives you,
    and converting them by hand at every call site is how a factor-of-two error
    gets in.
    """

    sensor_width_mm: float
    focal_length_mm: float
    image_width_px: int
    image_height_px: int

    def __post_init__(self) -> None:
        for name in ("sensor_width_mm", "focal_length_mm"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        for name in ("image_width_px", "image_height_px"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")

    @property
    def focal_px(self) -> float:
        """Focal length in pixels. Square pixels are assumed, which is true of
        every sensor this project is likely to see."""
        return self.focal_length_mm * self.image_width_px / self.sensor_width_mm

    @property
    def hfov_deg(self) -> float:
        return math.degrees(2.0 * math.atan(self.sensor_width_mm / (2.0 * self.focal_length_mm)))

    def gsd_m(self, altitude_agl_m: float) -> float:
        """Metres per pixel directly below the aircraft. Nadir only.

        Matches `training/gsd_calculator.py`, which is the tool that settled the
        product direction. Kept here too because the Pi runtime cannot import
        from `training/`.
        """
        ground_width_m = (self.sensor_width_mm / self.focal_length_mm) * altitude_agl_m
        return ground_width_m / self.image_width_px


# Pi Camera Module 3, the baseline for this project.
IMX708 = CameraIntrinsics(
    sensor_width_mm=7.4, focal_length_mm=4.74, image_width_px=4056, image_height_px=3040
)


@dataclass(frozen=True)
class CameraMount:
    """How the camera sits on the airframe.

    `yaw_offset_deg` is measured clockwise from "top of image points at the
    nose". A camera rotated 90 deg to fit the airframe is the common case, and
    getting it wrong rotates every detection about the frame centre — which
    looks plausible on a single frame and scrambles a whole flight.
    """

    yaw_offset_deg: float = 0.0


def _rotation_body_to_ned(roll_rad: float, pitch_rad: float, yaw_rad: float) -> np.ndarray:
    """Standard aerospace ZYX rotation, body (forward-right-down) -> NED.

    MAVLink's ATTITUDE message is exactly this convention: roll about the nose
    axis, pitch about the right wing, yaw clockwise from north.

    SIGNS, because a belly camera inverts the intuition. The camera looks along
    body +Z (down), so it follows the *belly*, not the wing:

        +roll  (right wing DOWN) -> belly tilts LEFT  -> view swings WEST  when heading north
        +pitch (nose UP)         -> belly tilts FWD   -> view swings NORTH when heading north

    Roll right 90 degrees and the camera is looking due west. Getting the roll
    sign backwards mirrors a whole flight about its own track, which is invisible
    frame by frame. `tests/test_georeference.py` pins both signs separately.
    """
    cr, sr = math.cos(roll_rad), math.sin(roll_rad)
    cp, sp = math.cos(pitch_rad), math.sin(pitch_rad)
    cy, sy = math.cos(yaw_rad), math.sin(yaw_rad)
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp,     cp * sr,                cp * cr],
    ])


def pixel_ray_ned(
    u_norm: float,
    v_norm: float,
    intr: CameraIntrinsics,
    roll_deg: float,
    pitch_deg: float,
    yaw_deg: float,
    mount: CameraMount | None = None,
) -> np.ndarray:
    """Unit ray through a normalised pixel, expressed in NED.

    `u_norm`/`v_norm` are 0-1 across the frame, origin top-left, matching
    `Detection.bbox`.

    The camera convention: looking down, the top of the image points at the nose.
    So image-right is the aircraft's right (+Y body) and image-down is *aft*
    (-X body). Getting that mapping backwards mirrors the frame, which is
    invisible on a symmetric scene and wrong everywhere else.
    """
    mount = mount or CameraMount()

    # Pixel offsets from the principal point, in pixels.
    du = (u_norm - 0.5) * intr.image_width_px
    dv = (v_norm - 0.5) * intr.image_height_px
    f = intr.focal_px

    # Body frame: X forward, Y right, Z down.
    ray_body = np.array([-dv / f, du / f, 1.0])

    if mount.yaw_offset_deg:
        c = math.cos(math.radians(mount.yaw_offset_deg))
        s = math.sin(math.radians(mount.yaw_offset_deg))
        x, y = ray_body[0], ray_body[1]
        ray_body = np.array([c * x - s * y, s * x + c * y, ray_body[2]])

    ray_ned = _rotation_body_to_ned(
        math.radians(roll_deg), math.radians(pitch_deg), math.radians(yaw_deg)
    ) @ ray_body
    return ray_ned / np.linalg.norm(ray_ned)


def local_to_geographic(
    north_m: float, east_m: float, origin: tuple[float, float]
) -> tuple[float, float]:
    """Local NE metres -> (lat, lon). Inverse of `geofence.project_to_local`."""
    lat0, lon0 = origin
    lat = lat0 + math.degrees(north_m / _EARTH_R_M)
    cos_lat0 = math.cos(math.radians(lat0))
    # A pole-adjacent field would divide by ~0 here. Nothing agricultural is,
    # but failing loudly beats returning a longitude of infinity.
    if abs(cos_lat0) < 1e-9:
        raise ValueError("Cannot convert local offsets to longitude at the pole.")
    lon = lon0 + math.degrees(east_m / (_EARTH_R_M * cos_lat0))
    return lat, lon


def pixel_to_ground(
    u_norm: float,
    v_norm: float,
    intr: CameraIntrinsics,
    lat: float,
    lon: float,
    altitude_agl_m: float,
    yaw_deg: float,
    roll_deg: float = 0.0,
    pitch_deg: float = 0.0,
    mount: CameraMount | None = None,
) -> tuple[float, float]:
    """Where on the ground does this pixel land? Returns (lat, lon).

    Raises if the ray does not reach the ground -- which happens when the
    aircraft is tilted far enough that part of the frame is looking at the sky.
    That is a real condition, not an edge case to paper over: returning a
    position for a pixel pointing at the horizon would be fabrication.
    """
    if altitude_agl_m <= 0:
        raise ValueError(
            f"altitude_agl_m must be > 0, got {altitude_agl_m}. On the ground "
            "there is no projection to make."
        )

    ray = pixel_ray_ned(u_norm, v_norm, intr, roll_deg, pitch_deg, yaw_deg, mount)
    down = ray[2]
    if down <= 1e-6:
        raise ValueError(
            "This pixel's ray does not intersect the ground -- it points at or "
            f"above the horizon (attitude roll={roll_deg}, pitch={pitch_deg}). "
            "The frame is too oblique to georeference."
        )

    t = altitude_agl_m / down
    return local_to_geographic(ray[0] * t, ray[1] * t, (lat, lon))


def off_nadir_deg(
    u_norm: float, v_norm: float, intr: CameraIntrinsics,
    roll_deg: float = 0.0, pitch_deg: float = 0.0,
) -> float:
    """Angle between this pixel's ray and straight down, in degrees.

    The number that governs how badly terrain error hurts -- see
    `ground_error_estimate_m`.
    """
    ray = pixel_ray_ned(u_norm, v_norm, intr, roll_deg, pitch_deg, 0.0)
    return math.degrees(math.acos(max(-1.0, min(1.0, float(ray[2])))))


def ground_error_estimate_m(
    u_norm: float, v_norm: float, intr: CameraIntrinsics,
    altitude_agl_m: float, terrain_uncertainty_m: float = 2.0,
    roll_deg: float = 0.0, pitch_deg: float = 0.0,
) -> float:
    """Horizontal error from the flat-ground assumption, in metres.

    `dh * tan(theta)`: an elevation error of `dh` slides the intersection along
    the ray by that much horizontally. Zero directly below the aircraft, and
    growing toward the frame edge.

    `terrain_uncertainty_m` defaults to 2 m, which is a reasonable guess for a
    Prairie field flown with home at field level. **It is a guess.** Measure your
    field's relief, or fit a rangefinder and stop guessing.

    This deliberately excludes GNSS error, attitude error and lens distortion.
    It answers one question -- what does assuming flat ground cost -- and a
    number that quietly folded in three other unquantified terms would be worse
    than no number at all.
    """
    theta = math.radians(off_nadir_deg(u_norm, v_norm, intr, roll_deg, pitch_deg))
    return abs(terrain_uncertainty_m) * math.tan(theta)


def frame_footprint(
    intr: CameraIntrinsics,
    lat: float,
    lon: float,
    altitude_agl_m: float,
    yaw_deg: float,
    roll_deg: float = 0.0,
    pitch_deg: float = 0.0,
    mount: CameraMount | None = None,
) -> list[tuple[float, float]]:
    """The four ground corners of the frame, clockwise from top-left.

    Useful for coverage checking, for drawing what was actually surveyed, and
    for spotting gaps between passes before the crop shows them to you.
    """
    corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    return [
        pixel_to_ground(u, v, intr, lat, lon, altitude_agl_m, yaw_deg,
                        roll_deg, pitch_deg, mount)
        for u, v in corners
    ]


def georeference_detections(
    detections,
    intr: CameraIntrinsics,
    telemetry,
    mount: CameraMount | None = None,
    terrain_uncertainty_m: float = 2.0,
):
    """Attach a ground position to each detection, in place. Returns the list.

    Uses the **bottom-centre** of each box, not its centroid. For an object
    standing on the ground and viewed off-nadir, the box's lower edge is where it
    meets the earth; its centre is partway up the object and projects beyond it.
    At nadir the two agree, and off-nadir the bottom edge is the honest choice.

    Detections that cannot be georeferenced are left without a position rather
    than being given a plausible wrong one, and the reason is recorded.
    """
    if telemetry is None or telemetry.lat is None or telemetry.lon is None:
        return detections

    alt = telemetry.alt_rel_m
    if alt is None or alt <= 0:
        for d in detections:
            d.geo_error = "no usable AGL altitude"
        return detections

    yaw = telemetry.yaw_deg if telemetry.yaw_deg is not None else 0.0
    roll = telemetry.roll_deg or 0.0
    pitch = telemetry.pitch_deg or 0.0

    for d in detections:
        x1, y1, x2, y2 = d.bbox
        u = (x1 + x2) / 2.0
        v = y2                      # bottom edge: where the object meets the ground
        try:
            d.lat, d.lon = pixel_to_ground(
                u, v, intr, telemetry.lat, telemetry.lon, alt, yaw, roll, pitch, mount
            )
            d.position_error_m = round(
                ground_error_estimate_m(u, v, intr, alt, terrain_uncertainty_m,
                                        roll, pitch),
                2,
            )
        except ValueError as exc:
            d.geo_error = str(exc)
    return detections
