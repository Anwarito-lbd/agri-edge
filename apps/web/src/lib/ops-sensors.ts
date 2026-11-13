import type { DeviceRow } from "@/lib/ops-types";

export type SensorState = "ok" | "warn" | "critical";

/** A battery under this percentage is called out (the demo data has one such probe). */
export const LOW_BATTERY_PCT = 25;

/**
 * State is read from the device row itself: no last_seen -> no signal ("critical"); a low battery -> flagged
 * ("warn"); else reporting ("ok"). Nothing here is measured by this site.
 */
export function deviceState(d: DeviceRow): SensorState {
  if (!d.last_seen) return "critical";
  if (typeof d.battery_pct === "number" && d.battery_pct < LOW_BATTERY_PCT) return "warn";
  return "ok";
}
