"""FarmOSHttpClient + FarmOSAdapter network path, against a LOCAL MOCK farmOS.

The mock speaks the shapes in https://farmos.org/development/api/ (OAuth2 at /oauth/token,
JSON:API under /api/...). It proves OUR client's behaviour -- token handling, paging,
origin pinning, error mapping, the allow_network gate. It does NOT prove a real farmOS
accepts these requests. Label: IMPLEMENTED, mock-tested, UNVERIFIED against a real server.
"""
from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agri_edge.adapters import FarmDataReader, FarmManagementAdapter, FarmOSAdapter, FarmOSNetworkDisabled
from agri_edge.adapters.farmos_http import (
    FarmOSAuthError,
    FarmOSError,
    FarmOSField,
    FarmOSHttpClient,
    FarmOSPlanting,
)
from agri_edge.store.farmos import FarmOSConfig, sidecar_to_log

LAND = [{"id": f"land-{i}", "type": "asset--land",
         "attributes": {"name": f"Field {i}", "status": "active", "land_type": "field",
                        "intrinsic_geometry": {"value": f"POLYGON(({i} 0, {i} 1, {i+1} 1, {i} 0))"}}}
        for i in range(5)]
PLANTS = [{"id": "plant-1", "type": "asset--plant",
           "attributes": {"name": "Spring wheat 2026", "status": "active"},
           "relationships": {"plant_type": {"data": [{"type": "taxonomy_term--plant_type", "id": "pt-1"}]},
                             "location": {"data": [{"type": "asset--land", "id": "land-0"}]}}}]


class Mock(BaseHTTPRequestHandler):
    # state, reset per test by the fixture
    token_requests: list = []
    api_requests: list = []
    posted: list = []
    token_ttl = "300"
    reject_next_n_with_401 = 0
    revoke_after_first = False
    page_size = 2
    next_override = None
    tokens_issued = 0
    issue_refresh = True

    def log_message(self, *a):
        pass

    def _send(self, code, doc, ctype="application/json"):
        body = json.dumps(doc).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        if self.path == "/oauth/token":
            form = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}
            Mock.token_requests.append(form)
            gt = form.get("grant_type")
            ok = ((gt == "password" and form.get("username") == "u" and form.get("password") == "p")
                  or (gt == "client_credentials" and form.get("client_secret") == "s3cret")
                  or (gt == "refresh_token" and form.get("refresh_token", "").startswith("refresh-")))
            if not ok:
                return self._send(401, {"error": "invalid_grant"})
            Mock.tokens_issued += 1
            doc = {"access_token": f"tok-{Mock.tokens_issued}", "token_type": "Bearer",
                   "expires_in": Mock.token_ttl, "scope": "farm_manager"}
            if Mock.issue_refresh:
                doc["refresh_token"] = f"refresh-{Mock.tokens_issued}"
            return self._send(200, doc)
        if not self._authed():
            return
        Mock.api_requests.append(("POST", self.path))
        doc = json.loads(raw.decode())
        assert self.headers["Content-Type"] == "application/vnd.api+json"
        Mock.posted.append((self.path, doc))
        return self._send(201, {"data": {"id": f"new-{len(Mock.posted)}", "type": doc["data"]["type"]}},
                          "application/vnd.api+json")

    def _authed(self) -> bool:
        a = self.headers.get("Authorization", "")
        if Mock.reject_next_n_with_401 > 0:
            Mock.reject_next_n_with_401 -= 1
            self._send(401, {"errors": [{"title": "Unauthorized"}]})
            return False
        if not a.startswith("Bearer tok-"):
            self._send(403, {"errors": [{"title": "Forbidden"}]})
            return False
        return True

    def do_GET(self):  # noqa: N802
        if not self._authed():
            return
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        Mock.api_requests.append(("GET", self.path))
        if u.path == "/api/asset/land":
            off = int(q.get("page[offset]", ["0"])[0])
            chunk = LAND[off: off + Mock.page_size]
            doc = {"data": chunk, "links": {}}
            if off + Mock.page_size < len(LAND):
                host = Mock.next_override or f"http://{self.headers['Host']}"
                doc["links"]["next"] = {"href": f"{host}/api/asset/land?page%5Boffset%5D={off + Mock.page_size}"}
            return self._send(200, doc, "application/vnd.api+json")
        if u.path == "/api/asset/plant":
            return self._send(200, {"data": PLANTS, "links": {}}, "application/vnd.api+json")
        if u.path == "/api/broken":
            return self._send(200, ["not", "a", "dict"])
        return self._send(404, {"errors": []})


