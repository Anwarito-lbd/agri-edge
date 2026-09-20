#!/usr/bin/env bash
# Run ArduPilot SITL and point it at agri-edge.
#
# SITL is a full ArduCopter build running on your computer: real EKF, real
# failsafes, real flight dynamics. It is the only way to test the telemetry path
# properly without an aircraft, and the fault matrix in the research report
# assumes it.
#
# WHAT THIS IS NOT
# ----------------
# `workstation/fake_autopilot.py` also emits real MAVLink and needs none of the
# toolchain below, but it only replays a scripted stream. It proves OUR decoder
# against the protocol. It cannot show how a real autopilot behaves when GPS
# drops mid-flight, because there is no EKF and no flight to disturb. Use SITL
# for that.
#
# PREREQUISITES -- none of which existed on the machine this was written on.
# SITL is compiled from source, so it needs a POSIX environment with a C++
# toolchain. On Windows that means WSL2 or Docker; there is no native build.
#
#   Linux / WSL2 Ubuntu:
#       sudo apt update && sudo apt install -y git python3-pip
#       cd vendor/ardupilot && ./Tools/environment_install/install-prereqs-ubuntu.sh -y
#
#   Docker (any host):
#       docker run --rm -it -p 14550:14550/udp ardupilot/ardupilot-dev-base \
#           bash -c "cd /ardupilot && ./Tools/autotest/sim_vehicle.py -v ArduCopter \
#                    --out=udp:host.docker.internal:14550"
#
# Then:
#       bash scripts/sitl.sh
#       agri-edge -c config/sitl.yaml fly --frames 20
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Overridable, because building ArduPilot on a Windows drive through WSL's
# /mnt/c is 5-10x slower than on the Linux filesystem -- waf touches tens of
# thousands of small files and every one crosses the 9p boundary. Copy the tree
# to ~/ardupilot inside WSL and point this at it:
#
#     ARDUPILOT=~/ardupilot bash scripts/sitl.sh
ARDUPILOT="${ARDUPILOT:-${REPO_ROOT}/vendor/ardupilot}"
VEHICLE="${VEHICLE:-ArduCopter}"
# Winnipeg-ish, matching workstation/fake_autopilot.py so both look the same
# downstream and a test cannot pass because it silently used the other one.
LOCATION="${LOCATION:-49.8951,-97.1384,230,90}"
OUT="${OUT:-udp:127.0.0.1:14550}"
SPEEDUP="${SPEEDUP:-1}"

fail() { echo "ERROR: $*" >&2; exit 1; }

# Checked before anything else touches the tree, because the error waf produces
# is about python3 and says nothing about line endings.
crlf_guard() {
    [ -f "${ARDUPILOT}/waf" ] || return 0
    # The carriage return is matched by code, not written as a literal. A
    # literal CR is exactly the byte an editor, a heredoc or a checkout quietly
    # rewrites, which would leave this guard silently matching nothing -- the
    # failure mode it exists to prevent.
    CR=$(printf '\r')
    if head -1 "${ARDUPILOT}/waf" | grep -q "$CR"; then
        fail "vendor/ardupilot has CRLF line endings and will not build on Linux.

Its shebang is read as '#!/usr/bin/env python3<CR>', so env looks for a program
literally named 'python3<CR>':

    /usr/bin/env: 'python3\r': No such file or directory

This happens when the tree is cloned on Windows, where core.autocrlf=true is
the default. vendor/ is a separate clone, so this repository's .gitattributes
cannot reach it. 21,822 of ArduPilot's files were affected here.

Fix the existing tree, from inside it:
    grep -rlI \"\$(printf '\\r')\" . | xargs sed -i 's/\r\$//'

Or re-clone with --config core.autocrlf=false (see the top of this script)."
    fi
}

[ -d "${ARDUPILOT}" ] || fail "vendor/ardupilot is missing. Clone it first:

    gh repo clone ArduPilot/ardupilot vendor/ardupilot -- \
        --depth 1 --recurse-submodules --config core.autocrlf=false

The --config matters on Windows. core.autocrlf=true is the default there, and
vendor/ is a separate clone that this repository's .gitattributes cannot reach,
so git rewrites all 21,822 of ArduPilot's text files to CRLF. waf then fails
with:

    /usr/bin/env: 'python3\r': No such file or directory"

[ -f "${ARDUPILOT}/Tools/autotest/sim_vehicle.py" ] || fail \
    "vendor/ardupilot looks incomplete -- Tools/autotest/sim_vehicle.py is absent.
    The clone needs --recurse-submodules."

crlf_guard

command -v python3 >/dev/null 2>&1 || fail "python3 not found. SITL's build tooling requires it."

# Check for a C++ compiler before letting waf spend several minutes discovering
# the same thing with a much longer error.
if ! command -v g++ >/dev/null 2>&1 && ! command -v clang++ >/dev/null 2>&1; then
    fail "No C++ compiler (g++ or clang++) on PATH.

SITL is compiled from source and cannot run without one. On Windows there is no
native build -- use WSL2 or Docker (see the header of this script).

To test the MAVLink path without a toolchain, use the scripted emitter instead:
    python workstation/fake_autopilot.py --duration 60
    agri-edge -c config/sitl.yaml fly --frames 20
It speaks real MAVLink but has no flight dynamics. See its module docstring for
exactly what that does and does not prove."
fi

echo "ArduPilot SITL"
echo "  vehicle : ${VEHICLE}"
echo "  location: ${LOCATION}"
echo "  MAVLink : ${OUT}   (agri-edge listens on udpin:0.0.0.0:14550)"
echo

cd "${ARDUPILOT}"
exec ./Tools/autotest/sim_vehicle.py \
    -v "${VEHICLE}" \
    --custom-location="${LOCATION}" \
    --speedup="${SPEEDUP}" \
    --out="${OUT}" \
    --no-rebuild-on-changes \
    "$@"
