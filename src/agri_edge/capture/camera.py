"""Camera abstraction.

Two backends: Picamera2 on real hardware, and a synthetic generator that produces
plausible field imagery so the whole pipeline -- QA, inference, spooling -- can be
exercised and tested on a laptop with no camera attached.

The synthetic backend is not a stub. It is used to verify that QA thresholds
behave the way the field crew expects before anyone trusts them at 100 m AGL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from typing import Any

import numpy as np

from ..telemetry.mavlink_link import TelemetrySnapshot


@dataclass
class Frame:
    """One captured frame plus the provenance needed to use it later."""

    image: np.ndarray
    telemetry: TelemetrySnapshot
    captured_at: float
    sequence: int
    bands: list[str]

    @property
    def band_count(self) -> int:
        return 1 if self.image.ndim == 2 else self.image.shape[2]


class Camera:
    def start(self) -> None:  # pragma: no cover - trivial
        pass

    def stop(self) -> None:  # pragma: no cover - trivial
        pass

    def capture(self, telem: TelemetrySnapshot) -> Frame:
        raise NotImplementedError


class SimulatedCamera(Camera):
    """Generates synthetic multispectral field imagery.

    The scene is a crop canopy with row structure, a vigour gradient, and an
    optional stressed patch -- enough structure that vegetation indices produce
    meaningful spatial variation rather than noise.

    `blur_sigma` and `exposure_bias` exist so tests can drive the QA checks into
    their failure modes deliberately.
    """

    def __init__(
        self,
        resolution: tuple[int, int] = (640, 480),
        bands: list[str] | None = None,
        blur_sigma: float = 0.0,
        exposure_bias: float = 0.0,
        seed: int = 0,
    ):
        self.resolution = resolution
        self.bands = bands or ["red", "green", "blue"]
        self.blur_sigma = blur_sigma
        self.exposure_bias = exposure_bias
        self._rng = np.random.default_rng(seed)
        self._seq = 0

    def capture(self, telem: TelemetrySnapshot) -> Frame:
        w, h = self.resolution
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)

        # Crop rows running north-south, ~24 px apart.
        rows = 0.5 + 0.5 * np.sin(xx * (2 * np.pi / 24.0))

        # Vigour gradient: healthier toward the top-left of the field.
        vigour = 1.0 - 0.4 * (yy / h) - 0.2 * (xx / w)

        # A stressed ellipse, the thing a real survey is looking for.
        cy, cx = h * 0.65, w * 0.35
        stress = np.exp(-(((yy - cy) / (h * 0.12)) ** 2 + ((xx - cx) / (w * 0.12)) ** 2))
        vigour = vigour * (1.0 - 0.6 * stress)

        planes = []
        for band in self.bands:
            if band in ("nir", "near-infrared"):
                # Healthy canopy reflects strongly in NIR.
                base = 60 + 170 * vigour * rows
            elif band in ("red",):
                # Chlorophyll absorbs red, so vigour *reduces* red reflectance.
                base = 140 - 90 * vigour * rows
            elif band in ("red-edge", "rededge"):
                base = 90 + 90 * vigour * rows
            elif band in ("green",):
                base = 90 + 60 * vigour * rows
            else:
                base = 80 + 70 * vigour * rows

            noise = self._rng.normal(0, 3.0, size=base.shape)
            planes.append(base + noise + self.exposure_bias)

        img = np.stack(planes, axis=2) if len(planes) > 1 else planes[0]

        if self.blur_sigma > 0:
            img = _box_blur(img, int(max(1, round(self.blur_sigma * 3))))

        img = np.clip(img, 0, 255).astype(np.uint8)
        self._seq += 1
        return Frame(
            image=img,
            telemetry=telem,
            captured_at=time.time(),
            sequence=self._seq,
            bands=list(self.bands),
        )


def _box_blur(img: np.ndarray, k: int) -> np.ndarray:
    """Separable box blur via cumulative sums. Used only to synthesise blur."""
    if k < 2:
        return img
    out = img.astype(np.float64)
    for axis in (0, 1):
        n = out.shape[axis]
        k_eff = min(k, n)
        cs = np.cumsum(out, axis=axis)
        pad_shape = list(out.shape)
        pad_shape[axis] = 1
        cs = np.concatenate([np.zeros(pad_shape), cs], axis=axis)
        sl_hi = [slice(None)] * out.ndim
        sl_lo = [slice(None)] * out.ndim
        sl_hi[axis] = slice(k_eff, n + 1)
        sl_lo[axis] = slice(0, n + 1 - k_eff)
        windowed = (cs[tuple(sl_hi)] - cs[tuple(sl_lo)]) / k_eff
        # Re-pad back to the original length by edge replication.
        reps = n - windowed.shape[axis]
        if reps > 0:
            edge_sl = [slice(None)] * out.ndim
            edge_sl[axis] = slice(-1, None)
            pad = np.repeat(windowed[tuple(edge_sl)], reps, axis=axis)
            windowed = np.concatenate([windowed, pad], axis=axis)
        out = windowed
    return out


def swap_rb(image: np.ndarray) -> np.ndarray:
    """Swap the red and blue channels of an HxWx3+ array.

    Kept separate and tested because getting this wrong is invisible: a model fed
    BGR instead of RGB does not crash and does not obviously misbehave. It just
    detects slightly worse, in a way nobody attributes to channel order for days.
    """
    if image.ndim != 3 or image.shape[2] < 3:
        return image
    out = image.copy()
    out[:, :, 0], out[:, :, 2] = image[:, :, 2], image[:, :, 0]
    return out


class Picamera2Camera(Camera):
    """Raspberry Pi camera backend. Requires the optional `camera` extra.

    CHANNEL ORDER
    -------------
    Picamera2's format names describe the byte layout, not the numpy channel
    order, and the two are reversed: requesting **"RGB888" yields arrays whose
    channels are B, G, R**, and "BGR888" yields R, G, B. This trips up nearly
    everyone, and it fails silently -- the detector still runs, still emits
    boxes, and is simply a bit worse.

    This class therefore requests "RGB888" and swaps by default, so `capture()`
    returns genuine RGB, which is what the model was trained on. If a future
    Picamera2 changes the convention, set `swap_red_blue=False` rather than
    editing the pipeline.

    Verify on the real hardware once, with `verify_channel_order()`.
    """

    def __init__(
        self,
        resolution: tuple[int, int],
        bands: list[str] | None = None,
        swap_red_blue: bool = True,
        video_mode: bool = True,
    ):
        self.resolution = resolution
        self.bands = bands or ["red", "green", "blue"]
        self.swap_red_blue = swap_red_blue
        # Video configuration gives a continuous stream at a steady frame rate.
        # Still configuration reconfigures the sensor per shot, which costs
        # hundreds of milliseconds -- fine for a survey grid, far too slow for
        # continuous detection.
        self.video_mode = video_mode
        # Any, not Picamera2: the library is an optional extra and only
        # exists on the Pi, so the annotation cannot name it.
        self._cam: Any = None
        self._seq = 0

    def start(self) -> None:  # pragma: no cover - requires hardware
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "picamera2 is required for hardware capture. "
                "Install with: pip install 'agri-edge[camera]'"
            ) from exc
        self._cam = Picamera2()
        maker = (
            self._cam.create_video_configuration
            if self.video_mode
            else self._cam.create_still_configuration
        )
        config = maker(main={"size": self.resolution, "format": "RGB888"})
        self._cam.configure(config)
        self._cam.start()

    def stop(self) -> None:  # pragma: no cover - requires hardware
        if self._cam is not None:
            self._cam.stop()
            self._cam = None

    def capture(self, telem: TelemetrySnapshot) -> Frame:  # pragma: no cover - hardware
        if self._cam is None:
            raise RuntimeError("Camera not started.")
        arr = self._cam.capture_array("main")

        # Picamera2 may hand back a 4-channel buffer (XBGR); drop alpha.
        if arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[:, :, :3]
        if self.swap_red_blue:
            arr = swap_rb(arr)

        self._seq += 1
        return Frame(
            image=arr,
            telemetry=telem,
            captured_at=time.time(),
            sequence=self._seq,
            bands=list(self.bands),
        )

    def verify_channel_order(self) -> dict:  # pragma: no cover - requires hardware
        """Capture one frame and report per-channel means.

        Point the camera at something strongly and unambiguously red, then call
        this. `red` should be the largest mean. If `blue` is largest, the swap
        setting is wrong for your Picamera2 version -- flip `swap_red_blue`.

        Worth doing once on real hardware: it takes a minute, and the failure it
        catches is otherwise near-undetectable.
        """
        if self._cam is None:
            raise RuntimeError("Camera not started.")
        raw = self._cam.capture_array("main")
        if raw.ndim == 3 and raw.shape[2] == 4:
            raw = raw[:, :, :3]
        delivered = swap_rb(raw) if self.swap_red_blue else raw

        means = {
            "red": float(delivered[:, :, 0].mean()),
            "green": float(delivered[:, :, 1].mean()),
            "blue": float(delivered[:, :, 2].mean()),
        }
        dominant = max(means, key=means.get)
        return {
            "swap_red_blue": self.swap_red_blue,
            "channel_means": means,
            "dominant_channel": dominant,
            "hint": (
                f"Dominant channel is '{dominant}'. Pointing at a red subject, this "
                f"should be 'red'. If it is 'blue', set swap_red_blue="
                f"{not self.swap_red_blue}."
            ),
        }


def build_camera(cfg, simulated: bool = False, bands: list[str] | None = None) -> Camera:
    if simulated:
        # Smaller frames in simulation: the point is pipeline behaviour, not pixels.
        return SimulatedCamera(resolution=(640, 480), bands=bands)
    return Picamera2Camera(
        resolution=cfg.resolution,
        bands=bands,
        swap_red_blue=getattr(cfg, "swap_red_blue", True),
        video_mode=getattr(cfg, "video_mode", True),
    )
