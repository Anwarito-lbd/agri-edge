# Edge pipeline notes

This is the longer engineering note that used to be the root README. The
current overview, with the 13 November 2026 laptop run, is `README.md`.

One correction before the altitude section below. Those ceilings were computed
when the notes still described a 4056-pixel-wide frame and a 6.3× letterbox.
`training/gsd_calculator.py` now uses the Pi Camera Module 3 (IMX708) at
4608×2592, and the run captured in `docs/proof/gsd_3cm.log` and
`docs/proof/gsd_30cm.log` is the one to quote: a 3 cm target is resolvable up
to about 0.7 m whole-frame and 5.1 m tiled. The 29-versus-66 detection count
later in this note was an earlier measurement on imagery that is not in this
tree; it was not repeated for the portfolio run.

# agri-edge

Companion-computer edge pipeline for agricultural RPAS operations in Canada.

Runs on a Raspberry Pi 5 alongside a Pixhawk/Cube autopilot: captures geotagged
imagery, assesses its quality at the point of capture, runs optional edge
inference, computes vegetation indices, and spools everything for
store-and-forward transfer. Runs fully simulated on a laptop with no hardware.

```bash
pip install -e ".[dev]"
python -m pytest                                    # 347 tests, no hardware needed
agri-edge -c config/example.yaml preflight --simulate
agri-edge -c config/example.yaml fly --simulate --frames 20
```

Two halves, deliberately separated:

| | `src/agri_edge/` | `training/` |
|---|---|---|
| Runs on | the Pi, in flight | your laptop |
| Dependencies | numpy, PyYAML (+ onnx/camera extras) | torch, YOLOX, pycocotools |
| Ships to the aircraft | yes | **never** |

Torch is ~3 GB and YOLOX pulls a large dependency tree. Neither belongs on an
aircraft, so the split is **enforced by test**: `tests/test_runtime_deps.py`
asserts that nothing under `src/agri_edge/` imports torch, onnxruntime, OpenCV,
picamera2, rasterio, HailoRT or pymavlink at module level, then imports the whole
package in a subprocess with those blocked and runs the pipeline end to end.
Optional extras are imported lazily, inside the functions that need them.

---

## Why it is built this way

Three design rules carry most of the weight. Each is enforced in code, not just
documented.

### 1. The Pi cannot command the aircraft

The autopilot owns attitude stabilisation, navigation and failsafes. The Pi owns
perception and data management. `telemetry/mavlink_link.py` is read-only by
construction — it has no method that could arm, disarm, change mode, upload a
mission or trigger a failsafe, and a test asserts that none appears.

The aircraft must fly its geofence, lost-link, battery and return-to-home logic
correctly with this process dead. A companion computer that can command the
vehicle puts that guarantee at the mercy of a Linux userspace process.

### 2. A model is a sensor, not a decision

Every `Detection` carries `validated_locally`, and `may_drive_treatment` is False
whenever it is False. Every frame's sidecar records `decision_support_only`.

A weed model trained on DeepWeeds learned Australian species in Australian
conditions; PlantVillage is single leaves on plain backgrounds and is not aerial
field imagery at all. Neither is evidence of performance on Saskatchewan canola.
A false positive used for scouting costs a walk across a field; the same false
positive wired to a sprayer costs chemical, crop, or an environmental incident.
So the flag travels with the detection all the way to whatever would act on it.

Set `validated_locally: true` in a model's `.meta.json` only after validating
against local field observations, recorded by crop, growth stage, location,
season, altitude and lighting.

### 3. Failed QA flags data, it does not delete it

A frame that fails quality assessment is spooled at `DEGRADED` priority, not
discarded. A blurred frame over a genuine anomaly is still evidence that
something is there, and the decision to throw data away belongs to an agronomist
on the ground with context — not to a threshold on a Pi at 100 m AGL.

