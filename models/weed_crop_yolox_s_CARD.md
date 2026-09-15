# Model card — `weed_crop_yolox_s`

Fill in the metrics after the final training run (`training/evaluate.py --split test`).
This file is the human-readable companion to the machine-readable
`<model>.onnx.meta.json` sidecar that the runtime reads.

## What it is

| | |
|---|---|
| Task | Object detection, 2 classes: `crop`, `weed` |
| Architecture | YOLOX-s (Apache-2.0, Megvii), 8.94M parameters |
| Input | 640×640 RGB, letterboxed, **raw 0–255** (no /255 normalisation) |
| Output | Raw head, 8400 anchors × (4 box + 1 obj + 2 cls). Decode and NMS run on the host |
| Training data | `LibreYOLO/weed-crop-aerial` — 823 train / 235 val / 118 test, CC BY 4.0 |
| Initialised from | COCO-pretrained `yolox_s.pth` |
| Intended use | **Decision support for weed scouting from aerial imagery** |

## What it is NOT approved for

**`validated_locally: false`.** The runtime enforces this: every `Detection`
carries the flag, `Detection.may_drive_treatment` returns False while it is
false, and each spooled frame records `decision_support_only: true`.

Concretely, this model must not drive chemical application. Not because the code
forbids it — because nothing has been measured that would justify it.

## Known limitations

**0. The dataset is three different visual domains, and the `crop` class comes
almost entirely from indoor imagery.**

Splitting the dataset by filename prefix and counting labels:

| Sub-population | Images | crop boxes | weed boxes |
|---|---:|---:|---:|
| `3xxxx_` — outdoor, close-up of soil | 883 | **7** | 5,926 |
| `IMG_*` — **indoor propagation trays** | 241 | **403** | 1,401 |
| other — mixed ground-level | 52 | 0 | 115 |

**98.3% of every `crop` label lives in the indoor tray images** — visibly plastic
seed trays, electrical cables and a plastic floor grate, not a field.

So this is effectively two models in one file: a weed detector trained on outdoor
soil close-ups, and a crop detector trained indoors on seedling trays. The
reported `crop` AP measures the latter. **It says nothing about detecting a crop
in a field**, and should not be quoted as if it did.

Practical consequence: treat the `weed` class as the usable output. Treat `crop`
as unvalidated for any outdoor use until retrained on real field imagery.

**1. Severe class imbalance: 95% weed, 5% crop — which mattered less than expected.**

| Split | crop boxes | weed boxes |
|---|---:|---:|
| train | 278 (5%) | 5,188 (95%) |
| valid | 47 (3%) | 1,558 (97%) |
| test | 85 (11%) | 696 (89%) |

The prediction here was that `crop`, with 278 training boxes against weed's
5,188, would be close to untrainable and score near zero. **That was wrong.** At
convergence the two classes are within half a point of each other on validation
(crop 47.6, weed 48.1).

Two plausible reasons: crop plants are large and visually distinctive while weeds
are small seedlings, so the harder class is the abundant one; and mosaic
augmentation plus COCO pretraining together stretch a few hundred examples much
further than the raw count suggests.

The operational lesson stands even though the prediction failed: **read per-class
AP, never the aggregate.** A model that ignored `crop` entirely would still have
posted a respectable mAP, and only the per-class table could have told you —
which is exactly how you would have caught it had the pessimistic prediction been
right instead.

**2. Train/test distribution shift.** The test split is 11% crop against
training's 5%. Test numbers are not drawn from the training distribution.

**3. The training imagery is NOT aerial, despite the dataset name.**

`weed-crop-aerial` is a Roboflow-100 *domain-category* label, not a description of
the photographs. Inspecting them shows **close-range ground-level images, roughly
30–80 cm above the soil** — individual seedlings filling a large fraction of the
frame, with visible soil texture and crop leaves at close range.

This is the most consequential limitation, because it is a scale mismatch, not
merely a geographic one. A model trained on seedlings at ~50 cm will not transfer
to the same seedlings viewed from 30 m, where they are a couple of pixels across.
See the altitude table in the README: at 30 m AGL a 3 cm seedling is 2.6 px at
native resolution. The model is not the limiting factor — the optics are.

Practical reading: this checkpoint suits **low-altitude or ground-level**
deployment (a boom-mounted camera, a ground robot, or a drone at ~3 m with tiled
inference). It is not a survey-altitude model.

**4. Provenance mismatch with the deployment target.** Crop species, growth
stages, soil colour, row spacing and lighting all differ from Canadian fields.
Performance on Canadian canola, soybean or potato is **unknown and should be
assumed poor** until measured.

**5. Small dataset.** 823 training images. Heavy augmentation (mosaic, mixup,
±180° rotation) compensates somewhat, but this is a pilot-scale model.

## Before flipping `validated_locally` to true

This is a deliberate act with real consequences, not a build step. It requires:

1. Imagery collected from the **actual target fields**, at the operating
   altitude, in the operating light.
2. Annotation (CVAT or Label Studio — both open-source and self-hosted, so the
   imagery stays yours).
3. Fine-tuning from this checkpoint, then re-evaluating **per class**.
4. Recording in `validation_notes` exactly what was validated: crop, growth
   stage, location, season, altitude, lighting.

Anything narrower than that is a claim the data does not support.

## Reproducing

```bash
python training/download_data.py
python training/yolo_to_coco.py
python training/verify_coco.py
python vendor/YOLOX/tools/train.py -f training/exps/weed_crop_yolox_s.py \
    -d 1 -b 8 --fp16 -c weights/yolox_s.pth
python training/export_onnx.py --ckpt YOLOX_outputs/weed_crop_yolox_s/best_ckpt.pth
python training/evaluate.py --model models/weed_crop_yolox_s.onnx --split test
```

## Attribution (required — CC BY 4.0)

> Trained in part on the *weed-crop-aerial* dataset from the Roboflow 100
> benchmark (Roboflow Universe), licensed CC BY 4.0. Ciaglia, F., Zuppichini,
> F. S., Guerrie, P., McQuade, M., Solawetz, J. *Roboflow 100: A Rich,
> Multi-Domain Object Detection Benchmark.* arXiv:2211.13523, 2022.

See [../NOTICE.md](../NOTICE.md).

## Results

*Measured 2026-09-14 04:31 UTC on the held-out **test** split, via `training/evaluate.py`,
running inference through the deployed `OnnxEngine`.*

*Checkpoint: best_ckpt.pth (highest validation AP)*

| Class | AP@.50:.95 | AP@.50 | GT boxes |
|---|---:|---:|---:|
| crop | 0.3628 | 0.6301 | 85 |
| weed | 0.4221 | 0.7485 | 696 |
| **overall** | **0.3924** | **0.6893** | 781 |

Inference latency: run `python training/benchmark.py` on the target device.
Laptop CPU (x86, ONNX Runtime) measured ~100 ms/frame ≈ 10 FPS; the Pi CPU will
be substantially slower and the Hailo NPU substantially faster. Measure on the
device you will actually fly.
