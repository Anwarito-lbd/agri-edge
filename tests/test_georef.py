"""Pose-validated georeferencing (SIMULATED maths; flat-ground assumption).

Hand-computed expectations, not "whatever the code returns":
* nadir, level, bbox centre -> directly under the aircraft (offset 0, within quantisation);
* a bbox centre 0.1 of the frame right of centre at 30 m AGL, heading north -> east by
  `0.1 * W_px / f_px * alt`;
* heading rotates the same offset (heading east -> the offset goes south);
* invalid / stale pose -> REJECTED and NO position fields (fail closed).
"""
from __future__ import annotations

import math

import pytest

from agri_edge.geo import georef as G
from agri_edge.geo.georeference import IMX708
from agri_edge.inference.engine import Detection
from agri_edge.telemetry.mavlink_link import TelemetrySnapshot

LAT, LON, ALT = 49.8951, -97.1384, 30.0
NOW = 1_000_000.0
M_PER_DEG_LAT = 111_320.0


def pose(**kw):
    base = dict(lat=LAT, lon=LON, alt_agl_m=ALT, heading_deg=0.0, pitch_deg=0.0,
                roll_deg=0.0, timestamp=NOW, h_acc_m=0.02, source="test")
    base.update(kw)
    return G.VehiclePose(**base)


def en(res):
    return res.local_x, res.local_y


def test_nadir_centre_is_directly_below():
    r = G.georeference_bbox([0.4, 0.4, 0.6, 0.6], IMX708, pose(), now=NOW)
    assert r.ok and r.status == G.OK
    assert abs(r.local_x) < 1e-6 and abs(r.local_y) < 1e-6
    assert abs(r.world_lat - LAT) < 1e-9 and abs(r.world_lon - LON) < 1e-9


def test_right_of_centre_is_east_when_heading_north():
    du = 0.1  # fraction of width
    expected_east = du * IMX708.image_width_px / IMX708.focal_px * ALT
    r = G.georeference_bbox([0.5, 0.4, 0.7, 0.6], IMX708, pose(), now=NOW)  # centre u=0.6
    assert r.local_x == pytest.approx(expected_east, rel=1e-6)
    assert abs(r.local_y) < 1e-6


def test_top_of_frame_is_north_when_heading_north():
    dv = 0.1
    expected_north = dv * IMX708.image_height_px / IMX708.focal_px * ALT
    r = G.georeference_bbox([0.4, 0.3, 0.6, 0.5], IMX708, pose(), now=NOW)
    # centre v = 0.4 -> 0.1 above frame centre -> toward the nose
    assert r.local_y == pytest.approx(expected_north, rel=1e-3)


def test_heading_rotates_offset():
    # image-right = vehicle right; heading east (90) -> vehicle right is SOUTH
    r = G.georeference_bbox([0.5, 0.4, 0.7, 0.6], IMX708, pose(heading_deg=90.0), now=NOW)
    expected = 0.1 * IMX708.image_width_px / IMX708.focal_px * ALT
    assert r.local_y == pytest.approx(-expected, rel=1e-6)
    assert abs(r.local_x) < 1e-6


def test_world_latlon_matches_local_metres():
    r = G.georeference_bbox([0.5, 0.4, 0.7, 0.6], IMX708, pose(), now=NOW)
    dn = (r.world_lat - LAT) * M_PER_DEG_LAT
    de = (r.world_lon - LON) * M_PER_DEG_LAT * math.cos(math.radians(LAT))
    assert de == pytest.approx(r.local_x, abs=0.05)
    assert dn == pytest.approx(r.local_y, abs=0.05)


def test_explicit_origin_changes_local_but_not_world():
    a = G.georeference_bbox([0.5, 0.4, 0.7, 0.6], IMX708, pose(), now=NOW)
    b = G.georeference_bbox([0.5, 0.4, 0.7, 0.6], IMX708, pose(), now=NOW,
                            origin=(LAT - 0.001, LON))
    assert (a.world_lat, a.world_lon) == (b.world_lat, b.world_lon)
    assert b.local_y == pytest.approx(a.local_y + 0.001 * M_PER_DEG_LAT, abs=0.2)


