# Model card — `imageweeds_yolox_s`

**Species-level weed detection from nadir aerial imagery.** This is the model that
matches the product decision of 14 Sept 2026: identify mature weeds *by species*,
because which species it is determines which chemical you reach for.

## What it is

| | |
|---|---|
| Task | Object detection, 5 classes |
| Classes | `ragweed`, `waterhemp`, `horseweed`, `redrootpigweed`, `kochia` |
| Architecture | YOLOX-s (Apache-2.0, Megvii), 8.94M parameters |
| Input | 640×640 RGB, letterboxed, **raw 0–255** (no /255 normalisation) |
| Output | Raw head, 8400 anchors × (4 box + 1 obj + 5 cls). Decode and NMS on host |
| Training data | `Project-AgML/ImageWeeds_aerial_weed_detection`, CC BY 4.0 |
| Split | 391 train / 90 valid / 70 test, **split by source image** |
| Boxes | 1,691 / 391 / 306 |
| Initialised from | COCO-pretrained `yolox_s.pth` |

Why these five species: they are the herbicide-resistant weeds that actually
matter on the Canadian Prairies. Kochia and waterhemp in particular have
widespread glyphosate resistance, so identifying them rather than just "a weed"
changes the management decision.

## Why this dataset, and how it was checked

The previous dataset (`weed-crop-aerial`) turned out not to be aerial — close-range
ground shots plus indoor propagation trays. So this one was **verified by looking
at the imagery before any training**: genuine nadir views of a real tilled field,
crop rows and tractor tracks visible, harsh natural sunlight.

Class balance is also far healthier than the previous dataset's 95/5 split:

| Class | Boxes | Share |
|---|---:|---:|
| ragweed | 647 | 27.1% |
| kochia | 616 | 25.8% |
| waterhemp | 419 | 17.5% |
| horseweed | 384 | 16.1% |
| redroot pigweed | 322 | 13.5% |

## Known limitations

**1. Only transplanted specimens are annotated.** The target weeds were grown in
black pots and placed into research plots. Each frame *also* contains dozens of
naturally-occurring weeds that are **not** labelled. Two consequences:

- Measured precision **understates** real performance — correct detections of
  unlabelled natural weeds are scored as false positives.
- Recall is capped by the annotation, not the model.
- The model can learn container cues alongside plant morphology.

None of this is fixable by tuning. It is fixed by annotating your own field
imagery, which is the phase-8 work regardless.

**2. Species discrimination did not work, and this is now measured, not feared.**
Across the 70-image test split the model emits 421 detections, and **76.2% of
them are `horseweed`** — against horseweed being 14% of the ground truth:

| Class | GT boxes | Predicted |
|---|---:|---:|
| ragweed | 95 | 9 |
| waterhemp | 52 | 5 |
| horseweed | 44 | **321** |
| redrootpigweed | 36 | 6 |
| kochia | 79 | 80 |

It has collapsed onto one class. Only kochia is predicted at a sane rate.

**But the boxes are right.** Scoring the identical model as a single-class
detector — collapsing predictions *and* ground truth to `weed` — roughly doubles
measured performance:

| Mode | AP@.50:.95 | AP@.50 |
|---|---:|---:|
| 5-class species | 0.132 | 0.246 |
| **Binary `weed`** | **0.247** | **0.520** |

So this is a competent weed *localiser* wearing a species label it cannot
support. **Ship it collapsed:**

```yaml
inference:
  class_names: [ragweed, waterhemp, horseweed, redrootpigweed, kochia]
  collapse_labels_to: weed
```

The predicted class is kept in each detection's `source_label`, so nothing is
thrown away — the model stops *claiming* a species while still recording what it
guessed. Reproduce with:

```bash
python training/evaluate.py --model models/imageweeds_yolox_s.onnx     --root data/imageweeds --split test --collapse-to weed
```

Note that 0.520 is still an **understatement**: unlabelled natural weeds in every
frame are scored as false positives (see limitation 1).

Species ID remains the right product goal — species is what picks the chemical —
but it needs locally annotated data, not tuning.

**3. Small dataset.** 391 training images, 1,691 boxes across 5 classes — roughly
340 examples per class. Heavy augmentation (mosaic, mixup, ±180° rotation, since
nadir imagery has no canonical "up") compensates somewhat.

**4. One site, one season.** Soil colour, crop, growth stage and lighting are all
from a single research location. Transfer to different soils and regions is
unmeasured.

## Operating envelope

For a ~30 cm mature weed with a Raspberry Pi Camera Module 3, needing ~20 px
across the target:

| | Max altitude |
|---|---:|
| Whole-frame inference | 6.1 m AGL |
| **Tiled inference** | **39 m AGL** |

Tiling is **required** for survey-altitude operation, and tiling a full 4056 px
frame is 48 inferences per frame — roughly 7.3 s on a CPU but ~288 ms on the
Hailo NPU. **The AI HAT+ is a requirement for this model, not an upgrade.**

Recompute for your own optics: `python training/gsd_calculator.py --target-size 30`.

## Not approved for

**`validated_locally: false`**, enforced in code: every `Detection` carries the
flag, `may_drive_treatment` is False while it is false, and each spooled frame
records `decision_support_only`.

This model must not drive chemical application — not because the code forbids it,
but because nothing has been measured on your fields that would justify it. See
the limitations above, particularly (1).

## Reproducing

```bash
python training/prepare_imageweeds.py
python training/yolo_to_coco.py --root data/imageweeds
python training/verify_coco.py --root data/imageweeds
python vendor/YOLOX/tools/train.py -f training/exps/imageweeds_yolox_s.py \
    -d 1 -b 8 --fp16 -c weights/yolox_s.pth
python training/finalize.py --exp imageweeds_yolox_s
```

## Attribution (required — CC BY 4.0)

> Rai, N., Villamil Mahecha, M., Christensen, A., Quanbeck, J., Zhang, Y.,
> Howatt, K., Ostlie, M., Sun, X. *Multi-format open-source weed image dataset
> for real-time weed identification in precision agriculture.* Data in Brief 51
> (2023), 109691.

Also in `data/imageweeds/ATTRIBUTION.md` and [../NOTICE.md](../NOTICE.md).

## Results

*Measured 2026-09-14 22:27 UTC on the held-out **test** split, via `training/evaluate.py`,
running inference through the deployed `OnnxEngine`.*

*Checkpoint: best_ckpt.pth (highest validation AP)*

| Class | AP@.50:.95 | AP@.50 | GT boxes |
|---|---:|---:|---:|
| ragweed | 0.0896 | 0.2105 | 95 |
| waterhemp | 0.0080 | 0.0348 | 52 |
| horseweed | 0.3024 | 0.5250 | 44 |
| redrootpigweed | 0.0392 | 0.0764 | 36 |
| kochia | 0.2189 | 0.3850 | 79 |
| **overall** | **0.1316** | **0.2463** | 306 |

Inference latency: run `python training/benchmark.py --tiled --capture-width 4056`
on the target device. Laptop CPU tiled ≈ 7.3 s/frame; measure on the Pi with the
Hailo backend before setting any flight parameter.
