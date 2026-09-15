#!/usr/bin/env bash
# Set up a Raspberry Pi 5 (+ AI HAT) to run agri-edge. Idempotent -- safe to re-run.
#
# Run ON the Pi, not on the laptop:
#     bash scripts/pi_setup.sh
#
# What this deliberately does NOT install: torch, YOLOX, the Hailo compiler.
# Those are laptop-side. The aircraft runs numpy, PyYAML, onnxruntime and
# HailoRT -- nothing else. Keeping the flight image small is not tidiness, it is
# how you keep a 2 GB dependency from being able to break a flight.

set -euo pipefail

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
ok()  { printf '   [ok] %s\n' "$1"; }
warn(){ printf '   [!!] %s\n' "$1"; }

# ---------------------------------------------------------------- sanity checks
say "Checking this is actually a Raspberry Pi 5"
if [ -f /proc/device-tree/model ]; then
    MODEL=$(tr -d '\0' < /proc/device-tree/model)
    ok "$MODEL"
    case "$MODEL" in
        *"Raspberry Pi 5"*) ;;
        *) warn "Not a Pi 5. The AI HAT needs the Pi 5's PCIe; continuing anyway." ;;
    esac
else
    warn "Cannot read /proc/device-tree/model -- are you running this on the Pi?"
fi

if [ "$(getconf LONG_BIT)" != "64" ]; then
    warn "32-bit OS detected. HailoRT and picamera2 need 64-bit Pi OS (Bookworm)."
fi

# ------------------------------------------------------------------- system pkgs
say "Updating system packages"
sudo apt-get update
sudo apt-get full-upgrade -y

say "Installing camera and Python build prerequisites"
sudo apt-get install -y \
    python3-picamera2 python3-venv python3-pip python3-dev \
    libcap-dev libcamera-apps git

# ------------------------------------------------------------------------ hailo
say "Installing the Hailo runtime stack"
# hailo-all pulls HailoRT, the PCIe driver, the Python bindings and TAPPAS.
if sudo apt-get install -y hailo-all; then
    ok "hailo-all installed"
else
    warn "hailo-all not available. It ships in Raspberry Pi OS Bookworm's repo --"
    warn "check your OS version. Skipping; ONNX-on-CPU will still work."
fi

# PCIe Gen 3 roughly doubles NPU bandwidth. Not enabled by default because not
# every board/cable combination is stable at Gen 3; if the device stops being
# detected after a reboot, set this back to 2.
say "Enabling PCIe Gen 3"
CONFIG=/boot/firmware/config.txt
[ -f "$CONFIG" ] || CONFIG=/boot/config.txt
if ! grep -q "^dtparam=pciex1_gen=3" "$CONFIG" 2>/dev/null; then
    echo "dtparam=pciex1_gen=3" | sudo tee -a "$CONFIG" > /dev/null
    ok "Added dtparam=pciex1_gen=3 to $CONFIG (reboot required)"
    NEEDS_REBOOT=1
else
    ok "PCIe Gen 3 already enabled"
fi

# ----------------------------------------------------------------- agri-edge
say "Installing agri-edge (core + camera + onnx extras only)"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --system-site-packages so the venv can see python3-picamera2, which is an apt
# package and is painful to install with pip on the Pi.
if [ ! -d .venv ]; then
    python3 -m venv --system-site-packages .venv
    ok "Created .venv"
fi
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -e ".[onnx]"
ok "agri-edge installed"

# ----------------------------------------------------------------- verification
say "Verifying"

if command -v hailortcli > /dev/null 2>&1; then
    if hailortcli fw-control identify 2>/dev/null | head -5; then
        ok "Hailo device responds"
    else
        warn "hailortcli found but the device did not respond -- reboot, then re-run."
    fi
else
    warn "hailortcli not on PATH (expected if hailo-all did not install)"
fi

if command -v rpicam-hello > /dev/null 2>&1; then
    if rpicam-hello -t 2000 --nopreview 2>&1 | tail -3; then
        ok "Camera responds"
    else
        warn "Camera did not respond -- check the ribbon cable seating and orientation."
    fi
else
    warn "rpicam-hello not found; camera stack may not be installed"
fi

./.venv/bin/python -c "import numpy, yaml, agri_edge; print('   agri_edge', agri_edge.__version__)"

say "Next"
cat <<'EOF'
   1. Verify the camera's channel order before trusting any detection:
          .venv/bin/python -c "from picamera2 import Picamera2; import numpy as np; \
            c=Picamera2(); c.configure(c.create_still_configuration()); c.start(); \
            a=c.capture_array('main'); print(a.shape, a.dtype)"
      Point the camera at something strongly red. If the RED channel is not the
      largest, the frames are BGR and Picamera2Camera must swap them. Swapped
      channels degrade detection subtly rather than obviously -- it will not be
      the first thing you suspect.

   2. Edge preflight:
          .venv/bin/agri-edge -c config/pi.yaml preflight

   3. Live run:
          .venv/bin/agri-edge -c config/pi.yaml fly --duration 60

   Note: with no autopilot connected, every frame is skipped as "stale telemetry"
   by design. Use --simulate for bench work rather than weakening that gate.
EOF

if [ "${NEEDS_REBOOT:-0}" = "1" ]; then
    warn "Reboot required for PCIe Gen 3: sudo reboot"
fi
