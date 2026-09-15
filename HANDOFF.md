# HANDOFF — agri-edge

Last updated: 15 Sept 2026. For an agent or person picking this up with no prior
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

**333 tests passing**, no hardware required. `pip install -e ".[dev]"` then `pytest`.

### Working

| Component | State |
|---|---|
| Edge pipeline (capture → QA → inference → indices → spool → provenance) | Done, integration-tested |
| YOLOX decode/letterbox/NMS, pure numpy | Verified against YOLOX's own torch impl to 1e-5 |
| Tiled inference | Measured 2.3× more detections than whole-frame |
| Label collapsing | Report a coarse label, keep the model's own class as `source_label` |
| Store-and-forward uploader | Metadata-first, priority-ordered, stdlib only |
| Environmental sensing (BME280) | Temp/humidity/pressure + dew point + VPD + spray advisory |
| Read-only MAVLink telemetry | Safety contract enforced by test |
| Dependency boundary | Pi runtime imports with numpy + PyYAML alone, test-enforced |
| CI | `.github/workflows/test.yml`, Python 3.11 + 3.12 |

### Models

| Model | Status | Result |
|---|---|---|
| `weed_crop_yolox_s` (binary, **seedlings**) | Done | weed AP@.50 **0.749**, crop 0.630 |
| `imageweeds_yolox_s` (5 prairie **species**) | Finalized from epoch-75 ckpt; **resume to 150 queued** | species AP@.50 0.246; **binary `weed` 0.520** |
| `aerial_sheep_yolox_s` (**livestock**) | **Training**, epoch 37/60 | val mAP 0.274 at ep19 |

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

### The species head collapsed — and the fix was free

`imageweeds_yolox_s` puts **76.2% of its test predictions into `horseweed`**,
which is 14% of ground truth (ragweed 95 GT → 9 predicted; waterhemp 52 → 5;
redroot pigweed 36 → 6; kochia 79 → 80, the only sane one).

But its **boxes are right**. Scored as a single-class detector — collapsing
predictions *and* ground truth — it roughly doubles:

| Mode | AP@.50:.95 | AP@.50 |
|---|---:|---:|
| 5-class species | 0.132 | 0.246 |
| **binary `weed`** | **0.247** | **0.520** |

And 0.520 still *understates* it, because unlabelled natural weeds score as false
positives. So `inference.collapse_labels_to: weed` was added: it reports the
coarse label while keeping the predicted class in `source_label`, so collapsing
changes what is **claimed**, never what was **observed**. Seven tests pin that
down, including that it cannot launder the `validated_locally` gate.

Reproduce: `python training/evaluate.py --model models/imageweeds_yolox_s.onnx
--root data/imageweeds --split test --collapse-to weed`

**This was found by opening the prediction images, not by reading mAP.** The
aggregate number looked like a weak model; it was actually a good localiser
wearing a label it could not support.

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
12. **Don't run the full test suite while training.** `cv2.resize` in
   `test_yolox_postprocess.py` flaked once under memory pressure. Not a code bug.
   (Re-run on 15 Sept during training: 333 passed, no flakes.)
13. **An abrupt kill looks nothing like a crash.** On 15 Sept the livestock run
   was found dead at epoch 35/60 with **no error in the log** — the log's tail was
   nulls and `last_epoch_ckpt.pth` was a truncated 108 KB. That is the signature
   of the process being killed mid-write (session restart), not a CUDA fault.
   `latest_ckpt.pth` was intact, so `train_resilient.py` resumed at a cost of one
   epoch. **Check the log tail for nulls before hunting for an exception.**
14. **`nvidia-smi` clock readings are unreliable on this laptop.** It reported
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
1. Species model finishes (~3 h throttled, ~40 min if power mode fixed), then
   self-finalizes into `models/imageweeds_yolox_s_CARD.md`.
2. Livestock training starts automatically when `runs/metrics_imageweeds_yolox_s.json`
   appears, then self-finalizes.
3. **Review `runs/predictions_*/` by eye.** mAP hid two dataset problems already.

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
scripts/           pi_setup.sh (on the Pi), hailo_compile.sh (in WSL2)
config/            example.yaml (bench), pi.yaml (deployment)
docs/BUILD_NOTES.md  Findings and reasoning — read this second
docs/USE_CASES.md    Roadmap: what's free, what's days, what's a separate product
docs/briefs/         Canadian RPAS regulation, procurement, compliance checklist
models/*_CARD.md     Per-model limitations and measured results
```

Published reports (read-only, shareable):
- Build report: https://claude.ai/code/artifact/ea614d7a-52db-4857-a18f-581e43f72640
- Regulatory brief: https://claude.ai/code/artifact/edcaf6cf-3cea-4cc1-9646-ced7c92d0e82
- Progress report + airframe brief for the mechanical side (15 Sept):
  https://claude.ai/artifact/GFUHuETvcaQmeoGK8GEyT7
