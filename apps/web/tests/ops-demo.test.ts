/**
 * Demo / simulated mode for the ops proxy (1 Oct 2026).
 *
 * Without a backend (the Vercel default) /api/ops/* answers from deterministic
 * synthetic fixtures, labelled as such. With a backend it forwards; if that is
 * unreachable, reads fall back to the same flagged fixtures and writes do not.
 */

import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as opsGet, POST as opsPost } from "@/app/api/ops/[...path]/route";
import { GET as meGet } from "@/app/api/auth/me/route";
import { demoGet } from "@/lib/ops-demo";

const BASE = "http://localhost:3000";
const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });
const nextReq = (path: string, init?: RequestInit) => new NextRequest(`${BASE}${path}`, init as never);

/** Every route the /ops pages and the shell call. */
const PAGE_ROUTES = [
  "overview", "live", "weather", "weather/derived", "sensors", "alerts",
  "map/geojson", "map/detections", "fields", "satellite", "prescriptions",
  "prescriptions/rx-demo-001", "recommendations",
];

describe("demo mode without a backend", () => {
  const realFetch = globalThis.fetch;
  let spy: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    delete process.env.OPS_API_URL;
    delete process.env.OPS_DEMO;
    spy = vi.fn();
    globalThis.fetch = spy as unknown as typeof fetch;
  });
  afterEach(() => {
    globalThis.fetch = realFetch;
    process.env.OPS_API_URL = "http://ops.test.invalid";
    delete process.env.OPS_DEMO;
  });

  it.each(PAGE_ROUTES)("answers /api/ops/%s with flagged synthetic data and never calls out", async (route) => {
    const res = await opsGet(nextReq(`/api/ops/${route}`), ctx(route.split("/")));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.demo).toBe(true);
    expect(body.synthetic).toBe(true);
    expect(body.simulation).toBe(true);
    expect(body.banner).toBe("SIMULATION");
    expect(res.headers.get("X-Ops-Mode")).toBe("demo");
    expect(spy).not.toHaveBeenCalled();
  });

  it("is deterministic", () => {
    for (const r of PAGE_ROUTES) {
      const a = JSON.stringify(demoGet(r.split("/"), new URLSearchParams()));
      const b = JSON.stringify(demoGet(r.split("/"), new URLSearchParams()));
      expect(a).toBe(b);
    }
  });

  it("every row it hands out is marked synthetic, and detections carry no confidence", () => {
    const weather = demoGet(["weather"], new URLSearchParams()).body as { observations: { synthetic: boolean }[] };
    expect(weather.observations.every((o) => o.synthetic)).toBe(true);
    const det = demoGet(["map", "detections"], new URLSearchParams()).body as {
      features: { properties: Record<string, unknown> }[];
    };
    expect(det.features.length).toBeGreaterThan(0);
    for (const f of det.features) {
      expect(f.properties.synthetic).toBe(true);
      expect(f.properties).not.toHaveProperty("confidence");
    }
  });

  it("does not apply writes, and does not call out", async () => {
    const res = await opsPost(
      nextReq("/api/ops/alerts/ack", {
        method: "POST",
        body: "{}",
        headers: { "Content-Type": "application/json" },
      }),
      ctx(["alerts", "ack"]),
    );
    // No session and OPS_ALLOW_WRITES unset: the policy blocks before demo even runs.
    expect([403, 405]).toContain(res.status);
    expect(spy).not.toHaveBeenCalled();
  });

  it("with writes enabled, demo still refuses them (405) instead of storing", async () => {
    process.env.OPS_ALLOW_WRITES = "1";
    const res = await opsPost(
      nextReq("/api/ops/alerts/ack", { method: "POST", body: "{}", headers: { "Content-Type": "application/json" } }),
      ctx(["alerts", "ack"]),
    );
    delete process.env.OPS_ALLOW_WRITES;
    expect(res.status).toBe(405);
    expect((await res.json()).error).toBe("demo_read_only");
  });

  it("still refuses vehicle paths", async () => {
    const res = await opsGet(nextReq("/api/ops/arm"), ctx(["arm"]));
    expect(res.status).toBe(403);
  });

  it("reports a demo identity, not an account", async () => {
    const res = await meGet(nextReq("/api/auth/me"));
    expect((await res.json()).kind).toBe("demo");
    expect(spy).not.toHaveBeenCalled();
  });

  it("OPS_DEMO=1 wins over a configured URL", async () => {
    process.env.OPS_API_URL = "https://ops.example.invalid";
    process.env.OPS_DEMO = "1";
    const res = await opsGet(nextReq("/api/ops/overview"), ctx(["overview"]));
    expect((await res.json()).demo).toBe(true);
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("a configured backend", () => {
  const realFetch = globalThis.fetch;
  beforeEach(() => {
    process.env.OPS_API_URL = "https://ops.example.invalid";
    delete process.env.OPS_DEMO;
  });
  afterEach(() => {
    globalThis.fetch = realFetch;
    process.env.OPS_API_URL = "http://ops.test.invalid";
    delete process.env.OPS_DEMO;
  });

  it("is used when reachable (live data is not marked demo)", async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(JSON.stringify({ device_count: 9 }), { status: 200, headers: { "Content-Type": "application/json" } }),
    ) as unknown as typeof fetch;
    const res = await opsGet(nextReq("/api/ops/overview"), ctx(["overview"]));
    const body = await res.json();
    expect(body.device_count).toBe(9);
    expect(body.demo).toBeUndefined();
  });

  it("falls back to flagged demo data on reads when unreachable", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    const res = await opsGet(nextReq("/api/ops/overview"), ctx(["overview"]));
    expect(res.status).toBe(200);
    expect(res.headers.get("X-Ops-Mode")).toBe("demo-fallback");
    expect((await res.json()).demo).toBe(true);
  });

  it("OPS_DEMO=0 restores the strict 503", async () => {
    process.env.OPS_DEMO = "0";
    globalThis.fetch = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    const res = await opsGet(nextReq("/api/ops/overview"), ctx(["overview"]));
    expect(res.status).toBe(503);
  });

  it("never fakes a write when the backend is down", async () => {
    process.env.OPS_ALLOW_WRITES = "1";
    globalThis.fetch = vi.fn(async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    const res = await opsPost(
      nextReq("/api/ops/alerts/ack", { method: "POST", body: "{}", headers: { "Content-Type": "application/json" } }),
      ctx(["alerts", "ack"]),
    );
    delete process.env.OPS_ALLOW_WRITES;
    expect(res.status).toBe(503);
  });
});
