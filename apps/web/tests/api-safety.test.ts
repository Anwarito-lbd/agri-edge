/**
 * The API routes that touch, or refuse to touch, the aircraft.
 *
 * WHY THESE EXIST
 * ---------------
 * This repository had no tests at all, and the least-covered surface was the
 * one carrying the most authority: `/api/ops/[...path]`, an unauthenticated
 * proxy that forwarded every GET and POST straight to the ops API. That
 * included `POST /api/ops/vra/approve` -- the human-in-the-loop gate that
 * authorises a variable-rate prescription -- so anyone able to reach the Next
 * server could approve one, and the upstream audit record would name whatever
 * `actor` string they sent.
 *
 * The rest of the app is careful about exactly this. The command route rejects
 * all five verbs; the alert-ack route refuses any body carrying a forbidden op.
 * Those behaviours were correct and completely untested, which meant nothing
 * stopped a later edit from quietly removing them.
 *
 * So the tests below fall into two groups:
 *
 *   1. pin the refusals that were already right, so they cannot erode;
 *   2. cover the proxy's new fail-closed policy.
 *
 * Route handlers are imported and called directly with a Request. That is the
 * real handler, not a mock of it.
 */

import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as opsGet, POST as opsPost } from "@/app/api/ops/[...path]/route";
import {
  DELETE as cmdDelete,
  GET as cmdGet,
  PATCH as cmdPatch,
  POST as cmdPost,
  PUT as cmdPut,
} from "@/app/api/v1/command/[...path]/route";
import {
  DELETE as ackDelete,
  PATCH as ackPatch,
  POST as ackPost,
  PUT as ackPut,
} from "@/app/api/v1/alerts/[id]/ack/route";
import { checkProxy, MUTATING_OPS_PATHS, NEVER_PROXY } from "@/lib/ops-proxy-policy";

const BASE = "http://localhost:3000";

function req(path: string, init?: RequestInit) {
  return new Request(`${BASE}${path}`, init);
}

/**
 * The proxy reads `req.nextUrl.search`, which only exists on NextRequest. Using
 * a plain Request here passes a handler that is not the one Next will call.
 */
function nextReq(path: string, init?: RequestInit) {
  return new NextRequest(`${BASE}${path}`, init as never);
}

/** Next's route context: params arrive as a promise in the app router. */
function ctx<T extends object>(params: T) {
  return { params: Promise.resolve(params) };
}

// ---------------------------------------------------------------------------
// /api/v1/command/[...path] -- the explicit reject surface
// ---------------------------------------------------------------------------

describe("the command route refuses everything", () => {
  const handlers = {
    GET: cmdGet,
    POST: cmdPost,
    PUT: cmdPut,
    PATCH: cmdPatch,
    DELETE: cmdDelete,
  } as const;

  for (const [method, handler] of Object.entries(handlers)) {
    it(`${method} returns 403`, async () => {
      const res = await handler(req("/api/v1/command/arm", { method }));
      expect(res.status).toBe(403);
      const body = await res.json();
      expect(body.error).toBe("forbidden_op");
    });
  }

  it("names what it forbids, so the refusal is auditable", async () => {
    const body = await (await cmdPost(req("/api/v1/command/arm", { method: "POST" }))).json();
    expect(Array.isArray(body.forbidden_ops)).toBe(true);
    expect(body.forbidden_ops.length).toBeGreaterThan(0);
  });

  it("refuses regardless of what the path claims to be", async () => {
    for (const path of ["/api/v1/command/status", "/api/v1/command/read/telemetry"]) {
      const res = await cmdGet(req(path));
      expect(res.status).toBe(403);
    }
  });
});

// ---------------------------------------------------------------------------
// /api/v1/alerts/[id]/ack -- ack only, and nothing that looks like a command
// ---------------------------------------------------------------------------

describe("the alert-ack route", () => {
  it("rejects a forbidden op in the body with 403", async () => {
    const res = await ackPost(
      req("/api/v1/alerts/a1/ack", { method: "POST", body: JSON.stringify({ op: "arm" }) }),
      ctx({ id: "a1" }),
    );
    expect(res.status).toBe(403);
    expect((await res.json()).error).toBe("forbidden_op");
  });

  it("is case-insensitive about it", async () => {
    const res = await ackPost(
      req("/api/v1/alerts/a1/ack", { method: "POST", body: JSON.stringify({ op: "ARM" }) }),
      ctx({ id: "a1" }),
    );
    expect(res.status).toBe(403);
  });

  it("rejects an op it does not recognise rather than ignoring it", async () => {
    const res = await ackPost(
      req("/api/v1/alerts/a1/ack", { method: "POST", body: JSON.stringify({ op: "resolve" }) }),
      ctx({ id: "a1" }),
    );
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe("unknown_op");
  });

  it("returns 400 on malformed JSON instead of throwing", async () => {
    const res = await ackPost(
      req("/api/v1/alerts/a1/ack", { method: "POST", body: "{not json" }),
      ctx({ id: "a1" }),
    );
    expect(res.status).toBe(400);
  });

  it("404s an unknown alert id", async () => {
    const res = await ackPost(
      req("/api/v1/alerts/definitely-not-real/ack", { method: "POST", body: "{}" }),
      ctx({ id: "definitely-not-real" }),
    );
    expect(res.status).toBe(404);
  });

  for (const [name, handler] of Object.entries({ PUT: ackPut, PATCH: ackPatch, DELETE: ackDelete })) {
    it(`${name} is 405, not a command`, async () => {
      const res = await handler();
      expect(res.status).toBe(405);
    });
  }
});