def test_uncertainty_has_named_terms_and_grows_with_off_nadir():
    centre = G.georeference_bbox([0.45, 0.45, 0.55, 0.55], IMX708, pose(), now=NOW)
    edge = G.georeference_bbox([0.0, 0.0, 0.1, 0.1], IMX708, pose(), now=NOW)
    assert set(centre.uncertainty_terms) == {
        "terrain_m", "gnss_m", "heading_m", "attitude_m", "quantisation_m"}
    assert centre.position_uncertainty_m > 0
    assert edge.position_uncertainty_m > centre.position_uncertainty_m
    # RSS check on the centre result
    rss = math.sqrt(sum(v * v for v in centre.uncertainty_terms.values()))
    assert centre.position_uncertainty_m == pytest.approx(rss, rel=1e-3)


def test_unknown_gnss_accuracy_assumes_plain_gnss_not_rtk():
    r = G.georeference_bbox([0.45, 0.45, 0.55, 0.55], IMX708, pose(h_acc_m=None), now=NOW)
    assert r.uncertainty_terms["gnss_m"] == G.DEFAULT_GNSS_H_ACC_M


def test_high_uncertainty_is_flagged_but_still_returned():
    r = G.georeference_bbox([0.45, 0.45, 0.55, 0.55], IMX708, pose(h_acc_m=9.0), now=NOW)
    assert r.ok and r.status == G.FLAGGED_UNCERTAINTY_HIGH
    assert r.world_lat is not None and r.position_uncertainty_m > G.DEFAULT_FLAG_UNCERTAINTY_M


# ---- fail-closed pose validation -------------------------------------------------

BAD_POSES = {
    "missing": None,
    "nan_lat": pose(lat=float("nan")),
    "inf_alt": pose(alt_agl_m=float("inf")),
    "lat_range": pose(lat=91.0),
    "lon_range": pose(lon=-181.0),
    "null_island": pose(lat=0.0, lon=0.0),
    "alt_zero": pose(alt_agl_m=0.0),
    "alt_negative": pose(alt_agl_m=-5.0),
    "alt_too_high": pose(alt_agl_m=500.0),
    "heading_range": pose(heading_deg=400.0),
    "nan_heading": pose(heading_deg=float("nan")),
    "roll_too_big": pose(roll_deg=40.0),
    "pitch_too_big": pose(pitch_deg=-40.0),
    "neg_hacc": pose(h_acc_m=-1.0),
}


@pytest.mark.parametrize("name", sorted(BAD_POSES))
def test_invalid_pose_is_rejected_with_no_position(name):
    r = G.georeference_bbox([0.4, 0.4, 0.6, 0.6], IMX708, BAD_POSES[name], now=NOW)
    assert not r.ok
    assert r.status in (G.REJECTED_POSE_INVALID, G.REJECTED_POSE_STALE)
    assert r.world_lat is None and r.world_lon is None
    assert r.local_x is None and r.position_uncertainty_m is None


def test_stale_pose_rejected():
    r = G.georeference_bbox([0.4, 0.4, 0.6, 0.6], IMX708, pose(timestamp=NOW - 5.0), now=NOW)
    assert r.status == G.REJECTED_POSE_STALE and not r.ok


def test_unstamped_pose_is_stale_not_fresh():
    r = G.georeference_bbox([0.4, 0.4, 0.6, 0.6], IMX708, pose(timestamp=0.0), now=NOW)
    assert r.status == G.REJECTED_POSE_STALE


def test_future_pose_rejected():
    r = G.georeference_bbox([0.4, 0.4, 0.6, 0.6], IMX708, pose(timestamp=NOW + 60), now=NOW)
    assert not r.ok


