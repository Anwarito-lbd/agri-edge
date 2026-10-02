"""Pose-validated georeferencing: detection bbox -> world lat/lon + uncertainty.

STATUS: SIMULATED. The maths is unit-tested against hand-computed geometry; it
has never been run against a real camera, a real GNSS/IMU stack, or a surveyed
ground-truth target. Nothing here is VALIDATED.

WHAT THIS ADDS OVER `geo/georeference.py`
-----------------------------------------
`georeference.py` owns the optics (pinhole model, ray-plane intersection, the
sign conventions for a belly camera). This module is the *gate and the ledger*
around it:

1. **Pose validation.** A vehicle pose is only usable if it is finite, in range,
   fresh, and not so tilted that the flat-ground model stops meaning anything.
   An invalid or stale pose yields a REJECTED result and **no position at all**.
   A plausible-looking wrong coordinate is worse than none, because a treatment
   decision downstream would act on it.
2. **A stated uncertainty.** Every position carries `position_uncertainty_m`, a
   root-sum-square of the terms we can name (below). It is a *model*, and says so.
3. **Local metres.** `local_x`/`local_y` (east/north) so the treatment geofence --
   which works in metres, never degrees -- can consume the result directly.

THE FLAT-GROUND ASSUMPTION (read this before trusting a number)
---------------------------------------------------------------
The ray through the bbox centre is intersected with a **horizontal plane at
`alt_agl_m` below the aircraft**. That is correct only if

* the ground is flat and level under the frame, and
* `alt_agl_m` really is height *above ground at that point* (not above the home
  point, not MSL).

Where either fails the point lands `dh * tan(theta)` away from the truth, with
`dh` the terrain height error and `theta` the off-nadir angle. `terrain_sigma_m`
(default 2 m, a guess for a Prairie field) feeds that term. **Measure your
field's relief or fit a rangefinder; do not trust the default on hills.** Also
unmodelled: lens distortion, rolling shutter, gimbal motion, camera boresight
misalignment, and latency between the frame and the pose sample (bounded only by
the staleness gate).

UNCERTAINTY MODEL (all terms in metres, combined as root-sum-square)
-------------------------------------------------------------------
* terrain      `terrain_sigma_m * tan(off_nadir)`            flat-ground cost
* gnss         `pose.h_acc_m` (default 2.0 when unknown)     vehicle position
* heading      `slant_range * sin(heading_sigma)`            yaw error swings the point
* attitude     `alt * (tan(th + a) - tan(th))`, a = attitude sigma
* quantisation `0.5 * GSD`                                    half a pixel at nadir

It deliberately double-counts nothing and invents nothing: each term is a named
input with a stated default. A caller with better numbers passes them.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .geofence import project_to_local
from .georeference import (
    CameraIntrinsics,
    CameraMount,
    local_to_geographic,
    off_nadir_deg,
    pixel_ray_ned,
)

GEOREF_ALGORITHM_VERSION = "georef-flat-1.0.0"

# Status codes (stable strings; they are stored in detection rows).
OK = "OK"
REJECTED_POSE_INVALID = "REJECTED_POSE_INVALID"
REJECTED_POSE_STALE = "REJECTED_POSE_STALE"
REJECTED_NO_GROUND_INTERSECTION = "REJECTED_NO_GROUND_INTERSECTION"
REJECTED_BAD_BBOX = "REJECTED_BAD_BBOX"
FLAGGED_UNCERTAINTY_HIGH = "FLAGGED_UNCERTAINTY_HIGH"

# Defaults, each overridable per call. Stated so they can be argued with.
DEFAULT_MAX_POSE_AGE_S = 1.0
DEFAULT_MAX_FUTURE_SKEW_S = 0.25
DEFAULT_MAX_TILT_DEG = 25.0      # QA gate passes at 10 deg; beyond ~25 the frame is oblique
DEFAULT_MIN_ALT_AGL_M = 1.0
DEFAULT_MAX_ALT_AGL_M = 150.0    # Part 107/SFOC-style ceiling plus margin
DEFAULT_GNSS_H_ACC_M = 2.0       # unknown fix quality -> assume plain GNSS, not RTK
DEFAULT_HEADING_SIGMA_DEG = 2.0
DEFAULT_ATTITUDE_SIGMA_DEG = 1.0
DEFAULT_TERRAIN_SIGMA_M = 2.0
DEFAULT_FLAG_UNCERTAINTY_M = 5.0  # above this the position is returned but FLAGGED


@dataclass(frozen=True)
class VehiclePose:
    """What the georeferencer needs to know about the vehicle, and *when*.

    `timestamp` is epoch seconds of the pose sample (not of the frame). Angles are
    degrees in the same convention as MAVLink ATTITUDE: heading clockwise from
    north; +roll right-wing-down; +pitch nose-up.
    """

    lat: float
    lon: float
    alt_agl_m: float
    heading_deg: float
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    timestamp: float = 0.0
    h_acc_m: float | None = None     # reported horizontal accuracy, if the source has one
    source: str = "unknown"


@dataclass
class PoseCheck:
    valid: bool
    stale: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.stale and not self.valid:
            return REJECTED_POSE_STALE
        if not self.valid:
            return REJECTED_POSE_INVALID
        return OK


def _finite(*vals: Any) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in vals)


def validate_pose(
    pose: VehiclePose | None,
    *,
    now: float | None = None,
    max_age_s: float = DEFAULT_MAX_POSE_AGE_S,
    max_future_skew_s: float = DEFAULT_MAX_FUTURE_SKEW_S,
    max_tilt_deg: float = DEFAULT_MAX_TILT_DEG,
    min_alt_agl_m: float = DEFAULT_MIN_ALT_AGL_M,
    max_alt_agl_m: float = DEFAULT_MAX_ALT_AGL_M,
) -> PoseCheck:
    """Fail closed: anything not positively valid is invalid.

    A pose with `timestamp == 0` (never stamped) is **stale**, not "fresh because
    unknown" -- an unstamped pose cannot be shown to be current.
    """
    if pose is None:
        return PoseCheck(False, False, ["pose_missing"])
    reasons: list[str] = []
    if not _finite(pose.lat, pose.lon, pose.alt_agl_m, pose.heading_deg,
                   pose.pitch_deg, pose.roll_deg, pose.timestamp):
        return PoseCheck(False, False, ["pose_non_finite"])
    if not (-90.0 <= pose.lat <= 90.0) or not (-180.0 <= pose.lon <= 180.0):
        reasons.append("lat_lon_out_of_range")
    elif pose.lat == 0.0 and pose.lon == 0.0:
        reasons.append("null_island_position")   # the classic no-fix default
    if not (min_alt_agl_m <= pose.alt_agl_m <= max_alt_agl_m):
        reasons.append(f"alt_agl_out_of_range:{pose.alt_agl_m}")
    if not (0.0 <= pose.heading_deg <= 360.0):
        reasons.append("heading_out_of_range")
    if abs(pose.roll_deg) > max_tilt_deg or abs(pose.pitch_deg) > max_tilt_deg:
        reasons.append(f"tilt_exceeds_{max_tilt_deg}deg")
    if pose.h_acc_m is not None and (not _finite(pose.h_acc_m) or pose.h_acc_m < 0):
        reasons.append("h_acc_invalid")

    stale = False
    ref = time.time() if now is None else now
    if pose.timestamp <= 0:
        stale = True
        reasons.append("pose_unstamped")
    else:
        age = ref - pose.timestamp
        if age > max_age_s:
            stale = True
            reasons.append(f"pose_stale:{age:.2f}s>{max_age_s}s")
        elif age < -max_future_skew_s:
            reasons.append(f"pose_from_future:{-age:.2f}s")
    return PoseCheck(valid=not reasons, stale=stale, reasons=reasons)


@dataclass
class GeorefResult:
    ok: bool
    status: str
    reasons: list[str] = field(default_factory=list)
    world_lat: float | None = None
    world_lon: float | None = None
    local_x: float | None = None          # metres east of `origin`
    local_y: float | None = None          # metres north of `origin`
    position_uncertainty_m: float | None = None
    origin: tuple[float, float] | None = None
    uncertainty_terms: dict[str, float] = field(default_factory=dict)
    algorithm_version: str = GEOREF_ALGORITHM_VERSION
    assumption: str = "flat_ground_at_alt_agl"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "reasons": list(self.reasons),
            "world_lat": self.world_lat,
            "world_lon": self.world_lon,
            "local_x": self.local_x,
            "local_y": self.local_y,
            "position_uncertainty_m": self.position_uncertainty_m,
            "uncertainty_terms": dict(self.uncertainty_terms),
            "algorithm_version": self.algorithm_version,
            "assumption": self.assumption,
        }


def _reject(status: str, reasons: list[str]) -> GeorefResult:
    return GeorefResult(ok=False, status=status, reasons=reasons)


def georeference_bbox(
    bbox: tuple[float, float, float, float] | list[float],
    intr: CameraIntrinsics,
    pose: VehiclePose | None,
    *,
    now: float | None = None,
    frame_ts: float | None = None,
    origin: tuple[float, float] | None = None,
    mount: CameraMount | None = None,
    anchor: str = "center",
    terrain_sigma_m: float = DEFAULT_TERRAIN_SIGMA_M,
    heading_sigma_deg: float = DEFAULT_HEADING_SIGMA_DEG,
    attitude_sigma_deg: float = DEFAULT_ATTITUDE_SIGMA_DEG,
    flag_uncertainty_m: float = DEFAULT_FLAG_UNCERTAINTY_M,
    max_age_s: float = DEFAULT_MAX_POSE_AGE_S,
    max_tilt_deg: float = DEFAULT_MAX_TILT_DEG,
) -> GeorefResult:
    """Normalised bbox (xyxy, 0-1) -> world position, or a REJECTED result.

    `anchor="center"` uses the bbox centre (the default, per the master spec);
    `"bottom"` uses the bottom-centre, which is the honest choice for tall objects
    viewed off-nadir. `frame_ts` (epoch s), when given, is checked against the pose
    timestamp: a pose that is fresh *now* but was sampled long before the frame was
    exposed is still wrong for that frame.

    `origin` is the (lat, lon) of the local frame for `local_x/local_y`; when
    omitted the frame is centred on the vehicle's own position at pose time.
    """
    check = validate_pose(pose, now=now, max_age_s=max_age_s, max_tilt_deg=max_tilt_deg)
    if not check.valid:
        return _reject(check.status, check.reasons)
    assert pose is not None  # narrowed by validate_pose

    if frame_ts is not None:
        if not _finite(frame_ts):
            return _reject(REJECTED_POSE_STALE, ["frame_ts_non_finite"])
        skew = abs(frame_ts - pose.timestamp)
        if skew > max_age_s:
            return _reject(REJECTED_POSE_STALE, [f"pose_frame_skew:{skew:.2f}s>{max_age_s}s"])

    try:
        x1, y1, x2, y2 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return _reject(REJECTED_BAD_BBOX, ["bbox_not_four_numbers"])
    if not _finite(x1, y1, x2, y2) or not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        return _reject(REJECTED_BAD_BBOX, ["bbox_not_normalised_xyxy"])
    if anchor not in ("center", "bottom"):
        raise ValueError("anchor must be 'center' or 'bottom'")
    u = (x1 + x2) / 2.0
    v = (y1 + y2) / 2.0 if anchor == "center" else y2

    ray = pixel_ray_ned(u, v, intr, pose.roll_deg, pose.pitch_deg, pose.heading_deg, mount)
    down = float(ray[2])
    if down <= 1e-6:
        return _reject(REJECTED_NO_GROUND_INTERSECTION, ["ray_at_or_above_horizon"])
    t = pose.alt_agl_m / down
    north_m, east_m = float(ray[0]) * t, float(ray[1]) * t
    lat, lon = local_to_geographic(north_m, east_m, (pose.lat, pose.lon))

    # --- uncertainty budget ------------------------------------------------
    theta = math.radians(off_nadir_deg(u, v, intr, pose.roll_deg, pose.pitch_deg))
    att = math.radians(attitude_sigma_deg)
    terms = {
        "terrain_m": abs(terrain_sigma_m) * math.tan(theta),
        "gnss_m": pose.h_acc_m if pose.h_acc_m is not None else DEFAULT_GNSS_H_ACC_M,
        "heading_m": math.hypot(north_m, east_m) * math.sin(math.radians(heading_sigma_deg)),
        "attitude_m": pose.alt_agl_m * abs(math.tan(min(theta + att, math.radians(89.0)))
                                           - math.tan(theta)),
        "quantisation_m": 0.5 * intr.gsd_m(pose.alt_agl_m),
    }
    sigma = math.sqrt(sum(x * x for x in terms.values()))

    frame_origin = origin if origin is not None else (pose.lat, pose.lon)
    local = project_to_local(np.array([lat]), np.array([lon]), frame_origin)[0]
    status, reasons = OK, []
    if sigma > flag_uncertainty_m:
        status = FLAGGED_UNCERTAINTY_HIGH
        reasons.append(f"uncertainty_{sigma:.1f}m>{flag_uncertainty_m}m")
    return GeorefResult(
        ok=True,
        status=status,
        reasons=reasons,
        world_lat=lat,
        world_lon=lon,
        local_x=float(local[0]),
        local_y=float(local[1]),
        position_uncertainty_m=sigma,
        origin=frame_origin,
        uncertainty_terms={k: round(v, 4) for k, v in terms.items()},
    )


def georeference_detection(
    det: Any,
    intr: CameraIntrinsics,
    pose: VehiclePose | None,
    **kwargs: Any,
) -> GeorefResult:
    """Georeference one `Detection` in place and return the result.

    On success sets `world_lat/world_lon/local_x/local_y/position_uncertainty_m`
    and mirrors them into the legacy `lat/lon/position_error_m` so the geofence
    and farmOS paths see a position. On REJECTED it clears every position field --
    a detection that was once placed and is now re-run against a bad pose must not
    keep its old coordinates -- and records `geo_error` + `georef_status`.
    """
    res = georeference_bbox(det.bbox, intr, pose, **kwargs)
    det.georef_status = res.status
    if not res.ok:
        det.world_lat = det.world_lon = det.local_x = det.local_y = None
        det.position_uncertainty_m = None
        det.lat = det.lon = det.position_error_m = None
        det.geo_error = ";".join(res.reasons) or res.status
        return res
    det.world_lat, det.world_lon = res.world_lat, res.world_lon
    det.local_x, det.local_y = res.local_x, res.local_y
    det.position_uncertainty_m = res.position_uncertainty_m
    det.lat, det.lon = res.world_lat, res.world_lon
    det.position_error_m = round(float(res.position_uncertainty_m or 0.0), 2)
    det.geo_error = ";".join(res.reasons) if res.reasons else None
    return res


def pose_from_snapshot(snap: Any, *, h_acc_m: float | None = None) -> VehiclePose | None:
    """Adapt a `TelemetrySnapshot` (MAVLink read path). None if it lacks a position.

    Missing attitude/altitude become NaN-free *invalid* values (alt 0) rather than
    zeros that look like a level hover at a sensible height; `validate_pose` then
    refuses them.
    """
    if snap is None or snap.lat is None or snap.lon is None:
        return None
    return VehiclePose(
        lat=snap.lat,
        lon=snap.lon,
        alt_agl_m=snap.alt_rel_m if snap.alt_rel_m is not None else 0.0,
        heading_deg=snap.yaw_deg % 360.0 if snap.yaw_deg is not None else float("nan"),
        pitch_deg=snap.pitch_deg if snap.pitch_deg is not None else float("nan"),
        roll_deg=snap.roll_deg if snap.roll_deg is not None else float("nan"),
        timestamp=snap.timestamp,
        h_acc_m=h_acc_m,
        source="mavlink_snapshot",
    )
