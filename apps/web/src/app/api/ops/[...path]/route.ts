import { NextRequest, NextResponse } from "next/server";

import { demoGet, demoWriteRefusal, type DemoReply } from "@/lib/ops-demo";
import { DEMO_HEADER, demoFallbackAllowed, demoForced } from "@/lib/ops-mode";
import { checkProxy, checkWriteRequest } from "@/lib/ops-proxy-policy";
import { opsBase, SESSION_COOKIE, validTokenShape } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const TIMEOUT_MS = 8_000;

function targetUrl(pathSegments: string[], search: string): string {
  const suffix = pathSegments.map(encodeURIComponent).join("/");
  return `${opsBase()}/api/ops/${suffix}${search}`;
}

function blocked(status: number, error: string, message: string, path: string, method: string) {
  return NextResponse.json(
    { error, message, path, method, simulation: true, banner: "SIMULATION" },
    { status, headers: { "Cache-Control": "no-store", "X-Ops-Proxy": "blocked" } },
  );
}

function demoResponse(reply: DemoReply, mode: "demo" | "demo-fallback") {
  return NextResponse.json(reply.body, {
    status: reply.status,
    headers: { "Cache-Control": "no-store", "X-Ops-Proxy": "demo", [DEMO_HEADER]: mode },
  });
}

async function proxy(
  req: NextRequest,
  pathSegments: string[],
  method: "GET" | "POST",
): Promise<NextResponse> {
  // Fail closed before the request is built. Reads forward; writes are
  // allowlisted and off by default. See src/lib/ops-proxy-policy.ts -- this
  // proxy used to forward anything, including the prescription approval gate,
  // with no authentication anywhere in the app.
  const shown = `/api/ops/${pathSegments.join("/")}`;
  const session = validTokenShape(req.cookies.get(SESSION_COOKIE)?.value);
  const request = checkWriteRequest(method, req.headers, req.url);
  if (!request.allowed) {
    return blocked(request.status, request.error, request.message, shown, method);
  }
  const verdict = checkProxy(pathSegments, method, process.env, { hasSession: !!session });
  if (!verdict.allowed) {
    return blocked(verdict.status, verdict.error, verdict.message, shown, method);
  }

  // No backend configured (the Vercel default) or OPS_DEMO=1: answer from the
  // built-in synthetic sample data. Reads only; a write is refused, not stored.
  if (demoForced()) {
    return demoResponse(
      method === "GET"
        ? demoGet(pathSegments, req.nextUrl.searchParams)
        : demoWriteRefusal(pathSegments.join("/")),
      "demo",
    );
  }

  const url = targetUrl(pathSegments, req.nextUrl.search);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    // The person's session goes upstream as a bearer token; the ops API checks
    // their role and records them in the audit log. No session, no header: the
    // station then decides (401 once it has users).
    const headers: Record<string, string> = { Accept: "application/json" };
    if (session) headers.Authorization = `Bearer ${session}`;
    const init: RequestInit = {
      method,
      signal: controller.signal,
      headers,
      cache: "no-store",
    };

    if (method === "POST") {
      const bodyText = await req.text();
      init.headers = { ...headers, "Content-Type": "application/json" };
      init.body = bodyText || "{}";
    }

    const upstream = await fetch(url, init);
    const ctype = upstream.headers.get("content-type") || "";
    if (upstream.ok && ctype.startsWith("application/zip")) {
      // Prescription export: bytes, not JSON.
      return new NextResponse(await upstream.arrayBuffer(), {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition":
            upstream.headers.get("content-disposition") || 'attachment; filename="prescription.zip"',
          "Cache-Control": "no-store",
          "X-Ops-Proxy": "1",
        },
      });
    }
    const text = await upstream.text();
    let payload: unknown;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      payload = {
        error: "upstream_non_json",
        status: upstream.status,
        body: text.slice(0, 500),
      };
    }

    return NextResponse.json(payload, {
      status: upstream.status,
      headers: {
        "Cache-Control": "no-store",
        "X-Ops-Proxy": "1",
      },
    });
  } catch (err) {
    // A configured backend that cannot be reached: reads fall back to the
    // clearly-flagged demo data instead of a dead page. Writes never do -- an
    // approval must not appear to succeed against sample data. OPS_DEMO=0
    // turns the fallback off and restores the plain 503.
    if (method === "GET" && demoFallbackAllowed()) {
      return demoResponse(demoGet(pathSegments, req.nextUrl.searchParams), "demo-fallback");
    }
    const message =
      err instanceof Error
        ? err.name === "AbortError"
          ? "Ops API timeout"
          : err.message
        : "Ops API unreachable";
    return NextResponse.json(
      {
        error: "ops_unreachable",
        message,
        offline: true,
        simulation: true,
        banner: "SIMULATION",
        detail: "Could not reach the ops API.",
      },
      { status: 503, headers: { "Cache-Control": "no-store", "X-Ops-Proxy": "1" } },
    );
  } finally {
    clearTimeout(timer);
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? [], "GET");
}

export async function POST(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  return proxy(req, path ?? [], "POST");
}
