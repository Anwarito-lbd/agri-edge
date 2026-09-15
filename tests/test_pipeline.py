"""Pipeline, spool and safety-contract tests."""

import time

import numpy as np
import pytest

from agri_edge.capture.camera import SimulatedCamera
from agri_edge.config import Config, QAConfig
from agri_edge.inference.engine import Detection, ModelMetadata, SimulatedEngine
from agri_edge.pipeline.runner import Pipeline
from agri_edge.store.spool import Priority, Spool
from agri_edge.telemetry.mavlink_link import (
    GPS_FIX_3D,
    GPS_FIX_RTK_FIXED,
    MavlinkTelemetry,
    SimulatedTelemetry,
    TelemetrySnapshot,
    TelemetrySource,
)


class StaleTelemetry(TelemetrySource):
    """Telemetry that is always older than any tolerance."""

    def snapshot(self):
        return TelemetrySnapshot(timestamp=time.time() - 600, lat=50.0, lon=-105.0, fix_type=GPS_FIX_3D)


class NoTelemetry(TelemetrySource):
    def snapshot(self):
        return TelemetrySnapshot()


def make_config(tmp_path, **overrides) -> Config:
    cfg = Config()
    cfg.site = "test-site"
    cfg.field_id = "field-01"
    cfg.spool.spool_dir = tmp_path / "spool"
    cfg.capture.interval_s = 0.0
    cfg.qa = QAConfig(blur_threshold=1.0)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def build(tmp_path, telemetry=None, engine=None, cfg=None, bands=None):
    cfg = cfg or make_config(tmp_path)
    bands = bands or ["red", "green", "blue", "nir", "red-edge"]
    return Pipeline(
        cfg,
        SimulatedCamera(resolution=(64, 48), bands=bands),
        telemetry or SimulatedTelemetry(),
        Spool(cfg.spool.spool_dir),
        engine,
    )


class TestSafetyContract:
    """The Pi must not be able to command the aircraft. Enforced, not documented."""

    FORBIDDEN = (
        "arm", "disarm", "set_mode", "takeoff", "land", "goto", "reboot",
        "command_long", "mission_upload", "set_position", "rc_override",
    )

    def test_telemetry_exposes_no_command_surface(self):
        for name in self.FORBIDDEN:
            assert not hasattr(MavlinkTelemetry, name), (
                f"MavlinkTelemetry gained a '{name}' method. The companion computer "
                "must not be able to command the vehicle -- see the safety contract "
                "in telemetry/mavlink_link.py."
            )

    def test_telemetry_source_interface_is_read_only(self):
        public = {m for m in dir(TelemetrySource) if not m.startswith("_")}
        assert public == {"start", "stop", "snapshot"}

    def test_snapshot_is_immutable(self):
        """Provenance that can be edited after capture is not provenance."""
        snap = SimulatedTelemetry().snapshot()
        with pytest.raises(Exception):
            snap.lat = 0.0


