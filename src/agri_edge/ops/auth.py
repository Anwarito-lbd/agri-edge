"""Users, roles and sessions for the ops station.

WHY
---
Until now the audit log recorded whatever `actor` string the client sent, so
"who approved this prescription" had no answer. Here a person logs in, gets a
signed session, and every write is checked against their role and audited
under their name -- the body's `actor`/`by` is ignored once someone is
logged in.

MODES
-----
* **No users yet** (a fresh install): the station behaves as before -- open on
  loopback, optional OPS_API_TOKEN for writes. Create the first admin with
  `python -m agri_edge.ops.auth add-user NAME --role admin --db data/ops.sqlite`.
* **Any user exists**: every API call needs a session (cookie `ae_session` or
  `Authorization: Bearer <token>`), except login itself. OPS_API_TOKEN then
  means a *service* identity (the aircraft, the LoRa bridge) that may only
  ingest.

ROLES (ops/types.Role)
----------------------
viewer < operator < agronomist < admin. `auditor` reads like a viewer and may
also read the audit log. Route permissions: `POST_ROLES` below.

Passwords: PBKDF2-HMAC-SHA256, 200 000 iterations, per-user salt. Sessions:
HMAC-SHA256-signed, 12 h, invalidated on password change or disable (the
user's token version is part of the signature). Five failed logins lock a
username for a minute.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Optional

from .store import OpsStore
from .types import Role

ITERATIONS = 200_000
SESSION_S = 12 * 3600
RANK = {Role.VIEWER: 0, Role.AUDITOR: 0, Role.OPERATOR: 1, Role.AGRONOMIST: 2, Role.ADMIN: 3}

# Minimum role for each POST route; anything unlisted needs admin.
POST_ROLES: dict[str, Role] = {
    "/api/ops/alerts/ack": Role.OPERATOR, "/api/ops/alerts/resolve": Role.OPERATOR,
    "/api/ops/alerts/escalate": Role.OPERATOR, "/api/ops/notes": Role.OPERATOR,
    "/api/ops/scouts": Role.OPERATOR, "/api/ops/manual": Role.OPERATOR,
    "/api/ops/cameras": Role.OPERATOR, "/api/ops/map/layers/toggle": Role.OPERATOR,
    "/api/ops/satellite/refresh": Role.OPERATOR, "/api/ops/odm/submit": Role.OPERATOR,
    "/api/ops/mapfield/create": Role.OPERATOR, "/api/ops/mapfield/validate": Role.OPERATOR,
    "/api/ops/irrigation/recommend": Role.OPERATOR, "/api/ops/gateway/enqueue": Role.OPERATOR,
    "/api/ops/gateway/sync": Role.OPERATOR,
    "/api/ops/fields": Role.AGRONOMIST, "/api/ops/prescriptions": Role.AGRONOMIST,
    "/api/ops/prescriptions/*/approve": Role.AGRONOMIST, "/api/ops/vra/approve": Role.AGRONOMIST,
    "/api/ops/mapfield/approve": Role.AGRONOMIST, "/api/ops/mapfield/execute": Role.AGRONOMIST,
    "/api/ops/command/confirm": Role.AGRONOMIST,
    "/api/ops/ingest": Role.ADMIN, "/api/ops/detections": Role.ADMIN, "/api/ops/seed": Role.ADMIN,
    "/api/ops/auth/users": Role.ADMIN,
}
GET_ROLES: dict[str, set[Role]] = {"/api/ops/audit": {Role.ADMIN, Role.AUDITOR}}
SERVICE_POSTS = {"/api/ops/ingest"}
PUBLIC = {"/api/ops/auth/login", "/api/ops/auth/logout"}


@dataclass
class Principal:
    name: str
    role: str                  # a Role value, or "service", or "dev"
    kind: str                  # user | service | dev

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _route_key(path: str) -> str:
    if path.startswith("/api/ops/prescriptions/") and path.endswith("/approve"):
        return "/api/ops/prescriptions/*/approve"
    return path


def may(principal: Principal, method: str, path: str) -> bool:
    if principal.kind == "dev":
        return True
    if principal.kind == "service":
        return method == "POST" and path in SERVICE_POSTS
    role = Role(principal.role)
    if method == "GET":
        allowed = GET_ROLES.get(path)
        return allowed is None or role in allowed
    need = POST_ROLES.get(_route_key(path), Role.ADMIN)
    return RANK[role] >= RANK[need]


# -- storage -------------------------------------------------------------------


_mem_lock = threading.Lock()


def _db(store: OpsStore) -> Optional[sqlite3.Connection]:
    if not store.sqlite_path:
        return None
    con = sqlite3.connect(store.sqlite_path)
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, pw_hash TEXT NOT NULL, role TEXT NOT NULL,
        display_name TEXT, disabled INTEGER NOT NULL DEFAULT 0,
        token_version INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL)""")
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    return con


def _users(store: OpsStore) -> dict[str, dict]:
    if not hasattr(store, "users"):
        store.users = {}  # type: ignore[attr-defined]
        con = _db(store)
        if con is not None:
            try:
                for row in con.execute("SELECT username, pw_hash, role, display_name, disabled, "
                                       "token_version, created FROM users"):
                    store.users[row[0]] = {"username": row[0], "pw_hash": row[1], "role": row[2],  # type: ignore[attr-defined]
                                           "display_name": row[3], "disabled": bool(row[4]),
                                           "token_version": row[5], "created": row[6]}
                con.commit()
            finally:
                con.close()
    return store.users  # type: ignore[attr-defined]


