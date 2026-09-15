"""Vegetation index tests."""

import numpy as np
import pytest

from agri_edge.geo.indices import (
    BandStack,
    available_indices,
    compute,
    excess_green,
    management_zones,
    ndre,
    ndvi,
    resolve_band,
    savi,
)


def stack(**bands) -> BandStack:
    """Build a BandStack from keyword band arrays or scalars.

    Scalars broadcast to the shape of whichever band was given as an array, so a
    test can write `stack(nir=arr, red=20)` and get a matching constant plane.
    """
    names = list(bands)
    shape = next(
        (np.asarray(v).shape for v in bands.values() if not np.isscalar(v)),
        (4, 4),
    )
    arrays = [
        np.full(shape, bands[n], dtype=np.float64)
        if np.isscalar(bands[n])
        else np.asarray(bands[n], dtype=np.float64)
        for n in names
    ]
    return BandStack(np.stack(arrays, axis=2), names)


class TestBandResolution:
    @pytest.mark.parametrize(
        "alias,canonical",
        [
            ("NIR", "nir"),
            ("near-infrared", "nir"),
            ("RedEdge", "red-edge"),
            ("red_edge", "red-edge"),
            ("re", "red-edge"),
            ("R", "red"),
            ("pan", "panchromatic"),
            ("LWIR", "thermal"),
        ],
    )
    def test_aliases(self, alias, canonical):
        assert resolve_band(alias) == canonical

    def test_unknown_band_returns_none(self):
        assert resolve_band("ultraviolet") is None

    def test_mismatched_labels_rejected(self):
        with pytest.raises(ValueError, match="3 planes but 2 band labels"):
            BandStack(np.zeros((4, 4, 3)), ["red", "green"])

    def test_2d_image_is_promoted(self):
        s = BandStack(np.zeros((4, 4)), ["red"])
        assert s.available == ["red"]

    def test_missing_band_raises_with_a_useful_message(self):
        s = stack(red=100, green=100, blue=100)
        with pytest.raises(KeyError, match="not a degraded index, it is nothing"):
            s.band("nir")


class TestNdvi:
    def test_healthy_canopy_is_high(self):
        # High NIR, low red -> NDVI near 1.
        r = ndvi(stack(nir=200, red=20))
        assert r.array.mean() == pytest.approx((200 - 20) / (200 + 20))
        assert r.array.mean() > 0.7

    def test_bare_soil_is_low(self):
        r = ndvi(stack(nir=110, red=100))
        assert 0 < r.array.mean() < 0.1

    def test_water_is_negative(self):
        r = ndvi(stack(nir=20, red=80))
        assert r.array.mean() < 0

    def test_zero_denominator_is_nan_not_inf(self):
        """A spurious infinity averaged into a management zone is a bad prescription."""
        r = ndvi(stack(nir=0, red=0))
        assert np.all(np.isnan(r.array))
        assert not np.any(np.isinf(r.array))
        assert r.valid_fraction == 0.0

    def test_uncalibrated_by_default(self):
        assert ndvi(stack(nir=200, red=20)).calibrated is False

    def test_calibrated_flag_propagates(self):
        assert ndvi(stack(nir=200, red=20), calibrated=True).calibrated is True


class TestOtherIndices:
    def test_ndre_uses_red_edge_not_red(self):
        s = stack(nir=200, red=20, **{"red-edge": 100})
        assert ndre(s).array.mean() == pytest.approx((200 - 100) / (200 + 100))

    def test_savi_differs_from_ndvi(self):
        s = stack(nir=200, red=20)
        assert savi(s).array.mean() != pytest.approx(ndvi(s).array.mean())

    def test_savi_soil_adjustment_bounded(self):
        v = savi(stack(nir=200, red=20)).array.mean()
        assert -1.5 <= v <= 1.5

    def test_excess_green_is_never_calibrated(self):
        """ExG is a contrast measure on digital numbers, not a reflectance value."""
        r = excess_green(stack(green=200, red=50, blue=50))
        assert r.calibrated is False
        assert r.array.mean() == pytest.approx(2 * 200 - 50 - 50)

    def test_unknown_index_raises(self):
        with pytest.raises(KeyError, match="Unknown index"):
            compute(stack(nir=1, red=1), "nbr")


class TestAvailability:
    def test_rgb_only_payload(self):
        avail = available_indices(stack(red=1, green=1, blue=1))
        assert "excess_green" in avail
        assert "ndvi" not in avail
        assert "ndre" not in avail

    def test_m3m_style_payload(self):
        avail = available_indices(stack(green=1, red=1, nir=1, **{"red-edge": 1}))
        assert {"ndvi", "ndre", "gndvi", "savi"} <= set(avail)

    def test_nir_red_only(self):
        avail = set(available_indices(stack(nir=1, red=1)))
        assert {"ndvi", "savi"} <= avail
        assert "ndre" not in avail


class TestSummary:
    def test_summary_reports_distribution(self):
        arr = np.linspace(0, 1, 100).reshape(10, 10)
        r = ndvi(stack(nir=arr * 200 + 20, red=20))
        s = r.summary()
        assert s["min"] <= s["p05"] <= s["median"] <= s["p95"] <= s["max"]
        assert s["calibrated"] is False

    def test_summary_of_all_nan_is_safe(self):
        s = ndvi(stack(nir=0, red=0)).summary()
        assert s["valid_fraction"] == 0.0
        assert "median" not in s


class TestManagementZones:
    def test_three_equal_area_zones(self):
        arr = np.arange(90, dtype=np.float64).reshape(9, 10)
        r = ndvi(stack(nir=arr + 100, red=10))
        zones = management_zones(r, n_zones=3)
        counts = [int((zones == z).sum()) for z in range(3)]
        assert sum(counts) == 90
        # Quantile split on distinct values gives near-equal areas.
        assert max(counts) - min(counts) <= 1

    def test_lowest_zone_is_lowest_vigour(self):
        arr = np.arange(90, dtype=np.float64).reshape(9, 10)
        r = ndvi(stack(nir=arr + 100, red=10))
        zones = management_zones(r, n_zones=3)
        assert r.array[zones == 0].mean() < r.array[zones == 2].mean()

    def test_nan_pixels_marked_minus_one(self):
        arr = np.arange(16, dtype=np.float64).reshape(4, 4)
        nir = arr + 100
        red = np.full((4, 4), 10.0)
        nir[0, 0] = 0
        red[0, 0] = 0  # forces NaN
        zones = management_zones(ndvi(BandStack(np.stack([nir, red], axis=2), ["nir", "red"])))
        assert zones[0, 0] == -1
        assert (zones >= 0).sum() == 15

    def test_all_nan_returns_all_unassigned(self):
        zones = management_zones(ndvi(stack(nir=0, red=0)))
        assert np.all(zones == -1)
