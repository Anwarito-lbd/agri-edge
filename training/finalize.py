"""Turn a finished training run into a shippable model, in one step.

Export -> evaluate on the held-out test split -> annotated example predictions
-> benchmark -> fill in the model card's results table.

Safe to run against a partially-trained run: it uses `best_ckpt.pth` when the
evaluator has produced one and falls back to `latest_ckpt.pth` otherwise, and it
says which it used. If training is still going, the numbers are a snapshot, not
a final result -- the output labels them as such.

Run:
    python training/finalize.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_EXP = "weed_crop_yolox_s"


def run(cmd: list[str], label: str) -> bool:
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    result = subprocess.run([sys.executable, *cmd])
    if result.returncode != 0:
        print(f"  FAILED: {label}", file=sys.stderr)
        return False
    return True


def pick_checkpoint(run_dir: Path) -> tuple[Path | None, str]:
    best = run_dir / "best_ckpt.pth"
    latest = run_dir / "latest_ckpt.pth"
    if best.exists():
        return best, "best_ckpt.pth (highest validation AP)"
    if latest.exists():
        return latest, "latest_ckpt.pth -- no best_ckpt yet, so this is a SNAPSHOT of an unfinished run"
    return None, "none found"


def update_card(card: Path, metrics: dict, checkpoint_note: str) -> None:
    """Replace the placeholder results table in the model card."""
    if not card.exists():
        return

    per_class = metrics.get("per_class", {})
    if not per_class:
        return

    rows = []
    total_gt = 0
    for name, m in per_class.items():
        ap = "n/a" if m["AP"] != m["AP"] else f"{m['AP']:.4f}"       # NaN check
        ap50 = "n/a" if m["AP50"] != m["AP50"] else f"{m['AP50']:.4f}"
        rows.append(f"| {name} | {ap} | {ap50} | {m['n_ground_truth']} |")
        total_gt += m["n_ground_truth"]

    overall = metrics.get("overall", {})
    rows.append(
        f"| **overall** | **{overall.get('mAP', 0):.4f}** | "
        f"**{overall.get('mAP50', 0):.4f}** | {total_gt} |"
    )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    table = "\n".join(
        [
            f"*Measured {stamp} on the held-out **test** split, via `training/evaluate.py`,",
            f"running inference through the deployed `OnnxEngine`.*",
            f"",
            f"*Checkpoint: {checkpoint_note}*",
            "",
            "| Class | AP@.50:.95 | AP@.50 | GT boxes |",
            "|---|---:|---:|---:|",
            *rows,
        ]
    )

    text = card.read_text(encoding="utf-8")
    marker = "## Results\n"
    if marker not in text:
        return
    head, _, tail = text.partition(marker)

    # Keep everything after the placeholder table (the latency paragraph).
    remainder = tail
    if "Inference latency:" in tail:
        remainder = "\n" + tail[tail.index("Inference latency:"):]
    else:
        remainder = "\n"

    card.write_text(head + marker + "\n" + table + "\n" + remainder, encoding="utf-8")
    print(f"\nUpdated {card} with measured results.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exp", default=DEFAULT_EXP,
                    help="Experiment name; run dir, model path and card are derived from it.")
    ap.add_argument("--data-root", type=Path, default=None,
                    help="Dataset root. Default: inferred from the exp file.")
    ap.add_argument("--classes", default=None, help="Comma-separated class names.")
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--model", type=Path, default=None)
    ap.add_argument("--card", type=Path, default=None)
    ap.add_argument("--conf", type=float, default=0.30, help="For the annotated examples.")
    ap.add_argument("--skip-benchmark", action="store_true")
    args = ap.parse_args()

    exp_file = Path("training/exps") / f"{args.exp}.py"
    if not exp_file.exists():
        print(f"No exp file at {exp_file}", file=sys.stderr)
        return 1

    args.run_dir = args.run_dir or Path("YOLOX_outputs") / args.exp
    args.model = args.model or Path("models") / f"{args.exp}.onnx"
    args.card = args.card or Path("models") / f"{args.exp}_CARD.md"

    # Read data_dir and class names out of the exp/data.yaml rather than making
    # the caller repeat them -- a mismatch here silently mislabels every result.
    exp_text = exp_file.read_text(encoding="utf-8")
    if args.data_root is None:
        for line in exp_text.splitlines():
            if "self.data_dir" in line and "=" in line:
                args.data_root = Path(line.split("=", 1)[1].strip().strip('"\''))
                break
    if args.classes is None and args.data_root:
        sys.path.insert(0, "training")
        from yolo_to_coco import load_class_names

        args.classes = ",".join(load_class_names(args.data_root))

    print(f"exp      : {args.exp}")
    print(f"data     : {args.data_root}")
    print(f"classes  : {args.classes}")

    ckpt, note = pick_checkpoint(args.run_dir)
    if ckpt is None:
        print(f"No checkpoint in {args.run_dir}. Has training run?", file=sys.stderr)
        return 1

    print(f"Checkpoint: {ckpt}")
    print(f"            {note}")
    if "SNAPSHOT" in note:
        print("\n  Training has not produced a best_ckpt yet. Numbers below are a\n"
              "  snapshot of an unfinished run, not a final result.")

    if not run(
        ["training/export_onnx.py", "--exp", str(exp_file),
         "--ckpt", str(ckpt), "--output", str(args.model), "--class-names", args.classes],
        "1/4  Export to ONNX",
    ):
        return 1

    metrics_path = Path("runs") / f"metrics_{args.exp}.json"
    if not run(
        ["training/evaluate.py", "--model", str(args.model), "--root", str(args.data_root),
         "--split", "test", "--conf", "0.01", "--out", str(metrics_path)],
        "2/4  Evaluate on the held-out test split (per class)",
    ):
        return 1

    run(
        ["training/predict_image.py", "--model", str(args.model),
         "--images", str(args.data_root / "test" / "images"),
         "--out", f"runs/predictions_{args.exp}", "--conf", str(args.conf), "--limit", "24"],
        "3/4  Annotated example predictions",
    )

    if not args.skip_benchmark:
        run(
            ["training/benchmark.py", "--model", str(args.model), "--runs", "30",
             "--images", str(args.data_root / "test" / "images")],
            "4/4  Inference benchmark",
        )

    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        update_card(args.card, metrics, note)

    print(f"\n{'=' * 70}")
    print("Done. Review in this order:")
    print(f"  1. runs/predictions_{args.exp}/ -- look at the boxes. mAP hides what eyes catch.")
    print(f"  2. {args.card} -- per-class AP, not the aggregate.")
    print(f"  3. {metrics_path} -- full numbers.")
    print()
    print("  validated_locally stays FALSE until the model is checked against")
    print("  imagery from the fields you actually intend to fly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
