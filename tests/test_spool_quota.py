"""The spool keeps working when the disk fills.

Finding F11 of docs/audit-2026-09-24.md:

* the quota evicted QA-failed frames and nothing else, so a spool of ordinary
  frames grew until every save failed;
* evicted entries stayed "pending" in the index, so the uploader hit their
  missing sidecars on every pass, counted three of them as "the link is down",
  and stopped -- permanently, since the same entries were first in line next
  time too.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from agri_edge.store.spool import Priority, Spool
from agri_edge.store.uploader import Uploader

IMG = np.ones((100, 100, 3), dtype=np.uint8)   # 30 kB as .npy


def _add(spool: Spool, prio: Priority, seq: int):
    return spool.add(IMG, {"seq": seq}, prio, "s", "f", seq)


def test_evicted_entries_leave_the_upload_queue(tmp_path):
    spool = Spool(tmp_path, max_bytes=10**9)
    kept = _add(spool, Priority.ANOMALY, 1)
    doomed = _add(spool, Priority.DEGRADED, 2)
    spool.max_bytes = 1
    spool._enforce_quota()
    ids = {e.entry_id for e in spool.pending()}
    assert doomed.entry_id not in ids
    assert kept.entry_id in ids
    # ...but the record that it existed remains.
    all_ids = {e.entry_id for e in spool.entries(include_uploaded=True, include_evicted=True)}
    assert doomed.entry_id in all_ids


def test_normal_frames_lose_their_image_but_keep_their_sidecar(tmp_path):
    spool = Spool(tmp_path, max_bytes=10**9)
    normals = [_add(spool, Priority.NORMAL, i) for i in range(5)]
    spool.max_bytes = int(spool.total_bytes() * 0.5)
    spool._enforce_quota()

    assert spool.total_bytes() <= spool.max_bytes
    pending = {e.entry_id: e for e in spool.pending()}
    assert set(pending) == {e.entry_id for e in normals}, "sidecars must stay queued"
    oldest = pending[normals[0].entry_id]
    assert oldest.image_evicted
    assert not (spool.dir / oldest.image_path).exists()
    assert (spool.dir / oldest.meta_path).exists()
    newest = pending[normals[-1].entry_id]
    assert not newest.image_evicted, "evict oldest first"


def test_anomaly_frames_are_never_evicted(tmp_path, caplog):
    spool = Spool(tmp_path, max_bytes=10**9)
    anomalies = [_add(spool, Priority.ANOMALY, i) for i in range(3)]
    spool.max_bytes = 1
    spool._enforce_quota()
    for e in anomalies:
        assert (spool.dir / e.image_path).exists()
    assert "only anomaly frames left" in caplog.text


class _OK(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def endpoint():
    httpd = HTTPServer(("127.0.0.1", 0), _OK)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_missing_sidecars_do_not_stop_the_uploader(tmp_path, endpoint):
    """Three entries whose files vanished, queued ahead of a good one."""
    spool = Spool(tmp_path, max_bytes=10**9)
    lost = [_add(spool, Priority.ANOMALY, i) for i in range(3)]
    good = _add(spool, Priority.NORMAL, 9)
    for e in lost:
        (spool.dir / e.meta_path).unlink()
        (spool.dir / e.image_path).unlink()

    result = Uploader(spool, endpoint).upload_pending()
    assert result.succeeded == 1
    assert good.entry_id in result.uploaded_ids
    assert result.failed == 0
    # And they are not retried on the next pass.
    assert spool.pending() == []


def test_full_mode_uploads_metadata_for_an_image_evicted_frame(tmp_path, endpoint):
    spool = Spool(tmp_path, max_bytes=10**9)
    entry = _add(spool, Priority.NORMAL, 1)
    _add(spool, Priority.NORMAL, 2)
    spool.max_bytes = int(spool.total_bytes() * 0.6)
    spool._enforce_quota()
    result = Uploader(spool, endpoint, mode="full").upload_pending()
    assert entry.entry_id in result.uploaded_ids
    assert result.failed == 0