// ---------------------------------------------------------------------------
// The proxy policy, as pure logic
// ---------------------------------------------------------------------------

describe("ops proxy policy", () => {
  // `as unknown as` because ProcessEnv requires NODE_ENV; these are stubs
  // that exercise one variable, not real environments.
  const noWrites = {} as unknown as NodeJS.ProcessEnv;
  const withWrites = { OPS_ALLOW_WRITES: "1" } as unknown as NodeJS.ProcessEnv;

  it("forwards reads", () => {
    expect(checkProxy(["alerts"], "GET", noWrites).allowed).toBe(true);
    expect(checkProxy(["weather", "current"], "GET", noWrites).allowed).toBe(true);
  });

  it("blocks the prescription approval gate by default", () => {
    const v = checkProxy(["vra", "approve"], "POST", noWrites);
    expect(v.allowed).toBe(false);
    if (!v.allowed) expect(v.error).toBe("writes_disabled");
  });

  it("allows it once the operator has explicitly enabled writes", () => {
    expect(checkProxy(["vra", "approve"], "POST", withWrites).allowed).toBe(true);
  });

  it("fails closed on a write it does not recognise", () => {
    const v = checkProxy(["something", "new"], "POST", withWrites);
    expect(v.allowed).toBe(false);
    if (!v.allowed) expect(v.error).toBe("write_not_allowlisted");
  });

  it("refuses vehicle paths on every method, even with writes enabled", () => {
    for (const path of NEVER_PROXY) {
      for (const method of ["GET", "POST"]) {
        const v = checkProxy(path.split("/"), method, withWrites);
        expect(v.allowed, `${method} ${path}`).toBe(false);
        if (!v.allowed) expect(v.error).toBe("forbidden_op");
      }
    }
  });

  it("no environment variable can turn the vehicle refusal off", () => {
    const permissive = {
      OPS_ALLOW_WRITES: "1",
      NODE_ENV: "development",
    } as unknown as NodeJS.ProcessEnv;
    expect(checkProxy(["arm"], "POST", permissive).allowed).toBe(false);
  });

  it("rejects path traversal", () => {
    for (const segs of [["..", "etc"], ["alerts", ".."], ["a\0b"]]) {
      const v = checkProxy(segs, "GET", withWrites);
      expect(v.allowed).toBe(false);
      if (!v.allowed) expect(v.status).toBe(400);
    }
  });

  it("every allowlisted write path is a real upstream route shape", () => {
    for (const path of MUTATING_OPS_PATHS) {
      expect(path).not.toMatch(/^\//);
      expect(path).toBe(path.toLowerCase());
    }
  });
});

// ---------------------------------------------------------------------------
// The proxy handler itself, against a stubbed upstream
// ---------------------------------------------------------------------------

describe("ops proxy handler", () => {
  const realFetch = globalThis.fetch;

  beforeEach(() => {
    delete process.env.OPS_ALLOW_WRITES;
  });

  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
    delete process.env.OPS_ALLOW_WRITES;
    delete process.env.OPS_DEMO;
  });

  function stubUpstream(status: number, payload: unknown) {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify(payload), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
    ) as unknown as typeof fetch;
  }

  it("passes a read through and preserves the upstream status", async () => {
    stubUpstream(200, { alerts: [], banner: "SIMULATION" });
    const res = await opsGet(nextReq("/api/ops/alerts"), ctx({ path: ["alerts"] }));
    expect(res.status).toBe(200);
    expect((await res.json()).banner).toBe("SIMULATION");
  });

  it("does not call upstream at all for a blocked write", async () => {
    const spy = vi.fn();
    globalThis.fetch = spy as unknown as typeof fetch;

    const res = await opsPost(
      nextReq("/api/ops/vra/approve", {
        method: "POST",
        body: "{}",
        headers: { "Content-Type": "application/json" },
      }),
      ctx({ path: ["vra", "approve"] }),
    );

    expect(res.status).toBe(403);
    expect(spy).not.toHaveBeenCalled();
  });

  it("says which header blocked it, so the refusal is visible in devtools", async () => {
    const res = await opsPost(
      nextReq("/api/ops/vra/approve", {
        method: "POST",
        body: "{}",
        headers: { "Content-Type": "application/json" },
      }),
      ctx({ path: ["vra", "approve"] }),
    );
    expect(res.headers.get("X-Ops-Proxy")).toBe("blocked");
  });

  it("reports an unreachable ops API as 503 and SIMULATION, not as success (strict mode, OPS_DEMO=0)", async () => {
    // By default reads now fall back to flagged demo data (tests/ops-demo.test.ts);
    // OPS_DEMO=0 keeps the strict behaviour this test pins.
    process.env.OPS_DEMO = "0";
    globalThis.fetch = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;

    const res = await opsGet(nextReq("/api/ops/alerts"), ctx({ path: ["alerts"] }));
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.offline).toBe(true);
    expect(body.banner).toBe("SIMULATION");
  });

  it("does not present a non-JSON upstream body as data", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response("<html>gateway error</html>", { status: 502 }),
    ) as unknown as typeof fetch;

    const res = await opsGet(nextReq("/api/ops/alerts"), ctx({ path: ["alerts"] }));
    expect(res.status).toBe(502);
    expect((await res.json()).error).toBe("upstream_non_json");
  });
});
