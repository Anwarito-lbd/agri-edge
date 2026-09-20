"""agri-edge against a real ArduPilot, not a script that imitates one.

WHAT THIS PROVES THAT test_mavlink_faults.py CANNOT
---------------------------------------------------
`workstation/fake_autopilot.py` emits genuine MAVLink and is the right tool for
checking our decoder against the wire format. It has no EKF, no flight, and no
opinion of its own -- it replays whatever the test asked for, so it can only
confirm we read correctly what we chose to send.

SITL is a full ArduCopter build: real EKF, real failsafes, real flight dynamics,
and a GPS model with real noise. Its numbers are produced by an autopilot rather
than by the test, which is what makes them worth reading. A heading that drifts,
an HDOP that moves, an altitude that settles -- none of those can come out of a
scripted emitter, and all of them are what the QA gates will actually see.

THE CONTRACT THIS RE-ASSERTS
----------------------------
`MavlinkTelemetry` is read-only by construction and a test already asserts that
against a stub. The point of re-asserting it here is that SITL is a vehicle
which *would* obey a command. A read-only contract verified only against
something that could not act on a write has not been verified.

WHY IT SKIPS
------------
SITL is compiled from source, so it needs a POSIX toolchain -- WSL2 or Docker on
Windows. These tests skip unless something is already broadcasting MAVLink on
the configured endpoint. That keeps CI green on a runner with no autopilot,
which is the honest state, rather than pretending the path is covered.

    # terminal 1
    bash scripts/sitl.sh                    # or: ARDUPILOT=~/ardupilot bash scripts/sitl.sh
    # terminal 2
    python -m pytest tests/test_sitl.py -v
"""

from __future__ import annotations

import math
import os
import socket
import time

import pytest

pytest.importorskip("pymavlink", reason="needs the mavlink extra")

from agri_edge.qa.checks import (  # noqa: E402
    Severity,
    check_attitude,
    check_gnss,
)
from agri_edge.telemetry.mavlink_link import (  # noqa: E402
    GPS_FIX_3D,
    MavlinkTelemetry,
)

# Where scripts/sitl.sh sends its second MAVLink stream.
SITL_ENDPOINT = os.environ.get("SITL_ENDPOINT", "udpin:0.0.0.0:14550")
SITL_PORT = int(SITL_ENDPOINT.rsplit(":", 1)[1])

# Long enough for the EKF to settle and a GPS fix to appear. SITL takes a few
# seconds from launch; a shorter wait produces a flaky "no fix" that looks like
# a bug in the gate rather than an impatient test.
SETTLE_S = 25.0


