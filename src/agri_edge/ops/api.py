"""Ops Station HTTP API (§121–125, live/overview/map screens).

Serves JSON endpoints + Release-1 HTML under /ops/.
Run: python -m agri_edge.ops.api
"""
from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import mimetypes
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from .store import get_store, reset_store, OpsStore
from .simulate import seed_demo
from .geo import demo_farm_geojson, TIME_RANGES, filter_by_time_range
from .derived import derive_from_weather, gdd_stub
from .irrigation import irrigation_dashboard, rule_based_irrigation
from .vra import make_demo_prescription, validate_prescription, feedback_map_stub, approve_prescription, list_cells
from .analytics import battery_analytics, energy_analytics, water_analytics, application_analytics, kpi_page
from .maintenance import check_calibration_due, default_schedules
from .gateway import OfflineGateway, TRANSPORT_NOTE
from .reports import daily_brief, report_summary, build_timeline
from .commands import confirm_command
from .odm import ODMPipelineStub
from .map3d import scene, vr_status
from .notifications import DashboardNotificationProvider, MultiplexNotificationProvider, LogNotificationProvider
from .alerts import InvalidTransition
from . import agronomy_service, auth, prescription_service, satellite_service
from .ingest import detections_geojson, ingest, replay_ingest_log
from .types import AlertState, utcnow, new_id

UI_DIR = Path(__file__).parent / "ui"
HOST = "127.0.0.1"
PORT = 8765
# Largest request body accepted. Every write here is a few hundred bytes of
# JSON; an unbounded Content-Length lets one request pin a thread and memory.
MAX_BODY_BYTES = 1_000_000
# When set, every POST must carry `Authorization: Bearer <token>`. This is a
# shared secret, not user accounts -- roles (types.Role) are still future work.
TOKEN_ENV = "OPS_API_TOKEN"

_gateway = OfflineGateway()
_odm = ODMPipelineStub()
_notify = MultiplexNotificationProvider([DashboardNotificationProvider(), LogNotificationProvider()])
_schedules = default_schedules()
_rx = make_demo_prescription()
# HTTP handler threads and the MQTT subscriber thread all write the store.
_ingest_lock = threading.Lock()


def _json(handler: BaseHTTPRequestHandler, code: int, payload: Any,
          headers: Optional[dict[str, str]] = None) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(code)
    for k, v in (headers or {}).items():
        handler.send_header(k, v)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    # No Access-Control-Allow-Origin. The UI is served from this same origin and
    # the web proxy calls from its server, so neither needs CORS -- and `*` let
    # any page the operator had open read every response.
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def _binary(handler: BaseHTTPRequestHandler, data: bytes, ctype: str, filename: str) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


class BadRequest(ValueError):
    """Client input that cannot be acted on. Answered 400, never 500."""


