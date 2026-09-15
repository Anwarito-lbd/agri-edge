"""How fast can the aircraft fly before the image stops being usable?

`gsd_calculator.py` answers "can the camera *resolve* the target at altitude h".
This answers the other half, which is a **mechanical and flight-planning**
question rather than a model one:

  1. **Motion blur** - the aircraft moves while the shutter is open, smearing the
     target across pixels. Budget: keep the smear under ~1 pixel.
  2. **Rolling-shutter skew** - the Pi Camera Module 3 (IMX708) exposes the frame
     one row at a time. During the readout the aircraft keeps moving, so the
     bottom of the frame is taken from a different position than the top. The
     frame is not a rectangle on the ground; it is a parallelogram.

WHY THIS BITES HARDER THAN PEOPLE EXPECT
----------------------------------------
Everything in this project uses **tiled inference at native resolution** (see
docs/BUILD_NOTES.md). Whole-frame inference letterboxes 4056 px down to 640, so
a 6-pixel smear becomes one blurred pixel and nobody notices. Tiling removes that
free 6.3x forgiveness: the detector now sees the blur at full scale.

**Tiling makes the motion-blur budget 6.3x tighter.** That is a direct
consequence of the product decision, and it lands on the airframe, not the code.

Run:
    python training/motion_budget.py --altitude 30 --target-size 30
    python training/motion_budget.py --camera imx296 --altitude 41 --target-size 200
"""

from __future__ import annotations

import argparse
import os
import sys

# gsd_calculator.py sits next to this file and is not a package, so make the
# directory importable regardless of where this is run from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gsd_calculator import CAMERAS, native_gsd_cm  # noqa: E402

# Rolling-shutter readout time for a full frame, seconds.
#
# This is the number to MEASURE rather than trust: it varies with the sensor
# mode, binning and the line length the driver picks. The values below are
# order-of-magnitude figures for full-resolution stills; at 2x2 binning the
# readout roughly halves.
#
# Measure it properly by photographing a spinning propeller or a CRT-style
# rolling bar and reading the skew, or from `picamera2` sensor mode metadata.
READOUT_S = {
    "imx708": 0.033,   # ~33 ms full-res, approximate - MEASURE THIS
    "imx477": 0.030,
    "imx296": 0.0,     # global shutter: every row exposes simultaneously
    "m3m": 0.0,        # mechanical shutter
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", choices=sorted(CAMERAS), default="imx708")
    ap.add_argument("--altitude", type=float, default=30.0, help="AGL, metres.")
    ap.add_argument("--target-size", type=float, default=30.0, help="cm across.")
    ap.add_argument("--min-pixels", type=float, default=20.0,
                    help="Pixels across target needed for reliable detection.")
    ap.add_argument("--blur-px", type=float, default=1.0,
                    help="Motion smear budget, in native pixels.")
    ap.add_argument("--skew-px", type=float, default=5.0,
                    help="Tolerable top-to-bottom rolling-shutter shift, native px.")
    args = ap.parse_args()

    cam = CAMERAS[args.camera]
    readout = READOUT_S[args.camera]

    gsd_cm = native_gsd_cm(cam, args.altitude)
    gsd_m = gsd_cm / 100.0
    px_on_target = args.target_size / gsd_cm

    print(f"camera         : {cam['name']}")
    print(f"altitude       : {args.altitude:.0f} m AGL")
    print(f"native GSD     : {gsd_cm:.3f} cm/px")
    print(f"target         : {args.target_size:.0f} cm -> {px_on_target:.1f} px "
          f"({'resolvable' if px_on_target >= args.min_pixels else 'TOO SMALL'} "
          f"at >={args.min_pixels:.0f} px, tiled)")
    print()

    # --- 1. motion blur -------------------------------------------------
    # smear_m = ground_speed * exposure_time. Hold it to `blur_px` pixels.
    print(f"MOTION BLUR  (budget {args.blur_px:.0f} px = {args.blur_px * gsd_cm:.2f} cm on the ground)")
    print(f"{'speed m/s':>10}{'km/h':>8}{'max exposure':>15}{'  i.e.':>8}")
    print("-" * 46)
    for v in [1, 2, 3, 5, 8, 12, 15]:
        t = (args.blur_px * gsd_m) / v
        print(f"{v:>10.0f}{v * 3.6:>8.1f}{t * 1000:>12.2f} ms   1/{1 / t:.0f} s")
    print()
    print("  Shorter exposure needs more light or more gain. Gain adds noise, and")
    print("  noise costs detections. This is why survey flying happens in bright")
    print("  midday light, and why a slower pass genuinely buys image quality.")
    print()

    # --- 2. rolling shutter ---------------------------------------------
    if readout <= 0:
        print("ROLLING SHUTTER: none - this is a global-shutter sensor. Skew is zero")
        print("  at any speed, which is the whole reason to pay its resolution penalty.")
        return 0

    print(f"ROLLING SHUTTER  (readout ~{readout * 1000:.0f} ms full frame -- MEASURE, do not trust)")
    print(f"  Top and bottom of one frame are taken {readout * 1000:.0f} ms apart.")
    print(f"{'speed m/s':>10}{'km/h':>8}{'top-to-bottom skew':>21}{'  verdict':>10}")
    print("-" * 52)
    for v in [1, 2, 3, 5, 8, 12, 15]:
        shift_m = v * readout
        shift_px = shift_m / gsd_m
        verdict = "ok" if shift_px <= args.skew_px else "SKEWED"
        print(f"{v:>10.0f}{v * 3.6:>8.1f}{shift_px:>17.1f} px{verdict:>10}")
    print()
    v_max = (args.skew_px * gsd_m) / readout
    print(f"  Max ground speed for <={args.skew_px:.0f} px skew: **{v_max:.1f} m/s "
          f"({v_max * 3.6:.1f} km/h)**")
    print()

    # Be precise about what rolling shutter does and does not break. One target
    # only spans a few rows, so it is read almost instantaneously; the distortion
    # is a FRAME-level geometry error, not an object-level one.
    # A roughly square target spans about as many rows as columns.
    rows_on_target = px_on_target
    t_obj = readout * (rows_on_target / cam["height_px"])
    obj_shift_px = (5.0 * t_obj) / gsd_m   # at a representative 5 m/s
    print(f"  Across ONE {args.target_size:.0f} cm target ({rows_on_target:.0f} rows) the readout is")
    print(f"  only {t_obj * 1000:.2f} ms, so at 5 m/s the target itself is distorted by")
    print(f"  {obj_shift_px:.2f} px. **Rolling shutter does not break detection.**")
    print()
    print("  What it breaks is frame geometry: the footprint is a parallelogram, not")
    print("  a rectangle. That silently corrupts georeferencing, area measurement,")
    print("  stitching and photogrammetry -- and it looks perfectly sharp while doing")
    print("  it. Vibration turns the same effect into visible 'jello'.")
    print()
    print("  So: detection can fly fast. Mapping cannot. Decide per mission.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
