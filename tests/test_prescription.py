"""Prescription maps: grid building, safety clipping, approval gate, and the
ISOXML / shapefile outputs read back."""

from __future__ import annotations

import io
import math
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pytest

from agri_edge.geo.geofence import project_to_local
from agri_edge.prescription import isoxml, shapefile
from agri_edge.prescription.export import NotApproved, approve, export_zip
from agri_edge.prescription.grid import DetectionPoint, spot_spray, variable_rate

LAT0, LON0 = 50.45, -104.60
DLAT = 120 / 111_320
DLON = 120 / (111_320 * math.cos(math.radians(LAT0)))
FIELD = {"type": "Polygon", "coordinates": [[
    [LON0, LAT0], [LON0 + DLON, LAT0], [LON0 + DLON, LAT0 + DLAT], [LON0, LAT0 + DLAT], [LON0, LAT0]]]}
MODEL = ("imageweeds_yolox_s", "2")


def _at(e_m, n_m, err=0.0, model=MODEL, conf=0.9):
    lat = LAT0 + math.degrees(n_m / 6_378_137.0)
    lon = LON0 + math.degrees(e_m / (6_378_137.0 * math.cos(math.radians(LAT0))))
    return DetectionPoint(lat, lon, "kochia", conf, err, model)


def test_spot_spray_turns_on_the_cells_with_weeds():
    g = spot_spray("north", FIELD, [_at(61, 61)], rate=100, cell_m=6, buffer_m=10,
                   validated_models={MODEL})
    assert g.validated and not g.issues
    on = np.argwhere(g.rates > 0)
    assert on.tolist() == [[10, 10]]                  # 61 m // 6 m
    assert g.summary()["treated_ha"] == pytest.approx(0.0036)


def test_position_error_spreads_to_neighbouring_cells():
    g = spot_spray("north", FIELD, [_at(59.5, 59.5, err=2.0)], rate=100, cell_m=6,
                   validated_models={MODEL})
    assert int((g.rates > 0).sum()) == 4              # near a corner of four cells


def test_nothing_is_applied_in_the_buffer_or_outside():
    g = spot_spray("north", FIELD, [_at(3, 60), _at(60, 118), _at(500, 500)], rate=100,
                   cell_m=6, buffer_m=10, validated_models={MODEL})
    assert int((g.rates > 0).sum()) == 0
    assert any("outside the treatment area" in n for n in g.notes)


def test_holes_are_never_sprayed():
    h = 30 / 111_320
    hole = [[LON0 + DLON / 2 - h, LAT0 + DLAT / 2 - h], [LON0 + DLON / 2 + h, LAT0 + DLAT / 2 - h],
            [LON0 + DLON / 2 + h, LAT0 + DLAT / 2 + h], [LON0 + DLON / 2 - h, LAT0 + DLAT / 2 + h],
            [LON0 + DLON / 2 - h, LAT0 + DLAT / 2 - h]]
    with_hole = {"type": "Polygon", "coordinates": [FIELD["coordinates"][0], hole]}
    g = spot_spray("north", with_hole, [_at(60, 60)], rate=100, cell_m=6, validated_models={MODEL})
    assert int((g.rates > 0).sum()) == 0


def test_an_unvalidated_model_cannot_produce_an_approvable_map():
    g = spot_spray("north", FIELD, [_at(60, 60)], rate=100, cell_m=6)   # no validated models
    assert not g.validated
    assert "not validated on local imagery" in g.issues[0]
    out = approve(g, "agronomist", wind_ms=2.0)
    assert out["approved"] is False
    with pytest.raises(NotApproved):
        export_zip(g, FIELD, "isoxml", field_name="North")


def test_rates_are_clamped_to_the_safety_limit():
    g = spot_spray("north", FIELD, [_at(60, 60)], rate=5000, cell_m=6, validated_models={MODEL})
    assert g.rates.max() == g.constraints.max_rate_l_ha
    assert "clamped" in g.notes[0]


@pytest.mark.parametrize("wind,ok", [(None, False), (7.0, False), (3.0, True)])
def test_approval_needs_a_calm_measured_wind(wind, ok):
    g = spot_spray("north", FIELD, [_at(60, 60)], rate=100, cell_m=6, validated_models={MODEL})
    assert approve(g, "agronomist", wind)["approved"] is ok


def test_variable_rate_zones_from_values():
    samples = {}
    for e in range(5, 120, 10):
        for n in range(5, 120, 10):
            p = _at(e, n)
            samples[(p.lat, p.lon)] = 0.3 if e < 60 else 0.8      # west weak, east strong
    g = variable_rate("north", FIELD, samples, [40.0, 120.0], cell_m=20, buffer_m=0, invert=True)
    assert g.validated
    west = g.rates[:, 0]
    east = g.rates[:, -1]
    assert (west[west > 0] == 120).all() and (east[east > 0] == 40).all()


