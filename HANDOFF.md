# HANDOFF — agri-edge

Last updated: 15 Sept 2026 (evening). For an agent or person picking this up with no prior
context. Read this, then [docs/BUILD_NOTES.md](docs/BUILD_NOTES.md) for the
reasoning behind the findings.

---

## Goal

A **commercial** agricultural drone product for a two-person team: the user
writes all the code, their friend does mechanical and airframe work. Built on a
Raspberry Pi 5 + Hailo AI HAT companion computer alongside a Pixhawk autopilot.

Started as "weed detection". Has become a **platform**: the pipeline is
use-case agnostic, so a new capability is usually a model file or an I2C sensor,
not a rebuild. See [docs/USE_CASES.md](docs/USE_CASES.md) for the full roadmap.

**Hard constraint: Apache-2.0 / permissive licensing only.** This is a product,
so AGPL (Ultralytics YOLOv8/v11) and GPL (YOLOv6) are excluded deliberately.
Never introduce `ultralytics` as a convenience — it silently breaks the licensing
posture. See [NOTICE.md](NOTICE.md).

---

## Current progress

**520 tests passing**, no hardware required. `pip install -e ".[dev]"` then `pytest`.

### Working

| Component | State |
|---|---|
| Edge pipeline (capture → QA → inference → indices → spool → provenance) | Done, integration-tested |
| YOLOX decode/letterbox/NMS, pure numpy | Verified against YOLOX's own torch impl to 1e-5 |
| Tiled inference | Measured 2.3× more detections than whole-frame |
| Label collapsing | Report a coarse label, keep the model's own class as `source_label` |
| Model provenance | Derived per dataset; an unregistered dataset refuses to export |
| Green-on-brown detection | Classical ExG thresholding, no model, no NPU (OpenWeedLocator, MIT) |
| MAVLink fault injection | Real protocol via `workstation/fake_autopilot.py` |
| Treatment geofence | Flight boundary vs treatment boundary, GeoJSON, wired into the pipeline |
| Detection georeferencing | Ray-plane intersection -> lat/lon + error budget per detection |
| farmOS integration | Observation logs, stdlib only, credentials from the environment |
| WebODM integration | Spool -> geotagged JPEG -> orthomosaic/DSM |
| Store-and-forward uploader | Metadata-first, priority-ordered, stdlib only |
| Environmental sensing (BME280) | Temp/humidity/pressure + dew point + VPD + spray advisory |
| Read-only MAVLink telemetry | Safety contract enforced by test |
| Dependency boundary | Pi runtime imports with numpy + PyYAML alone, test-enforced |
| CI | `.github/workflows/test.yml`, Python 3.11 + 3.12 |

### Models

| Model | Status | Result |
|---|---|---|
| `weed_crop_yolox_s` (binary, **seedlings**) | Done | weed AP@.50 **0.749**, crop 0.630 |
| `imageweeds_yolox_s` (5 prairie **species**) | Done, 150/150 | species AP@.50 **0.457**; binary `weed` 0.673 |
| `aerial_sheep_yolox_s` (**livestock**) | Done, 60/60 | sheep AP@.50 **0.905** on 5,603 boxes |

Per-species AP@.50: horseweed **0.793**, ragweed **0.642**, kochia **0.624** are
usable; redrootpigweed 0.153 and waterhemp 0.073 are **not** — treat those two
labels as "a weed", not an identification.

Training is chained: each run finalizes itself (export → evaluate → predictions →
benchmark → fill model card) via `training/finalize.py --exp <name>`.

---

## What worked

- **Looking at the imagery instead of trusting metrics.** This caught every major
  finding. Two datasets were not what their names claimed.
- **Verifying against an independent reference.** The numpy decoder was checked
  against YOLOX's own torch implementation; dew point/VPD against published
  psychrometric values; every converted annotation re-derived from source.
- **Checking datasets before spending on them.** After the first one burned us,
  every subsequent dataset was inspected visually and checked for split leakage
  before any training.
- **Deriving the optics limits first.** `training/gsd_calculator.py` settled the
  product direction more decisively than any model result.
- **Chaining background work** (`until grep -q ...; do sleep; done; <next step>`)
  so training → finalize runs unattended.

### The species head collapsed at epoch 75 — and more training fixed it

At the epoch-75 checkpoint `imageweeds_yolox_s` put **76.2% of its predictions
into `horseweed`**, against horseweed being 14% of ground truth. It had collapsed
onto one class. **Training to the full 150 epochs fixed it**: the largest class
share is now 31.4% and per-class AP@.50 roughly doubled.

