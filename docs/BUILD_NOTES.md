# Build notes — overnight session, 13–14 Sept 2026

What got built, what was found, and what to do next. Read the **Findings**
section first; two of them change what you should build.

---

## Status

| | |
|---|---|
| Tests | **253 passing**, no hardware required |
| Pipeline | Verified end to end: camera → QA → ONNX → decode → spool → provenance |
| Model 1 (seedlings, binary) | Trained to convergence. Best validation mAP 0.488 |
| Model 2 (species, mature) | In training — the one that matches the product decision |
| Dependency boundary | Enforced by test: the Pi runtime imports with numpy + PyYAML alone |
| CI | `.github/workflows/test.yml`, Python 3.11 and 3.12 |
| Blocked on you | WSL2 install (Hailo compiler), hardware, GPU power mode |

**Model 1 final results — held-out test split, through the deployed `OnnxEngine`:**

| Class | AP@.50:.95 | AP@.50 | GT boxes |
|---|---:|---:|---:|
| weed | **0.422** | **0.749** | 696 |
| crop | 0.363 | 0.630 | 85 |
| overall | 0.392 | 0.689 | 781 |

Read finding 1b before quoting the `crop` number — it was trained indoors. And
note finding 1c: model 1 detects *seedlings*, which is not the product that was
chosen. It is kept because it works and may be useful later, not because it ships.

The dependency-boundary tests are worth knowing about. `src/agri_edge/` must
install and run with **numpy and PyYAML only** — torch, onnxruntime, OpenCV,
picamera2, rasterio, HailoRT and pymavlink are all imported lazily inside the
functions that need them. `tests/test_runtime_deps.py` asserts this statically
*and* by importing the package in a subprocess with those modules blocked, then
running the pipeline end to end. Torch alone is ~3 GB; it has no business on a
drone, and this is the kind of guarantee that regresses silently when someone
adds one convenience import.


---

## Product decision (made 14 Sept 2026)

**Target: mature weeds, identified by species** — kochia, waterhemp, ragweed,
horseweed, redroot pigweed. These are the herbicide-resistant ones, where knowing
*which* species changes which chemical you reach for.

This was chosen over early-seedling detection, and it is the choice that flies.
For a ~30 cm mature weed with a Pi Camera Module 3:

| | Whole-frame | Tiled |
|---|---:|---:|
| 30 cm mature weed | **6.1 m AGL** | **39 m AGL** |
| 3 cm seedling (rejected) | 0.6 m | 3.9 m |

Seedling detection is capped at 3.9 m even with tiling — barely a flight. Species
detection of mature weeds works at genuine survey altitude **provided tiling is
enabled**. That is what makes `inference/tiling.py` load-bearing rather than a
nice-to-have.

Model 2 (`training/exps/imageweeds_yolox_s.py`) targets this directly.

### The AI HAT+ is now required, not optional

Tiling a full 4056 px frame is 48 inferences. Measured on an idle laptop CPU that
is **7.3 s per frame — 0.14 FPS, capping ground speed at 1.5 m/s (6 km/h)**. Not
a survey flight. The Pi's CPU is slower still.

**Treat that figure as an order of magnitude, not a specification.** Re-run on
15 Sept on the same laptop *while training occupied the machine* it measured
**35.4 s per frame (0.03 FPS, 0.2 m/s)** — 4.8× worse, purely from CPU
contention. So the honest range for "tiled inference on a CPU" is seconds to
tens of seconds depending on what else is running, and the Pi sits at the
unfavourable end of it.

None of that changes the decision: every value in that range is one to two orders
of magnitude below survey speed. The conclusion is robust precisely *because* the
measurement is not. **The only number worth planning a flight around is measured
on the board**, with nothing else running.

On the Hailo NPU the constraint disappears:

| Capture | Tiles | Max altitude | Hailo latency | Max ground speed |
|---|---:|---:|---|---:|
| **4056×3042** | 48 | **39.0 m** | 288 ms (3.5 FPS) | 47 m/s |
| 3040×2280 | 30 | 29.2 m | 180 ms (5.6 FPS) | 57 m/s |
| 2028×1521 | 12 | 19.5 m | 72 ms (13.9 FPS) | 95 m/s |
| 1014×760 | 4 | 9.7 m | 24 ms (41.7 FPS) | 143 m/s |

Every row exceeds survey speed (5–15 m/s) by a wide margin, so **capture at full
resolution and fly high** — the altitude ceiling is the binding constraint, not
inference. Dropping resolution buys throughput you do not need and costs altitude
you do.

Hailo figures assume ~6 ms per 640×640 tile, deliberately conservative against
the model zoo's 385 FPS rating for `yolox_s_leaky`. **Measure on the board**:
`python training/benchmark.py --backend hailo --tiled --capture-width 4056`.

## Findings

### 1. The dataset is not aerial, and that changes the product