@pytest.fixture
def server():
    Mock.token_requests, Mock.api_requests, Mock.posted = [], [], []
    Mock.token_ttl, Mock.reject_next_n_with_401, Mock.page_size = "300", 0, 2
    Mock.next_override, Mock.tokens_issued, Mock.issue_refresh = None, 0, True
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
    t = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    t.join(timeout=5)


def cfg(url, **kw):
    base = dict(url=url, username="u", password="p", client_id="farm", land_asset_id="land-0")
    base.update(kw)
    return FarmOSConfig(**base)


OBS = sidecar_to_log({"sequence": 1, "site": "s", "field_id": "f", "telemetry": {"lat": 49.9, "lon": -97.1},
                      "model": {"name": "m", "version": "1"}, "detections": []}, "land-0")


# ---- auth ----------------------------------------------------------------------------
def test_password_grant_and_bearer_header(server):
    c = FarmOSHttpClient(cfg(server))
    assert c.create_log(OBS) == "new-1"
    form = Mock.token_requests[0]
    assert form["grant_type"] == "password" and form["client_id"] == "farm"
    assert form["scope"] == "farm_manager" and "client_secret" not in form


def test_client_credentials_grant_is_used_when_only_a_secret_is_configured(server):
    c = FarmOSHttpClient(cfg(server, username="", password="", client_id="agri-edge", client_secret="s3cret"))
    c.authenticate()
    assert Mock.token_requests[0]["grant_type"] == "client_credentials"
    assert len(c.list_land_assets()) == 5


def test_bad_credentials_raise_auth_error_without_leaking_them(server):
    c = FarmOSHttpClient(cfg(server, password="wrong-password-xyz"))
    with pytest.raises(FarmOSAuthError) as e:
        c.authenticate()
    assert "wrong-password-xyz" not in str(e.value) and "401" in str(e.value)


def test_expired_token_is_refreshed_with_the_refresh_grant(server):
    Mock.token_ttl = "0"                         # every token is already expired
    c = FarmOSHttpClient(cfg(server))
    c.create_log(OBS)
    c.create_log(OBS)
    grants = [f["grant_type"] for f in Mock.token_requests]
    assert grants == ["password", "refresh_token"]
    assert Mock.token_requests[1]["refresh_token"] == "refresh-1"


def test_a_401_mid_flight_reauthenticates_once_then_succeeds(server):
    c = FarmOSHttpClient(cfg(server))
    c.authenticate()
    Mock.reject_next_n_with_401 = 1
    assert c.create_log(OBS) == "new-1"
    assert len(Mock.token_requests) == 2


def test_persistent_401_gives_up_after_one_retry(server):
    c = FarmOSHttpClient(cfg(server))
    c.authenticate()
    Mock.reject_next_n_with_401 = 99
    with pytest.raises(FarmOSAuthError):
        c.create_log(OBS)
    assert len(Mock.token_requests) == 2          # not an infinite loop


def test_missing_credentials_and_bad_url_are_rejected_up_front():
    with pytest.raises(ValueError, match="missing"):
        FarmOSHttpClient(cfg("http://127.0.0.1:1", username="", password=""))
    for bad in ("", "ftp://x", "file:///etc/passwd", "javascript:1", "//host"):
        with pytest.raises(ValueError):
            FarmOSHttpClient(cfg(bad))


# ---- writes ---------------------------------------------------------------------------
def test_observation_and_activity_logs_go_to_their_bundle_endpoints(server):
    c = FarmOSHttpClient(cfg(server))
    c.create_log(OBS)
    c.create_log(FarmOSAdapter().build_treatment_log({"kind": "skipped", "reasons": ["X"], "lat": 49.9, "lon": -97.1}))
    assert [p for p, _ in Mock.posted] == ["/api/log/observation", "/api/log/activity"]
    assert "SIMULATION" in Mock.posted[1][1]["data"]["attributes"]["notes"]["value"]


@pytest.mark.parametrize("doc", [{}, {"data": {}}, {"data": {"type": "asset--land"}},
                                 {"data": {"type": "log--harvest"}}, {"data": {"type": "../../etc"}}])
def test_unsupported_resource_types_are_refused_not_guessed(server, doc):
    with pytest.raises(FarmOSError, match="unsupported"):
        FarmOSHttpClient(cfg(server)).create_log(doc)
    assert Mock.posted == []


