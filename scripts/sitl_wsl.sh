#!/usr/bin/env bash
# Run ArduCopter SITL inside WSL2 and forward MAVLink to agri-edge on Windows.
#
#     wsl -d Ubuntu-22.04 -u root -e bash scripts/sitl_wsl.sh
#
# scripts/sitl.sh is the right script when SITL and agri-edge share a machine.
# This one exists for the split that a Windows dev box forces: the toolchain
# only exists inside WSL, and the tests run outside it.
#
# FIRST RUN
# ---------
# Stage the tree onto ext4 and build. Building through /mnt/c is 5-10x slower
# because waf touches tens of thousands of small files and every one crosses
# WSL's 9p boundary.
#
#     tar --exclude=./.git --exclude=./build -C vendor/ardupilot -cf - . \
#         | tar -C ~/ardupilot -xf -
#     cd ~/ardupilot
#     grep -rlI "$(printf '\r')" . | xargs sed -i 's/\r$//'   # see CRLF below
#     git init -q && git commit -q --allow-empty -m staged     # waf wants a HEAD
#     ./waf configure --board sitl --no-submodule-update
#     ./waf copter --no-submodule-update                       # ~2 min, 20 cores
#
# THREE THINGS THAT WILL BITE
# ---------------------------
# CRLF. vendor/ardupilot is a separate clone, so this repository's
# .gitattributes cannot reach it and core.autocrlf rewrote all 21,822 of its
# text files. waf then dies on `/usr/bin/env: 'python3\r'`. Either strip them as
# above, or re-clone with --config core.autocrlf=false.
#
# Submodules. A staged copy has a synthetic .git with none registered, so waf's
# `git submodule status --recursive` fails. The submodule CONTENTS came across
# in the tar; only the bookkeeping is missing, which is what
# --no-submodule-update is for.
#
# Stream rates. The arducopter binary alone emits HEARTBEAT and nothing else.
# ArduPilot streams position and attitude at the rates in its SRx_ parameters,
# and a ground station normally REQUESTS them at connect. MavlinkTelemetry
# cannot -- it is read-only by construction and has no method that transmits,
# which is deliberate. So MAVProxy runs here as the ground station: it asks, and
# agri-edge observes a stream someone else established. On the real airframe
# there is no MAVProxy between the autopilot and the Pi, so the SRx_ block must
# be set on the autopilot instead -- see config/sitl-streams.parm.
#
# sim_vehicle.py would normally do all this, but it launches MAVProxy through
# run_in_terminal_window.sh, which wants a TTY. With none, MAVProxy exits two
# seconds in and takes the whole thing down with it. Hence two processes and
# --daemon.
set -euo pipefail

ARDUPILOT="${ARDUPILOT:-$HOME/ardupilot}"
LOCATION="${LOCATION:-49.8951,-97.1384,230,90}"
DURATION="${DURATION:-900}"
PORT="${PORT:-14550}"

fail() { echo "ERROR: $*" >&2; exit 1; }

[ -x "${ARDUPILOT}/build/sitl/bin/arducopter" ] || fail \
"No SITL binary at ${ARDUPILOT}/build/sitl/bin/arducopter.
Build it first -- see FIRST RUN at the top of this script."

command -v mavproxy.py >/dev/null 2>&1 || fail \
"mavproxy.py not found. pip install MAVProxy pymavlink"

# SITL runs in the WSL VM and agri-edge runs on Windows, so 127.0.0.1 is the
# VM's own loopback. The Windows host is the VM's default gateway.
HOST_IP="$(ip route show default | awk '{print $3; exit}')"
[ -n "${HOST_IP}" ] || fail "could not determine the Windows host IP"

cd "${ARDUPILOT}"
pkill -f arducopter 2>/dev/null || true
pkill -f mavproxy   2>/dev/null || true
sleep 1

echo "ArduCopter SITL (WSL)"
echo "  location : ${LOCATION}"
echo "  MAVLink  : udp:${HOST_IP}:${PORT}   (Windows listens on 0.0.0.0:${PORT})"
echo "  duration : ${DURATION}s"
echo
echo "Then, on the Windows side:"
echo "    python -m pytest tests/test_sitl.py -v"
echo "    python -m agri_edge.cli -c config/sitl.yaml fly --sitl --frames 10"
echo

timeout "${DURATION}" ./build/sitl/bin/arducopter \
    --model quad \
    --home "${LOCATION}" \
    --defaults Tools/autotest/default_params/copter.parm \
    > /tmp/arducopter.log 2>&1 &

# Let it bind TCP 5760 before MAVProxy attaches.
sleep 6

timeout "${DURATION}" mavproxy.py \
    --daemon \
    --master tcp:127.0.0.1:5760 \
    --out "udp:${HOST_IP}:${PORT}" \
    > /tmp/mavproxy.log 2>&1 &

sleep 8
echo "  arducopter: $(pgrep -c arducopter || echo 0)   mavproxy: $(pgrep -cf mavproxy || echo 0)"
echo "  logs: /tmp/arducopter.log  /tmp/mavproxy.log"
echo
echo "Running. Ctrl-C to stop, or it exits after ${DURATION}s."
wait