`LibreYOLO/weed-crop-aerial` sounds like drone imagery. It is not. "Aerial" is a
Roboflow-100 *domain-category* label. Looking at the actual photographs, they are
**close-range ground-level shots, roughly 30–80 cm above the soil** — individual
seedlings filling much of the frame.

I only caught this by opening the annotated predictions rather than reading the
mAP. It is the single most consequential thing found tonight.

### 1b. …and the `crop` class was trained indoors, on plastic seed trays

Following finding 1 further: splitting the dataset by filename prefix and
counting labels shows it is **three different visual domains**, not one.

| Sub-population | Images | crop boxes | weed boxes |
|---|---:|---:|---:|
| `3xxxx_` — outdoor, close-up of soil | 883 | **7** | 5,926 |
| `IMG_*` — **indoor propagation trays** | 241 | **403** | 1,401 |
| other — mixed ground-level | 52 | 0 | 115 |

**98.3% of every `crop` label is in the indoor tray images** — visibly plastic
seed trays, electrical cables, a plastic floor grate.

So the file contains two models: a weed detector trained outdoors and a crop
detector trained indoors. `crop` AP 0.363 is real, and it measures seedlings in
trays. It says nothing about finding a crop in a field.

**Use the `weed` class. Treat `crop` as unvalidated for outdoor use.**

This also explains an earlier confusion: crop AP looked healthy on validation, yet
scanning the first 40 test images turned up no crop detections at all — those
happened to be outdoor `3xxxx_` files, which contain 7 crop boxes in total.

### 1c. Model 1 transfers to aerial imagery — but at the wrong growth stage

Rather than assert domain mismatch, I measured it: model 1 (trained on
ground-level close-ups) was run over 20 genuine nadir aerial frames it had never
seen.

| | |
|---|---|
| Labelled specimens present | 65 |
| Detected by model 1 (IoU 0.3) | **1 — recall 2%** |
| Detections it made anyway | 523 |

The 2% is not incompetence, and the 523 are not noise. Looking at the rendered
output, model 1 is finding real plants — the small naturally-occurring seedlings
scattered across the soil. It simply is not finding the *labelled* objects,
because those are a different thing:

| | Median box area |
|---|---:|
| ImageWeeds labels (mature transplants) | 0.269% of frame |
| What model 1 detects (seedlings) | 0.022% of frame |
| | **12× difference** |

**Two models, two growth stages.** Model 1 detects weeds young; ImageWeeds labels
them mature. Evaluating either against the other's annotation gives a number near
zero while both are working correctly.

This is the clearest example in the whole project of why per-class mAP against a
mismatched annotation is worse than no metric at all — it would have read as
"model 1 is broken," and it is not.

### 2. Weed detection from survey altitude is an optics problem, not a model problem

This follows from (1) and is worse than it first appears. Letterboxing a
4056-wide camera frame down to the 640×640 network input **discards 6.3× of
linear resolution before inference happens**.

Ceilings for a Pi Camera Module 3, needing ~20 px across the target
(`training/gsd_calculator.py`):

| Target | Whole-frame | Tiled |
|---|---:|---:|
| 3 cm weed seedling | **0.6 m AGL** | **3.9 m AGL** |
| 25 cm mature weed | 5.1 m | **32 m** |
| 100 cm weed patch | 20.5 m | **130 m** |

At a normal 30 m survey altitude a 3 cm seedling is **2.6 px** natively and
**0.4 px** after downscaling. No amount of training recovers that.

**The decision this forces:** seedling-stage spot-spraying and patch-level
mapping are *different products* with different airframes and flight profiles.
Pick one before buying hardware.

### 3. Tiling recovers most of it — implemented and measured

`src/agri_edge/inference/tiling.py` slices frames into native-resolution tiles
instead of downscaling. On a 1280×1280 mosaic of real test imagery:

| Method | Detections |
|---|---:|
| whole-frame (2× downscale) | 29 |
| **tiled** | **66** |
| per-image native (reference) | 61 |

2.3× more, and it matches the native reference. Costs one inference per tile —
a 4056×3040 frame is ~56 tiles, which is far too slow on the Pi CPU. This is an
argument for the Hailo NPU, or for lowering capture resolution.

Enable with `tiled: true` in the inference config.

### 4. Class balance is 95% weed / 5% crop

The opposite of what I assumed when planning. Only 278 crop boxes in training —
`crop` is effectively untrainable from this dataset. A model that predicts only
`weed` still scores well on aggregate mAP, which is why `evaluate.py` leads with
per-class AP. For a weed-spraying product this is probably acceptable; if you
need crop detection, you need more crop data.

Also: the test split is 11% crop vs training's 5% — a distribution shift between
splits.

### 5. Your GPU is power-capped

