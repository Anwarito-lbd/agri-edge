# Third-party notices and licence obligations

This project is built for commercial use, so the components were chosen for
permissive licensing as much as for capability. Keep this file current — these
are obligations, not credits.

## The deliberate exclusion

**Ultralytics YOLO (v5/v8/v11) is AGPL-3.0 and is not used here.** Under AGPL,
distributing the software — or merely offering it over a network — obliges you to
release your own source under the same terms. YOLOv6 is GPL-3.0 with the same
problem. Both are excluded on purpose.

If someone adds `pip install ultralytics` to this project, that decision needs to
be made deliberately and with the licence understood, not absorbed as a
convenience.

## Components

| Component | Licence | What you must do |
|---|---|---|
| [YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) (Megvii) | Apache-2.0 | Retain the copyright and licence notice; state changes. Closed-source distribution is permitted. |
| [`LibreYOLO/weed-crop-aerial`](https://huggingface.co/datasets/LibreYOLO/weed-crop-aerial) | **CC BY 4.0** | **Attribution is required** — see below. Commercial use permitted. |
| ONNX Runtime | MIT | Retain notice. |
| NumPy, PyYAML, Pillow | BSD-3 / MIT / HPND | Retain notice. |
| Picamera2 | BSD-2 | Retain notice. Pi runtime only. |
| pycocotools | BSD-2 | Retain notice. Evaluation only, not shipped. |
| PyTorch | BSD-3 | Retain notice. Training only, not shipped to the Pi. |
| HailoRT / Dataflow Compiler | Hailo proprietary | Review Hailo's terms before redistributing anything produced with them, including `.hef` files. |
| `agri_edge` (this repo) | yours | — |

## Required attribution for the training data

The model is trained on data licensed CC BY 4.0. Attribution must survive into
anything shipped, published, or demonstrated that was trained on it:

> Trained in part on the *weed-crop-aerial* dataset from the Roboflow 100
> benchmark (Roboflow Universe), licensed CC BY 4.0.
>
> Ciaglia, F., Zuppichini, F. S., Guerrie, P., McQuade, M., Solawetz, J.
> *Roboflow 100: A Rich, Multi-Domain Object Detection Benchmark.*
> arXiv:2211.13523, 2022.

The same text is written to `data/weed-crop-aerial/ATTRIBUTION.md` by
`training/download_data.py`.

## Vendored code

`vendor/` holds upstream repositories cloned via `gh` and is **gitignored**, so
third-party source never merges into this tree and their licences stay distinct
from yours. Re-create it with:

```bash
gh repo clone Megvii-BaseDetection/YOLOX vendor/YOLOX -- --depth 1
gh repo clone hailo-ai/hailo-rpi5-examples vendor/hailo-rpi5-examples -- --depth 1
```

## Model weights

`weights/yolox_s.pth` is the COCO-pretrained YOLOX-s checkpoint released by
Megvii under Apache-2.0. Models fine-tuned from it inherit no copyleft
obligation, but the YOLOX attribution above still applies.

## Training datasets (2 of 3) — ImageWeeds, the species model

| Component | Licence | What you must do |
|---|---|---|
| [`Project-AgML/ImageWeeds_aerial_weed_detection`](https://huggingface.co/datasets/Project-AgML/ImageWeeds_aerial_weed_detection) | **CC BY 4.0** | **Attribution required.** Commercial use permitted. |

Required credit for anything trained on it:

> Rai, N., Villamil Mahecha, M., Christensen, A., Quanbeck, J., Zhang, Y.,
> Howatt, K., Ostlie, M., Sun, X. *Multi-format open-source weed image dataset
> for real-time weed identification in precision agriculture.* Data in Brief 51
> (2023), 109691. Licensed CC BY 4.0.

Written by `training/prepare_imageweeds.py` to `data/imageweeds/ATTRIBUTION.md`.

`datasets` (Hugging Face) is Apache-2.0 and is a **training-only** dependency —
it never reaches the Pi.

## Training datasets (3 of 3) — Aerial Sheep, the livestock model

| Component | Licence | What you must do |
|---|---|---|
| [Aerial Sheep Dataset](https://universe.roboflow.com/riis/aerial-sheep) (Riis, via Roboflow Universe) | **Public Domain** | **Nothing.** No attribution obligation follows the model. |

Credited anyway in `data/aerial-sheep/ATTRIBUTION.md`, because it costs nothing:

> Aerial Sheep Dataset by Riis, via Roboflow Universe (2022). Public Domain.
> Mirrored on Hugging Face as `keremberke/aerial-sheep-object-detection`.

This is the **only** model here whose output carries no attribution obligation —
worth remembering when deciding what to demonstrate publicly first.

## Where the obligations actually live

Attribution has to travel with the *model*, not just the repo, because a model
file can be copied out of here and deployed on its own. So each model's
`.meta.json` sidecar carries its own `trained_on` credit, and
`training/export_onnx.py` derives it from the experiment's dataset — refusing to
export at all if the dataset has no registered provenance.

That refusal exists because the sidecars were once **all wrong in the same way**:
a hardcoded default meant every model, including a stock COCO detector, claimed
to be trained on `weed-crop-aerial`. `tests/test_provenance.py` now holds the
line.
