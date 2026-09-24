# Field training loop — from your own field to a model you can trust

You have a Pi 5 and a Camera Module 3. That is enough to start: the aircraft is
not needed to collect training data. Every step below is a command in this repo.

## 0. Kit
Pi 5 + Camera Module 3 on a ~2 m pole pointing straight down, a USB GNSS
receiver (any u-blox, ~C$30), a power bank. `bash scripts/pi_setup.sh` first,
then verify the camera channel order (HANDOFF.md) — once.

## 1. Walk the field
```bash
agri-edge -c config/pi.yaml walk --gps /dev/ttyACM0 --pole-height 2.0 --duration 1800
```
Frames are spooled with GNSS position and tagged `capture_mode: walk`. Walk
different parts of the field, and come back on **different days** — validation
requires at least two capture days, because a model that only ever saw one
morning's light has not been tested.

## 2. Pick what to label
```bash
agri-edge -c config/pi.yaml label-export --n 150 --classes kochia,ragweed,horseweed --out labeling/
```
Chooses frames where the model is unsure or may have missed something, spread
across the field, plus 15 % random frames so the set is not all hard cases.
Writes PNGs, `tasks.json` (with the model's boxes as pre-annotations) and
`label_config.xml`.

## 3. Label in Label Studio
```bash
docker run -p 8080:8080 -e LOCAL_FILES_SERVING_ENABLED=true \
  -e LOCAL_FILES_DOCUMENT_ROOT=/label-studio/data \
  -v $PWD/labeling:/label-studio/data heartexlabs/label-studio
```
Create a project with `label_config.xml`, add local storage `/label-studio/data`,
import `tasks.json`. **Correct every box** — the pre-annotations are the model's
guesses, and the import ignores anything that is only a prediction. Export as JSON.

## 4. Import as COCO, split by day
```bash
agri-edge label-import --export export.json --classes kochia,ragweed,horseweed \
    --out data/local/annotations --val-days 1
```
The last capture day becomes validation, so near-identical frames from one walk
never sit on both sides of the split.

## 5. Retrain (workstation)
Fine-tune the existing YOLOX exp on `instances_train.json` (see `training/`),
export to ONNX with `training/export_onnx.py`.

## 6. Validate locally — the only way to `validated_locally`
```bash
agri-edge -c config/pi.yaml validate-model --model models/imageweeds_yolox_s.onnx \
    --coco data/local/annotations/instances_val.json --classes kochia \
    --reviewer "Your Name"
```
Writes a report to `ai/model_registry/validations/` with the model file's
sha256, the dataset hash, per-class AP50/recall and every criterion
(≥ 200 images, ≥ 2 days, local site/field, AP50 ≥ 0.5, recall ≥ 0.7, a named
reviewer). The engine then trusts that exact file — and only that file — as
locally validated; a retrained file needs its own report. A hand-edited
`validated_locally: true` in a meta file is ignored.

Spot-spray prescriptions (`agri-edge prescription`, ops `/api/ops/prescriptions`)
can only be approved from detections of a model with a passing report.
