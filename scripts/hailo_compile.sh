#!/usr/bin/env bash
# Compile the exported ONNX model to a Hailo .hef.
#
# RUN THIS IN WSL2 UBUNTU, NOT WINDOWS AND NOT ON THE PI.
#
# The Hailo Dataflow Compiler is x86_64 Linux only. It does not run on Windows,
# and it does not run on the Pi's ARM CPU. On a Windows dev machine that means
# WSL2:
#
#     wsl --install -d Ubuntu-22.04       # admin PowerShell, then reboot
#
# The DFC is not on PyPI -- download the wheel from the Hailo Developer Zone
# (free account) and install it into a Python 3.10 venv inside WSL, along with
# hailo_model_zoo from vendor/.
#
#     bash scripts/hailo_compile.sh --arch hailo8l

set -euo pipefail

MODEL="models/weed_crop_yolox_s.onnx"
CALIB="data/weed-crop-aerial/train/images"
ARCH="hailo8l"
CLASSES=2
ZOO_MODEL="yolox_s_leaky"
OUT_DIR="models"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)   MODEL="$2"; shift 2 ;;
        --calib)   CALIB="$2"; shift 2 ;;
        --arch)    ARCH="$2"; shift 2 ;;
        --classes) CLASSES="$2"; shift 2 ;;
        --out)     OUT_DIR="$2"; shift 2 ;;
        # Run every preflight check and print the command, without
        # compiling. This is what `make hailo-smoke` calls: it exercises
        # the argument handling and the environment checks on a machine
        # that will never have the Dataflow Compiler, so the script is
        # known-good before the one machine that can run it exists.
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
die() { printf '\n\033[31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

say "Preflight"

# The single most common way this script is run wrongly.
case "$(uname -m)" in
    x86_64) echo "   arch: x86_64 (ok)" ;;
    aarch64) die "Running on ARM. The Hailo compiler cannot run on the Pi. Use an x86_64 Linux machine or WSL2." ;;
    *) die "Unsupported architecture: $(uname -m)" ;;
esac

# Validate arguments before probing the environment: checking a string is free,
# and it is infuriating to install a toolchain only to be told a flag was
# misspelled. The arch must match the board -- a .hef built for the wrong one
# compiles cleanly and then refuses to load, with an error that never mentions
# architecture.
case "$ARCH" in
    hailo8l)  echo "   target: Hailo-8L  -- AI HAT+ 13 TOPS" ;;
    hailo8)   echo "   target: Hailo-8   -- AI HAT+ 26 TOPS" ;;
    hailo10h) echo "   target: Hailo-10H -- AI HAT+ 2, 40 TOPS" ;;
    *) die "Unknown --arch '$ARCH'. Expected hailo8l, hailo8 or hailo10h." ;;
esac

need() {
    # $1 what is missing, $2 the label, $3 the fatal message.
    if [ "$DRY_RUN" = "1" ]; then
        printf "   %s: %s\n" "$2" "$1"
        return 0
    fi
    die "$3"
}

[ -f "$MODEL" ] || need "MISSING" "model" \
    "Model not found: $MODEL  (run training/export_onnx.py first)"
[ -d "$CALIB" ] || need "MISSING" "calibration set" \
    "Calibration images not found: $CALIB"

if [ "$DRY_RUN" = "1" ] && ! command -v hailomz > /dev/null 2>&1; then
    echo "   hailomz: absent (dry run, not required)"
else
command -v hailomz > /dev/null 2>&1 || die \
"hailomz not found. Inside WSL2 Ubuntu:
   1. Create a Python 3.10 venv
   2. Install the Hailo Dataflow Compiler wheel from the Hailo Developer Zone
      (https://hailo.ai/developer-zone/ -- free account; it is not on PyPI)
   3. pip install -e vendor/hailo_model_zoo"
fi

N_CALIB=$(find "$CALIB" -maxdepth 1 \( -name '*.jpg' -o -name '*.png' \) 2>/dev/null | wc -l)
echo "   calibration images: $N_CALIB"
[ "$N_CALIB" -ge 64 ] || need "$N_CALIB (need 64+)" "calibration count" \
    "Need at least ~64 calibration images, found $N_CALIB."

mkdir -p "$OUT_DIR"

if [ "$DRY_RUN" = "1" ]; then
    say "Dry run, not compiling"
    HEF_NAME="$(basename "${MODEL%.onnx}").hef"
    cat <<EOF
   Would run:

     hailomz compile $ZOO_MODEL \\
         --ckpt $MODEL \\
         --hw-arch $ARCH \\
         --calib-path $CALIB \\
         --classes $CLASSES \\
         --performance

   Then move the .hef to $OUT_DIR/$HEF_NAME and copy the provenance sidecar
   beside it, so validated_locally still travels with the model onto the Pi.

   Preflight passed as far as it can without the Dataflow Compiler. What is
   still needed is WSL2 with the DFC wheel installed; see the header of this
   script.
EOF
    exit 0
fi

say "Compiling $MODEL -> $ARCH"
# Quantisation to INT8 is data-dependent: the compiler measures activation ranges
# on the calibration set. Calibrating on the wrong distribution is the usual
# cause of "works in ONNX, garbage on the NPU", so these must be real training
# images from this dataset -- not COCO, not random photos.
hailomz compile "$ZOO_MODEL" \
    --ckpt "$MODEL" \
    --hw-arch "$ARCH" \
    --calib-path "$CALIB" \
    --classes "$CLASSES" \
    --performance

HEF=$(ls -t ./*.hef 2>/dev/null | head -1)
[ -n "$HEF" ] || die "Compilation finished but no .hef was produced."

TARGET="$OUT_DIR/$(basename "${MODEL%.onnx}").hef"
mv "$HEF" "$TARGET"

# Carry the provenance sidecar across, so validated_locally still travels with
# the model on the Pi.
if [ -f "${MODEL}.meta.json" ]; then
    cp "${MODEL}.meta.json" "${TARGET}.meta.json"
    echo "   copied provenance sidecar"
fi

say "Done"
echo "   $TARGET  ($(du -h "$TARGET" | cut -f1))"
cat <<EOF

Next, on the Pi:

  1. Copy $TARGET and ${TARGET}.meta.json to the Pi.

  2. Test the .hef standalone FIRST, via vendor/hailo-rpi5-examples.
     Confirm the NPU gives sane detections before integrating. Debugging a bad
     .hef and a new engine class at the same time is how a day disappears.

  3. Then point config/pi.yaml at it:
         inference:
           backend: hailo
           model_path: models/$(basename "$TARGET")

  4. agri-edge -c config/pi.yaml fly --duration 60
EOF