| Class | GT | pred @ep75 | pred @ep150 | AP@.50 |
|---|---:|---:|---:|---:|
| ragweed | 95 | 9 | 80 | 0.642 |
| horseweed | 44 | 321 | 82 | 0.793 |
| kochia | 79 | 80 | 89 | 0.624 |
| redrootpigweed | 36 | 6 | 19 | 0.153 |
| waterhemp | 52 | 5 | 13 | 0.073 |

Binary still wins on aggregate (AP@.50 0.673 vs 0.457), so
`inference.collapse_labels_to` stays and is one line to enable — but species is
what picks the chemical, so **species is the default**. Collapsing keeps the
predicted class in `source_label`, so it changes what is **claimed**, never what
was **observed**; seven tests pin that down, including that it cannot launder the
`validated_locally` gate.

Two lessons, and the second is the bigger one:

1. **This was found by opening the prediction images, not by reading mAP.** The
   aggregate said "weak model"; the images said "good localiser, wrong label".
2. **A collapsed head can be a symptom of undertraining, not a dataset limit.**
   The binary-collapse workaround was the right call on the evidence available at
   epoch 75 and the wrong permanent conclusion. Finish the training run before
   deciding what a model fundamentally cannot do.

Reproduce: `python training/evaluate.py --model models/imageweeds_yolox_s.onnx
--root data/imageweeds --split test --collapse-to weed`

---

## The safety gate has TWO conditions now (16 Sept)

`Detection.may_drive_treatment` used to mean only "is this model validated".
It now means:

    validated_locally AND in_treatment_zone is True

The second **fails closed**: `None` means the question was never asked -- no
boundary configured, or the detection could not be georeferenced -- and an
unasked question is not a yes. A farm therefore cannot leave decision-support
mode without deliberately defining a treatment boundary, which is the right
thing to be unable to reach by accident.

Enabling treatment now requires, in order: fly your own fields, annotate,
retrain, set `validated_locally: true`, **and** supply
`treatment_zone.boundary_geojson`. Miss any one and nothing is treatable.

This module computes the answer; the report puts **enforcement** on the payload
MCU, independent of this computer, so a fault in Linux cannot open a valve.

## The five integrated projects (15 Sept)

All cloned into gitignored `vendor/`. **No GitHub forks**, and no GPL or AGPL
code is linked into this tree.

| Project | Licence | How it is used |
|---|---|---|
| **OpenWeedLocator** | **MIT** | Code ported into `inference/greenonbrown.py` |
| **AgOpenGPS** | **Apache-2.0** | Reference for `geo/geofence.py` section geometry |
| ArduPilot | GPL-3.0 | Separate process/hardware, MAVLink protocol boundary |
| WebODM | **AGPL-3.0** | Unmodified Docker service, HTTP boundary |
| farmOS | GPL-2.0 | Unmodified Docker service, HTTP boundary |

Only the two permissive ones have code brought in. The rest are separate
programs behind documented protocols — which is what keeps the closed-source
posture intact. See NOTICE.md for the AGPL network clause in particular.

**This machine cannot run three of them.** No compiler, no WSL, no Docker. So:

- ArduPilot SITL cannot be built here. `scripts/sitl.sh` refuses early with the
  reason rather than failing halfway through a build.
- WebODM and farmOS cannot be started here, so their clients are tested against
  local stubs. That verifies our requests, **not** that those servers accept
  them. Point each at a real instance before trusting it.
- `workstation/fake_autopilot.py` fills the SITL gap for the telemetry path
  only: it speaks genuine MAVLink so it tests our decoder against the real
  protocol, but it has no flight dynamics, no EKF and no failsafes.

---

## What did NOT work — do not repeat

1. **`LibreYOLO/weed-crop-aerial` is not aerial.** "Aerial" is a Roboflow-100
   *category* label. The images are ground-level close-ups (~30–80 cm) plus
   **indoor propagation trays** — 98.3% of its `crop` labels are from the trays.
   Model 1 is a *seedling* detector; do not quote its `crop` number as field
   performance.
2. **Do not evaluate a model against a mismatched annotation.** Model 1 scored
   **2% recall** on ImageWeeds while working correctly — it detects seedlings
   (0.022% of frame), those labels are mature plants (0.269%), a 12× size gap.
3. **`torch.onnx._export` no longer exists** (removed in torch 2.x). YOLOX 0.3.0
   calls it. Use `training/export_onnx.py`, not `vendor/YOLOX/tools/export_onnx.py`.
4. **YOLOX's C++ COCOeval extension kills training at the first eval.** Its loader
   raises `RuntimeError` past an `ImportError`-only guard. Installing ninja does
   **not** fix it — `cl.exe` is absent. Every exp file sets
   `sys.modules.setdefault("yolox.layers.fast_coco_eval_api", None)` to force
   YOLOX's own pycocotools fallback. **Keep that line in any new exp.**
