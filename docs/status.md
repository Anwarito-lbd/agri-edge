# Capability status

**Updated:** 2026-10-02 (America/Toronto) — batch 2 (`feat/batch2`): MQTT ingest and the PostGIS backend now have a BENCH run against a real Mosquitto 2.0.21 and a real PostgreSQL 17 + PostGIS 3.5 installed on the build box (throwaway, synthetic data; no bug found), a drafted but INACTIVE `live-services` CI job (`docs/ci/`; the push token lacked `workflow` scope), a read-only Ops decisions dashboard, a mock-tested farmOS HTTP client, a read-only AgOpenGPS UDP/PGN observer (SIMULATED packets), a water-only bench test plan (BLOCKED-HARDWARE) and a PX4 evaluation note (ArduPilot stays primary). Nothing VALIDATED. Previously 2026-10-01 — broker-path MQTT ingest (`ops/live_ingest.py`, subscribe-only), optional PostGIS backend, georeferencing, decision engine and farmOS/AgOpenGPS adapter stubs added, all SIMULATED (in-memory broker / throwaway PostGIS only; nothing VALIDATED). Previously (2026-09-24, later): roadmap items 1–7 built in software: edge → station ingest, Sentinel-2 change detection, agronomy (ET0 water balance, growth stage, disease and frost risk), ISOXML/shapefile prescriptions, ESP32/LoRaWAN sensors with per-device credentials, the field-training loop, and users/roles plus the farmer web app (agri-edge-web#3). None of it has run on hardware or against live services yet; see the rows below. Earlier the same day: second verification audit (docs/audit-2026-09-24.md): 15 defects fixed with tests (safety gates, ops API write surface, MQTT broker, telemetry freshness, spool, Hailo decode, Camera Module 3 geometry); ops checklist re-graded 80 DONE / 8 PARTIAL. Previous: 2026-09-20 (America/Toronto) — WSL2 installed; ArduCopter SITL built and the pipeline verified against it (14/14, 10 frames spooled with real EKF telemetry). Verification audit in docs/audit-2026-09-19.md. CI green on both repos.

**Legend:** Code = implemented in repo · Sim = works in sim/tests · Hardware = run on real device · Field = farm-validated  
Statuses: ✅ done · ⏳ partial/unproven · ❌ absent · N/A

| Component | Code | Sim | Hardware | Field |
|-----------|------|-----|----------|-------|
| YOLOX training / export ONNX | ✅ | N/A | N/A | N/A |
| YOLOX numpy decode / NMS | ✅ | ✅ | ⏳ | ⏳ |
| Export stub `scripts/export_yolox_onnx.py` | ✅ | ✅ dry-run | N/A | N/A |
| Green-on-brown (OWL port) | ✅ | ✅ | ⏳ | ⏳ |
| Tiled inference | ✅ | ✅ | ⏳ | ⏳ |
| Hailo compile script (.sh/.ps1) | ✅ | ⏳ docs | ⏳ | ⏳ |
| Hailo live inference | ⏳ stub API | ⏳ | ❌ BLOCKED | ❌ |
| Normalized Detection API | ✅ | ✅ | ⏳ | ⏳ |
| Model registry (sha256 schema) | ✅ | ✅ | N/A | N/A |
| Pi camera runtime | ✅ scripts | ⏳ | ❌ BLOCKED | ❌ |
| Georeference | ✅ | ✅ | ⏳ | ⏳ |
| Treatment geofence | ✅ | ✅ | ⏳ | ⏳ |
| MAVLink read-only | ✅ | ✅ | ⏳ | ⏳ |
| VehicleAdapter + ArduPilot stub | ✅ | ✅ fail-closed | ❌ BLOCKED cmds | ❌ |
| farmOS client | ✅ HTTP client (`adapters/farmos_http.py`) | ✅ local mock server, 24 tests | ❌ never run against a real farmOS | ❌ |
| AgOpenGPS read-only observer (UDP/PGN) | ✅ | ✅ SIMULATED packets over loopback | ❌ no real AgIO capture; layout partly UNVERIFIED | ❌ |
| Ops decisions dashboard (`/ops/decisions.html`, `/api/ops/decisions`) | ✅ read-only | ✅ synthetic demo through the simulated-only engine | N/A | ❌ |
| WebODM client | ✅ | stub | ⏳ | ⏳ |
| Ground MQTT topics (helpers + ACL'd broker) | ✅ | ✅ edge publishes, station ingests | ⏳ | ⏳ |
| Edge → MQTT detection publisher (`iot/edge_publisher.py`) | ✅ | ✅ | ⏳ | ❌ |
| Ops store ingestion (MQTT/HTTP → store, SQLite ingest log replayed on start) | ✅ | ✅ | N/A | ❌ |
| Weather adapter (Open-Meteo forecast) | ✅ | ✅ recorded fixtures | ⏳ live fetch unverified (blocked in the build sandbox) | ❌ |
| Agronomy: FAO-56 ET0, water balance, GDD/BBCH stage | ✅ | ✅ | N/A | ❌ not checked against a field |
| Disease risk (late blight, FHB, sclerotinia) + frost alerts | ✅ | ✅ | N/A | ❌ not checked against a season |
| Explained recommendations (why / missing / confidence / sources) | ✅ | ✅ | N/A | ❌ |
| Sentinel-2 STAC + SCL mask + NDVI change detection | ✅ | ✅ synthetic rasters | ⏳ live fetch unverified (blocked in the build sandbox) | ❌ |
| Prescriptions: ISOXML (ISO 11783-10) + shapefile | ✅ | ✅ | ❌ not loaded on a task controller | ❌ |
| ESP32 soil/weather (ESPHome) + LoRaWAN codec (ChirpStack) | ✅ | ✅ codec round-trip | ❌ not flashed | ❌ |
| Per-device MQTT credentials + device last-seen watch | ✅ | ✅ | ⏳ | ❌ |
| Field-training loop (walk / Label Studio / validate-model) | ✅ | ✅ | ❌ no field walk yet | ❌ |
| Ops users, roles, sessions; audit names the person | ✅ | ✅ | N/A | N/A |
| Farmer web app: login, offline PWA, French (agri-edge-web) | ✅ | ✅ end-to-end vs ops API | ⏳ not tried in a phone browser | ❌ |
| Mosquitto + Node-RED compose | ✅ | ⏳ (compose itself never started: no Docker on the build box) | N/A | N/A |
| Live-services CI job (`docs/ci/live-services.yml`, **not active**: push token lacked `workflow` scope) | ✅ written | never run on GitHub | N/A | N/A |
| Thermal / MS indices | ✅ | ✅ | ⏳ cams | ⏳ |
| RelateAnything | hook only | ⏳ | N/A laptop | ❌ |
| Companion phone UI | agri-edge-web | Demo | N/A | N/A |
| ArduPilot SITL | ✅ | ✅ **built + run** | N/A | N/A |
| Pipeline vs real autopilot telemetry | ✅ | ✅ 14/14 + 10 frames spooled | ⏳ | ⏳ |
| WSL2 toolchain (Stage 0) | ✅ | ✅ | ✅ | N/A |
| Decision / safety supervisor (flight cmd) | ✅ stub | ✅ | ❌ | ❌ |
| Physical treatment actuator | ❌ | ❌ | ❌ BLOCKED | ❌ |
| Postgres / PostGIS schema | ✅ SQL | ✅ SQLite path; **BENCH** vs real PostgreSQL 17 + PostGIS 3.5 on the build box (not production) | ⏳ PG deploy | ❌ |
| SQLite SensorReading + detections | ✅ | ✅ | N/A | N/A |
| Detections HTTP API | ✅ | ✅ | N/A | N/A |
| CI (Makefile + GHA pytest) | ✅ | ✅ | N/A | N/A |
| third_party/manifest.yaml | ✅ | N/A | N/A | N/A |
| `validated_locally` | flag false | N/A | ⏳ | ❌ |
| Airframe spec + Blender model | ✅ | ✅ | N/A | N/A |
| agri-edge-web tests + CI | ✅ | ✅ | N/A | N/A |
| Ops proxy write policy (fail closed) | ✅ | ✅ | N/A | N/A |
| Lean-runner check (`make test-lean`) | ✅ | ✅ | N/A | N/A |
| Hailo compile `--dry-run` | ✅ | ✅ | ❌ BLOCKED no WSL2 | ❌ |

Do not mark Hardware/Field green without evidence.

## Phase status (DONE / SIMULATED / BENCH / BLOCKED-HARDWARE) — updated 2026-10-02

| Phase | Status | Evidence / note |
|-------|--------|-----------------|
| Ops Station §79–166 | **DONE** 88/88 sim-complete | `docs/operations/PHASE_CHECKLIST_79_166.md`; simulation only, not field-validated |
| MQTT ingest (subscribe-only) | **BENCH** | `src/agri_edge/ops/live_ingest.py`, [`docs/operations/MQTT_INGEST.md`](operations/MQTT_INGEST.md); `tests/test_ops_ingest_broker.py` and `tests/test_live_services_e2e.py` passed against a real Mosquitto 2.0.21 started on the build box (loopback, anonymous, synthetic data). Not the repo's ACL'd broker config, not a farm broker, no real edge publisher |
| PostGIS backend option | **BENCH** | `src/agri_edge/ops/postgis.py`, [`docs/operations/POSTGIS_BACKEND.md`](operations/POSTGIS_BACKEND.md); `tests/test_ops_postgis.py` (all live tests, none skipped) + `tests/test_live_services_e2e.py` (MQTT → ingest → PostGIS, `ST_DWithin` query) passed against a throwaway PostgreSQL 17 + PostGIS 3.5 on the build box. Not production, not the `postgis/postgis:16-3.4` image. SQLite remains the default |
| PostGIS compose file never run | **SIMULATED** (never run) | `ground_iot/docker-compose.postgis.yml` has never been started: Docker is not installed on the build box, so `docker compose config` was not possible. Only the YAML was parsed, and its init script `docs/operations/schema_postgis.sql` was applied with `psql -v ON_ERROR_STOP=1` to a fresh database (7 tables created). Nothing run against production PostGIS |
| Georeferencing (pose-validated) | **SIMULATED** | `src/agri_edge/geo/georef.py`; unit-tested maths, no real camera/GNSS |
| Treatment decision engine + simulated actuator | **SIMULATED** | `src/agri_edge/decision/engine.py`; fail-closed gates, simulated actuator only |
| farmOS HTTP client | **BENCH** (mock only) | `src/agri_edge/adapters/farmos_http.py`, [`docs/operations/FARMOS_ADAPTER.md`](operations/FARMOS_ADAPTER.md); behind `allow_network=True`; 24 tests against a local mock server; **never run against a real farmOS** (payload acceptance UNVERIFIED) |
| AgOpenGPS read-only observer | **SIMULATED** | `src/agri_edge/adapters/agopengps_pgn.py`, `agopengps_udp.py`, [`docs/operations/AGOPENGPS_ADAPTER.md`](operations/AGOPENGPS_ADAPTER.md); receive-only, all guidance commands refused; packets constructed from the public PGN list, layout partly UNVERIFIED; no real AgIO capture |
| Ops decisions dashboard | **SIMULATED** | `src/agri_edge/ops/decisions.py`, `ui/decisions.html`, `GET /api/ops/decisions`; read-only (no write route, no controls); demo data is a synthetic run of the simulated-only engine |
| Water-only bench test plan | **BLOCKED-HARDWARE** | [`mechanical/WATER_ONLY_BENCH_TEST_PLAN.md`](mechanical/WATER_ONLY_BENCH_TEST_PLAN.md); plan only, nothing executed, no rig |
| PX4 evaluation | **evaluation only** | [`architecture/px4-evaluation.md`](architecture/px4-evaluation.md); ArduPilot SITL stays primary; no PX4 run exists, PX4-integration claims UNVERIFIED |
| Live Pi camera | **BLOCKED-HARDWARE** | no Pi camera on hand |
| Real HEF + HailoRT on the AI HAT | **BLOCKED-HARDWARE** | needs Pi + AI HAT + HailoRT + a compiled `.hef` |
| Actuators and pumps | **BLOCKED-HARDWARE** | no physical treatment hardware |
| Field radios | **BLOCKED-HARDWARE** | no radios / gateways deployed |

No row in this table has hardware or field evidence; none is claimed as validated. BENCH here means: run on the build box against real, throwaway software services (or a mock), with synthetic data. It is not hardware evidence and not production.

## YOLOX / Detection interface (priority 3 + 6)

- **Decode:** `agri_edge.inference.yolox` — letterbox (pad 114, top-left), raw head decode, class-wise NMS.
- **Public Detection:** `agri_edge.detection.Detection` (re-export of `inference.engine.Detection`).
- **Backends:** `SimulatedBackend`, `CpuOnnxBackend`, `HailoBackend` — return `InferenceResult` only; no HailoRT/ORT types leak.
- **Treatment gate:** `may_drive_treatment` ⇒ `validated_locally and in_treatment_zone is True` (fail closed).
- **Export:** `training/export_onnx.py` (real) · `scripts/export_yolox_onnx.py` (documented wrapper).
- **Hailo:** `scripts/hailo_compile.sh` / `.ps1` — SIMULATED until DFC+device evidence.

## Ops Station (§79–166)

| Component | Code | Sim | Hardware | Field |
|-----------|------|-----|----------|-------|
| Ops Station domain + API | ✅ | ✅ | N/A | ❌ |
| SIMULATION UI Release-1 | ✅ | ✅ | N/A | N/A |
| Alert engine ACK/RESOLVE | ✅ | ✅ | ⏳ notify | ❌ |
| Map GeoJSON layers | ✅ | ✅ | ⏳ | ❌ |
| Irrigation rule skeleton | ✅ | ✅ | ⏳ MQTT | ❌ |
| VRA + ODM + 3D | partial/stub | ✅ | ❌ | ❌ |

Checklist: `docs/operations/PHASE_CHECKLIST_79_166.md` — **80 DONE / 8 PARTIAL** after the 24 Sept re-grade. Everything runs on seeded demo data; the PARTIAL rows name what is missing (ingestion, persistence, roles, real weather). Do not redo the DONE rows.  
Run: `python -m agri_edge.ops.api` → http://127.0.0.1:8765/ops/
