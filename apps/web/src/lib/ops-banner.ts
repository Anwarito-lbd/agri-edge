import type { Key } from "@/lib/i18n";

/**
 * The ops screens show ONE persistent amber SIMULATION banner (design v2). This picks the detail
 * line shown on the right of it. There is deliberately no "no banner" outcome, and no second banner:
 * PR #4's DEMO banner is the "demo" detail of this same bar.
 */
export type OpsBannerMode = "cached" | "offline" | "demo" | "sim" | "live";

export const OPS_BANNER_HEADLINE: Key = "d.k78b3a344"; // SIMULATION — synthetic demo data, no aircraft connected

export function opsBannerMode(s: {
  cachedAt: string | null;
  offline: boolean;
  demo: boolean;
  simulation: boolean;
  /** Whether the first status answer has arrived; until then, assume simulation. */
  known: boolean;
}): OpsBannerMode {
  if (s.cachedAt) return "cached";
  if (s.offline) return "offline";
  if (s.demo) return "demo";
  if (s.simulation || !s.known) return "sim";
  return "live";
}

export const OPS_BANNER_DETAIL: Record<OpsBannerMode, Key> = {
  cached: "shell.offlineCached",
  offline: "shell.unreachable",
  demo: "shell.demo",
  sim: "d.k2009a7c9", // Nothing on this screen is measured
  live: "shell.live",
};
