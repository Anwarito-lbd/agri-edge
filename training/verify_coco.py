"""Independently cross-check the COCO conversion against the original YOLO labels.

`tests/test_data_prep.py` verifies the arithmetic in isolation. This verifies the
actual converted files on disk, by reloading them through pycocotools (the same
library that will compute mAP) and recomputing every box from its YOLO source.

Run this after `yolo_to_coco.py`, before training. A conversion error caught here
costs a minute; caught after a training run it costs an afternoon.

Run:  python training/verify_coco.py
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

DEFAULT_ROOT = Path("data/weed-crop-aerial")
SPLITS = ["train", "valid", "test"]
TOL = 0.02  # bbox values are rounded to 2dp on write


def check_split(root: Path, split: str) -> list[str]:
    from PIL import Image
    from pycocotools.coco import COCO

    problems: list[str] = []
    ann_path = root / "annotations" / f"instances_{split}.json"
    if not ann_path.exists():
        return [f"{split}: missing {ann_path}"]

    with contextlib.redirect_stdout(io.StringIO()):
        coco = COCO(str(ann_path))

    img_ids = sorted(coco.getImgIds())
    n_boxes = 0
    sizes: set[tuple[int, int]] = set()

    for img_id in img_ids:
        info = coco.loadImgs(img_id)[0]
        W, H = info["width"], info["height"]
        sizes.add((W, H))

        img_file = root / split / "images" / info["file_name"]
        with Image.open(img_file) as im:
            if (im.width, im.height) != (W, H):
                problems.append(
                    f"{split}/{info['file_name']}: json says {W}x{H}, file is {im.width}x{im.height}"
                )

        lbl_file = root / split / "labels" / f"{Path(info['file_name']).stem}.txt"
        yolo_rows = []
        if lbl_file.exists():
            yolo_rows = [ln.split() for ln in lbl_file.read_text(encoding="utf-8").splitlines() if ln.strip()]

        anns = coco.loadAnns(coco.getAnnIds(imgIds=img_id))
        n_boxes += len(anns)

        # Recompute each COCO box from its YOLO source and compare.
        for ann, row in zip(anns, yolo_rows):
            cls = int(row[0])
            cx, cy, bw, bh = (float(v) for v in row[1:])
            expected = ((cx - bw / 2) * W, (cy - bh / 2) * H, bw * W, bh * H)
            got = tuple(ann["bbox"])

            if ann["category_id"] != cls + 1:
                problems.append(
                    f"{split}/{info['file_name']}: YOLO class {cls} -> category_id "
                    f"{ann['category_id']}, expected {cls + 1}"
                )
            if any(abs(e - g) > TOL for e, g in zip(expected, got)):
                problems.append(
                    f"{split}/{info['file_name']}: bbox mismatch\n"
                    f"      expected {[round(v, 2) for v in expected]}\n"
                    f"      got      {[round(v, 2) for v in got]}"
                )
            x, y, w, h = got
            if x < 0 or y < 0 or x + w > W + TOL or y + h > H + TOL:
                problems.append(f"{split}/{info['file_name']}: bbox {got} outside {W}x{H}")
            if w <= 0 or h <= 0:
                problems.append(f"{split}/{info['file_name']}: non-positive box {got}")

    cats = {c["id"]: c["name"] for c in coco.loadCats(coco.getCatIds())}
    size_note = f"{sizes.pop()}" if len(sizes) == 1 else f"{len(sizes)} distinct sizes"
    print(f"  {split:<6} {len(img_ids):>5} images  {n_boxes:>6} boxes  cats={cats}  size={size_note}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = ap.parse_args()

    print(f"Cross-checking COCO annotations in {args.root} against YOLO source labels")
    all_problems: list[str] = []
    for split in SPLITS:
        all_problems.extend(check_split(args.root, split))

    if all_problems:
        print(f"\n{len(all_problems)} PROBLEM(S):")
        for p in all_problems[:20]:
            print(f"  - {p}")
        if len(all_problems) > 20:
            print(f"  ... and {len(all_problems) - 20} more")
        return 1

    print("\nEvery box round-trips from its YOLO source. Conversion verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
