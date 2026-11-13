import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const root = join(__dirname, "..", "src");
const css = readFileSync(join(root, "styles", "tokens.css"), "utf8");
const globals = readFileSync(join(root, "app", "globals.css"), "utf8");
const json = JSON.parse(readFileSync(join(root, "styles", "tokens.json"), "utf8")) as {
  color: Record<string, string>;
  motion: Record<string, string>;
};

function cssVar(name: string): string | undefined {
  const m = css.match(new RegExp(`--ae-${name}:\\s*([^;]+);`));
  return m?.[1]?.trim();
}

describe("design v2 tokens", () => {
  it("every colour in tokens.json is the same value in tokens.css", () => {
    for (const [name, value] of Object.entries(json.color)) {
      expect(cssVar(name)?.toUpperCase(), `--ae-${name}`).toBe(value.toUpperCase());
    }
  });

  it("motion tokens match", () => {
    expect(cssVar("dur-fast")).toBe(json.motion.fast);
    expect(cssVar("dur-base")).toBe(json.motion.base);
    expect(cssVar("ease")?.replace(/\s/g, "")).toBe(json.motion.ease.replace(/\s/g, ""));
  });

  it("globals.css pulls the tokens in and exposes them to Tailwind", () => {
    expect(globals).toMatch(/@import "\.\.\/styles\/tokens\.css"/);
    for (const c of ["navy", "paper", "sim-bg", "sim-border", "sim-text", "primary-dark"]) {
      expect(globals, c).toContain(`--color-${c}:`);
    }
  });

  it("keeps cyan and paper in their lane (no gradients, no green)", () => {
    expect(css).not.toMatch(/gradient\(/);
    expect(css.toLowerCase()).not.toMatch(/#1f5c2e/);
  });
});
