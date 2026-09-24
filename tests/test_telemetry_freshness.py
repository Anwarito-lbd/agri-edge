"""A position that stopped updating does not pass as a current one.

Finding F7 of docs/audit-2026-09-24.md: every MAVLink message type bumped the
snapshot's `timestamp`, including SYS_STATUS (battery) and VFR_HUD (airspeed).
If GLOBAL_POSITION_INT stopped -- an EKF reset, a stream-rate misconfiguration,
a GNSS dropout the autopilot handles by withholding position -- battery
messages kept the snapshot "fresh", the stale-telemetry gate passed, and every
frame was georeferenced at the last known position.
"""

from __future__ import annotations

import time
from dataclasses import replace

from agri_edge.config import Config
from agri_edge.pipeline.runner import Pipeline
from agri_edge.store.spool import Spool
from agri_edge.telemetry.mavlink_link import MavlinkTelemetry, TelemetrySnapshot

POSITION = {"lat": 504452000, "lon": -1046189000, "alt": 600000, "relative_alt": 100000, "hdg": 9000}
ATTITUDE = {"roll": 0.0, "pitch": 0.0, "yaw": 1.57}


def _link() -> MavlinkTelemetry:
    return MavlinkTelemetry("udpin:127.0.0.1:0")


def test_battery_and_airspeed_do_not_refresh_the_position(monkeypatch):
    link = _link()
    clock = [1000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    link._ingest("GLOBAL_POSITION_INT", POSITION)
    clock[0] = 1010.0
    link._ingest("SYS_STATUS", {"battery_remaining": 80})
    link._ingest("VFR_HUD", {"groundspeed": 9.0})
    link._ingest("GPS_RAW_INT", {"fix_type": 3, "satellites_visible": 12, "eph": 80})
    snap = link.snapshot()
    assert snap.age_s(now=1010.0) == 10.0
    assert snap.link_timestamp == 1010.0
    assert snap.battery_pct == 80.0


def test_attitude_is_tracked_separately(monkeypatch):
    link = _link()
    clock = [2000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    link._ingest("GLOBAL_POSITION_INT", POSITION)
    assert link.snapshot().attitude_age_s(now=2000.0) is None
    link._ingest("ATTITUDE", ATTITUDE)
    clock[0] = 2005.0
    link._ingest("GLOBAL_POSITION_INT", POSITION)
    snap = link.snapshot()
    assert snap.age_s(now=2005.0) == 0.0
    assert snap.attitude_age_s(now=2005.0) == 5.0


class _FixedTelemetry:
    def __init__(self, snap: TelemetrySnapshot):
        self.snap = snap

    def start(self):
        pass

    def stop(self):
        pass

    def snapshot(self):
        return self.snap


class _NoCamera:
    def capture(self, telem):  # pragma: no cover - must not be reached
        raise AssertionError("captured despite stale telemetry")


def _pipeline(snap: TelemetrySnapshot, tmp_path) -> Pipeline:
    return Pipeline(Config(), camera=_NoCamera(), telemetry=_FixedTelemetry(snap),
                    spool=Spool(tmp_path))


def _fresh(now: float) -> TelemetrySnapshot:
    return TelemetrySnapshot(
        timestamp=now, lat=50.0, lon=-104.0, alt_rel_m=100.0, fix_type=3,
        roll_deg=0.0, pitch_deg=0.0, yaw_deg=90.0,
        attitude_timestamp=now, link_timestamp=now,
    )


def test_pipeline_skips_a_frozen_position_even_with_a_live_link(tmp_path):
    now = time.time()
    snap = replace(_fresh(now), timestamp=now - 30.0)
    pipe = _pipeline(snap, tmp_path)
    assert pipe.process_once() is None
    assert pipe.stats.skipped_no_telemetry == 1


def test_pipeline_skips_a_frozen_attitude(tmp_path):
    now = time.time()
    snap = replace(_fresh(now), attitude_timestamp=now - 30.0)
    pipe = _pipeline(snap, tmp_path)
    assert pipe.process_once() is None
    assert pipe.stats.skipped_no_telemetry == 1
