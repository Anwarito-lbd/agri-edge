"""Convert keremberke/aerial-sheep-object-detection to a YOLO dataset.

WHY LIVESTOCK, AND WHY IT IS THE EASY WIN
-----------------------------------------
Every other use case in this project is capped by optics. Livestock is not:

    target            whole-frame ceiling   tiling needed at survey altitude?
    3 cm seedling            0.6 m           yes, and still capped at 3.9 m
    30 cm mature weed        6.1 m           yes
    120 cm sheep            24.6 m           no
    200 cm cow              41.0 m           no

A cow is detectable at 41 m AGL with plain whole-frame inference. That means
**livestock counting runs on a bare Raspberry Pi with no AI accelerator**, which
is true of nothing else here.

Sheep are used rather than cattle because that is what exists as a public aerial
dataset -- and being smaller, they are the conservative case. Anything that works
on sheep works on cattle with margin.

Licence: **Public Domain.** No attribution obligation, no copyleft. The cleanest
possible position for a commercial product.

LEAKAGE
-------
Roboflow produced "3 versions of each source image" by augmentation. If augmented
copies of one photo land on both sides of a split, every reported number is
inflated and the model looks far better than it is.

Roboflow filenames encode their source: `IMG_1234_jpg.rf.<hash>.jpg`. The part
before `.rf.` identifies the original photo, so overlap between splits is
directly checkable rather than assumed -- and this script checks it and fails
loudly if it finds any.

Run:  python training/prepare_aerial_sheep.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ID = "keremberke/aerial-sheep-object-detection"
DEFAULT_DEST = Path("data/aerial-sheep")
CLASS_NAMES = ["sheep"]
SPLITS = {"train": "train", "valid": "valid", "test": "test"}

ATTRIBUTION = """# Attribution

**Licence: Public Domain.** No attribution is legally required. Credited anyway,
because it costs nothing and the dataset is genuinely useful:

