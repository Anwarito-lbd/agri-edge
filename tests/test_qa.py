"""QA check tests.

These matter more than they look: the QA thresholds decide what data survives a
flight. A threshold that silently never fires is worse than no check at all,
because it produces the appearance of quality control.
"""

import numpy as np
import pytest

from agri_edge.config import QAConfig
from agri_edge.qa.checks import (
    Severity,
    check_attitude,
    check_bands,
    check_blur,
    check_exposure,
    check_gnss,
    laplacian_variance,
    run_qa,
)
from agri_edge.telemetry.mavlink_link import (
    GPS_FIX_2D,
    GPS_FIX_3D,
    GPS_FIX_RTK_FIXED,
    TelemetrySnapshot,
)


def sharp_image(seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(40, 200, size=(120, 160, 3), dtype=np.uint8)


def flat_image(value=128):
    return np.full((120, 160, 3), value, dtype=np.uint8)


def good_telemetry(**kw):
    defaults = dict(
        timestamp=1.0,
        lat=50.0,
        lon=-105.0,
        alt_rel_m=100.0,
        roll_deg=0.5,
        pitch_deg=0.5,
        fix_type=GPS_FIX_RTK_FIXED,
        satellites=18,
        hdop=0.7,
    )
    defaults.update(kw)
    return TelemetrySnapshot(**defaults)


class TestLaplacianVariance:
    def test_noise_has_higher_variance_than_flat(self):
        assert laplacian_variance(sharp_image()) > laplacian_variance(flat_image())

    def test_flat_image_is_zero(self):
        assert laplacian_variance(flat_image()) == pytest.approx(0.0)

    def test_handles_grayscale(self):
        gray = np.random.default_rng(1).integers(0, 255, size=(50, 50), dtype=np.uint8)
        assert laplacian_variance(gray) > 0

    def test_handles_five_band_stack(self):
        stack = np.random.default_rng(2).integers(0, 255, size=(50, 50, 5), dtype=np.uint8)
        assert laplacian_variance(stack) > 0

    def test_band_count_does_not_dilute_sharpness(self):
        """Regression: collapsing bands to luminance first suppressed sharpness.

        Averaging N bands averages N largely independent noise/texture fields,
        scaling the measured variance by roughly 1/N. A sharp 5-band frame then
        scored a fifth of its true sharpness and was rejected as blurred. Blur is
        geometric and present in every band, so the metric takes the sharpest band.
        """
        rng = np.random.default_rng(7)
        one_band = rng.integers(40, 200, size=(80, 80, 1), dtype=np.uint8)
        five_band = np.repeat(one_band, 5, axis=2)
        # Give each band its own independent noise, as a real payload would.
        five_band = np.clip(
            five_band.astype(np.int32) + rng.integers(-20, 20, size=five_band.shape), 0, 255
        ).astype(np.uint8)

        v1 = laplacian_variance(one_band)
        v5 = laplacian_variance(five_band)
        # Within a factor of two, not a factor of five.
        assert v5 > v1 * 0.5, f"5-band sharpness {v5:.1f} diluted vs 1-band {v1:.1f}"

    def test_sharpest_band_wins(self):
        """A frame with one sharp band and one flat band is not blurred."""
        rng = np.random.default_rng(11)
        sharp = rng.integers(40, 200, size=(60, 60), dtype=np.uint8)
        flat = np.full((60, 60), 128, dtype=np.uint8)
        stacked = np.stack([flat, sharp], axis=2)
        assert laplacian_variance(stacked) == pytest.approx(laplacian_variance(sharp))

    def test_tiny_image_does_not_crash(self):
        assert laplacian_variance(np.zeros((2, 2), dtype=np.uint8)) == 0.0

    def test_rejects_bad_shape(self):
        with pytest.raises(ValueError):
            laplacian_variance(np.zeros((2, 2, 2, 2), dtype=np.uint8))


class TestBlur:
    def test_sharp_passes(self):
        assert check_blur(sharp_image(), threshold=10.0).severity is Severity.OK

    def test_flat_fails(self):
        r = check_blur(flat_image(), threshold=100.0)
        assert r.severity is Severity.FAIL
        assert "motion blur" in r.detail

    def test_marginal_warns(self):
        img = sharp_image()
        v = laplacian_variance(img)
        # Place the threshold so the value lands in the 1.0-1.5x warning band.
        r = check_blur(img, threshold=v / 1.2)
        assert r.severity is Severity.WARN


class TestExposure:
    def test_midtone_passes(self):
        assert check_exposure(flat_image(128), 0.05, 0.05).severity is Severity.OK

    def test_blown_highlights_fail(self):
        r = check_exposure(flat_image(255), 0.05, 0.05)
        assert r.severity is Severity.FAIL
        assert "highlight" in r.detail

    def test_crushed_shadows_fail(self):
        r = check_exposure(flat_image(0), 0.05, 0.05)
        assert r.severity is Severity.FAIL
        assert "shadow" in r.detail

    def test_partial_clipping_warns(self):
        img = flat_image(128)
        # Clip ~3% of pixels: over half the 5% threshold, so WARN not FAIL.
        n = int(img[:, :, 0].size * 0.03)
        flat = img.reshape(-1, 3)
        flat[:n] = 255
        r = check_exposure(flat.reshape(img.shape), 0.05, 0.05)
        assert r.severity is Severity.WARN


class TestGnss:
    def test_rtk_fixed_passes(self):
        assert check_gnss(good_telemetry(), 3, True, 2.0, 8).severity is Severity.OK

    def test_below_min_fix_fails(self):
        r = check_gnss(good_telemetry(fix_type=GPS_FIX_2D), 3, False, 2.0, 8)
        assert r.severity is Severity.FAIL
        assert "2d" in r.detail

    def test_rtk_required_but_only_3d_fails(self):
        r = check_gnss(good_telemetry(fix_type=GPS_FIX_3D), 3, True, 2.0, 8)
        assert r.severity is Severity.FAIL
        assert "base station" in r.detail

    def test_rtk_not_required_and_3d_passes(self):
        assert check_gnss(good_telemetry(fix_type=GPS_FIX_3D), 3, False, 2.0, 8).severity is Severity.OK

    def test_high_hdop_warns(self):
        r = check_gnss(good_telemetry(hdop=5.0), 3, False, 2.0, 8)
        assert r.severity is Severity.WARN

    def test_few_satellites_warns(self):
        r = check_gnss(good_telemetry(satellites=4), 3, False, 2.0, 8)
        assert r.severity is Severity.WARN


class TestBands:
    def test_no_requirement_passes(self):
        assert check_bands(["red"], []).severity is Severity.OK

    def test_all_present_passes(self):
        assert check_bands(["red", "nir"], ["red", "nir"]).severity is Severity.OK

    def test_missing_band_fails(self):
        r = check_bands(["red", "green"], ["red", "green", "nir"])
        assert r.severity is Severity.FAIL
        assert "nir" in r.detail


class TestAttitude:
    def test_level_passes(self):
        assert check_attitude(good_telemetry()).severity is Severity.OK

    def test_tilted_warns(self):
        r = check_attitude(good_telemetry(roll_deg=15.0, pitch_deg=10.0))
        assert r.severity is Severity.WARN
        assert "off-nadir" in r.detail

    def test_missing_attitude_is_not_a_failure(self):
        r = check_attitude(TelemetrySnapshot(timestamp=1.0))
        assert r.severity is Severity.OK


class TestRunQa:
    def test_good_frame_passes_everything(self):
        cfg = QAConfig(blur_threshold=10.0)
        report = run_qa(sharp_image(), good_telemetry(), cfg, bands_present=["red", "green", "blue"])
        assert report.passed
        assert report.severity is Severity.OK

    def test_report_severity_is_the_worst_check(self):
        cfg = QAConfig(blur_threshold=1e9)  # guarantee a blur failure
        report = run_qa(sharp_image(), good_telemetry(), cfg)
        assert report.severity is Severity.FAIL
        assert {f.name for f in report.failures} == {"blur"}

    def test_missing_band_fails_the_whole_report(self):
        cfg = QAConfig(blur_threshold=10.0, required_bands=["red", "nir"])
        report = run_qa(sharp_image(), good_telemetry(), cfg, bands_present=["red", "green", "blue"])
        assert not report.passed
        assert "bands" in {f.name for f in report.failures}

    def test_report_serialises(self):
        cfg = QAConfig(blur_threshold=10.0)
        d = run_qa(sharp_image(), good_telemetry(), cfg).to_dict()
        assert d["severity"] == "ok"
        assert {c["name"] for c in d["checks"]} == {"blur", "exposure", "gnss", "bands", "attitude"}