class TestTelemetryIngest:
    """Verify MAVLink decoding without needing a vehicle."""

    def test_global_position_int_decoded(self):
        link = MavlinkTelemetry("udpin:127.0.0.1:1")
        link._ingest(
            "GLOBAL_POSITION_INT",
            {"lat": 504452000, "lon": -1046189000, "alt": 550000, "relative_alt": 100000, "hdg": 9000},
        )
        s = link.snapshot()
        assert s.lat == pytest.approx(50.4452)
        assert s.lon == pytest.approx(-104.6189)
        assert s.alt_rel_m == pytest.approx(100.0)
        assert s.yaw_deg == pytest.approx(90.0)

    def test_unknown_heading_does_not_overwrite(self):
        link = MavlinkTelemetry("udpin:127.0.0.1:1")
        link._ingest("ATTITUDE", {"roll": 0.0, "pitch": 0.0, "yaw": 1.0})
        before = link.snapshot().yaw_deg
        link._ingest(
            "GLOBAL_POSITION_INT",
            {"lat": 0, "lon": 0, "alt": 0, "relative_alt": 0, "hdg": 65535},
        )
        assert link.snapshot().yaw_deg == before

    def test_gps_raw_int_decoded(self):
        link = MavlinkTelemetry("udpin:127.0.0.1:1")
        link._ingest("GPS_RAW_INT", {"fix_type": 6, "satellites_visible": 20, "eph": 70})
        s = link.snapshot()
        assert s.is_rtk_fixed
        assert s.fix_name == "rtk-fixed"
        assert s.hdop == pytest.approx(0.7)

    def test_negative_battery_remaining_ignored(self):
        link = MavlinkTelemetry("udpin:127.0.0.1:1")
        link._ingest("SYS_STATUS", {"battery_remaining": -1})
        assert link.snapshot().battery_pct is None

    def test_has_position_requires_3d_fix(self):
        assert not TelemetrySnapshot(lat=1.0, lon=1.0, fix_type=2).has_position
        assert TelemetrySnapshot(lat=1.0, lon=1.0, fix_type=GPS_FIX_3D).has_position


class TestCaptureGating:
    def test_stale_telemetry_is_skipped(self, tmp_path):
        p = build(tmp_path, telemetry=StaleTelemetry())
        assert p.process_once() is None
        assert p.stats.skipped_no_telemetry == 1
        assert p.stats.captured == 0

    def test_absent_telemetry_is_skipped(self, tmp_path):
        p = build(tmp_path, telemetry=NoTelemetry())
        assert p.process_once() is None
        assert p.stats.skipped_no_telemetry == 1

    def test_good_telemetry_captures(self, tmp_path):
        p = build(tmp_path)
        meta = p.process_once()
        assert meta is not None
        assert p.stats.captured == 1
        assert meta["telemetry"]["fix_name"] == "rtk-fixed"


class TestMetadata:
    def test_provenance_fields_present(self, tmp_path):
        meta = build(tmp_path).process_once()
        for key in ("schema", "site", "field_id", "sequence", "captured_at",
                    "bands", "image_shape", "crs", "telemetry", "qa", "indices"):
            assert key in meta, f"missing provenance field: {key}"
        assert meta["crs"] == "EPSG:4326"

    def test_indices_computed_for_multispectral_payload(self, tmp_path):
        meta = build(tmp_path).process_once()
        assert {"ndvi", "ndre", "gndvi", "savi"} <= set(meta["indices"])

    def test_indices_marked_uncalibrated(self, tmp_path):
        """Digital numbers must never be presented as reflectance."""
        meta = build(tmp_path).process_once()
        assert all(v["calibrated"] is False for v in meta["indices"].values())

    def test_rgb_payload_gets_only_exg(self, tmp_path):
        meta = build(tmp_path, bands=["red", "green", "blue"]).process_once()
        assert set(meta["indices"]) == {"excess_green"}

    def test_no_model_recorded_when_inference_disabled(self, tmp_path):
        assert build(tmp_path).process_once()["model"] is None


