"""Sentinel-2 baseline: search parsing, per-scene statistics, change detection,
and the reader against a real (synthetic) UTM GeoTIFF."""

from __future__ import annotations

import math

import numpy as np
import pytest

from agri_edge.satellite import series
from agri_edge.satellite.field import Boundary, field_mask, observe
from agri_edge.satellite.reader import field_grid
from agri_edge.satellite.service import field_summary, update_field
from agri_edge.satellite.stac import Band, Scene, parse_items, search_body

LAT0, LON0 = 50.45, -104.60
D_LAT = 500 / 111_320
D_LON = 500 / (111_320 * math.cos(math.radians(LAT0)))
SQUARE = {"type": "Polygon", "coordinates": [[
    [LON0, LAT0], [LON0 + D_LON, LAT0], [LON0 + D_LON, LAT0 + D_LAT],
    [LON0, LAT0 + D_LAT], [LON0, LAT0]]]}


def _grid():
    b = Boundary.from_geojson(SQUARE)
    _, lats, lons = field_grid(b, 10.0)
    return b, lats, lons


def _bands(lats, ndvi, scl=4):
    """red/nir giving the requested NDVI (array or scalar)."""
    ndvi = np.broadcast_to(np.asarray(ndvi, dtype=np.float64), lats.shape).copy()
    red = np.full(lats.shape, 0.05)
    nir = red * (1 + ndvi) / (1 - ndvi)
    re_ = (nir + red) / 2
    return {"red": red, "nir": nir, "rededge": re_,
            "scl": np.broadcast_to(np.asarray(scl), lats.shape).astype(np.int64).copy()}


# -- STAC -------------------------------------------------------------------------


def test_stac_items_keep_scale_and_offset_and_drop_incomplete_scenes():
    def asset(key):
        return {"href": f"https://x/{key}.tif", "raster:bands": [{"scale": 0.0001, "offset": -0.1}]}

    payload = {"features": [
        {"id": "S2B_13UDR_20260710_0_L2A", "properties": {"datetime": "2026-07-10T18:05:00Z",
                                                          "eo:cloud_cover": 3.1},
         "assets": {k: asset(k) for k in ("red", "nir", "rededge1", "scl")}},
        {"id": "no-scl", "properties": {"datetime": "2026-07-12T18:05:00Z"},
         "assets": {k: asset(k) for k in ("red", "nir", "rededge1")}},
    ]}
    scenes = parse_items(payload)
    assert [s.scene_id for s in scenes] == ["S2B_13UDR_20260710_0_L2A"]
    assert scenes[0].date == "2026-07-10"
    assert scenes[0].bands["rededge"].href.endswith("rededge1.tif")
    assert scenes[0].bands["red"].offset == -0.1


def test_search_body_filters_cloud_and_sorts():
    b = search_body([-104.6, 50.4, -104.5, 50.5], "2026-06-01", "2026-07-31", 30)
    assert b["query"]["eo:cloud_cover"] == {"lt": 30}
    assert b["collections"] == ["sentinel-2-l2a"]


# -- one scene ----------------------------------------------------------------------


def test_clear_scene_statistics():
    b, lats, lons = _grid()
    obs = observe("s1", "2026-07-01", _bands(lats, 0.7), lats, lons, b)
    assert obs.usable and obs.valid_fraction == pytest.approx(1.0)
    assert obs.ndvi_mean == pytest.approx(0.7, abs=1e-3)
    assert len(obs.cells) == 100                     # 500 m / 50 m squared


