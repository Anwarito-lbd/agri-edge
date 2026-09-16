# HANDOFF — agri-edge

Last updated: 16 Sept 2026. For an agent or person picking this up with no prior
context. Read this first, then [docs/HARDWARE_PLAN.md](docs/HARDWARE_PLAN.md) for
what to buy, then [docs/BUILD_NOTES.md](docs/BUILD_NOTES.md) for the reasoning
behind the findings.

---

## Goal

A **commercial** agricultural drone product for a two-person team: one writes all
the code, the other does mechanical and airframe work. Raspberry Pi 5 + Hailo AI
HAT companion computer alongside a Pixhawk autopilot, **under 25 kg**.

Started as "weed detection". Became a **platform**: the pipeline is use-case
agnostic, so a new capability is usually a model file or an I2C sensor, not a
rebuild. See [docs/USE_CASES.md](docs/USE_CASES.md).

**Licensing: permissive only.** Ultralytics YOLOv8/v11 (AGPL) and YOLOv6 (GPL)
are excluded deliberately. Never add `ultralytics` as a convenience. See
[NOTICE.md](NOTICE.md).

---

## Where it stands

**606 tests, no hardware required.** `pip install -e ".[dev]"` then `pytest`.

**Every software gap identified is now closed. Everything remaining is blocked on
hardware that does not exist.**

### Models (all finished)

| Model | Result |
|---|---|
| `aerial_sheep_yolox_s` — livestock | sheep AP@.50 **0.905** on 5,603 boxes. **Runs on a bare Pi, no accelerator.** |
| `imageweeds_yolox_s` — 5 prairie species | species AP@.50 **0.457**; binary `weed` 0.673 |
| `weed_crop_yolox_s` — binary, seedlings | weed AP@.50 0.749 — **pipeline proof only**, see below |

Per-species: horseweed **0.793**, ragweed **0.642**, kochia **0.624** are usable;
redrootpigweed 0.153 and waterhemp 0.073 are **not** — treat those two labels as
"a weed", not an identification.

### Subsystems

| Component | State |
|---|---|
| Edge pipeline: capture → QA → inference → indices → spool → provenance | Integration-tested |
| YOLOX decode / letterbox / NMS, pure numpy | Verified against YOLOX's torch impl to 1e-5 |
| Tiled inference | 2.3× more detections than whole-frame |
| Green-on-brown detection (OpenWeedLocator, MIT) | Classical ExG, 62 ms vs YOLOX's 270 ms, no NPU |
| **Detection georeferencing** | Ray-plane intersection → lat/lon + error budget |
| **Coverage planning** | Boustrophedon lines, heading search, 0% gaps |
| **Reflectance calibration** | Empirical-line from a panel; unlocks `calibrated=True` |
| **NTRIP / RTK corrections** | Written; goes to the GNSS receiver, never the autopilot |
| Treatment geofence | Flight vs treatment boundary, GeoJSON, wired into the pipeline |
| Spray advisory | Wind-first; refuses a verdict without wind |
| MAVLink telemetry | Read-only by construction, fault-injected against real protocol |
| farmOS / WebODM | Clients written, tested against stubs |
| Dependency boundary | Pi runtime imports with numpy + PyYAML alone, test-enforced |
| CI | Two jobs: lean (proves the boundary) + extras (proves the optional paths run) |

---

## The two safety contracts

**1. The Pi cannot command the aircraft.** `telemetry/mavlink_link.py` is
read-only by construction and a test asserts no write method exists. This is why
NTRIP corrections go to the GNSS receiver's own serial port rather than being
injected as MAVLink `GPS_RTCM_DATA` — the standard shortcut, deliberately not
taken. Adding a write path "just for corrections" gives the next thing that wants
to transmit a precedent.

**2. Treatment requires TWO conditions, and fails closed.**

```
may_drive_treatment = validated_locally AND in_treatment_zone is True
```

`None` means the question was never asked — no boundary configured, or the
detection could not be georeferenced — and an unasked question is not a yes.
Enabling treatment requires: fly your own fields → annotate → retrain → set
`validated_locally: true` → **and** supply `treatment_zone.boundary_geojson`.
Miss any one and nothing is treatable.

This computes the answer. The research report puts **enforcement** on the payload
MCU, independent of this computer, so a fault in Linux cannot open a valve.

---

## What worked