5. **YOLOX's default `max_labels` silently truncates dense scenes.** Defaults are
   50 (dataset) and 120 (post-mosaic). The sheep data has up to 105 objects per
   image; at the defaults a quarter of images would silently lose labels. See
   `aerial_sheep_yolox_s.py` for the override, including a copied
   `get_data_loader` because the base class hardcodes 120.
6. **Two repos the user suggested are unusable: no licence** —
   `DevilStudio27/Plant-Disease-Detection-and-Solution` and
   `MindsHub/crop-detection`. No licence means all rights reserved.
7. **YOLOX prints "Training of experiment is done" even when it CRASHED.** It
   lives in a `finally` block. The species run died at epoch 80/150 with a cuDNN
   fault and still printed "done and the best AP is 26.14" — which I first read
   as success. **Never key completion on that string.** Check the last
   `epoch: N/TOTAL` in the log instead (`train_resilient.finished()`).
8. **This GPU drops transient cuDNN faults on long runs.**
   `CUDNN_STATUS_EXECUTION_FAILED_CUDART` killed a 4-hour run at epoch 80, with
   VRAM at 7.1/8.1 GB and clocks oscillating 217 MHz ↔ 3090 MHz. Not a code bug.
   **Always launch training via `training/train_resilient.py --exp <name>`**,
   which auto-resumes from `latest_ckpt.pth` on transient faults only (it
   deliberately does *not* retry config or shape errors, which would fail
   identically).
9. **YOLOX `--resume` is broken on PyTorch 2.6+.** `trainer.resume_train` calls
   `torch.load(ckpt)` without `weights_only=False`; the checkpoints contain numpy
   scalars/dtypes, which the safe unpickler rejects. And loguru's `@logger.catch`
   swallows it, so the process **exits 0** and looks like a successful no-op.
   Fixed by allowlisting numpy's dtype family in each exp file (search
   `add_safe_globals`). **Keep that block in any new exp.**
10. **Never put `| tail` before `&&` in a pipeline chain.** The pipe's exit code
   is `tail`'s (always 0), so the chain proceeds even when the step failed. This
   caused two competing training runs to fight over the 8 GB GPU, which then
   surfaced as `RuntimeError: Trying to create tensor with negative dimension`.
   That error means **GPU contention, not corruption** — check
   `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv`
   before assuming anything is broken. Capture `rc=$?` explicitly instead.
11. **Only one training run at a time.** 8 GB VRAM fits exactly one YOLOX-s run
   (~7.1 GB). Queue on a finalize artifact (`runs/metrics_<exp>.json`), not on a
   log string.
12. **Newline escapes inside a heredoc-embedded Python string corrupt the file.**
   Writing a backslash-n through `python - <<'PYEOF'` produced a *literal*
   newline inside the string literal four separate times, each one an
   unterminated-string SyntaxError — including once while writing this very
   entry. **Use the Edit tool for any text containing escape sequences**, and
   keep heredoc-driven edits to plain substitutions.
13. **A stale UDP sender makes a fault test pass spuriously.** A previous
   `fake_autopilot` run was still alive and sending healthy packets on the same
   port, so an injected GNSS-loss test saw a mix of both streams and two frames
   "passed" that should not have. It looked exactly like a QA bug in
   `check_gnss`. Every test in `test_mavlink_faults.py` now takes its own port.
14. **Don't run the full test suite while training.** `cv2.resize` in
   `test_yolox_postprocess.py` flaked once under memory pressure. Not a code bug.
   (Re-run on 15 Sept during training: 333 passed, no flakes.)
15. **`export_onnx.py` hardcoded `trained_on`, so every sidecar was wrong.**
   All three models claimed `weed-crop-aerial` -- including the stock COCO model
   and the species model, which owes CC BY credit to a *different* paper (Rai et
   al. 2023). A wrong CC BY credit is a compliance failure, not untidiness.
   Provenance is now keyed on the exp's `data_dir` and an unregistered dataset
   **raises** rather than defaulting (`DATASET_PROVENANCE`), because a
   confidently wrong attribution is worse than a missing one.
   `tests/test_provenance.py` holds it.
16. **An abrupt kill looks nothing like a crash.** On 15 Sept the livestock run
   was found dead at epoch 35/60 with **no error in the log** — the log's tail was
   nulls and `last_epoch_ckpt.pth` was a truncated 108 KB. That is the signature
   of the process being killed mid-write (session restart), not a CUDA fault.
   `latest_ckpt.pth` was intact, so `train_resilient.py` resumed at a cost of one
   epoch. **Check the log tail for nulls before hunting for an exception.**
