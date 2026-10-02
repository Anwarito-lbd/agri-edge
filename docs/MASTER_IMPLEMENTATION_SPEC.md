# MASTER IMPLEMENTATION SPEC (governing)

**Source:** product owner brief. Full phase text retained in conversation; this file is the durable summary agents must follow.

## Mission
Closed loop: SENSE → UNDERSTAND → GEOREFERENCE → DECIDE → SAFETY → ACT → MEASURE → LOG → MAP → LEARN. Agri-Edge is the integration brain; third parties are components.

## Rules
1. AI never directly controls flight motors / LLM never drives FC actuators.
2. FC owns attitude, mixing, failsafes. Linux may later command missions only through adapters + safety.
3. Payload safety independent of AI confidence alone.
4. Every external system behind an adapter interface.

## Current vs future
- **Today:** Pi companion **MAVLink read-only**; treatment gated; ground MQTT irrigation separate.
- **Later:** VehicleAdapter may expose mission/arm for SITL and approved ops — never bypass safety supervisor.
- **Edge Profile A (now):** Pi 5 + Hailo. **Profile B (later):** Jetson-class. Do not block MVP on Jetson.
- **Autopilot:** Keep ArduPilot SITL working; ADR-0001 for PX4 long-term; do not dual-support in product early.

## Immediate priority order
1. Repo audit (Phase 0)  
2. Dev environment + CI  
3. Validate YOLOX pipeline  
4. YOLOX → ONNX → Hailo HEF → Pi inference  
5. Camera → Hailo live  
6. Normalized Detection API  
7. MQTT (vehicle + ground)  
8. Backend/PostGIS  
9. Dashboard decisions UI  
10. ArduPilot SITL + VehicleAdapter  
… then georef hardening, tracking, decision/safety, simulated actuator, OWL integration, water-only bench, mapping, farmOS, AgOpenGPS, PX4 eval.

## First meaningful product milestone
REAL CAMERA → Pi 5 → Hailo → YOLOX → normalized detections → MQTT → dashboard. No autonomous physical treatment until that is reliable.

## Definition of done
Implementation + tests + docs + no secrets. Hardware tasks need explicit VALIDATED status (IMPLEMENTED / SIMULATED / BENCH / HARDWARE / FIELD).

---

## Phase checklist (master priorities 3–10) — updated 2026-09-19

| # | Item | Status | Evidence |
|---|------|--------|----------|
| 3 | YOLOX pipeline validate | **DONE** | `tests/test_yolox_postprocess.py` (36 passed); interface in `docs/status.md` |
| 3b | YOLOX→ONNX export path | **DONE** (BENCH deps) | `training/export_onnx.py` + `scripts/export_yolox_onnx.py` |
| 4 | Hailo compile ONNX→HEF | **SIMULATED** | `scripts/hailo_compile.sh` + `scripts/hailo_compile.ps1` + `docs/architecture/hailo-compile.md` |
| 4b | HEF inference on AI HAT | **BLOCKED-HARDWARE** | Needs Pi + HailoRT + real `.hef` |
| 5 | Live camera on Pi | **BLOCKED-HARDWARE** | Capture scripts exist; no device this wave |
| 6 | Normalized Detection API | **DONE** | `src/agri_edge/detection/` — Detection + DetectionBackend + CpuOnnx/Hailo/Simulated |
| 6b | Model registry | **DONE** | `src/agri_edge/ai/registry.py` + `ai/model_registry/registry.json` |
| 7 | MQTT vehicle + ground | **PARTIAL** / ingest **BENCH** | Topic helpers, ACL'd broker, edge publisher, subscribe-only ingest (`ops/live_ingest.py`) run against a real Mosquitto on the build box 2026-10-02. Still no edge publisher on real hardware |
| 8 | Backend SQLite/PostGIS | **DONE** / PostGIS **BENCH** (real PostGIS 17 on the build box, 2026-10-02; not production) | `src/agri_edge/ops/db.py` sensors+detections; `docs/operations/schema_postgis.sql`; `/api/ops/detections` |
| 9 | Dashboard decisions UI | **DONE** (SIMULATED data, read-only) | `/ops/decisions.html` + `GET /api/ops/decisions` over the decision engine event log: treated/skipped/refused counts, refusals per gate, recent table, armed/geofence/mission readout; no write route, no controls; `tests/test_ops_decisions.py` (2026-10-02) |
| 10 | VehicleAdapter + ArduPilot stub | **DONE** (SIMULATED cmds) | `src/agri_edge/vehicle/` fail-closed; SITL `scripts/sitl.sh` kept |
| CI | Makefile `test`/`lint` + GHA | **DONE** | `Makefile`, `.github/workflows/test.yml` |
| Licences | `third_party/manifest.yaml` | **DONE** | + NOTICE.md pointer |
| Ops Station §79–166 | **80 DONE / 8 PARTIAL** | Re-graded 2026-09-24; demo data only | `docs/operations/PHASE_CHECKLIST_79_166.md` |