The disk-quota policy follows the same logic: it evicts uploaded payloads first,
then QA-failed frames oldest-first, and never evicts an anomaly frame.

---

## What runs where

Deliberately split, because the wrong split is the most common way these systems
fail:

| Stage | Runs on | Why |
|---|---|---|
| Flight control, failsafes | **Pixhawk / Cube** | Must survive any failure of everything else |
| Capture, QA, detection, indices, spooling | **Raspberry Pi 5** (+ AI HAT+) | Low latency, works offline, reduces what must be transferred |
| Orthomosaics, dense point clouds, DSM/DTM, full multispectral mosaics | **Field workstation** | 32–64 GB RAM and a real GPU; never on an airborne Pi |
| Multi-year archives, cross-farm training, dashboards | **Cloud** | Scale and collaboration |

**Edge first for flight-time decisions, workstation first for photogrammetry,
cloud for scale.**

On accelerator choice: the **26-TOPS AI HAT+** is the right buy for this
workload. The 40-TOPS AI HAT+ 2 (Hailo-10H, 8 GB) delivers roughly comparable
computer-vision throughput — its advantage is local LLM and VLM inference, which
this pipeline does not do.

---

## Read this before planning a flight altitude

Detecting weeds from a surveying drone is limited by **optics, not by the model**.
Two numbers differ and only one is usually considered:

- **native GSD** — cm per pixel on the sensor.
- **effective GSD** — cm per pixel *as the model sees it*. Letterboxing a
  4056-wide frame down to the 640×640 network input discards **6.3× of linear
  resolution** before inference happens.

For a Pi Camera Module 3, needing ~20 px across the target:

| Target | Whole-frame ceiling | Tiled ceiling |
|---|---:|---:|
| 3 cm weed seedling | **0.6 m AGL** | **3.9 m AGL** |
| 30 cm mature weed | 6.1 m | **39 m** |
| 120 cm sheep | 24.6 m | 155 m |
| 200 cm cow | **41 m** | 260 m |

At a normal 30 m survey altitude a 3 cm seedling is **2.6 px** even at native
resolution, and 0.4 px after downscaling. No model recovers that. Run
`python training/gsd_calculator.py --target-size 3` for your own camera and target.

**Tiling is the fix**, and it is not an optimisation. It slices the frame into
native-resolution tiles instead of downscaling, buying back the full 6.3×:

```yaml
inference:
  tiled: true
  tile_size: 640
  tile_overlap: 0.2
```

Measured on a 1280×1280 mosaic of real test imagery: whole-frame found 29
detections, tiled found 66 — **2.3× more**, matching the 61 found by inferring
each source image natively. It costs one inference per tile, so measure the frame
rate with `training/benchmark.py` before committing to it.

