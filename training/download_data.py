"""Fetch the weed/crop aerial dataset from Hugging Face and verify it.

Dataset: LibreYOLO/weed-crop-aerial (CC BY 4.0)
  823 train / 235 valid / 118 test aerial images, YOLO format, classes [crop, weed].
  Mirrored from the Roboflow 100 benchmark.

Two things this script does beyond downloading:

1. **Verifies the tree matches what we expect.** A silently-changed upstream
   dataset that trains to a plausible loss and detects nothing is far more
   expensive to debug than a loud failure here.

2. **Reports class balance before training, not after.** With two classes on
   aerial imagery, "crop" typically outnumbers "weed" heavily. Knowing the ratio
   up front turns a confusing mAP into an expected one.

Run:  python training/download_data.py
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO_ID = "LibreYOLO/weed-crop-aerial"
DEFAULT_DEST = Path("data/weed-crop-aerial")

# From the dataset card. Treated as an assertion, not a hint.
EXPECTED_COUNTS = {"train": 823, "valid": 235, "test": 118}
EXPECTED_CLASSES = ["crop", "weed"]

ATTRIBUTION = """# Attribution

This dataset is redistributed under **CC BY 4.0**, which permits commercial use
**provided attribution is given**. For a commercial product this is a licence
obligation, not a courtesy: the credit below must survive into anything shipped
or published that was trained on this data.

## Source

- Dataset: `LibreYOLO/weed-crop-aerial` on Hugging Face
- Original: [Roboflow Universe -- weed-crop-aerial](https://universe.roboflow.com/roboflow-100/weed-crop-aerial)
- Benchmark: [Roboflow 100](https://www.rf100.org/)
- Licence: CC BY 4.0

## Citation

```bibtex
@misc{rf100_2022,
    Author = {Floriana Ciaglia and Francesco Saverio Zuppichini and Paul Guerrie
              and Mark McQuade and Jacob Solawetz},
    Title = {Roboflow 100: A Rich, Multi-Domain Object Detection Benchmark},
    Year = {2022},
    Eprint = {arXiv:2211.13523},
}
```
"""


def parse_label_file(path: Path) -> list[tuple[int, float, float, float, float]]:
    """Read one YOLO label file: `class_id cx cy w h`, all normalised to [0, 1]."""
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"{path}:{line_no}: expected 5 fields, got {len(parts)}")
        cls, cx, cy, w, h = parts
        rows.append((int(cls), float(cx), float(cy), float(w), float(h)))
    return rows


def verify(dest: Path) -> int:
    """Check the tree, count boxes per class, and report. Returns an exit code."""
    problems: list[str] = []

    data_yaml = dest / "data.yaml"
    if not data_yaml.exists():
        problems.append(f"missing {data_yaml}")
    else:
        text = data_yaml.read_text(encoding="utf-8")
        for name in EXPECTED_CLASSES:
            if name not in text:
                problems.append(f"data.yaml does not mention class '{name}'")

    print(f"\n{'split':<8}{'images':>9}{'labels':>9}{'boxes':>9}   class balance")
    print("-" * 72)

    grand_total: Counter[int] = Counter()

    for split, expected in EXPECTED_COUNTS.items():
        img_dir = dest / split / "images"
        lbl_dir = dest / split / "labels"

        if not img_dir.is_dir():
            problems.append(f"missing directory {img_dir}")
            continue

        images = [p for p in img_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
        labels = sorted(lbl_dir.glob("*.txt")) if lbl_dir.is_dir() else []

        if len(images) != expected:
            problems.append(
                f"{split}: expected {expected} images, found {len(images)} "
                "-- upstream dataset may have changed"
            )

        # Every image needs a label file. A missing one is silently treated as
        # "no objects here" by most training loops, which quietly teaches the
        # model that real weeds are background.
        image_stems = {p.stem for p in images}
        label_stems = {p.stem for p in labels}
        orphan_images = image_stems - label_stems
        if orphan_images:
            problems.append(
                f"{split}: {len(orphan_images)} image(s) have no label file "
                f"(e.g. {sorted(orphan_images)[0]}) -- these train as pure background"
            )

        counts: Counter[int] = Counter()
        for lbl in labels:
            try:
                for cls, cx, cy, w, h in parse_label_file(lbl):
                    counts[cls] += 1
                    if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0):
                        problems.append(f"{lbl}: centre out of [0,1] -- labels may not be normalised")
                    if w <= 0 or h <= 0:
                        problems.append(f"{lbl}: non-positive box size")
            except ValueError as exc:
                problems.append(str(exc))

        grand_total.update(counts)
        total = sum(counts.values())
        balance = "  ".join(
            f"{EXPECTED_CLASSES[c] if c < len(EXPECTED_CLASSES) else c}={counts.get(c, 0)}"
            f" ({counts.get(c, 0) / total:.0%})" if total else ""
            for c in sorted(set(list(counts) + list(range(len(EXPECTED_CLASSES)))))
        )
        print(f"{split:<8}{len(images):>9}{len(labels):>9}{total:>9}   {balance}")

    total = sum(grand_total.values())
    print("-" * 72)
    if total:
        ratio = {EXPECTED_CLASSES[c]: grand_total.get(c, 0) / total for c in range(len(EXPECTED_CLASSES))}
        print(f"overall {total:>26} boxes   " + "  ".join(f"{k}={v:.0%}" for k, v in ratio.items()))
        minority = min(ratio, key=ratio.get)
        majority = max(ratio, key=ratio.get)
        if ratio[minority] < 0.25:
            n_minority = grand_total.get(EXPECTED_CLASSES.index(minority), 0)
            print(
                f"\n  NOTE: '{minority}' is only {ratio[minority]:.0%} of all boxes ({n_minority} total).\n"
                f"  Consequences to plan around:\n"
                f"    - A degenerate model that labels everything '{majority}' already scores\n"
                f"      ~{ratio[majority]:.0%} on anything prevalence-weighted. Aggregate mAP will\n"
                f"      flatter it. Judge per-class AP, and expect '{minority}' AP to lag badly.\n"
                f"    - With so few '{minority}' examples, that class may be effectively\n"
                f"      untrainable from this dataset alone. That is a dataset limit, not a\n"
                f"      training bug -- do not burn days tuning against it.\n"
                f"    - If the product only needs '{majority}' detection, this is acceptable.\n"
                f"      If it needs both, plan to source more '{minority}' data."
            )

    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("\nDataset verified.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--verify-only", action="store_true", help="Skip download, just check what's on disk.")
    args = ap.parse_args()

    if not args.verify_only:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("huggingface_hub is required:  pip install huggingface_hub", file=sys.stderr)
            return 1

        print(f"Downloading {REPO_ID} -> {args.dest}")
        snapshot_download(
            repo_id=REPO_ID,
            repo_type="dataset",
            local_dir=str(args.dest),
        )

        args.dest.mkdir(parents=True, exist_ok=True)
        (args.dest / "ATTRIBUTION.md").write_text(ATTRIBUTION, encoding="utf-8")
        print(f"Wrote {args.dest / 'ATTRIBUTION.md'} -- keep this with anything you ship.")

    return verify(args.dest)


if __name__ == "__main__":
    sys.exit(main())