18. **A belly-mounted camera follows the BELLY, not the wing.** Positive roll
   drops the right wing and swings the camera's view **west** when heading north;
   positive pitch swings it **north**. Opposite handedness, and getting roll
   backwards mirrors an entire flight about its own track while looking perfectly
   plausible frame by frame. Pinned by its own test in `test_georeference.py`.
19. **`inference.confidence_threshold` means different things per backend.** A
   probability for YOLOX (0.30 = permissive) and index strength for
   green-on-brown, where field vegetation scores 0.10-0.20. The same 0.30
   therefore discards *everything* from green-on-brown. Found by getting zero
   detections on a synthetic scene that was 30% vegetation. **Set it explicitly
   when switching backends.**
20. **Two repos evaluated and rejected (16 Sept).**
   `Abrar0703/DADIS` has **no licence** (all rights reserved), is automotive, and
   is a 5-commit educational prototype built on Ultralytics AGPL.
   `Maelic/RelateAnything` is subtler: the *code* is Apache-2.0 but the
   **weights** derive from DINOv3 (DINOv3 licence) with annotations from Gemma
   (Gemma Terms of Use), so the artefact you would ship is not permissively
   licensed. **Check the weights' licence, not just the repo's.**
17. **`nvidia-smi` clock readings are unreliable on this laptop.** It reported
   22–44 MHz of 3090 with *no throttle reason active*, while YOLOX logged
   2.5 s/iter; an hour later, same reported clock (217 MHz), 0.264 s/iter — near
   full speed. **Trust `iter_time` in the training log, not the clock query.**

---

## Environment gotchas

- **GPU is power-capped.** RTX 5060 sits at 217 MHz of 3090 MHz (`SW Power Cap:
  Active`), P-state P4, on AC at 65 °C — not thermal. **5.8 s/iter throttled vs
  0.32 s/iter unthrottled, an 18× difference.** Check
  `nvidia-smi --query-gpu=clocks.sm,power.draw --format=csv,noheader` before
  blaming code. Fix: Windows power mode → Best performance, Acer NitroSense →
  Performance, NVIDIA Control Panel → Prefer maximum performance. **Still not
  done by the user.**
- **Blackwell sm_120** — PyTorch must come from the cu128 index or kernels fail
  with "no kernel image is available".
- **Use `./.venv/Scripts/python.exe`**, not bare `python`.
- **WSL2 is not installed** and is required for the Hailo compiler (x86_64 Linux
  only — not Windows, not the Pi). `wsl --install -d Ubuntu-22.04`, admin, reboot.
- **No `cl.exe`** (no MSVC), so anything needing C++ JIT compilation will fail.

---

## The findings that drive product decisions

**Weed detection from survey altitude is an optics problem, not a model problem.**
Letterboxing a 4056-wide frame to 640×640 discards **6.3× of linear resolution
before inference**. Ceilings for a Pi Camera Module 3 at ~20 px on target:

| Target | Whole-frame | Tiled |
|---|---:|---:|
| 3 cm seedling | 0.6 m | 3.9 m |
| 30 cm mature weed | 6.1 m | **39 m** |
| 120 cm sheep | 24.6 m | 155 m |
| 200 cm cow | **41 m** | 260 m |

**Product decision made (14 Sept):** mature weeds identified **by species**
(kochia, waterhemp, ragweed, horseweed, redroot pigweed) — the
herbicide-resistant ones where species determines chemical. Seedling detection
was rejected: capped at 3.9 m even tiled.

**Second finding (15 Sept): tiling moves the remaining constraint onto the
airframe.** Whole-frame inference downscales 6.3x, which quietly absorbs motion
blur. Tiling runs at native resolution, so **the motion-blur budget is 6.3x
tighter** and it is now a mechanical problem. At 30 m AGL, holding smear under
1 px: 3.9 ms exposure at 3 m/s, 2.3 ms at 5 m/s, 1.4 ms at 8 m/s.

Rolling shutter (~33 ms readout) is a separate effect, and **be precise about it**:
a 30 cm weed spans ~26 of 3040 rows, so its own readout is 0.28 ms and it is
distorted by 0.12 px at 5 m/s. **Detection is unaffected.** What skews is
frame-level geometry -- georeferencing, area measurement, stitching,
photogrammetry -- while the image still looks sharp. So scouting can fly at
5-8 m/s (67-108 ha/h); mapping-grade geometry caps near 1.7 m/s (23 ha/h, ~3x the
airtime for the same field). Compute with `training/motion_budget.py`.

