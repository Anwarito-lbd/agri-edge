"""Alert state transitions are checked, and the dedupe window is used.

Finding F6 of docs/audit-2026-09-24.md: `ack()` set ACKNOWLEDGED from any
state, so acknowledging a RESOLVED alert re-opened it, and `dedupe_seconds`
was stored but never read.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from agri_edge.ops.alerts import AlertEngine, InvalidTransition
from agri_edge.ops.types import AlertState, TempKind, TypedTemperature, utcnow

FROST = TypedTemperature(value_c=-1.0, kind=TempKind.AIR)


def _raised(eng: AlertEngine):
    a = eng.evaluate_temperature(FROST, device_id="wx1", synthetic=True)
    assert a is not None
    return a


def test_ack_does_not_reopen_a_resolved_alert():
    eng = AlertEngine()
    a = _raised(eng)
    eng.resolve(a.alert_id, "op")
    with pytest.raises(InvalidTransition):
        eng.ack(a.alert_id, "late-click")
    assert a.state == AlertState.RESOLVED


@pytest.mark.parametrize("action", ["ack", "resolve", "escalate"])
def test_resolved_is_terminal_for_operator_actions(action):
    eng = AlertEngine()
    a = _raised(eng)
    eng.resolve(a.alert_id, "op")
    with pytest.raises(InvalidTransition):
        getattr(eng, action)(a.alert_id, "op")


def test_escalated_alert_can_still_be_acknowledged():
    eng = AlertEngine()
    a = _raised(eng)
    eng.escalate(a.alert_id, "op")
    eng.ack(a.alert_id, "op")
    assert a.state == AlertState.ACKNOWLEDGED


def test_recurrence_inside_the_window_reopens_the_same_alert():
    eng = AlertEngine(dedupe_seconds=600)
    a = _raised(eng)
    eng.resolve(a.alert_id, "op")
    again = _raised(eng)
    assert again.alert_id == a.alert_id
    assert again.state == AlertState.OPEN
    assert again.meta["reopened"] == 1


def test_recurrence_after_the_window_is_a_new_alert():
    eng = AlertEngine(dedupe_seconds=600)
    a = _raised(eng)
    eng.resolve(a.alert_id, "op")
    a.updated_at = (utcnow() - timedelta(seconds=601)).isoformat()
    again = _raised(eng)
    assert again.alert_id != a.alert_id
    assert again.state == AlertState.OPEN


def test_http_ack_of_resolved_alert_is_409():
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from agri_edge.ops.api import OpsHandler, create_app_store

    store = create_app_store(seed=True)
    alert = store.alerts.list_alerts()[0]
    if alert.state != AlertState.RESOLVED:
        store.alerts.resolve(alert.alert_id, "op")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), OpsHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{httpd.server_address[1]}/api/ops/alerts/ack",
            data=json.dumps({"alert_id": alert.alert_id, "by": "op"}).encode(),
            method="POST", headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=10)
        assert err.value.code == 409
    finally:
        httpd.shutdown()
