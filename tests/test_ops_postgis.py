"""PostGIS backend option (SIMULATED: only ever a throwaway local PostGIS).

* Selection / lazy-import / schema-file tests run everywhere.
* The live tests need a reachable Postgres WITH the postgis extension available and
  psycopg installed. Point `AGRIEDGE_TEST_PG_URL` at a throwaway server, e.g.

      AGRIEDGE_TEST_PG_URL=postgresql://postgres@127.0.0.1:55432/agriedge_test

  They skip cleanly otherwise (pytest.mark.skipif), including in CI with no database.
  Each run works in its own schema and drops it afterwards. Never point this at a
  database that matters.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest

from agri_edge.ops import db as opsdb
from agri_edge.ops.postgis import SCHEMA_SQL_PATH, postgres_reachable
from agri_edge.ops.schema import SensorReading

PG_URL = os.environ.get("AGRIEDGE_TEST_PG_URL", "")
HAVE_PG = bool(PG_URL) and postgres_reachable(PG_URL)
needs_pg = pytest.mark.skipif(not HAVE_PG, reason="no reachable PostGIS (set AGRIEDGE_TEST_PG_URL)")


@pytest.fixture(autouse=True)
def _reset():
    opsdb.reset_sensor_db()
    yield
    opsdb.reset_sensor_db()


# ---- always-on tests -------------------------------------------------------------
@pytest.mark.parametrize("url,expected", [
    ("postgresql://u@h/db", True), ("postgres://u@h/db", True), ("POSTGRESQL://u@h/db", True),
    ("sqlite:///x.db", False), ("", False), ("mysql://x", False),
])
def test_is_postgres_url(url, expected):
    assert opsdb.is_postgres_url(url) is expected


def test_sqlite_is_still_the_default_and_unset_means_no_db(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AGRIEDGE_DB_URL", raising=False)
    assert opsdb.get_sensor_db() is None and opsdb.get_detection_db() is None
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'a.db'}")
    assert type(opsdb.get_sensor_db()).__name__ == "SensorReadingStore"
    assert type(opsdb.get_detection_db()).__name__ == "DetectionStore"


def test_agriedge_db_url_is_honoured_when_database_url_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AGRIEDGE_DB_URL", f"sqlite:///{tmp_path / 'b.db'}")
    assert opsdb.get_sensor_db() is not None
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'c.db'}")
    assert opsdb.get_sensor_db().path.endswith("c.db")        # DATABASE_URL wins


def test_postgres_url_selects_postgis_store_without_connecting(monkeypatch):
    made = []

    class FakeBundle:
        def __init__(self, url):
            made.append(url)
            self.sensors = object()
            self.detections = object()

    monkeypatch.setattr(opsdb, "_postgres_stores", lambda url: FakeBundle(url))
    url = "postgresql://nobody@127.0.0.1:1/none"
    s = opsdb.get_sensor_db(url)
    d = opsdb.get_detection_db(url)
    assert s is not None and d is not None
    assert opsdb.get_sensor_db(url) is s                      # cached per URL
    assert made == [url, url]


def test_psycopg_is_imported_lazily_and_missing_psycopg_is_a_clear_error(monkeypatch):
    # importing the module must not import psycopg
    import importlib
    sys.modules.pop("psycopg", None)
    import agri_edge.ops.postgis as pg
    importlib.reload(pg)
    assert "psycopg" not in sys.modules
    # and a missing psycopg fails with an actionable message, not a stack of nonsense
    monkeypatch.setitem(sys.modules, "psycopg", None)
    with pytest.raises(ImportError, match="psycopg"):
        pg._connect("postgresql://x@127.0.0.1:1/x")
    assert pg.postgres_reachable("postgresql://x@127.0.0.1:1/x") is False


def test_unreachable_postgres_is_not_reachable_and_does_not_raise():
    assert postgres_reachable("postgresql://nobody@127.0.0.1:1/none", timeout_s=1) is False


def test_schema_file_defines_every_table_the_store_writes():
    sql = Path(SCHEMA_SQL_PATH).read_text(encoding="utf-8")
    for needle in ("CREATE EXTENSION IF NOT EXISTS postgis", "TABLE IF NOT EXISTS farms",
                   "TABLE IF NOT EXISTS devices", "TABLE IF NOT EXISTS sensor_readings",
                   "TABLE IF NOT EXISTS detections", "world_lat", "position_uncertainty_m",
                   "georef_status", "geometry(Point, 4326)"):
        assert needle in sql, needle


def test_compose_file_has_no_default_password_and_loads_the_schema():
    root = Path(__file__).resolve().parents[1]
    text = (root / "ground_iot" / "docker-compose.postgis.yml").read_text(encoding="utf-8")
    assert "postgis/postgis" in text
    assert "schema_postgis.sql" in text and "docker-entrypoint-initdb.d" in text
    assert "${POSTGRES_PASSWORD:?" in text                   # compose refuses to start without it
    assert "127.0.0.1:5432:5432" in text                     # loopback only
    assert "SIMULATED" in text
    import re
    assert not re.search(r"POSTGRES_PASSWORD:\s*[A-Za-z0-9]", text)


def test_sqlite_detection_store_roundtrips_georef_columns_and_migrates_old_files(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)          # an "old" file: detections table without georef columns
    con.execute("CREATE TABLE detections (detection_id TEXT PRIMARY KEY, ts TEXT NOT NULL, "
                "label TEXT NOT NULL, confidence REAL NOT NULL, bbox_json TEXT NOT NULL, lat REAL, "
                "lon REAL, model_name TEXT, model_version TEXT, backend TEXT, "
                "validated_locally INTEGER NOT NULL DEFAULT 0, may_drive_treatment INTEGER NOT NULL "
                "DEFAULT 0, in_treatment_zone INTEGER, farm_id TEXT NOT NULL DEFAULT 'demo_farm', "
                "mission_id TEXT, frame_id TEXT, payload_json TEXT, synthetic INTEGER NOT NULL "
                "DEFAULT 0)")
    con.commit()
    con.close()
    store = opsdb.DetectionStore(str(path))                 # must migrate, not crash
    store.upsert({"detection_id": "d1", "ts": "2026-09-19T12:00:00Z", "label": "weed",
                  "confidence": 0.9, "bbox": [0.1, 0.1, 0.2, 0.2], "world_lat": 45.1,
                  "world_lon": -75.2, "local_x": 1.5, "local_y": -2.5,
                  "position_uncertainty_m": 0.7, "georef_status": "OK"})
    row = store.list()[0]
    assert (row["world_lat"], row["world_lon"], row["local_x"], row["local_y"]) == (45.1, -75.2, 1.5, -2.5)
    assert row["position_uncertainty_m"] == 0.7 and row["georef_status"] == "OK"
    store.upsert({"detection_id": "d2", "ts": "2026-09-19T12:00:01Z", "label": "crop",
                  "confidence": 0.5, "bbox": [0, 0, 1, 1]})
    d2 = [r for r in store.list() if r["detection_id"] == "d2"][0]
    assert d2["world_lat"] is None and d2["georef_status"] is None


# ---- live PostGIS tests -------------------------------------------------------------
@pytest.fixture
def pg_url():
    import psycopg
    schema = "t_" + uuid.uuid4().hex[:10]
    with psycopg.connect(PG_URL, autocommit=True) as con:
        con.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in PG_URL else "?"
    url = f"{PG_URL}{sep}options={quote(f'-csearch_path={schema},public')}"
    yield url
    with psycopg.connect(PG_URL, autocommit=True) as con:
        con.execute(f"DROP SCHEMA {schema} CASCADE")


@needs_pg
def test_postgis_sensor_roundtrip_idempotent_and_selected_by_url(pg_url):
    s = opsdb.get_sensor_db(pg_url)
    assert type(s).__name__ == "PostgisSensorStore"
    r = SensorReading(reading_id="r1", sensor_id="soil1", ts="2026-09-19T12:00:00Z",
                      metric="moisture_pct", value=22.5, unit="%", synthetic=True,
                      farm_id="farm_x", depth_cm=10.0)
    s.upsert(r)
    s.upsert(r)                                  # replay -> still one row
    rows = s.list(sensor_id="soil1")
    assert len(rows) == 1
    got = rows[0]
    assert got["value"] == 22.5 and got["quality"] == "GOOD" and got["origin"] == "MEASURED"
    assert got["synthetic"] is True and got["farm_id"] == "farm_x" and got["depth_cm"] == 10.0
    assert got["ts"] == "2026-09-19T12:00:00+00:00"           # reported in UTC, like the SQLite path
    s.upsert(SensorReading(reading_id="r1", sensor_id="soil1", ts="2026-09-19T12:00:00Z",
                           metric="moisture_pct", value=30.0, unit="%"))
    assert s.list("soil1")[0]["value"] == 30.0                # upsert updates


@needs_pg
def test_postgis_matches_sqlite_interface_for_sensors(pg_url, tmp_path):
    lite = opsdb.SensorReadingStore(str(tmp_path / "l.db"))
    pg = opsdb.get_sensor_db(pg_url)
    for i in range(5):
        r = SensorReading(reading_id=f"r{i}", sensor_id="s", ts=f"2026-09-19T12:0{i}:00Z",
                          metric="m", value=float(i), unit="u")
        lite.upsert(r)
        pg.upsert(r)
    a = [(x["reading_id"], x["value"]) for x in lite.list("s", limit=3)]
    b = [(x["reading_id"], x["value"]) for x in pg.list("s", limit=3)]
    assert a == b == [("r4", 4.0), ("r3", 3.0), ("r2", 2.0)]


@needs_pg
def test_postgis_detection_roundtrip_with_geometry(pg_url):
    import psycopg
    d = opsdb.get_detection_db(pg_url)
    assert type(d).__name__ == "PostgisDetectionStore"
    d.upsert({"detection_id": "d1", "ts": "2026-09-19T12:00:01Z", "label": "weed",
              "confidence": 0.88, "bbox": [0.1, 0.2, 0.3, 0.4], "world_lat": 45.4011,
              "world_lon": -75.6987, "local_x": 3.0, "local_y": 4.0,
              "position_uncertainty_m": 0.6, "georef_status": "OK", "synthetic": True,
              "may_drive_treatment": False, "validated_locally": False})
    d.upsert({"detection_id": "d2", "ts": "2026-09-19T12:00:02Z", "label": "crop",
              "confidence": 0.5, "bbox": [0, 0, 1, 1]})        # no position
    rows = d.list()
    assert [r["detection_id"] for r in rows] == ["d2", "d1"]
    r1 = rows[1]
    assert r1["bbox"] == [0.1, 0.2, 0.3, 0.4] and r1["world_lat"] == 45.4011
    assert r1["position_uncertainty_m"] == 0.6 and r1["georef_status"] == "OK"
    assert r1["may_drive_treatment"] is False and r1["synthetic"] is True
    assert d.list(label="weed")[0]["detection_id"] == "d1"
    with psycopg.connect(pg_url) as con:                        # geom only where we have a position
        n_geom = con.execute("SELECT count(*) FROM detections WHERE geom IS NOT NULL").fetchone()[0]
        n_all = con.execute("SELECT count(*) FROM detections").fetchone()[0]
        x, y = con.execute("SELECT ST_X(geom), ST_Y(geom) FROM detections "
                           "WHERE detection_id='d1'").fetchone()
    assert (n_geom, n_all) == (1, 2) and (x, y) == (-75.6987, 45.4011)
    d.upsert({"detection_id": "d1", "ts": "2026-09-19T12:00:01Z", "label": "weed",
              "confidence": 0.9, "bbox": [0.1, 0.2, 0.3, 0.4]})  # replay without position clears geom
    assert d.list(label="weed")[0]["world_lat"] is None
    assert len([r for r in d.list() if r["detection_id"] == "d1"]) == 1


@needs_pg
def test_postgis_schema_is_idempotent(pg_url):
    from agri_edge.ops.postgis import PostgisStore
    PostgisStore(pg_url)
    PostgisStore(pg_url)


@needs_pg
def test_ops_store_and_ingest_write_through_postgis(pg_url, monkeypatch):
    from datetime import datetime, timezone
    import json
    from agri_edge.iot.transport import InMemoryTransport
    from agri_edge.ops.live_ingest import OpsIngestor
    from agri_edge.ops.mqtt_sim import build_demo_messages
    from agri_edge.ops.store import OpsStore

    monkeypatch.setenv("DATABASE_URL", pg_url)
    store = OpsStore()
    ing = OpsIngestor(store, InMemoryTransport(), now_fn=lambda: datetime.now(timezone.utc))
    for topic, body in build_demo_messages():
        ing.handle_message(topic, json.dumps(body).encode())
    for topic, body in build_demo_messages():                   # replay
        ing.handle_message(topic, json.dumps(body).encode())
    s = opsdb.get_sensor_db()
    rows = s.list(limit=500)
    assert rows and len(rows) == len({r["reading_id"] for r in rows}) == len(store.sensor_readings)
    dets = opsdb.get_detection_db().list()
    assert len(dets) == 2 and all(x["may_drive_treatment"] is False for x in dets)
    assert all(x["synthetic"] for x in dets)