def _optional_float(value: Any, name: str) -> Optional[float]:
    """None/"" stays None (missing is not zero); anything else must be a number."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise BadRequest(f"{name} must be a number, got {value!r}") from None


def _write_refusal(handler: BaseHTTPRequestHandler, check_token: bool = True) -> Optional[tuple[int, str]]:
    """Why this POST must not run, or None if it may.

    Three checks, cheapest first:

    * A browser always sends Origin on a cross-site POST. If it names a host
      other than this one, a page the operator happened to have open is trying
      to use their network position -- refuse it.
    * The body must be declared JSON. A cross-site ``text/plain`` or form POST
      needs no CORS preflight, so it is exactly the request a hostile page can
      send; ``application/json`` forces a preflight, which this server never
      approves.
    * When OPS_API_TOKEN is set, the bearer token must match.
    """
    origin = handler.headers.get("Origin")
    if origin and origin != "null":
        origin_host = urlparse(origin).netloc
        if origin_host != (handler.headers.get("Host") or ""):
            return 403, "cross-origin write refused"
    elif origin == "null":
        return 403, "opaque-origin write refused"
    ctype = (handler.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if ctype != "application/json":
        return 415, "Content-Type must be application/json"
    token = os.environ.get(TOKEN_ENV)
    if token and check_token:
        supplied = handler.headers.get("Authorization") or ""
        if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            return 401, "missing or wrong bearer token"
    return None


def _banner(store: OpsStore) -> dict[str, Any]:
    return {"simulation": store.simulation_mode, "banner": "SIMULATION" if store.simulation_mode else None}


def build_routes(store: OpsStore) -> dict[str, Any]:
    """Route table used by handler and tests."""
    return {}  # populated dynamically in handler


class OpsHandler(BaseHTTPRequestHandler):
    principal: auth.Principal = auth.Principal("dev", "dev", "dev")

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter
        pass

    def _authorize(self, store: OpsStore, method: str, path: str) -> Optional[tuple[int, str]]:
        """Resolve the caller and check the route. None = go ahead.

        With no users configured the station is in its original open mode
        (loopback, optional OPS_API_TOKEN), and the caller is 'dev'."""
        if not auth.auth_enabled(store):
            self.principal = auth.Principal("dev", "dev", "dev")
            return None
        if path in auth.PUBLIC or path == "/api/ops/auth/me":
            self.principal = auth.principal_from(store, self.headers.get("Authorization"),
                                                 self.headers.get("Cookie")) or auth.Principal("", "", "anonymous")
            return None
        p = auth.principal_from(store, self.headers.get("Authorization"), self.headers.get("Cookie"))
        if p is None:
            return 401, "log in first"
        self.principal = p
        if not auth.may(p, method, path):
            return 403, f"{p.role} may not {method} {path}"
        return None

    def _actor(self, body: dict, key: str = "actor") -> str:
        """The logged-in user's name. The body's actor/by is only a fallback in
        open (no-users) mode -- it used to be the only source, so the audit log
        recorded whatever the client claimed."""
        if self.principal.kind == "user":
            return self.principal.name
        return str(body.get(key, "operator"))

    def do_OPTIONS(self) -> None:  # noqa: N802
        # Answer the preflight without granting it: no Allow-Origin, so a
        # browser refuses to send the cross-origin request that follows.
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        with get_store().lock:
            return self._do_get()

    def _do_get(self) -> None:
        store = get_store()
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        # Static UI
        if path == "/ops" or path.startswith("/ops/"):
            return self._serve_ui(path)

        denied = self._authorize(store, "GET", path)
        if denied is not None:
            return _json(self, denied[0], {"error": denied[1], "auth_required": True})

        try:
            if path == "/api/ops/auth/me":
                if self.principal.kind == "anonymous":
                    return _json(self, 401, {"error": "not logged in", "auth_enabled": True})
                return _json(self, 200, {"auth_enabled": auth.auth_enabled(store),
                                         **self.principal.to_dict()})
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
            if path == "/api/ops/detections":
                from .db import get_detection_db
                db = get_detection_db()
                rows = db.list(limit=200) if db is not None else list(getattr(store, "detections", []))
                return _json(self, 200, {**_banner(store), "detections": rows, "count": len(rows), "status": "IMPLEMENTED"})
            if path == "/api/ops/ingest":
                return _json(self, 200, {
                    **_banner(store),
                    "stats": dict(getattr(store, "ingest_stats", {}) or {}),
                    "recent_rejects": list(getattr(store, "ingest_rejects", []) or []),
                    "channel": "mqtt_subscribe_only",
                    "status": "SIMULATED",
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
            if path == "/api/ops/fields":
                return _json(self, 200, {**_banner(store), "fields": [
                    f.to_dict() for f in agronomy_service.list_fields(store)]})
            if path == "/api/ops/agronomy":
                fid = (qs.get("field") or [""])[0]
                if not fid:
                    raise BadRequest("field is required")
                try:
                    return _json(self, 200, {**_banner(store), **agronomy_service.assess(store, fid)})
                except KeyError:
                    return _json(self, 404, {"error": f"unknown field {fid}"})
            if path == "/api/ops/recommendations":
                recs = (agronomy_service.all_recommendations(store)
                        + satellite_service.scouting_recommendations(store))
                return _json(self, 200, {**_banner(store),
                                         "recommendations": sorted(recs, key=lambda r: r["priority"])})
            if path == "/api/ops/satellite":
                fid = (qs.get("field") or [""])[0]
                if not fid:
                    raise BadRequest("field is required")
                try:
                    return _json(self, 200, {**_banner(store), **satellite_service.summary(store, fid)})
                except KeyError:
                    return _json(self, 404, {"error": f"unknown field {fid}"})
                except ValueError as exc:
                    return _json(self, 400, {"error": str(exc)})
            if path == "/api/ops/prescriptions":
                return _json(self, 200, {**_banner(store), "prescriptions": prescription_service.listing(store)})
            if path.startswith("/api/ops/prescriptions/"):
                parts = path[len("/api/ops/prescriptions/"):].split("/")
                try:
                    rec = prescription_service.get(store, parts[0])
                except KeyError:
                    return _json(self, 404, {"error": f"unknown prescription {parts[0]}"})
                if len(parts) == 1:
                    g = rec["grid"]
                    return _json(self, 200, {**_banner(store), **g.summary(), "geojson": g.geojson()})
                if parts[1:] == ["export"]:
                    fmt = (qs.get("format") or ["isoxml"])[0]
                    from ..prescription.export import NotApproved

                    try:
                        data = prescription_service.export(store, parts[0], fmt)
                    except NotApproved as exc:
                        return _json(self, 409, {"error": str(exc)})
                    except ValueError as exc:
                        return _json(self, 400, {"error": str(exc)})
                    return _binary(self, data, "application/zip", f"{parts[0]}_{fmt}.zip")
                return _json(self, 404, {"error": "not found", "path": path})
            if path == "/api/ops/map/detections":
                return _json(self, 200, {**_banner(store), **detections_geojson(store)})
            if path == "/api/ops/map/layers":
                layers = [m.to_dict() for m in store.map_assets.values()]
                return _json(self, 200, {**_banner(store), "layers": layers, "time_ranges": list(TIME_RANGES)})
            if path == "/api/ops/map/time":
                tr = (qs.get("range") or ["now"])[0]
                assets = list(store.map_assets.values())
                filtered = filter_by_time_range(assets, tr)
                return _json(self, 200, {**_banner(store), "range": tr, "layers": [a.to_dict() for a in filtered]})
            if path == "/api/ops/devices/health":
                from .device_watch import check as check_devices

                return _json(self, 200, {**_banner(store),
                                         "health": [h.to_dict() for h in store.health.values()],
                                         "registered": check_devices(store)})
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
                # Absent means unknown, not 0 m/s -- the old default of "0"
                # invented a calm day and validated against it.
                wind_q = qs.get("wind_ms")
                wind = _optional_float(wind_q[0] if wind_q else None, "wind_ms")
                return _json(self, 200, {**_banner(store), **validate_prescription(_rx, wind_ms=wind)})
            if path == "/api/ops/vra/feedback":
                return _json(self, 200, {**_banner(store), **feedback_map_stub(_rx.prescription_id)})
            if path == "/api/ops/kpi":
                return _json(self, 200, kpi_page(store))
            if path == "/api/ops/analytics/battery":
                return _json(self, 200, {**_banner(store), **battery_analytics(store)})
            if path == "/api/ops/analytics/energy":
                return _json(self, 200, {**_banner(store), **energy_analytics(store)})
            if path == "/api/ops/analytics/water":
                return _json(self, 200, {**_banner(store), **water_analytics(store)})
            if path == "/api/ops/analytics/application":
                return _json(self, 200, {**_banner(store), **application_analytics(store)})
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
                return _json(self, 200, {**_banner(store), **scene(store=store)})
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
                        {"id": "3d", "path": "/api/ops/3d", "release": 5, "stub": False, "path_ui": "/ops/map3d.html"},
                    ],
                })
            
            if path == "/api/ops/vra/cells":
                return _json(self, 200, {**_banner(store), **list_cells(_rx)})
            if path == "/api/ops/vr/status":
                return _json(self, 200, {**_banner(store), **vr_status()})
            if path == "/api/ops/cameras":
                return _json(self, 200, {**_banner(store), "items": [c.to_dict() for c in store.cameras]})
            if path == "/api/ops/scouts":
                return _json(self, 200, {**_banner(store), "items": [c.to_dict() for c in store.scouts]})
            if path == "/api/ops/manual":
                return _json(self, 200, {**_banner(store), "items": [c.to_dict() for c in store.manual]})
            if path == "/api/ops/notes":
                return _json(self, 200, {**_banner(store), "items": [c.to_dict() for c in store.notes]})
            if path == "/api/ops/mapfield":
                return _json(self, 200, {**_banner(store), "workflows": [w.to_dict() for w in _odm.workflows.values()]})
            return _json(self, 404, {"error": "not found", "path": path})
        except BadRequest as exc:
            return _json(self, 400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return _json(self, 500, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        store = get_store()
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        refusal = _write_refusal(self, check_token=not auth.auth_enabled(store))
        if refusal is not None:
            return _json(self, refusal[0], {"error": refusal[1]})
        denied = self._authorize(store, "POST", path)
        if denied is not None:
            return _json(self, denied[0], {"error": denied[1], "auth_required": True})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return _json(self, 400, {"error": "invalid Content-Length"})
        if length < 0:
            return _json(self, 400, {"error": "invalid Content-Length"})
        if length > MAX_BODY_BYTES:
            # The unread body is still on the socket; do not reuse it.
            self.close_connection = True
            return _json(self, 413, {"error": f"body exceeds {MAX_BODY_BYTES} bytes"})
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _json(self, 400, {"error": "invalid json"})
        if not isinstance(body, dict):
            return _json(self, 400, {"error": "body must be a JSON object"})

        try:
            if path == "/api/ops/auth/login":
                try:
                    res = auth.login(store, str(body.get("username", "")), str(body.get("password", "")))
                except PermissionError as exc:
                    return _json(self, 429, {"error": str(exc)})
                if res is None:
                    return _json(self, 401, {"error": "wrong username or password"})
                token, exp, user = res
                secure = "; Secure" if os.environ.get("AGRIEDGE_COOKIE_SECURE") == "1" else ""
                store.add_audit(user["username"], "login", user["username"], role=user["role"])
                return _json(self, 200, {"token": token, "expires": exp, "user": user}, headers={
                    "Set-Cookie": f"ae_session={token}; HttpOnly; SameSite=Strict; Path=/; "
                                  f"Max-Age={auth.SESSION_S}{secure}"})
            if path == "/api/ops/auth/logout":
                return _json(self, 200, {"ok": True}, headers={
                    "Set-Cookie": "ae_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
            if path == "/api/ops/auth/users":
                user = auth.add_user(store, str(body.get("username", "")), str(body.get("password", "")),
                                     str(body.get("role", "viewer")), body.get("display_name"))
                store.add_audit(self._actor(body), "user_upsert", user["username"], user["role"])
                return _json(self, 201, {"user": user})
            if path == "/api/ops/fields":
                prof = agronomy_service.upsert_field(store, body)
                store.add_audit(self._actor(body, "actor"), "field_upsert", prof.field_id)
                return _json(self, 200, {"field": prof.to_dict()})
            if path == "/api/ops/prescriptions":
                return _json(self, 201, prescription_service.build(store, body))
            if path.startswith("/api/ops/prescriptions/") and path.endswith("/approve"):
                rx_id = path[len("/api/ops/prescriptions/"):-len("/approve")]
                wind = _optional_float(body.get("wind_ms"), "wind_ms")
                return _json(self, 200, prescription_service.approve_rx(
                    store, rx_id, self._actor(body, "actor"), wind))
            if path == "/api/ops/satellite/refresh":
                fid = str(body.get("field_id") or "")
                try:
                    started = satellite_service.refresh(store, fid)
                except KeyError:
                    return _json(self, 404, {"error": f"unknown field {fid}"})
                return _json(self, 202, {"started": started, **satellite_service.status(fid)})
            if path == "/api/ops/ingest":
                # One message {topic, payload} or a batch {messages: [...]}. The
                # same function the MQTT subscriber calls (ops/ingest.py).
                msgs = body.get("messages") if "messages" in body else [body]
                if not isinstance(msgs, list) or not msgs or len(msgs) > 500:
                    raise BadRequest("messages must be a list of 1-500 {topic, payload}")
                results = []
                with _ingest_lock:
                    for m in msgs:
                        if not isinstance(m, dict) or "topic" not in m:
                            raise BadRequest("each message needs a topic and a payload")
                        results.append(ingest(store, str(m["topic"]), m.get("payload")))
                return _json(self, 202, {"accepted": len(results), "results": results})
            if path == "/api/ops/detections":
                row = dict(body)
                row.setdefault("detection_id", body.get("detection_id") or body.get("id") or f"det_{len(getattr(store, 'detections', []))+1:05d}")
                row.setdefault("ts", body.get("ts") or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z"))
                row.setdefault("label", body.get("label", "unknown"))
                row.setdefault("confidence", float(body.get("confidence", 0.0)))
                row.setdefault("bbox", body.get("bbox", [0, 0, 0, 0]))
                # The treatment gate is computed on the edge from the model's
                # own validation record and the treatment geofence. A caller of
                # this endpoint cannot grant it: `setdefault` used to keep a
                # client-sent `may_drive_treatment: true`. What the client
                # claimed is kept, under a name nothing downstream trusts.
                for flag in ("validated_locally", "may_drive_treatment"):
                    if flag in row:
                        row[f"claimed_{flag}"] = bool(row.pop(flag))
                    row[flag] = False
                row.setdefault("synthetic", True)
                store.persist_detection(row)
                return _json(self, 201, {**_banner(store), "detection": row, "status": "IMPLEMENTED"})
            if path == "/api/ops/seed":
                reset_store()
                store = get_store()
                result = seed_demo(store)
                return _json(self, 200, result)
            if path == "/api/ops/alerts/ack":
                a = store.alerts.ack(body["alert_id"], self._actor(body, "by"))
                _notify.send(a)
                store.add_audit(self._actor(body, "by"), "ack", a.alert_id)
                return _json(self, 200, a.to_dict())
            if path == "/api/ops/alerts/resolve":
                a = store.alerts.resolve(body["alert_id"], self._actor(body, "by"))
                store.add_audit(self._actor(body, "by"), "resolve", a.alert_id)
                return _json(self, 200, a.to_dict())
            if path == "/api/ops/alerts/escalate":
                a = store.alerts.escalate(body["alert_id"], self._actor(body, "by"))
                _notify.send(a)
                store.add_audit(self._actor(body, "by"), "escalate", a.alert_id)
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
                    actor=self._actor(body, "actor"),
                ).to_dict())
            if path == "/api/ops/odm/submit":
                # Pass the store, or the finished orthomosaic is never registered
                # as a map layer (it was not, until 24 Sept 2026).
                job = _odm.submit(body.get("field_id", "field_north"), store=store)
                return _json(self, 202, job.to_dict())
            if path == "/api/ops/irrigation/recommend":
                rec = rule_based_irrigation(
                    moisture_pct=body.get("moisture_pct"),
                    zone_id=body.get("zone_id", "zone_a"),
                    frost_level=body.get("frost_level", "none"),
                )
                return _json(self, 200, rec.to_dict())

            # These nine routes lived inside do_GET until 19 Sept 2026, where
            # `body` does not exist. GET returned 500 NameError and POST
            # returned 404, so the prescription-approval endpoint -- the
            # human-in-the-loop gate the spec requires before any variable-rate
            # application -- could not be called at all, and neither could the
            # mapping workflow or the manual-observation ingestion.
            #
            # Found by ruff F821 (undefined-name), which is why `make lint`
            # silently exiting 0 when ruff was absent mattered.
            if path == "/api/ops/vra/approve":
                wind = _optional_float(body.get("wind_ms"), "wind_ms")
                result = approve_prescription(_rx, actor=self._actor(body, "actor"), wind_ms=wind)
                store.add_audit(self._actor(body, "actor"), "vra_approve", _rx.prescription_id, str(result.get("approved")))
                return _json(self, 200, {**_banner(store), **result, "prescription": _rx.to_dict()})
            if path == "/api/ops/mapfield/create":
                wf = _odm.create_workflow(body.get("field_id", "field_north"), sensor=body.get("sensor", "rgb"), gsd_cm=float(body.get("gsd_cm", 2.5)))
                return _json(self, 201, {**_banner(store), "workflow": wf.to_dict()})
            if path == "/api/ops/mapfield/validate":
                return _json(self, 200, {**_banner(store), **_odm.validate_workflow(body["workflow_id"])})
            if path == "/api/ops/mapfield/approve":
                return _json(self, 200, {**_banner(store), **_odm.approve_workflow(body["workflow_id"], actor=self._actor(body, "actor"))})
            if path == "/api/ops/mapfield/execute":
                return _json(self, 202, {**_banner(store), **_odm.execute_workflow(body["workflow_id"], store=store)})
            if path == "/api/ops/cameras":
                from .schema import CameraEvent
                ev = CameraEvent(event_id=new_id("cam_"), camera_id=body.get("camera_id", "cam1"), ts=utcnow().isoformat(), label=body.get("label", "note"), confidence=float(body.get("confidence", 0.5)), image_path=body.get("image_path"), synthetic=True)
                store.cameras.append(ev)
                return _json(self, 201, ev.to_dict())
            if path == "/api/ops/scouts":
                from .schema import ScoutReport
                report = ScoutReport(report_id=new_id("sc_"), ts=utcnow().isoformat(), scout_id=body.get("scout_id", "scout"), notes=body.get("notes", ""), zone_id=body.get("zone_id"), synthetic=True)
                store.scouts.append(report)
                return _json(self, 201, report.to_dict())
            if path == "/api/ops/manual":
                from .schema import ManualObservation
                obs = ManualObservation(obs_id=new_id("mo_"), ts=utcnow().isoformat(), observer=body.get("observer", "operator"), text=body.get("text", ""), category=body.get("category", "general"), lat=body.get("lat"), lon=body.get("lon"), synthetic=True)
                store.manual.append(obs)
                return _json(self, 201, obs.to_dict())
            if path == "/api/ops/notes":
                from .schema import MobileNote
                note = MobileNote(note_id=new_id("mn_"), ts=utcnow().isoformat(), author=body.get("author", "operator"), text=body.get("text", ""), lat=body.get("lat"), lon=body.get("lon"), synthetic=True)
                store.notes.append(note)
                return _json(self, 201, note.to_dict())

            return _json(self, 404, {"error": "not found", "path": path})
        except InvalidTransition as exc:
            return _json(self, 409, {"error": str(exc)})
        except KeyError as exc:
            # A required field missing from the body is the client's error; it
            # was reported as 404, which reads as "no such route".
            return _json(self, 400, {"error": f"missing or unknown: {exc}"})
        except (BadRequest, ValueError, TypeError) as exc:
            return _json(self, 400, {"error": str(exc)})
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


def create_app_store(seed: bool = True, sqlite_path: Optional[str] = None) -> OpsStore:
    store = reset_store(sqlite_path=sqlite_path)
    if seed:
        seed_demo(store)
    else:
        # No demo data: whatever the station shows came through ops/ingest.py.
        store.simulation_mode = False
    replay_ingest_log(store)
    return store


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve(host: str = HOST, port: int = PORT, seed: bool = True,
          db: Optional[str] = None) -> None:
    if not _is_loopback(host) and not os.environ.get(TOKEN_ENV):
        raise SystemExit(
            f"Refusing to serve the Ops API on {host} without {TOKEN_ENV} set: "
            "every write, including prescription approval, would be open to "
            "anything on the network."
        )
    store = create_app_store(seed=seed, sqlite_path=db)
    from .mqtt_ingest import start_subscriber

    start_subscriber(store, _ingest_lock)
    httpd = ThreadingHTTPServer((host, port), OpsHandler)
    mode = "SIMULATION (seeded demo data)" if seed else "LIVE (ingested data only)"
    print(f"Ops Station API at http://{host}:{port}/ -- {mode}")
    if db:
        print(f"Persisting to {db}; replayed {store.live_messages} messages.")
    print(f"UI: http://{host}:{port}/ops/")
    httpd.serve_forever()


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m agri_edge.ops.api")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--db", help="SQLite file for durable ingest (replayed on start)")
    ap.add_argument("--no-seed", action="store_true",
                    help="start empty and show only ingested data (not the demo)")
    args = ap.parse_args(argv)
    serve(host=args.host, port=args.port, seed=not args.no_seed, db=args.db)


if __name__ == "__main__":
    main()