`SW Power Cap: Active`, 217 MHz of 3090 MHz, P-state P4, on AC at 65 °C — so not
thermal. Throttled it trains at ~5.8 s/iter; unthrottled at **0.32 s/iter**, an
18× difference. It oscillates.

I deliberately did not change your power settings while you were asleep — that's
your machine's thermal and battery state to decide. Fix via Windows power mode →
Best performance, Acer NitroSense → Performance, NVIDIA Control Panel → Power
management → Prefer maximum performance.

---

## Problems hit and fixed

| Problem | Cause | Fix |
|---|---|---|
| `torch.onnx._export` missing | YOLOX 0.3.0 (June 2025) uses a private API removed in torch 2.x | Wrote `training/export_onnx.py` instead of patching vendored code |
| Training died at epoch 5 | YOLOX JIT-compiles a C++ COCOeval extension; its loader raises `RuntimeError` but the guard only catches `ImportError`. Ninja absent, and `cl.exe` absent too, so it could never compile | `sys.modules` guard in the exp file makes YOLOX take its own documented pycocotools fallback |
| `Path(None)` on config load | Optional path with `null` in YAML | Skip None; also now rejects unknown config keys, since a typo'd threshold silently disables its check |
| Sharp 5-band frames failing blur QA | `laplacian_variance` averaged bands first, suppressing high-frequency signal ~1/N | Measure per band, take the sharpest |
| `HailoEngine` borrowed a method from `OnnxEngine` | Class-body assignment — works, but fragile | Extracted `detections_from_raw()` as a shared function |

---

## What was verified, and how

Not "it ran without error" — these are independent checks:

- **Decoder vs upstream.** The numpy YOLOX decode matches YOLOX's own torch
  `decode_outputs` to 1e-5 on random input, square and non-square. Letterbox
  ratio matches upstream `preproc`.
- **Known-answer image.** The COCO model on `dog.jpg` returns bicycle 0.96 / dog
  0.90 / truck 0.54 with pixel-tight boxes on a non-square 768×576 frame — so the
  whole geometry path is right.
- **Every annotation re-derived.** `verify_coco.py` recomputes all 7,852 boxes
  from their YOLO sources through pycocotools. All round-trip.
- **Full stack.** `tests/test_integration.py` drives the real ONNX model through
  the real `Pipeline` and asserts provenance, geometry, spool priority and the
  safety gate.

---

## Next steps

**Before anything else**

1. Fix the GPU power mode (§5) if you want fast iteration.
2. `wsl --install -d Ubuntu-22.04` from an admin PowerShell, then reboot. Needed
   for the Hailo compiler, which is x86_64 Linux only.
3. Decide: **seedlings at ~3 m, or patches at survey altitude?** (§2) Everything
   downstream depends on this.

**When training finishes**

```bash
python training/finalize.py
```

Exports, evaluates on the held-out test split, writes annotated predictions,
benchmarks, and fills in the model card. Then:

1. **Look at `runs/predictions/`.** Actually look. mAP hid the fact that the
   dataset wasn't aerial; eyes caught it in one image.
2. Read **per-class AP** in `models/weed_crop_yolox_s_CARD.md`, not the aggregate.

**When hardware arrives**

```bash
bash scripts/pi_setup.sh                      # on the Pi
bash scripts/hailo_compile.sh --arch hailo8l  # in WSL2 Ubuntu
```

Verify the camera's channel order once on real hardware —
`Picamera2Camera.verify_channel_order()`. Picamera2's "RGB888" delivers BGR; we
swap by default, but confirm rather than trust.

Test the `.hef` standalone via `vendor/hailo-rpi5-examples` **before** switching
the config to `backend: hailo`.

**Version control — not done, deliberately**

This is not a git repository yet. For a commercial product that's a real gap, but
initialising and committing wasn't mine to decide. A `.gitignore` is written and
correct (vendored code, data, weights and model binaries excluded; the
`.meta.json` provenance sidecars **are** tracked, since they record what each
model was trained on and whether it was validated).

```bash
git init && git add -A && git commit -m "agri-edge: edge pipeline + YOLOX training"
```

**The real work**

Everything above is scaffolding. The model that matters is the one fine-tuned on
imagery from the fields you actually intend to fly, at the altitude you intend to
fly. That is also the only point at which `validated_locally` may become true —
and it is what separates a scouting aid from something allowed to influence
chemical application.

---

## Things I chose not to do

- **Change your system power settings.** Reversible, but it's your laptop's
  thermal and battery state, and you were asleep.
- **Add a `--no-telemetry-gate` flag.** A flag that disables the stale-telemetry
  check would eventually be left on in flight. `--bench` supplies synthetic
  telemetry instead: the gate stays intact and the fake position is obvious in
  every sidecar it touches.
- **Install ninja to fix the eval crash.** It would not have worked — `cl.exe` is
  absent, so the C++ extension could never compile. The fallback was the right
  fix, not a bigger toolchain.
