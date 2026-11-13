/**
 * The farmer app's offline, French and map pieces (24 Sept 2026).
 *
 * None of these need a browser: the service worker's routing rule, the
 * dictionaries, the layer merging and the login redirect are plain functions.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import { en, fr, translate } from "@/lib/i18n";
import { advanceClock, nextStreamFrames, resetMockForTests, TICK_MS } from "@/lib/mock-pi/state";
import { mergeLayers, polygonsOf, type LayerId } from "@/lib/map-layers";
import type { FeatureCollection } from "@/lib/ops-types";
import { safeNext } from "@/lib/safe-next";

const root = (p: string) => fileURLToPath(new URL(`../${p}`, import.meta.url));

describe("French", () => {
  it("every English string has a French one, and no French string is left empty", () => {
    for (const k of Object.keys(en)) {
      expect(fr, k).toHaveProperty(k);
      expect(fr[k as keyof typeof en].trim(), k).not.toBe("");
    }
    expect(Object.keys(fr).sort()).toEqual(Object.keys(en).sort());
  });

  it("keeps the same placeholders in both languages", () => {
    const vars = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort();
    for (const k of Object.keys(en) as (keyof typeof en)[]) expect(vars(fr[k]), k).toEqual(vars(en[k]));
  });

  it("fills placeholders and leaves unknown ones visible", () => {
    expect(translate("fr", "alerts.by", { name: "Ada" })).toBe("par Ada");
    expect(translate("en", "alerts.by")).toBe("by {name}");
  });
});

// sw.js is a classic script for the browser; evaluate it with stand-ins for
// the worker globals and take its exported routing rule.
function loadServiceWorker() {
  const src = readFileSync(root("public/sw.js"), "utf8");
  const mod: { exports: Record<string, unknown> } = { exports: {} };
  const self = { addEventListener: () => {}, location: { origin: "https://farm.example" } };
  new Function("self", "caches", "module", src)(self, {}, mod);
  return mod.exports as { classify: (r: { method: string; url: string; mode?: string }) => string; CACHED_AT: string };
}

describe("the service worker", () => {
  const { classify, CACHED_AT } = loadServiceWorker();
  const at = (path: string, method = "GET", mode?: string) =>
    classify({ method, url: `https://farm.example${path}`, mode });

  it("never caches a write: an approval must not be queued and replayed unseen", () => {
    for (const m of ["POST", "PUT", "PATCH", "DELETE"]) expect(at("/api/ops/alerts/ack", m)).toBe("network");
  });

  it("never caches logins or prescription downloads", () => {
    expect(at("/api/auth/me")).toBe("network");
    expect(at("/api/ops/prescriptions/rx_1/export")).toBe("network");
  });

  it("keeps ops reads, tiles, static assets and pages", () => {
    expect(at("/api/ops/recommendations")).toBe("api");
    expect(classify({ method: "GET", url: "https://tile.openstreetmap.org/12/1186/1417.png" })).toBe("tile");
    expect(at("/_next/static/chunk.js")).toBe("static");
    expect(at("/ops/map", "GET", "navigate")).toBe("page");
  });

  it("leaves other sites alone", () => {
    expect(classify({ method: "GET", url: "https://evil.example/api/ops/overview" })).toBe("network");
  });

  it("stamps with the header the pages read", async () => {
    const { CACHED_AT_HEADER } = await import("@/lib/ops-api");
    expect(CACHED_AT).toBe(CACHED_AT_HEADER);
  });
});

describe("the install manifest", () => {
  const manifest = JSON.parse(readFileSync(root("public/manifest.webmanifest"), "utf8"));

  it("has what a browser needs to install it", () => {
    expect(manifest.name).toBeTruthy();
    expect(manifest.start_url).toMatch(/^\//);
    expect(manifest.display).toBe("standalone");
    const sizes = manifest.icons.map((i: { sizes: string }) => i.sizes);
    expect(sizes).toEqual(expect.arrayContaining(["192x192", "512x512"]));
  });

  it("points at icons that exist and are PNGs of the stated size", () => {
    for (const icon of manifest.icons as { src: string; sizes: string }[]) {
      const png = readFileSync(root(`public${icon.src}`));
      expect(png.subarray(1, 4).toString("ascii")).toBe("PNG");
      const [w, h] = [png.readUInt32BE(16), png.readUInt32BE(20)];
      expect(`${w}x${h}`).toBe(icon.sizes);
    }
  });
});

describe("map layers", () => {
  const square = (x: number): number[][][] => [[[x, 0], [x + 1, 0], [x + 1, 1], [x, 0]]];
  const fc = (...features: FeatureCollection["features"]): FeatureCollection => ({ type: "FeatureCollection", features });

  it("draws every part of a MultiPolygon (they used to be counted and not drawn)", () => {
    expect(polygonsOf({ type: "MultiPolygon", coordinates: [square(0), square(2)] })).toHaveLength(2);
    expect(polygonsOf({ type: "Polygon", coordinates: square(0) })).toHaveLength(1);
    expect(polygonsOf({ type: "Point", coordinates: [0, 0] })).toHaveLength(0);
    expect(polygonsOf(null)).toHaveLength(0);
  });

  it("shows only the layers switched on, tagged with where they came from", () => {
    const sources = {
      farm: fc({ type: "Feature", id: "f1", geometry: { type: "Polygon", coordinates: square(0) }, properties: { layer: "field" } }),
      detections: fc({ type: "Feature", id: "d1", geometry: { type: "Point", coordinates: [0.5, 0.5] }, properties: {} }),
      satellite: null,
    };
    const on = (...ids: LayerId[]) => mergeLayers(sources, new Set(ids));
    expect(on("farm", "detections").features.map((f) => f.id)).toEqual(["farm:f1", "detections:d1"]);
    expect(on("detections").features[0].properties?.source_layer).toBe("detections");
    expect(on("satellite", "prescription").features).toEqual([]);
  });
});

describe("after login", () => {
  it.each([
    ["/ops/alerts", "/ops/alerts"],
    ["/ops/map?rx=rx_1", "/ops/map?rx=rx_1"],
    [null, "/ops/recommendations"],
    ["https://evil.example", "/ops/recommendations"],
    ["//evil.example", "/ops/recommendations"],
    ["/\\evil.example", "/ops/recommendations"],
    ["/\t/evil.example", "/ops/recommendations"],
    ["javascript:alert(1)", "/ops/recommendations"],
  ])("next=%s goes to %s", (value, expected) => {
    expect(safeNext(value)).toBe(expected);
  });
});

describe("the demo feed's clock", () => {
  afterEach(() => resetMockForTests());

  it("ticks once per interval however many streams ask", () => {
    resetMockForTests();
    const t0 = 1_000_000;
    expect(advanceClock(t0)).toBe(true);
    // Two more open tabs asking in the same interval do not tick again.
    expect(advanceClock(t0 + 10)).toBe(false);
    expect(advanceClock(t0 + 500)).toBe(false);
    expect(advanceClock(t0 + TICK_MS)).toBe(true);
  });

  it("a stream still gets its frames when another stream already ticked", () => {
    resetMockForTests();
    advanceClock(2_000_000);
    const topics = nextStreamFrames(2_000_010).map((f) => f.topic);
    expect(topics).toEqual(expect.arrayContaining(["heartbeat", "gps", "battery"]));
  });
});

describe("French covers the public site (1 Oct 2026)", () => {
  const siteKeys = Object.keys(en).filter((k) =>
    /^(d|nav\.site|footer|ov|live|wx|sn|ops|map)\./.test(k),
  );

  it("has site, ops and map keys to translate", () => {
    expect(siteKeys.length).toBeGreaterThan(200);
  });

  it("French differs from English for long prose (nothing left as untranslated English)", () => {
    // Short labels and product terms may legitimately match ("Vision", "Contact", "GitHub").
    const same = siteKeys.filter(
      (k) => en[k as keyof typeof en].length > 40 && fr[k as keyof typeof en] === en[k as keyof typeof en],
    );
    expect(same).toEqual([]);
  });

  it("keeps the honesty wording in both languages", () => {
    // d.k54d1eb25 is the footer line; d.kae5ffbda answers "Has this been tested in the field?"
    expect(en["d.k54d1eb25"]).toMatch(/^Software prototype, simulated and bench-tested\./);
    expect(en["d.kae5ffbda"]).toMatch(/^Not yet\./);
    expect(fr["d.k54d1eb25"]).toMatch(/simulé et testé sur banc d’essai/);
    expect(fr["d.kae5ffbda"]).toMatch(/^Pas encore\./);
    expect(en["d.k6c1bfbe7"]).toBe("88/88 simulation requirements");
    expect(fr["d.k6c1bfbe7"]).toMatch(/88\/88/);
    // "bench-tested" is never turned into "validated" in French.
    for (const k of siteKeys) expect(fr[k as keyof typeof en], k).not.toMatch(/validé en banc/);
    expect(en["shell.demo"]).toMatch(/DEMO MODE/);
    expect(fr["shell.demo"]).toMatch(/MODE DÉMO/);
  });

  it("never claims what the prototype cannot", () => {
    // A denial ("not yet field-proven", "pas éprouvé") is the honest wording; only an affirmative claim fails.
    const banned = /(?<!not yet )(?<!not )\b(field[- ]proven|flight[- ]proven|validated in the field|our customers|testimonial|\d+\s?% (accuracy|more)|revenue of|\$\s?\d)/i;
    for (const k of siteKeys) {
      expect(en[k as keyof typeof en], k).not.toMatch(banned);
      expect(fr[k as keyof typeof en], k).not.toMatch(banned);
    }
  });
});
