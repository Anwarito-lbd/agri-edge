"""Decisions dashboard (master-spec #9): a READ-ONLY view of the simulated decision engine.

The properties that matter most are negative: nothing reachable from this page or its
API can arm, command or actuate. Everything is SIMULATED; demo data is synthetic.
"""
from __future__ import annotations

import ast
import json
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from agri_edge.decision import ArmingState, TreatmentEventLog, engine as E
from agri_edge.decision.engine import TreatmentEvent
from agri_edge.ops import decisions as D
from agri_edge.ops.api import OpsHandler, create_app_store
from agri_edge.ops.store import OpsStore

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "src" / "agri_edge" / "ops" / "ui" / "decisions.html"
MODULE = ROOT / "src" / "agri_edge" / "ops" / "decisions.py"


@pytest.fixture
def seeded():
    s = OpsStore()
    D.seed_demo_decisions(s, now=2_000_000.0)
    return s


# ---- report content -------------------------------------------------------------
def test_empty_store_reports_nothing_and_not_armed():
    r = D.decisions_report(OpsStore(), now=1.0)
    assert r["source"] == "none" and r["read_only"] is True and r["status"] == "SIMULATED"
    assert r["counts"] == {"detected": 0, "treated": 0, "skipped": 0,
                           "outside_geofence": 0, "refused_other_gate": 0}
    assert r["recent"] == [] and r["state"]["arm_live"] is False
    assert r["state"]["geofence"]["configured"] is False
    assert "refuses every treatment" in r["state"]["arm_note"]


def test_demo_counts_add_up(seeded):
    r = D.decisions_report(seeded, now=2_000_000.0)
    c = r["counts"]
    assert r["source"] == "demo" and r["simulation"] is True
    assert c["detected"] == c["treated"] + c["skipped"] == 13
    assert c["treated"] == 4 and c["skipped"] == 9
    assert c["skipped"] == c["outside_geofence"] + c["refused_other_gate"]
    assert c["outside_geofence"] == 2          # inside-the-buffer and outside-the-field targets


def test_refusals_are_attributed_to_the_right_gate(seeded):
    g = D.decisions_report(seeded, now=2_000_000.0)["refusals_by_gate"]
    assert g["reasons"]["geofence"][E.OUTSIDE_TREATMENT_GEOFENCE] == 2
    assert g["reasons"]["confidence"][E.CONFIDENCE_BELOW_THRESHOLD] == 1
    assert g["reasons"]["model_validated"][E.MODEL_NOT_VALIDATED] == 1
    assert g["reasons"]["pose"][E.POSE_STALE] == 1
    assert g["reasons"]["mission_state"][E.MISSION_STATE_NOT_PERMITTED] == 1
    assert g["reasons"]["command"][E.COMMAND_MISSING] == 1
    assert g["reasons"]["command"][E.COMMAND_REPLAYED] == 1
    # one event can fail several gates: the uncertain position also leaves the geofence unevaluated
    assert g["reasons"]["position"][E.POSITION_UNCERTAIN] == 1
    assert g["reasons"]["geofence"][E.GEOFENCE_NOT_EVALUATED] == 1
    assert g["totals"]["geofence"] == 3 and "unmapped" not in g["totals"]


def test_every_engine_reason_code_is_mapped_to_a_gate():
    codes = {v for k, v in vars(E).items() if k.isupper() and isinstance(v, str) and v == k}
    assert codes, "no reason codes found"
    assert codes <= set(D.REASON_TO_GATE), codes - set(D.REASON_TO_GATE)
    assert set(D.REASON_TO_GATE.values()) <= set(E.GATES) | {"engine_error"}


def test_recent_table_newest_first_limited_and_simulated(seeded):
    r = D.decisions_report(seeded, limit=5, now=2_000_000.0)
    assert len(r["recent"]) == 5 and all(x["simulated"] is True for x in r["recent"])
    assert r["recent"][0]["detection_id"] > "" and r["recent"][0]["outcome"] == "skipped"
    assert r["recent"][0]["gates_failed"] == ["command"]       # the replay is the last event
    assert len(D.decisions_report(seeded, limit=10_000)["recent"]) <= D.MAX_RECENT
    assert len(D.decisions_report(seeded, limit=-3)["recent"]) == 1


def test_state_readout_and_arm_expiry(seeded):
    now = 2_000_000.0
    live = D.decisions_report(seeded, now=now)["state"]
    assert live["operator_armed"] and live["payload_armed"] and live["arm_live"]
    assert live["armed_by"] == "demo-operator" and live["arm_seconds_remaining"] > 0
    assert live["geofence"]["configured"] and live["geofence"]["treatment_buffer_m"] == 10.0
    assert live["geofence"]["area_ha"] == 4.0
    assert live["mission_state"] == "TREATMENT_ACTIVE" and live["actuator"]["simulated"] is True
    lapsed = D.decisions_report(seeded, now=now + 7200)["state"]
    assert lapsed["arm_live"] is False and lapsed["arm_seconds_remaining"] == 0.0


def test_half_armed_is_not_armed():
    s = OpsStore()
    log = TreatmentEventLog()
    D.attach_decision_source(s, log, arming=ArmingState(operator_armed=True, payload_armed=False,
                                                        armed_by="a", expires_at=100.0))
    assert D.decisions_report(s, now=50.0)["state"]["arm_live"] is False


