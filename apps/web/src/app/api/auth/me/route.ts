import { NextRequest, NextResponse } from "next/server";

import { demoForced } from "@/lib/ops-mode";
import { opsBase, SESSION_COOKIE, validTokenShape } from "@/lib/session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Who is logged in, per the ops API. 401 when nobody is. */
export async function GET(req: NextRequest) {
  // Demo mode has no accounts; say so instead of failing against a backend that is not there.
  if (demoForced()) {
    return NextResponse.json({ kind: "demo", name: "demo", role: "viewer", demo: true }, { headers: { "Cache-Control": "no-store" } });
  }
  const token = validTokenShape(req.cookies.get(SESSION_COOKIE)?.value);
  try {
    const upstream = await fetch(`${opsBase()}/api/ops/auth/me`, {
      headers: token ? { Authorization: `Bearer ${token}`, Accept: "application/json" } : { Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    });
    const data = await upstream.json().catch(() => ({}));
    return NextResponse.json(data, { status: upstream.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "ops_unreachable", offline: true }, { status: 503 });
  }
}
