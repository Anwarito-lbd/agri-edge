import { describe, expect, it } from "vitest";

import { en, fr } from "@/lib/i18n";
import { OPS_BANNER_DETAIL, OPS_BANNER_HEADLINE, opsBannerMode } from "@/lib/ops-banner";

const base = { cachedAt: null, offline: false, demo: false, simulation: false, known: true };

describe("ops banner: one persistent amber SIMULATION bar", () => {
  it("always resolves to a mode, so the banner never disappears", () => {
    for (const cachedAt of [null, "2026-01-01T00:00:00Z"])
      for (const offline of [false, true])
        for (const demo of [false, true])
          for (const simulation of [false, true])
            for (const known of [false, true]) {
              const m = opsBannerMode({ cachedAt, offline, demo, simulation, known });
              expect(OPS_BANNER_DETAIL[m]).toBeTruthy();
            }
  });

  it("assumes simulation until the first answer arrives", () => {
    expect(opsBannerMode({ ...base, known: false })).toBe("sim");
  });

  it("merges PR #4's DEMO banner into the same bar as its detail line", () => {
    expect(opsBannerMode({ ...base, demo: true, simulation: true })).toBe("demo");
    expect(OPS_BANNER_DETAIL.demo).toBe("shell.demo");
  });

  it("offline and cached states keep the SIMULATION headline too", () => {
    expect(opsBannerMode({ ...base, offline: true })).toBe("offline");
    expect(opsBannerMode({ ...base, cachedAt: "x" })).toBe("cached");
  });

  it("headline and every detail line exist in EN and FR", () => {
    for (const k of [OPS_BANNER_HEADLINE, ...Object.values(OPS_BANNER_DETAIL)]) {
      expect(en[k], k).toBeTruthy();
      expect(fr[k], k).toBeTruthy();
    }
    expect(en[OPS_BANNER_HEADLINE]).toMatch(/^SIMULATION/);
    expect(fr[OPS_BANNER_HEADLINE]).toMatch(/^SIMULATION/);
  });
});
