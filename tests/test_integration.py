"""End-to-end integration: a real ONNX model driven through the real Pipeline.

Every other test exercises one layer. This one runs the whole stack -- camera,
telemetry gate, QA, ONNX inference, YOLOX decode, priority spooling, provenance
sidecar -- and asserts the pieces actually fit together.

Skips cleanly when no exported model is present, so the suite still passes on a
fresh clone or on the Pi before a model has been copied over.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from agri_edge.config import Config, QAConfig
from agri_edge.pipeline.runner import Pipeline
from agri_edge.store.spool import Priority, Spool
from agri_edge.telemetry.mavlink_link import SimulatedTelemetry

REPO = Path(__file__).resolve().parents[1]
MODEL_CANDIDATES = [
    REPO / "models" / "weed_crop_yolox_s.onnx",
    REPO / "models" / "yolox_s_coco.onnx",
]
MODEL = next((p for p in MODEL_CANDIDATES if p.exists()), None)

pytestmark = pytest.mark.skipif(
    MODEL is None,
    reason="no exported ONNX model (run training/export_onnx.py)",
)


class RealImageCamera:
    """Feeds real dataset images through the pipeline.

    Synthetic frames would exercise the plumbing but tell you nothing about
    whether the decode produces sane boxes on real pixels.
    """

    def __init__(self, paths, bands=("red", "green", "blue")):
        from PIL import Image

        self.images = [np.array(Image.open(p).convert("RGB")) for p in paths]
        self.bands = list(bands)
        self._seq = 0

    def start(self):
        pass

    def stop(self):
        pass

    def capture(self, telem):
        import time

        from agri_edge.capture.camera import Frame

        img = self.images[self._seq % len(self.images)]
        self._seq += 1
        return Frame(
            image=img, telemetry=telem, captured_at=time.time(),
            sequence=self._seq, bands=list(self.bands),
        )


def sample_images(n=3):
    d = REPO / "data" / "weed-crop-aerial" / "test" / "images"
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.suffix.lower() == ".jpg")[:n]


def build_config(tmp_path, **inference_overrides) -> Config:
    cfg = Config()
    cfg.site = "integration-test"
    cfg.field_id = "plot-it"
    cfg.spool.spool_dir = tmp_path / "spool"
    cfg.capture.interval_s = 0.0
    cfg.qa = QAConfig(blur_threshold=1.0, required_bands=[])
    cfg.inference.enabled = True
    cfg.inference.backend = "onnx"
    cfg.inference.model_path = MODEL
    cfg.inference.confidence_threshold = 0.30
    cfg.inference.class_names = ["crop", "weed"] if "weed_crop" in MODEL.name else []
    for k, v in inference_overrides.items():
        setattr(cfg.inference, k, v)
    return cfg


@pytest.fixture
def images():
    paths = sample_images()
    if not paths:
        pytest.skip("dataset not downloaded (run training/download_data.py)")
    return paths


class TestEndToEnd:
    def test_full_pipeline_runs_and_spools(self, tmp_path, images):
        cfg = build_config(tmp_path)
        spool = Spool(cfg.spool.spool_dir)
        from agri_edge.inference.engine import build_engine

        pipeline = Pipeline(
            cfg, RealImageCamera(images), SimulatedTelemetry(), spool, build_engine(cfg.inference)
        )
        stats = pipeline.run(max_frames=len(images))

        assert stats.captured == len(images)
        assert stats.spooled == len(images)
        assert stats.skipped_no_telemetry == 0
        assert len(spool.pending()) == len(images)

    def test_sidecar_carries_full_provenance(self, tmp_path, images):
        cfg = build_config(tmp_path)
        spool = Spool(cfg.spool.spool_dir)
        from agri_edge.inference.engine import build_engine

        Pipeline(
            cfg, RealImageCamera(images), SimulatedTelemetry(), spool, build_engine(cfg.inference)
        ).run(max_frames=1)

        entry = spool.pending()[0]
        meta = json.loads((spool.dir / entry.meta_path).read_text(encoding="utf-8"))

        assert meta["schema"] == "agri-edge/frame/1"
        assert meta["site"] == "integration-test"
        assert meta["crs"] == "EPSG:4326"
        assert meta["telemetry"]["fix_name"] == "rtk-fixed"
        assert meta["qa"]["severity"] in {"ok", "warn", "fail"}
        assert meta["model"] is not None
        assert "detections" in meta

    def test_unvalidated_model_never_authorises_treatment(self, tmp_path, images):
        """The safety contract, end to end through the real stack."""
        cfg = build_config(tmp_path)
        spool = Spool(cfg.spool.spool_dir)
        from agri_edge.inference.engine import build_engine

        engine = build_engine(cfg.inference)
        assert engine.metadata.validated_locally is False

        Pipeline(cfg, RealImageCamera(images), SimulatedTelemetry(), spool, engine).run(
            max_frames=len(images)
        )

        for entry in spool.pending():
            meta = json.loads((spool.dir / entry.meta_path).read_text(encoding="utf-8"))
            assert meta["decision_support_only"] is True
            assert meta["model"]["validated_locally"] is False
            for det in meta["detections"]:
                assert det["may_drive_treatment"] is False

    def test_detections_have_sane_geometry(self, tmp_path, images):
        """Boxes must be normalised, ordered, and inside the frame."""
        cfg = build_config(tmp_path)
        from agri_edge.inference.engine import build_engine

        engine = build_engine(cfg.inference)
        from PIL import Image

        img = np.array(Image.open(images[0]).convert("RGB"))
        for det in engine.infer(img):
            x1, y1, x2, y2 = det.bbox
            assert 0.0 <= x1 <= 1.0 and 0.0 <= y1 <= 1.0
            assert 0.0 <= x2 <= 1.0 and 0.0 <= y2 <= 1.0
            assert x2 > x1 and y2 > y1, "degenerate or inverted box"
            assert 0.0 <= det.confidence <= 1.0

    def test_detections_raise_spool_priority(self, tmp_path, images):
        """A frame with findings should upload before an empty one."""
        cfg = build_config(tmp_path)
        spool = Spool(cfg.spool.spool_dir)
        from agri_edge.inference.engine import build_engine

        pipeline = Pipeline(
            cfg, RealImageCamera(images), SimulatedTelemetry(), spool, build_engine(cfg.inference)
        )
        pipeline.run(max_frames=len(images))

        priorities = {e.priority for e in spool.pending()}
        assert priorities <= {int(Priority.ANOMALY), int(Priority.NORMAL), int(Priority.DEGRADED)}
        if pipeline.stats.detections:
            assert int(Priority.ANOMALY) in priorities

    def test_spooled_image_is_lossless(self, tmp_path, images):
        cfg = build_config(tmp_path)
        spool = Spool(cfg.spool.spool_dir)
        from agri_edge.inference.engine import build_engine
        from PIL import Image

        Pipeline(
            cfg, RealImageCamera(images), SimulatedTelemetry(), spool, build_engine(cfg.inference)
        ).run(max_frames=1)

        entry = spool.pending()[0]
        restored = np.load(spool.dir / entry.image_path)
        original = np.array(Image.open(images[0]).convert("RGB"))
        np.testing.assert_array_equal(restored, original)


class TestTiledIntegration:
    def test_tiled_engine_runs_through_the_pipeline(self, tmp_path, images):
        from agri_edge.inference.engine import build_engine
        from agri_edge.inference.tiling import TiledEngine

        cfg = build_config(tmp_path, tiled=True, tile_size=320, tile_overlap=0.2)
        engine = build_engine(cfg.inference)
        assert isinstance(engine, TiledEngine)

        spool = Spool(cfg.spool.spool_dir)
        stats = Pipeline(
            cfg, RealImageCamera(images), SimulatedTelemetry(), spool, engine
        ).run(max_frames=1)
        assert stats.spooled == 1

    def test_tiling_finds_at_least_as_much_at_native_scale(self, tmp_path, images):
        """Tiling a 640x640 frame at 320 should not lose detections.

        Each tile is upscaled to the 640 network input, so small objects get
        *more* pixels, never fewer.
        """
        from PIL import Image

        from agri_edge.inference.engine import build_engine

        plain = build_engine(build_config(tmp_path).inference)
        tiled = build_engine(
            build_config(tmp_path, tiled=True, tile_size=320, tile_overlap=0.25).inference
        )

        img = np.array(Image.open(images[0]).convert("RGB"))
        n_plain = len(plain.infer(img))
        n_tiled = len(tiled.infer(img))
        assert n_tiled >= n_plain, f"tiling lost detections: {n_tiled} < {n_plain}"
