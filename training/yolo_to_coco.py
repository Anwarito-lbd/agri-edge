"""Convert the YOLO-format dataset to COCO JSON, which is what YOLOX consumes.

The two formats disagree on almost everything about a box:

    YOLO   class_id  cx  cy  w  h        centre + size, normalised to [0, 1]
    COCO   [x_min, y_min, width, height]  top-left + size, absolute pixels

So the conversion is:

    abs_w = w * img_w          x_min = (cx - w/2) * img_w
    abs_h = h * img_h          y_min = (cy - h/2) * img_h

Getting this wrong is the single most expensive mistake available in this
pipeline, because it does not fail loudly. Boxes shifted by half their width
still produce a training run whose loss descends convincingly and whose final
model detects nothing. `tests/test_data_prep.py` pins the arithmetic against a
hand-computed box for exactly this reason.

Category ids are 1-indexed (COCO convention). YOLOX sorts `getCatIds()` and uses
the sorted position as the class index, so 1-indexed ids map back to the 0-indexed
YOLO class order correctly.

Run:  python training/yolo_to_coco.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_ROOT = Path("data/weed-crop-aerial")
FALLBACK_CLASS_NAMES = ["crop", "weed"]
SPLITS = ["train", "valid", "test"]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def load_class_names(root: Path) -> list[str]:
    """Read class names from the dataset's own `data.yaml`.

    Reading them rather than hardcoding means one converter serves every dataset,
    and -- more importantly -- the class *order* always matches the label files'
    integer ids. Hardcoding a list that has silently drifted from the data is how
    you end up training a model whose labels are permuted, which produces
    plausible-looking metrics and nonsense predictions.
    """
    data_yaml = root / "data.yaml"
    if not data_yaml.exists():
        print(f"  no data.yaml in {root}, assuming {FALLBACK_CLASS_NAMES}")
        return list(FALLBACK_CLASS_NAMES)

    names: list[str] = []
    in_names = False
    for line in data_yaml.read_text(encoding="utf-8").splitlines():
        if line.startswith("names:"):
            in_names = True
            continue
        if in_names:
            if line.startswith("- "):
                names.append(line[2:].strip())
            elif line.strip() and not line.startswith(" "):
                break
    if not names:
        print(f"  could not parse names from {data_yaml}, assuming {FALLBACK_CLASS_NAMES}")
        return list(FALLBACK_CLASS_NAMES)
    return names


def yolo_box_to_coco(
    cx: float, cy: float, w: float, h: float, img_w: int, img_h: int
) -> tuple[float, float, float, float]:
    """Normalised centre-form box -> absolute COCO `[x, y, width, height]`.

    Clamped to the image, because a few annotations in most real datasets run a
    pixel or two past the edge and pycocotools computes negative-area boxes from
    them without complaining.
    """
    abs_w = w * img_w
    abs_h = h * img_h
    x_min = (cx - w / 2.0) * img_w
    y_min = (cy - h / 2.0) * img_h

    x_min = max(0.0, min(x_min, img_w))
    y_min = max(0.0, min(y_min, img_h))
    abs_w = max(0.0, min(abs_w, img_w - x_min))
    abs_h = max(0.0, min(abs_h, img_h - y_min))

    return x_min, y_min, abs_w, abs_h


def image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as im:
        return im.width, im.height


def convert_split(root: Path, split: str, out_dir: Path,
                  class_names: list[str] | None = None) -> dict:
    class_names = class_names or load_class_names(root)
    img_dir = root / split / "images"
    lbl_dir = root / split / "labels"
    if not img_dir.is_dir():
        raise FileNotFoundError(f"missing {img_dir}")

    images, annotations = [], []
    ann_id = 1
    skipped_degenerate = 0

    paths = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    for img_id, img_path in enumerate(paths, start=1):
        w, h = image_size(img_path)
        images.append(
            {"id": img_id, "file_name": img_path.name, "width": w, "height": h}
        )

        lbl_path = lbl_dir / f"{img_path.stem}.txt"
        if not lbl_path.exists():
            continue

        for line in lbl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 5:
                raise ValueError(f"{lbl_path}: expected 5 fields, got {len(parts)}")

            cls = int(parts[0])
            cx, cy, bw, bh = (float(v) for v in parts[1:])
            x, y, aw, ah = yolo_box_to_coco(cx, cy, bw, bh, w, h)

            # A zero-area box makes pycocotools' AP computation misbehave rather
            # than error, so drop these and report the count.
            if aw <= 1e-6 or ah <= 1e-6:
                skipped_degenerate += 1
                continue

            annotations.append(
                {
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": cls + 1,   # COCO ids are 1-indexed
                    "bbox": [round(x, 2), round(y, 2), round(aw, 2), round(ah, 2)],
                    "area": round(aw * ah, 2),
                    "iscrowd": 0,
                    "segmentation": [],
                }
            )
            ann_id += 1

    # Provenance is derived from the dataset being converted, not hardcoded --
    # otherwise a second dataset silently inherits the first one's attribution,
    # which for CC BY content is a licensing error, not just untidy metadata.
    attribution = root / "ATTRIBUTION.md"
    coco = {
        "info": {
            "description": f"{root.name}, converted from YOLO format",
            "source": str(root),
            "licence": (
                f"see {attribution}" if attribution.exists()
                else "unknown -- check the dataset's own terms before redistributing"
            ),
        },
        "licenses": [{"id": 1, "name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}],
        "images": images,
        "annotations": annotations,
        "categories": [
            {"id": i + 1, "name": name, "supercategory": "plant"}
            for i, name in enumerate(class_names)
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"instances_{split}.json"
    out_path.write_text(json.dumps(coco), encoding="utf-8")

    note = f"  ({skipped_degenerate} degenerate boxes dropped)" if skipped_degenerate else ""
    print(f"  {split:<6} {len(images):>5} images  {len(annotations):>6} boxes  -> {out_path}{note}")
    return coco


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    ap.add_argument("--out", type=Path, default=None, help="Default: <root>/annotations")
    args = ap.parse_args()

    out_dir = args.out or (args.root / "annotations")
    class_names = load_class_names(args.root)
    print(f"Converting YOLO -> COCO from {args.root}")
    print(f"  classes: {class_names}")
    for split in SPLITS:
        try:
            convert_split(args.root, split, out_dir, class_names)
        except FileNotFoundError as exc:
            print(f"  skipping: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