- **Looking at the imagery instead of trusting metrics.** Caught every major
  finding. Two datasets were not what their names claimed.
- **Verifying against an independent reference.** The numpy decoder against
  YOLOX's torch implementation; dew point against published psychrometrics;
  georeferencing against hand-computed geometry; `coverage_gaps` as a check on
  the planner that is *not* a restatement of it — it found two real bugs.
- **Checking datasets before spending on them.** Visual inspection and split-leak
  checks before any training.
- **Deriving the optics limits first.** `training/gsd_calculator.py` settled the
  product direction more decisively than any model result.

---

## What did NOT work — do not repeat

1. **`LibreYOLO/weed-crop-aerial` is not aerial.** "Aerial" is a Roboflow-100
   *category*. Ground-level close-ups plus **indoor propagation trays**; 98.3% of
   its `crop` labels come from the trays, and one test image contains a person's
   boot. Model 1 is a seedling detector. Never quote its numbers as field
   performance.
2. **Do not evaluate a model against a mismatched annotation.** Model 1 scored 2%
   recall on ImageWeeds while working correctly — a 12× size gap between what it
   detects and what that dataset labels.
3. **`ImageWeeds` labels only potted specimens.** Dozens of natural weeds per
   frame are unlabelled, so measured precision *understates* reality.
4. **`torch.onnx._export` no longer exists.** Use `training/export_onnx.py`.
5. **YOLOX's C++ COCOeval extension kills training at the first eval.** Every exp
   sets `sys.modules.setdefault("yolox.layers.fast_coco_eval_api", None)`. Keep
   that line in any new exp.
6. **YOLOX's default `max_labels` silently truncates dense scenes** (50 dataset,
   120 post-mosaic). The sheep data has up to 105 objects per image. See
   `aerial_sheep_yolox_s.py`.
7. **YOLOX prints "Training of experiment is done" even when it CRASHED** — it is
   in a `finally`. Check the last `epoch: N/TOTAL` instead.
8. **This GPU drops transient cuDNN faults.** Always launch via
   `training/train_resilient.py`.
9. **YOLOX `--resume` is broken on PyTorch 2.6+.** Fixed by `add_safe_globals` in
   each exp. Keep that block.
10. **Never put `| tail` before `&&`.** The pipe's exit code is `tail`'s, so a
    failed step still advances the chain.
11. **Only one training run at a time.** 8 GB VRAM fits exactly one YOLOX-s.
12. **Newline escapes inside heredoc-embedded Python strings corrupt the file.**
    Produced a literal newline inside a string literal *five* times, each an
    unterminated-string SyntaxError — including once while writing this entry.
    **Use the Edit tool for anything containing escape sequences.**
13. **A stale UDP sender makes a fault test pass spuriously.** A leftover
    `fake_autopilot` fed healthy packets into a GNSS-loss test and two frames
    "passed". Looked exactly like a QA bug. Every test in
    `test_mavlink_faults.py` now takes its own port.
14. **Don't run the full suite while training.** `cv2.resize` flaked once under
    memory pressure.
15. **`export_onnx.py` hardcoded `trained_on`, so every sidecar was wrong.** All
    three models claimed `weed-crop-aerial`, including a stock COCO model and one
    owing CC BY credit to a different paper. Provenance is now keyed on the exp's
    `data_dir` and an unregistered dataset **raises**.
16. **An abrupt kill looks nothing like a crash.** Log tail was nulls,
    `last_epoch_ckpt.pth` truncated, *no error*. Check for nulls before hunting
    an exception.
17. **`nvidia-smi` clock readings are unreliable here.** Trust `iter_time` in the
    training log.
18. **A belly camera follows the BELLY, not the wing.** Positive roll swings the
    view **west** when heading north; positive pitch swings it **north**.
    Opposite handedness. Getting roll backwards mirrors a whole flight about its
    own track and looks plausible frame by frame.
19. **`inference.confidence_threshold` means different things per backend.** A
    probability for YOLOX (0.30 = permissive), index strength for green-on-brown
    (field vegetation scores 0.10–0.20). The same 0.30 discards *everything* from
    green-on-brown. Set it explicitly when switching.
20. **A collapsed classification head can be undertraining, not a data limit.**
    At epoch 75 the species model put 76.2% of predictions in one class and
    collapsing to binary was right on that evidence. Finishing 150 epochs fixed
    it. **Finish the run before concluding what a model cannot do.**
