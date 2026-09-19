"""Ops Station HTTP API (§121–125, live/overview/map screens).

Serves JSON endpoints + Release-1 HTML under /ops/.
Run: python -m agri_edge.ops.api
"""
from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from .store import get_store, reset_store, OpsStore
from .simulate import seed_demo
from .geo import demo_farm_geojson, TIME_RANGES, filter_by_time_range
from .derived import derive_from_weather, gdd_stub
from .irrigation import irrigation_dashboard, rule_based_irrigation
from .vra import make_demo_prescription, validate_prescription, feedback_map_stub
from .analytics import battery_analytics, energy_analytics_stub, water_analytics, application_analytics_stub, kpi_page
from .maintenance import check_calibration_due, default_schedules
from .gateway import OfflineGateway, TRANSPORT_NOTE
from .reports import daily_brief, report_summary, build_timeline
from .commands import confirm_command
from .odm import ODMPipelineStub
from .map3d import scene_stub
from .notifications import DashboardNotificationProvider, MultiplexNotificationProvider, LogNotificationProvider
from .types import AlertState, DataOrigin, utcnow

UI_DIR = Path(__file__).parent / "ui"
HOST = "127.0.0.1"
PORT = 8765

_gateway = OfflineGateway()
_odm = ODMPipelineStub()
_notify = MultiplexNotificationProvider([DashboardNotificationProvider(), LogNotificationProvider()])
_schedules = default_schedules()
_rx = make_demo_prescription()


def _json(handler: BaseHTTPRequestHandler, code: int, payload: Any) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _banner(store: OpsStore) -> dict[str, Any]:
    return {"simulation": store.simulation_mode, "banner": "SIMULATION" if store.simulation_mode else None}


def build_routes(store: OpsStore) -> dict[str, Any]:
    """Route table used by handler and tests."""
    return {}  # populated dynamically in handler


class OpsHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # quieter
        pass

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        store = get_store()
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        # Static UI
        if path == "/ops" or path.startswith("/ops/"):
            return self._serve_ui(path)

        try:
            if path in ("/", "/api/ops/overview"):
                return _json(self, 200, {**_banner(store), **store.overview()})
            if path == "/api/ops/live":
                return _json(self, 200, {
                    **_banner(store),
                    "devices": [d.to_dict() for d in store.devices.values()],
                    "health": [h.to_dict() for h in store.health.values()],
                    "latest_weather": store.weather[-1].to_dict() if store.weather else None,
                    "open_alerts": [a.to_dict() for a in store.alerts.list_alerts() if a.state != AlertState.RESOLVED],
                    "ts": utcnow().isoformat(),
                })
            if path == "/api/ops/weather":
                return _json(self, 200, {
                    **_banner(store),
                    "observations": [w.to_dict() for w in store.weather],
                    "aggregates": [a.to_dict() for a in store.weather_aggs],
                    "note": "Raw observations stored separately from aggregates",
                })
            if path == "/api/ops/weather/derived":
                if not store.weather or not store.weather[-1].air_temp:
                    return _json(self, 404, {"error": "no weather"})
                w = store.weather[-1]
                return _json(self, 200, {
                    **_banner(store),
                    **derive_from_weather(w.air_temp.value_c, w.rh_pct or 50.0),
                    "gdd_stub": gdd_stub(
                        (store.weather_aggs[-1].air_temp_min_c or 10) if store.weather_aggs else 10,
                        (store.weather_aggs[-1].air_temp_max_c or 20) if store.weather_aggs else 20,
                    ),
                })
            if path == "/api/ops/sensors":
                return _json(self, 200, {
                    **_banner(store),
                    "soil": [s.to_dict() for s in store.soil],
                    "readings": [r.to_dict() for r in store.sensor_readings],
                    "devices": [d.to_dict() for d in store.devices.values()],
                })
            if path == "/api/ops/alerts":
                return _json(self, 200, {
                    **_banner(store),
                    "alerts": [a.to_dict() for a in store.alerts.list_alerts()],
                })
            if path == "/api/ops/map" or path == "/api/ops/map/geojson":
                return _json(self, 200, {**_banner(store), **demo_farm_geojson()})
            if path == "/api/ops/map/layers":
                layers = [m.to_dict() for m in store.map_assets.values()]
                return _json(self, 200, {**_banner(store), "layers": layers, "time_ranges": list(TIME_RANGES)})
            if path == "/api/ops/map/time":
                tr = (qs.get("range") or ["now"])[0]
                assets = list(store.map_assets.values())
                filtered = filter_by_time_range(assets, tr)
                return _json(self, 200, {**_banner(store), "range": tr, "layers": [a.to_dict() for a in filtered]})
            if path == "/api/ops/devices/health":
                return _json(self, 200, {**_banner(store), "health": [h.to_dict() for h in store.health.values()]})
            if path == "/api/ops/water":
                return _json(self, 200, {
                    **_banner(store),
                    "sources": [x.to_dict() for x in store.water_sources.values()],
                    "tanks": [x.to_dict() for x in store.tanks.values()],
                    "pumps": [x.to_dict() for x in store.pumps.values()],
                    "valves": [x.to_dict() for x in store.valves.values()],
                    "flow_meters": [x.to_dict() for x in store.flow_meters.values()],
                    "readings": [x.to_dict() for x in store.water_readings],
                    "usage": [x.to_dict() for x in store.water_usage],
                })
            if path == "/api/ops/irrigation":
                return _json(self, 200, irrigation_dashboard(store))
            if path == "/api/ops/vra":
                return _json(self, 200, {**_banner(store), "prescription": _rx.to_dict()})
            if path == "/api/ops/vra/validate":
                wind = float((qs.get("wind_ms") or ["0"])[0])
                return _json(self, 200, {**_banner(store), **validate_prescription(_rx, wind_ms=wind)})
            if path == "/api/ops/vra/feedback":
                return _json(self, 200, {**_banner(store), **feedback_map_stub(_rx.prescription_id)})
            if path == "/api/ops/kpi":
                return _json(self, 200, kpi_page(store))
            if path == "/api/ops/analytics/battery":
                return _json(self, 200, {**_banner(store), **battery_analytics(store)})
            if path == "/api/ops/analytics/energy":
                return _json(self, 200, {**_banner(store), **energy_analytics_stub(store)})
            if path == "/api/ops/analytics/water":
                return _json(self, 200, {**_banner(store), **water_analytics(store)})
            if path == "/api/ops/analytics/application":
                return _json(self, 200, {**_banner(store), **application_analytics_stub(store)})
            if path == "/api/ops/maintenance":
                due = check_calibration_due(store.calibrations, store.alerts)
                return _json(self, 200, {
                    **_banner(store),
                    "schedules": [s.to_dict() for s in _schedules],
                    "calibrations": [c.to_dict() for c in store.calibrations],
                    "due": due,
                })
            if path == "/api/ops/gateway":
                return _json(self, 200, {**_banner(store), **_gateway.status(), "transport_note": TRANSPORT_NOTE})
            if path == "/api/ops/retention":
                return _json(self, 200, {**_banner(store), "policy": store.retention.to_dict()})
            if path == "/api/ops/rtk":
                return _json(self, 200, {**_banner(store), "stations": [r.to_dict() for r in store.rtk.values()]})
            if path == "/api/ops/service-stations":
                return _json(self, 200, {
                    **_banner(store),
                    "stations": [s.to_dict() for s in store.service_stations.values()],
                    "note": "No physical dock servicing automation",
                })
            if path == "/api/ops/greenhouse":
                return _json(self, 200, {
                    **_banner(store),
                    "zones": [g.to_dict() for g in store.greenhouse.values()],
                    "actuators_automated": False,
                })
            if path == "/api/ops/pest":
                return _json(self, 200, {**_banner(store), "observations": [p.to_dict() for p in store.pests]})
            if path == "/api/ops/tasks":
                return _json(self, 200, {**_banner(store), "tasks": [t.to_dict() for t in store.tasks.values()]})
            if path == "/api/ops/timeline":
                return _json(self, 200, {**_banner(store), "events": build_timeline(store)})
            if path == "/api/ops/brief":
                return _json(self, 200, daily_brief(store))
            if path == "/api/ops/report":
                return _json(self, 200, report_summary(store))
            if path == "/api/ops/audit":
                return _json(self, 200, {**_banner(store), "entries": [e.to_dict() for e in store.audit]})
            if path == "/api/ops/frost":
                from .derived import frost_risk
                t = store.weather[-1].air_temp.value_c if store.weather and store.weather[-1].air_temp else 5.0
                return _json(self, 200, {**_banner(store), **frost_risk(t)})
            if path == "/api/ops/heat":
                from .derived import heat_stress
                w = store.weather[-1] if store.weather else None
                t = w.air_temp.value_c if w and w.air_temp else 20.0
                return _json(self, 200, {**_banner(store), **heat_stress(t, w.rh_pct if w else None)})
            if path == "/api/ops/odm":
                return _json(self, 200, {**_banner(store), "jobs": [j.to_dict() for j in _odm.jobs.values()]})
            if path == "/api/ops/3d":
                return _json(self, 200, {**_banner(store), **scene_stub()})
            if path == "/api/ops/mqtt/topics":
                # §124 topic catalogue (ground only)
                return _json(self, 200, {
                    **_banner(store),
                    "topics": [
                        "agriedge/farm/{farm}/zone/{zone}/soil",
                        "agriedge/farm/{farm}/zone/{zone}/weather",
                        "agriedge/farm/{farm}/zone/{zone}/status",
                        "agriedge/farm/{farm}/zone/{zone}/irrigation/set",
                        "agriedge/farm/{farm}/zone/{zone}/irrigation/status",
                    ],
                    "forbidden": ["mavlink", "arm", "mission", "aircraft"],
                    "note": "Irrigation = ground MQTT only; companion MAVLink read-only",
                })
            if path == "/api/ops/nav":
                return _json(self, 200, {
                    **_banner(store),
                    "pages": [
                        {"id": "overview", "path": "/ops/", "release": 1},
                        {"id": "map", "path": "/ops/map.html", "release": 1},
                        {"id": "live", "path": "/ops/live.html", "release": 1},
                        {"id": "weather", "path": "/ops/weather.html", "release": 1},
                        {"id": "sensors", "path": "/ops/sensors.html", "release": 1},
                        {"id": "alerts", "path": "/ops/alerts.html", "release": 1},
                        {"id": "irrigation", "path": "/ops/irrigation.html", "release": 2},
                        {"id": "vra", "path": "/api/ops/vra", "release": 3},
                        {"id": "kpi", "path": "/api/ops/kpi", "release": 4},
                        {"id": "3d", "path": "/api/ops/3d", "release": 5, "stub": True},
                    ],
                })
            return _json(self, 404, {"error": "not found", "path": path})
        except Exception as exc:  # noqa: BLE001
            return _json(self, 500, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        store = get_store()
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return _json(self, 400, {"error": "invalid json"})

        try:
            if path == "/api/ops/seed":
                reset_store()
                store = get_store()
                result = seed_demo(store)
                return _json(self, 200, result)
            if path == "/api/ops/alerts/ack":
                a = store.alerts.ack(body["alert_id"], body.get("by", "operator"))
                _notify.send(a)
                store.add_audit(body.get("by", "operator"), "ack", a.alert_id)
                return _json(self, 200, a.to_dict())
            if path == "/api/ops/alerts/resolve":
                a = store.alerts.resolve(body["alert_id"], body.get("by", "operator"))
                store.add_audit(body.get("by", "operator"), "resolve", a.alert_id)
                return _json(self, 200, a.to_dict())
            if path == "/api/ops/alerts/escalate":
                a = store.alerts.escalate(body["alert_id"], body.get("by", "operator"))
                _notify.send(a)
                store.add_audit(body.get("by", "operator"), "escalate", a.alert_id)
                return _json(self, 200, a.to_dict())
            if path == "/api/ops/map/layers/toggle":
                asset_id = body["asset_id"]
                enabled = bool(body.get("enabled", True))
                asset = store.map_assets[asset_id]
                asset.enabled = enabled
                return _json(self, 200, asset.to_dict())
            if path == "/api/ops/gateway/enqueue":
                msg = _gateway.enqueue(body.get("topic", "test"), body.get("payload", {}), idempotency_key=body.get("idempotency_key"))
                return _json(self, 200, msg.to_dict())
            if path == "/api/ops/gateway/sync":
                return _json(self, 200, _gateway.sync())
            if path == "/api/ops/command/confirm":
                return _json(self, 200, confirm_command(
                    body.get("command", ""),
                    human_confirmed=bool(body.get("human_confirmed")),
                    actor=body.get("actor", "operator"),
                ).to_dict())
            if path == "/api/ops/odm/submit":
                job = _odm.submit(body.get("field_id", "field_north"))
                return _json(self, 202, job.to_dict())
            if path == "/api/ops/irrigation/recommend":
                rec = rule_based_irrigation(
                    moisture_pct=body.get("moisture_pct"),
                    zone_id=body.get("zone_id", "zone_a"),
                    frost_level=body.get("frost_level", "none"),
                )
                return _json(self, 200, rec.to_dict())
            return _json(self, 404, {"error": "not found", "path": path})
        except KeyError as exc:
            return _json(self, 404, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return _json(self, 500, {"error": str(exc)})

    def _serve_ui(self, path: str) -> None:
        rel = path[len("/ops"):].lstrip("/") or "index.html"
        if ".." in rel:
            return _json(self, 400, {"error": "bad path"})
        fp = UI_DIR / rel
        if not fp.exists() or not fp.is_file():
            # fallback index
            fp = UI_DIR / "index.html"
        if not fp.exists():
            return _json(self, 404, {"error": "ui missing"})
        data = fp.read_bytes()
        ctype = mimetypes.guess_type(str(fp))[0] or "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_app_store(seed: bool = True) -> OpsStore:
    store = reset_store()
    if seed:
        seed_demo(store)
    return store


def serve(host: str = HOST, port: int = PORT, seed: bool = True) -> None:
    create_app_store(seed=seed)
    httpd = ThreadingHTTPServer((host, port), OpsHandler)
    print(f"Ops Station SIMULATION API at http://{host}:{port}/")
    print(f"UI: http://{host}:{port}/ops/")
    httpd.serve_forever()


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
