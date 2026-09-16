"""Reflectance calibration, and RTK corrections.

Both close a gate that could not previously open: every index was permanently
`calibrated=False`, and `require_rtk_fixed` could never pass because nothing
delivered corrections.

The NTRIP tests carry a safety assertion as well as functional ones. Corrections
go to the GNSS receiver over its own serial link, never to the flight controller
over MAVLink, so that `MavlinkTelemetry` stays read-only by construction. A test
asserts the client has no MAVLink surface at all, because the tempting shortcut
here is exactly the one that would quietly end that property.
"""

import socket
import threading
import time

import numpy as np
import pytest

from agri_edge.geo.calibration import (
    GREY_50,
    CalibrationGains,
    ReflectancePanel,
    apply_gains,
    calibrated_stack,
    compute_gains,
    panel_drift,
)
from agri_edge.geo.indices import BandStack, ndvi
from agri_edge.telemetry.ntrip import (
    NtripClient,
    NtripConfig,
    NtripStats,
    build_request,
    check_response,
)

BANDS = ["red", "nir"]
PANEL = ReflectancePanel({"red": 0.5, "nir": 0.5}, label="test 50% grey")


def stack(red, nir, shape=(8, 8)):
    return BandStack(
        np.stack([np.full(shape, red, float), np.full(shape, nir, float)], axis=2), BANDS
    )


class TestPanel:
    def test_reflectance_must_be_a_fraction(self):
        """50 means 5000%, and the resulting gain would be 100x wrong."""
        with pytest.raises(ValueError, match="fractions"):
            ReflectancePanel({"red": 50.0})

    def test_empty_panel_is_rejected(self):
        with pytest.raises(ValueError):
            ReflectancePanel({})

    def test_the_default_panel_is_labelled_a_placeholder(self):
        """Nobody should ship a map calibrated against a guess."""
        assert "PLACEHOLDER" in GREY_50.label


class TestGains:
    def test_gain_maps_the_panel_to_its_known_value(self):
        cal = compute_gains(stack(100.0, 200.0), PANEL)
        assert cal.gains["red"] == pytest.approx(0.5 / 100.0)
        assert cal.gains["nir"] == pytest.approx(0.5 / 200.0)

    def test_applying_the_gain_reproduces_the_panel_reflectance(self):
        raw = stack(100.0, 200.0)
        out = apply_gains(raw, compute_gains(raw, PANEL))
        assert out.band("red").mean() == pytest.approx(0.5)
        assert out.band("nir").mean() == pytest.approx(0.5)

    def test_a_saturated_panel_is_refused(self):
        """Clipped pixels hide the true mean, so the gain would be too high."""
        with pytest.raises(ValueError, match="saturated"):
            compute_gains(stack(255.0, 255.0), PANEL)

    def test_a_near_black_panel_is_refused(self):
        """Near-black is sensor noise; the gain would be unstable."""
        with pytest.raises(ValueError, match="too dark"):
            compute_gains(stack(3.0, 3.0), PANEL)

    def test_a_region_isolates_the_panel_from_its_surroundings(self):
        """Averaging the grass around the panel biases the gain by whatever it
        reflects -- which is the most likely way to get this subtly wrong."""
        img = np.zeros((10, 10, 2), float)
        img[...] = 20.0            # dark grass
        img[2:5, 2:5] = 100.0      # the panel
        s = BandStack(img, BANDS)
        whole = compute_gains(s, PANEL)
        just_panel = compute_gains(s, PANEL, region=(2, 5, 2, 5))
        assert just_panel.gains["red"] == pytest.approx(0.5 / 100.0)
        assert whole.gains["red"] != pytest.approx(just_panel.gains["red"])

    def test_no_overlapping_bands_is_an_error(self):
        with pytest.raises(ValueError, match="No overlap"):
            compute_gains(stack(100.0, 100.0), ReflectancePanel({"thermal": 0.5}))


