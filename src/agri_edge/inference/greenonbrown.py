"""Green-on-brown detection: no model, no training set, no accelerator.

Ported from **OpenWeedLocator** (https://github.com/geezacoleman/OpenWeedLocator,
MIT, © 2020 Guy Coleman), which has run this approach on Raspberry Pi weed rigs
in real fields for years. The vegetation indices themselves come from the
published literature — ExG is Woebbecke et al. 1995, MaxG is Jin et al. 2021.

WHY THIS EXISTS ALONGSIDE THE YOLOX MODELS
------------------------------------------
Every trained model in this project has two hard limits: it needs the Hailo NPU
to run tiled at survey altitude, and it can only find what its dataset contained.
This backend has neither limit, and one of its own:

    YOLOX models              green-on-brown
    -----------------------   ------------------------------------------
    needs the AI HAT+         runs on a bare Pi, no accelerator
    knows 5 weed species      knows no species at all
    misses unseen species     finds ANY green, including species nobody
                              has ever labelled
    works in-crop             CANNOT separate weed from crop

**It detects green, not weeds.** On fallow ground, a stubble field or a seedbed
before emergence, green *is* weed and this is the right tool — arguably better
than a detector, because it cannot be surprised by an unfamiliar species. Inside
a standing crop it is close to useless on its own: the crop is green too.

That is why the default label is `vegetation` rather than `weed`. Set
`class_names: [weed]` in config only when operating somewhere that the equivalence
actually holds, and know that you are asserting it.

CONFIDENCE IS NOT A PROBABILITY
-------------------------------
There is no model here and therefore no likelihood. The `confidence` on each
Detection is the mean index strength inside the blob, rescaled to 0-1 across the
threshold range. It ranks detections sensibly — greener blobs score higher — but
it must not be read as "94% sure this is a weed". See `_blob_confidence`.

DEPENDENCIES
------------
Module level is numpy only, so `tests/test_runtime_deps.py` keeps passing and the
Pi runtime stays installable with numpy + PyYAML. OpenCV is imported lazily and
used when present, because its connected-component labelling is orders of
magnitude faster than the numpy fallback on a full 4056x3040 frame. The fallback
exists so the backend is testable and correct without it, not so you would choose
it in flight.
"""

from __future__ import annotations

import logging

import numpy as np

from .engine import Detection, InferenceEngine, ModelMetadata

log = logging.getLogger("agri_edge.inference.greenonbrown")


# ---------------------------------------------------------------------------
# Vegetation indices.
#
# NOTE ON CHANNEL ORDER. OpenWeedLocator takes BGR because it is built on
# OpenCV; this codebase uses RGB throughout (see capture/camera.py). These are
# rewritten for RGB rather than wrapped, because the difference is not uniform:
#
#   ExG   = 2G - R - B          SYMMETRIC in R and B -- a swap is harmless
#   nExG  = (2G-R-B)/(R+G+B)    SYMMETRIC -- numerator and denominator both are
#   ExGR  = ExG - (1.4R - G)    ASYMMETRIC -- a swap silently changes the result
#   MaxG  = 24G - 19R - 2B      ASYMMETRIC
#
# Half of them are symmetric, which is the worst possible split: an R/B mix-up
# leaves the default index and nExG working perfectly while quietly corrupting
# the other two. A bug that half-works is far harder to notice than one that
# fails outright. `tests/test_greenonbrown.py` pins each case down individually.
#
# (MaxG rescales by its own frame maximum, so its asymmetry is invisible on a
# single pixel and only shows up on a real image -- see the test.)
# ---------------------------------------------------------------------------


