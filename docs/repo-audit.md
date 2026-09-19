# Repository audit — agri-edge

**Date:** 19 September 2026 (America/Toronto)  
**Tree:** `C:\Users\issao\OneDrive\Desktop\agricultrul`  
**Remote:** `Anwarito-lbd/agri-edge` (private). Website is **separate**: `Anwarito-lbd/agri-edge-web`.

## Languages / frameworks
| Area | Stack |
|------|--------|
| Edge runtime | Python 3, numpy, PyYAML, onnxruntime (extras), picamera2 on Pi |
| Tests | pytest (~606 historically; see command table) |
| Training | YOLOX (vendor), torch on workstation |
| Ground IoT | Docker Compose: Mosquitto + Node-RED (`ground_iot/`) |
| Mechanical | Blender scripts, STL/GLB handoff |
| Frontend product | Next.js in **agri-edge-web** (not this tree) |

## Top-level layout (non-vendor)
```
agricultrul/
  AGENTS.md, README.md, HANDOFF.md, NOTICE.md, pyproject.toml
  src/agri_edge/     # package
  tests/
  scripts/           # pi_setup, sitl, hailo_compile, bootstrap_pi, laptop_relate
  training/          # export_onnx, train_resilient, exps, …
  models/            # *.onnx + CARD.md meta (not huge .pth in git ideally)
  config/
  docs/
  ground_iot/        # mosquitto + node-red compose
  mechanical/handoff/
  workstation/
  vendor/            # gitignored clones (YOLOX, hailo_*, ardupilot, OWL, AgOpenGPS)
  weights/, data/, runs/, YOLOX_outputs*/  # local artifacts
```

## `src/agri_edge` packages
| Package | Role |
|---------|------|
| `capture/` | Camera / frame sources |
| `inference/` | `yolox.py`, `greenonbrown.py`, `tiling.py`, `engine.py` |
| `geo/` | `georeference.py`, `geofence.py`, `calibration.py`, `coverage.py`, `indices.py` |
| `qa/` | Frame quality checks |
| `pipeline/` | End-to-end edge pipeline |
| `telemetry/` | **MAVLink read-only** `mavlink_link.py`, NTRIP |
| `sensors/` | environment, **thermal**, **multispectral** |
| `iot/` | MQTT topics + optional Mosquitto bridge |
| `relations/` | RelateAnything laptop hook (licence-gated) |
| `store/` | farmOS client, spool |
| `cli.py`, `config.py` | Entry / settings |

## YOLOX path (do not rewrite lightly)
- Train/export: `training/export_onnx.py`, `training/exps/*`, `training/train_resilient.py`
- Runtime decode: `src/agri_edge/inference/yolox.py`
- Models on disk: `models/aerial_sheep_yolox_s.onnx`, `imageweeds_yolox_s.onnx`, `weed_crop_yolox_s.onnx`, (+ meta/CARD)
- Vendor: `vendor/YOLOX` (Apache-2.0)

## Hailo
- `scripts/hailo_compile.sh` → expects WSL/x86_64 + `hailomz` + `vendor/hailo_model_zoo`
- `vendor/hailo-rpi5-examples` reference
- **Not hardware-validated** on this machine yet (no AI HAT run recorded)

## ArduPilot / SITL
- `scripts/sitl.sh` + `vendor/ardupilot`
- **SITL not validated** here (needs WSL/POSIX build tools)

## Ground IoT
- `ground_iot/docker-compose.yml` — Mosquitto `:1883`, Node-RED `:1880`
- Topics: `docs/MQTT_CONTRACT.md`
- Code: `src/agri_edge/iot/mqtt_topics.py`

## Secrets / hygiene
- farmOS credentials from **env** (not config file) — good
- Mosquitto compose currently `allow_anonymous` — **demo only**
- Do not commit `.env` with passwords; add `.env.example` in Phase 1

## Large / generated (keep out of git)
`vendor/`, `weights/`, `YOLOX_outputs*`, `.venv`, heavy `data/`, local runs

## Command table

| Command | Purpose | Works? | Error / note | Required fix |
|---------|---------|--------|--------------|--------------|
| `pytest tests/test_sensing_p1.py tests/test_mqtt_topics.py` | P1 sensing + MQTT | **Yes** (12 passed, 2026-09-19) | — | Keep green |
| `pytest` (full) | Full suite | **Likely** historically ~606; re-confirm after Phase 1 | Slow / env | `make test` wrapper |
| `bash scripts/sitl.sh` | ArduPilot SITL | **No** on Windows host | Needs WSL | Stage 0 WSL |
| `bash scripts/hailo_compile.sh` | ONNX→HEF | **No** here | Needs WSL + DFC | Stage 0 + Hailo account |
| `bash scripts/pi_setup.sh` | Pi image deps | **Not run** | Run on Pi Bookworm | Flash SD tomorrow+ |
| `docker compose -f ground_iot/docker-compose.yml up -d` | MQTT + Node-RED | **Untested** here | Needs Docker Desktop | Install Docker |
| `npm` / frontend | Product UI | N/A in this repo | Use agri-edge-web | Separate CI |
| `make bootstrap/lint/test` | Dev UX | **Missing** | — | Phase 1 Makefile |

## Dead / duplicate notes
- Website not duplicated here (correct split)
- OWL algorithms already **ported** to `greenonbrown.py` — vendor is reference
- AgOpenGPS vendor = guidance reference; geofence concepts in `geo/geofence.py`