- Aerial Sheep Dataset, by Riis, via
  [Roboflow Universe](https://universe.roboflow.com/riis/aerial-sheep) (2022)
- Mirrored as `keremberke/aerial-sheep-object-detection` on Hugging Face

Public Domain means this imposes **no obligation on anything you ship** — unlike
the CC BY 4.0 weed datasets, whose attribution must survive into the product.
"""


def source_image_of(filename: str) -> str:
    """The original photo a Roboflow-augmented file came from.

    `IMG_1234_jpg.rf.deadbeef.jpg` -> `IMG_1234_jpg`. Used to detect augmented
    copies of one photo appearing in more than one split.
    """
    return filename.split(".rf.")[0]


def download_and_extract(dest: Path) -> Path:
    from huggingface_hub import hf_hub_download

    raw = dest / "_raw"
    raw.mkdir(parents=True, exist_ok=True)

    for split in SPLITS:
        marker = raw / split
        if marker.is_dir() and any(marker.iterdir()):
            print(f"  {split}: already extracted")
            continue
        print(f"  {split}: downloading...")
        zpath = hf_hub_download(
            repo_id=REPO_ID, repo_type="dataset", filename=f"data/{split}.zip"
        )
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(marker)
        print(f"  {split}: extracted")
    return raw


def find_coco_json(split_dir: Path) -> Path | None:
    candidates = list(split_dir.rglob("*.json"))
    for c in candidates:
        if "annotation" in c.name.lower() or c.name == "_annotations.coco.json":
            return c
    return candidates[0] if candidates else None


def convert(raw: Path, dest: Path) -> tuple[dict, dict]:
    """COCO -> YOLO txt, returning per-split counts and source-image sets."""
    counts: dict[str, dict] = {}
    sources: dict[str, set] = {}

    for split in SPLITS:
        split_dir = raw / split
        ann_path = find_coco_json(split_dir)
        if ann_path is None:
            raise FileNotFoundError(f"no COCO json found under {split_dir}")

        coco = json.loads(ann_path.read_text(encoding="utf-8"))
        images = {im["id"]: im for im in coco["images"]}
        by_image: dict[int, list] = {}
        for ann in coco.get("annotations", []):
            by_image.setdefault(ann["image_id"], []).append(ann)

        # Roboflow COCO exports often carry a dummy supercategory at id 0.
        cats = {c["id"]: c["name"] for c in coco.get("categories", [])}
        real_cat_ids = sorted(i for i, n in cats.items() if n.lower() not in ("sheep-detection",))
        cat_to_idx = {cid: 0 for cid in real_cat_ids}   # single class

        out_img = dest / split / "images"
        out_lbl = dest / split / "labels"
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)

        n_img = n_box = 0
        src: set[str] = set()

        for img_id, info in images.items():
            fname = info["file_name"]
            W, H = info["width"], info["height"]
            src_path = next(split_dir.rglob(fname), None)
            if src_path is None:
                continue

            lines = []
            for ann in by_image.get(img_id, []):
                x, y, w, h = ann["bbox"]          # COCO xywh, absolute
                if w <= 0 or h <= 0:
                    continue
                cx, cy = (x + w / 2) / W, (y + h / 2) / H
                nw, nh = w / W, h / H
                if not (0 < nw <= 1 and 0 < nh <= 1 and 0 <= cx <= 1 and 0 <= cy <= 1):
                    continue
                lines.append(f"{cat_to_idx.get(ann['category_id'], 0)} "
                             f"{cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
                n_box += 1

            shutil.copy2(src_path, out_img / fname)
            (out_lbl / f"{Path(fname).stem}.txt").write_text(
                "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
            )
            src.add(source_image_of(fname))
            n_img += 1

        counts[split] = {"images": n_img, "boxes": n_box, "sources": len(src)}
        sources[split] = src
        print(f"  {split:<6} {n_img:>5} images  {n_box:>6} boxes  "
              f"({len(src)} distinct source photos)")

    return counts, sources


def check_leakage(sources: dict[str, set]) -> list[str]:
    """Fail loudly if one source photo appears in more than one split."""
    problems = []
    pairs = [("train", "valid"), ("train", "test"), ("valid", "test")]
    for a, b in pairs:
        overlap = sources[a] & sources[b]
        if overlap:
            problems.append(
                f"{len(overlap)} source photo(s) appear in BOTH {a} and {b} "
                f"(e.g. {sorted(overlap)[0]}). Augmented copies of one image on "
                f"both sides of a split inflate every number you measure."
            )
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--keep-raw", action="store_true")
    args = ap.parse_args()

    print(f"Preparing {REPO_ID}")
    raw = download_and_extract(args.dest)
    print()
    counts, sources = convert(raw, args.dest)

    (args.dest / "data.yaml").write_text(
        "names:\n- sheep\nnc: 1\npath: .\n"
        "train: train/images\nval: valid/images\ntest: test/images\n",
        encoding="utf-8",
    )
    (args.dest / "ATTRIBUTION.md").write_text(ATTRIBUTION, encoding="utf-8")

    print()
    problems = check_leakage(sources)
    if problems:
        print("SPLIT LEAKAGE DETECTED:")
        for p in problems:
            print(f"  - {p}")
        print("\nRefusing to proceed. Re-split by source photo before training.")
        return 1

    total_img = sum(c["images"] for c in counts.values())
    total_box = sum(c["boxes"] for c in counts.values())
    aug = counts["train"]["images"] / max(counts["train"]["sources"], 1)
    print("No source photo appears in more than one split -- splits are clean.")
    print(f"  train augmentation factor: {aug:.1f}x "
          f"({counts['train']['sources']} photos -> {counts['train']['images']} images)")
    print()
    print(f"Total: {total_img} images, {total_box} boxes, 1 class (sheep)")
    print(f"Wrote {args.dest}  (Public Domain -- no attribution obligation)")

    if not args.keep_raw:
        shutil.rmtree(raw, ignore_errors=True)
        print("Removed extracted archives (--keep-raw to retain).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
