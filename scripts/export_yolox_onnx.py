#!/usr/bin/env python3
"""YOLOX -> ONNX export entrypoint (wrapper + documented commands).

Status: IMPLEMENTED (wrapper) · real export requires YOLOX + torch (BENCH).
Canonical implementation: ``training/export_onnx.py``.

Hard constraints (must match Hailo + host decode path):
  * decode_in_inference = False  (host decode in agri_edge.inference.yolox)
  * opset 11, fixed 640x640 batch 1, no NMS in graph
  * writes ``<model>.onnx.meta.json`` with validated_locally=false

Usage::

    python scripts/export_yolox_onnx.py --dry-run

    python training/export_onnx.py \\
        --exp training/exps/weed_crop_yolox_s.py \\
        --ckpt YOLOX_outputs/weed_crop_yolox_s/best_ckpt.pth \\
        --output models/weed_crop_yolox_s.onnx

Then HEF (x86_64 / WSL2 only — NOT HARDWARE-validated)::

    bash scripts/hailo_compile.sh --arch hailo8l
    pwsh scripts/hailo_compile.ps1 -Arch hailo8l -DryRun
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REAL = REPO / "training" / "export_onnx.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Delegate to training/export_onnx.py or print documented commands."
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands only")
    parser.add_argument(
        "--exp",
        default="training/exps/weed_crop_yolox_s.py",
        help="YOLOX exp module path",
    )
    parser.add_argument(
        "--ckpt",
        default="YOLOX_outputs/weed_crop_yolox_s/best_ckpt.pth",
        help="Trained checkpoint",
    )
    parser.add_argument(
        "--output",
        default="models/weed_crop_yolox_s.onnx",
        help="ONNX output path",
    )
    args, rest = parser.parse_known_args(argv)

    cmd = [
        sys.executable,
        str(REAL),
        "--exp",
        args.exp,
        "--ckpt",
        args.ckpt,
        "--output",
        args.output,
        *rest,
    ]
    print("Agri-Edge YOLOX->ONNX export")
    print("  status: IMPLEMENTED wrapper; real export needs torch+YOLOX (BENCH)")
    print("  canonical: training/export_onnx.py")
    print("  command:", " ".join(cmd))
    if args.dry_run:
        return 0
    if not REAL.is_file():
        print(f"ERROR: missing {REAL}", file=sys.stderr)
        return 2
    try:
        return subprocess.call(cmd, cwd=str(REPO))
    except OSError as exc:
        print(f"Export failed (deps?): {exc}", file=sys.stderr)
        print("Install torch + vendor/YOLOX, then re-run.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

