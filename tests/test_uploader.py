"""Uploader tests, run against a real local HTTP server.

A mocked `urlopen` would pass while the multipart body was malformed, which is
the most likely thing to be wrong here. So these spin up an actual
`http.server`, POST to it, and assert on what the server received.

The failure paths matter as much as the happy one: on an aircraft, "the network
is absent" is the normal state, not an exception.
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from agri_edge.config import SpoolConfig
from agri_edge.store.spool import Priority, Spool
from agri_edge.store.uploader import Uploader, build_uploader, encode_multipart


class _Handler(BaseHTTPRequestHandler):
    received: list[dict] = []
    status = 200
    fail_first = 0

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        type(self).received.append(
            {
                "path": self.path,
                "content_type": self.headers.get("Content-Type", ""),
                "auth": self.headers.get("Authorization"),
                "body": body,
                "len": length,
            }
        )
        cls = type(self)
        if cls.fail_first > 0:
            cls.fail_first -= 1
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(cls.status)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass   # keep the test output clean


@pytest.fixture
def server():
    _Handler.received = []
    _Handler.status = 200
    _Handler.fail_first = 0
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", _Handler
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def spool(tmp_path):
    s = Spool(tmp_path / "spool")
    img = np.full((16, 16, 3), 7, dtype=np.uint8)
    s.add(img, {"schema": "agri-edge/frame/1", "detections": [], "seq": 1},
          Priority.NORMAL, "site-a", "field-1", 1)
    s.add(img, {"schema": "agri-edge/frame/1", "detections": [{"label": "weed"}], "seq": 2},
          Priority.ANOMALY, "site-a", "field-1", 2)
    s.add(img, {"schema": "agri-edge/frame/1", "detections": [], "seq": 3},
          Priority.DEGRADED, "site-a", "field-1", 3)
    return s


class TestEncodeMultipart:
    def test_includes_fields_and_files(self):
        body, ctype = encode_multipart({"a": "1"}, {"f": ("x.json", b"{}")})
        assert ctype.startswith("multipart/form-data; boundary=")
        assert b'name="a"' in body
        assert b'name="f"; filename="x.json"' in body
        assert b"{}" in body

    def test_boundary_matches_body(self):
        body, ctype = encode_multipart({"a": "1"}, {})
        boundary = ctype.split("boundary=")[1]
        assert body.startswith(f"--{boundary}".encode())
        assert body.rstrip().endswith(f"--{boundary}--".encode())

    def test_boundary_is_unique_per_call(self):
        """A reused boundary colliding with payload bytes corrupts the request."""
        _, c1 = encode_multipart({}, {})
        _, c2 = encode_multipart({}, {})
        assert c1 != c2

    def test_binary_payload_survives(self):
        blob = bytes(range(256))
        body, _ = encode_multipart({}, {"img": ("a.npy", blob)})
        assert blob in body

    def test_content_type_guessed_from_extension(self):
        body, _ = encode_multipart({}, {"m": ("a.json", b"{}")})
        assert b"Content-Type: application/json" in body


class TestUploadHappyPath:
    def test_uploads_all_pending(self, spool, server):
        url, handler = server
        result = Uploader(spool, url).upload_pending()
        assert result.attempted == 3
        assert result.succeeded == 3
        assert result.failed == 0
        assert len(handler.received) == 3

    def test_posts_to_frames_endpoint(self, spool, server):
        url, handler = server
        Uploader(spool, url).upload_pending(limit=1)
        assert handler.received[0]["path"] == "/frames"

    def test_highest_priority_first(self, spool, server):
        """ANOMALY frames carry findings and must go first on a brief link."""
        url, handler = server
        Uploader(spool, url).upload_pending()
        first = handler.received[0]["body"]
        assert b'name="priority"' in first
        # Priority.ANOMALY == 0
        assert b"\r\n\r\n0\r\n" in first

    def test_marks_uploaded_so_they_are_not_resent(self, spool, server):
        url, _ = server
        Uploader(spool, url).upload_pending()
        assert spool.pending() == []
        assert len(spool.entries(include_uploaded=True)) == 3

    def test_second_pass_sends_nothing(self, spool, server):
        url, handler = server
        up = Uploader(spool, url)
        up.upload_pending()
        again = up.upload_pending()
        assert again.attempted == 0
        assert len(handler.received) == 3

    def test_limit_is_respected(self, spool, server):
        url, handler = server
        result = Uploader(spool, url).upload_pending(limit=2)
        assert result.attempted == 2
        assert len(handler.received) == 2
        assert len(spool.pending()) == 1

    def test_api_key_sent_as_bearer(self, spool, server):
        url, handler = server
        Uploader(spool, url, api_key="s3cret").upload_pending(limit=1)
        assert handler.received[0]["auth"] == "Bearer s3cret"

    def test_no_auth_header_without_key(self, spool, server):
        url, handler = server
        Uploader(spool, url).upload_pending(limit=1)
        assert handler.received[0]["auth"] is None

    def test_trailing_slash_on_endpoint_is_tolerated(self, spool, server):
        url, handler = server
        Uploader(spool, url + "/").upload_pending(limit=1)
        assert handler.received[0]["path"] == "/frames"


class TestUploadModes:
    def test_metadata_mode_omits_the_image(self, spool, server):
        """The whole point: kilobytes, not megabytes, on a rural link."""
        url, handler = server
        Uploader(spool, url, mode="metadata").upload_pending(limit=1)
        body = handler.received[0]["body"]
        assert b'name="metadata"' in body
        assert b'name="image"' not in body

    def test_full_mode_includes_the_image(self, spool, server):
        url, handler = server
        Uploader(spool, url, mode="full").upload_pending(limit=1)
        assert b'name="image"' in handler.received[0]["body"]

    def test_full_mode_is_substantially_larger(self, spool, server):
        url, handler = server
        Uploader(spool, url, mode="metadata").upload_pending(limit=1)
        meta_len = handler.received[0]["len"]
        handler.received.clear()
        Uploader(spool, url, mode="full").upload_pending(limit=1)
        assert handler.received[0]["len"] > meta_len

    def test_metadata_content_is_the_sidecar(self, spool, server):
        url, handler = server
        Uploader(spool, url).upload_pending(limit=1)
        body = handler.received[0]["body"].decode("utf-8", "replace")
        assert "agri-edge/frame/1" in body

    def test_missing_image_still_sends_metadata(self, spool, server):
        """After a purge the payload is gone; the sidecar is still worth sending."""
        url, handler = server
        entry = spool.pending()[0]
        (spool.dir / entry.image_path).unlink()
        result = Uploader(spool, url, mode="full").upload_pending(limit=1)
        assert result.succeeded == 1
        assert b'name="metadata"' in handler.received[0]["body"]

    def test_invalid_mode_rejected(self, spool):
        with pytest.raises(ValueError, match="metadata"):
            Uploader(spool, "http://x", mode="thumbnail")


class TestFailureHandling:
    def test_server_error_leaves_entries_spooled(self, spool, server):
        """Nothing is lost when the backend is unhappy."""
        url, handler = server
        handler.status = 500
        handler.fail_first = 99
        result = Uploader(spool, url).upload_pending()
        assert result.succeeded == 0
        assert result.failed > 0
        assert len(spool.pending()) == 3

    def test_stops_after_consecutive_failures(self, spool, server):
        """A dead link should not be retried 4,000 times."""
        url, handler = server
        handler.fail_first = 99
        result = Uploader(spool, url).upload_pending(stop_after_failures=2)
        assert result.attempted == 2
        assert result.failed == 2

    def test_recovers_after_a_transient_failure(self, spool, server):
        url, handler = server
        handler.fail_first = 1
        result = Uploader(spool, url).upload_pending(stop_after_failures=3)
        assert result.failed == 1
        assert result.succeeded == 2
        assert len(spool.pending()) == 1     # only the failed one remains

    def test_unreachable_host_does_not_raise(self, spool):
        """Out of coverage is the normal state, not an exception."""
        up = Uploader(spool, "http://127.0.0.1:1", timeout_s=1.0)
        result = up.upload_pending(stop_after_failures=1)
        assert result.succeeded == 0
        assert result.failed == 1
        assert len(spool.pending()) == 3

    def test_errors_are_capped_in_the_summary(self, spool, server):
        url, handler = server
        handler.fail_first = 99
        result = Uploader(spool, url).upload_pending(stop_after_failures=99)
        assert len(result.as_dict()["errors"]) <= 5

    def test_empty_spool_is_a_no_op(self, tmp_path, server):
        url, handler = server
        result = Uploader(Spool(tmp_path / "empty"), url).upload_pending()
        assert result.attempted == 0
        assert result.all_ok
        assert handler.received == []


class TestBuildUploader:
    def test_none_when_no_endpoint(self, spool):
        assert build_uploader(spool, SpoolConfig()) is None

    def test_built_when_endpoint_set(self, spool):
        cfg = SpoolConfig(upload_endpoint="http://example.test")
        up = build_uploader(spool, cfg)
        assert isinstance(up, Uploader)
        assert up.endpoint == "http://example.test"

    def test_config_values_are_used(self, spool):
        cfg = SpoolConfig(
            upload_endpoint="http://example.test", upload_timeout_s=5.0, upload_api_key="k"
        )
        up = build_uploader(spool, cfg, mode="full")
        assert up.timeout_s == 5.0
        assert up.api_key == "k"
        assert up.mode == "full"

    def test_default_mode_is_metadata(self):
        assert SpoolConfig().upload_mode == "metadata"


class TestPurge:
    def test_purge_after_upload_frees_payloads(self, spool, server):
        url, _ = server
        entry = spool.pending()[0]
        Uploader(spool, url, purge_after_upload=True).upload_pending()
        assert not (spool.dir / entry.image_path).exists()
        # The index record survives, so the frame's existence is still provable.
        assert len(spool.entries(include_uploaded=True)) == 3

    def test_payloads_kept_by_default(self, spool, server):
        url, _ = server
        entry = spool.pending()[0]
        Uploader(spool, url).upload_pending()
        assert (spool.dir / entry.image_path).exists()
