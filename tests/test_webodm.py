"""Tests for the WebODM submission path.

The HTTP part is incidental. The part that matters is **geotagging**: spooled
frames are `.npy` plus a JSON sidecar and carry no EXIF whatsoever, while WebODM
reads position from EXIF. Submit raw exports and you get a confident, completely
wrong reconstruction — the most expensive silent failure in this pipeline.

So most of these tests are about EXIF round-tripping and about refusing to
submit frames whose position is untrustworthy.

WebODM itself needs Docker, which is absent here, so the client is exercised
against a stub speaking the same shapes. That checks our requests, not WebODM's
acceptance of them.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workstation"))

from webodm_submit import (  # noqa: E402
    _to_dms,
    prepare_images,
    read_gps_exif,
    write_geotagged_jpeg,
)

LAT, LON, ALT = 49.8951, -97.1384, 260.0


def _sidecar(seq=1, lat=LAT, lon=LON, alt=ALT, gnss="ok"):
    return {
        "entry_id": f"e{seq}",
        "sequence": seq,
        "site": "s",
        "field_id": "f",
        "telemetry": {"lat": lat, "lon": lon, "alt_msl_m": alt, "alt_rel_m": 30.0},
        "qa": {"passed": gnss == "ok", "checks": [{"name": "gnss", "severity": gnss}]},
        "detections": [],
    }


def _spool(tmp_path, sidecars, shape=(16, 16, 3), dtype=np.uint8):
    d = tmp_path / "spool"
    d.mkdir(parents=True, exist_ok=True)
    for i, sc in enumerate(sidecars):
        stem = f"entry{i:03d}"
        (d / f"{stem}.json").write_text(json.dumps(sc), encoding="utf-8")
        np.save(d / f"{stem}.npy", np.full(shape, 80, dtype=dtype))
    return d


class TestDMS:
    def test_known_conversion(self):
        d, m, s = _to_dms(49.5)
        assert (float(d), float(m), float(s)) == (49.0, 30.0, 0.0)

    def test_sign_is_dropped_because_the_ref_carries_it(self):
        """EXIF stores magnitude plus N/S/E/W, never a negative degree."""
        assert [float(v) for v in _to_dms(-97.1384)] == [float(v) for v in _to_dms(97.1384)]


class TestGeotagging:
    def test_round_trips_to_sub_metre(self, tmp_path):
        p = write_geotagged_jpeg(np.zeros((16, 16, 3), np.uint8), LAT, LON, ALT,
                                 tmp_path / "a.jpg")
        lat, lon, alt = read_gps_exif(p)
        assert lat == pytest.approx(LAT, abs=1e-6)
        assert lon == pytest.approx(LON, abs=1e-6)
        assert alt == pytest.approx(ALT, abs=0.01)

    @pytest.mark.parametrize(
        "lat,lon",
        [(49.8951, -97.1384), (-33.87, 151.21), (51.5, -0.12), (-1.29, 36.82)],
    )
    def test_all_four_hemispheres(self, tmp_path, lat, lon):
        """A sign error survives testing in one hemisphere and fails in another."""
        p = write_geotagged_jpeg(np.zeros((8, 8, 3), np.uint8), lat, lon, 100.0,
                                 tmp_path / "h.jpg")
        got_lat, got_lon, _ = read_gps_exif(p)
        assert got_lat == pytest.approx(lat, abs=1e-6)
        assert got_lon == pytest.approx(lon, abs=1e-6)

    def test_sixteen_bit_frames_are_scaled_not_truncated(self, tmp_path):
        """A dim 16-bit frame naively cast to uint8 comes out black."""
        arr = np.full((16, 16, 3), 4000, np.uint16)
        arr[0, 0] = 40000
        p = write_geotagged_jpeg(arr, LAT, LON, ALT, tmp_path / "b.jpg")
        from PIL import Image

        assert np.asarray(Image.open(p)).max() > 200

    def test_extra_bands_are_dropped(self, tmp_path):
        """Five-band multispectral frames must not break the JPEG encoder."""
        p = write_geotagged_jpeg(np.zeros((16, 16, 5), np.uint8), LAT, LON, ALT,
                                 tmp_path / "c.jpg")
        from PIL import Image

        assert np.asarray(Image.open(p)).shape[2] == 3

    def test_plain_jpeg_has_no_gps(self, tmp_path):
        """Proves read_gps_exif is actually reading, not always returning a value."""
        from PIL import Image

        plain = tmp_path / "plain.jpg"
        Image.fromarray(np.zeros((8, 8, 3), np.uint8)).save(plain)
        assert read_gps_exif(plain) is None


class TestPrepare:
    def test_writes_one_jpeg_per_frame(self, tmp_path):
        spool = _spool(tmp_path, [_sidecar(i) for i in range(3)])
        res = prepare_images(spool, tmp_path / "out")
        assert len(res.written) == 3
        assert all(p.exists() for p in res.written)

    def test_every_output_carries_position(self, tmp_path):
        """The whole point. An ungeotagged set silently ruins the reconstruction."""
        spool = _spool(tmp_path, [_sidecar(i) for i in range(3)])
        for p in prepare_images(spool, tmp_path / "out").written:
            assert read_gps_exif(p) is not None

    def test_failed_gnss_is_refused_by_default(self, tmp_path):
        """Bad positions do not average out in a bundle adjustment."""
        spool = _spool(tmp_path, [_sidecar(0), _sidecar(1, gnss="fail"), _sidecar(2)])
        res = prepare_images(spool, tmp_path / "out")
        assert len(res.written) == 2
        assert res.skipped_failed_gnss == 1

    def test_failed_gnss_can_be_included_deliberately(self, tmp_path):
        spool = _spool(tmp_path, [_sidecar(0), _sidecar(1, gnss="fail")])
        res = prepare_images(spool, tmp_path / "out", include_failed_gnss=True)
        assert len(res.written) == 2
        assert res.skipped_failed_gnss == 0

    def test_frames_without_position_are_skipped_not_placed_at_zero(self, tmp_path):
        """Null Island is a real place to nobody, but bundle adjustment believes it."""
        sc = _sidecar(0)
        sc["telemetry"] = {}
        spool = _spool(tmp_path, [sc, _sidecar(1)])
        res = prepare_images(spool, tmp_path / "out")
        assert len(res.written) == 1
        assert res.skipped_no_position == 1

    def test_missing_payload_is_an_error_not_a_crash(self, tmp_path):
        spool = _spool(tmp_path, [_sidecar(0)])
        next(spool.glob("*.npy")).unlink()
        res = prepare_images(spool, tmp_path / "out")
        assert res.written == [] and len(res.errors) == 1

    def test_index_file_is_not_treated_as_a_frame(self, tmp_path):
        spool = _spool(tmp_path, [_sidecar(0)])
        (spool / "index.json").write_text("[]", encoding="utf-8")
        assert len(prepare_images(spool, tmp_path / "out").written) == 1

    def test_msl_altitude_is_preferred_over_relative(self, tmp_path):
        """Relative altitude puts the whole model at the wrong elevation."""
        spool = _spool(tmp_path, [_sidecar(0)])
        p = prepare_images(spool, tmp_path / "out").written[0]
        assert read_gps_exif(p)[2] == pytest.approx(260.0, abs=0.01)

    def test_falls_back_to_relative_altitude_when_msl_is_absent(self, tmp_path):
        sc = _sidecar(0)
        del sc["telemetry"]["alt_msl_m"]
        spool = _spool(tmp_path, [sc])
        p = prepare_images(spool, tmp_path / "out").written[0]
        assert read_gps_exif(p)[2] == pytest.approx(30.0, abs=0.01)
