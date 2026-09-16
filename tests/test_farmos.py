"""Tests for the farmOS integration, against a stub farmOS.

There is no farmOS server on this machine (it needs Docker, which is absent), so
these run against a local stub that speaks the same OAuth2 + JSON:API shapes.
That verifies **our** side: the payload we build, the auth flow, error handling
and the give-up rule. It does not verify that farmOS accepts these payloads — for
that, point it at a real instance. `test_payload_shape_matches_farmos_jsonapi`
encodes what the API expects so a drift shows up as a test failure rather than a
500 in the field.

Two things here are security-relevant rather than merely functional:

* credentials must come from the environment and never from config, and
* a refusal to run without them must be loud, not a silent no-op.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from agri_edge.store.farmos import (
    FarmOSClient,
    FarmOSConfig,
    push_spool,
    sidecar_to_log,
)
from agri_edge.store.spool import Priority, Spool

SIDECAR = {
    "entry_id": "e1",
    "sequence": 7,
    "site": "field-trial",
    "field_id": "plot-01",
    "priority": 1,
    "telemetry": {"lat": 49.8951, "lon": -97.1384},
    "model": {"name": "imageweeds_yolox_s", "version": "0.1.0"},
    "detections": [
        {"label": "kochia", "may_drive_treatment": False},
        {"label": "kochia", "may_drive_treatment": False},
        {"label": "ragweed", "may_drive_treatment": False},
    ],
    "qa": {"passed": True},
}


class _Stub(BaseHTTPRequestHandler):
    received: list = []
    fail_logs = False

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        if self.path.endswith("/oauth/token"):
            self._json(200, {"access_token": "test-token-123", "token_type": "Bearer"})
            return

        if self.path.endswith("/api/log/observation"):
            if self.fail_logs:
                self._json(500, {"errors": [{"detail": "stub failure"}]})
                return
            _Stub.received.append(
                {"auth": self.headers.get("Authorization"),
                 "content_type": self.headers.get("Content-Type"),
                 "body": json.loads(body.decode("utf-8"))}
            )
            self._json(201, {"data": {"id": f"log-{len(_Stub.received)}"}})
            return

        self._json(404, {})

    def _json(self, status, obj):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/vnd.api+json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):  # silence the test log
        pass


@pytest.fixture
def stub():
    _Stub.received = []
    _Stub.fail_logs = False
    httpd = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", _Stub
    httpd.shutdown()


def _cfg(url, **kw):
    return FarmOSConfig(url=url, username="u", password="p", **kw)


class TestPayload:
    def test_counts_detections_by_label(self):
        attrs = sidecar_to_log(SIDECAR)["data"]["attributes"]
        assert "2 x kochia" in attrs["name"]
        assert "1 x ragweed" in attrs["name"]

    def test_geometry_is_wkt_longitude_first(self):
        """POINT(x y) is POINT(lon lat). Reversed puts Manitoba in Somalia."""
        geom = sidecar_to_log(SIDECAR)["data"]["attributes"]["geometry"]["value"]
        assert geom == "POINT(-97.1384 49.8951)"

    def test_unvalidated_model_says_so_in_words(self):
        """The flag's whole purpose is that a human can read it later."""
        notes = sidecar_to_log(SIDECAR)["data"]["attributes"]["notes"]["value"]
        assert "DECISION SUPPORT ONLY" in notes
        assert "may drive a treatment" in notes

    def test_validated_model_is_described_differently(self):
        meta = json.loads(json.dumps(SIDECAR))
        meta["detections"][0]["may_drive_treatment"] = True
        notes = sidecar_to_log(meta)["data"]["attributes"]["notes"]["value"]
        assert "DECISION SUPPORT ONLY" not in notes
        assert "may inform treatment" in notes

    def test_failed_qa_is_recorded_as_degraded_not_hidden(self):
        meta = json.loads(json.dumps(SIDECAR))
        meta["qa"] = {"passed": False}
        notes = sidecar_to_log(meta)["data"]["attributes"]["notes"]["value"]
        assert "degraded, not discarded" in notes

    def test_missing_position_omits_geometry_rather_than_inventing_one(self):
        meta = json.loads(json.dumps(SIDECAR))
        meta["telemetry"] = {}
        assert "geometry" not in sidecar_to_log(meta)["data"]["attributes"]

    def test_no_detections_is_still_a_valid_observation(self):
        """An empty field is a real agronomic result, not a reason to send nothing."""
        meta = json.loads(json.dumps(SIDECAR))
        meta["detections"] = []
        attrs = sidecar_to_log(meta)["data"]["attributes"]
        assert "no detections" in attrs["name"]

    def test_land_asset_relationship_is_optional(self):
        assert "relationships" not in sidecar_to_log(SIDECAR)["data"]
        linked = sidecar_to_log(SIDECAR, land_asset_id="abc-123")
        rel = linked["data"]["relationships"]["location"]["data"][0]
        assert rel == {"type": "asset--land", "id": "abc-123"}

    def test_payload_shape_matches_farmos_jsonapi(self):
        """Pins the contract so upstream drift fails here, not in the field."""
        data = sidecar_to_log(SIDECAR)["data"]
        assert data["type"] == "log--observation"
        assert set(data["attributes"]) >= {"name", "status", "notes", "data"}
        assert data["attributes"]["status"] == "done"
        # `data` is a JSON string field in farmOS, not a nested object.
        assert isinstance(data["attributes"]["data"], str)
        json.loads(data["attributes"]["data"])