# -- ISOXML ------------------------------------------------------------------------


def _approved_grid():
    g = spot_spray("north", FIELD, [_at(60, 60), _at(30, 90)], rate=80, cell_m=6,
                   validated_models={MODEL})
    assert approve(g, "agronomist", 2.0)["approved"]
    return g


def test_isoxml_round_trip():
    g = _approved_grid()
    xml, binary = isoxml.taskdata_xml(g, FIELD, field_name="North")
    root = ET.fromstring(xml)
    assert root.tag == "ISO11783_TaskData" and root.get("VersionMajor") == "4"
    tsk = root.find("TSK")
    # Position lost / out of field -> zone 2, which applies nothing.
    assert tsk.get("I") == "2" and tsk.get("J") == "2"
    off = next(z for z in tsk.findall("TZN") if z.get("A") == "2")
    assert off.find("PDV").get("B") == "0"
    assert tsk.find("TZN/PDV").get("A") == "0001"            # volume per area
    ids = {e.get("A") for e in root.iter() if e.tag in ("CTR", "FRM", "PFD", "PDT")}
    for ref in (tsk.get("C"), tsk.get("D"), tsk.get("E"), tsk.find("TZN/PDV").get("C")):
        assert ref in ids, f"dangling reference {ref}"
    grd, rates = isoxml.read_grid(xml, binary)
    assert grd["I"] == "2" and int(grd["E"]) == g.cols and int(grd["F"]) == g.rows
    np.testing.assert_allclose(rates, g.rates)
    # The degree cell size maps back onto the metre grid.
    n_deg = float(grd["C"])
    assert n_deg * 6_378_137.0 * math.pi / 180 == pytest.approx(6.0, rel=1e-9)


def test_isoxml_grid_origin_is_the_south_west_corner():
    g = _approved_grid()
    xml, _ = isoxml.taskdata_xml(g, FIELD, field_name="North")
    grd = ET.fromstring(xml).find("TSK/GRD")
    assert float(grd.get("A")) == pytest.approx(LAT0)
    assert float(grd.get("B")) == pytest.approx(LON0)


# -- shapefile ---------------------------------------------------------------------


def test_shapefile_is_readable_by_pyshp():
    pyshp = pytest.importorskip("shapefile")
    g = _approved_grid()
    data = export_zip(g, FIELD, "shapefile", field_name="North")
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    for ext in (".shp", ".shx", ".dbf", ".prj"):
        assert f"rx_north{ext}" in names
    r = pyshp.Reader(shp=io.BytesIO(z.read("rx_north.shp")), shx=io.BytesIO(z.read("rx_north.shx")),
                     dbf=io.BytesIO(z.read("rx_north.dbf")))
    assert len(r) == int(g.applicable.sum())
    rates = sorted({round(rec["RATE"], 2) for rec in r.records()})
    assert rates == [0.0, 80.0]
    shp = r.shape(0)
    assert shp.shapeType == 5 and len(shp.points) == 5


def test_shapefile_outer_rings_are_clockwise():
    files = shapefile.write([[(0, 0), (1, 0), (1, 1), (0, 1)]], [{"RATE": 1}], [("RATE", "N", 8, 2)])
    shp = files[".shp"]
    n_points = int.from_bytes(shp[100 + 8 + 40:100 + 8 + 44], "little")
    pts = [tuple(np.frombuffer(shp[100 + 8 + 48 + 16 * i:100 + 8 + 64 + 16 * i], "<f8"))
           for i in range(n_points)]
    assert shapefile._signed_area(pts[:-1]) < 0


def test_geojson_export_and_unknown_format():
    g = _approved_grid()
    z = zipfile.ZipFile(io.BytesIO(export_zip(g, FIELD, "geojson", field_name="North")))
    assert "rx_north.geojson" in z.namelist() and "README.txt" in z.namelist()
    with pytest.raises(ValueError):
        export_zip(g, FIELD, "kml", field_name="North")


def test_projection_helper_consistency():
    e, n = project_to_local([LAT0 + DLAT], [LON0 + DLON], (LAT0, LON0))[0]
    assert e == pytest.approx(120, rel=1e-3) and n == pytest.approx(120, rel=1e-3)


# -- through the ops station ------------------------------------------------------


