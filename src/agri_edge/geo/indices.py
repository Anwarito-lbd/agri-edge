"""Vegetation indices.

A caution that belongs in the code and not only in the documentation: these
functions return arithmetic, not agronomy. Comparing NDVI between two dates is
only meaningful when illumination, exposure, reflectance calibration and growth
stage are all controlled. Uncalibrated digital numbers from a consumer RGB sensor
produce attractive maps that are agronomically misleading, which is a worse
outcome than no map at all.

Where the input is raw digital numbers rather than calibrated reflectance, the
`calibrated` flag on IndexResult stays False and downstream consumers are expected
to refuse cross-date comparison.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Band name aliases seen across MicaSense, DJI and custom payloads.
BAND_ALIASES = {
    "red": {"red", "r"},
    "green": {"green", "g"},
    "blue": {"blue", "b"},
    "nir": {"nir", "near-infrared", "nearinfrared", "n"},
    "red-edge": {"red-edge", "rededge", "re", "red_edge"},
    "panchromatic": {"panchromatic", "pan"},
    "thermal": {"thermal", "lwir", "t"},
}


def resolve_band(name: str) -> str | None:
    """Map a payload's band label onto a canonical name."""
    n = name.strip().lower()
    for canonical, aliases in BAND_ALIASES.items():
        if n in aliases:
            return canonical
    return None


class BandStack:
    """A multi-band image addressed by canonical band name."""

    def __init__(self, image: np.ndarray, bands: list[str]):
        if image.ndim == 2:
            image = image[:, :, None]
        if image.shape[2] != len(bands):
            raise ValueError(
                f"Image has {image.shape[2]} planes but {len(bands)} band labels were given."
            )
        self._image = image
        self._index: dict[str, int] = {}
        for i, raw in enumerate(bands):
            canonical = resolve_band(raw)
            if canonical is not None:
                self._index[canonical] = i

    def has(self, *names: str) -> bool:
        return all(n in self._index for n in names)

    def band(self, name: str) -> np.ndarray:
        if name not in self._index:
            raise KeyError(
                f"Band '{name}' not present. Available: {sorted(self._index)}. "
                "An index computed from a missing band is not a degraded index, it is nothing."
            )
        return self._image[:, :, self._index[name]].astype(np.float64)

    @property
    def available(self) -> list[str]:
        return sorted(self._index)


@dataclass
class IndexResult:
    name: str
    array: np.ndarray
    calibrated: bool
    valid_fraction: float

    def summary(self) -> dict:
        a = self.array[np.isfinite(self.array)]
        if a.size == 0:
            return {"name": self.name, "calibrated": self.calibrated, "valid_fraction": 0.0}
        return {
            "name": self.name,
            "calibrated": self.calibrated,
            "valid_fraction": self.valid_fraction,
            "min": float(a.min()),
            "p05": float(np.percentile(a, 5)),
            "median": float(np.median(a)),
            "p95": float(np.percentile(a, 95)),
            "max": float(a.max()),
            "mean": float(a.mean()),
        }


def _normalized_difference(a: np.ndarray, b: np.ndarray, name: str, calibrated: bool) -> IndexResult:
    """(a - b) / (a + b), guarding the division.

    Where the denominator is at or near zero the result is NaN rather than a large
    spurious value -- silently emitting +/-inf into a raster that later gets
    averaged into a management zone is how a bad prescription gets made.
    """
    denom = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.abs(denom) > 1e-9, (a - b) / denom, np.nan)
    valid = float(np.isfinite(out).sum()) / out.size if out.size else 0.0
    return IndexResult(name=name, array=out, calibrated=calibrated, valid_fraction=valid)


def ndvi(stack: BandStack, calibrated: bool = False) -> IndexResult:
    """Normalised Difference Vegetation Index: (NIR - Red) / (NIR + Red).

    The general-purpose canopy vigour index. Saturates in dense canopy, which is
    why NDRE is preferred later in the season.
    """
    return _normalized_difference(stack.band("nir"), stack.band("red"), "ndvi", calibrated)


def ndre(stack: BandStack, calibrated: bool = False) -> IndexResult:
    """Normalised Difference Red Edge: (NIR - RedEdge) / (NIR + RedEdge).

    More sensitive than NDVI once the canopy has closed, which makes it the more
    useful index for mid- and late-season nitrogen and stress work.
    """
    return _normalized_difference(stack.band("nir"), stack.band("red-edge"), "ndre", calibrated)


def gndvi(stack: BandStack, calibrated: bool = False) -> IndexResult:
    """Green NDVI: (NIR - Green) / (NIR + Green)."""
    return _normalized_difference(stack.band("nir"), stack.band("green"), "gndvi", calibrated)


def savi(stack: BandStack, L: float = 0.5, calibrated: bool = False) -> IndexResult:
    """Soil-Adjusted Vegetation Index.

    Worth preferring over NDVI at emergence and early growth, when a lot of each
    pixel is bare soil and NDVI is reporting the soil as much as the crop.
    """
    nir, red = stack.band("nir"), stack.band("red")
    denom = nir + red + L
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(np.abs(denom) > 1e-9, ((nir - red) / denom) * (1.0 + L), np.nan)
    valid = float(np.isfinite(out).sum()) / out.size if out.size else 0.0
    return IndexResult("savi", out, calibrated, valid)


def excess_green(stack: BandStack) -> IndexResult:
    """ExG = 2G - R - B, for RGB-only payloads.

    Useful for green-vs-soil segmentation on a plain RGB camera, which is what a
    Raspberry Pi Camera Module gives you. Never calibrated -- it is a contrast
    index on digital numbers, not a reflectance measurement, and it must not be
    compared across flights.
    """
    g, r, b = stack.band("green"), stack.band("red"), stack.band("blue")
    out = 2.0 * g - r - b
    return IndexResult("excess_green", out, calibrated=False, valid_fraction=1.0)


INDEX_REQUIREMENTS = {
    "ndvi": ("nir", "red"),
    "ndre": ("nir", "red-edge"),
    "gndvi": ("nir", "green"),
    "savi": ("nir", "red"),
    "excess_green": ("green", "red", "blue"),
}

_INDEX_FUNCS = {
    "ndvi": ndvi,
    "ndre": ndre,
    "gndvi": gndvi,
    "savi": savi,
    "excess_green": lambda s, calibrated=False: excess_green(s),
}


def available_indices(stack: BandStack) -> list[str]:
    """Which indices this payload can actually produce."""
    return [name for name, req in INDEX_REQUIREMENTS.items() if stack.has(*req)]


def compute(stack: BandStack, name: str, calibrated: bool = False) -> IndexResult:
    if name not in _INDEX_FUNCS:
        raise KeyError(f"Unknown index '{name}'. Known: {sorted(_INDEX_FUNCS)}")
    return _INDEX_FUNCS[name](stack, calibrated=calibrated)


def management_zones(index: IndexResult, n_zones: int = 3) -> np.ndarray:
    """Split an index raster into equal-area zones by quantile.

    Quantiles rather than fixed index breakpoints, because a fixed NDVI threshold
    means different things on different crops, growth stages and dates. Equal-area
    zones at least describe *this* field on *this* date honestly.

    Returns an int array: 0 is the lowest-vigour zone, n_zones-1 the highest,
    and -1 marks pixels with no valid index value.
    """
    a = index.array
    out = np.full(a.shape, -1, dtype=np.int16)
    finite = np.isfinite(a)
    if not finite.any():
        return out
    vals = a[finite]
    edges = np.quantile(vals, np.linspace(0, 1, n_zones + 1)[1:-1])
    out[finite] = np.digitize(vals, edges)
    return out
