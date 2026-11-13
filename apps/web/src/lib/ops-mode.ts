/**
 * Which backend the ops pages talk to: a live ops API, or the built-in
 * DEMO / SIMULATED sample data.
 *
 * - OPS_API_URL unset (or blank)  -> demo. This is the Vercel preview/production
 *   default: there is no backend there, and there must not be a localhost URL
 *   pretending to be one.
 * - OPS_DEMO=1                    -> demo even if OPS_API_URL is set.
 * - OPS_API_URL set               -> live. If a read cannot reach it, the proxy
 *   falls back to demo data (clearly flagged) instead of a 503 -- unless
 *   OPS_DEMO=0, which keeps the old strict behaviour (503, nothing invented).
 */

export function opsConfigured(env: NodeJS.ProcessEnv = process.env): boolean {
  return !!env.OPS_API_URL && env.OPS_API_URL.trim() !== "";
}

/** The deployment has no live backend (or was told to ignore it). */
export function demoForced(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.OPS_DEMO === "1" || !opsConfigured(env);
}

/** A configured-but-unreachable backend may be replaced by demo data on reads. */
export function demoFallbackAllowed(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.OPS_DEMO !== "0";
}

export const DEMO_HEADER = "X-Ops-Mode";
