"""Turn raw digital numbers into reflectance, so two dates can be compared.

WHY THIS IS THE DIFFERENCE BETWEEN A MAP AND A PICTURE
------------------------------------------------------
`IndexResult.calibrated` has been False for every index this project has ever
computed, and the pipeline is right to refuse cross-date comparison on that
basis. An NDVI built from raw digital numbers measures the *camera*, not the
crop: change the exposure, the sun angle, or the cloud cover and the number moves
without a single plant changing.

That makes repeat monitoring -- the whole reason to fly a field more than once --
impossible. A June map and a July map of the same field differ mostly by
illumination, and the difference is agronomically meaningless while looking
exactly like a real change. An attractive map that is quietly wrong is worse than
no map, because it gets believed.

HOW IT IS FIXED
---------------
Photograph a panel of known reflectance in the same light as the flight, then
scale each band so the panel reads its true value:

    gain_band = known_reflectance_band / measured_mean_band
    reflectance = raw * gain

This is the standard empirical-line method with a single target, which assumes
sensor response is linear through the origin. That holds well for the mid-range
of a well-exposed sensor and fails at both ends -- a saturated or near-black
panel gives a wildly wrong gain, so `compute_gains` refuses those rather than
returning a confident number.

WHAT IT STILL DOES NOT FIX
--------------------------
Calibrating at takeoff corrects the *average* conditions of the flight, not
changes during it. A cloud crossing mid-flight still shifts reflectance, and
nothing here detects that. Panels before AND after, with the difference treated
as an uncertainty estimate, is the honest version; `panel_drift` supports it.

A downwelling light sensor is the real answer and is the reason commercial
multispectral rigs have one. That is `docs/USE_CASES.md` Tier 1, ~C$100.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from .indices import BandStack


@dataclass(frozen=True)
class ReflectancePanel:
    """A calibration target with known reflectance per band, 0-1.

    Comes off the panel's own calibration certificate. A 50% grey card is the
    common field target; the values are rarely flat across bands, which is
    precisely why they are stored per band rather than as one number.
    """

    reflectance: dict[str, float]
    label: str = "unnamed panel"

    def __post_init__(self) -> None:
        if not self.reflectance:
            raise ValueError("A panel needs at least one band's reflectance.")
        for band, r in self.reflectance.items():
            if not 0.0 < r <= 1.0:
                raise ValueError(
                    f"{self.label}: reflectance for '{band}' is {r}; must be in (0, 1]. "
                    "These are fractions from the panel's certificate, not percentages."
                )


# A generic 50% grey target. REPLACE with your panel's certificate values --
# these are a plausible default, not a measurement of anything you own.
GREY_50 = ReflectancePanel(
    reflectance={"blue": 0.50, "green": 0.50, "red": 0.50, "red-edge": 0.50, "nir": 0.50},
    label="generic 50% grey (PLACEHOLDER -- use your panel's certificate)",
)


@dataclass
class CalibrationGains:
    """Per-band multipliers taking raw digital numbers to reflectance."""

    gains: dict[str, float] = field(default_factory=dict)
    panel_label: str = ""
    measured_at: float = 0.0
    saturated_fraction: dict[str, float] = field(default_factory=dict)
    # How long a calibration is trusted. Light changes; a morning panel does not
    # describe an afternoon flight.
    max_age_s: float = 7200.0

    def is_fresh(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) - self.measured_at <= self.max_age_s

    def covers(self, bands) -> bool:
        return all(b in self.gains for b in bands)

    def as_dict(self) -> dict:
        return {
            "gains": {k: round(v, 5) for k, v in self.gains.items()},
            "panel": self.panel_label,
            "measured_at": self.measured_at,
            "saturated_fraction": {k: round(v, 4) for k, v in self.saturated_fraction.items()},
        }


def compute_gains(
    panel_stack: BandStack,
    panel: ReflectancePanel = GREY_50,
    region: tuple[int, int, int, int] | None = None,
    max_value: float = 255.0,
    max_saturated_fraction: float = 0.02,
    min_signal_fraction: float = 0.05,
) -> CalibrationGains:
    """Derive per-band gains from an image of the calibration panel.

    `region` is (y0, y1, x0, x1) selecting just the panel within the frame. Pass
    it: averaging the whole frame averages the grass around the panel too, and
    the resulting gain is wrong by whatever that grass reflects.

    **Refuses rather than guessing** on the two exposures that break the linear
    assumption:

    * more than `max_saturated_fraction` of the panel clipped at `max_value` --
      the true mean is unknowable, and the computed gain would be too high;
    * a mean below `min_signal_fraction` of full scale -- near-black is
      dominated by sensor noise and dark current, so the gain is unstable.

    Both are silent in the resulting imagery and catastrophic in the numbers.
    """
    gains: dict[str, float] = {}
    sat: dict[str, float] = {}

    for band, known in panel.reflectance.items():
        if band not in panel_stack.available:
            continue
        plane = panel_stack.band(band)
        if region is not None:
            y0, y1, x0, x1 = region
            plane = plane[y0:y1, x0:x1]
        if plane.size == 0:
            raise ValueError(f"Panel region for '{band}' is empty.")

        saturated = float((plane >= max_value).mean())
        sat[band] = saturated
        if saturated > max_saturated_fraction:
            raise ValueError(
                f"Panel is {saturated:.1%} saturated in '{band}' (limit "
                f"{max_saturated_fraction:.0%}). The true mean cannot be recovered "
                "from clipped pixels -- re-shoot the panel with shorter exposure."
            )

        mean = float(plane.mean())
        if mean < min_signal_fraction * max_value:
            raise ValueError(
                f"Panel mean in '{band}' is {mean:.1f} of {max_value:.0f} -- too dark "
                "to calibrate from. Near-black is dominated by sensor noise, so the "
                "gain would be unstable. Re-shoot with longer exposure."
            )
        gains[band] = known / mean

    if not gains:
        raise ValueError(
            f"No overlap between the panel's bands ({sorted(panel.reflectance)}) "
            f"and the image's ({panel_stack.available})."
        )
    return CalibrationGains(
        gains=gains, panel_label=panel.label, measured_at=time.time(), saturated_fraction=sat
    )


def apply_gains(stack: BandStack, cal: CalibrationGains) -> BandStack:
    """Scale a raw stack into reflectance. Bands without a gain are dropped.

    Dropped, not passed through. A stack silently mixing calibrated and raw bands
    would produce an index that is neither, and `calibrated=True` on it would be
    a lie -- an NDVI from a calibrated NIR and a raw red is not a partially
    calibrated NDVI, it is nonsense.
    """
    usable = [b for b in stack.available if b in cal.gains]
    if not usable:
        raise ValueError(
            f"No band has a gain. Image has {stack.available}, "
            f"calibration covers {sorted(cal.gains)}."
        )
    planes = [stack.band(b) * cal.gains[b] for b in usable]
    return BandStack(np.stack(planes, axis=2), usable)


def calibrated_stack(
    stack: BandStack, cal: CalibrationGains | None, now: float | None = None
) -> tuple[BandStack, bool]:
    """Apply a calibration if one is usable. Returns `(stack, calibrated)`.

    The single decision point for whether an index may claim to be calibrated,
    so the answer cannot drift between callers. A stale or partial calibration
    yields the raw stack and False -- never a partly-corrected stack wearing a
    calibrated label.
    """
    if cal is None or not cal.gains:
        return stack, False
    if not cal.is_fresh(now):
        return stack, False
    try:
        return apply_gains(stack, cal), True
    except ValueError:
        return stack, False


def panel_drift(before: CalibrationGains, after: CalibrationGains) -> dict[str, float]:
    """Relative change in each gain between two panel shots, as a fraction.

    The honest uncertainty estimate for a flight: shoot the panel before and
    after, and this says how much the light moved while you were up. A drift of
    0.30 in a band means index values in that band are uncertain by roughly that
    much, which is usually larger than the agronomic difference being looked for.

    It reports; it does not decide. What counts as too much drift depends on what
    the map is for.
    """
    out: dict[str, float] = {}
    for band, g0 in before.gains.items():
        g1 = after.gains.get(band)
        if g1 is not None and g0 != 0:
            out[band] = abs(g1 - g0) / abs(g0)
    return out
