"""Evaluate the exported ONNX model with COCO mAP, reported per class.

Runs inference through `agri_edge.inference.engine.OnnxEngine` -- the exact class
the Pi runs -- rather than through YOLOX's torch evaluator. The number that
matters is the one describing what actually ships, including the letterbox and
the host-side decode. A torch-side mAP can look fine while the deployed path is
subtly broken.

**Read per-class AP, not the aggregate.** This dataset is 95% weed / 5% crop, so
a model that ignores crop entirely still posts a respectable mAP. The aggregate
number will flatter a model that is useless for half its job.

Run:
    python training/evaluate.py --model models/weed_crop_yolox_s.onnx --split test
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

import numpy as np

DEFAULT_ROOT = Path("data/weed-crop-aerial")


def evaluate(
    model_path: Path,
    root: Path,
    split: str,
    conf: float,
    limit: int | None = None,
    collapse_to: str | None = None,
) -> dict:
    from PIL import Image
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval

    from agri_edge.inference.engine import OnnxEngine

    ann_path = root / "annotations" / f"instances_{split}.json"
    with contextlib.redirect_stdout(io.StringIO()):
        coco = COCO(str(ann_path))

    cat_ids = sorted(coco.getCatIds())
    cats = {c["id"]: c["name"] for c in coco.loadCats(cat_ids)}

    engine = OnnxEngine(model_path, confidence_threshold=conf, collapse_labels_to=collapse_to)
    names = engine.class_names or [cats[c] for c in cat_ids]

    if collapse_to:
        # Score the model as a single-class detector: rewrite ground truth to one
        # category as well, otherwise every prediction is scored against the wrong
        # class and the result is meaningless rather than merely coarse.
        #
        # This is the honest measurement for a model that localises well and
        # classifies badly -- it answers "does it find the weeds", having stopped
        # asking "does it name them".
        for ann in coco.anns.values():
            ann["category_id"] = 1
        coco.dataset["categories"] = [
            {"id": 1, "name": collapse_to, "supercategory": collapse_to}
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            coco.createIndex()
        cat_ids = [1]
        cats = {1: collapse_to}
        names = [collapse_to]
        print(f"collapsed: every class scored as '{collapse_to}'")

    print(f"model   : {engine.metadata.name} v{engine.metadata.version}")
    print(f"split   : {split}  ({len(coco.getImgIds())} images)  conf>={conf}")
    print(f"classes : {names}")
    if not engine.metadata.validated_locally:
        print("          validated_locally=false -- decision support only")
    print()

    img_ids = sorted(coco.getImgIds())
    if limit:
        img_ids = img_ids[:limit]

    results = []
    n_dets = 0
    for i, img_id in enumerate(img_ids, 1):
        info = coco.loadImgs(img_id)[0]
        img = np.array(Image.open(root / split / "images" / info["file_name"]).convert("RGB"))
        h, w = img.shape[:2]

        for det in engine.infer(img):
            # normalised xyxy -> absolute COCO xywh
            x1, y1, x2, y2 = det.bbox
            x1, x2 = x1 * w, x2 * w
            y1, y2 = y1 * h, y2 * h
            cls_idx = names.index(det.label) if det.label in names else 0
            results.append(
                {
                    "image_id": img_id,
                    "category_id": cat_ids[cls_idx],
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "score": float(det.confidence),
                }
            )
            n_dets += 1

        if i % 25 == 0 or i == len(img_ids):
            print(f"  inferred {i}/{len(img_ids)} images, {n_dets} detections", end="\r")

    print(f"  inferred {len(img_ids)}/{len(img_ids)} images, {n_dets} detections    ")

    if not results:
        print(
            "\nNo detections at all -- mAP is 0 by definition and tells you nothing.\n"
            "Check the confidence threshold and that training actually converged."
        )
        return {"mAP": 0.0, "per_class": {}, "n_detections": 0}

    with contextlib.redirect_stdout(io.StringIO()):
        dt = coco.loadRes(results)
        ev = COCOeval(coco, dt, "bbox")
        ev.params.imgIds = img_ids
        ev.evaluate()
        ev.accumulate()
        ev.summarize()

    overall = {
        "mAP": float(ev.stats[0]),        # IoU 0.50:0.95
        "mAP50": float(ev.stats[1]),
        "mAP75": float(ev.stats[2]),
        "mAP_small": float(ev.stats[3]),
        "mAP_medium": float(ev.stats[4]),
        "mAP_large": float(ev.stats[5]),
    }

    # Per-class AP. precision has shape [T, R, K, A, M]:
    # IoU thresholds, recall, category, area range, max dets.
    precision = ev.eval["precision"]
    per_class: dict[str, dict] = {}
    for k, cat_id in enumerate(cat_ids):
        p_all = precision[:, :, k, 0, 2]
        p_50 = precision[0, :, k, 0, 2]
        n_gt = len(coco.getAnnIds(catIds=[cat_id], imgIds=img_ids))
        per_class[cats[cat_id]] = {
            "AP": float(np.mean(p_all[p_all > -1])) if (p_all > -1).any() else float("nan"),
            "AP50": float(np.mean(p_50[p_50 > -1])) if (p_50 > -1).any() else float("nan"),
            "n_ground_truth": n_gt,
        }

    print()
    print(f"{'class':<12}{'AP@.5:.95':>12}{'AP@.50':>10}{'GT boxes':>11}")
    print("-" * 45)
    for name, m in per_class.items():
        ap = "n/a" if np.isnan(m["AP"]) else f"{m['AP']:.4f}"
        ap50 = "n/a" if np.isnan(m["AP50"]) else f"{m['AP50']:.4f}"
        print(f"{name:<12}{ap:>12}{ap50:>10}{m['n_ground_truth']:>11}")
    print("-" * 45)
    print(f"{'OVERALL':<12}{overall['mAP']:>12.4f}{overall['mAP50']:>10.4f}")

    valid = [m["AP"] for m in per_class.values() if not np.isnan(m["AP"])]
    if valid and len(valid) > 1:
        worst = min(per_class.items(), key=lambda kv: kv[1]["AP"] if not np.isnan(kv[1]["AP"]) else 9)
        best = max(per_class.items(), key=lambda kv: kv[1]["AP"] if not np.isnan(kv[1]["AP"]) else -1)
        if worst[1]["AP"] < best[1]["AP"] * 0.5:
            print(
                f"\n  '{worst[0]}' AP ({worst[1]['AP']:.3f}) is less than half "
                f"'{best[0]}' ({best[1]['AP']:.3f}).\n"
                f"  With {worst[1]['n_ground_truth']} ground-truth boxes this is most likely a\n"
                f"  data limit, not a tuning problem. More '{worst[0]}' data is the fix."
            )

    return {"mAP": overall["mAP"], "overall": overall, "per_class": per_class, "n_detections": n_dets}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--split", default="test", choices=["train", "valid", "test"])
    ap.add_argument("--conf", type=float, default=0.01,
                    help="Low by default: mAP needs the full precision/recall curve.")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--collapse-to", default=None, metavar="LABEL",
                    help="Score as a single-class detector under LABEL, collapsing "
                         "both predictions and ground truth. Use when a model "
                         "localises well but classifies badly -- it measures "
                         "whether the boxes are right, independently of the names.")
    ap.add_argument("--out", type=Path, default=None, help="Write metrics JSON here.")
    args = ap.parse_args()

    metrics = evaluate(args.model, args.root, args.split, args.conf, args.limit,
                       collapse_to=args.collapse_to)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
