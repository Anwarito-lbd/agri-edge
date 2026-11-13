# Case Study: Designing a Fail-Closed Web & Ops Station Interface for `agri-edge`

## Problem & Context

When I built the web interface for **agri-edge** — a Canadian under-25 kg agricultural RPAS companion computer prototype (Raspberry Pi 5 + Hailo AI HAT + Pixhawk/Cube) — I wanted a single codebase that could serve three different audiences without ever blurring the line between a software prototype and a flight-ready system:

1. **Growers and investors** evaluating the product on `/`, `/product`, `/hardware`, `/vision`, and `/proof`.
2. **Operators and agronomists** reviewing field boundaries, satellite NDVI decline patches, detections, and ISOXML/shapefile prescriptions in the Operations Station (`/ops/*`).
3. **Field reviewers** inspecting the read-only mobile companion shell (`/app`) and mock field dashboard (`/dashboard`).

The core engineering constraint was **safety and honesty by construction**: a web UI for an aerial scouting prototype must never masquerade as live telemetry when disconnected, and it must never expose an accidental path to arm, disarm, or command an aircraft.

---

## Architecture Decisions

### 1. Fail-Closed Ops Proxy (`/api/ops/[...path]`)

Rather than letting the browser talk directly to an engineering backend, every `/ops/*` screen calls same-origin `/api/ops/...`, which is gated by `src/app/api/ops/[...path]/route.ts` and `src/lib/ops-proxy-policy.ts`:

- **Default-deny writes:** Only `POST` requests with `Content-Type: application/json`, same-origin `Origin`/`Host` matching, and an explicit allowlisted route can pass through.
- **Vehicle-action blocks:** Routes such as `seed`, `detections`, `ingest`, `auth/users`, and any vehicle-command verbs (`arm`, `takeoff`, `mission`, `pump`, etc.) are blocked before a request is ever constructed.
- **httpOnly session cookies:** When authentication is enabled (`OPS_AUTH=1`), `/login` stores the session token in an `httpOnly`, `SameSite=Strict` cookie (`ae_session`) so page scripts can never read it, and the proxy forwards it upstream as `Authorization: Bearer ...`.

### 2. Deterministic Demo Mode vs. Live Ops API

When `OPS_API_URL` is unset (for example, in a static/preview deployment), `/api/ops/[...path]` does not throw a broken error page and does not invent random numbers. Instead, `src/lib/ops-demo.ts` returns deterministic synthetic payloads tagged with `demo: true`, `simulation: true`, `synthetic: true`, and `banner: "SIMULATION"`, while refusing all writes.

For the drone survey replay on `/ops/map` and `/ops/live`, `src/lib/ops-scenario.ts` computes a deterministic 15-minute (`t+00:00` to `t+15:00`) lawn-mower survey path (`surveyPath`), aircraft interpolation (`pathAt`), altitude/groundspeed SVG traces (`tracePoints`), and progressive detection reveal (`detectionShowAt`) as pure functions of synthetic seconds `t`.

### 3. Read-Only Companion Feed (`/app` & `/api/v1/stream`)

To demonstrate the Raspberry Pi 5 companion UX without requiring hardware on a desk, `src/app/api/v1/stream/route.ts` streams Server-Sent Events (SSE) every ~2 seconds from `src/lib/mock-pi/state.ts`. I chose SSE over WebSockets so it deploys cleanly on serverless runtimes, and restricted mutations to alert acknowledgement (`POST /api/v1/alerts/[id]/ack`) while keeping MAVLink strictly listen-only.

### 4. Graceful Basemap Degradation & Bilingual Coverage

In `src/components/BasemapTiles.tsx`, if external OpenStreetMap tiles fail to load (for example, offline on a farm LAN or behind a restricted network), the map displays an explicit fallback notice after `TILE_FAILURE_THRESHOLD` (4) failed tiles while keeping all React-Leaflet vector polygons, survey lines, and detection markers interactive.

All public and ops copy is maintained in English and French (`src/lib/i18n.ts`, `src/lib/i18n-design.ts`, `src/lib/i18n-ops.ts`), and design tokens in `src/styles/tokens.css` are checked against `src/styles/tokens.json` in `tests/tokens.test.ts`.

---

## Verification & Evidence

The repository's invariants are enforced by **7 Vitest test suites (124 tests)**:

- `tests/api-safety.test.ts` (28 tests) — verifies mock-Pi route safety and forbidden command rejection.
- `tests/auth-and-proxy.test.ts` (26 tests) — verifies proxy allowlists, CSRF origin checks, and cookie handling.
- `tests/farmer-app.test.ts` (26 tests) — verifies companion shell safety labels and treatment-lock rules.
- `tests/ops-demo.test.ts` (24 tests) — verifies deterministic demo payloads and `synthetic: true` flags.
- `tests/ops-scenario.test.ts` (11 tests) — verifies scenario clock clamping, formatting, and survey path geometry.
- `tests/ops-banner.test.ts` (5 tests) — verifies simulation/demo banner state transitions.
- `tests/tokens.test.ts` (4 tests) — verifies CSS custom properties match `tokens.json`.

All pipeline imagery on `/proof` comes from real `agri-edge` evaluation outputs: `aerial_sheep_yolox_s` (**AP@.50 0.905**), ImageWeeds (species ~**0.457** / binary **0.673**), and CAD renders of the under-25 kg airframe.