def _split(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = rgb.astype(np.float32)
    return a[..., 0], a[..., 1], a[..., 2]


def excess_green(rgb: np.ndarray) -> np.ndarray:
    """ExG = 2G - R - B (Woebbecke et al. 1995). Range 0-255."""
    r, g, b = _split(rgb)
    return np.clip(2.0 * g - r - b, 0, 255)


def excess_green_red(rgb: np.ndarray) -> np.ndarray:
    """ExGR = ExG - (1.4R - G). Suppresses reddish soil better than ExG."""
    r, g, _ = _split(rgb)
    return np.clip(excess_green(rgb) - (1.4 * r - g), 0, 255)


def normalised_excess_green(rgb: np.ndarray) -> np.ndarray:
    """ExG normalised by total intensity, so it survives exposure changes.

    The reason to prefer this one outdoors: plain ExG scales with brightness, so
    a threshold tuned at midday fails in cloud. Dividing by (R+G+B) removes most
    of that, which matters when a flight spans changing light.
    """
    r, g, b = _split(rgb)
    total = np.maximum(r + g + b, 1.0)
    return np.clip(((2.0 * g - r - b) / total) * 255.0, 0, 255)


def max_green(rgb: np.ndarray) -> np.ndarray:
    """MaxG = 24G - 19R - 2B (Jin et al. 2021), rescaled to 0-255."""
    r, g, b = _split(rgb)
    out = 24.0 * g - 19.0 * r - 2.0 * b
    peak = float(out.max())
    if peak <= 0:
        return np.zeros(out.shape, dtype=np.float32)
    return np.clip(out / peak * 255.0, 0, 255)


INDICES = {
    "exg": excess_green,
    "exgr": excess_green_red,
    "nexg": normalised_excess_green,
    "maxg": max_green,
}


# ---------------------------------------------------------------------------
# Thresholding
# ---------------------------------------------------------------------------


def threshold_absolute(index: np.ndarray, low: float, high: float) -> np.ndarray:
    """Everything between `low` and `high` is vegetation. Explainable and fast.

    Measured on real nadir imagery this separates far more decisively than the
    adaptive path (mean ExG 59.9 inside the mask vs 1.7 outside, against 20.6 vs
    3.8) at the cost of more fragmentation. It is the default because you can say
    exactly what it did.

    **`high` EXCLUDES, it does not clamp** -- and that is a trap worth stating.
    The indices saturate at 255, so strongly-lit pure vegetation lands exactly
    there; OpenWeedLocator's default upper bound of 250 would therefore discard
    the greenest pixels in the frame. OWL gets away with it because its path
    *clips* to the band rather than filtering on it. Here the default is 255, and
    lowering it removes the strongest vegetation signal first.
    """
    return ((index >= low) & (index <= high)).astype(np.uint8)


def threshold_adaptive(index: np.ndarray, low: float, high: float,
                       block: int = 31, c: float = 2.0) -> np.ndarray:
    """OpenWeedLocator's own path: clip, then local-mean threshold, inverted.

    Worth understanding before trusting, because it reads backwards: on an ExG
    image, "below the local mean" is soil. It works because the clip raises all
    soil to exactly `low`, making background a flat plateau that sits *above*
    `mean - c` in a uniform window and *below* it near a plant. So what it
    actually selects is the transition zone around vegetation — whose bounding
    boxes enclose the plant.

    Verified on real imagery rather than assumed: mean ExG inside the resulting
    mask is 20.6 against 3.8 outside, so it does land on vegetation. It gives
    chunkier, less fragmented blobs than `threshold_absolute`, which is why it is
    offered; it is not the default because it is much harder to reason about.
    """
    clipped = np.clip(index, low, high).astype(np.uint8)
    try:
        import cv2
    except ImportError:  # pragma: no cover - exercised only without the cv extra
        raise RuntimeError(
            "threshold_mode='adaptive' needs OpenCV. Install with "
            "pip install 'agri-edge[cv]', or use threshold_mode='absolute'."
        ) from None
    if block % 2 == 0:
        block += 1  # OpenCV requires an odd block size
    mask = cv2.adaptiveThreshold(
        clipped, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,
        block, c,
    )
    return (mask > 0).astype(np.uint8)


# ---------------------------------------------------------------------------
# Connected components
# ---------------------------------------------------------------------------


def _label_numpy(mask: np.ndarray, max_iterations: int = 512) -> tuple[np.ndarray, int]:
    """Label connected regions with numpy alone, by iterative max-propagation.

    Each foreground pixel starts with a unique id; every pass takes the maximum
    over its 8-neighbourhood until nothing changes, so each region converges to
    the largest id it contains. Correct, vectorised, and much slower than
    OpenCV — convergence takes roughly as many passes as the longest blob is
    wide, so a full-resolution frame with long connected weed rows is genuinely
    expensive.

    Present so this backend works and can be tested with numpy alone. Use OpenCV
    in flight.
    """
    if not mask.any():
        return np.zeros(mask.shape, dtype=np.int32), 0

    ids = np.arange(1, mask.size + 1, dtype=np.int64).reshape(mask.shape)
    lab = np.where(mask > 0, ids, 0)

    for n in range(max_iterations):
        prev = lab
        m = lab
        acc = m.copy()
        acc[1:, :] = np.maximum(acc[1:, :], m[:-1, :])
        acc[:-1, :] = np.maximum(acc[:-1, :], m[1:, :])
        acc[:, 1:] = np.maximum(acc[:, 1:], acc[:, :-1])
        acc[:, :-1] = np.maximum(acc[:, :-1], acc[:, 1:])
        lab = acc * (mask > 0)
        if np.array_equal(lab, prev):
            break
    else:  # pragma: no cover - only on pathologically elongated blobs
        log.warning(
            "green-on-brown labelling hit %d iterations without converging; "
            "blobs may be split. Install OpenCV for the exact fast path.",
            max_iterations,
        )

    uniq = np.unique(lab)
    uniq = uniq[uniq > 0]
    out = np.zeros(lab.shape, dtype=np.int32)
    for i, u in enumerate(uniq, start=1):
        out[lab == u] = i
    return out, len(uniq)


def label_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Label connected regions, using OpenCV when it is available."""
    try:
        import cv2
    except ImportError:
        return _label_numpy(mask)
    n, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    return labels.astype(np.int32), n - 1  # label 0 is background


def _blob_confidence(values: np.ndarray, low: float, high: float) -> float:
    """Mean index strength inside a blob, rescaled to 0-1. NOT a probability.

    Nothing here estimates a likelihood; there is no model. This exists so
    `confidence_threshold` has something monotonic to filter on and so stronger
    detections sort first.
    """
    if values.size == 0:
        return 0.0
    span = max(high - low, 1e-6)
    return float(np.clip((values.mean() - low) / span, 0.0, 1.0))


# ---------------------------------------------------------------------------


class GreenOnBrownEngine(InferenceEngine):
    """Threshold-based vegetation detection. See the module docstring first."""

    def __init__(
        self,
        index: str = "exg",
        threshold_mode: str = "absolute",
        index_min: float = 30.0,
        index_max: float = 255.0,
        min_area_px: int = 100,
        max_detections: int = 50,
        label: str = "vegetation",
        confidence_threshold: float = 0.0,
    ):
        if index not in INDICES:
            raise ValueError(
                f"Unknown index '{index}'. Available: {', '.join(sorted(INDICES))}."
            )
        if threshold_mode not in ("absolute", "adaptive"):
            raise ValueError(
                f"Unknown threshold_mode '{threshold_mode}'. Use 'absolute' or 'adaptive'."
            )

        super().__init__(
            ModelMetadata(
                name="greenonbrown",
                version="1.0.0",
                trained_on=["no training data -- threshold on a vegetation index"],
                class_names=[label],
                # No amount of threshold tuning makes this a validated detector,
                # and the gate is what stops it driving a sprayer.
                validated_locally=False,
                validation_notes=(
                    "Classical green-on-brown thresholding ported from "
                    "OpenWeedLocator (MIT). Detects VEGETATION, not weeds: it "
                    "cannot distinguish a weed from a crop plant, so it is only "
                    "meaningful where green implies weed (fallow ground, stubble, "
                    "pre-emergence). Confidence is index strength, not probability."
                ),
            )
        )
        self.index = index
        self.threshold_mode = threshold_mode
        self.index_min = float(index_min)
        self.index_max = float(index_max)
        self.min_area_px = int(min_area_px)
        self.max_detections = int(max_detections)
        self.label = label
        self.confidence_threshold = float(confidence_threshold)

    def infer(self, image: np.ndarray) -> list[Detection]:
        if image.ndim != 3 or image.shape[2] < 3:
            raise ValueError(
                f"green-on-brown needs an RGB image, got shape {image.shape}. "
                "It is a colour index; a single band carries no green signal."
            )
        rgb = image[..., :3]
        h, w = rgb.shape[:2]

        index = INDICES[self.index](rgb)
        if self.threshold_mode == "adaptive":
            mask = threshold_adaptive(index, self.index_min, self.index_max)
        else:
            mask = threshold_absolute(index, self.index_min, self.index_max)

        labels, n = label_components(mask)
        if n == 0:
            return []

        # Everything below is O(frame) ONCE, not O(frame x blobs). The obvious
        # implementation -- `for lab in range(n): np.nonzero(labels == lab)` --
        # rescans the whole frame per blob and measured 732 ms on a 1280x853
        # frame against YOLOX's 313 ms, which defeats the entire point of a
        # backend whose selling point is running on a bare Pi.
        ys, xs = np.nonzero(labels)
        if ys.size == 0:
            return []
        lab = labels[ys, xs]

        areas = np.bincount(lab, minlength=n + 1)
        sums = np.bincount(lab, weights=index[ys, xs].astype(np.float64), minlength=n + 1)
        means = sums / np.maximum(areas, 1)

        x0 = np.full(n + 1, w, dtype=np.int64)
        y0 = np.full(n + 1, h, dtype=np.int64)
        x1 = np.zeros(n + 1, dtype=np.int64)
        y1 = np.zeros(n + 1, dtype=np.int64)
        np.minimum.at(x0, lab, xs)
        np.minimum.at(y0, lab, ys)
        np.maximum.at(x1, lab, xs)
        np.maximum.at(y1, lab, ys)

        span = max(self.index_max - self.index_min, 1e-6)
        confs = np.clip((means - self.index_min) / span, 0.0, 1.0)

        keep = np.nonzero(
            (areas >= self.min_area_px) & (confs >= self.confidence_threshold)
        )[0]
        keep = keep[keep > 0]  # label 0 is background

        found = []
        for i in keep:
            # Normalised xyxy, +1 on the far edge so a single-pixel blob has extent.
            found.append(
                (
                    int(areas[i]),
                    Detection(
                        label=self.label,
                        confidence=float(confs[i]),
                        bbox=(
                            float(x0[i]) / w,
                            float(y0[i]) / h,
                            float(x1[i] + 1) / w,
                            float(y1[i] + 1) / h,
                        ),
                        # The safety contract, identical to every other backend.
                        validated_locally=self.metadata.validated_locally,
                    ),
                )
            )

        # Largest first, then cap -- a frame of algae-green water should not
        # produce ten thousand Detections and a multi-megabyte sidecar.
        found.sort(key=lambda t: t[0], reverse=True)
        return [d for _, d in found[: self.max_detections]]
