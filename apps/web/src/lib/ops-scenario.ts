/**
 * The design's synthetic replay scenario, ported from the design's js/ops.js.
 *
 * ALL OF THIS IS SIMULATED. It is a deterministic function of "synthetic seconds" (t+00:00 .. t+15:00),
 * with no randomness, no clock and no network. It exists only to drive the demo scrubber on /ops/map and
 * /ops/live. It is never shown when a live Ops API is answering: there is no aircraft telemetry endpoint,
 * and nothing here is a measurement. Times are "t+mm:ss", never wall-clock.
 */

/** Length of the synthetic scenario in synthetic seconds (15 minutes). */
export const SCENARIO_TOTAL = 900;
/** Synthetic seconds advanced per 100 ms tick while playing (the design's pace). */
export const SCENARIO_STEP = 6;

export function clampT(t: number): number {
  if (!Number.isFinite(t)) return 0;
  return Math.max(0, Math.min(SCENARIO_TOTAL, Math.round(t)));
}

/** "t+mm:ss" */
export function fmtT(t: number): string {
  const s = Math.round(t);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `t+${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

/** ?t=300 preset, same as the design. Anything unusable is 0. */
export function parseT(raw: string | null | undefined): number {
  if (raw == null || raw.trim() === "") return 0;
  return clampT(Number(raw));
}

export type SeriesKey = "alt" | "spd" | "hdg" | "bat" | "sat";

const SERIES: Record<SeriesKey, (t: number) => number> = {
  alt: (t) => (t < 40 ? 2 * t : t > 860 ? Math.max(0, 80 - (t - 860) * 2) : 80 + 2 * Math.sin(t / 45)),
  spd: (t) => (t < 40 || t > 860 ? 3 : 11 + 1.2 * Math.sin(t / 30)),
  hdg: (t) => {
    const leg = Math.floor(t / 60) % 2;
    return Math.round(leg ? 94 + 2 * Math.sin(t / 9) : 274 + 2 * Math.sin(t / 9));
  },
  bat: (t) => Math.round(100 - t * 0.032),
  sat: (t) => 14 + Math.round(Math.sin(t / 120)),
};

export function seriesAt(key: SeriesKey, t: number): number {
  return SERIES[key](clampT(t));
}

/** Display string of a series value (alt and speed to one decimal, the rest whole). */
export function seriesText(key: SeriesKey, t: number): string {
  const v = seriesAt(key, t);
  return key === "alt" || key === "spd" ? v.toFixed(1) : String(v);
}

/** Polyline points of the synthetic trace (design: 640 px wide, 14 px apart) for one series, scaled to a y-range. */
export function tracePoints(key: "alt" | "spd", x0 = 20, width = 640, step = 14): string {
  const out: string[] = [];
  for (let x = 0; x <= width; x += step) {
    const t = (x / width) * SCENARIO_TOTAL;
    const v = seriesAt(key, t);
    // alt 0..100 m plotted on y 190..30; speed 0..20 m/s plotted on y 190..30.
    const max = key === "alt" ? 100 : 20;
    const y = 190 - (v / max) * 160;
    out.push(`${(x0 + x).toFixed(1)},${y.toFixed(1)}`);
  }
  return out.join(" ");
}

export type ScenarioEvent = {
  /** Synthetic second the event happens at. */
  at: number;
  /** Design i18n key for the event text. */
  key: string;
  level: "ok" | "warn" | "critical";
};

/** Scripted event log from the design (live screen). Keys are design keys, "d.k…". */
export const SCENARIO_EVENTS: readonly ScenarioEvent[] = [
  { at: 0, key: "d.k7e3c3499", level: "ok" },
  { at: 40, key: "d.k743db1ec", level: "ok" },
  { at: 180, key: "d.kcfb0d39c", level: "ok" },
  { at: 420, key: "d.k78f3e374", level: "ok" },
  { at: 560, key: "d.kae57df91", level: "warn" },
  { at: 720, key: "d.k9b5b3e4e", level: "critical" },
];

export type LatLng = [number, number];

/**
 * A lawn-mower survey path inside a bounding box [south, west, north, east]: `legs` east-west passes,
 * joined at alternating ends. Deterministic; it is a drawing aid for the simulated aircraft, not a flight plan.
 */
export function surveyPath(bbox: [number, number, number, number], legs = 6, inset = 0.12): LatLng[] {
  const [s, w, n, e] = bbox;
  const dLat = n - s;
  const dLng = e - w;
  const west = w + dLng * inset;
  const east = e - dLng * inset;
  const out: LatLng[] = [];
  for (let i = 0; i < legs; i++) {
    const lat = s + dLat * (inset + ((1 - 2 * inset) * i) / Math.max(1, legs - 1));
    if (i % 2 === 0) out.push([lat, west], [lat, east]);
    else out.push([lat, east], [lat, west]);
  }
  return out;
}

function dist(a: LatLng, b: LatLng): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}

/** The point at fraction f (0..1) along the path, and every vertex up to it (for a progress line). */
export function pathAt(path: LatLng[], f: number): { point: LatLng | null; upTo: LatLng[] } {
  if (path.length === 0) return { point: null, upTo: [] };
  if (path.length === 1) return { point: path[0], upTo: [path[0]] };
  const frac = Math.max(0, Math.min(1, f));
  const lens: number[] = [];
  let total = 0;
  for (let i = 1; i < path.length; i++) {
    const d = dist(path[i - 1], path[i]);
    lens.push(d);
    total += d;
  }
  let target = total * frac;
  const upTo: LatLng[] = [path[0]];
  for (let i = 1; i < path.length; i++) {
    const d = lens[i - 1];
    if (target <= d || i === path.length - 1) {
      const k = d === 0 ? 0 : Math.min(1, target / d);
      const p: LatLng = [
        path[i - 1][0] + (path[i][0] - path[i - 1][0]) * k,
        path[i - 1][1] + (path[i][1] - path[i - 1][1]) * k,
      ];
      upTo.push(p);
      return { point: p, upTo };
    }
    target -= d;
    upTo.push(path[i]);
  }
  return { point: path[path.length - 1], upTo };
}

/** The n-th of `count` demo detections becomes visible this many synthetic seconds in (evenly spread). */
export function detectionShowAt(index: number, count: number): number {
  return Math.round(((index + 1) / (count + 1)) * SCENARIO_TOTAL);
}
