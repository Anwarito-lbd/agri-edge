/**
 * Logins, sessions, and the proxy's write rules (24 Sept 2026).
 *
 * The ops API now has users and roles (agri_edge/ops/auth.py). This app keeps
 * the session in an httpOnly cookie and forwards it upstream as a bearer
 * token; the ops API decides what the person may do and audits it under their
 * name. The proxy's own job shrinks to: JSON only, same origin only, never a
 * vehicle path, and only routes a person should reach.
 */

import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST as loginPost } from "@/app/api/auth/login/route";
import { POST as logoutPost } from "@/app/api/auth/logout/route";
import { GET as opsGet, POST as opsPost } from "@/app/api/ops/[...path]/route";
import { checkProxy, checkWriteRequest, MUTATING_OPS_PATHS } from "@/lib/ops-proxy-policy";

const BASE = "http://localhost:3000";
const TOKEN = "v1.eyJ1IjoiYWRhIn0.c2lnbmF0dXJl";
const none = {} as unknown as NodeJS.ProcessEnv;

function nextReq(path: string, init?: RequestInit & { cookie?: string }) {
  const headers = new Headers(init?.headers);
  if (init?.cookie) headers.set("cookie", init.cookie);
  return new NextRequest(`${BASE}${path}`, { ...init, headers } as never);
}

const ctx = (params: { path: string[] }) => ({ params: Promise.resolve(params) });
const json = { "Content-Type": "application/json" };

/**
 * Copied from agri_edge/ops/auth.py POST_ROLES (the ops API's POST routes).
 * When the backend gains or loses a route, update this list; the tests below
 * then say whether the proxy should follow.
 */
const UPSTREAM_POST_ROUTES = [
  "alerts/ack", "alerts/resolve", "alerts/escalate", "notes", "scouts", "manual", "cameras",
  "map/layers/toggle", "satellite/refresh", "odm/submit", "mapfield/create", "mapfield/validate",
  "irrigation/recommend", "gateway/enqueue", "gateway/sync", "fields", "prescriptions",
  "prescriptions/*/approve", "vra/approve", "mapfield/approve", "mapfield/execute",
  "command/confirm", "ingest", "detections", "seed", "auth/users",
];

describe("the write allowlist and the ops API agree", () => {
  it("every allowlisted write is a real upstream route", () => {
    for (const p of MUTATING_OPS_PATHS) expect(UPSTREAM_POST_ROUTES, p).toContain(p);
  });

  it.each(["seed", "detections", "ingest", "auth/users"])(
    "%s is never reachable through the app, even with writes enabled",
    (p) => {
      const v = checkProxy(p.split("/"), "POST", { OPS_ALLOW_WRITES: "1" } as never, { hasSession: true });
      expect(v.allowed).toBe(false);
    },
  );

  it("an approve route with an id matches the wildcard entry", () => {
    expect(checkProxy(["prescriptions", "rx_42", "approve"], "POST", none, { hasSession: true }).allowed).toBe(true);
    expect(checkProxy(["prescriptions", "rx_42", "delete"], "POST", none, { hasSession: true }).allowed).toBe(false);
  });

  it("a session is what enables writes; without one they stay off", () => {
    expect(checkProxy(["alerts", "ack"], "POST", none, { hasSession: true }).allowed).toBe(true);
    const v = checkProxy(["alerts", "ack"], "POST", none, {});
    expect(v.allowed).toBe(false);
    if (!v.allowed) expect(v.error).toBe("writes_disabled");
  });
});

describe("vehicle paths are refused wherever the word appears", () => {
  it.each([["x", "arm"], ["vehicle", "takeoff"], ["a", "mission", "start"], ["pump"]])(
    "%s",
    (...segs) => {
      const v = checkProxy(segs, "GET", none, { hasSession: true });
      expect(v.allowed).toBe(false);
      if (!v.allowed) expect(v.error).toBe("forbidden_op");
    },
  );

  it("but a word that merely contains one is fine (farm is not arm)", () => {
    expect(checkProxy(["farm", "overview"], "GET", none).allowed).toBe(true);
  });
});

describe("write requests must be same-origin JSON", () => {
  const url = `${BASE}/api/ops/alerts/ack`;

  it.each(["text/plain", "application/x-www-form-urlencoded", ""])("%s is refused", (ct) => {
    const v = checkWriteRequest("POST", new Headers(ct ? { "content-type": ct } : {}), url);
    expect(v.allowed).toBe(false);
    if (!v.allowed) expect(v.status).toBe(415);
  });

  it("a foreign Origin is refused", () => {
    const v = checkWriteRequest("POST", new Headers({ ...json, origin: "https://evil.example" }), url);
    expect(v.allowed).toBe(false);
    if (!v.allowed) expect(v.status).toBe(403);
  });

  it("same origin passes", () => {
    expect(checkWriteRequest("POST", new Headers({ ...json, origin: BASE }), url).allowed).toBe(true);
  });

  it("same origin passes when the server's own URL names a different host (next start, reverse proxy)", () => {
    const own = "http://localhost:3000/api/ops/alerts/ack";
    const lan = new Headers({ ...json, origin: "http://192.168.1.20:3000", host: "192.168.1.20:3000" });
    expect(checkWriteRequest("POST", lan, own).allowed).toBe(true);
    const proxied = new Headers({ ...json, origin: "https://farm.example", host: "localhost:3000", "x-forwarded-host": "farm.example" });
    expect(checkWriteRequest("POST", proxied, own).allowed).toBe(true);
    const foreign = new Headers({ ...json, origin: "https://evil.example", host: "192.168.1.20:3000" });
    expect(checkWriteRequest("POST", foreign, own).allowed).toBe(false);
  });
});

