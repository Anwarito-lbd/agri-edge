import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  // The `@/*` -> `./src/*` alias is declared here rather than read from
  // tsconfig.json by vite-tsconfig-paths.
  //
  // The plugin resolves fine on Linux -- CI ran all 28 tests green -- and
  // stopped resolving on Windows with no change to tsconfig.json or to the test
  // file. A suite that passes in CI and fails only on the machine someone is
  // editing on is the worst of both: it wastes the developer's afternoon and
  // teaches them to distrust the runner.
  //
  // Its failure mode makes that worse. The alias is silently not registered,
  // the import falls through to node resolution, and vitest reports "no tests"
  // rather than a broken import -- which reads as an empty suite, not an error.
  //
  // Route paths here contain literal brackets (`api/ops/[...path]/route`), one
  // more thing for a glob-based resolver to disagree about across platforms.
  // An explicit alias has no discovery step to go wrong on either.
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    // The proxy tests exercise the live-forwarding path against a stubbed
    // fetch, so they need a backend to be "configured". Without OPS_API_URL
    // the app serves demo data (tests/ops-demo.test.ts covers that path and
    // clears this variable itself).
    env: { OPS_API_URL: "http://ops.test.invalid" },
    include: ["tests/**/*.test.ts"],
    // A file that fails to import reports "no tests" and can still exit 0 in
    // some configurations. It must not pass here.
    passWithNoTests: false,
  },
});
