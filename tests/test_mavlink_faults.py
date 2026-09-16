"""Fault injection against a real MAVLink stream.

Until now `MavlinkTelemetry` had never parsed a real MAVLink packet: its tests
called `_ingest()` with hand-built dicts, which exercises the folding logic and
nothing about wire format, UDP, the heartbeat handshake, or field scaling. Those
scalings are where telemetry bugs hide, because every one of them produces a
plausible-looking number in the wrong place:

    lat/lon       int32 degrees x 1e7
    altitudes     millimetres
    HDOP (eph)    centi-units
    heading       centi-degrees
    attitude      radians, not degrees

These tests run `workstation/fake_autopilot.py`, which speaks genuine MAVLink
through pymavlink, and walk the fault matrix from the research report down onto
the gates that already exist in `qa/checks.py`.

**What this does NOT prove.** It tests our decoder against the real protocol, not
an autopilot against reality. Flight dynamics, EKF behaviour, mode changes and
real failsafes need ArduPilot SITL (`scripts/sitl.sh`), which needs a compiler,
WSL or Docker — none of which exist on the machine this was written on. A green
run here is not "tested against an autopilot".

Skipped cleanly when pymavlink is absent, so the Pi runtime's suite stays green.
"""

import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("pymavlink", reason="needs the mavlink extra")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workstation"))

from fake_autopilot import FakeAutopilot  # noqa: E402

from agri_edge.qa.checks import Severity, check_attitude, check_gnss  # noqa: E402
from agri_edge.telemetry.mavlink_link import MavlinkTelemetry  # noqa: E402

# Each test gets its own port so a lingering socket from a previous test cannot
# feed the next one stale packets and turn a real failure green.
_PORT = iter(range(14600, 14700))


def _link(fault="none", fault_after_s=0.0, settle_s=1.2):
    """Bring up an emitter and a reader on a private port; return a snapshot fn."""
    port = next(_PORT)
    ap = FakeAutopilot(
        connection=f"udpout:127.0.0.1:{port}",
        rate_hz=20.0,
        fault=fault,
        fault_after_s=fault_after_s,
    )
    ap.start()
    time.sleep(0.3)   # let the sender bind before the reader waits for a heartbeat
    tel = MavlinkTelemetry(connection=f"udpin:0.0.0.0:{port}", heartbeat_timeout_s=10.0)
    tel.start()
    time.sleep(settle_s)
    return ap, tel


class TestHealthyLink:
    """Field-by-field, because each scaling is a separate chance to be wrong."""

    @pytest.fixture(scope="class")
    @staticmethod
    def snap():
        ap, tel = _link()
        try:
            yield tel.snapshot()
        finally:
            tel.stop()
            ap.stop()

    def test_position_decodes_from_int32_degrees(self, snap):
        assert snap.lat == pytest.approx(49.8951, abs=1e-4)
        assert snap.lon == pytest.approx(-97.1384, abs=1e-4)

    def test_relative_and_msl_altitude_are_not_confused(self, snap):
        """Both are millimetres on the wire and they differ by ground elevation."""
        assert snap.alt_rel_m == pytest.approx(30.0, abs=0.1)
        assert snap.alt_msl_m == pytest.approx(260.0, abs=0.1)

    def test_hdop_converts_from_centi_units(self, snap):
        """eph=80 is HDOP 0.80, not 80. A factor of 100 here passes every gate."""
        assert snap.hdop == pytest.approx(0.80, abs=0.01)

    def test_fix_and_satellites(self, snap):
        assert snap.fix_type == 6
        assert snap.fix_name == "rtk-fixed"
        assert snap.is_rtk_fixed is True
        assert snap.satellites == 18

    def test_attitude_converts_radians_to_degrees(self, snap):
        assert snap.yaw_deg == pytest.approx(90.0, abs=0.1)
        assert snap.roll_deg == pytest.approx(0.0, abs=0.1)

    def test_battery_and_groundspeed(self, snap):
        assert snap.battery_pct == pytest.approx(72.0)
        assert snap.groundspeed_ms == pytest.approx(5.0, abs=0.1)

    def test_snapshot_is_fresh(self, snap):
        assert snap.age_s() < 3.0

    def test_healthy_link_passes_both_gates(self, snap):
        assert check_gnss(snap, 3, True, 2.5, 6).severity is Severity.OK
        assert check_attitude(snap, 10.0).severity is Severity.OK