The practical consequence, and the product decision taken on 14 Sept 2026:
**seedlings are out** — capped at 3.9 m even tiled, which is a nervous hover
rather than a survey. The target is **mature weeds at 39 m**, which makes the
AI HAT+ a requirement rather than an upgrade (48 tiles per frame is ~7.3 s on the
Pi's CPU but ~288 ms on the NPU). **Livestock is the exception**: a cow is
detectable at 41 m whole-frame, so that model runs usefully on a bare Pi.

### …and then the aircraft becomes the limit

Tiling buys back the resolution, but it also removes a cushion: whole-frame
inference downscales 6.3×, which quietly absorbs motion blur. Tiling shows the
detector the blur at full scale too, so **the motion-blur budget is 6.3× tighter
and it is now a mechanical problem.** At 30 m holding smear under one pixel:
3.9 ms exposure at 3 m/s, 2.3 ms at 5 m/s, 1.4 ms at 8 m/s.

Rolling shutter is a *separate* effect and worth being precise about: a 30 cm
weed spans ~26 of 3040 rows, so its own readout is 0.28 ms and it is distorted by
0.12 px at 5 m/s — **detection is unaffected**. What skews is frame-level
geometry, so georeferencing, area measurement and photogrammetry degrade while
the image still looks perfectly sharp. Scouting can fly at 5–8 m/s (67–108 ha/h);
mapping-grade geometry caps near 1.7 m/s (23 ha/h, ~3× the airtime per field).

```bash
python training/motion_budget.py --altitude 30 --target-size 30
```

## Training the detector

The model is **YOLOX-s (Apache-2.0)**, not YOLOv8/v11 (AGPL-3.0) or YOLOv6
(GPL-3.0). This is a product: AGPL would oblige you to open-source it. YOLOX is
also already in the Hailo model zoo as `yolox_s_leaky`, so there is a documented
path from checkpoint to `.hef`. See [NOTICE.md](NOTICE.md).

```bash
python training/download_data.py        # fetch + verify + report class balance
python training/yolo_to_coco.py         # YOLO txt -> COCO json (YOLOX's format)
python training/verify_coco.py          # re-check every box against its source

python vendor/YOLOX/tools/train.py -f training/exps/weed_crop_yolox_s.py \
    -d 1 -b 8 --fp16 -c weights/yolox_s.pth

python training/export_onnx.py --ckpt YOLOX_outputs/weed_crop_yolox_s/best_ckpt.pth
python training/evaluate.py --model models/weed_crop_yolox_s.onnx --split test
python training/predict_image.py --model models/weed_crop_yolox_s.onnx \
    --images data/weed-crop-aerial/test/images
```

### The three models, and what each is actually good for

| Model | Task | Measured on held-out test | Verdict |
|---|---|---|---|
| `weed_crop_yolox_s` | weed vs crop, **seedling scale** | weed AP@.50 **0.749**, crop 0.630 | pipeline proof only — see below |
| `imageweeds_yolox_s` | 5 prairie weed **species** | species AP@.50 0.246 · **binary `weed` 0.520** | **ship it collapsed to binary** |
| `aerial_sheep_yolox_s` | livestock counting | in training | the one that runs on a bare Pi |

**Three dataset problems were caught by looking at the imagery, not the metrics.**
Every one of them would have produced a confident, wrong product:

1. `LibreYOLO/weed-crop-aerial` **is not aerial.** "Aerial" is a Roboflow-100
   *category* label. The images are ground-level close-ups plus **indoor
   propagation trays**, and 98.3% of its `crop` labels come from the trays. Model
   1 is a seedling detector; never quote its `crop` number as field performance.
   It is also 95% weed / 5% crop, so aggregate mAP flatters it — `evaluate.py`
   reports per-class AP and says so out loud.
2. `ImageWeeds` labels only the **transplanted potted specimens**. Dozens of
   natural weeds per frame are unlabelled and train as background, so recall is
   capped by the annotation and measured precision *understates* reality.
3. The sheep set is 3× machine-augmented. Had copies of one photo landed on both
   sides of a split every number would be inflated — checked, and no source photo
   appears in two splits.

### When a model localises well but classifies badly

`imageweeds_yolox_s` puts **76.2% of its predictions into one of its five
species** (horseweed, which is 14% of ground truth). The species head collapsed.
The *boxes*, however, are right — scoring the same model as a single-class
detector roughly doubles it:

| Mode | AP@.50:.95 | AP@.50 |
|---|---:|---:|
| 5-class species | 0.132 | 0.246 |
| **binary `weed`** | **0.247** | **0.520** |

So the runtime can report a coarser label than the model predicted, while keeping
the prediction as `source_label` in every sidecar — collapsing changes what is
*claimed*, never what was *observed*:

```yaml
inference:
  class_names: [ragweed, waterhemp, horseweed, redrootpigweed, kochia]
  collapse_labels_to: weed
```

```bash
python training/evaluate.py --model models/imageweeds_yolox_s.onnx     --root data/imageweeds --split test --collapse-to weed
```

Species ID is still the right goal — species is what picks the chemical — but it
needs locally annotated imagery, not tuning.

### Training on a machine that fails

Long runs on this laptop drop transient cuDNN faults, and YOLOX prints
`Training of experiment is done` from a `finally` block **even when it crashed**.
Always launch through the wrapper, which resumes from `latest_ckpt.pth` on
transient faults only and judges completion by the last logged epoch:

```bash
python training/train_resilient.py --exp imageweeds_yolox_s --batch 8
```

`evaluate.py` and `predict_image.py` both run inference through
`agri_edge.inference.engine.OnnxEngine` — the exact class the Pi runs — so the
reported numbers describe the deployed path, letterbox and host-side decode
included, rather than a torch-side path that never flies.

## Layout

```
src/agri_edge/              THE PI RUNTIME -- numpy + PyYAML core
  config.py                 All thresholds in one place, with unknown-key rejection
  telemetry/mavlink_link.py Read-only MAVLink + simulated telemetry
  capture/camera.py         Picamera2 backend + synthetic multispectral scene
  qa/checks.py              Blur, exposure, GNSS, band completeness, attitude
  geo/indices.py            NDVI, NDRE, GNDVI, SAVI, ExG; management zones
  inference/yolox.py        Letterbox, grid decode, class-wise NMS (pure numpy)
  inference/tiling.py       Native-resolution tiled inference (see altitude section)
  inference/engine.py       ONNX / Hailo / simulated, local-validation + label collapsing
  sensors/environment.py    BME280 -> temp/RH/pressure, dew point, VPD, spray advisory
  store/spool.py            Priority store-and-forward queue with quota policy
  store/uploader.py         Metadata-first, priority-ordered uplink (stdlib only)
  pipeline/runner.py        The capture -> QA -> inference -> spool loop
  cli.py                    fly | spool | indices | preflight

training/                   LAPTOP ONLY -- never shipped to the aircraft
  download_data.py          Fetch from HF, verify counts, report class balance
  yolo_to_coco.py           Format conversion (the highest-risk step; unit-tested)
  verify_coco.py            Independent re-check of every converted box
  prepare_imageweeds.py     Species dataset: fetch, split by source image, verify
  prepare_aerial_sheep.py   Livestock dataset, incl. the split-leakage check
  exps/*.py                 One YOLOX experiment per model (three of them)
  train_resilient.py        Training that survives this GPU's transient faults
  export_onnx.py            Checkpoint -> ONNX + provenance sidecar
  evaluate.py               Per-class COCO mAP through the deployed engine
  predict_image.py          Annotated predictions through the deployed engine
  benchmark.py              Latency -> capture interval and ground-speed limits
  gsd_calculator.py         Can the camera resolve the target at altitude X?
  motion_budget.py          How fast can it fly before blur/skew ruins the frame?
  finalize.py               Export + evaluate + predict + benchmark, in one step

scripts/pi_setup.sh         Pi 5 provisioning (run on the Pi)
scripts/hailo_compile.sh    ONNX -> .hef (run in WSL2 Ubuntu; x86_64 only)
config/example.yaml         Bench/simulation configuration
config/pi.yaml              Pi + camera + inference configuration
HANDOFF.md                  START HERE if you are picking this up cold
docs/BUILD_NOTES.md         Findings, problems hit, and what to do next
docs/USE_CASES.md           Roadmap: what is free, what is weeks, what is a company
docs/source/                The original research report
docs/briefs/                Critique, one-pager, procurement memo, compliance checklist
tests/                      347 tests, all hardware-free
```

## Commands

```bash
# Which indices can a given payload actually produce, and why not the others
agri-edge indices red,green,blue
agri-edge indices red,green,nir,red-edge

# Edge-system preflight: config, storage, telemetry, model provenance
agri-edge -c config/example.yaml preflight

# Capture run
agri-edge -c config/example.yaml fly --duration 600

# Inspect or offload the spool
agri-edge -c config/example.yaml spool --list 20
agri-edge -c config/example.yaml spool --export /media/ssd/flight-2026-09-13
```

`preflight` checks only what software can check. It is **not** an aviation
preflight — airspace, NOTAMs, certification, weather and pesticide label
conditions are all outside what a Python process can verify. See
[the compliance checklist](docs/briefs/04-compliance-checklist.md).

## Deploying to the Pi

```bash
bash scripts/pi_setup.sh                    # on the Pi: apt, hailo-all, PCIe Gen3, venv
bash scripts/hailo_compile.sh --arch hailo8l # in WSL2 Ubuntu: ONNX -> .hef
```

**The Hailo compiler is x86_64 Linux only.** Not Windows, not the Pi's ARM CPU.
On a Windows machine that means WSL2 (`wsl --install -d Ubuntu-22.04`, admin,
reboot). `hailo_compile.sh` checks `uname -m` and refuses early rather than
failing halfway through a compile.

Match `--arch` to the board: `hailo8l` = 13-TOPS AI HAT+, `hailo8` = 26-TOPS,
`hailo10h` = AI HAT+ 2. A mismatched `.hef` compiles cleanly and then refuses to
load, with an error that never mentions architecture.

Test the `.hef` standalone through `vendor/hailo-rpi5-examples` **before**
switching the config to `backend: hailo`. Debugging a bad `.hef` and a new engine
class simultaneously is how a day disappears.

## Optional extras

The core installs with numpy and PyYAML only, so the pipeline and its whole test
suite run on a laptop with no camera, no autopilot and no GDAL.

| Extra | Brings | Needed for |
|---|---|---|
| `mavlink` | pymavlink | Live autopilot telemetry |
| `camera` | picamera2 | Raspberry Pi camera capture |
| `cv` | opencv-python-headless | Better inference preprocessing |
| `geo` | rasterio | GeoTIFF/COG export on the workstation |
| `onnx` | onnxruntime | ONNX inference backend |

Hailo inference additionally needs HailoRT and a compiled `.hef`; model
compilation (PyTorch → ONNX → Hailo compiler) is part of the deployment
workflow, and not every operator survives the trip.

## Data model

Each spooled frame is a lossless `.npy` plus a JSON sidecar carrying telemetry,
QA results, index summaries, detections, model provenance and CRS. `.npy` because
it is lossless, needs no encoder dependency, and preserves above-8-bit
multispectral data; convert to GeoTIFF on the workstation.

```
Farm -> field -> season -> flight -> sensor -> raw imagery -> calibrated imagery
     -> orthomosaic -> index/model output -> agronomist observation -> action
```

Every derived product keeps a pointer back to its raw imagery, flight logs,
calibration data, model version and CRS. Without that chain, nobody can explain
why an NDVI anomaly moved between two flights.

## A caution on vegetation indices

`geo/indices.py` returns arithmetic, not agronomy. Comparing NDVI between dates
is only meaningful when illumination, exposure, reflectance calibration and
growth stage are all controlled. Uncalibrated digital numbers from a consumer RGB
sensor produce attractive maps that are agronomically misleading — which is worse
than no map, because a misleading map gets believed.

`IndexResult.calibrated` stays False for raw digital numbers, and the pipeline
sets it False for everything it computes on board. Downstream consumers should
refuse cross-date comparison on uncalibrated results.

## Regulatory context

Canadian operations are governed by Transport Canada Part IX (Basic / Advanced /
Level 1 Complex / SFOC, plus an RPOC for BVLOS) and, for spraying, Health Canada
SPN2026-02 of 30 June 2026. A Remote ID rule is pending from NPA 2026-005
(published 8 June 2026; comments closed 9 September 2026) — reserve power, a
serial port and physical space for a broadcast module on any custom airframe.

See [the compliance checklist](docs/briefs/04-compliance-checklist.md). Current to
13 September 2026; re-verify before 31 March 2027.
