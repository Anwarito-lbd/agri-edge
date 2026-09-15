"""Measure real inference throughput, and translate it into flight parameters.

Runs the actual `OnnxEngine`/`HailoEngine` over real frames and reports the
latency breakdown. The headline number is not FPS for its own sake -- it is the
two operational limits it implies:

  * **capture interval** -- you cannot capture faster than you can process, or
    the spool grows without bound until the card fills.
  * **ground speed** -- at a given altitude and forward speed, consecutive frames
    must overlap enough to be useful. Too fast and you get gaps between frames.

Both are printed at the end.

Run on the laptop:
    python training/benchmark.py --model models/weed_crop_yolox_s.onnx

Run on the Pi (the number that actually matters):
    .venv/bin/python training/benchmark.py --model models/weed_crop_yolox_s.hef \\
        --backend hailo
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np

# Sony IMX708 (Camera Module 3): 7.4 x 5.5 mm sensor, 4.74 mm focal length.
# Used only to translate FPS into a ground-speed limit; override for other optics.
SENSOR_WIDTH_MM = 7.4
FOCAL_LENGTH_MM = 4.74


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--backend", choices=["onnx", "hailo"], default="onnx")
    ap.add_argument("--images", type=Path, default=Path("data/weed-crop-aerial/test/images"))
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--conf", type=float, default=0.30)
    ap.add_argument("--altitude", type=float, default=30.0, help="Metres AGL, for the speed limit.")
    ap.add_argument("--overlap", type=float, default=0.70, help="Required forward overlap, 0-1.")
    ap.add_argument("--tiled", action="store_true",
                    help="Benchmark the tiled path. Required at survey altitude -- "
                         "see training/gsd_calculator.py.")
    ap.add_argument("--tile-size", type=int, default=640)
    ap.add_argument("--tile-overlap", type=float, default=0.2)
    ap.add_argument("--capture-width", type=int, default=None,
                    help="Camera width to simulate tiling cost for, e.g. 4056. "
                         "Defaults to the benchmark images' own width.")
    args = ap.parse_args()

    from PIL import Image

    if args.backend == "hailo":
        from agri_edge.inference.engine import HailoEngine as Engine
    else:
        from agri_edge.inference.engine import OnnxEngine as Engine

    engine = Engine(args.model, confidence_threshold=args.conf)

    if args.tiled:
        from agri_edge.inference.tiling import TiledEngine, plan_tiles

        engine = TiledEngine(
            engine, tile_size=args.tile_size, overlap=args.tile_overlap, max_tiles=512
        )

    # Real frames, not noise: inference cost is roughly content-independent, but
    # NMS cost is not -- a frame with 300 candidate boxes costs more than an empty
    # one, and benchmarking on noise understates the worst case.
    if args.images.is_dir():
        paths = sorted(
            p for p in args.images.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )[: args.runs]
    else:
        paths = [args.images]
    if not paths:
        print(f"No images found in {args.images}", file=sys.stderr)
        return 1

    frames = [np.array(Image.open(p).convert("RGB")) for p in paths]
    h, w = frames[0].shape[:2]

    mode = f"{args.backend}, tiled {args.tile_size}px/{args.tile_overlap:.0%}" if args.tiled else args.backend
    print(f"model    : {engine.metadata.name} v{engine.metadata.version}  ({mode})")
    print(f"frames   : {w}x{h}   n={len(frames)}   warmup={args.warmup}")

    # Latency scales with tile count, and the benchmark images are usually much
    # smaller than the real camera frame. Extrapolate honestly rather than
    # quoting a number measured on the wrong resolution.
    scale_factor = 1.0
    if args.tiled:
        from agri_edge.inference.tiling import plan_tiles

        here = len(plan_tiles(w, h, args.tile_size, args.tile_overlap))
        print(f"tiles    : {here} on these {w}x{h} frames")
        if args.capture_width and args.capture_width != w:
            cw = args.capture_width
            ch = int(round(h * (cw / w)))
            there = len(plan_tiles(cw, ch, args.tile_size, args.tile_overlap))
            scale_factor = there / max(here, 1)
            print(f"           {there} on a real {cw}x{ch} camera frame "
                  f"-> {scale_factor:.1f}x this cost")
    print()

    for i in range(args.warmup):
        engine.infer(frames[i % len(frames)])

    times: list[float] = []
    n_dets = 0
    for i in range(args.runs):
        frame = frames[i % len(frames)]
        t0 = time.perf_counter()
        dets = engine.infer(frame)
        times.append((time.perf_counter() - t0) * 1000.0)
        n_dets += len(dets)

    mean = statistics.mean(times)
    print(f"{'latency mean':<18}{mean:>9.1f} ms")
    print(f"{'latency median':<18}{statistics.median(times):>9.1f} ms")
    print(f"{'latency p95':<18}{percentile(times, 0.95):>9.1f} ms")
    print(f"{'latency min/max':<18}{min(times):>9.1f} / {max(times):.1f} ms")
    print(f"{'throughput':<18}{1000.0 / mean:>9.2f} FPS")
    print(f"{'detections/frame':<18}{n_dets / args.runs:>9.1f}")

    if scale_factor != 1.0:
        print()
        print(f"Extrapolated to a {args.capture_width}px camera frame "
              f"({scale_factor:.1f}x the tiles measured above):")
        print(f"  {'latency':<18}{mean * scale_factor:>9.1f} ms")
        print(f"  {'throughput':<18}{1000.0 / (mean * scale_factor):>9.2f} FPS")
        mean = mean * scale_factor

    fps = 1000.0 / mean
    print()
    print("Operational limits implied by this number")
    print("-" * 52)

    # Capture must not outrun processing, or the spool grows without bound.
    safe_interval = 1.0 / fps * 1.25          # 25% headroom
    print(f"  min capture interval   {safe_interval:>8.2f} s   (capture.interval_s)")
    print("                                     25% headroom over mean latency")

    # Ground footprint from a pinhole model, then the speed that preserves overlap.
    gsd_width_m = (SENSOR_WIDTH_MM / FOCAL_LENGTH_MM) * args.altitude
    footprint_h = gsd_width_m * (h / w)
    advance = footprint_h * (1.0 - args.overlap)
    max_speed = advance / safe_interval

    print(f"  ground footprint       {gsd_width_m:>8.1f} x {footprint_h:.1f} m  at {args.altitude:.0f} m AGL")
    print(f"  max ground speed       {max_speed:>8.1f} m/s  ({max_speed * 3.6:.0f} km/h)")
    print(f"                                     to keep {args.overlap:.0%} forward overlap")

    # A typical agricultural multirotor surveys at 5-15 m/s. If the computed
    # limit is far above that, inference is not what constrains the mission and
    # quoting the number as a "max speed" would be misleading.
    TYPICAL_SURVEY_SPEED = 15.0
    if max_speed > TYPICAL_SURVEY_SPEED * 2:
        print()
        print(f"  Inference is NOT the binding constraint at {args.altitude:.0f} m AGL: the limit above")
        print(f"  is far beyond survey speeds (typically 5-15 m/s). Airframe endurance,")
        print(f"  battery and ground-sampling distance will decide the mission instead.")
        print(f"  At a realistic {TYPICAL_SURVEY_SPEED:.0f} m/s you could fly as low as "
              f"{TYPICAL_SURVEY_SPEED * safe_interval / (1 - args.overlap) * (w / h) / (SENSOR_WIDTH_MM / FOCAL_LENGTH_MM):.1f} m AGL")
        print(f"  and still hold {args.overlap:.0%} overlap.")
    elif max_speed < 3.0:
        print()
        print(f"  WARNING: {max_speed:.1f} m/s is slower than most survey flights. Inference")
        print(f"  is the bottleneck -- use the Hailo backend, raise the altitude, or")
        print(f"  accept less overlap before planning a mission around this.")

    if args.backend == "onnx":
        print()
        print("  This is CPU inference. The Hailo NPU is typically an order of")
        print("  magnitude faster -- re-run with --backend hailo on the Pi before")
        print("  setting flight parameters from these numbers.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
