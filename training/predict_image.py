"""Run the real `OnnxEngine` over images and write annotated output.

Deliberately uses `agri_edge.inference.engine.OnnxEngine` -- the exact class the
Pi runs -- rather than a separate demo path. A visualiser that reimplements
decoding proves nothing about the code that will actually fly.

The boxes this draws must agree with `evaluate.py`'s numbers. If they disagree,
the bug is in the decode/letterbox path, not in the model.

Run:
    python training/predict_image.py --model models/weed_crop_yolox_s.onnx \
        --images data/weed-crop-aerial/test/images --limit 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

# Distinct hues per class. Not red/green: the imagery is vegetation, and a green
# box on a green canopy is invisible.
PALETTE = [
    (255, 196, 0),    # amber   -- class 0 (crop)
    (0, 176, 255),    # cyan    -- class 1 (weed)
    (255, 0, 212),
    (124, 255, 0),
    (255, 92, 92),
]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def draw_box(
    img: np.ndarray, x1: int, y1: int, x2: int, y2: int, colour: tuple[int, int, int], width: int = 2
) -> None:
    """Draw a rectangle outline in place, clipped to the image."""
    h, w = img.shape[:2]
    x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w - 1))
    y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h - 1))
    c = np.array(colour, dtype=np.uint8)
    for t in range(width):
        if y1 + t < h:
            img[y1 + t, x1:x2 + 1] = c
        if y2 - t >= 0:
            img[y2 - t, x1:x2 + 1] = c
        if x1 + t < w:
            img[y1:y2 + 1, x1 + t] = c
        if x2 - t >= 0:
            img[y1:y2 + 1, x2 - t] = c


def label_bar(img: np.ndarray, x: int, y: int, text: str, colour: tuple[int, int, int]) -> None:
    """Draw a filled bar with the label text above a box.

    Uses PIL for text so no OpenCV dependency is required.
    """
    from PIL import Image, ImageDraw

    pil = Image.fromarray(img)
    d = ImageDraw.Draw(pil)
    tw = int(6.5 * len(text)) + 8
    th = 14
    by = max(0, y - th)
    d.rectangle([x, by, min(x + tw, img.shape[1] - 1), by + th], fill=colour)
    d.text((x + 4, by + 2), text, fill=(0, 0, 0))
    img[:] = np.array(pil)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--images", type=Path, required=True, help="Image file or directory")
    ap.add_argument("--out", type=Path, default=Path("runs/predictions"))
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    from PIL import Image

    from agri_edge.inference.engine import OnnxEngine

    engine = OnnxEngine(args.model, confidence_threshold=args.conf)
    names = engine.class_names or ["class_0", "class_1"]

    print(f"model  : {engine.metadata.name} v{engine.metadata.version}")
    print(f"classes: {names}")
    print(f"input  : {engine.input_size}   conf>={args.conf}")
    if not engine.metadata.validated_locally:
        print("         model is NOT locally validated -- decision support only\n")

    if args.images.is_dir():
        paths = sorted(p for p in args.images.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    else:
        paths = [args.images]
    paths = paths[: args.limit]

    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    per_class: dict[str, int] = {}

    for path in paths:
        img = np.array(Image.open(path).convert("RGB"))
        dets = engine.infer(img)
        total += len(dets)

        h, w = img.shape[:2]
        annotated = img.copy()
        for d in sorted(dets, key=lambda d: -d.confidence):
            per_class[d.label] = per_class.get(d.label, 0) + 1
            idx = names.index(d.label) if d.label in names else 0
            colour = PALETTE[idx % len(PALETTE)]
            x1, y1, x2, y2 = (
                int(d.bbox[0] * w), int(d.bbox[1] * h),
                int(d.bbox[2] * w), int(d.bbox[3] * h),
            )
            draw_box(annotated, x1, y1, x2, y2, colour)
            label_bar(annotated, x1, y1, f"{d.label} {d.confidence:.2f}", colour)

        Image.fromarray(annotated).save(args.out / path.name)
        print(f"  {path.name:<48} {len(dets):>3} detections")

    print(f"\n{len(paths)} images, {total} detections -> {args.out}")
    if per_class:
        print("by class: " + "  ".join(f"{k}={v}" for k, v in sorted(per_class.items())))
    else:
        print(
            "No detections at all. Before blaming the model, check that --conf is not\n"
            "too high and that the class names match the checkpoint."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
