import { NextRequest, NextResponse } from "next/server";

import { demoForced } from "@/lib/ops-mode";
import { checkWriteRequest } from "@/lib/ops-proxy-policy";
import { opsBase, SESSION_COOKIE, sessionCookieOptions, validTokenShape } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Log in against the ops API and keep the session in an httpOnly cookie.
 * The token is never returned to the browser's JavaScript.
 */
export async function POST(req: NextRequest) {
  const check = checkWriteRequest("POST", req.headers, req.url);
  if (!check.allowed) {
    return NextResponse.json({ error: check.error, message: check.message }, { status: check.status });
  }
  if (demoForced()) {
    return NextResponse.json({ error: "demo_mode", demo: true }, { status: 503 });
  }
  let body: { username?: unknown; password?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const username = typeof body.username === "string" ? body.username : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!username || !password) {
    return NextResponse.json({ error: "missing_credentials" }, { status: 400 });
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${opsBase()}/api/ops/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
  } catch {
    return NextResponse.json({ error: "ops_unreachable", offline: true }, { status: 503 });
  }
  const data = (await upstream.json().catch(() => ({}))) as {
    token?: string;
    expires?: number;
    user?: unknown;
    error?: string;
  };
  if (!upstream.ok) {
    return NextResponse.json({ error: data.error || "login_failed" }, { status: upstream.status });
  }
  const token = validTokenShape(data.token);
  if (!token) {
    return NextResponse.json({ error: "bad_upstream_token" }, { status: 502 });
  }
  const maxAge = typeof data.expires === "number" ? data.expires - Date.now() / 1000 : 12 * 3600;
  const res = NextResponse.json({ user: data.user }, { headers: { "Cache-Control": "no-store" } });
  res.cookies.set(SESSION_COOKIE, token, sessionCookieOptions(maxAge));
  return res;
}