def test_unknown_reason_is_reported_not_dropped():
    s = OpsStore()
    log = TreatmentEventLog()
    log.append(TreatmentEvent(event_id="x", ts=1.0, kind="skipped", reasons=["BRAND_NEW_CODE"]))
    r = D.decisions_report(s if False else _attach(s, log))
    assert r["refusals_by_gate"]["totals"] == {"unmapped": 1}


def _attach(s, log):
    D.attach_decision_source(s, log)
    return s


def test_view_is_a_copy_not_a_handle_to_the_live_log():
    s = OpsStore()
    log = TreatmentEventLog()
    log.append(TreatmentEvent(event_id="a", ts=1.0, kind="skipped", reasons=["COMMAND_MISSING"]))
    D.attach_decision_source(s, log)
    log.events[0].reasons.append("TAMPERED")
    log.append(TreatmentEvent(event_id="b", ts=2.0, kind="treated"))
    r = D.decisions_report(s)
    assert r["counts"]["treated"] == 0 and r["refusals_by_gate"]["by_reason"] == {"COMMAND_MISSING": 1}


# ---- read-only by construction ----------------------------------------------------
def test_module_never_calls_anything_that_actuates():
    # Only `seed_demo_decisions` (a startup-time synthetic scenario on a SimulatedActuator,
    # never reachable from a route) may drive the engine; the report/attach path may not.
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    forbidden = {"process", "evaluate", "execute", "publish", "send", "post"}
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        called = {n.func.attr for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        if fn.name == "seed_demo_decisions":
            assert "process" in called          # documents the one exception
        else:
            assert not called & forbidden, (fn.name, called & forbidden)
    api = (ROOT / "src" / "agri_edge" / "ops" / "api.py").read_text(encoding="utf-8")
    assert "seed_demo_decisions" not in api and "decision_view" not in api


def test_view_holds_no_engine_or_actuator_handle(seeded):
    v = seeded.decision_view
    assert isinstance(v, D.DecisionView)
    for value in vars(v).values():
        assert not hasattr(value, "execute") and not hasattr(value, "process")
    assert not hasattr(v.actuator, "execute")


def test_page_has_no_controls_and_no_writes():
    src = PAGE.read_text(encoding="utf-8").lower()
    for forbidden in ("<form", "<button", "<input", "<select", "method:", "'post'", '"post"',
                      "xmlhttprequest", "sendbeacon", "onclick"):
        assert forbidden not in src, forbidden
    assert "fetch(path)" in src and "simulation" in src


@pytest.fixture(scope="module")
def server():
    create_app_store(seed=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OpsHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    t.join(timeout=5)


def _call(base, method, path, body=None):
    data = json.dumps(body or {}).encode() if method in ("POST", "PUT", "DELETE", "PATCH") else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_api_get_returns_the_report(server):
    status, raw = _call(server, "GET", "/api/ops/decisions?limit=3")
    r = json.loads(raw)
    assert status == 200 and r["banner"] == "SIMULATION" and r["read_only"] is True
    assert len(r["recent"]) == 3 and r["counts"]["treated"] == 4


def test_api_bad_limit_is_a_400_not_a_500(server):
    assert _call(server, "GET", "/api/ops/decisions?limit=abc")[0] == 400


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_no_write_route_exists_for_decisions(server, method):
    before = json.loads(_call(server, "GET", "/api/ops/decisions")[1])["counts"]
    for path in ("/api/ops/decisions", "/api/ops/decisions/arm", "/api/ops/decisions/treat",
                 "/api/ops/decisions/command"):
        status, _ = _call(server, method, path, {"operator_armed": True, "treat": True})
        assert status in (404, 405, 501), (method, path, status)
    after = json.loads(_call(server, "GET", "/api/ops/decisions")[1])["counts"]
    assert before == after


def test_page_is_served_and_linked_in_nav(server):
    status, raw = _call(server, "GET", "/ops/decisions.html")
    assert status == 200 and b"READ-ONLY" in raw and b"sim-banner" in raw
    status, raw = _call(server, "GET", "/api/ops/nav")
    pages = {p["id"]: p for p in json.loads(raw)["pages"]}
    assert pages["decisions"]["path"] == "/ops/decisions.html" and pages["decisions"]["read_only"]


# ---- the page itself, executed -------------------------------------------------------
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_script_renders_the_report_and_escapes_hostile_text(seeded):
    seeded.decision_view.events[-1]["reasons"] = ["<img src=x onerror=alert(1)>"]
    report = D.decisions_report(seeded, now=2_000_000.0)
    script = PAGE.read_text(encoding="utf-8").split("<script>")[1].split("</script>")[0]
    harness = (
        "const REPORT=" + json.dumps(report) + ";"
        "const els={content:{innerHTML:''},'sim-banner':{style:{}}};"
        "global.document={getElementById:id=>els[id]};"
        "global.location={};"
        "global.fetch=async p=>({status:200,json:async()=>p.includes('overview')?{simulation:true}:REPORT});"
        + script +
        ";setTimeout(()=>process.stdout.write(els.content.innerHTML),50);"
    )
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, check=True).stdout
    assert "OUTSIDE_TREATMENT_GEOFENCE" in out and "Recent decisions" in out
    assert "<img" not in out and "&lt;img" in out
    assert "demo-operator" in out and "SIMULATED" in out
