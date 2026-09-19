# Capability status

**Updated:** 2026-09-19 (America/Toronto) — master priorities 3–10 advanced in software.

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
| Ground MQTT topics | ✅ | ✅ | ⏳ | ⏳ |
| Mosquitto + Node-RED compose | ✅ | ⏳ | N/A | N/A |
| Thermal / MS indices | ✅ | ✅ | ⏳ cams | ⏳ |
| RelateAnything | hook only | ⏳ | N/A laptop | ❌ |
| Companion phone UI | agri-edge-web | Demo | N/A | N/A |
| ArduPilot SITL | script | ⏳ | N/A | N/A |
| Decision / safety supervisor (flight cmd) | ✅ stub | ✅ | ❌ | ❌ |
| Physical treatment actuator | ❌ | ❌ | ❌ BLOCKED | ❌ |
| Postgres / PostGIS schema | ✅ SQL | ✅ SQLite path | ⏳ PG deploy | ❌ |
| SQLite SensorReading + detections | ✅ | ✅ | N/A | N/A |
| Detections HTTP API | ✅ | ✅ | N/A | N/A |
| CI (Makefile + GHA pytest) | ✅ | ✅ | N/A | N/A |
| third_party/manifest.yaml | ✅ | N/A | N/A | N/A |
| `validated_locally` | flag false | N/A | ⏳ | ❌ |

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

Checklist: `docs/operations/PHASE_CHECKLIST_79_166.md` — DONE 88/88. **Do not redo.**  
Run: `python -m agri_edge.ops.api` → http://127.0.0.1:8765/ops/
