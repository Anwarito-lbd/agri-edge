/** The design's synthetic replay scenario: deterministic, bounded, and never wall-clock. */
import { describe, expect, it } from "vitest";

import { stripTimestamps } from "@/lib/map-layers";
import {
  clampT,
  detectionShowAt,
  fmtT,
  parseT,
  pathAt,
  SCENARIO_EVENTS,
  SCENARIO_TOTAL,
  seriesAt,
  seriesText,
  surveyPath,
  tracePoints,
} from "@/lib/ops-scenario";

describe("synthetic time", () => {
  it("formats t+mm:ss and never looks like a clock time", () => {
    expect(fmtT(0)).toBe("t+00:00");
    expect(fmtT(560)).toBe("t+09:20");
    expect(fmtT(900)).toBe("t+15:00");
    expect(fmtT(75)).not.toMatch(/\d{4}-\d{2}-\d{2}|AM|PM|Z$/);
  });

  it("clamps and parses the ?t= preset", () => {
    expect(clampT(-5)).toBe(0);
    expect(clampT(5000)).toBe(SCENARIO_TOTAL);
    expect(clampT(Number.NaN)).toBe(0);
    expect(parseT("300")).toBe(300);
    expect(parseT("abc")).toBe(0);
    expect(parseT(null)).toBe(0);
    expect(parseT("")).toBe(0);
  });
});

describe("synthetic series", () => {
  it("matches the design's closed-form functions at known points", () => {
    expect(seriesAt("alt", 0)).toBe(0);
    expect(seriesAt("alt", 20)).toBe(40);
    expect(seriesAt("spd", 0)).toBe(3);
    expect(seriesAt("bat", 0)).toBe(100);
    expect(seriesAt("bat", 900)).toBe(71);
    expect(seriesAt("sat", 0)).toBe(14);
    expect(seriesText("alt", 20)).toBe("40.0");
    expect(seriesText("hdg", 0)).toMatch(/^\d+$/);
  });

  it("is deterministic, bounded and never negative", () => {
    for (let t = 0; t <= SCENARIO_TOTAL; t += 30) {
      expect(seriesAt("alt", t)).toBe(seriesAt("alt", t));
      expect(seriesAt("alt", t)).toBeGreaterThanOrEqual(0);
      expect(seriesAt("bat", t)).toBeLessThanOrEqual(100);
    }
    expect(tracePoints("alt")).toBe(tracePoints("alt"));
  });

  it("scripts only events inside the scenario, in order, using design keys", () => {
    const ats = SCENARIO_EVENTS.map((e) => e.at);
    expect([...ats].sort((a, b) => a - b)).toEqual(ats);
    expect(Math.max(...ats)).toBeLessThanOrEqual(SCENARIO_TOTAL);
    for (const e of SCENARIO_EVENTS) expect(e.key).toMatch(/^d\.k[0-9a-f]{8}$/);
  });
});

describe("simulated flight path", () => {
  const box: [number, number, number, number] = [45.0, -75.0, 45.01, -74.99];

  it("stays inside the box and starts empty", () => {
    const path = surveyPath(box);
    for (const [lat, lng] of path) {
      expect(lat).toBeGreaterThanOrEqual(box[0]);
      expect(lat).toBeLessThanOrEqual(box[2]);
      expect(lng).toBeGreaterThanOrEqual(box[1]);
      expect(lng).toBeLessThanOrEqual(box[3]);
    }
    expect(pathAt(path, 0).point).toEqual(path[0]);
    expect(pathAt(path, 1).point).toEqual(path[path.length - 1]);
    expect(pathAt([], 0.5).point).toBeNull();
  });

  it("moves forward as time advances", () => {
    const path = surveyPath(box);
    expect(pathAt(path, 0.5).upTo.length).toBeGreaterThan(pathAt(path, 0.1).upTo.length);
  });

  it("reveals demo detections spread across the scenario", () => {
    const times = [0, 1, 2].map((i) => detectionShowAt(i, 3));
    expect(times).toEqual([225, 450, 675]);
  });
});

describe("demo timestamps", () => {
  it("are removed from map features so nothing looks live", () => {
    const fc = stripTimestamps({
      type: "FeatureCollection",
      features: [
        { type: "Feature", id: "d1", geometry: null, properties: { label: "x", ts: "2026-09-15T12:00:00Z", synthetic: true } },
      ],
    });
    expect(fc?.features[0].properties).toEqual({ label: "x", synthetic: true });
    expect(stripTimestamps(null)).toBeNull();
  });
});

describe("sensor state and alert severity helpers", () => {
  it("reads state from the device row only", async () => {
    const { deviceState } = await import("@/lib/ops-sensors");
    const base = { device_id: "x", device_type: "soil_probe", name: "x" };
    expect(deviceState({ ...base, last_seen: "t", battery_pct: 80 })).toBe("ok");
    expect(deviceState({ ...base, last_seen: "t", battery_pct: 18 })).toBe("warn");
    expect(deviceState({ ...base, last_seen: null, battery_pct: 80 })).toBe("critical");
    expect(deviceState({ ...base, last_seen: "t" })).toBe("ok");
  });

  it("maps API severities to badge classes", async () => {
    const { severityClass } = await import("@/lib/ops-severity");
    expect(severityClass("EMERGENCY")).toBe("critical");
    expect(severityClass("critical")).toBe("critical");
    expect(severityClass("WARNING")).toBe("warn");
    expect(severityClass("INFO")).toBe("ok");
    expect(severityClass(undefined)).toBe("neutral");
  });
});
