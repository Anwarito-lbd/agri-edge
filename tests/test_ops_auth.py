"""Users, roles and sessions on the ops station.

Before 24 Sept 2026 there were no users: the audit log recorded whatever
`actor` the client sent, and any caller could do anything.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from agri_edge.ops import auth
from agri_edge.ops.api import OpsHandler, create_app_store

PW = "correct-horse-battery"


@pytest.fixture
def station(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "ITERATIONS", 1000)       # keep the suite fast
    monkeypatch.setattr(auth, "_failures", {})
    monkeypatch.delenv("OPS_API_TOKEN", raising=False)
    store = create_app_store(seed=True, sqlite_path=str(tmp_path / "ops.sqlite"))
    for name, role in (("vera", "viewer"), ("otto", "operator"), ("agnes", "agronomist"),
                       ("ada", "admin"), ("aud", "auditor")):
        auth.add_user(store, name, PW, role)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OpsHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield store, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(base, path, body=None, token=None, cookie=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read()), dict(exc.headers)


def login(base, user):
    st, body, headers = call(base, "/api/ops/auth/login", {"username": user, "password": PW})
    assert st == 200, body
    return body["token"], headers


def test_everything_needs_a_login_once_users_exist(station):
    _, base = station
    assert call(base, "/api/ops/overview")[0] == 401
    assert call(base, "/api/ops/alerts/ack", {"alert_id": "x"})[0] == 401
    with urllib.request.urlopen(base + "/ops/", timeout=10) as r:
        assert r.status == 200, "the login page and static UI still load"


def test_login_sets_a_strict_http_only_cookie_that_works(station):
    _, base = station
    token, headers = login(base, "vera")
    cookie = headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    st, me, _ = call(base, "/api/ops/auth/me", cookie=f"ae_session={token}")
    assert st == 200 and me["name"] == "vera" and me["role"] == "viewer"
    assert call(base, "/api/ops/overview", cookie=f"ae_session={token}")[0] == 200


def test_wrong_password_and_lockout(station):
    _, base = station
    for _ in range(5):
        assert call(base, "/api/ops/auth/login", {"username": "otto", "password": "nope-nope-nope"})[0] == 401
    assert call(base, "/api/ops/auth/login", {"username": "otto", "password": PW})[0] == 429


@pytest.mark.parametrize("user,path,body,ok", [
    ("vera", "/api/ops/notes", {"text": "x"}, False),
    ("otto", "/api/ops/notes", {"text": "x"}, True),
    ("otto", "/api/ops/vra/approve", {"wind_ms": 1.0}, False),
    ("agnes", "/api/ops/vra/approve", {"wind_ms": 1.0}, True),
    ("agnes", "/api/ops/seed", {}, False),
    ("ada", "/api/ops/seed", {}, True),
    ("agnes", "/api/ops/auth/users", {"username": "x", "password": PW, "role": "admin"}, False),
])
def test_roles_gate_writes(station, user, path, body, ok):
    _, base = station
    token, _ = login(base, user)
    st, out, _ = call(base, path, body, token=token)
    assert (st != 403) is ok, (st, out)


def test_the_audit_log_names_the_logged_in_user_not_the_body(station):
    store, base = station
    token, _ = login(base, "otto")
    alert = store.alerts.list_alerts()[0]
    st, _, _ = call(base, "/api/ops/alerts/ack", {"alert_id": alert.alert_id, "by": "the-ceo"}, token=token)
    assert st == 200
    entry = [e for e in store.audit if e.action == "ack"][-1]
    assert entry.actor == "otto"
    assert alert.ack_by == "otto"


def test_audit_log_is_readable_by_admin_and_auditor_only(station):
    _, base = station
    for user, code in (("vera", 403), ("agnes", 403), ("aud", 200), ("ada", 200)):
        token, _ = login(base, user)
        assert call(base, "/api/ops/audit", token=token)[0] == code, user


def test_service_token_may_only_ingest(station, monkeypatch):
    _, base = station
    monkeypatch.setenv("OPS_API_TOKEN", "svc-secret-token")
    st, _, _ = call(base, "/api/ops/ingest", {"topic": "agriedge/farm/f/zone/z/soil",
                                              "payload": {"moisture_pct": 20}}, token="svc-secret-token")
    assert st == 202
    assert call(base, "/api/ops/notes", {"text": "x"}, token="svc-secret-token")[0] == 403
    assert call(base, "/api/ops/overview", token="svc-secret-token")[0] == 403


def test_password_reset_signs_the_user_out(station):
    store, base = station
    token, _ = login(base, "otto")
    auth.add_user(store, "otto", "a-brand-new-password", "operator")
    assert call(base, "/api/ops/overview", token=token)[0] == 401


def test_tampered_and_expired_tokens_are_rejected(station):
    store, base = station
    token, _ = login(base, "vera")
    v, body, sig = token.split(".")
    forged = auth._b64(auth._unb64(body).replace(b'"vera"', b'"ada"'))
    assert call(base, "/api/ops/seed", {}, token=f"{v}.{forged}.{sig}")[0] == 401
    u = auth._users(store)["vera"]
    old, _ = auth.issue(store, u, now=time.time() - auth.SESSION_S - 10)
    assert auth.verify(store, old) is None


def test_users_and_sessions_survive_a_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "ITERATIONS", 1000)
    monkeypatch.delenv("OPS_SESSION_SECRET", raising=False)
    db = str(tmp_path / "ops.sqlite")
    store = create_app_store(seed=False, sqlite_path=db)
    auth.add_user(store, "ada", PW, "admin")
    token, _, _ = auth.login(store, "ada", PW)
    again = create_app_store(seed=False, sqlite_path=db)
    assert auth.verify(again, token).name == "ada"


def test_weak_passwords_and_bad_roles_are_refused(tmp_path):
    store = create_app_store(seed=False)
    with pytest.raises(ValueError):
        auth.add_user(store, "x", "short", "viewer")
    with pytest.raises(ValueError):
        auth.add_user(store, "x", PW, "emperor")


def test_open_mode_is_unchanged_without_users():
    store = create_app_store(seed=True)
    assert not auth.auth_enabled(store)
