# Capability status

**Updated:** 2026-09-24 — second verification audit (docs/audit-2026-09-24.md): 15 defects fixed with tests (safety gates, ops API write surface, MQTT broker, telemetry freshness, spool, Hailo decode, Camera Module 3 geometry); ops checklist re-graded 80 DONE / 8 PARTIAL. Previous: 2026-09-20 (America/Toronto) — WSL2 installed; ArduCopter SITL built and the pipeline verified against it (14/14, 10 frames spooled with real EKF telemetry). Verification audit in docs/audit-2026-09-19.md. CI green on both repos.

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
| farmOS client | ✅ | stub | ⏳ | ⏳ |
| WebODM client | ✅ | stub | ⏳ | ⏳ |
| Ground MQTT topics (helpers + ACL'd broker) | ✅ | ⏳ nothing publishes or ingests yet | ⏳ | ⏳ |
| Edge → MQTT detection publisher | ❌ | ❌ | ❌ | ❌ |
| Ops store ingestion (MQTT/HTTP → store) | ❌ | ❌ | N/A | ❌ |
| Mosquitto + Node-RED compose | ✅ | ⏳ | N/A | N/A |
| Thermal / MS indices | ✅ | ✅ | ⏳ cams | ⏳ |
| RelateAnything | hook only | ⏳ | N/A laptop | ❌ |
| Companion phone UI | agri-edge-web | Demo | N/A | N/A |
| ArduPilot SITL | ✅ | ✅ **built + run** | N/A | N/A |
| Pipeline vs real autopilot telemetry | ✅ | ✅ 14/14 + 10 frames spooled | ⏳ | ⏳ |
| WSL2 toolchain (Stage 0) | ✅ | ✅ | ✅ | N/A |
| Decision / safety supervisor (flight cmd) | ✅ stub | ✅ | ❌ | ❌ |
| Physical treatment actuator | ❌ | ❌ | ❌ BLOCKED | ❌ |
| Postgres / PostGIS schema | ✅ SQL | ✅ SQLite path | ⏳ PG deploy | ❌ |
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