**Consequence: the AI HAT+ is required, not optional.** Tiling a full frame is 48
inferences — 7.3 s on CPU (1.5 m/s ground speed, unflyable) vs ~288 ms on Hailo
(47 m/s). **Except for livestock**, which works whole-frame at 41 m on a bare Pi.

---

## Next steps

### Immediate (automated, running now)
1. Livestock training resumed from epoch 35/60, then self-finalizes into
   `models/aerial_sheep_yolox_s_CARD.md`.
2. Species model then resumes 80 -> 150 and re-finalizes.
   Both are chained in one script; **one run at a time, 8 GB VRAM fits exactly one.**
3. ~~Review `runs/predictions_*/` by eye~~ — **done 15 Sept, and it paid for
   itself twice**: it found the collapsed species head (above) and confirmed
   model 1's test imagery contains a person's boot. Keep doing this after every
   retrain. mAP has now hidden three separate problems.

### Blocked on the user
4. Fix the GPU power mode — 18× on every retrain.
5. `wsl --install -d Ubuntu-22.04` — needed for Hailo compilation.
6. Confirm what hardware physically exists. Earlier answer was contradictory
   ("nothing yet" **and** Pi 5 + camera + AI HAT).

### When hardware arrives
7. `bash scripts/pi_setup.sh` on the Pi.
8. **Verify camera channel order** — `Picamera2Camera.verify_channel_order()`.
   Picamera2's "RGB888" delivers BGR; we swap by default but it must be confirmed.
9. `bash scripts/hailo_compile.sh --arch hailo8l` **in WSL2**. Match `--arch` to
   the board.
10. Test the `.hef` standalone via `vendor/hailo-rpi5-examples` **before**
    switching config to `backend: hailo`.
11. `python training/benchmark.py --backend hailo --tiled --capture-width 4056` —
    the real number that sets flight parameters.

### The work that actually matters
12. **Fly your own fields and annotate.** Everything so far is scaffolding. Public
    datasets are one site, one season, and in two cases the wrong domain entirely.
13. Only after local validation may `validated_locally` become `true` in a
    model's `.meta.json`. It is enforced end to end: `Detection.may_drive_treatment`
    is False while it is false, and every spooled frame records
    `decision_support_only`. **That flag is the line between a scouting aid and
    something allowed to influence chemical application.**
14. Easiest next capability: livestock counting is nearly free (in progress).
    After that, see the tier table in `docs/USE_CASES.md`.

### Not done, deliberately
- **No git repository.** `.gitignore` is written and correct; initialising and
  committing was the user's call, not mine.
- **No system power settings changed** — the user's machine, their thermal and
  battery state.
- **No `--no-telemetry-gate` flag.** Such a flag would eventually be left on in
  flight. `--bench` supplies synthetic telemetry instead, keeping the gate intact
  and making the fake position obvious in every sidecar.

---

## Orientation

```
src/agri_edge/     Pi runtime — numpy + PyYAML core, everything else lazy
training/          Laptop only — never ships to the aircraft
  exps/            YOLOX experiment configs (one per model)
  finalize.py      export + evaluate + predict + benchmark, one command
  gsd_calculator.py  Can the camera resolve target X at altitude Y?
  motion_budget.py   How fast can it fly before blur/skew ruins the frame?
workstation/       Laptop only -- fake_autopilot.py (MAVLink + faults),
                   webodm_submit.py (spool -> geotagged JPEG -> orthomosaic)
scripts/           pi_setup.sh (on the Pi), hailo_compile.sh (in WSL2)
config/            example.yaml (bench), pi.yaml (deployment)
docs/BUILD_NOTES.md  Findings and reasoning — read this second
docs/USE_CASES.md    Roadmap: what's free, what's days, what's a separate product
docs/briefs/         Canadian RPAS regulation, procurement, compliance checklist
models/*_CARD.md     Per-model limitations and measured results
```

The current progress report, including the numbered airframe brief for the
mechanical side, is checked in at
[docs/progress-report-and-airframe-brief.html](docs/progress-report-and-airframe-brief.html)
— open it in a browser. The published copy is convenient but the repo copy is
the one that cannot disappear.

Published reports (read-only, shareable):
- Build report: https://claude.ai/code/artifact/ea614d7a-52db-4857-a18f-581e43f72640
- Regulatory brief: https://claude.ai/code/artifact/edcaf6cf-3cea-4cc1-9646-ced7c92d0e82
- Progress report + airframe brief for the mechanical side (15 Sept):
  https://claude.ai/artifact/GFUHuETvcaQmeoGK8GEyT7
