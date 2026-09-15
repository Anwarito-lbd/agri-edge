"""Export a trained YOLOX checkpoint to ONNX, ready for Hailo compilation.

Replaces `vendor/YOLOX/tools/export_onnx.py`, which calls `torch.onnx._export` --
a private API removed in torch 2.x. Rather than patching vendored upstream code
(which is gitignored and would be lost on re-clone), the export lives here.

Export choices, all of which matter downstream:

* **`decode_in_inference = False`** -- the ONNX graph emits the *raw* head, and
  the grid/stride decode happens on the host in `agri_edge.inference.yolox`.
  Hailo's compiler cannot handle the decode ops well, and the host decode is
  a few numpy operations.
* **opset 11** -- Hailo's ONNX parser is conservative; newer opsets fail at
  compile time with unhelpful messages.
* **Fixed 640x640, batch 1** -- Hailo requires static shapes.
* **No NMS in the graph** -- NMS runs on the host, class-wise.
* **SiLU replaced with an explicit sigmoid-multiply** -- exactly what upstream
  does, because fused SiLU does not survive some ONNX consumers.

Also writes the `.meta.json` provenance sidecar that `ModelMetadata.load_beside`
reads. `validated_locally` is written **false**; see the note at the bottom.

Run:
    python training/export_onnx.py \
        --exp training/exps/weed_crop_yolox_s.py \
        --ckpt YOLOX_outputs/weed_crop_yolox_s/best_ckpt.pth \
        --output models/weed_crop_yolox_s.onnx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from torch import nn


def build_meta(name: str, class_names: list[str], ckpt_path: Path, input_size) -> dict:
    return {
        "name": name,
        "version": "0.1.0",
        "trained_on": [
            "LibreYOLO/weed-crop-aerial (CC BY 4.0) -- credit Roboflow 100 / Roboflow Universe",
        ],
        "class_names": class_names,
        "input_size": list(input_size),
        "architecture": "YOLOX-s (Apache-2.0, Megvii)",
        "checkpoint": str(ckpt_path),
        "decode": "raw head; decode + NMS on host via agri_edge.inference.yolox",
        # Stays false until the model has been validated against local field
        # observations by crop, growth stage, location, season, altitude and
        # lighting. Detection.may_drive_treatment is gated on this: while it is
        # false, output is decision support and must not drive chemical
        # application. Flipping it is a deliberate act, not a build step.
        "validated_locally": False,
        "validation_notes": (
            "Trained on Roboflow-100 aerial imagery (Australian/US provenance, 95% weed "
            "/ 5% crop class balance). NOT validated on Canadian field imagery. "
            "Decision support only."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exp", type=Path, default=Path("training/exps/weed_crop_yolox_s.py"))
    ap.add_argument("--ckpt", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path("models/weed_crop_yolox_s.onnx"))
    ap.add_argument("--opset", type=int, default=11)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--name", type=str, default=None, help="Built-in exp name instead of --exp")
    ap.add_argument("--class-names", type=str, default="crop,weed")
    args = ap.parse_args()

    from yolox.exp import get_exp
    from yolox.models.network_blocks import SiLU
    from yolox.utils import replace_module

    exp = get_exp(str(args.exp) if args.name is None else None, args.name)

    model = exp.get_model()
    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    if "model" in ckpt:
        ckpt = ckpt["model"]
    model.load_state_dict(ckpt)
    model.eval()

    model = replace_module(model, nn.SiLU, SiLU)
    # The host decodes. See agri_edge/inference/yolox.py.
    model.head.decode_in_inference = False

    h, w = exp.test_size
    dummy = torch.randn(args.batch_size, 3, h, w)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.onnx.export(
        model,
        dummy,
        str(args.output),
        input_names=["images"],
        output_names=["output"],
        opset_version=args.opset,
        dynamo=False,          # the legacy tracer; dynamo does not honour opset 11
        do_constant_folding=True,
    )

    class_names = [c.strip() for c in args.class_names.split(",") if c.strip()]
    if len(class_names) != exp.num_classes:
        print(
            f"  WARNING: --class-names has {len(class_names)} entries but the model has "
            f"{exp.num_classes} classes. Labels will be wrong.",
            file=sys.stderr,
        )

    meta_path = args.output.with_suffix(args.output.suffix + ".meta.json")
    meta_path.write_text(
        json.dumps(build_meta(args.output.stem, class_names, args.ckpt, (h, w)), indent=2),
        encoding="utf-8",
    )

    size_mb = args.output.stat().st_size / 1e6
    print(f"Exported {args.output}  ({size_mb:.1f} MB, opset {args.opset}, {h}x{w}, raw head)")
    print(f"Wrote    {meta_path}  (validated_locally=false)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