def _something_is_broadcasting(port: int, timeout_s: float = 6.0) -> bool:
    """True if any MAVLink-looking packet arrives on the port.

    Deliberately not a MavlinkTelemetry connection: this decides whether to
    skip, and a skip decision must not depend on the thing under test.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout_s)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            # Something else already holds the port -- most likely SITL's own
            # client. Treat that as "not available to us" rather than guessing.
            return False
        try:
            data, _ = sock.recvfrom(512)
        except socket.timeout:
            return False
        # v1 and v2 magic bytes.
        return len(data) > 0 and data[0] in (0xFE, 0xFD)
    finally:
        sock.close()


pytestmark = pytest.mark.skipif(
    not _something_is_broadcasting(SITL_PORT),
    reason=(
        f"nothing is broadcasting MAVLink on {SITL_ENDPOINT}. "
        "Start it with: bash scripts/sitl.sh"
    ),
)


@pytest.fixture(scope="module")
def link():
    """One connection for the module. Each test reads the latest snapshot."""
    telem = MavlinkTelemetry(SITL_ENDPOINT, heartbeat_timeout_s=15.0)
    telem.start()

    # Wait for a position rather than a fixed sleep: SITL's fix appears when it
    # appears, and polling says why it failed if it never does.
    deadline = time.time() + SETTLE_S
    while time.time() < deadline:
        if telem.snapshot().has_position:
            break
        time.sleep(0.5)

    yield telem
    telem.stop()


class TestRealAutopilot:
    def test_the_link_reports_a_heartbeat(self, link):
        """start() only returns if a heartbeat arrived -- it raises otherwise.
        Reaching this line is the assertion."""
        assert link.snapshot().timestamp > 0

    def test_a_position_arrives(self, link):
        snap = link.snapshot()
        assert snap.has_position, (
            f"no 3D fix after {SETTLE_S:.0f}s: fix={snap.fix_name} "
            f"sats={snap.satellites} hdop={snap.hdop}"
        )
        assert snap.fix_type >= GPS_FIX_3D

    def test_the_position_is_where_sitl_was_told_to_be(self, link):
        """scripts/sitl.sh launches at 49.8951, -97.1384 (Winnipeg-ish), the
        same place workstation/fake_autopilot.py uses -- so a test cannot pass
        because it silently connected to the other one. Within ~2 km covers any
        drift while the EKF settles."""
        snap = link.snapshot()
        assert math.isclose(snap.lat, 49.8951, abs_tol=0.02), snap.lat
        assert math.isclose(snap.lon, -97.1384, abs_tol=0.02), snap.lon

    def test_satellites_and_hdop_are_plausible(self, link):
        snap = link.snapshot()
        assert snap.satellites >= 6, f"only {snap.satellites} satellites"
        assert 0.0 < snap.hdop < 5.0, f"hdop {snap.hdop}"

    def test_attitude_is_present_and_in_radians_not_degrees(self, link):
        """The scaling bug that produces a plausible number in the wrong place.
        A stationary copter is near level, so a value above a few degrees means
        radians were read as degrees or vice versa."""
        snap = link.snapshot()
        assert snap.roll_deg is not None and snap.pitch_deg is not None
        assert abs(snap.roll_deg) < 15.0, snap.roll_deg
        assert abs(snap.pitch_deg) < 15.0, snap.pitch_deg

    def test_the_snapshot_keeps_moving(self, link):
        """A stale snapshot that never updates looks identical to a healthy one
        in a single read. This is the check that separates them."""
        first = link.snapshot()
        time.sleep(2.0)
        second = link.snapshot()
        assert second.timestamp > first.timestamp, "telemetry stopped updating"

    def test_telemetry_is_fresh_by_the_pipeline_s_standard(self, link):
        assert link.snapshot().age_s() < 2.0


class TestGatesAgainstRealTelemetry:
    """The QA gates, fed by an autopilot instead of by the test."""

    def test_gnss_gate_passes_a_healthy_sitl_fix(self, link):
        result = check_gnss(
            link.snapshot(),
            min_fix_type=GPS_FIX_3D,
            require_rtk_fixed=False,
            max_hdop=2.5,
            min_satellites=6,
        )
        assert result.severity is Severity.OK, result.detail

    def test_rtk_gate_correctly_refuses_a_non_rtk_fix(self, link):
        """SITL's default GPS is not RTK. The gate must say so rather than pass
        -- it exists precisely to keep a standard fix out of a plot-research
        dataset."""
        result = check_gnss(
            link.snapshot(),
            min_fix_type=GPS_FIX_3D,
            require_rtk_fixed=True,
            max_hdop=2.5,
            min_satellites=6,
        )
        assert result.severity is not Severity.OK
        assert not link.snapshot().is_rtk_fixed

    def test_attitude_gate_passes_a_level_copter(self, link):
        assert check_attitude(link.snapshot(), max_tilt_deg=10.0).severity is Severity.OK

    def test_attitude_gate_would_flag_a_tilt(self, link):
        """The gate has to be capable of failing, or passing means nothing. A
        real snapshot with an impossible threshold proves the comparison runs
        on live values rather than being short-circuited somewhere."""
        assert check_attitude(link.snapshot(), max_tilt_deg=0.0).severity is not Severity.OK


class TestReadOnlyAgainstSomethingThatCouldObey:
    def test_the_link_has_no_method_that_could_command_the_vehicle(self, link):
        """Asserted elsewhere against a stub. Re-asserted here because SITL is
        a vehicle that *would* act on a write, and a contract verified only
        against something incapable of obeying has not been verified."""
        for forbidden in (
            "send", "arm", "disarm", "set_mode", "command_long",
            "mav", "write", "param_set", "mission_item_send",
        ):
            assert not hasattr(link, forbidden), forbidden

    def test_the_underlying_connection_is_not_exposed(self, link):
        """A private handle is fine; a public one is an invitation. `_conn` is
        reachable by anyone determined enough, but nothing in the public API
        hands it out."""
        public = [n for n in dir(link) if not n.startswith("_")]
        assert "conn" not in public and "connection" not in public
