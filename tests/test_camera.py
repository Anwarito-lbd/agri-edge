"""Camera tests, chiefly the channel-order handling.

Channel order gets its own test file because it is the kind of bug that costs
days: feeding BGR to a model trained on RGB does not crash, does not warn, and
does not obviously misbehave. It just detects a bit worse, and nobody suspects
the camera.
"""

import numpy as np
import pytest

from agri_edge.capture.camera import Frame, Picamera2Camera, SimulatedCamera, swap_rb
from agri_edge.config import CaptureConfig
from agri_edge.telemetry.mavlink_link import SimulatedTelemetry


class TestSwapRb:
    def test_swaps_red_and_blue_leaves_green(self):
        img = np.zeros((2, 2, 3), dtype=np.uint8)
        img[:, :, 0] = 10   # R
        img[:, :, 1] = 20   # G
        img[:, :, 2] = 30   # B
        out = swap_rb(img)
        assert (out[:, :, 0] == 30).all()
        assert (out[:, :, 1] == 20).all()
        assert (out[:, :, 2] == 10).all()

    def test_is_its_own_inverse(self):
        rng = np.random.default_rng(0)
        img = rng.integers(0, 255, (4, 4, 3), dtype=np.uint8)
        np.testing.assert_array_equal(swap_rb(swap_rb(img)), img)

    def test_does_not_mutate_input(self):
        """An in-place swap would corrupt the caller's frame."""
        img = np.zeros((2, 2, 3), dtype=np.uint8)
        img[:, :, 0] = 10
        img[:, :, 2] = 30
        swap_rb(img)
        assert img[0, 0, 0] == 10 and img[0, 0, 2] == 30

    def test_grayscale_passes_through(self):
        img = np.zeros((4, 4), dtype=np.uint8)
        np.testing.assert_array_equal(swap_rb(img), img)

    def test_single_channel_3d_passes_through(self):
        img = np.zeros((4, 4, 1), dtype=np.uint8)
        np.testing.assert_array_equal(swap_rb(img), img)

    def test_extra_bands_are_preserved(self):
        """A 5-band multispectral stack keeps bands 3 and 4 untouched."""
        img = np.zeros((2, 2, 5), dtype=np.uint8)
        for i in range(5):
            img[:, :, i] = i * 10
        out = swap_rb(img)
        assert (out[:, :, 0] == 20).all()   # was band 2
        assert (out[:, :, 2] == 0).all()    # was band 0
        assert (out[:, :, 3] == 30).all()   # untouched
        assert (out[:, :, 4] == 40).all()   # untouched


class TestPicamera2CameraConfig:
    """Construction-time behaviour, testable without a camera attached."""

    def test_swap_defaults_on(self):
        """Picamera2's 'RGB888' delivers BGR, so the default must swap."""
        assert Picamera2Camera(resolution=(640, 480)).swap_red_blue is True

    def test_video_mode_defaults_on(self):
        """Still config reconfigures the sensor per shot -- far too slow."""
        assert Picamera2Camera(resolution=(640, 480)).video_mode is True

    def test_settings_are_overridable(self):
        cam = Picamera2Camera(resolution=(640, 480), swap_red_blue=False, video_mode=False)
        assert cam.swap_red_blue is False
        assert cam.video_mode is False

    def test_capture_without_start_raises(self):
        cam = Picamera2Camera(resolution=(640, 480))
        with pytest.raises(RuntimeError, match="not started"):
            cam.capture(SimulatedTelemetry().snapshot())


class TestCaptureConfigDefaults:
    def test_swap_red_blue_default(self):
        assert CaptureConfig().swap_red_blue is True

    def test_video_mode_default(self):
        assert CaptureConfig().video_mode is True

    def test_build_camera_passes_settings_through(self):
        from agri_edge.capture.camera import build_camera

        cfg = CaptureConfig(swap_red_blue=False, video_mode=False)
        cam = build_camera(cfg, simulated=False)
        assert cam.swap_red_blue is False
        assert cam.video_mode is False

    def test_build_camera_simulated_ignores_hardware_settings(self):
        from agri_edge.capture.camera import build_camera

        cam = build_camera(CaptureConfig(), simulated=True, bands=["red", "green", "blue"])
        assert isinstance(cam, SimulatedCamera)


class TestSimulatedCamera:
    def test_produces_requested_bands(self):
        cam = SimulatedCamera(resolution=(64, 48), bands=["red", "green", "blue", "nir"])
        frame = cam.capture(SimulatedTelemetry().snapshot())
        assert frame.image.shape == (48, 64, 4)
        assert frame.bands == ["red", "green", "blue", "nir"]

    def test_sequence_increments(self):
        cam = SimulatedCamera(resolution=(32, 32))
        t = SimulatedTelemetry().snapshot()
        assert cam.capture(t).sequence == 1
        assert cam.capture(t).sequence == 2

    def test_nir_exceeds_red_over_canopy(self):
        """Healthy vegetation reflects NIR strongly and absorbs red.

        If this inverts, NDVI goes negative over crops and every downstream
        index is meaningless -- so it is worth pinning.
        """
        cam = SimulatedCamera(resolution=(64, 64), bands=["red", "nir"])
        img = cam.capture(SimulatedTelemetry().snapshot()).image
        assert img[:, :, 1].mean() > img[:, :, 0].mean()

    def test_blur_sigma_reduces_sharpness(self):
        from agri_edge.qa.checks import laplacian_variance

        t = SimulatedTelemetry().snapshot()
        sharp = SimulatedCamera(resolution=(64, 64), seed=1).capture(t).image
        blurred = SimulatedCamera(resolution=(64, 64), seed=1, blur_sigma=3.0).capture(t).image
        assert laplacian_variance(blurred) < laplacian_variance(sharp)

    def test_frame_band_count_property(self):
        cam = SimulatedCamera(resolution=(32, 32), bands=["red", "green", "blue"])
        assert cam.capture(SimulatedTelemetry().snapshot()).band_count == 3


class TestFrame:
    def test_band_count_for_grayscale(self):
        f = Frame(
            image=np.zeros((4, 4), dtype=np.uint8),
            telemetry=SimulatedTelemetry().snapshot(),
            captured_at=0.0,
            sequence=1,
            bands=["mono"],
        )
        assert f.band_count == 1
