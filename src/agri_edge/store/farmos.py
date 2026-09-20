"""Push spooled frames into farmOS as observation logs.

WHY
---
`store/uploader.py` POSTs to a generic `<endpoint>/frames` that nothing on the
other end implements. farmOS (https://farmos.org, GPL-2.0) is a real farm record
system with a real data model — assets, land areas, logs, quantities — so a
flight stops being a folder of `.npy` files and becomes something an agronomist
can actually look up next season.

LICENCE BOUNDARY
----------------
farmOS is GPL-2.0 and is run **unmodified**, as a separate server, reached over
HTTP. None of its code is linked here; this module speaks JSON:API to it exactly
as a browser would. Using GPL software creates no obligation — distributing it
does, and we do not distribute it. See NOTICE.md.

DEPENDENCIES
------------
Standard library only, matching `uploader.py`. farmOS speaks JSON:API over HTTP
and `urllib` is entirely capable of that, so the Pi runtime keeps installing with
numpy + PyYAML alone and `tests/test_runtime_deps.py` keeps passing.

CREDENTIALS
-----------
**Read from the environment, never from config and never from git.** farmOS uses
OAuth2; a client secret committed to a repository is the single most likely way
this project leaks something that matters. `FarmOSConfig.from_env` is the only
constructor that takes secrets, and it takes them from `FARMOS_USERNAME`,
`FARMOS_PASSWORD` and `FARMOS_CLIENT_SECRET`.

WHAT IS SENT
------------
The sidecar, not the image. A flight produces gigabytes of frames and kilobytes
of decisions, and the decisions are the part a farm record needs. Images stay in
the spool for the workstation to collect.

Every log carries the model provenance and `may_drive_treatment`, so the record
itself says whether a detection was ever allowed to influence a treatment.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .spool import Spool

log = logging.getLogger("agri_edge.store.farmos")

JSONAPI = "application/vnd.api+json"


@dataclass
class FarmOSConfig:
    """Connection settings. Secrets come from the environment, not from YAML."""

    url: str = ""
    username: str = ""
    password: str = ""
    client_id: str = "farm"
    client_secret: str = ""
    timeout_s: float = 20.0
    # farmOS land asset this flight belongs to. Optional: without it the logs are
    # still created, just not attached to a field.
    land_asset_id: str = ""

    @classmethod
    def from_env(cls, url: str, land_asset_id: str = "", **kw) -> "FarmOSConfig":
        """Build from environment variables, which is the only supported path.

        Deliberately not read from `config/*.yaml`: those files are committed, and
        an OAuth client secret in git is not recoverable by rotating one key.
        """
        return cls(
            url=url,
            username=os.environ.get("FARMOS_USERNAME", ""),
            password=os.environ.get("FARMOS_PASSWORD", ""),
            client_id=os.environ.get("FARMOS_CLIENT_ID", "farm"),
            client_secret=os.environ.get("FARMOS_CLIENT_SECRET", ""),
            land_asset_id=land_asset_id,
            **kw,
        )

    def missing_credentials(self) -> list[str]:
        missing = []
        if not self.url:
            missing.append("url")
        if not self.username:
            missing.append("FARMOS_USERNAME")
        if not self.password:
            missing.append("FARMOS_PASSWORD")
        return missing


@dataclass
class FarmOSResult:
    attempted: int = 0
    created: int = 0
    failed: int = 0
    log_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "created": self.created,
            "failed": self.failed,
            "log_ids": self.log_ids,
            "errors": self.errors[:5],
        }


def sidecar_to_log(meta: dict, land_asset_id: str = "") -> dict:
    """Translate one frame sidecar into a farmOS `log--observation` payload.

    Only the decision-bearing parts travel: where the aircraft was, what the
    model said, and crucially whether that was allowed to drive a treatment.

    The notes field is written for a human reading the record in six months, not
    for a machine. `may_drive_treatment` is stated in words rather than left as a
    boolean buried in a payload, because the whole point of the flag is that
    somebody later can tell what the detection was permitted to do.
    """
    telem = meta.get("telemetry", {}) or {}
    model = meta.get("model", {}) or {}
    dets = meta.get("detections", []) or []

    counts: dict[str, int] = {}
    for d in dets:
        counts[d.get("label", "unknown")] = counts.get(d.get("label", "unknown"), 0) + 1

    placed = [d for d in dets if d.get("lat") is not None and d.get("lon") is not None]
    may_treat = any(d.get("may_drive_treatment") for d in dets)
    summary = ", ".join(f"{n} x {lab}" for lab, n in sorted(counts.items())) or "no detections"

    notes = [
        f"agri-edge frame {meta.get('sequence', '?')} at {meta.get('site', '?')}"
        f" / {meta.get('field_id', '?')}",
        f"Detections: {summary}",
        f"Model: {model.get('name', 'none')} v{model.get('version', '?')}",
        (
            "DECISION SUPPORT ONLY - this model is not validated on local imagery, "
            "so nothing here may drive a treatment."
            if not may_treat
            else "Model is marked locally validated; detections may inform treatment."
        ),
    ]
    qa = meta.get("qa", {}) or {}
    if qa.get("passed") is False:
        notes.append("QA: FAILED - this frame is flagged degraded, not discarded.")
    if placed:
        worst = max(d.get("position_error_m") or 0.0 for d in placed)
        notes.append(
            f"Positions: {len(placed)} of {len(dets)} detections georeferenced, "
            f"worst-case +/- {worst:.1f} m from the flat-ground assumption."
        )
    elif dets:
        notes.append("Positions: none -- this log locates the AIRCRAFT, not the findings.")

    attributes: dict[str, Any] = {
        "name": f"Aerial scouting: {summary}",
        "status": "done",
        "notes": {"value": "\n".join(notes), "format": "default"},
        "data": json.dumps(
            {
                "entry": meta.get("entry_id"),
                "sequence": meta.get("sequence"),
                "priority": meta.get("priority"),
                "detections": counts,
                "may_drive_treatment": may_treat,
                "model": model,
                "qa_passed": qa.get("passed"),
                "georeferenced": len(placed),
                # Worst-case positional uncertainty across the placed detections,
                # so the record says how well it knows where these things are.
                "position_error_m": (
                    max(d.get("position_error_m") or 0.0 for d in placed) if placed else None
                ),
            }
        ),
    }
    # Geometry: prefer where the WEEDS are over where the AIRCRAFT was.
    #
    # The aircraft's position answers "where was the drone", which is nearly
    # useless agronomically. Once detections are georeferenced they answer "where
    # is the kochia", which is the thing a farmer acts on. Fall back to the frame
    # position only when no detection has one.
    #
    # farmOS geometry is WKT, and longitude comes FIRST: POINT(x y) is
    # POINT(lon lat). Backwards puts every Prairie observation in Somalia.
    lat, lon = telem.get("lat"), telem.get("lon")
    if placed:
        points = ", ".join(f"({d['lon']} {d['lat']})" for d in placed)
        attributes["geometry"] = {"value": f"MULTIPOINT({points})"}
    elif lat is not None and lon is not None:
        attributes["geometry"] = {"value": f"POINT({lon} {lat})"}

    payload: dict[str, Any] = {
        "data": {"type": "log--observation", "attributes": attributes}
    }
    if land_asset_id:
        payload["data"]["relationships"] = {
            "location": {"data": [{"type": "asset--land", "id": land_asset_id}]}
        }
    return payload


class FarmOSClient:
    """Minimal JSON:API client: authenticate, then create observation logs."""

    def __init__(self, cfg: FarmOSConfig):
        missing = cfg.missing_credentials()
        if missing:
            raise ValueError(
                "farmOS is not configured: missing " + ", ".join(missing) + ". "
                "Credentials come from the environment (FARMOS_USERNAME, "
                "FARMOS_PASSWORD, FARMOS_CLIENT_SECRET), never from a config file."
            )
        self.cfg = cfg
        self.base = cfg.url.rstrip("/")
        self._token: str | None = None

    # -- auth ---------------------------------------------------------------

    def authenticate(self) -> None:
        """OAuth2 password grant, which is what farmOS exposes for scripts."""
        data = {
            "grant_type": "password",
            "username": self.cfg.username,
            "password": self.cfg.password,
            "client_id": self.cfg.client_id,
            "scope": "farm_manager",
        }
        if self.cfg.client_secret:
            data["client_secret"] = self.cfg.client_secret

        req = urllib.request.Request(
            f"{self.base}/oauth/token",
            data=urllib.parse.urlencode(data).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "agri-edge/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        token = body.get("access_token")
        if not token:
            raise RuntimeError("farmOS returned no access_token.")
        self._token = token

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise RuntimeError("Call authenticate() before sending anything.")
        return {
            "Content-Type": JSONAPI,
            "Accept": JSONAPI,
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "agri-edge/0.1",
        }

    # -- writes --------------------------------------------------------------

    def create_log(self, payload: dict) -> str:
        req = urllib.request.Request(
            f"{self.base}/api/log/observation",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers=self._headers(),
        )
        with urllib.request.urlopen(req, timeout=self.cfg.timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return str(body.get("data", {}).get("id", ""))


def push_spool(
    spool: Spool,
    cfg: FarmOSConfig,
    limit: int | None = None,
    stop_after_failures: int = 3,
) -> FarmOSResult:
    """Send pending sidecars to farmOS, highest priority first.

    Mirrors `Uploader.upload_pending`, including giving up after a few
    consecutive failures: consecutive failures nearly always mean the link or the
    server is down rather than that individual frames are bad, and retrying
    thousands of frames against a dead endpoint wastes battery and fills the log.
    """
    result = FarmOSResult()
    client = FarmOSClient(cfg)
    try:
        client.authenticate()
    except Exception as exc:
        result.errors.append(f"authentication failed: {exc}")
        return result

    entries = spool.pending()
    if limit is not None:
        entries = entries[:limit]
    consecutive = 0
    for entry in entries:
        result.attempted += 1
        try:
            meta = json.loads((spool.dir / entry.meta_path).read_text(encoding="utf-8"))
            log_id = client.create_log(sidecar_to_log(meta, cfg.land_asset_id))
            result.created += 1
            result.log_ids.append(log_id)
            consecutive = 0
        except Exception as exc:
            result.failed += 1
            result.errors.append(f"{entry.entry_id}: {exc}")
            consecutive += 1
            if consecutive >= stop_after_failures:
                log.warning(
                    "farmOS: %d consecutive failures, stopping. The link or the "
                    "server is probably down.", consecutive,
                )
                break
    return result
