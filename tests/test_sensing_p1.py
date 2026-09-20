"""Tests for thermal + multispectral sensing (no hardware)."""

from __future__ import annotations

import numpy as np
import pytest

from agri_edge.sensors.multispectral import gndvi, index_map, ndre, ndvi, osavi
from agri_edge.sensors.thermal import canopy_stats, cwsi, thermal_stress_features
from agri_edge.relations.laptop_relate import (
    NotConfiguredError,
    relation_feature,
    relations_to_geojson,
    run_offline,
)


def test_canopy_stats_and_cwsi():
    t = np.full((8, 8), 28.0)
    t[0, 0] = 20.0
    t[-1, -1] = 36.0
    s = canopy_stats(t)
    assert s["n"] == 64
    assert 20 <= s["mean_c"] <= 36
    score = cwsi(s["mean_c"], twet_c=22.0, tdry_c=40.0)
    assert 0.0 <= score <= 1.0


def test_cwsi_fails_closed_on_zero_span():
    with pytest.raises(ValueError):
        cwsi(25.0, 25.0, 25.0)


def test_thermal_features_omit_cwsi_without_refs():
    t = np.ones((4, 4), dtype=np.float32) * 30.0
    feats = thermal_stress_features(t, frame_id="t1")
    assert feats[0]["cwsi"] is None
    feats2 = thermal_stress_features(t, twet_c=22.0, tdry_c=38.0, frame_id="t2")
    assert feats2[0]["cwsi"] is not None


def test_ndvi_healthy_vs_bare():
    nir = np.ones((4, 4), dtype=np.float32) * 0.6
    red = np.ones((4, 4), dtype=np.float32) * 0.1
    v = ndvi(nir, red)
    assert float(v.mean()) > 0.5
    bare = ndvi(np.full((4, 4), 0.2, np.float32), np.full((4, 4), 0.2, np.float32))
    assert abs(float(bare.mean())) < 0.05


def test_index_map_missing_band_fails():
    with pytest.raises(ValueError, match="missing"):
        index_map({"nir": np.ones((2, 2))}, "ndvi")


def test_ndre_gndvi_osavi_shapes():
    nir = np.random.rand(5, 5).astype(np.float32)
    re = np.random.rand(5, 5).astype(np.float32)
    green = np.random.rand(5, 5).astype(np.float32)
    red = np.random.rand(5, 5).astype(np.float32)
    assert ndre(nir, re).shape == (5, 5)
    assert gndvi(nir, green).shape == (5, 5)
    assert osavi(nir, red).shape == (5, 5)
    assert index_map({"nir": nir, "red_edge": re}, "ndre").shape == (5, 5)


def test_relation_schema():
    f = relation_feature("weed", "in", "crop_row", confidence=0.7)
    g = relations_to_geojson([f], lon=-113.5, lat=53.5)
    assert g["type"] == "FeatureCollection"
    assert g["features"][0]["properties"]["predicate"] == "in"


def test_run_offline_not_configured(tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    with pytest.raises(NotConfiguredError):
        run_offline(spool, repo_root=tmp_path)
