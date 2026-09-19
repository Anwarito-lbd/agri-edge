# AGENTS.md — agri-edge

## Governing docs
- `docs/MASTER_IMPLEMENTATION_SPEC.md` — phased build order and rules
- `docs/TARGET_ARCHITECTURE.md` — agri-edge as the brain
- `docs/repo-audit.md` / `docs/status.md` — baseline honesty

## Non-negotiables
1. AI never directly drives motors or payload GPIO.
2. Flight-critical control stays in the FC firmware.
3. Companion computer MAVLink toward aircraft is **read-only** today; mission commands only later via `VehicleAdapter` + safety supervisor.
4. Treatment requires validated_locally + geofence + payload arm + freshness (fails closed).
5. Third parties via adapters; do not vendor Node-RED/farmOS/ArduPilot into `src/`.
6. Preserve working tests; no giant untested refactors.

## Phase discipline
Follow MASTER spec priority order. Phase 0 (audit) before Hailo/camera major work. Every cycle report: COMPLETED / FILES / COMMANDS / TESTS / WORKS / SIMULATED / HARDWARE / RISKS / NEXT.

## Website
Product site lives in separate repo `Anwarito-lbd/agri-edge-web` — do not merge into this tree.