describe("the proxy forwards the session, and only the session", () => {
  const realFetch = globalThis.fetch;
  let seen: Headers | undefined;

  beforeEach(() => {
    seen = undefined;
    globalThis.fetch = vi.fn(async (_url: unknown, init?: RequestInit) => {
      seen = new Headers(init?.headers);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }) as unknown as typeof fetch;
  });
  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it("sends the cookie's token upstream as a bearer token", async () => {
    await opsGet(nextReq("/api/ops/overview", { cookie: `ae_session=${TOKEN}` }), ctx({ path: ["overview"] }));
    expect(seen?.get("authorization")).toBe(`Bearer ${TOKEN}`);
  });

  it("sends nothing without a session, and nothing for a malformed cookie", async () => {
    await opsGet(nextReq("/api/ops/overview"), ctx({ path: ["overview"] }));
    expect(seen?.get("authorization")).toBeNull();
    await opsGet(nextReq("/api/ops/overview", { cookie: "ae_session=<script>" }), ctx({ path: ["overview"] }));
    expect(seen?.get("authorization")).toBeNull();
  });

  it("lets a logged-in write through and keeps the upstream's 403", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ error: "operator may not POST" }), { status: 403 }),
    ) as unknown as typeof fetch;
    const res = await opsPost(
      nextReq("/api/ops/vra/approve", { method: "POST", body: "{}", headers: json, cookie: `ae_session=${TOKEN}` }),
      ctx({ path: ["vra", "approve"] }),
    );
    expect(res.status).toBe(403);
    expect(res.headers.get("X-Ops-Proxy")).toBe("1");
  });

  it("passes a prescription zip through as bytes", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(new Uint8Array([0x50, 0x4b, 3, 4]), {
        status: 200,
        headers: { "content-type": "application/zip", "content-disposition": 'attachment; filename="rx.zip"' },
      }),
    ) as unknown as typeof fetch;
    const res = await opsGet(
      nextReq("/api/ops/prescriptions/rx_1/export?format=isoxml", { cookie: `ae_session=${TOKEN}` }),
      ctx({ path: ["prescriptions", "rx_1", "export"] }),
    );
    expect(res.headers.get("content-type")).toBe("application/zip");
    expect(new Uint8Array(await res.arrayBuffer())[0]).toBe(0x50);
  });
});

describe("login and logout", () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it("keeps the token in an httpOnly, SameSite=Strict cookie and never in the body", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ token: TOKEN, expires: Date.now() / 1000 + 3600,
                                    user: { username: "ada", role: "admin" } }), { status: 200 }),
    ) as unknown as typeof fetch;
    const res = await loginPost(nextReq("/api/auth/login", {
      method: "POST", headers: json, body: JSON.stringify({ username: "ada", password: "x".repeat(12) }),
    }));
    expect(res.status).toBe(200);
    const cookie = res.headers.get("set-cookie") || "";
    expect(cookie).toContain(`ae_session=${TOKEN}`);
    expect(cookie.toLowerCase()).toContain("httponly");
    expect(cookie.toLowerCase()).toContain("samesite=strict");
    const body = await res.json();
    expect(JSON.stringify(body)).not.toContain(TOKEN);
    expect(body.user.username).toBe("ada");
  });

  it("a wrong password sets no cookie", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ error: "wrong username or password" }), { status: 401 }),
    ) as unknown as typeof fetch;
    const res = await loginPost(nextReq("/api/auth/login", {
      method: "POST", headers: json, body: JSON.stringify({ username: "ada", password: "nope" }),
    }));
    expect(res.status).toBe(401);
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  it("a cross-site form post to login is refused before reaching upstream", async () => {
    const spy = vi.fn();
    globalThis.fetch = spy as unknown as typeof fetch;
    const res = await loginPost(nextReq("/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: "username=a",
    }));
    expect(res.status).toBe(415);
    expect(spy).not.toHaveBeenCalled();
  });

  it("logout clears the cookie", async () => {
    const res = await logoutPost(nextReq("/api/auth/logout", { method: "POST", headers: json, body: "{}" }));
    expect(res.headers.get("set-cookie")).toMatch(/ae_session=;.*Max-Age=0/i);
  });
});