def auth_enabled(store: OpsStore) -> bool:
    return bool(_users(store))


def _save(store: OpsStore, u: dict) -> None:
    _users(store)[u["username"]] = u
    con = _db(store)
    if con is None:
        return
    try:
        con.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,?,?)",
                    (u["username"], u["pw_hash"], u["role"], u.get("display_name"),
                     int(u.get("disabled", False)), u["token_version"], u["created"]))
        con.commit()
    finally:
        con.close()


def hash_password(password: str, *, salt: bytes | None = None, iterations: int | None = None) -> str:
    iterations = iterations or ITERATIONS
    salt = salt if salt is not None else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, dk = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.b64decode(salt), int(it))
    return hmac.compare_digest(base64.b64encode(got).decode(), dk)


def add_user(store: OpsStore, username: str, password: str, role: str,
             display_name: str | None = None) -> dict:
    if not username or len(username) > 64 or not username.replace("-", "").replace("_", "").replace(".", "").replace("@", "").isalnum():
        raise ValueError("username: 1-64 letters, digits, - _ . @")
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    Role(role)
    with _mem_lock:
        users = _users(store)
        prev = users.get(username)
        u = {"username": username, "pw_hash": hash_password(password), "role": role,
             "display_name": display_name or username, "disabled": False,
             "token_version": (prev["token_version"] + 1) if prev else 1,
             "created": prev["created"] if prev else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _save(store, u)
    return public(u)


def public(u: dict) -> dict:
    return {k: u[k] for k in ("username", "role", "display_name", "disabled", "created")}


# -- sessions ------------------------------------------------------------------


def _secret(store: OpsStore) -> bytes:
    env = os.environ.get("OPS_SESSION_SECRET")
    if env:
        return env.encode()
    if not hasattr(store, "_session_secret"):
        secret = None
        con = _db(store)
        if con is not None:
            try:
                row = con.execute("SELECT value FROM settings WHERE key='session_secret'").fetchone()
                if row:
                    secret = row[0]
                else:
                    secret = secrets.token_hex(32)
                    con.execute("INSERT INTO settings VALUES ('session_secret', ?)", (secret,))
                    con.commit()
            finally:
                con.close()
        store._session_secret = (secret or secrets.token_hex(32)).encode()  # type: ignore[attr-defined]
    return store._session_secret  # type: ignore[attr-defined]


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue(store: OpsStore, u: dict, now: float | None = None) -> tuple[str, int]:
    exp = int((now or time.time()) + SESSION_S)
    body = _b64(json.dumps({"u": u["username"], "v": u["token_version"], "exp": exp},
                           separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(store), body.encode(), hashlib.sha256).digest())
    return f"v1.{body}.{sig}", exp


def verify(store: OpsStore, token: str, now: float | None = None) -> Optional[Principal]:
    try:
        ver, body, sig = token.split(".")
    except ValueError:
        return None
    if ver != "v1":
        return None
    want = _b64(hmac.new(_secret(store), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(want, sig):
        return None
    try:
        claims = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if claims.get("exp", 0) < (now or time.time()):
        return None
    u = _users(store).get(claims.get("u"))
    if u is None or u.get("disabled") or u["token_version"] != claims.get("v"):
        return None
    return Principal(u["username"], u["role"], "user")


_failures: dict[str, list[float]] = {}


def login(store: OpsStore, username: str, password: str) -> Optional[tuple[str, int, dict]]:
    now = time.time()
    recent = [t for t in _failures.get(username, []) if now - t < 60]
    if len(recent) >= 5:
        raise PermissionError("too many failed attempts; wait a minute")
    u = _users(store).get(username)
    if u is None or u.get("disabled") or not check_password(password, u["pw_hash"]):
        _failures[username] = recent + [now]
        return None
    _failures.pop(username, None)
    token, exp = issue(store, u, now)
    return token, exp, public(u)


def principal_from(store: OpsStore, authorization: str | None, cookie: str | None) -> Optional[Principal]:
    """Resolve the caller. None = unauthenticated (only meaningful when auth is on)."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif cookie:
        for part in cookie.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "ae_session":
                token = v
    if not token:
        return None
    service = os.environ.get("OPS_API_TOKEN")
    if service and hmac.compare_digest(token.encode(), service.encode()):
        return Principal("service", "service", "service")
    return verify(store, token)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import getpass

    from .store import OpsStore as _Store

    ap = argparse.ArgumentParser(prog="python -m agri_edge.ops.auth")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-user", help="create a user, or reset their password (signs them out)")
    a.add_argument("username")
    a.add_argument("--role", required=True, choices=[r.value for r in Role])
    a.add_argument("--display-name")
    a.add_argument("--db", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--db", required=True)
    args = ap.parse_args(argv)
    store = _Store(sqlite_path=args.db)
    if args.cmd == "list":
        for u in _users(store).values():
            print(f"{u['username']:24} {u['role']:11} {'DISABLED' if u['disabled'] else ''}")
        return 0
    pw = getpass.getpass("Password (12+ characters): ")
    if pw != getpass.getpass("Again: "):
        print("passwords differ")
        return 1
    print(add_user(store, args.username, pw, args.role, args.display_name))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
