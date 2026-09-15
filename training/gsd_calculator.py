"""Can the camera physically resolve a weed at a given altitude?

This exists because of a finding that invalidates the obvious plan: detecting
weed *seedlings* from normal survey altitude is not a model problem, it is an
optics problem. At 30 m AGL a 3 cm seedling is a couple of pixels wide before the
detector even sees it — and the detector downscales further.

Two numbers matter and they are different:

  **native GSD**    — centimetres per pixel on the sensor.
  **effective GSD** — centimetres per pixel *as the model sees it*, after the
                      frame is letterboxed down to the network input (640x640).
                      Downscaling a 4056-wide frame to 640 throws away 6.3x of
                      linear resolution. This is the number that decides
                      detectability, and it is the one people forget.

Tiling fixes the gap: instead of downscaling the whole frame, cut it into
640x640 tiles at native resolution and run the detector on each. Costs N
inferences per frame, buys back the full 6.3x.

Run:
    python training/gsd_calculator.py --target-size 3 --min-pixels 20
"""

from __future__ import annotations

import argparse
import sys

# Sony IMX708, Raspberry Pi Camera Module 3.
CAMERAS = {
    "imx708": {"name": "Pi Camera Module 3 (IMX708)", "sensor_w_mm": 7.4, "focal_mm": 4.74,
               "width_px": 4056, "height_px": 3040},
    "imx477": {"name": "Pi HQ Camera (IMX477) + 6mm lens", "sensor_w_mm": 6.287, "focal_mm": 6.0,
               "width_px": 4056, "height_px": 3040},
    "imx296": {"name": "Pi Global Shutter (IMX296) + 6mm lens", "sensor_w_mm": 6.3, "focal_mm": 6.0,
               "width_px": 1456, "height_px": 1088},
    "m3m": {"name": "DJI Mavic 3M multispectral band", "sensor_w_mm": 6.4, "focal_mm": 4.34,
            "width_px": 2592, "height_px": 1944},
}


def native_gsd_cm(cam: dict, altitude_m: float) -> float:
    """Centimetres per pixel on the sensor at a given altitude (pinhole model)."""
    ground_width_m = (cam["sensor_w_mm"] / cam["focal_mm"]) * altitude_m
    return (ground_width_m * 100.0) / cam["width_px"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--camera", choices=sorted(CAMERAS), default="imx708")
    ap.add_argument("--target-size", type=float, default=3.0,
                    help="Size of the thing to detect, in cm. Weed seedling ~2-5 cm.")
    ap.add_argument("--min-pixels", type=float, default=20.0,
                    help="Pixels across the target needed for reliable detection. "
                         "~20 px is a reasonable floor for a small object.")
    ap.add_argument("--model-input", type=int, default=640)
    args = ap.parse_args()

    cam = CAMERAS[args.camera]
    downscale = cam["width_px"] / args.model_input

    print(f"camera        : {cam['name']}")
    print(f"resolution    : {cam['width_px']}x{cam['height_px']}")
    print(f"model input   : {args.model_input}x{args.model_input}  "
          f"(downscale {downscale:.1f}x when the whole frame is letterboxed)")
    print(f"target        : {args.target_size:.0f} cm object, need >= {args.min_pixels:.0f} px across")
    print()
    print(f"{'alt (m)':>8}{'native GSD':>13}{'px whole-frame':>16}{'px tiled':>10}   verdict")
    print("-" * 72)

    for alt in [1, 2, 3, 5, 10, 15, 20, 30, 50, 80, 120]:
        native = native_gsd_cm(cam, alt)
        effective = native * downscale
        px_whole = args.target_size / effective
        px_tiled = args.target_size / native

        if px_whole >= args.min_pixels:
            verdict = "OK whole-frame"
        elif px_tiled >= args.min_pixels:
            verdict = "TILING REQUIRED"
        else:
            verdict = "not resolvable"

        print(f"{alt:>8}{native:>11.3f} cm{px_whole:>14.1f}{px_tiled:>10.1f}   {verdict}")

    # Solve for the altitude where each mode stops working.
    max_alt_whole = (
        args.target_size / args.min_pixels / downscale
        * cam["width_px"] / ((cam["sensor_w_mm"] / cam["focal_mm"]) * 100.0)
    )
    max_alt_tiled = max_alt_whole * downscale

    print()
    print("Ceilings for this target size")
    print("-" * 72)
    print(f"  whole-frame inference   up to {max_alt_whole:>6.1f} m AGL")
    print(f"  tiled inference         up to {max_alt_tiled:>6.1f} m AGL  "
          f"({downscale:.1f}x higher, at {downscale ** 2:.0f}x the inference cost)")
    print()
    print("  Above the tiled ceiling the object is not in the image in any useful")
    print("  sense. No model recovers it: you need a longer lens, a higher-resolution")
    print("  sensor, or a lower flight.")
    print()
    print("  Note these are optics ceilings, not recommendations. Motion blur,")
    print("  focus and lighting all degrade real detection well before the limit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
