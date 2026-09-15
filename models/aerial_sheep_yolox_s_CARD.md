# Model card — `aerial_sheep_yolox_s`

**Livestock counting from nadir aerial imagery.** The one model in this project
that runs usefully on a bare Raspberry Pi with no AI accelerator.

## What it is

| | |
|---|---|
| Task | Object detection, 1 class: `sheep` |
| Architecture | YOLOX-s (Apache-2.0, Megvii), 8.94M parameters |
| Input | 640×640 RGB, letterboxed, **raw 0–255** |
| Training data | `keremberke/aerial-sheep-object-detection` (Roboflow Universe / Riis) |
| Licence | **Public Domain** |
| Split | 3,609 train / 350 valid / 174 test images |
| Boxes | 113,494 / 11,334 / 5,603 — **130,431 total** |
| Density | mean 31 objects/image, max 105 |

## Why livestock is the easy win

Every other target in this project is capped by optics. This one is not:

| Target | Whole-frame ceiling | Tiling needed at survey altitude? |
|---|---:|---|
| 3 cm weed seedling | 0.6 m | yes — and still capped at 3.9 m |
| 30 cm mature weed | 6.1 m | yes |
| **120 cm sheep** | **24.6 m** | **no** |
| **200 cm cow** | **41.0 m** | **no** |

Cattle are detectable at 41 m AGL with plain whole-frame inference at ~10 FPS on
a CPU. No tiling, no Hailo NPU, no 48-inferences-per-frame. Recompute for your
optics with `python training/gsd_calculator.py --target-size 200`.

Sheep were used because that is what exists as public aerial data — and being
smaller, they are the **conservative** case. Anything that works on sheep works
on cattle with margin.

## Data quality — verified, not assumed

Three things were checked before training, because two earlier datasets in this
project turned out not to be what their names claimed:

**1. It is genuinely aerial.** Inspected directly: filenames are `DJI_*`, the
view is true nadir, sheep on pasture with long low-sun shadows. No indoor trays,
no ground-level close-ups.

**2. The splits do not leak.** Roboflow generated "3 versions of each source
image" by augmentation. Had augmented copies of one photo landed on both sides of
a split, every number here would be inflated. Roboflow filenames encode their
source (`NAME.rf.<hash>.jpg`), so this was checked rather than trusted:

| Split | Images | Distinct source photos | Augmentation |
|---|---:|---:|---:|
| train | 3,609 | 1,203 | 3.0× |
| valid | 350 | 350 | 1.0× |
| test | 174 | 174 | 1.0× |

**No source photo appears in more than one split.** Train is augmented, valid and
test are not — the split happened before augmentation, which is correct.

**3. Labels are not silently truncated.** 24.4% of training images carry more than
50 objects, max 105. YOLOX defaults to `max_labels=50` for the dataset and 120
after mosaic — at those values a quarter of the training images would have lost
labels **with no error**, teaching the model that visible sheep are background.
Raised to 150 and 450; verified that the densest image (105 objects) retains all
105.

## Known limitations

**1. Sheep, not cattle.** The class is `sheep`. It will likely transfer to cattle
with fine-tuning — they are larger and higher-contrast against pasture — but
that is **untested**. Do not claim cattle performance from these numbers.

**2. One visual context.** Green pasture, low sun, strong shadows. Snow, mud, dry
stubble, dense tree cover and midday overhead light are all unrepresented.

**3. Counting is not detection.** Good AP does not guarantee an accurate *count*.
Animals occlude each other, stand in tight clusters, and move between frames.
Producing a herd count from per-frame detections needs de-duplication across
overlapping frames — that work is not done here.

**4. Shadows are a confound.** In this imagery every sheep casts a long dark
shadow. The model may be using shadow as a cue, which would degrade under
overhead sun. Worth testing before relying on it at midday.

## Operating envelope

| | Sheep (120 cm) | Cattle (200 cm) |
|---|---:|---:|
| Whole-frame, Pi Camera Module 3 | 24.6 m AGL | **41.0 m AGL** |
| Tiled | 155 m | 260 m — above the 122 m legal ceiling |

At 41 m the legal ceiling (122 m AGL) and battery endurance bind long before
inference does. **This is the use case where the hardware stops being the
constraint.**

## Not approved for

**`validated_locally: false`**, enforced in code. Counting animals is lower-stakes
than directing chemical application, but a miscount that drives a stock decision
is still a real cost. Validate on your own herd, in your own light, before
trusting a number.

## Reproducing

```bash
python training/prepare_aerial_sheep.py      # downloads, converts, checks leakage
python training/yolo_to_coco.py   --root data/aerial-sheep
python training/verify_coco.py    --root data/aerial-sheep
python vendor/YOLOX/tools/train.py -f training/exps/aerial_sheep_yolox_s.py \
    -d 1 -b 8 --fp16 -c weights/yolox_s.pth
python training/finalize.py --exp aerial_sheep_yolox_s
```

## Attribution

Public Domain — **no obligation**. Credited anyway:

> Aerial Sheep Dataset, by Riis, via
> [Roboflow Universe](https://universe.roboflow.com/riis/aerial-sheep), 2022.

Note this is the only dataset here with no licence obligation. The weed datasets
are CC BY 4.0 and their attribution **must** follow anything you ship.

## Results

*Measured 2026-09-15 14:55 UTC on the held-out **test** split, via `training/evaluate.py`,
running inference through the deployed `OnnxEngine`.*

*Checkpoint: best_ckpt.pth (highest validation AP)*

| Class | AP@.50:.95 | AP@.50 | GT boxes |
|---|---:|---:|---:|
| sheep | 0.4664 | 0.9049 | 5603 |
| **overall** | **0.4664** | **0.9049** | 5603 |

Inference latency: run `python training/benchmark.py --model models/aerial_sheep_yolox_s.onnx`
on the target device. Whole-frame, so expect roughly the un-tiled figures — and
unlike the weed models, no NPU is required.