class TestInferenceGating:
    def test_detections_recorded(self, tmp_path):
        p = build(tmp_path, engine=SimulatedEngine())
        meta = p.process_once()
        assert len(meta["detections"]) >= 1
        assert p.stats.detections >= 1

    def test_unvalidated_model_cannot_drive_treatment(self, tmp_path):
        """The central safety rule: a model is a sensor until locally validated."""
        meta = build(tmp_path, engine=SimulatedEngine()).process_once()
        assert meta["decision_support_only"] is True
        for d in meta["detections"]:
            assert d["validated_locally"] is False
            assert d["may_drive_treatment"] is False

    def test_validated_model_may_drive_treatment(self, tmp_path):
        engine = SimulatedEngine()
        engine.metadata = ModelMetadata(
            name="canola-weed", version="1.2.0", validated_locally=True,
            validation_notes="Validated against 2026 SK ground truth.",
        )
        meta = build(tmp_path, engine=engine).process_once()
        assert meta["model"]["validated_locally"] is True
        assert all(d["may_drive_treatment"] for d in meta["detections"])
        assert meta["decision_support_only"] is False

    def test_no_inference_on_qa_failed_frames(self, tmp_path):
        """Confident nonsense from a blurred frame is worse than no output."""
        cfg = make_config(tmp_path)
        cfg.qa = QAConfig(blur_threshold=1e12)  # force failure
        p = build(tmp_path, engine=SimulatedEngine(), cfg=cfg)
        meta = p.process_once()
        assert meta["qa"]["severity"] == "fail"
        assert meta["detections"] == []
        assert p.stats.detections == 0

    def test_low_confidence_detections_dropped(self, tmp_path):
        cfg = make_config(tmp_path)
        cfg.inference.confidence_threshold = 1.1  # nothing can pass
        meta = build(tmp_path, engine=SimulatedEngine(), cfg=cfg).process_once()
        assert meta["detections"] == []

    def test_detection_flag_defaults_closed(self):
        assert Detection("weed", 0.9, (0, 0, 1, 1)).may_drive_treatment is False


class TestPriority:
    def test_clean_frame_is_normal(self, tmp_path):
        assert build(tmp_path).process_once()["priority"] == int(Priority.NORMAL)

    def test_detection_raises_to_anomaly(self, tmp_path):
        meta = build(tmp_path, engine=SimulatedEngine()).process_once()
        assert meta["priority"] == int(Priority.ANOMALY)

    def test_qa_failure_is_degraded_not_discarded(self, tmp_path):
        """Failed frames are kept. Discarding data is an agronomist's call."""
        cfg = make_config(tmp_path)
        cfg.qa = QAConfig(blur_threshold=1e12)
        p = build(tmp_path, cfg=cfg)
        meta = p.process_once()
        assert meta["priority"] == int(Priority.DEGRADED)
        assert p.stats.spooled == 1
        assert len(p.spool.pending()) == 1


class TestRunLoop:
    def test_runs_for_a_frame_budget(self, tmp_path):
        p = build(tmp_path)
        stats = p.run(max_frames=5)
        assert stats.captured == 5
        assert stats.spooled == 5

    def test_qa_failures_are_tallied_by_check(self, tmp_path):
        cfg = make_config(tmp_path)
        cfg.qa = QAConfig(blur_threshold=1e12)
        stats = build(tmp_path, cfg=cfg).run(max_frames=3)
        assert stats.failed_qa == 3
        assert stats.qa_failure_counts["blur"] == 3

    def test_a_failing_frame_does_not_end_the_flight(self, tmp_path, monkeypatch):
        """One bad frame must never stop data collection mid-flight."""
        p = build(tmp_path)
        calls = {"n": 0}
        original = p.camera.capture

        def flaky(telem):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("simulated sensor glitch")
            return original(telem)

        monkeypatch.setattr(p.camera, "capture", flaky)
        p.run(max_frames=3)
        # Three captures attempted, one raised, the loop kept going.
        assert calls["n"] >= 3
        assert p.stats.spooled >= 2

    def test_duration_bound_terminates(self, tmp_path):
        p = build(tmp_path)
        start = time.time()
        p.run(duration_s=0.2)
        assert time.time() - start < 5.0


