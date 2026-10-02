"""AgOpenGPS read-only adapter: PGN parser + UDP listener.

Packets are SIMULATED (constructed from PGN.md's field list, tests/fixtures/make_agopengps_samples.py);
the byte layout is partly UNVERIFIED. These tests prove OUR parser/gating behave, not that the
layout matches a real AgOpenGPS.
"""
from __future__ import annotations

import ast
import json
import math
import random
import socket
import struct
import sys
import time
from pathlib import Path

import pytest

from agri_edge.adapters import (
    AgOpenGpsReadOnlyAdapter,
    AgOpenGpsUdpListener,
    GuidanceAdapter,
    GuidanceCommandRefused,
    GuidanceTrack,
    PgnParseError,
)
from agri_edge.adapters import agopengps_pgn as P

FIX = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIX))
import make_agopengps_samples as mk  # noqa: E402

SAMPLES = {k: bytes.fromhex(v) for k, v in
           json.loads((FIX / "agopengps_samples.json").read_text())["packets"].items()}
ADAPTERS_DIR = Path(P.__file__).parent


def test_fixture_file_matches_the_generator_and_is_labelled_simulated():
    doc = json.loads((FIX / "agopengps_samples.json").read_text())
    assert doc["provenance"].startswith("SIMULATED")
    assert SAMPLES == mk.SAMPLES


def test_crc_is_sum_of_bytes_2_to_n_minus_2():
    f = SAMPLES["from_imu"]
    assert f[-1] == sum(f[2:-1]) & 0xFF == P.crc(f)


def test_gps_main_antenna_decodes():
    frame, g = P.parse(SAMPLES["gps_rtk_fix"])
    assert (frame.src, frame.pgn, len(frame.data)) == (0x7C, 214, 51)
    assert g.longitude_deg == -97.1384 and g.latitude_deg == 49.8951
    assert g.heading_true_deg == pytest.approx(91.5) and g.altitude_m == pytest.approx(238.4, abs=1e-3)
    assert (g.satellites, g.fix_quality) == (18, 4)
    assert g.hdop == pytest.approx(0.85) and g.age_s == pytest.approx(1.2)
    assert g.simulated is True


def test_other_pgns_decode():
    assert P.parse(SAMPLES["steer_data"])[1] == P.SteerDataObserved(
        speed_raw=75, status=1, steer_angle_raw=-1234, xte_raw=130, sections_mask=0b0000_0010_0000_0101)
    a = P.parse(SAMPLES["from_autosteer"])[1]
    assert a.steer_angle_deg == pytest.approx(-12.34) and (a.switch, a.pwm_display) == (1, 77)
    i = P.parse(SAMPLES["from_imu"])[1]
    assert (i.heading_raw, i.roll_raw, i.gyro_raw) == (1800, -25, 7)
    m = P.parse(SAMPLES["machine"])[1]
    assert m.speed_x10 == 52 and m.sections_mask == 0x00FF


def test_valid_but_unmodelled_pgn_is_a_frame_without_typed_state():
    frame, dec = P.parse(SAMPLES["hello_unmodelled"])
    assert frame.pgn == 200 and dec is None


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_every_single_byte_corruption_is_rejected_or_changes_nothing_silently(name):
    good = SAMPLES[name]
    for i in range(len(good)):
        bad = bytearray(good)
        bad[i] ^= 0x5A
        try:
            P.parse(bytes(bad))
        except PgnParseError:
            continue
        pytest.fail(f"{name}: corruption at byte {i} was accepted")


@pytest.mark.parametrize("raw", [b"", b"\x80", b"\x80\x81\x7c\xd6", b"\x00" * 20,
                                 SAMPLES["gps_rtk_fix"][:-1], SAMPLES["gps_rtk_fix"] + b"\x00"])
def test_malformed_frames_are_rejected(raw):
    with pytest.raises(PgnParseError):
        P.parse(raw)


def test_wrong_length_for_a_known_pgn_is_rejected_even_with_a_valid_crc():
    with pytest.raises(PgnParseError, match="must carry 51"):
        P.parse(mk.frame(0x7C, 214, b"\x00" * 10))


def test_non_finite_and_out_of_range_gps_are_rejected():
    for lon, lat in ((float("nan"), 49.0), (float("inf"), 49.0), (0.0, 91.0), (181.0, 0.0)):
        with pytest.raises(PgnParseError):
            P.parse(mk.gps(lon, lat, 0, 0, 0, 0, 0, 5, 1, 100, 0))


def test_non_bytes_input_is_rejected():
    with pytest.raises(PgnParseError):
        P.parse("80817c")        # type: ignore[arg-type]


def test_fuzz_never_raises_anything_but_pgnparseerror():
    rng = random.Random(7)
    for _ in range(3000):
        n = rng.randrange(0, 70)
        raw = bytes(rng.randrange(256) for _ in range(n))
        if rng.random() < 0.5 and n > 5:
            raw = b"\x80\x81" + raw[2:]
        try:
            P.parse(raw)
        except PgnParseError:
            pass


