"""SQLite SensorReading + detections persistence and API wiring."""
from __future__ import annotations

import json
from pathlib import Path

from agri_edge.ops.db import DetectionStore, SensorReadingStore, get_detection_db, reset_sensor_db
from agri_edge.ops.schema import SensorReading
from agri_edge.ops.store import OpsStore


def test_sqlite_sensor_and_detection_roundtrip(tmp_path: Path):
    db_path = tmp_path / "ops.db"
    sensors = SensorReadingStore(str(db_path))
    sensors.upsert(
        SensorReading(
            reading_id="r1",
            sensor_id="soil_1",
            ts="2026-09-19T12:00:00Z",
            metric="moisture",
            value=22.5,
            unit="%",
        )
    )
    assert sensors.list(sensor_id="soil_1")[0]["value"] == 22.5

    dets = DetectionStore(str(db_path))
    dets.upsert(
        {
            "detection_id": "det1",
            "ts": "2026-09-19T12:00:01Z",
            "label": "weed",
            "confidence": 0.88,
            "bbox": [0.1, 0.2, 0.3, 0.4],
            "validated_locally": False,
            "may_drive_treatment": False,
            "synthetic": True,
            "model_name": "weed_crop_yolox_s",
            "model_version": "0.1.0",
            "backend": "simulated",
        }
    )
    rows = dets.list(label="weed")
    assert len(rows) == 1
    assert rows[0]["bbox"] == [0.1, 0.2, 0.3, 0.4]
    assert rows[0]["validated_locally"] is False
    assert rows[0]["may_drive_treatment"] is False


def test_ops_store_persist_detection_with_database_url(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "via_env.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    reset_sensor_db()
    store = OpsStore()
    store.persist_detection(
        {
            "detection_id": "det_env",
            "ts": "2026-09-19T12:00:00Z",
            "label": "crop",
            "confidence": 0.5,
            "bbox": [0, 0, 1, 1],
            "validated_locally": False,
            "may_drive_treatment": False,
        }
    )
    db = get_detection_db()
    assert db is not None
    assert any(r["detection_id"] == "det_env" for r in db.list())
    reset_sensor_db()


def test_detections_api_get_post():
    from agri_edge.ops.api import OpsHandler, get_store, reset_store
    from http.server import HTTPServer
    import threading
    import urllib.request

    reset_store()
    store = get_store()
    httpd = HTTPServer(("127.0.0.1", 0), OpsHandler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ops/detections",
            data=json.dumps(
                {
                    "label": "weed",
                    "confidence": 0.77,
                    "bbox": [0.2, 0.2, 0.5, 0.5],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode())
            assert resp.status == 201
            assert body["detection"]["label"] == "weed"
            assert body["detection"]["may_drive_treatment"] is False
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ops/detections", timeout=5) as resp:
            got = json.loads(resp.read().decode())
            assert got["count"] >= 1
            assert any(d["label"] == "weed" for d in got["detections"])
    finally:
        httpd.shutdown()
        reset_store()
