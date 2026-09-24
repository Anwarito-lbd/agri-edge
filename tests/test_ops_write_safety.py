"""The Ops API refuses the writes it used to accept.

Pins findings F1-F3 of docs/audit-2026-09-24.md:

F1  `approve_prescription` defaulted `force_validated=True`, marking the
    prescription validated before checking it, and skipped the wind check when
    no wind was sent. `approve_prescription(rx)` with no arguments returned
    approved=True.
F2  `POST /api/ops/detections` used `setdefault` for the treatment flags, so a
    client could store `may_drive_treatment: true`.
F3  Every response carried `Access-Control-Allow-Origin: *`, the body was
    parsed as JSON whatever its Content-Type, and there was no credential of
    any kind -- so any page open in the operator's browser could POST
    `/api/ops/seed` (wipes the store) or `/api/ops/vra/approve`.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from agri_edge.ops.api import OpsHandler, TOKEN_ENV, create_app_store, serve
from agri_edge.ops.vra import approve_prescription, make_demo_prescription, validate_prescription


# -- F1: the approval gate ------------------------------------------------------


def test_approval_without_arguments_is_refused():
    """The exact call that used to approve."""
    result = approve_prescription(make_demo_prescription())
    assert result["approved"] is False


def test_approving_does_not_mark_a_prescription_validated():
    rx = make_demo_prescription()
    approve_prescription(rx, wind_ms=1.0)
    assert rx.validated is False
    assert rx.approved is False


def test_missing_wind_blocks_even_a_validated_prescription():
    rx = make_demo_prescription()
    rx.validated = True
    result = approve_prescription(rx, wind_ms=None)
    assert result["approved"] is False
    assert any("wind" in i for i in result["issues"])


def test_high_wind_blocks():
    rx = make_demo_prescription()
    rx.validated = True
    result = approve_prescription(rx, wind_ms=rx.constraints.wind_max_ms + 0.1)
    assert result["approved"] is False


def test_validated_prescription_in_calm_wind_is_approved():
    """The gate still opens when every condition is actually met."""
    rx = make_demo_prescription()
    rx.validated = True
    result = approve_prescription(rx, actor="agronomist", wind_ms=1.0)
    assert result["approved"] is True
    assert result["auto_apply"] is False
    assert rx.approved_by == "agronomist"


def test_validation_does_not_treat_missing_wind_as_calm():
    rx = make_demo_prescription()
    rx.validated = True
    assert validate_prescription(rx, wind_ms=None)["ok"] is False
    assert validate_prescription(rx, wind_ms=0.0)["ok"] is True


# -- HTTP ---------------------------------------------------------------------


@pytest.fixture
def server():
    create_app_store(seed=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OpsHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    thread.join(timeout=5)


def call(base, method, path, payload=None, headers=None, raw=None):
    data = None
    if method == "POST":
        data = raw if raw is not None else json.dumps(payload or {}).encode()
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    req = urllib.request.Request(base + path, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body, status, got = r.read(), r.status, dict(r.headers)
    except urllib.error.HTTPError as exc:
        body, status, got = exc.read(), exc.code, dict(exc.headers)
    try:
        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        parsed = body
    return status, parsed, got


def test_http_approval_of_unvalidated_prescription_is_refused(server):
    status, body, _ = call(server, "POST", "/api/ops/vra/approve",
                           {"actor": "operator", "wind_ms": 1.0})
    assert status == 200
    assert body["approved"] is False
    assert body["prescription"]["approved"] is False


def test_non_numeric_wind_is_a_client_error_not_a_crash(server):
    status, body, _ = call(server, "POST", "/api/ops/vra/approve",
                           {"actor": "operator", "wind_ms": "calm"})
    assert status == 400, body
    status, body, _ = call(server, "GET", "/api/ops/vra/validate?wind_ms=calm")
    assert status == 400, body


def test_validate_without_wind_does_not_invent_a_calm_day(server):
    status, body, _ = call(server, "GET", "/api/ops/vra/validate")
    assert status == 200
    assert body["ok"] is False
    assert any("wind" in i for i in body["issues"])


def test_client_cannot_grant_the_treatment_gate(server):
    status, body, _ = call(server, "POST", "/api/ops/detections", {
        "label": "weed", "confidence": 0.99,
        "validated_locally": True, "may_drive_treatment": True,
    })
    assert status == 201
    det = body["detection"]
    assert det["may_drive_treatment"] is False
    assert det["validated_locally"] is False
    assert det["claimed_may_drive_treatment"] is True


def test_no_wildcard_cors(server):
    for method, path in (("GET", "/api/ops/overview"), ("OPTIONS", "/api/ops/seed")):
        _, _, headers = call(server, method, path)
        assert "Access-Control-Allow-Origin" not in headers, (method, path)


def test_cross_origin_post_is_refused(server):
    status, body, _ = call(server, "POST", "/api/ops/seed",
                           headers={"Origin": "https://evil.example"})
    assert status == 403, body


def test_same_origin_post_is_allowed(server):
    host = server.removeprefix("http://")
    status, body, _ = call(server, "POST", "/api/ops/alerts/ack",
                           {"alert_id": "nope"}, headers={"Origin": f"http://{host}"})
    # Reaches the route (400 for the unknown id), i.e. not refused as cross-origin.
    assert status == 400, body


@pytest.mark.parametrize("ctype", ["text/plain", "application/x-www-form-urlencoded", ""])
def test_simple_request_content_types_are_refused(server, ctype):
    """These are the content types a hostile page can POST without a preflight."""
    status, body, _ = call(server, "POST", "/api/ops/seed", headers={"Content-Type": ctype})
    assert status == 415, body


def test_oversized_body_is_refused(server):
    big = b'{"x": "' + b"a" * 1_100_000 + b'"}'
    status, _, _ = call(server, "POST", "/api/ops/notes", raw=big)
    assert status == 413


def test_non_object_body_is_refused(server):
    status, _, _ = call(server, "POST", "/api/ops/notes", raw=b"[1, 2, 3]")
    assert status == 400


def test_missing_required_field_is_400_not_404(server):
    status, body, _ = call(server, "POST", "/api/ops/alerts/ack", {})
    assert status == 400, body


def test_token_is_required_when_configured(server, monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, "s3cret")
    status, _, _ = call(server, "POST", "/api/ops/notes", {"text": "x"})
    assert status == 401
    status, _, _ = call(server, "POST", "/api/ops/notes", {"text": "x"},
                        headers={"Authorization": "Bearer wrong"})
    assert status == 401
    status, _, _ = call(server, "POST", "/api/ops/notes", {"text": "x"},
                        headers={"Authorization": "Bearer s3cret"})
    assert status == 201
    # Reads stay open on the loopback bind; the token guards writes.
    status, _, _ = call(server, "GET", "/api/ops/overview")
    assert status == 200


def test_refuses_to_serve_off_loopback_without_a_token(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    with pytest.raises(SystemExit):
        serve(host="0.0.0.0", port=0)
