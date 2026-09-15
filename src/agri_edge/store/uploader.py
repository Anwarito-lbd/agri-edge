"""Store-and-forward uploader: move spooled frames to the farm backend.

The spool was write-only until now -- `upload_endpoint` was configured and never
read. This closes that loop.

DESIGN CONSTRAINTS, AND WHY
---------------------------
**Standard library only.** No `requests`. The Pi runtime installs with numpy and
PyYAML alone (`tests/test_runtime_deps.py` enforces it), and an uploader is not
worth widening that boundary for. `urllib.request` does everything needed.

**Metadata-first by default.** A spooled frame is an image (megabytes) plus a
JSON sidecar carrying telemetry, QA results, vegetation-index summaries and
detections (a few kilobytes). On a rural link the sidecar is the part that
carries the decision-relevant information, and it costs roughly a thousandth of
the bandwidth. Uploading metadata for every frame and images only for the ones
that matter is what makes the link usable at all. `mode="full"` sends images too,
for when you are parked on wifi.

**Never blocks flight.** Upload failures are normal, not exceptional -- the
aircraft is often out of coverage by design. Every failure is counted and
reported, nothing raises into the capture loop, and anything not confirmed
uploaded stays in the spool for the next attempt.

**Confirm before forgetting.** An entry is marked uploaded only after the server
returns 2xx. A crash mid-upload re-sends rather than loses.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .spool import Spool, SpoolEntry

log = logging.getLogger("agri_edge.uploader")


@dataclass
class UploadResult:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    bytes_sent: int = 0
    errors: list[str] = field(default_factory=list)
    uploaded_ids: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return self.failed == 0

    def as_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "bytes_sent": self.bytes_sent,
            # Errors repeat heavily when the link is down; a few are diagnostic,
            # a thousand are a log flood.
            "errors": self.errors[:5],
        }


def encode_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    """Build a multipart/form-data body. Returns `(body, content_type)`.

    Hand-rolled because the stdlib has no multipart encoder and pulling in
    `requests` for this would breach the runtime's dependency boundary.
    """
    boundary = f"----agri-edge-{uuid.uuid4().hex}"
    parts: list[bytes] = []

    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode()
        )

    for name, (filename, payload) in files.items():
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode()
        )
        parts.append(payload)
        parts.append(b"\r\n")

    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class Uploader:
    """Sends spooled frames to an HTTP endpoint, highest priority first."""

    def __init__(
        self,
        spool: Spool,
        endpoint: str,
        mode: str = "metadata",
        timeout_s: float = 20.0,
        api_key: str | None = None,
        purge_after_upload: bool = False,
    ):
        if mode not in ("metadata", "full"):
            raise ValueError(f"mode must be 'metadata' or 'full', got {mode!r}")
        self.spool = spool
        self.endpoint = endpoint.rstrip("/")
        self.mode = mode
        self.timeout_s = timeout_s
        self.api_key = api_key
        self.purge_after_upload = purge_after_upload

    # -- one entry -------------------------------------------------------------

    def _post(self, entry: SpoolEntry) -> int:
        """Upload one entry. Returns bytes sent. Raises on failure."""
        meta_path = self.spool.dir / entry.meta_path
        metadata = meta_path.read_text(encoding="utf-8")

        fields = {
            "entry_id": entry.entry_id,
            "site": entry.site,
            "field_id": entry.field_id,
            "sequence": str(entry.sequence),
            "priority": str(entry.priority),
            "captured_at": str(entry.created_at),
            "mode": self.mode,
        }
        files: dict[str, tuple[str, bytes]] = {
            "metadata": (f"{entry.entry_id}.json", metadata.encode("utf-8"))
        }

        if self.mode == "full":
            img_path = self.spool.dir / entry.image_path
            if img_path.exists():
                files["image"] = (img_path.name, img_path.read_bytes())
            else:
                # Payload already purged; the sidecar is still worth sending.
                log.warning("Image %s missing; sending metadata only.", img_path.name)

        body, content_type = encode_multipart(fields, files)
        req = urllib.request.Request(
            f"{self.endpoint}/frames",
            data=body,
            method="POST",
            headers={"Content-Type": content_type, "User-Agent": "agri-edge/0.1"},
        )
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            if not (200 <= resp.status < 300):
                raise urllib.error.HTTPError(
                    req.full_url, resp.status, "unexpected status", resp.headers, None
                )
        return len(body)

    # -- batch -----------------------------------------------------------------

    def upload_pending(self, limit: int | None = None, stop_after_failures: int = 3) -> UploadResult:
        """Upload pending entries, highest priority first.

        `stop_after_failures` exists because consecutive failures almost always
        mean the link is down, not that individual frames are bad. Continuing to
        retry 4,000 frames against a dead connection wastes battery and fills the
        log; better to give up quickly and try again at the next opportunity.
        """
        result = UploadResult()
        pending = self.spool.pending()
        if limit is not None:
            pending = pending[:limit]

        consecutive_failures = 0
        for entry in pending:
            result.attempted += 1
            try:
                sent = self._post(entry)
            except Exception as exc:     # noqa: BLE001 - any failure is just "not now"
                result.failed += 1
                result.errors.append(f"{entry.entry_id}: {type(exc).__name__}: {exc}")
                consecutive_failures += 1
                if consecutive_failures >= stop_after_failures:
                    log.warning(
                        "%d consecutive upload failures; assuming the link is down "
                        "and stopping. %d entries remain spooled.",
                        consecutive_failures, len(pending) - result.attempted,
                    )
                    break
                continue

            consecutive_failures = 0
            result.succeeded += 1
            result.bytes_sent += sent
            result.uploaded_ids.append(entry.entry_id)

        # Mark in one batch: a single index rewrite rather than one per frame.
        if result.uploaded_ids:
            self.spool.mark_uploaded(result.uploaded_ids)
            if self.purge_after_upload:
                self.spool.purge_uploaded()

        return result

    def upload_forever(self, interval_s: float = 60.0, limit_per_pass: int = 50) -> None:
        """Poll the spool and upload opportunistically. Runs until interrupted.

        Intended for a separate process or thread, never the capture loop --
        capture must not stall waiting on a network that is usually absent.
        """
        while True:
            try:
                result = self.upload_pending(limit=limit_per_pass)
                if result.attempted:
                    log.info(
                        "uploaded %d/%d (%.1f kB)",
                        result.succeeded, result.attempted, result.bytes_sent / 1000,
                    )
            except Exception:
                log.exception("Upload pass failed; continuing.")
            time.sleep(interval_s)


def build_uploader(spool: Spool, cfg, mode: str = "metadata") -> Uploader | None:
    """Construct an uploader, or None when no endpoint is configured.

    Offline is the normal case, not an error -- returning None lets the caller
    treat "no endpoint" and "link down" the same way.
    """
    endpoint = getattr(cfg, "upload_endpoint", None)
    if not endpoint:
        return None
    return Uploader(
        spool,
        endpoint,
        mode=mode,
        timeout_s=getattr(cfg, "upload_timeout_s", 20.0),
        api_key=getattr(cfg, "upload_api_key", None),
    )
