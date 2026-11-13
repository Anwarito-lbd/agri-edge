import { NextRequest, NextResponse } from "next/server";

import { checkWriteRequest } from "@/lib/ops-proxy-policy";
import { SESSION_COOKIE, sessionCookieOptions } from "@/lib/session";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const check = checkWriteRequest("POST", req.headers, req.url);
  if (!check.allowed) {
    return NextResponse.json({ error: check.error }, { status: check.status });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, "", sessionCookieOptions(0));
  return res;
}