21. **Check the WEIGHTS' licence, not just the repo's.** `RelateAnything` is
    Apache-2.0 code with DINOv3/Gemma-licensed weights — the artefact you would
    ship is not permissive. `DADIS` has **no licence at all** (all rights
    reserved). Both declined.

---

## Integrated projects

All cloned into gitignored `vendor/`. **No forks. No GPL or AGPL code is linked
into this tree.**

| Project | Licence | How |
|---|---|---|
| **OpenWeedLocator** | **MIT** | Code ported into `inference/greenonbrown.py` |
| **AgOpenGPS** | **Apache-2.0** | Reference for `geo/geofence.py` |
| ArduPilot | GPL-3.0 | Separate process/hardware, MAVLink boundary |
| WebODM | **AGPL-3.0** | Unmodified Docker service, HTTP boundary |
| farmOS | GPL-2.0 | Unmodified Docker service, HTTP boundary |

**This machine cannot run three of them** — no compiler, no WSL, no Docker. So
SITL cannot be built (`scripts/sitl.sh` refuses early with the reason), and the
WebODM and farmOS clients are tested against **stubs**. That verifies our
requests, *not* those servers' acceptance of them.

`workstation/fake_autopilot.py` fills the SITL gap for telemetry only: genuine
MAVLink, so it tests our decoder against the real protocol — but no flight
dynamics, no EKF, no failsafes. **A green run there is not "tested against an
autopilot".**

---

## What to do next

### Free, this week
Install WSL2 and Docker; fix the GPU power mode. Unblocks SITL, the Hailo
compiler, WebODM, farmOS and 18× faster retraining.
[docs/HARDWARE_PLAN.md](docs/HARDWARE_PLAN.md) Stage 0.

### The one that matters (~C$400)
**A Pi 5, a camera and a reflectance panel — no aircraft needed.** Walk a field
with the camera on a pole and annotate what comes back. Every model here is
trained on other people's fields; `validated_locally` cannot become true without
local imagery, and until it does everything else is scaffolding.

First job on hardware: **verify the camera channel order.** Picamera2's "RGB888"
delivers BGR. We swap by default and it has never been confirmed. Half the
vegetation indices are R/B-symmetric and half are not, so a mix-up would *half*
work — the worst kind of bug.

### Then
Stages 2–5 of the hardware plan: AI HAT, aircraft, RTK, anemometer.

### Not done, deliberately
- No ROS 2, Jetson or PX4. The report assumes all three; the numpy-only boundary
  is deliberate and test-enforced.
- No spray hardware. Regulatorily and financially out of reach.
- No `validated_locally: true` anywhere.

---

## Orientation

```
src/agri_edge/          Pi runtime — numpy + PyYAML core, everything else lazy
  geo/georeference.py   Pixels -> lat/lon, with an error budget
  geo/geofence.py       Flight vs treatment boundary; GeoJSON loader
  geo/coverage.py       Where to fly
  geo/calibration.py    Raw DN -> reflectance, so two dates compare
  geo/indices.py        NDVI, NDRE, GNDVI, SAVI, ExG; management zones
  inference/            YOLOX (numpy), tiling, green-on-brown, Hailo/ONNX engines
  telemetry/ntrip.py    RTK corrections -> the GNSS receiver, never the autopilot
  sensors/environment.py  Temp/RH/pressure, dew point, VPD, wind-gated advisory
training/               Laptop only — never ships to the aircraft
  gsd_calculator.py     Can the camera resolve target X at altitude Y?
  motion_budget.py      How fast can it fly before blur/skew ruins the frame?
  train_resilient.py    Training that survives this GPU
workstation/            Laptop only
  fake_autopilot.py     Real MAVLink + scriptable faults, no aircraft
  webodm_submit.py      Spool -> geotagged JPEG -> orthomosaic
scripts/                pi_setup.sh, hailo_compile.sh (WSL2), sitl.sh
docs/HARDWARE_PLAN.md   What to buy, in what order, and what each unblocks
docs/BUILD_NOTES.md     Findings and reasoning
docs/briefs/            Canadian RPAS regulation, procurement, compliance
```

Reports: [docs/progress-report-and-airframe-brief.html](docs/progress-report-and-airframe-brief.html)
carries the twelve-item mechanical brief; published copy at
https://claude.ai/artifact/GFUHuETvcaQmeoGK8GEyT7