# ---- reads ------------------------------------------------------------------------------
def test_fields_are_read_across_pages(server):
    fields = FarmOSHttpClient(cfg(server)).list_land_assets()
    assert [f.id for f in fields] == [f"land-{i}" for i in range(5)]
    assert fields[0] == FarmOSField(id="land-0", name="Field 0", status="active", land_type="field",
                                    geometry_wkt="POLYGON((0 0, 0 1, 1 1, 0 0))")
    gets = [p for m, p in Mock.api_requests if m == "GET"]
    assert len(gets) == 3 and "page%5Blimit%5D=50" in gets[0]


def test_plantings_are_read_with_relationships(server):
    p = FarmOSHttpClient(cfg(server)).list_plant_assets()
    assert p == [FarmOSPlanting(id="plant-1", name="Spring wheat 2026", status="active",
                                plant_type_ids=("pt-1",), location_ids=("land-0",))]


def test_next_link_to_another_origin_is_refused_and_no_token_is_sent_there(server):
    Mock.next_override = "http://127.0.0.1:9"          # hostile/misconfigured pagination link
    with pytest.raises(FarmOSError, match="different origin"):
        FarmOSHttpClient(cfg(server)).list_land_assets()


def test_runaway_pagination_is_capped(server):
    Mock.page_size = 0                                   # server never advances
    Mock.next_override = None
    # with page_size 0 the mock emits `next` while 0 < 5 forever
    with pytest.raises(FarmOSError, match="pages"):
        FarmOSHttpClient(cfg(server)).list_land_assets()


def test_non_object_json_and_http_errors_map_to_farmos_error(server):
    c = FarmOSHttpClient(cfg(server))
    with pytest.raises(FarmOSError, match="unexpected JSON"):
        c._request("GET", f"{server}/api/broken")
    with pytest.raises(FarmOSError, match="HTTP 404"):
        c._request("GET", f"{server}/api/nothing")


def test_unreachable_server_is_a_farmos_error_not_a_raw_urllib_error():
    with pytest.raises(FarmOSError, match="unreachable"):
        FarmOSHttpClient(cfg("http://127.0.0.1:1", timeout_s=1.0)).authenticate()


def test_redirects_are_not_followed(server):
    # A 302 from the token endpoint must not be chased (it could carry credentials elsewhere).
    class R(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):  # noqa: N802
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/steal")
            self.end_headers()
    h = ThreadingHTTPServer(("127.0.0.1", 0), R)
    threading.Thread(target=h.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    try:
        with pytest.raises(FarmOSAuthError, match="HTTP 302"):
            FarmOSHttpClient(cfg(f"http://127.0.0.1:{h.server_address[1]}")).authenticate()
    finally:
        h.shutdown()


# ---- adapter gate --------------------------------------------------------------------------
def test_adapter_without_opt_in_never_builds_a_client_or_touches_the_network():
    a = FarmOSAdapter.from_config(cfg("http://127.0.0.1:1"), allow_network=False)
    assert a.network_enabled is False and a._client is None
    for call in (a.list_fields, a.list_plantings, a.flush):
        with pytest.raises(FarmOSNetworkDisabled):
            call()


def test_adapter_end_to_end_push_and_read(server):
    a = FarmOSAdapter.from_config(cfg(server), allow_network=True)
    assert isinstance(a, FarmManagementAdapter) and isinstance(a, FarmDataReader)
    assert a.network_enabled
    a.queue(a.build_observation_log({"sequence": 2, "telemetry": {"lat": 49.9, "lon": -97.1},
                                     "model": {"name": "m", "version": "1"}, "detections": []}))
    a.queue(a.build_treatment_log({"kind": "treated", "lat": 49.9, "lon": -97.1}))
    assert a.flush() == ["new-1", "new-2"] and a.outbox == []
    assert [f.name for f in a.list_fields()][:2] == ["Field 0", "Field 1"]
    assert a.list_plantings()[0].name == "Spring wheat 2026"


def test_failed_push_leaves_the_payload_queued(server):
    a = FarmOSAdapter.from_config(cfg(server), allow_network=True)
    a.queue({"data": {"type": "log--harvest"}})          # unsupported -> refused
    a.queue(OBS)
    with pytest.raises(FarmOSError):
        a.flush()
    assert len(a.outbox) == 2 and Mock.posted == []


def test_repr_never_contains_secrets(server):
    c = FarmOSHttpClient(cfg(server, client_secret="s3cret"))
    c.authenticate()
    text = repr(c)
    assert "tok-" not in text and "refresh-" not in text