# ---- listener ---------------------------------------------------------------------
def test_feed_keeps_latest_per_pgn_and_counts_rejects():
    t = [100.0]
    ln = AgOpenGpsUdpListener(now_fn=lambda: t[0])
    assert ln.feed(SAMPLES["gps_rtk_fix"]) and ln.feed(SAMPLES["from_imu"])
    assert not ln.feed(b"junk") and not ln.feed(b"\x00" * 600)
    assert ln.feed(SAMPLES["hello_unmodelled"])
    o = ln.observed()
    assert o.gps.fix_quality == 4 and o.imu.heading_raw == 1800 and o.steer_data is None
    assert (o.frames_ok, o.frames_rejected, o.frames_unmodelled) == (3, 2, 1)
    t[0] = 101.5
    assert ln.age_s() == pytest.approx(1.5)


def test_udp_loopback_roundtrip():
    ln = AgOpenGpsUdpListener(port=0)
    port = ln.start()
    try:
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tx.sendto(b"not a frame", ("127.0.0.1", port))
        tx.sendto(SAMPLES["gps_rtk_fix"], ("127.0.0.1", port))
        tx.sendto(SAMPLES["steer_data"], ("127.0.0.1", port))
        tx.close()
        deadline = time.time() + 3
        while time.time() < deadline and ln.observed().frames_ok < 2:
            time.sleep(0.02)
        o = ln.observed()
        assert o.gps.satellites == 18 and o.steer_data.steer_angle_raw == -1234
        assert o.frames_rejected == 1
    finally:
        ln.stop()


def test_listener_binds_loopback_by_default():
    assert AgOpenGpsUdpListener().bind == "127.0.0.1"


# ---- adapter -----------------------------------------------------------------------
def test_adapter_satisfies_the_guidance_interface_and_does_not_open_a_socket_by_default(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("opened a socket without allow_network=True")
    monkeypatch.setattr(socket, "socket", boom)
    a = AgOpenGpsReadOnlyAdapter()
    assert isinstance(a, GuidanceAdapter) and a.simulated is True
    assert a.connect() is False
    s = a.get_state()
    assert (s.connected, s.engaged, s.cross_track_error_m, s.source) == (False, False, None, "none")
    a.close()


def test_state_goes_stale_and_engaged_is_never_true():
    t = [0.0]
    a = AgOpenGpsReadOnlyAdapter(listener=AgOpenGpsUdpListener(now_fn=lambda: t[0]), stale_after_s=2.0)
    t[0] = 50.0
    a.listener.feed(SAMPLES["steer_data"])         # status byte says "1" -- still not engaged by us
    s = a.get_state()
    assert s.connected and s.engaged is False and s.source == "agopengps_udp"
    assert a.observed().steer_data.status == 1
    t[0] = 53.0
    assert a.get_state().connected is False
    assert a.get_state().cross_track_error_m is None       # xte scale unverified -> not invented


def test_adapter_connect_with_opt_in_receives_over_loopback():
    a = AgOpenGpsReadOnlyAdapter(allow_network=True, port=0)
    assert a.connect() is True
    try:
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tx.sendto(SAMPLES["gps_rtk_fix"], ("127.0.0.1", a.listener.port))
        tx.close()
        deadline = time.time() + 3
        while time.time() < deadline and not a.get_state().connected:
            time.sleep(0.02)
        assert a.get_state().connected and a.observed().gps.latitude_deg == 49.8951
    finally:
        a.close()


@pytest.mark.parametrize("call", [
    lambda a: a.engage(), lambda a: a.set_steer_angle(5.0), lambda a: a.set_speed(3.0),
    lambda a: a.command_steer(angle=1), lambda a: a.send_pgn(b"x"), lambda a: a.set_section(1, True),
    lambda a: a.write(b"x"), lambda a: a.disengage(),
])
def test_every_command_shaped_call_is_refused(call):
    a = AgOpenGpsReadOnlyAdapter(allow_network=True)
    with pytest.raises(GuidanceCommandRefused):
        call(a)
    assert a.get_state().engaged is False


def test_track_loading_is_memory_only():
    a = AgOpenGpsReadOnlyAdapter()
    ok = a.load_track(GuidanceTrack("t1", ((49.0, -97.0), (49.001, -97.0))))
    assert ok["ok"] and "cannot transmit" in ok["note"]
    assert not a.load_track(GuidanceTrack("t2", ((49.0, -97.0),)))["ok"]


def _names(path: Path) -> tuple[set[str], set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods.add(n.module.split(".")[0])
    return attrs, mods


def test_no_transmit_primitive_exists_anywhere_in_the_agopengps_modules():
    for name in ("agopengps_udp.py", "agopengps_pgn.py"):
        attrs, _ = _names(ADAPTERS_DIR / name)
        assert not attrs & {"send", "sendto", "sendall", "connect", "connect_ex", "setsockopt",
                            "SO_BROADCAST"}, (name, attrs & {"send", "sendto", "sendall", "connect"})


def test_parser_is_pure_no_io_modules():
    _, mods = _names(ADAPTERS_DIR / "agopengps_pgn.py")
    assert not mods & {"socket", "threading", "os", "subprocess", "urllib", "http", "serial", "paho"}


def test_guidance_commands_never_import_vehicle_or_mqtt_paths():
    _, mods = _names(ADAPTERS_DIR / "agopengps_udp.py")
    assert not mods & {"pymavlink", "paho", "serial", "subprocess", "urllib", "http"}
    assert math.isfinite(1.0) and struct.calcsize("<ddfffffHBHHHhhh") == 51
