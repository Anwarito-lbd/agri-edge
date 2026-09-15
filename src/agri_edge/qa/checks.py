"""Edge image quality assessment.

This runs on the aircraft, immediately after capture, and it exists to answer one
question: is this frame worth the bandwidth and the storage?

Design note on failure handling: a frame that fails QA is **flagged, not
discarded**. A blurred frame over a genuine anomaly is still evidence that
something is there, and the decision to throw data away belongs to an agronomist
on the ground with context, not to a threshold on a Pi at 100 m AGL. Failed
frames spool at low priority; they do not vanish.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ..telemetry.mavlink_link import TelemetrySnapshot


class Severity(str, Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    name: str
    severity: Severity
    value: float | None = None
    threshold: float | None = None
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.severity is Severity.OK


@dataclass
class QAReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def severity(self) -> Severity:
        if any(c.severity is Severity.FAIL for c in self.checks):
            return Severity.FAIL
        if any(c.severity is Severity.WARN for c in self.checks):
            return Severity.WARN
        return Severity.OK

    @property
    def passed(self) -> bool:
        return self.severity is Severity.OK

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if c.severity is Severity.FAIL]

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "checks": [
                {
                    "name": c.name,
                    "severity": c.severity.value,
                    "value": c.value,
                    "threshold": c.threshold,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
        }


def _to_gray(image: np.ndarray) -> np.ndarray:
    """Reduce an image to a single 2-D luminance plane.

    Uses Rec. 601 luma weights for 3-channel input. For anything else (a 4- or
    5-band multispectral stack, say) it averages the bands -- crude, but blur is
    a geometric property and any band carries it.
    """
    if image.ndim == 2:
        return image.astype(np.float64)
    if image.ndim == 3 and image.shape[2] == 3:
        r, g, b = image[..., 0], image[..., 1], image[..., 2]
        return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.float64)
    if image.ndim == 3:
        return image.mean(axis=2).astype(np.float64)
    raise ValueError(f"Unsupported image shape for QA: {image.shape}")


def _plane_laplacian_variance(plane: np.ndarray) -> float:
    """Variance of the 4-neighbour Laplacian of a single 2-D plane.

    The kernel is applied to the interior only; edge pixels are excluded rather
    than padded, since padding invents gradients that inflate the variance.
    """
    if plane.shape[0] < 3 or plane.shape[1] < 3:
        return 0.0
    lap = (
        plane[:-2, 1:-1]
        + plane[2:, 1:-1]
        + plane[1:-1, :-2]
        + plane[1:-1, 2:]
        - 4.0 * plane[1:-1, 1:-1]
    )
    return float(lap.var())


def laplacian_variance(image: np.ndarray) -> float:
    """Variance of the Laplacian -- the standard sharpness proxy.

    A sharp image has strong second derivatives at edges, so the Laplacian has
    high variance. A blurred one does not.

    Multi-band images are measured **per band, taking the sharpest**, rather than
    by collapsing the bands to one luminance plane first. Averaging N bands
    averages N largely independent noise and texture fields, which suppresses the
    high-frequency content this metric exists to detect -- a perfectly sharp
    five-band multispectral frame scores roughly 1/N of its true sharpness and
    gets rejected as blurred. Blur is geometric and appears in every band, so the
    best-focused band is the honest estimate of whether the frame is sharp.

    Implemented with numpy rather than OpenCV so QA runs on a base Raspberry Pi OS
    image with no `cv` extra installed.
    """
    if image.ndim == 2:
        return _plane_laplacian_variance(image.astype(np.float64))
    if image.ndim == 3:
        return max(
            _plane_laplacian_variance(image[:, :, i].astype(np.float64))
            for i in range(image.shape[2])
        )
    raise ValueError(f"Unsupported image shape for QA: {image.shape}")


def check_blur(image: np.ndarray, threshold: float) -> CheckResult:
    v = laplacian_variance(image)
    if v < threshold:
        return CheckResult(
            "blur",
            Severity.FAIL,
            value=v,
            threshold=threshold,
            detail=(
                f"Laplacian variance {v:.1f} below {threshold:.1f}. "
                "Likely motion blur -- check groundspeed, shutter and vibration isolation."
            ),
        )
    if v < threshold * 1.5:
        return CheckResult(
            "blur", Severity.WARN, value=v, threshold=threshold, detail="Marginal sharpness."
        )
    return CheckResult("blur", Severity.OK, value=v, threshold=threshold)


def check_exposure(
    image: np.ndarray,
    over_fraction: float,
    under_fraction: float,
    high: int = 250,
    low: int = 5,
) -> CheckResult:
    """Detect clipping at either end of the range.

    Clipped highlights are unrecoverable, and for multispectral work they are
    worse than a dark frame: a saturated band silently biases every vegetation
    index computed from it.
    """
    gray = _to_gray(image)
    total = gray.size
    over = float((gray >= high).sum()) / total
    under = float((gray <= low).sum()) / total

    if over > over_fraction:
        return CheckResult(
            "exposure",
            Severity.FAIL,
            value=over,
            threshold=over_fraction,
            detail=(
                f"{over:.1%} of pixels clipped at the highlight end. "
                "Saturated bands bias any index computed from them."
            ),
        )
    if under > under_fraction:
        return CheckResult(
            "exposure",
            Severity.FAIL,
            value=under,
            threshold=under_fraction,
            detail=f"{under:.1%} of pixels crushed at the shadow end.",
        )
    if over > over_fraction * 0.5 or under > under_fraction * 0.5:
        return CheckResult(
            "exposure",
            Severity.WARN,
            value=max(over, under),
            threshold=over_fraction,
            detail="Approaching clipping.",
        )
    return CheckResult("exposure", Severity.OK, value=max(over, under), threshold=over_fraction)


def check_gnss(
    telem: TelemetrySnapshot,
    min_fix_type: int,
    require_rtk_fixed: bool,
    max_hdop: float,
    min_satellites: int,
) -> CheckResult:
    """Gate on position quality.

    An image whose position is uncertain to metres cannot support temporal
    comparison between flights, which is the entire point of repeated monitoring.
    Better to know at capture time than to discover it during alignment.
    """
    if telem.fix_type < min_fix_type:
        return CheckResult(
            "gnss",
            Severity.FAIL,
            value=float(telem.fix_type),
            threshold=float(min_fix_type),
            detail=f"Fix type {telem.fix_name} below required minimum.",
        )
    if require_rtk_fixed and not telem.is_rtk_fixed:
        return CheckResult(
            "gnss",
            Severity.FAIL,
            value=float(telem.fix_type),
            threshold=float(6),
            detail=(
                f"RTK fixed required for this mission, got {telem.fix_name}. "
                "Check base station and correction link."
            ),
        )
    if telem.hdop > max_hdop:
        return CheckResult(
            "gnss",
            Severity.WARN,
            value=telem.hdop,
            threshold=max_hdop,
            detail=f"HDOP {telem.hdop:.2f} degraded.",
        )
    if telem.satellites < min_satellites:
        return CheckResult(
            "gnss",
            Severity.WARN,
            value=float(telem.satellites),
            threshold=float(min_satellites),
            detail=f"Only {telem.satellites} satellites.",
        )
    return CheckResult("gnss", Severity.OK, value=telem.hdop, threshold=max_hdop)


def check_bands(present: list[str], required: list[str]) -> CheckResult:
    """Multispectral completeness.

    A missing band is not a degraded capture, it is an unusable one: NDRE without
    the red-edge band is not a worse NDRE, it is nothing.
    """
    if not required:
        return CheckResult("bands", Severity.OK, detail="No band requirement configured.")
    missing = [b for b in required if b not in present]
    if missing:
        return CheckResult(
            "bands",
            Severity.FAIL,
            value=float(len(present)),
            threshold=float(len(required)),
            detail=f"Missing band(s): {', '.join(missing)}.",
        )
    return CheckResult("bands", Severity.OK, value=float(len(present)), threshold=float(len(required)))


def check_attitude(telem: TelemetrySnapshot, max_tilt_deg: float = 10.0) -> CheckResult:
    """Flag frames captured at significant tilt.

    Relevant for nadir photogrammetry on a fixed (ungimballed) mount: wind gusts
    tilt the airframe and the resulting oblique frame degrades the orthomosaic
    even when it looks perfectly sharp.
    """
    if telem.roll_deg is None or telem.pitch_deg is None:
        return CheckResult("attitude", Severity.OK, detail="No attitude data.")
    tilt = float(np.hypot(telem.roll_deg, telem.pitch_deg))
    if tilt > max_tilt_deg:
        return CheckResult(
            "attitude",
            Severity.WARN,
            value=tilt,
            threshold=max_tilt_deg,
            detail=f"Airframe tilted {tilt:.1f} deg at capture; frame is off-nadir.",
        )
    return CheckResult("attitude", Severity.OK, value=tilt, threshold=max_tilt_deg)


def run_qa(
    image: np.ndarray,
    telem: TelemetrySnapshot,
    cfg,
    bands_present: list[str] | None = None,
) -> QAReport:
    """Run the full QA suite over one captured frame."""
    return QAReport(
        checks=[
            check_blur(image, cfg.blur_threshold),
            check_exposure(
                image,
                cfg.overexposed_fraction,
                cfg.underexposed_fraction,
                cfg.saturation_high,
                cfg.saturation_low,
            ),
            check_gnss(
                telem,
                cfg.min_fix_type,
                cfg.require_rtk_fixed,
                cfg.max_hdop,
                cfg.min_satellites,
            ),
            check_bands(bands_present or [], cfg.required_bands),
            check_attitude(telem),
        ]
    )
