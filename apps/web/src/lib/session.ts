/**
 * The ops session, held in an httpOnly cookie on this app's origin.
 *
 * The browser never sees the token: `/api/auth/login` receives it from the ops
 * API and sets it as `ae_session` (httpOnly, SameSite=Strict, Secure in
 * production), and the ops proxy forwards it upstream as a bearer token. The
 * ops API checks the role and writes the audit log under the person's name.
 */

export const SESSION_COOKIE = "ae_session";

export function opsBase(): string {
  return (process.env.OPS_API_URL || "http://127.0.0.1:8765").replace(/\/$/, "");
}

export function cookieSecure(): boolean {
  return (
    process.env.AGRIEDGE_COOKIE_SECURE === "1" ||
    (process.env.NODE_ENV === "production" && process.env.AGRIEDGE_COOKIE_SECURE !== "0")
  );
}

export function sessionCookieOptions(maxAgeS: number) {
  return {
    httpOnly: true,
    sameSite: "strict" as const,
    secure: cookieSecure(),
    path: "/",
    maxAge: Math.max(0, Math.floor(maxAgeS)),
  };
}

/** A token shaped like the ops API's (v1.<payload>.<sig>), or undefined. */
export function validTokenShape(token: string | undefined): string | undefined {
  if (!token) return undefined;
  return /^v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(token) ? token : undefined;
}
