"""Agronomy through the ops station: fields, weather, probes, recommendations."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest

from agri_edge.agronomy.weather import parse_open_meteo
from agri_edge.ops import agronomy_service as svc
from agri_edge.ops.api import OpsHandler, create_app_store
from agri_edge.ops.ingest import ingest

from test_agronomy import _open_meteo_payload

TODAY = datetime.now(timezone.utc).date()
FIELD = {"field_id": "north", "name": "North quarter", "crop": "potato",
         "seeded": (TODAY - timedelta(days=60)).isoformat(), "soil": "sandy_loam",
         "lat": 50.45, "lon": -104.6, "elevation_m": 577.0, "irrigated": True}


@pytest.fixture(autouse=True)
def dry_hot_weather(monkeypatch):
    calls = []

    def provider(lat, lon):
        calls.append((lat, lon))
        return parse_open_meteo(_open_meteo_payload(TODAY - timedelta(days=65), 72,
                                                    tmax=30.0, tmin=15.0), TODAY)

    svc.clear_weather_cache()
    monkeypatch.setattr(svc, "weather_provider", provider)
    yield calls
    svc.clear_weather_cache()


def _server(tmp_path):
    store = create_app_store(seed=False, sqlite_path=str(tmp_path / "ops.sqlite"))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OpsHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return store, httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _call(base, path, body=None):
    req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_a_dry_irrigated_potato_field_is_told_to_irrigate(tmp_path, dry_hot_weather):
    store, httpd, base = _server(tmp_path)
    try:
        assert _call(base, "/api/ops/fields", FIELD)[0] == 200
        status, out = _call(base, "/api/ops/agronomy?field=north")
        assert status == 200
        irr = [r for r in out["recommendations"] if r["kind"] == "irrigation"]
        assert irr and irr[0]["title"].startswith("Irrigate")
        assert "no soil probe in this field; depletion is modelled" in irr[0]["missing"]
        status, allrecs = _call(base, "/api/ops/recommendations")
        assert status == 200 and allrecs["recommendations"][0]["priority"] == 1
        # Cached: the second and third calls did not refetch.
        assert len(dry_hot_weather) == 1
    finally:
        httpd.shutdown()


def test_a_probe_saying_wet_overrules_the_model(tmp_path):
    store, httpd, base = _server(tmp_path)
    try:
        _call(base, "/api/ops/fields", FIELD)
        yesterday = datetime.combine(TODAY - timedelta(days=1), datetime.min.time(),
                                     tzinfo=timezone.utc) + timedelta(hours=12)
        ingest(store, "agriedge/farm/f1/zone/z1/soil",
               {"device_id": "p1", "ts": yesterday.isoformat(), "moisture_pct": 23.0})
        _, out = _call(base, "/api/ops/agronomy?field=north")
        assert out["water"]["confidence"] == "high"
        assert any(b["probe_reset"] for b in out["balance_tail"])
    finally:
        httpd.shutdown()


def test_fields_survive_a_restart(tmp_path):
    db = str(tmp_path / "ops.sqlite")
    store = create_app_store(seed=False, sqlite_path=db)
    svc.upsert_field(store, FIELD)
    again = create_app_store(seed=False, sqlite_path=db)
    assert [f.field_id for f in svc.list_fields(again)] == ["north"]


@pytest.mark.parametrize("bad", [
    {**FIELD, "crop": "rice"},
    {**FIELD, "soil": "moon_dust"},
    {**FIELD, "lat": 123.0},
    {**FIELD, "seeded": "yesterday"},
    {**FIELD, "colour": "green"},
    {"field_id": "x"},
])
def test_invalid_fields_are_400(tmp_path, bad):
    store, httpd, base = _server(tmp_path)
    try:
        assert _call(base, "/api/ops/fields", bad)[0] == 400
    finally:
        httpd.shutdown()


def test_unknown_field_is_404_and_missing_param_400(tmp_path):
    store, httpd, base = _server(tmp_path)
    try:
        assert _call(base, "/api/ops/agronomy?field=nope")[0] == 404
        assert _call(base, "/api/ops/agronomy")[0] == 400
    finally:
        httpd.shutdown()


def test_offline_with_no_station_says_so(tmp_path, monkeypatch):
    def offline(lat, lon):
        raise OSError("no route to host")

    monkeypatch.setattr(svc, "weather_provider", offline)
    store = create_app_store(seed=False)
    svc.upsert_field(store, FIELD)
    recs = svc.assess(store, "north")["recommendations"]
    assert recs[0]["kind"] == "data" and recs[0]["title"] == "No weather since seeding"


def test_station_days_are_used_when_offline(monkeypatch):
    monkeypatch.setattr(svc, "weather_provider", lambda lat, lon: (_ for _ in ()).throw(OSError()))
    store = create_app_store(seed=False)
    svc.upsert_field(store, FIELD)
    for back in range(1, 4):
        day = TODAY - timedelta(days=back)
        for h in range(24):
            ts = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=h)
            ingest(store, "agriedge/farm/f1/zone/z1/weather",
                   {"device_id": "wx", "ts": ts.isoformat(), "air_temp_c": 10 + h * 0.5, "rh_pct": 60})
    out = svc.assess(store, "north")
    assert out["weather_sources"] == ["station"]


def test_seeded_demo_weather_is_not_agronomy_input():
    """Synthetic observations must never become a field's weather."""
    store = create_app_store(seed=True)
    ws = svc.weather_for(store, 50.45, -104.6, 577.0)
    assert all(d.source != "station" for d in ws.days)


def test_today_is_a_date():
    assert isinstance(TODAY, date)
