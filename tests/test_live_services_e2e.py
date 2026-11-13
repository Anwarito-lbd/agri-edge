"""Real broker + real PostGIS together (BENCH: throwaway local services, never production).

    AGRIEDGE_TEST_MQTT=127.0.0.1:18830 \
    AGRIEDGE_TEST_PG_URL=postgresql://postgres:...@127.0.0.1:5432/agriedge_test pytest tests/test_live_services_e2e.py

Skips cleanly unless BOTH are reachable. The CI job drafted in `docs/ci/live-services.yml`
(NOT active: the push token lacked the `workflow` scope; see docs/ci/README.md) starts both and
runs this file with tests/test_ops_postgis.py and tests/test_ops_ingest_broker.py.
Synthetic data only.
"""
from __future__ import annotations

import os
import socket
import time
import uuid
from urllib.parse import quote

import pytest

from agri_edge.ops import db as opsdb
from agri_edge.ops.postgis import postgres_reachable

MQTT = os.environ.get("AGRIEDGE_TEST_MQTT", "")
PG_URL = os.environ.get("AGRIEDGE_TEST_PG_URL", "")


def _mqtt_ok() -> bool:
    if not MQTT:
        return False
    try:
        import paho.mqtt.client  # noqa: F401
        host, port = MQTT.rsplit(":", 1)
        with socket.create_connection((host, int(port)), timeout=1):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (_mqtt_ok() and PG_URL and postgres_reachable(PG_URL)),
    reason="needs a real MQTT broker (AGRIEDGE_TEST_MQTT) AND PostGIS (AGRIEDGE_TEST_PG_URL)",
)


@pytest.fixture(autouse=True)
def _reset():
    opsdb.reset_sensor_db()
    yield
    opsdb.reset_sensor_db()


@pytest.fixture
def pg_url():
    import psycopg
    schema = "e2e_" + uuid.uuid4().hex[:10]
    with psycopg.connect(PG_URL, autocommit=True) as con:
        con.execute(f"CREATE SCHEMA {schema}")
    sep = "&" if "?" in PG_URL else "?"
    yield f"{PG_URL}{sep}options={quote(f'-csearch_path={schema},public')}"
    with psycopg.connect(PG_URL, autocommit=True) as con:
        con.execute(f"DROP SCHEMA {schema} CASCADE")


def test_mqtt_to_ingest_to_postgis_roundtrip(pg_url, monkeypatch):
    """Publish over a real broker -> OpsIngestor -> rows in real PostGIS, replay deduped."""
    from agri_edge.iot.transport import PahoTransport
    from agri_edge.ops.live_ingest import OpsIngestor
    from agri_edge.ops.mqtt_sim import publish_demo
    from agri_edge.ops.store import OpsStore

    monkeypatch.setenv("DATABASE_URL", pg_url)
    host, port = MQTT.rsplit(":", 1)
    farm = "e" + uuid.uuid4().hex[:8]
    store = OpsStore()
    sub = PahoTransport(host, int(port), client_id="e2e-sub-" + farm)
    ing = OpsIngestor(store, sub)
    ing.start()
    assert sub.wait_connected(5)
    time.sleep(0.3)
    pub = PahoTransport(host, int(port), client_id="e2e-pub-" + farm)
    pub.connect()
    assert pub.wait_connected(5)
    try:
        publish_demo(pub, farm=farm, replay=True)
        deadline = time.time() + 8
        while time.time() < deadline and ing.stats["received"] < 14:
            time.sleep(0.05)
    finally:
        pub.disconnect()
        ing.stop()

    assert ing.stats["accepted"] == 7 and ing.stats["duplicate"] == 7
    dets = opsdb.get_detection_db().list()
    assert len(dets) == 2
    assert all(d["may_drive_treatment"] is False and d["synthetic"] for d in dets)
    rows = opsdb.get_sensor_db().list(limit=500)
    assert rows and len(rows) == len({r["reading_id"] for r in rows}) == len(store.sensor_readings)


def test_postgis_spatial_query_over_ingested_detections(pg_url):
    """The reason PostGIS is here: a real ST_DWithin over stored detection geometry."""
    import psycopg
    d = opsdb.get_detection_db(pg_url)
    base = {"ts": "2026-10-01T12:00:00Z", "label": "weed", "confidence": 0.9,
            "bbox": [0, 0, 1, 1], "georef_status": "OK", "synthetic": True}
    d.upsert({**base, "detection_id": "near", "world_lat": 45.40000, "world_lon": -75.70000})
    d.upsert({**base, "detection_id": "far", "world_lat": 45.50000, "world_lon": -75.70000})
    with psycopg.connect(pg_url) as con:
        hits = con.execute(
            "SELECT detection_id FROM detections WHERE ST_DWithin("
            "geom::geography, ST_SetSRID(ST_MakePoint(-75.7, 45.4001), 4326)::geography, 50)"
        ).fetchall()
    assert [h[0] for h in hits] == ["near"]
