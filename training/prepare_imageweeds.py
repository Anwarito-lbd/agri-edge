"""Convert Project-AgML/ImageWeeds_aerial_weed_detection to a YOLO/COCO dataset.

WHY THIS DATASET
----------------
The first dataset (`LibreYOLO/weed-crop-aerial`) turned out not to be aerial at
all -- close-range ground shots plus indoor propagation trays. This one was
verified by looking at the imagery before any training: genuine **nadir aerial**
views of a real tilled field, crop rows and tractor tracks visible, with target
weeds transplanted into research plots.

The five classes are the herbicide-resistant weeds that actually matter on the
Canadian Prairies:

    ragweed, waterhemp, horseweed, redroot pigweed, kochia

Source: Rai et al., "Multi-format open-source weed image dataset for real-time
weed identification in precision agriculture", Data in Brief 51 (2023).
Licensed CC BY 4.0 -- attribution required, see the ATTRIBUTION.md this writes.

SIZING
------
Images are 5472x3648; boxes average ~350 px across, about 6.4% of frame width.
Letterboxed to a 640 network input that is ~41 px -- comfortably detectable, so
whole-frame training is right here and tiling is unnecessary. (Tiling exists for
*seedling*-scale targets, which are a different problem; see
`training/gsd_calculator.py`.)

Images are saved downscaled to 1280 wide: training happens at 640, and keeping
5472-px originals would cost ~4.5 GB for no benefit while leaving headroom to
retrain at higher resolution later.

SPLITTING
---------
Split by **source image**, never by box. With only 551 images, splitting
carelessly would put near-identical frames from the same plot on both sides and
inflate every number reported afterwards.

Run:  python training/prepare_imageweeds.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ID = "Project-AgML/ImageWeeds_aerial_weed_detection"
CLASS_NAMES = ["ragweed", "waterhemp", "horseweed", "redrootpigweed", "kochia"]
DEFAULT_DEST = Path("data/imageweeds")
SAVE_WIDTH = 1280

ATTRIBUTION = """# Attribution

Redistributed under **CC BY 4.0** -- commercial use is permitted **provided
attribution is given**. This credit must survive into anything shipped or
published that was trained on this data.

## Source

- Dataset: `Project-AgML/ImageWeeds_aerial_weed_detection` on Hugging Face
- Indexed by the [AgML](https://project-agml.github.io/) project
- Licence: CC BY 4.0

## Citation

```bibtex
@article{rai2023multi,
  title={Multi-format open-source weed image dataset for real-time weed
         identification in precision agriculture},
  author={Rai, Nitin and Mahecha, Maria Villamil and Christensen, Annika and
          Quanbeck, Jamison and Zhang, Yu and Howatt, Kirk and Ostlie, Michael
          and Sun, Xin},
  journal={Data in Brief}, volume={51}, pages={109691}, year={2023},
  publisher={Elsevier}
}
```

Rai, Nitin; Villamil Mahecha, Maria; Christensen, Annika; Quanbeck, Jamison;
Howatt, Kirk; Ostlie, Michael; Zhang, Yu; Sun, Xin (2023), "ImageWeeds",
Mendeley Data, V2, doi: 10.17632/8kjcztbjz2.2
"""


def split_for(index: int, key: str) -> str:
    """Deterministic train/valid/test assignment, stable across re-runs.

    Hash-based rather than random so that re-running the script cannot silently
    reshuffle which images are held out -- that would invalidate any previously
    reported number.
    """
    h = int(hashlib.sha256(f"{index}:{key}".encode()).hexdigest()[:8], 16) % 100
    if h < 70:
        return "train"
    if h < 85:
        return "valid"
    return "test"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--save-width", type=int, default=SAVE_WIDTH)
    ap.add_argument("--limit", type=int, default=None, help="Stop after N images (smoke test).")
    args = ap.parse_args()

    try:
        from datasets import load_dataset
    except ImportError:
        print("pip install datasets", file=sys.stderr)
        return 1
    from PIL import Image

    for split in ("train", "valid", "test"):
        (args.dest / split / "images").mkdir(parents=True, exist_ok=True)
        (args.dest / split / "labels").mkdir(parents=True, exist_ok=True)

    print(f"Streaming {REPO_ID} (about 4.5 GB, this takes a while)")
    ds = load_dataset(REPO_ID, split="train", streaming=True)

    per_split: Counter[str] = Counter()
    per_class: Counter[str] = Counter()
    split_class: dict[str, Counter] = {s: Counter() for s in ("train", "valid", "test")}
    dropped = 0
    n = 0

    for i, ex in enumerate(ds):
        if args.limit and i >= args.limit:
            break

        img = ex["image"]
        W, H = img.size
        boxes = ex["objects"]["bbox"]
        cats = ex["objects"]["categories"]

        scale = args.save_width / W
        new_w, new_h = args.save_width, int(round(H * scale))
        small = img.convert("RGB").resize((new_w, new_h), Image.LANCZOS)

        stem = f"iw_{i:05d}"
        split = split_for(i, stem)

        lines = []
        for (x, y, w, h), c in zip(boxes, cats):
            # Source is absolute COCO xywh; YOLO wants normalised centre-form.
            cx = (x + w / 2.0) / W
            cy = (y + h / 2.0) / H
            nw, nh = w / W, h / H
            if not (0 < nw <= 1 and 0 < nh <= 1 and 0 <= cx <= 1 and 0 <= cy <= 1):
                dropped += 1
                continue
            lines.append(f"{int(c)} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
            name = CLASS_NAMES[int(c)]
            per_class[name] += 1
            split_class[split][name] += 1

        small.save(args.dest / split / "images" / f"{stem}.jpg", quality=90)
        (args.dest / split / "labels" / f"{stem}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        per_split[split] += 1
        n += 1
        if n % 25 == 0:
            print(f"  {n} images...", end="\r")

    # data.yaml, matching the layout the YOLOX exp expects.
    (args.dest / "data.yaml").write_text(
        "names:\n" + "".join(f"- {c}\n" for c in CLASS_NAMES)
        + f"nc: {len(CLASS_NAMES)}\npath: .\n"
        "train: train/images\nval: valid/images\ntest: test/images\n",
        encoding="utf-8",
    )
    (args.dest / "ATTRIBUTION.md").write_text(ATTRIBUTION, encoding="utf-8")

    print(f"  {n} images processed{' ' * 20}")
    print()
    print(f"{'split':<8}{'images':>8}   class balance")
    print("-" * 76)
    for s in ("train", "valid", "test"):
        bal = "  ".join(f"{c}={split_class[s][c]}" for c in CLASS_NAMES)
        print(f"{s:<8}{per_split[s]:>8}   {bal}")
    print("-" * 76)
    total = sum(per_class.values())
    print(f"{'total':<8}{n:>8}   {total} boxes")
    print()
    for c in CLASS_NAMES:
        share = per_class[c] / total if total else 0
        print(f"  {c:<16}{per_class[c]:>6}  {share:>6.1%}")
    if dropped:
        print(f"\n  {dropped} malformed box(es) dropped")

    print(f"\nWrote {args.dest}  (+ ATTRIBUTION.md -- CC BY 4.0, keep it)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