class TestFaultMatrix:
    """Each row: a fault on the wire, and the gate that must catch it."""

    def test_gnss_loss_fails_the_gnss_gate(self):
        ap, tel = _link(fault="gnss-loss")
        try:
            s = tel.snapshot()
            assert s.fix_type == 0
            assert s.has_position is False
            assert check_gnss(s, 3, False, 2.5, 6).severity is Severity.FAIL
        finally:
            tel.stop()
            ap.stop()

    def test_rtk_float_passes_3d_but_fails_when_rtk_is_required(self):
        """The distinction that matters for cross-date comparison."""
        ap, tel = _link(fault="rtk-float")
        try:
            s = tel.snapshot()
            assert s.fix_type == 5 and s.is_rtk_fixed is False
            assert check_gnss(s, 3, False, 2.5, 6).severity is Severity.OK
            assert check_gnss(s, 3, True, 2.5, 6).severity is Severity.FAIL
        finally:
            tel.stop()
            ap.stop()

    def test_low_satellites_warns_rather_than_fails(self):
        """A warn still spools the frame. Degrade, do not discard."""
        ap, tel = _link(fault="low-sats")
        try:
            s = tel.snapshot()
            assert s.satellites == 3
            assert check_gnss(s, 3, False, 2.5, 6).severity is Severity.WARN
        finally:
            tel.stop()
            ap.stop()

    def test_high_hdop_warns(self):
        ap, tel = _link(fault="high-hdop")
        try:
            s = tel.snapshot()
            assert s.hdop == pytest.approx(5.0, abs=0.01)
            assert check_gnss(s, 3, False, 2.5, 6).severity is Severity.WARN
        finally:
            tel.stop()
            ap.stop()

    def test_tilt_warns_on_the_attitude_gate(self):
        """25 deg roll and 10 deg pitch: the frame is oblique.

        WARN rather than FAIL, deliberately. An off-nadir frame is degraded, not
        worthless -- it still shows what was there, it just will not
        orthorectify cleanly. The project rule is that failed QA flags data and
        never discards it, so this spools at DEGRADED priority rather than being
        dropped.

        Combined tilt is hypot(25, 10) = 26.9 deg, not 25.
        """
        ap, tel = _link(fault="tilt")
        try:
            s = tel.snapshot()
            assert s.roll_deg == pytest.approx(25.0, abs=0.5)
            assert s.pitch_deg == pytest.approx(10.0, abs=0.5)
            result = check_attitude(s, 10.0)
            assert result.severity is Severity.WARN
            assert result.value == pytest.approx(26.9, abs=0.2)
            assert check_attitude(s, 30.0).severity is Severity.OK
        finally:
            tel.stop()
            ap.stop()

    def test_silence_goes_stale_rather_than_erroring(self):
        """The nastiest failure: the link stops without closing.

        Nothing raises, the reader just blocks, and the last snapshot sits there
        looking perfectly valid. Only its age reveals it — which is why
        `capture.max_telemetry_age_s` exists and why the pipeline refuses to
        capture rather than trusting a stale position.
        """
        ap, tel = _link(fault="silence", fault_after_s=0.8, settle_s=1.0)
        try:
            fresh = tel.snapshot()
            assert fresh.age_s() < 1.0, "should still be live before the fault"
            time.sleep(2.5)
            stale = tel.snapshot()
            assert stale.age_s() > 2.0, "stream stopped; snapshot must age"
            # The values are still there and still look fine. That is the trap.
            assert stale.lat == pytest.approx(49.8951, abs=1e-4)
            assert check_gnss(stale, 3, True, 2.5, 6).severity is Severity.OK
        finally:
            tel.stop()
            ap.stop()


class TestSafetyContract:
    def test_the_emitter_cannot_receive_commands(self):
        """`MavlinkTelemetry` is read-only by construction.

        The existing contract test asserts no command method exists on our class.
        This asserts the other half: the test autopilot has no receive path
        either, so nothing in this suite could accidentally demonstrate a command
        working and normalise the idea.
        """
        for forbidden in ("recv", "recv_match", "handle_command", "arm", "set_mode"):
            assert not hasattr(FakeAutopilot, forbidden), forbidden

    def test_telemetry_class_exposes_no_command_surface(self):
        banned = ("arm", "disarm", "set_mode", "takeoff", "land", "send",
                  "upload_mission", "command_long")
        for name in banned:
            assert not hasattr(MavlinkTelemetry, name), f"MavlinkTelemetry.{name} exists"