class TestCredentials:
    def test_refuses_to_construct_without_credentials(self):
        """Loud, not a silent no-op that looks like a successful empty upload."""
        with pytest.raises(ValueError, match="FARMOS_USERNAME"):
            FarmOSClient(FarmOSConfig(url="http://x"))

    def test_error_names_the_environment_variables(self):
        with pytest.raises(ValueError, match="never from a config file"):
            FarmOSClient(FarmOSConfig(url="http://x"))

    def test_from_env_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("FARMOS_USERNAME", "alice")
        monkeypatch.setenv("FARMOS_PASSWORD", "hunter2")
        monkeypatch.setenv("FARMOS_CLIENT_SECRET", "s3cret")
        cfg = FarmOSConfig.from_env("http://farm.example")
        assert cfg.username == "alice" and cfg.client_secret == "s3cret"
        assert cfg.missing_credentials() == []

    def test_from_env_with_nothing_set_reports_what_is_missing(self, monkeypatch):
        for k in ("FARMOS_USERNAME", "FARMOS_PASSWORD", "FARMOS_CLIENT_SECRET"):
            monkeypatch.delenv(k, raising=False)
        missing = FarmOSConfig.from_env("http://farm.example").missing_credentials()
        assert "FARMOS_USERNAME" in missing and "FARMOS_PASSWORD" in missing

    def test_sending_before_authenticating_raises(self):
        client = FarmOSClient(_cfg("http://127.0.0.1:1"))
        with pytest.raises(RuntimeError, match="authenticate"):
            client.create_log({})


class TestAgainstStub:
    def test_authenticate_then_create(self, stub):
        url, srv = stub
        client = FarmOSClient(_cfg(url))
        client.authenticate()
        log_id = client.create_log(sidecar_to_log(SIDECAR))
        assert log_id == "log-1"
        assert srv.received[0]["auth"] == "Bearer test-token-123"
        assert srv.received[0]["content_type"] == "application/vnd.api+json"

    def test_push_spool_sends_highest_priority_first(self, stub, tmp_path):
        url, srv = stub
        spool = Spool(tmp_path / "spool", 10 * 1024 * 1024)
        import numpy as np

        for seq, prio in ((1, Priority.NORMAL), (2, Priority.ANOMALY), (3, Priority.DEGRADED)):
            meta = json.loads(json.dumps(SIDECAR))
            meta["sequence"] = seq
            spool.add(np.zeros((4, 4, 3), np.uint8), meta, priority=prio,
                      site="s", field_id="f", sequence=seq)

        result = push_spool(spool, _cfg(url))
        assert result.created == 3 and result.failed == 0
        order = [r["body"]["data"]["attributes"]["data"] for r in srv.received]
        seqs = [json.loads(o)["sequence"] for o in order]
        assert seqs[0] == 2, "ANOMALY must go first"

    def test_push_spool_gives_up_after_consecutive_failures(self, stub, tmp_path):
        """Repeated failures mean the server is down, not that frames are bad."""
        url, srv = stub
        srv.fail_logs = True
        spool = Spool(tmp_path / "spool", 10 * 1024 * 1024)
        import numpy as np

        for seq in range(10):
            spool.add(np.zeros((4, 4, 3), np.uint8), SIDECAR, priority=Priority.NORMAL,
                      site="s", field_id="f", sequence=seq)

        result = push_spool(spool, _cfg(url), stop_after_failures=3)
        assert result.created == 0
        assert result.attempted == 3, "should stop, not grind through all ten"

    def test_authentication_failure_is_reported_not_raised(self, stub, tmp_path):
        """A dead uplink must not crash the aircraft's software."""
        spool = Spool(tmp_path / "spool", 1024 * 1024)
        result = push_spool(spool, _cfg("http://127.0.0.1:1"))
        assert result.created == 0
        assert any("authentication failed" in e for e in result.errors)
