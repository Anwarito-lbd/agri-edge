"""The pieces are connected: aircraft -> ops station -> map, and ground sensors
-> ops station, through one ingest path that survives a restart.

Before 24 Sept 2026 none of this existed: the ops station showed seeded demo
data only, nothing accepted a reading, and the edge published nothing.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import timedelta
from http.server import ThreadingHTTPServer

import numpy as np
import pytest

from agri_edge.capture.camera import SimulatedCamera
from agri_edge.config import Config
from agri_edge.inference.engine import Detection, InferenceEngine, ModelMetadata
from agri_edge.iot.edge_publisher import (
    EdgePublisher,
    HttpTransport,
    build_publisher,
    detections_message,
)
from agri_edge.ops.api import OpsHandler, create_app_store
from agri_edge.ops.ingest import IngestError, ingest, replay_ingest_log
from agri_edge.ops.mqtt_ingest import handle_message
from agri_edge.ops.store import OpsStore
from agri_edge.ops.types import AlertSeverity, QualityFlag, utcnow
from agri_edge.pipeline.runner import Pipeline
from agri_edge.store.spool import Spool
from agri_edge.telemetry.mavlink_link import SimulatedTelemetry


class _CentreEngine(InferenceEngine):
    """One weed in the middle of every frame."""

    def __init__(self):
        super().__init__(ModelMetadata(name="centre", version="1", class_names=["kochia"]))

    def infer(self, image):
        return [Detection("kochia", 0.9, (0.45, 0.45, 0.55, 0.55))]


def _serve(tmp_path, seed=False):
    store = create_app_store(seed=seed, sqlite_path=str(tmp_path / "ops.sqlite"))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OpsHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return store, httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return json.loads(r.read())


def _post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


# -- aircraft -> station ------------------------------------------------------------


def test_a_flight_appears_on_the_ops_map(tmp_path):
    store, httpd, base = _serve(tmp_path)
    try:
        cfg = Config()
        cfg.camera_geometry.enabled = True
        cfg.publish.health_every_frames = 2
        pub = EdgePublisher(HttpTransport(base), farm_id="f1", vehicle_id="scout1")
        pipe = Pipeline(cfg, SimulatedCamera(resolution=(64, 48)), SimulatedTelemetry(),
                        Spool(tmp_path / "spool"), _CentreEngine(), publisher=pub)
        for _ in range(4):
            assert pipe.process_once() is not None

        assert pub.stats.errors == 0, pub.stats.last_error
        assert pub.stats.sent == 4 + 2          # frames + health every 2nd frame
        layer = _get(base, "/api/ops/map/detections")
        assert len(layer["features"]) == 4
        f = layer["features"][0]
        assert f["properties"]["label"] == "kochia"
        assert f["properties"]["vehicle_id"] == "scout1"
        assert "scout1" in store.health
        assert layer["simulation"] is False     # no demo data in this station
    finally:
        httpd.shutdown()


def test_a_dead_link_never_stops_capture(tmp_path):
    cfg = Config()
    pub = EdgePublisher(HttpTransport("http://127.0.0.1:9", timeout_s=0.2), "f1", "scout1")
    pipe = Pipeline(cfg, SimulatedCamera(resolution=(64, 48)), SimulatedTelemetry(),
                    Spool(tmp_path / "spool"), _CentreEngine(), publisher=pub)
    assert pipe.process_once() is not None
    assert pipe.stats.spooled == 1
    assert pub.stats.errors >= 1 and pub.stats.sent == 0


def test_only_located_detections_become_features():
    meta = {"sequence": 3, "captured_at": 1_758_700_000.0,
            "telemetry": {"lat": 50.0, "lon": -104.0},
            "detections": [{"label": "a", "confidence": 0.9, "lat": 50.0, "lon": -104.0},
                           {"label": "b", "confidence": 0.8, "geo_error": "no heading"}]}
    msg = detections_message(meta, "scout1")
    assert len(msg["detections"]["features"]) == 1
    assert msg["unplaced"] == 1
    assert msg["detections"]["features"][0]["geometry"]["coordinates"] == [-104.0, 50.0]


def test_publisher_is_off_unless_enabled():
    assert build_publisher(Config().publish) is None


def test_station_never_takes_the_edge_treatment_flag():
    store = OpsStore()
    ingest(store, "agriedge/farm/f1/vehicle/scout1/detections", {
        "detections": {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [-104.0, 50.0]},
            "properties": {"label": "kochia", "confidence": 0.9, "may_drive_treatment": True}}]},
    })
    row = store.detections[-1]
    assert row["may_drive_treatment"] is False
    assert row["edge_may_drive_treatment"] is True


# -- ground sensors -> station ----------------------------------------------------


def test_soil_and_weather_readings_are_stored_and_checked():
    store = OpsStore()
    ingest(store, "agriedge/farm/f1/zone/z1/soil", {
        "device_id": "soil-01", "battery_pct": 80, "rssi": -60,
        "depths": [{"depth_cm": 10, "moisture_pct": 22.5, "temp_c": 12.0},
                   {"depth_cm": 30, "moisture_pct": 140.0, "temp_c": 11.0}]})
    flags = {o.depth_cm: o.quality for o in store.soil}
    assert flags[10.0] == QualityFlag.GOOD
    assert flags[30.0] == QualityFlag.BAD, "an impossible reading is kept, and flagged"
    assert store.devices["soil-01"].battery_pct == 80

    ingest(store, "agriedge/farm/f1/zone/z1/weather",
           {"device_id": "wx-01", "air_temp_c": -1.5, "rh_pct": 90, "wind_ms": 1.2})
    assert store.weather[-1].air_temp.value_c == -1.5
    frost = [a for a in store.alerts.list_alerts() if a.severity == AlertSeverity.CRITICAL]
    assert frost, "a measured frost raises the frost alert"


def test_a_device_clock_in_the_future_is_not_trusted():
    store = OpsStore()
    future = (utcnow() + timedelta(days=400)).isoformat()
    out = ingest(store, "agriedge/farm/f1/zone/z1/weather",
                 {"device_id": "wx-01", "air_temp_c": 10.0, "ts": future})
    assert out["ts_trusted"] is False
    assert store.weather[-1].ts < future
    assert store.weather[-1].quality == QualityFlag.QUESTIONABLE


@pytest.mark.parametrize("topic,payload", [
    ("agriedge/farm/f1/zone/z1/irrigation/set", {"command": "on"}),
    ("agriedge/farm/f1/zone/z1/mavlink/arm", {}),
    ("agriedge/farm/f1/zone/z1/soil", {"moisture_pct": "wet"}),
    ("agriedge/farm/f1/zone/z1/soil", {"moisture_pct": float("nan")}),
    ("agriedge/farm/f1/zone/z1/soil", ["not", "an", "object"]),
    ("agriedge/farm/f1/vehicle/v1/detections", {"detections": {"features": [
        {"geometry": {"type": "Point", "coordinates": [500, 50]}}]}}),
])
def test_malformed_or_forbidden_messages_are_refused(topic, payload):
    with pytest.raises(IngestError):
        ingest(OpsStore(), topic, payload)


def test_http_ingest_batch_and_refusal(tmp_path):
    store, httpd, base = _serve(tmp_path)
    try:
        status, body = _post(base, "/api/ops/ingest", {"messages": [
            {"topic": "agriedge/farm/f1/zone/z1/soil", "payload": {"moisture_pct": 30}},
            {"topic": "agriedge/farm/f1/zone/z1/weather", "payload": {"air_temp_c": 18}},
        ]})
        assert status == 202 and body["accepted"] == 2
        status, _ = _post(base, "/api/ops/ingest",
                          {"topic": "agriedge/farm/f1/zone/z1/irrigation/set",
                           "payload": {"command": "on"}})
        assert status == 400
        sensors = _get(base, "/api/ops/sensors")
        assert any(r["metric"] == "soil_moisture" and not r["synthetic"]
                   for r in sensors["readings"])
    finally:
        httpd.shutdown()


def test_a_restart_keeps_what_was_ingested(tmp_path):
    db = str(tmp_path / "ops.sqlite")
    store = create_app_store(seed=False, sqlite_path=db)
    ingest(store, "agriedge/farm/f1/zone/z1/soil", {"device_id": "soil-01", "moisture_pct": 25})
    ingest(store, "agriedge/farm/f1/vehicle/scout1/detections", {
        "ts": "2026-09-20T12:00:00+00:00",
        "detections": {"type": "FeatureCollection", "features": [{
            "type": "Feature", "id": "1-0",
            "geometry": {"type": "Point", "coordinates": [-104.0, 50.0]},
            "properties": {"label": "kochia"}}]}})

    again = create_app_store(seed=False, sqlite_path=db)
    assert again.live_messages == 2
    assert again.soil[-1].moisture_pct == 25
    assert len(again.detections) == 1
    # Replaying twice does not duplicate anything.
    assert replay_ingest_log(OpsStore(sqlite_path=db)) == 2


def test_mqtt_handler_never_raises():
    store, lock = OpsStore(), threading.Lock()
    assert handle_message(store, lock, "agriedge/farm/f1/zone/z1/soil", b'{"moisture_pct": 20}')
    assert not handle_message(store, lock, "agriedge/farm/f1/zone/z1/soil", b"not json")
    assert not handle_message(store, lock, "some/other/topic", b"{}")


def test_seeded_demo_is_still_labelled_simulation(tmp_path):
    store = create_app_store(seed=True)
    assert store.simulation_mode is True
    assert np.isfinite(len(store.weather))