class TestSpool:
    def test_roundtrip(self, tmp_path):
        spool = Spool(tmp_path / "s")
        img = np.ones((8, 8, 3), dtype=np.uint8)
        entry = spool.add(img, {"k": "v"}, Priority.NORMAL, "site", "field", 1)
        pending = spool.pending()
        assert len(pending) == 1
        assert pending[0].entry_id == entry.entry_id

    def test_priority_ordering(self, tmp_path):
        spool = Spool(tmp_path / "s")
        img = np.ones((4, 4), dtype=np.uint8)
        spool.add(img, {}, Priority.DEGRADED, "s", "f", 1)
        spool.add(img, {}, Priority.NORMAL, "s", "f", 2)
        spool.add(img, {}, Priority.ANOMALY, "s", "f", 3)
        assert [e.priority for e in spool.pending()] == [0, 1, 2]

    def test_lossless_image_roundtrip(self, tmp_path):
        """Multispectral data above 8 bits must survive the spool."""
        spool = Spool(tmp_path / "s")
        img = (np.arange(48, dtype=np.uint16) * 1000).reshape(4, 4, 3)
        entry = spool.add(img, {}, Priority.NORMAL, "s", "f", 1)
        loaded = np.load(spool.dir / entry.image_path)
        assert loaded.dtype == np.uint16
        assert np.array_equal(loaded, img)

    def test_mark_uploaded_hides_from_pending(self, tmp_path):
        spool = Spool(tmp_path / "s")
        img = np.ones((4, 4), dtype=np.uint8)
        e = spool.add(img, {}, Priority.NORMAL, "s", "f", 1)
        assert spool.mark_uploaded([e.entry_id]) == 1
        assert spool.pending() == []
        assert len(spool.entries(include_uploaded=True)) == 1

    def test_marking_twice_is_idempotent(self, tmp_path):
        spool = Spool(tmp_path / "s")
        e = spool.add(np.ones((4, 4), dtype=np.uint8), {}, Priority.NORMAL, "s", "f", 1)
        spool.mark_uploaded([e.entry_id])
        assert spool.mark_uploaded([e.entry_id]) == 0

    def test_purge_keeps_the_index_record(self, tmp_path):
        """The record that a frame existed outlives the bytes."""
        spool = Spool(tmp_path / "s")
        e = spool.add(np.ones((4, 4), dtype=np.uint8), {}, Priority.NORMAL, "s", "f", 1)
        spool.mark_uploaded([e.entry_id])
        assert spool.purge_uploaded() == 2
        assert not (spool.dir / e.image_path).exists()
        assert len(spool.entries(include_uploaded=True)) == 1

    def test_truncated_index_line_is_survivable(self, tmp_path):
        """Power loss mid-write loses a frame, not the queue."""
        spool = Spool(tmp_path / "s")
        spool.add(np.ones((4, 4), dtype=np.uint8), {}, Priority.NORMAL, "s", "f", 1)
        with (spool.dir / Spool.INDEX_NAME).open("a", encoding="utf-8") as fh:
            fh.write('{"entry_id": "broken", "priorit')
        assert len(spool.pending()) == 1

    def test_quota_drops_degraded_before_anomaly(self, tmp_path):
        img = np.ones((200, 200), dtype=np.uint8)
        spool = Spool(tmp_path / "s", max_bytes=1)  # force eviction on every add
        spool.add(img, {}, Priority.ANOMALY, "s", "f", 1)
        spool.add(img, {}, Priority.DEGRADED, "s", "f", 2)
        remaining = {e.priority for e in spool.pending()}
        assert int(Priority.ANOMALY) in remaining

    def test_export_copies_payload_and_index(self, tmp_path):
        spool = Spool(tmp_path / "s")
        spool.add(np.ones((4, 4), dtype=np.uint8), {"a": 1}, Priority.NORMAL, "s", "f", 1)
        dest = tmp_path / "ssd"
        assert spool.export(dest) == 2
        assert (dest / Spool.INDEX_NAME).exists()

    def test_stats_shape(self, tmp_path):
        spool = Spool(tmp_path / "s")
        spool.add(np.ones((4, 4), dtype=np.uint8), {}, Priority.ANOMALY, "s", "f", 1)
        st = spool.stats()
        assert st["pending"] == 1
        assert st["by_priority"] == {"ANOMALY": 1}

    def test_empty_spool_is_empty_not_an_error(self, tmp_path):
        assert Spool(tmp_path / "fresh").pending() == []
