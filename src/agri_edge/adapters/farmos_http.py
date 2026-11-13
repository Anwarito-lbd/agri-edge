"""Real HTTP client for farmOS 2.x/3.x/4.x JSON:API (standard library only).

STATUS: IMPLEMENTED, tested against a LOCAL MOCK server only (`tests/test_farmos_http.py`).
It has NEVER talked to a real farmOS instance, so request/response shapes follow the
public farmOS docs (https://farmos.org/development/api/ and .../api/authentication/)
and are UNVERIFIED against a live server. Nothing here is VALIDATED.

NETWORK GATE
------------
This module is imported only by `FarmOSAdapter.from_config(..., allow_network=True)`.
`FarmOSAdapter` itself refuses to call the client unless it was constructed with
`allow_network=True`, so importing or constructing this client does not send anything:
the first request happens on `authenticate()` / a read / a write.

WHAT IT DOES
------------
* OAuth2 token: `password` grant (the farmOS default client `farm`, legacy but what the
  existing `store.farmos.FarmOSClient` uses) or `client_credentials` (preferred by the
  farmOS docs; used when a client secret is set and no username is). Refreshes with the
  `refresh_token` grant, and re-authenticates once on a 401.
* WRITE: `create_log(payload)` POSTs a `log--observation` / `log--activity` document to
  `/api/log/<bundle>`.
* READ: `list_land_assets()` -> `/api/asset/land` ("fields"), `list_plant_assets()` ->
  `/api/asset/plant` ("plantings"), following JSON:API `links.next` pagination.

SAFETY / HYGIENE
----------------
* The bearer token is only ever sent to the configured origin. A `links.next` pointing
  anywhere else is refused (`FarmOSError`), and redirects are not followed -- a hostile
  or misconfigured server cannot bounce the token to another host.
* Only http/https URLs are accepted; a hard cap on pages stops a looping `next` link.
* Credentials come from `FarmOSConfig` (environment variables), never from a file; they
  are never logged and never appear in error text.
* Nothing here can reach a vehicle, actuator or MQTT: it is a records client.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from agri_edge.store.farmos import JSONAPI, FarmOSConfig

ADAPTER_STATUS = "IMPLEMENTED (mock-tested; never run against a real farmOS)"
MAX_PAGES = 50
PAGE_LIMIT = 50
# log bundles this client will create; anything else is refused rather than guessed at.
WRITABLE_LOG_BUNDLES = {"log--observation": "observation", "log--activity": "activity"}


class FarmOSError(RuntimeError):
    """Any failure talking to farmOS. Never contains a token or password."""


class FarmOSAuthError(FarmOSError):
    pass


@dataclass(frozen=True)
class FarmOSField:
    """A farmOS land asset (what a grower calls a field)."""

    id: str
    name: str
    status: str = ""
    land_type: str = ""
    geometry_wkt: str = ""


@dataclass(frozen=True)
class FarmOSPlanting:
    """A farmOS plant asset (a planting / crop planting)."""

    id: str
    name: str
    status: str = ""
    plant_type_ids: tuple[str, ...] = ()
    location_ids: tuple[str, ...] = ()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a: Any, **k: Any) -> None:     # noqa: D401
        return None


@dataclass
class FarmOSHttpClient:
    cfg: FarmOSConfig
    timeout_s: float = 0.0
    _token: Optional[str] = field(default=None, repr=False)
    _refresh: Optional[str] = field(default=None, repr=False)
    _expires_at: float = 0.0

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlparse(self.cfg.url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("farmOS url must be an absolute http(s) URL")
        self.base = self.cfg.url.rstrip("/")
        self._origin = (parsed.scheme, parsed.netloc)
        if not self.timeout_s:
            self.timeout_s = float(self.cfg.timeout_s)
        use_cc = bool(self.cfg.client_secret) and not self.cfg.username
        if not use_cc:
            missing = [m for m in self.cfg.missing_credentials() if m != "url"]
            if missing:
                raise ValueError("farmOS is not configured: missing " + ", ".join(missing))
        elif not self.cfg.client_id:
            raise ValueError("farmOS is not configured: missing FARMOS_CLIENT_ID")
        self._opener = urllib.request.build_opener(_NoRedirect)

    # -- plumbing ----------------------------------------------------------------
    def _same_origin(self, url: str) -> bool:
        p = urllib.parse.urlparse(url)
        return (p.scheme, p.netloc) == self._origin

    def _open(self, req: urllib.request.Request) -> tuple[int, bytes]:
        try:
            with self._opener.open(req, timeout=self.timeout_s) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except urllib.error.URLError as e:
            raise FarmOSError(f"farmOS unreachable: {e.reason}") from None
        except (TimeoutError, OSError) as e:
            raise FarmOSError(f"farmOS request failed: {type(e).__name__}") from None

    def _token_request(self, form: dict[str, str]) -> None:
        req = urllib.request.Request(
            f"{self.base}/oauth/token",
            data=urllib.parse.urlencode(form).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json", "User-Agent": "agri-edge/0.1"})
        status, raw = self._open(req)
        if status != 200:
            raise FarmOSAuthError(f"farmOS token endpoint returned HTTP {status}")
        try:
            body = json.loads(raw.decode("utf-8"))
            token = body["access_token"]
        except (ValueError, KeyError, TypeError):
            raise FarmOSAuthError("farmOS token response had no access_token") from None
        if not isinstance(token, str) or not token:
            raise FarmOSAuthError("farmOS token response had an empty access_token")
        try:
            ttl = float(body.get("expires_in", 300))      # farmOS sends it as a string
        except (TypeError, ValueError):
            ttl = 300.0
        self._token = token
        rt = body.get("refresh_token")
        self._refresh = rt if isinstance(rt, str) and rt else None
        self._expires_at = time.time() + max(0.0, ttl)

    def authenticate(self) -> None:
        if self.cfg.client_secret and not self.cfg.username:
            form = {"grant_type": "client_credentials", "client_id": self.cfg.client_id,
                    "client_secret": self.cfg.client_secret, "scope": "farm_manager"}
        else:
            form = {"grant_type": "password", "username": self.cfg.username,
                    "password": self.cfg.password, "client_id": self.cfg.client_id,
                    "scope": "farm_manager"}
            if self.cfg.client_secret:
                form["client_secret"] = self.cfg.client_secret
        self._token_request(form)

    def _refresh_or_reauth(self) -> None:
        if self._refresh:
            form = {"grant_type": "refresh_token", "refresh_token": self._refresh,
                    "client_id": self.cfg.client_id}
            if self.cfg.client_secret:
                form["client_secret"] = self.cfg.client_secret
            try:
                self._token_request(form)
                return
            except FarmOSAuthError:
                pass                                         # fall through to a full login
        self.authenticate()

    def _ensure_token(self) -> None:
        if not self._token:
            self.authenticate()
        elif time.time() >= self._expires_at - 5:
            self._refresh_or_reauth()

    def _request(self, method: str, url: str, payload: Optional[dict] = None) -> dict:
        if not self._same_origin(url):
            raise FarmOSError("refusing to send credentials to a different origin")
        self._ensure_token()
        for attempt in (0, 1):
            data = json.dumps(payload).encode("utf-8") if payload is not None else None
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Accept": JSONAPI, "Content-Type": JSONAPI,
                "Authorization": f"Bearer {self._token}", "User-Agent": "agri-edge/0.1"})
            status, raw = self._open(req)
            if status == 401 and attempt == 0:
                self._refresh_or_reauth()                    # expired mid-flight: once only
                continue
            break
        if status in (401, 403):
            raise FarmOSAuthError(f"farmOS refused the request (HTTP {status})")
        if not 200 <= status < 300:
            raise FarmOSError(f"farmOS returned HTTP {status} for {method} {urllib.parse.urlparse(url).path}")
        try:
            doc = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            raise FarmOSError("farmOS returned a non-JSON body") from None
        if not isinstance(doc, dict):
            raise FarmOSError("farmOS returned an unexpected JSON document")
        return doc

    # -- writes --------------------------------------------------------------------
    def create_log(self, payload: dict) -> str:
        """POST one log document. Returns the new farmOS UUID."""
        t = ((payload or {}).get("data") or {}).get("type")
        bundle = WRITABLE_LOG_BUNDLES.get(t) if isinstance(t, str) else None
        if bundle is None:
            raise FarmOSError(f"refusing to create unsupported resource type {t!r}")
        doc = self._request("POST", f"{self.base}/api/log/{bundle}", payload)
        new_id = (doc.get("data") or {}).get("id")
        if not isinstance(new_id, str) or not new_id:
            raise FarmOSError("farmOS accepted the log but returned no id")
        return new_id

    # -- reads ---------------------------------------------------------------------
    def _paged(self, path: str) -> list[dict]:
        url: Optional[str] = (f"{self.base}{path}?"
                              + urllib.parse.urlencode({"page[limit]": PAGE_LIMIT}))
        out: list[dict] = []
        for _ in range(MAX_PAGES):
            if not url:
                return out
            doc = self._request("GET", url)
            out.extend(r for r in (doc.get("data") or []) if isinstance(r, dict))
            nxt = (doc.get("links") or {}).get("next")
            url = nxt.get("href") if isinstance(nxt, dict) else nxt
            if url is not None and not isinstance(url, str):
                raise FarmOSError("malformed pagination link")
        raise FarmOSError(f"more than {MAX_PAGES} pages; refusing to keep paging")

    def list_land_assets(self) -> list[FarmOSField]:
        out = []
        for r in self._paged("/api/asset/land"):
            a = r.get("attributes") or {}
            geom = a.get("intrinsic_geometry") or {}
            out.append(FarmOSField(
                id=str(r.get("id", "")), name=str(a.get("name", "")),
                status=str(a.get("status", "")), land_type=str(a.get("land_type", "")),
                geometry_wkt=str(geom.get("value", "")) if isinstance(geom, dict) else ""))
        return out

    def list_plant_assets(self) -> list[FarmOSPlanting]:
        def ids(rel: Any) -> tuple[str, ...]:
            d = (rel or {}).get("data") if isinstance(rel, dict) else None
            items = d if isinstance(d, list) else ([d] if isinstance(d, dict) else [])
            return tuple(str(i.get("id", "")) for i in items if isinstance(i, dict))

        out = []
        for r in self._paged("/api/asset/plant"):
            a = r.get("attributes") or {}
            rels = r.get("relationships") or {}
            out.append(FarmOSPlanting(
                id=str(r.get("id", "")), name=str(a.get("name", "")),
                status=str(a.get("status", "")),
                plant_type_ids=ids(rels.get("plant_type")),
                location_ids=ids(rels.get("location"))))
        return out
