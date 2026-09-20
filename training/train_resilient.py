"""Run a YOLOX training job, resuming automatically after transient GPU faults.

WHY THIS EXISTS
---------------
The species model died at epoch 80 of 150, four hours in, with:

    RuntimeError: cuDNN error: CUDNN_STATUS_EXECUTION_FAILED_CUDART

Not a code bug. This machine's GPU is power-capped and oscillates between
217 MHz and 3090 MHz (see `docs/BUILD_NOTES.md`), and VRAM sits at 7.1 of
8.1 GB. Long runs on an unstable, nearly-full GPU fail occasionally. Losing four
hours of training to a fault that a retry would have survived is avoidable.

YOLOX checkpoints every epoch and `--resume` restores model, optimizer and epoch
from `latest_ckpt.pth`, so a restart costs at most one epoch.

WHAT IT DOES NOT DO
-------------------
It does not retry *deterministic* failures. A config error, a missing dataset or
a shape mismatch fails identically every time, and retrying it just burns hours
and hides the real error. Only faults matching `TRANSIENT_PATTERNS` are retried;
anything else stops immediately and prints the log tail.

It also does not mistake YOLOX's exit message for success. YOLOX prints
"Training of experiment is done" from a `finally` block, so it appears **even
when training crashed** -- which is exactly how the crash above was first
misread as a completed run. Success here means the process exited 0 **and** the
log shows the final epoch.

Run:
    python training/train_resilient.py --exp imageweeds_yolox_s
    python training/train_resilient.py --exp aerial_sheep_yolox_s --batch 8
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

# Faults worth retrying: transient GPU/driver/memory conditions that a fresh
# process has a real chance of surviving.
TRANSIENT_PATTERNS = [
    r"CUDNN_STATUS_EXECUTION_FAILED",
    r"CUDNN_STATUS_INTERNAL_ERROR",
    r"CUDNN_STATUS_NOT_INITIALIZED",
    r"CUDA error: unspecified launch failure",
    r"CUDA error: an illegal memory access",
    r"CUDA out of memory",
    r"cuDNN error",
    r"NCCL error",
    r"device-side assert triggered",
    r"unable to find an engine to execute",
]


def log_path(exp: str) -> Path:
    return Path("YOLOX_outputs") / exp / "train_log.txt"


def last_epoch(exp: str) -> tuple[int, int] | None:
    """(current, total) from the log, or None if it has not started."""
    p = log_path(exp)
    if not p.exists():
        return None
    matches = re.findall(r"epoch: (\d+)/(\d+)", p.read_text(encoding="utf-8", errors="replace"))
    if not matches:
        return None
    cur, total = matches[-1]
    return int(cur), int(total)


def safe_print(text: str) -> None:
    """Print text that may contain characters the console cannot encode.

    YOLOX logs through loguru, whose tracebacks are drawn with box characters
    (U+2502 and friends). The Windows console is cp1252, so printing them raises
    UnicodeEncodeError -- which is exactly how this wrapper crashed while trying
    to *report* a failure, hiding the real error underneath its own.
    """
    enc = (sys.stdout.encoding or "utf-8")
    sys.stdout.write(text.encode(enc, errors="replace").decode(enc, errors="replace"))
    sys.stdout.write("\n")
    sys.stdout.flush()


def tail(exp: str, n: int = 40) -> str:
    p = log_path(exp)
    if not p.exists():
        return "(no log)"
    return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])


def is_transient(text: str) -> str | None:
    for pat in TRANSIENT_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return pat
    return None


def finished(exp: str) -> bool:
    """True only if the log reached its final epoch.

    Deliberately NOT keyed on YOLOX's "Training of experiment is done" message,
    which it prints from a `finally` block on crash as well as on success.
    """
    ep = last_epoch(exp)
    return ep is not None and ep[0] >= ep[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exp", required=True)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--ckpt", default="weights/yolox_s.pth",
                    help="Initial weights. Ignored once a run exists to resume.")
    ap.add_argument("--max-retries", type=int, default=6)
    ap.add_argument("--cooldown-s", type=float, default=60.0,
                    help="Pause before resuming -- lets a hot or unstable GPU settle.")
    args = ap.parse_args()

    exp_file = Path("training/exps") / f"{args.exp}.py"
    if not exp_file.exists():
        print(f"No exp file at {exp_file}", file=sys.stderr)
        return 1

    if finished(args.exp):
        ep = last_epoch(args.exp)
        print(f"{args.exp} already finished ({ep[0]}/{ep[1]}). Nothing to do.")
        return 0

    for attempt in range(1, args.max_retries + 2):
        resuming = (Path("YOLOX_outputs") / args.exp / "latest_ckpt.pth").exists()
        ep = last_epoch(args.exp)
        where = f" from epoch {ep[0]}/{ep[1]}" if (resuming and ep) else ""

        print(f"\n{'=' * 70}")
        print(f"attempt {attempt}  |  {'RESUMING' + where if resuming else 'STARTING FRESH'}")
        print(f"{'=' * 70}", flush=True)

        cmd = [
            sys.executable, "vendor/YOLOX/tools/train.py",
            "-f", str(exp_file), "-d", "1", "-b", str(args.batch), "--fp16", "-o",
        ]
        cmd += ["--resume"] if resuming else ["-c", args.ckpt]

        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        proc_out = (result.stdout or "") + (result.stderr or "")
        combined = proc_out + "\n" + tail(args.exp, 60)

        if result.returncode == 0 and finished(args.exp):
            ep = last_epoch(args.exp)
            print(f"\nTraining complete: {ep[0]}/{ep[1]} epochs.")
            return 0

        pattern = is_transient(combined)
        if pattern is None:
            print(f"\nFAILED with a non-transient error (exit {result.returncode}).")
            ep = last_epoch(args.exp)
            print(f"Progress: {ep[0]}/{ep[1]} epochs." if ep else "No epoch logged.")
            print("\n--- subprocess output (last 40 lines) ---")
            safe_print("\n".join(proc_out.splitlines()[-40:]) or "(none captured)")
            print("\n--- training log tail ---")
            safe_print(tail(args.exp, 25))
            return 1

        if attempt > args.max_retries:
            print(f"\nGave up after {args.max_retries} retries. Last fault: {pattern}")
            return 1

        ep = last_epoch(args.exp)
        progress = f"{ep[0]}/{ep[1]}" if ep else "unknown"
        print(f"\nTransient GPU fault ({pattern}) at epoch {progress}.")
        print("Checkpointed each epoch, so at most one epoch is lost.")
        print(f"Cooling down {args.cooldown_s:.0f}s, then resuming...", flush=True)
        time.sleep(args.cooldown_s)

    return 1


if __name__ == "__main__":
    sys.exit(main())
