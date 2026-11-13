import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { demoForced } from "@/lib/ops-mode";

/**
 * Send people without a session to the login page before the ops pages load.
 *
 * On when OPS_AUTH=1 -- set it once the ops station has users. A station in
 * its open dev mode has no users to log in as, and the pages there still work
 * without a session; the API itself answers 401 once users exist, and the
 * pages redirect on that too (OpsShell), so this is the fast path, not the gate.
 */
export function proxy(request: NextRequest) {
  // Demo mode has no accounts to log in with, so there is nothing to gate.
  if (demoForced()) return NextResponse.next();
  if (process.env.OPS_AUTH !== "1") return NextResponse.next();
  if (request.cookies.get("ae_session")?.value) return NextResponse.next();
  const login = new URL("/login", request.url);
  login.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/ops/:path*"],
};