class TestApplication:
    def test_bands_without_a_gain_are_dropped_not_passed_through(self):
        """A stack mixing calibrated and raw bands makes an index that is
        neither, and labelling it calibrated would be a lie."""
        img = np.stack([np.full((4, 4), 100.0)] * 3, axis=2)
        s = BandStack(img, ["red", "nir", "green"])
        out = apply_gains(s, CalibrationGains(gains={"red": 0.005, "nir": 0.005}))
        assert out.available == ["nir", "red"]
        assert "green" not in out.available

    def test_no_usable_band_raises(self):
        with pytest.raises(ValueError, match="No band has a gain"):
            apply_gains(stack(100.0, 100.0), CalibrationGains(gains={"thermal": 1.0}))


class TestCalibratedStack:
    def _cal(self, age_s=0.0):
        return CalibrationGains(
            gains={"red": 0.005, "nir": 0.0025}, measured_at=time.time() - age_s
        )

    def test_a_fresh_calibration_is_applied(self):
        out, ok = calibrated_stack(stack(100.0, 200.0), self._cal())
        assert ok is True
        assert out.band("red").mean() == pytest.approx(0.5)

    def test_a_stale_calibration_is_refused(self):
        """Light changes. A morning panel does not describe an afternoon flight."""
        _, ok = calibrated_stack(stack(100.0, 200.0), self._cal(age_s=99_999))
        assert ok is False

    def test_no_calibration_means_not_calibrated(self):
        s = stack(100.0, 200.0)
        out, ok = calibrated_stack(s, None)
        assert ok is False and out is s

    def test_a_partial_calibration_yields_raw_rather_than_half_corrected(self):
        cal = CalibrationGains(gains={"thermal": 1.0}, measured_at=time.time())
        _, ok = calibrated_stack(stack(100.0, 200.0), cal)
        assert ok is False

    def test_this_is_what_lets_an_index_claim_calibration(self):
        """The point of the whole module: NDVI that two dates can be compared."""
        raw = stack(100.0, 200.0)
        cal_stack, ok = calibrated_stack(raw, self._cal())
        assert ndvi(raw).calibrated is False
        assert ndvi(cal_stack, calibrated=ok).calibrated is True

    def test_calibration_changes_ndvi_when_bands_scale_differently(self):
        """If it did not, calibration would be doing nothing."""
        raw = stack(100.0, 200.0)
        cal_stack, _ = calibrated_stack(raw, self._cal())
        assert ndvi(raw).array.mean() != pytest.approx(ndvi(cal_stack).array.mean())