def test_pose_far_from_frame_time_rejected():
    r = G.georeference_bbox([0.4, 0.4, 0.6, 0.6], IMX708, pose(), now=NOW, frame_ts=NOW - 3.0)
    assert r.status == G.REJECTED_POSE_STALE
    ok = G.georeference_bbox([0.4, 0.4, 0.6, 0.6], IMX708, pose(), now=NOW, frame_ts=NOW - 0.2)
    assert ok.ok


@pytest.mark.parametrize("bbox", [
    [0.6, 0.4, 0.4, 0.6], [0.0, 0.0, 0.0, 0.0], [-0.1, 0.1, 0.5, 0.5], [0.1, 0.1, 1.5, 0.5],
    [float("nan"), 0.1, 0.5, 0.5], [0.1, 0.1, 0.5], "abc", None,
])
def test_bad_bbox_rejected(bbox):
    r = G.georeference_bbox(bbox, IMX708, pose(), now=NOW)
    assert not r.ok and r.status == G.REJECTED_BAD_BBOX


def test_validate_pose_reports_all_reasons():
    chk = G.validate_pose(pose(alt_agl_m=0.0, roll_deg=50.0, timestamp=NOW - 9), now=NOW)
    assert not chk.valid and chk.stale
    assert len(chk.reasons) >= 3


# ---- Detection integration -----------------------------------------------------

def test_detection_new_fields_default_none_and_serialisation_unchanged():
    d = Detection(label="weed", confidence=0.9, bbox=(0.1, 0.1, 0.2, 0.2))
    assert d.world_lat is None and d.local_x is None and d.position_uncertainty_m is None
    out = d.to_dict()
    for k in ("world_lat", "world_lon", "local_x", "local_y", "position_uncertainty_m",
              "georef_status"):
        assert k not in out
    assert d.may_drive_treatment is False


def test_georeference_detection_sets_fields_and_mirrors_legacy():
    d = Detection(label="weed", confidence=0.9, bbox=(0.5, 0.4, 0.7, 0.6), validated_locally=True)
    res = G.georeference_detection(d, IMX708, pose(), now=NOW)
    assert res.ok and d.georef_status == G.OK
    assert d.world_lat == d.lat and d.world_lon == d.lon
    assert d.position_uncertainty_m == pytest.approx(d.position_error_m, abs=0.01)
    assert d.has_position
    out = d.to_dict()
    assert {"world_lat", "world_lon", "local_x", "local_y", "position_uncertainty_m",
            "georef_status", "lat", "lon"} <= set(out)
    # georeferencing never grants treatment eligibility
    assert d.in_treatment_zone is None and d.may_drive_treatment is False


def test_rerun_with_bad_pose_clears_previous_position():
    d = Detection(label="weed", confidence=0.9, bbox=(0.5, 0.4, 0.7, 0.6))
    G.georeference_detection(d, IMX708, pose(), now=NOW)
    assert d.has_position
    G.georeference_detection(d, IMX708, pose(timestamp=NOW - 30), now=NOW)
    assert not d.has_position
    assert d.world_lat is None and d.local_x is None and d.position_uncertainty_m is None
    assert d.georef_status == G.REJECTED_POSE_STALE and d.geo_error


def test_pose_from_snapshot():
    snap = TelemetrySnapshot(timestamp=NOW, lat=LAT, lon=LON, alt_rel_m=ALT, roll_deg=1.0,
                             pitch_deg=-2.0, yaw_deg=370.0)
    p = G.pose_from_snapshot(snap)
    assert p.heading_deg == pytest.approx(10.0) and p.alt_agl_m == ALT
    assert G.validate_pose(p, now=NOW).valid
    assert G.pose_from_snapshot(TelemetrySnapshot()) is None
    # missing attitude -> NaN -> invalid, not a made-up level hover
    partial = TelemetrySnapshot(timestamp=NOW, lat=LAT, lon=LON, alt_rel_m=ALT)
    assert not G.validate_pose(G.pose_from_snapshot(partial), now=NOW).valid