def _ops(tmp_path, monkeypatch):
    import json
    import threading
    from http.server import ThreadingHTTPServer

    from agri_edge.ops import agronomy_service
    from agri_edge.ops.api import OpsHandler, create_app_store
    from agri_edge.ops.ingest import ingest

    monkeypatch.setenv("AGRIEDGE_VALIDATIONS_DIR", str(tmp_path / "validations"))
    store = create_app_store(seed=False, sqlite_path=str(tmp_path / "ops.sqlite"))
    agronomy_service.upsert_field(store, {"field_id": "north", "name": "North", "crop": "canola",
                                          "seeded": "2026-05-15", "soil": "loam", "lat": LAT0,
                                          "lon": LON0, "boundary": FIELD})
    for e, n in ((61, 61), (31, 91)):
        p = _at(e, n)
        ingest(store, "agriedge/farm/f1/vehicle/scout1/detections", {
            "model": {"name": MODEL[0], "version": MODEL[1]},
            "detections": {"type": "FeatureCollection", "features": [{
                "type": "Feature", "id": f"{e}", "geometry": {"type": "Point", "coordinates": [p.lon, p.lat]},
                "properties": {"label": "kochia", "confidence": 0.9, "position_error_m": 1.0}}]}})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OpsHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(path, body=None, raw=False):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
                return r.status, (data if raw else json.loads(data))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    return store, httpd, call


def test_ops_spot_spray_is_refused_until_the_model_is_validated_locally(tmp_path, monkeypatch):
    store, httpd, call = _ops(tmp_path, monkeypatch)
    try:
        st, rx = call("/api/ops/prescriptions", {"field_id": "north", "source": "detections", "rate": 80})
        assert st == 201 and rx["cells_on"] >= 2 and not rx["validated"]
        st, out = call(f"/api/ops/prescriptions/{rx['prescription_id']}/approve",
                       {"actor": "agronomist", "wind_ms": 2.0})
        assert st == 200 and out["approved"] is False
        st, _ = call(f"/api/ops/prescriptions/{rx['prescription_id']}/export?format=isoxml")
        assert st == 409
    finally:
        httpd.shutdown()


def test_ops_spot_spray_with_a_validated_model_exports_isoxml(tmp_path, monkeypatch):
    import json

    store, httpd, call = _ops(tmp_path, monkeypatch)
    vdir = tmp_path / "validations"
    vdir.mkdir()
    (vdir / "r1.json").write_text(json.dumps({"model_name": MODEL[0], "model_version": MODEL[1],
                                              "passed": True}))
    try:
        st, rx = call("/api/ops/prescriptions", {"field_id": "north", "source": "detections", "rate": 80})
        assert rx["validated"], rx["issues"]
        rid = rx["prescription_id"]
        assert call(f"/api/ops/prescriptions/{rid}/approve", {"actor": "a", "wind_ms": 9.0})[1]["approved"] is False
        assert call(f"/api/ops/prescriptions/{rid}/approve", {"actor": "a", "wind_ms": 2.0})[1]["approved"]
        st, data = call(f"/api/ops/prescriptions/{rid}/export?format=isoxml", raw=True)
        assert st == 200
        z = zipfile.ZipFile(io.BytesIO(data))
        grd, rates = isoxml.read_grid(z.read("TASKDATA/TASKDATA.XML"), z.read("TASKDATA/GRD00001.BIN"))
        assert (rates > 0).sum() >= 2
        audit = [e for e in store.audit if e.action == "rx_approve"]
        assert audit[-1].detail == "True"
    finally:
        httpd.shutdown()


def test_prescriptions_survive_a_restart(tmp_path, monkeypatch):
    from agri_edge.ops import prescription_service
    from agri_edge.ops.api import create_app_store

    store, httpd, call = _ops(tmp_path, monkeypatch)
    httpd.shutdown()
    rx = prescription_service.build(store, {"field_id": "north", "source": "detections", "rate": 80})
    again = create_app_store(seed=False, sqlite_path=store.sqlite_path)
    got = prescription_service.get(again, rx["prescription_id"])["grid"]
    assert got.summary()["cells_on"] == rx["cells_on"]


def test_ops_variable_rate_from_the_satellite(tmp_path, monkeypatch):
    from test_satellite import _grid, _bands  # noqa: F401 - reuse the synthetic scene helpers

    from agri_edge.ops import prescription_service, satellite_service
    from agri_edge.satellite import series
    from agri_edge.satellite.field import Boundary, observe
    from agri_edge.satellite.reader import field_grid

    store, httpd, call = _ops(tmp_path, monkeypatch)
    httpd.shutdown()
    b = Boundary.from_geojson(FIELD)
    _, lats, lons = field_grid(b, 10.0)
    en = project_to_local(lats.ravel(), lons.ravel(), b.origin)
    ndvi = np.where(en[:, 0].reshape(lats.shape) < 60, 0.35, 0.8)
    obs = observe("s1", "2026-07-10", _bands(lats, ndvi), lats, lons, b, cell_m=20)
    series.save(satellite_service.db_path(store), "north", obs.to_dict())
    rx = prescription_service.build(store, {"field_id": "north", "source": "satellite",
                                            "rates_by_zone": [40, 120], "buffer_m": 0})
    assert rx["validated"] and rx["cells_on"] > 0
    g = prescription_service.get(store, rx["prescription_id"])["grid"]
    assert set(np.unique(g.rates[g.rates > 0])) <= {40.0, 120.0}