### Explicitly BLOCKED-HARDWARE (this wave)
- Live camera on Pi
- Real HEF inference on AI HAT
- Physical spray / actuator
- Field radios

## Phase status table — 2026-10-02

Phase status key: DONE / SIMULATED / BENCH / BLOCKED-HARDWARE. Updated 2026-10-02 (`feat/batch2`).

| Phase | Status | Evidence / note |
|-------|--------|-----------------|
| Ops Station §79–166 | **DONE** 88/88 sim-complete | `docs/operations/PHASE_CHECKLIST_79_166.md`; simulation only, not field-validated |
| MQTT ingest (subscribe-only) | **BENCH** | `src/agri_edge/ops/live_ingest.py`, [`docs/operations/MQTT_INGEST.md`](operations/MQTT_INGEST.md); passed against a real Mosquitto 2.0.21 on the build box (loopback, synthetic); CI job drafted in `docs/ci/` (not active, never run on GitHub) |
| PostGIS backend option | **BENCH** | `src/agri_edge/ops/postgis.py`, [`docs/operations/POSTGIS_BACKEND.md`](operations/POSTGIS_BACKEND.md); live tests passed against a throwaway PostgreSQL 17 + PostGIS 3.5 on the build box (not production); SQLite remains the default |
| PostGIS compose file never run | **SIMULATED** (never run) | `ground_iot/docker-compose.postgis.yml` never started (no Docker on the build box); YAML parsed and its init SQL applied via `psql` only |
| Georeferencing (pose-validated) | **SIMULATED** | `src/agri_edge/geo/georef.py`; unit-tested maths, no real camera/GNSS |
| Treatment decision engine + simulated actuator | **SIMULATED** | `src/agri_edge/decision/engine.py`; fail-closed gates, simulated actuator only |
| farmOS HTTP client | **BENCH** (mock only) | `adapters/farmos_http.py`; `allow_network=True` gate; never run against a real farmOS |
| AgOpenGPS read-only observer | **SIMULATED** | `adapters/agopengps_pgn.py`, `agopengps_udp.py`; receive-only; SIMULATED packets; layout partly UNVERIFIED; guidance commands refused |
| Ops decisions dashboard (#9) | **SIMULATED** | read-only; `ops/decisions.py`, `ui/decisions.html` |
| Water-only bench test plan | **BLOCKED-HARDWARE** | `docs/mechanical/WATER_ONLY_BENCH_TEST_PLAN.md`; nothing executed |
| PX4 evaluation | **evaluation only** | `docs/architecture/px4-evaluation.md`; ArduPilot SITL stays primary |
| Live Pi camera | **BLOCKED-HARDWARE** | no Pi camera on hand |
| Real HEF + HailoRT on the AI HAT | **BLOCKED-HARDWARE** | needs Pi + AI HAT + HailoRT + a compiled `.hef` |
| Actuators and pumps | **BLOCKED-HARDWARE** | no physical treatment hardware |
| Field radios | **BLOCKED-HARDWARE** | no radios / gateways deployed |

No row in this table has hardware or field evidence; none is claimed as validated.

### Safety reminders
- No YOLO/LLM → motors
- Companion MAVLink read-only unless behind VehicleAdapter + safety supervisor (fail closed)
- No AI → unrestricted pump; treatment needs `validated_locally` + geofence + arm + freshness
- Irrigation: ground MQTT only