def test_clouds_and_shadows_are_masked_and_a_cloudy_scene_is_not_usable():
    b, lats, lons = _grid()
    scl = np.full(lats.shape, 4)
    scl[: lats.shape[0] * 2 // 3, :] = 9             # top two thirds: high-probability cloud
    obs = observe("s1", "2026-07-01", _bands(lats, 0.7, scl), lats, lons, b)
    assert obs.valid_fraction < 0.5
    assert not obs.usable


def test_holes_are_excluded():
    hole = [[LON0 + D_LON * 0.4, LAT0 + D_LAT * 0.4], [LON0 + D_LON * 0.6, LAT0 + D_LAT * 0.4],
            [LON0 + D_LON * 0.6, LAT0 + D_LAT * 0.6], [LON0 + D_LON * 0.4, LAT0 + D_LAT * 0.6],
            [LON0 + D_LON * 0.4, LAT0 + D_LAT * 0.4]]
    b = Boundary.from_geojson({"type": "Polygon", "coordinates": [SQUARE["coordinates"][0], hole]})
    _, lats, lons = field_grid(b, 10.0)
    full = field_mask(Boundary.from_geojson(SQUARE), lats, lons).sum()
    assert field_mask(b, lats, lons).sum() == pytest.approx(full * 0.96, rel=0.05)


# -- change detection -----------------------------------------------------------


def _patch_ndvi(lats, lons, base, patch_drop, field_shift):
    b = Boundary.from_geojson(SQUARE)
    from agri_edge.geo.geofence import project_to_local
    en = project_to_local(lats.ravel(), lons.ravel(), b.origin)
    e, n = en[:, 0].reshape(lats.shape), en[:, 1].reshape(lats.shape)
    v = np.full(lats.shape, base + field_shift)
    patch = (e >= 100) & (e < 200) & (n >= 300) & (n < 400)     # cells 2-3 x 6-7
    v[patch] -= patch_drop
    return v


def _series(db, drop, shift):
    b, lats, lons = _grid()
    for day, (d, s) in enumerate([(0.0, 0.0), (0.0, 0.0), (drop, shift)]):
        obs = observe(f"s{day}", f"2026-07-{1 + day * 10:02d}",
                      _bands(lats, _patch_ndvi(lats, lons, 0.7, d, s)), lats, lons, b)
        series.save(db, "north", obs.to_dict())
    return series.detect_change("north", series.load(db, "north"), b)


def test_a_declining_patch_is_flagged_and_gets_a_scouting_plan(tmp_path):
    rep = _series(str(tmp_path / "sat.sqlite"), drop=0.25, shift=-0.03)
    assert rep.status == "flagged"
    assert {f.cell for f in rep.flagged} == {"2_6", "2_7", "3_6", "3_7"}
    assert len(rep.patches) == 1
    p = rep.patches[0]
    assert p["cells"] == 4 and p["area_ha"] == 1.0
    assert p["mission"]["lines"] >= 2 and p["mission"]["total_distance_m"] > 0
    assert any("field as a whole" in w for w in rep.why)
    kinds = {f["properties"]["kind"] for f in rep.geojson()["features"]}
    assert kinds == {"ndvi_decline", "scout_patch"}


def test_the_whole_field_changing_together_is_not_a_patch(tmp_path):
    """Senescence, green-up, haze: everything moves; nothing to scout."""
    rep = _series(str(tmp_path / "sat.sqlite"), drop=0.0, shift=-0.2)
    assert rep.status == "ok" and not rep.flagged
    assert rep.field_shift == pytest.approx(-0.2, abs=1e-3)


def test_one_clear_scene_is_insufficient(tmp_path):
    b, lats, lons = _grid()
    obs = observe("s0", "2026-07-01", _bands(lats, 0.7), lats, lons, b)
    rep = series.detect_change("north", [obs.to_dict()], b)
    assert rep.status == "insufficient"


def test_update_is_idempotent_and_survives_a_bad_scene(tmp_path):
    db = str(tmp_path / "sat.sqlite")
    b, lats, lons = _grid()
    scenes = [Scene(f"s{i}", f"2026-07-{1 + 10 * i:02d}T18:00:00Z", 2.0,
                    {"red": Band("x")}) for i in range(3)] + [Scene("broken", "2026-07-25T18:00:00Z", 1.0)]

    def search(bbox, start, end, max_cloud):
        return scenes

    def read(scene, boundary):
        if scene.scene_id == "broken":
            raise OSError("HTTP 503 from the bucket")
        i = int(scene.scene_id[1:])
        return _bands(lats, _patch_ndvi(lats, lons, 0.7, 0.3 if i == 2 else 0.0, 0.0)), lats, lons

    first = update_field(db, "north", SQUARE, start="2026-06-01", end="2026-07-31",
                         search=search, read=read)
    assert len(first["added"]) == 3 and first["failed"][0]["scene_id"] == "broken"
    assert first["change"]["status"] == "flagged"
    second = update_field(db, "north", SQUARE, start="2026-06-01", end="2026-07-31",
                          search=search, read=read)
    assert second["added"] == []
    summary = field_summary(db, "north", SQUARE)
    assert [s["scene_id"] for s in summary["series"]] == ["s0", "s1", "s2"]


# -- the reader, against a real GeoTIFF in UTM -----------------------------------


def test_reader_warps_utm_cogs_onto_the_field_grid(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    from rasterio.warp import transform as warp_transform

    from agri_edge.satellite.reader import read_field

    # A 2 km x 2 km UTM zone 13N tile around the field, 10 m pixels, stored as
    # L2A digital numbers with the baseline-04 offset (DN * 1e-4 - 0.1).
    xs, ys = warp_transform("EPSG:4326", "EPSG:32613", [LON0 - 0.01], [LAT0 + 0.014])
    tr = from_origin(xs[0], ys[0], 10, 10)
    shape = (200, 200)
    red_dn = np.full(shape, 1500, dtype=np.uint16)   # 0.05 reflectance
    nir_dn = np.full(shape, 4500, dtype=np.uint16)   # 0.35 -> NDVI 0.75
    scl = np.full(shape, 4, dtype=np.uint8)
    paths = {}
    for name, arr in (("red", red_dn), ("nir", nir_dn), ("rededge", nir_dn), ("scl", scl)):
        p = tmp_path / f"{name}.tif"
        with rasterio.open(p, "w", driver="GTiff", width=200, height=200, count=1,
                           dtype=arr.dtype, crs="EPSG:32613", transform=tr, nodata=0) as dst:
            dst.write(arr, 1)
        paths[name] = str(p)
    scene = Scene("utm-test", "2026-07-10T18:00:00Z", 0.0,
                  {k: Band(v, *((1.0, 0.0) if k == "scl" else (1e-4, -0.1))) for k, v in paths.items()})
    b = Boundary.from_geojson(SQUARE)
    bands, lats, lons = read_field(scene, b)
    obs = observe("utm-test", "2026-07-10", bands, lats, lons, b)
    assert obs.usable
    assert obs.ndvi_mean == pytest.approx(0.75, abs=0.01)


def test_ops_station_turns_a_flagged_patch_into_a_scouting_recommendation(tmp_path, monkeypatch):
    from agri_edge.ops import agronomy_service, satellite_service
    from agri_edge.ops.api import create_app_store

    monkeypatch.setattr(agronomy_service, "weather_provider",
                        lambda lat, lon: (_ for _ in ()).throw(OSError("offline")))
    agronomy_service.clear_weather_cache()
    store = create_app_store(seed=False, sqlite_path=str(tmp_path / "ops.sqlite"))
    agronomy_service.upsert_field(store, {
        "field_id": "north", "name": "North", "crop": "canola", "seeded": "2026-05-15",
        "soil": "loam", "lat": LAT0, "lon": LON0, "boundary": SQUARE})
    _series(satellite_service.db_path(store), drop=0.25, shift=0.0)
    recs = satellite_service.scouting_recommendations(store)
    assert len(recs) == 1 and recs[0]["kind"] == "scouting"
    assert "lines" in recs[0]["action"]
    summary = satellite_service.summary(store, "north")
    assert summary["change"]["status"] == "flagged"
    assert "Copernicus" in summary["attribution"]


def test_satellite_needs_a_boundary(tmp_path):
    from agri_edge.ops import agronomy_service, satellite_service
    from agri_edge.ops.api import create_app_store

    store = create_app_store(seed=False)
    agronomy_service.upsert_field(store, {
        "field_id": "nob", "name": "x", "crop": "canola", "seeded": "2026-05-15",
        "soil": "loam", "lat": LAT0, "lon": LON0})
    with pytest.raises(ValueError):
        satellite_service.summary(store, "nob")
