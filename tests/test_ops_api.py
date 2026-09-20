"""API handler smoke tests without binding a port."""
from __future__ import annotations

import json
from io import BytesIO

from agri_edge.ops.api import OpsHandler, create_app_store
from agri_edge.ops.analytics import kpi_page
from agri_edge.ops.maintenance import check_calibration_due, default_schedules
from agri_edge.ops.notifications import DashboardNotificationProvider
from agri_edge.ops.odm import ODMPipelineStub
from agri_edge.ops.reports import daily_brief
from agri_edge.ops.map3d import scene_stub


class _W:
    def __init__(self):
        self.buf = BytesIO()
    def write(self, b):
        self.buf.write(b)


def _request(method: str, path: str, body: dict | None = None):
    create_app_store(seed=True)
    raw = json.dumps(body or {}).encode()
    handler = OpsHandler.__new__(OpsHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(raw)) if method == "POST" else "0"}
    handler.rfile = BytesIO(raw)
    handler.wfile = _W()
    handler.command = method
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 0)
    handler.raw_requestline = handler.requestline.encode()
    # minimal BaseHTTPRequestHandler state
    responses = []

    def send_response(code, message=None):
        responses.append(code)
    def send_header(k, v):
        pass
    def end_headers():
        pass
    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers
    if method == "GET":
        handler.do_GET()
    else:
        handler.do_POST()
    data = handler.wfile.buf.getvalue()
    return responses[0], json.loads(data.decode())


def test_overview_api():
    code, data = _request("GET", "/api/ops/overview")
    assert code == 200
    assert data["banner"] == "SIMULATION"
    assert data["device_count"] >= 1


def test_map_weather_sensors_alerts_live():
    for path in (
        "/api/ops/map/geojson",
        "/api/ops/weather",
        "/api/ops/sensors",
        "/api/ops/alerts",
        "/api/ops/live",
        "/api/ops/kpi",
        "/api/ops/irrigation",
        "/api/ops/mqtt/topics",
        "/api/ops/nav",
        "/api/ops/3d",
    ):
        code, data = _request("GET", path)
        assert code == 200, path
        assert data.get("banner") == "SIMULATION" or data.get("simulation") is True or data.get("stub") is True


def test_kpi_no_fake_health_score():
    from agri_edge.ops.store import get_store
    create_app_store(seed=True)
    kpi = kpi_page(get_store())
    assert kpi["health_score"] is None
    assert all("formula" in k for k in kpi["kpis"])


def test_notifications_and_maintenance():
    from agri_edge.ops.store import get_store
    create_app_store(seed=True)
    store = get_store()
    dash = DashboardNotificationProvider()
    alerts = store.alerts.list_alerts()
    if alerts:
        r = dash.send(alerts[0])
        assert r.ok
    due = check_calibration_due(store.calibrations, store.alerts)
    assert isinstance(due, list)
    assert default_schedules()


def test_odm_async_stub():
    pipe = ODMPipelineStub()
    job = pipe.submit("field_north")
    assert job.status in ("queued", "running", "done")
    assert job.synthetic is True


def test_daily_brief_factual():
    from agri_edge.ops.store import get_store
    create_app_store(seed=True)
    brief = daily_brief(get_store())
    assert "facts" in brief
    assert brief["banner"] == "SIMULATION"


def test_3d_stub():
    s = scene_stub()
    assert s["stub"] is False
    assert s.get("cesium_ready") is True or "terrain" in s
    assert s["vr_supported"] is False


def test_alert_ack_post():
    from agri_edge.ops.store import get_store
    create_app_store(seed=True)
    store = get_store()
    alerts = store.alerts.list_alerts()
    assert alerts
    a = store.alerts.ack(alerts[0].alert_id, "tester")
    assert a.state.value == "ACKNOWLEDGED"
