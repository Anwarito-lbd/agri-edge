"""Ops API routes answer on the verb they are written for.

THE DEFECT THIS PINS
--------------------
Nine POST handlers had been pasted inside `do_GET`, where the local name `body`
does not exist. The effect was invisible to every existing test because nothing
exercised those routes over HTTP:

    POST /api/ops/vra/approve   -> 404   (do_POST never had the route)
    GET  /api/ops/vra/approve   -> 500   NameError: name 'body' is not defined

`/api/ops/vra/approve` is the human-in-the-loop gate. Spec sections 39 and 105
both require an operator to approve a variable-rate prescription before it can
reach a mission, and section 151 requires the approval to be audited. None of
that could happen, because the endpoint could not be called.

The mapping workflow (create / validate / approve / execute) and the manual
observation, scout report, camera event and mobile note ingestion were in the
same block and equally unreachable.

WHY NO TEST CAUGHT IT
---------------------
The ops suite tests the store and the helper functions directly -- `approve_prescription`
itself works fine and is covered. What was untested was whether the HTTP layer
could reach it. A route table is exactly the kind of thing that must be checked
through the door it is served behind, so these tests speak HTTP.

It was ruff's F821 that found it, which is the reason `make lint` quietly
exiting 0 when ruff was not installed was worth treating as a real finding.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from agri_edge.ops.api import OpsHandler, create_app_store


@pytest.fixture(scope="module")
def server():
    create_app_store(seed=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OpsHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    thread.join(timeout=5)


def call(base, method, path, payload=None):
    """Returns (status, parsed_body_or_raw)."""
    data = json.dumps(payload or {}).encode() if method == "POST" else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    try:
        return status, json.loads(raw.decode("utf-8"))
    except Exception:
        return status, raw


# Every route that was stranded in do_GET, with the smallest body each needs.
STRANDED_POST_ROUTES = [
    ("/api/ops/vra/approve", {"actor": "operator", "wind_ms": 2.0}),
    ("/api/ops/mapfield/create", {"field_id": "field_north", "sensor": "rgb"}),
    ("/api/ops/cameras", {"camera_id": "cam1", "label": "weed"}),
    ("/api/ops/scouts", {"scout_id": "s1", "notes": "patch by the gate"}),
    ("/api/ops/manual", {"observer": "agronomist", "text": "waterlogging"}),
    ("/api/ops/notes", {"author": "operator", "text": "checked zone 4"}),
]


@pytest.mark.parametrize("path,payload", STRANDED_POST_ROUTES,
                         ids=[r[0] for r in STRANDED_POST_ROUTES])
def test_post_routes_are_reachable(server, path, payload):
    status, body = call(server, "POST", path, payload)
    assert status in (200, 201), f"{path} -> {status} {body}"


@pytest.mark.parametrize("path,_payload", STRANDED_POST_ROUTES,
                         ids=[r[0] for r in STRANDED_POST_ROUTES])
def test_no_route_raises_a_name_error(server, _payload, path):
    """A 500 whose message is a NameError means a handler is in the wrong
    method. 404 is a legitimate answer here; 500 never is."""
    status, body = call(server, "GET", path)
    assert status != 500, f"GET {path} -> 500 {body}"
    if isinstance(body, dict):
        assert "not defined" not in str(body.get("error", ""))


def test_the_approval_gate_actually_approves(server):
    """The endpoint existing is not the point -- it has to do the thing the
    spec requires a human to do before any variable-rate application."""
    status, body = call(server, "POST", "/api/ops/vra/approve",
                        {"actor": "operator", "wind_ms": 2.0})
    assert status == 200
    assert "prescription" in body


def test_approval_is_audited(server):
    """Spec section 151: who approved it, and when. The audit write sat in the
    same dead block, so it had never run either."""
    call(server, "POST", "/api/ops/vra/approve",
         {"actor": "test-agronomist", "wind_ms": 1.0})
    status, body = call(server, "GET", "/api/ops/audit")
    if status == 404:
        pytest.skip("no audit endpoint exposed; store-level coverage applies")
    assert status == 200
    text = json.dumps(body)
    assert "vra_approve" in text and "test-agronomist" in text


def test_the_mapping_workflow_runs_end_to_end(server):
    """create -> validate -> approve -> execute, spec section 112. All four
    were stranded together."""
    status, created = call(server, "POST", "/api/ops/mapfield/create",
                           {"field_id": "field_north", "sensor": "rgb", "gsd_cm": 2.5})
    assert status == 201
    wf_id = created["workflow"]["workflow_id"]

    for route in ("validate", "approve", "execute"):
        status, body = call(server, "POST", f"/api/ops/mapfield/{route}",
                            {"workflow_id": wf_id, "actor": "operator"})
        assert status in (200, 202), f"{route} -> {status} {body}"


def test_a_read_route_still_reads(server):
    """Guard against having moved too much out of do_GET."""
    status, body = call(server, "GET", "/api/ops/alerts")
    assert status == 200
    assert "alerts" in body


def test_listing_routes_and_their_post_twins_coexist(server):
    """`/api/ops/cameras` is both a GET listing and a POST ingestion. When the
    POST version sat in do_GET it shadowed nothing -- the earlier GET route
    matched first and the POST copy was simply unreachable. Both must work now."""
    status, listed = call(server, "GET", "/api/ops/cameras")
    assert status == 200 and "items" in listed
    before = len(listed["items"])

    status, _ = call(server, "POST", "/api/ops/cameras",
                     {"camera_id": "cam9", "label": "test"})
    assert status == 201

    status, listed = call(server, "GET", "/api/ops/cameras")
    assert status == 200
    assert len(listed["items"]) == before + 1


def test_every_route_is_declared_on_exactly_one_verb():
    """Static check over the source, so a future paste into the wrong method is
    caught without needing a request for each route."""
    import ast
    import inspect

    import agri_edge.ops.api as api

    tree = ast.parse(inspect.getsource(api))
    handler = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.ClassDef) and n.name == "OpsHandler")

    per_method: dict[str, set[str]] = {}
    for fn in handler.body:
        if not isinstance(fn, ast.FunctionDef) or not fn.name.startswith("do_"):
            continue
        # The names bound anywhere in this method, including its parameters.
        bound = {a.arg for a in fn.args.args}
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                bound.update((a.asname or a.name).split(".")[0] for a in node.names)
        per_method[fn.name] = bound

    # `body` is read from the request; a method that reads it without binding it
    # is holding a handler that belongs somewhere else.
    for name, bound in per_method.items():
        fn = next(f for f in handler.body
                  if isinstance(f, ast.FunctionDef) and f.name == name)
        reads_body = any(
            isinstance(n, ast.Name) and n.id == "body" and isinstance(n.ctx, ast.Load)
            for n in ast.walk(fn)
        )
        if reads_body:
            assert "body" in bound, (
                f"OpsHandler.{name} reads `body` but never binds it -- a POST "
                "handler has been pasted into the wrong method."
            )