class TestDrift:
    def test_drift_reports_relative_change(self):
        before = CalibrationGains(gains={"red": 0.005})
        after = CalibrationGains(gains={"red": 0.0065})
        assert panel_drift(before, after)["red"] == pytest.approx(0.3)

    def test_no_drift_between_identical_panels(self):
        cal = CalibrationGains(gains={"red": 0.005})
        assert panel_drift(cal, cal)["red"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# NTRIP
# ---------------------------------------------------------------------------


class _Sink:
    """Stands in for the serial port to the GNSS receiver."""

    def __init__(self):
        self.data = b""

    def write(self, b):
        self.data += b

    def close(self):
        pass


def _caster(response: bytes, body: bytes = b"", delay=0.0):
    """A minimal NTRIP caster. Returns (host, port, captured_request)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    captured = {}

    def serve():
        conn, _ = srv.accept()
        captured["request"] = conn.recv(4096)
        if delay:
            time.sleep(delay)
        conn.sendall(response + body)
        conn.close()
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[0], srv.getsockname()[1], captured


def _cfg(host, port, **kw):
    base = dict(host=host, port=port, mountpoint="MP", username="u",
                password="p", sink="/dev/null")
    base.update(kw)
    return NtripConfig(**base)


class TestNtripSafety:
    def test_the_client_has_no_mavlink_surface(self):
        """The corrections go to the RECEIVER, not the autopilot.

        Injecting RTCM as MAVLink GPS_RTCM_DATA is the standard shortcut and is
        deliberately not taken: `MavlinkTelemetry` is read-only by construction,
        and adding a write path "just for corrections" gives the next thing that
        wants to transmit a precedent. The contract is worth more than the
        convenience.
        """
        for forbidden in ("mav", "mavlink", "send_rtcm", "inject", "gps_rtcm_data"):
            assert not hasattr(NtripClient, forbidden), forbidden

    def test_the_sink_is_a_serial_device_not_a_flight_controller(self):
        assert "sink" in NtripConfig.__dataclass_fields__
        assert "receiver" in NtripClient.__doc__.lower()


class TestNtripProtocol:
    def test_request_carries_basic_auth_and_the_mountpoint(self):
        req = build_request(_cfg("h", 2101)).decode()
        assert "GET /MP HTTP/1.0" in req
        assert "Authorization: Basic dTpw" in req      # base64 of "u:p"
        assert "Ntrip-Version: Ntrip/1.0" in req       # or some casters send a source table

    @pytest.mark.parametrize("resp,match", [
        (b"HTTP/1.1 401 Unauthorized", "credentials"),
        (b"HTTP/1.1 404 Not Found", "mountpoint"),
        (b"SOURCETABLE 200 OK", "SOURCE TABLE"),
    ])
    def test_refusals_say_what_to_fix(self, resp, match):
        with pytest.raises(RuntimeError, match=match):
            check_response(resp)

    @pytest.mark.parametrize("ok", [b"HTTP/1.1 200 OK", b"ICY 200 OK"])
    def test_both_success_forms_are_accepted(self, ok):
        check_response(ok)      # must not raise

    def test_credentials_must_come_from_the_environment(self):
        with pytest.raises(ValueError, match="NTRIP_USERNAME"):
            NtripClient(NtripConfig(host="h", mountpoint="m", sink="/dev/x"))

    def test_from_env_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("NTRIP_USERNAME", "alice")
        monkeypatch.setenv("NTRIP_PASSWORD", "s3cret")
        cfg = NtripConfig.from_env("caster.example", "MP", "/dev/serial0")
        assert cfg.username == "alice" and cfg.missing() == []


class TestNtripStreaming:
    def test_rtcm_reaches_the_sink(self):
        host, port, _ = _caster(b"ICY 200 OK\r\n\r\n", b"\xd3\x00\x13RTCMPAYLOAD")
        sink = _Sink()
        client = NtripClient(_cfg(host, port), sink_factory=lambda: sink)
        assert client.stream_once() == len(b"\xd3\x00\x13RTCMPAYLOAD")
        assert sink.data.startswith(b"\xd3")

    def test_bytes_sharing_the_header_packet_are_not_lost(self):
        """The header and the first RTCM often arrive together. Reading a fixed
        block and discarding it would silently drop the start of the stream."""
        host, port, _ = _caster(b"ICY 200 OK\r\n\r\n\xd3\x00\x04HEAD")
        sink = _Sink()
        NtripClient(_cfg(host, port), sink_factory=lambda: sink).stream_once()
        assert sink.data == b"\xd3\x00\x04HEAD"

    def test_a_rejected_stream_raises_rather_than_writing_garbage(self):
        host, port, _ = _caster(b"HTTP/1.1 401 Unauthorized\r\n\r\ndenied")
        sink = _Sink()
        with pytest.raises(RuntimeError, match="credentials"):
            NtripClient(_cfg(host, port), sink_factory=lambda: sink).stream_once()
        assert sink.data == b""

    def test_the_request_actually_reaches_the_caster(self):
        host, port, captured = _caster(b"ICY 200 OK\r\n\r\nx")
        NtripClient(_cfg(host, port), sink_factory=_Sink).stream_once()
        time.sleep(0.05)
        assert b"GET /MP" in captured["request"]


class TestNtripStaleness:
    def test_an_open_socket_with_no_data_counts_as_stale(self):
        """The failure that looks like success -- same trap as stale MAVLink."""
        s = NtripStats(connected=True, last_data_at=time.time() - 120)
        assert s.is_stale(30.0) is True

    def test_fresh_data_is_not_stale(self):
        assert NtripStats(connected=True, last_data_at=time.time()).is_stale(30.0) is False

    def test_never_having_received_anything_is_stale(self):
        assert NtripStats(connected=True).is_stale(30.0) is True
