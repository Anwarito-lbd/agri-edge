"""Tests for tiled inference.

Tiling is geometry code, and geometry code fails quietly: boxes land in almost
the right place and everything downstream keeps working. So these tests pin the
coordinate mapping against hand-computed values and check the guard rails.
"""

import numpy as np
import pytest

from agri_edge.config import InferenceConfig
from agri_edge.inference.engine import Detection, InferenceEngine, ModelMetadata
from agri_edge.inference.tiling import TiledEngine, maybe_wrap_tiled, plan_tiles


class FixedDetectionEngine(InferenceEngine):
    """Returns one detection covering the middle half of whatever it is given.

    Deterministic and content-independent, so any variation in the merged output
    comes from the tiling maths rather than the detector.
    """

    def __init__(self, label="weed", confidence=0.9, validated=False):
        super().__init__(ModelMetadata(name="fixed", class_names=[label],
                                       validated_locally=validated))
        self.label = label
        self.confidence = confidence
        self.calls = 0
        self.seen_shapes: list[tuple[int, int]] = []

    def infer(self, image):
        self.calls += 1
        self.seen_shapes.append(image.shape[:2])
        return [Detection(self.label, self.confidence, (0.25, 0.25, 0.75, 0.75),
                          validated_locally=self.metadata.validated_locally)]


class FullTileEngine(InferenceEngine):
    """Returns one box covering its whole input.

    Needed to exercise cross-tile merging: a box centred *within* each tile never
    overlaps its neighbour in global coordinates, so NMS has nothing to do. A
    full-tile box does overlap wherever the tiles themselves overlap, which is
    the case the merge step exists for.
    """

    def __init__(self, label="weed"):
        super().__init__(ModelMetadata(name="fulltile", class_names=[label]))
        self.label = label
        self.calls = 0

    def infer(self, image):
        self.calls += 1
        return [Detection(self.label, 0.9, (0.0, 0.0, 1.0, 1.0), validated_locally=False)]


class SilentEngine(InferenceEngine):
    def __init__(self):
        super().__init__(ModelMetadata(name="silent"))
        self.calls = 0

    def infer(self, image):
        self.calls += 1
        return []


class TestPlanTiles:
    def test_single_tile_when_frame_fits(self):
        assert plan_tiles(640, 640, 640, 0.2) == [(0, 0, 640, 640)]

    def test_covers_the_whole_frame(self):
        """Every pixel must fall in at least one tile, or objects are missed."""
        w, h, tile = 1500, 1100, 640
        tiles = plan_tiles(w, h, tile, 0.2)
        covered = np.zeros((h, w), dtype=bool)
        for x0, y0, x1, y1 in tiles:
            covered[y0:y1, x0:x1] = True
        assert covered.all()

    def test_edges_are_flush_not_padded(self):
        """Last row/column pull back to the frame edge so no tile contains padding."""
        tiles = plan_tiles(1500, 1100, 640, 0.2)
        assert max(t[2] for t in tiles) == 1500
        assert max(t[3] for t in tiles) == 1100

    def test_overlap_increases_tile_count(self):
        few = plan_tiles(2000, 2000, 640, 0.0)
        many = plan_tiles(2000, 2000, 640, 0.5)
        assert len(many) > len(few)

    def test_camera_module_3_frame_tile_count(self):
        """4056x3040 at 640/0.2 -- the real configuration, so pin the number."""
        tiles = plan_tiles(4056, 3040, 640, 0.2)
        assert 40 <= len(tiles) <= 70, f"unexpected tile count {len(tiles)}"

    def test_invalid_overlap_rejected(self):
        with pytest.raises(ValueError, match="overlap"):
            plan_tiles(1000, 1000, 640, 1.0)
        with pytest.raises(ValueError, match="overlap"):
            plan_tiles(1000, 1000, 640, -0.1)


class TestTiledEngineGeometry:
    def test_small_frame_bypasses_tiling(self):
        """No point slicing a frame no bigger than one tile."""
        inner = FixedDetectionEngine()
        tiled = TiledEngine(inner, tile_size=640)
        dets = tiled.infer(np.zeros((480, 640, 3), dtype=np.uint8))
        assert inner.calls == 1
        assert dets[0].bbox == (0.25, 0.25, 0.75, 0.75)

    def test_inner_sees_native_resolution_tiles(self):
        """The whole point: the detector gets un-downscaled pixels."""
        inner = FixedDetectionEngine()
        TiledEngine(inner, tile_size=640, overlap=0.2).infer(
            np.zeros((1280, 1280, 3), dtype=np.uint8)
        )
        assert all(shape == (640, 640) for shape in inner.seen_shapes)

    def test_box_maps_to_correct_global_position(self):
        """Hand-computed: a box at 25-75% of the tile at origin (0,0) of a
        1280x1280 frame occupies 12.5-37.5% of the frame."""
        inner = FixedDetectionEngine()
        tiled = TiledEngine(inner, tile_size=640, overlap=0.0)
        dets = tiled.infer(np.zeros((1280, 1280, 3), dtype=np.uint8))
        corners = {tuple(round(v, 4) for v in d.bbox) for d in dets}
        assert (0.125, 0.125, 0.375, 0.375) in corners

    def test_bottom_right_tile_maps_correctly(self):
        """The tile at (640,640) of a 1280x1280 frame -> 62.5-87.5%."""
        inner = FixedDetectionEngine()
        tiled = TiledEngine(inner, tile_size=640, overlap=0.0)
        dets = tiled.infer(np.zeros((1280, 1280, 3), dtype=np.uint8))
        corners = {tuple(round(v, 4) for v in d.bbox) for d in dets}
        assert (0.625, 0.625, 0.875, 0.875) in corners

    def test_all_boxes_stay_in_unit_range(self):
        inner = FixedDetectionEngine()
        dets = TiledEngine(inner, tile_size=640, overlap=0.2).infer(
            np.zeros((1500, 1100, 3), dtype=np.uint8)
        )
        for d in dets:
            assert all(0.0 <= v <= 1.0 for v in d.bbox), d.bbox

    def test_non_square_frame(self):
        inner = FixedDetectionEngine()
        dets = TiledEngine(inner, tile_size=640, overlap=0.0).infer(
            np.zeros((640, 1920, 3), dtype=np.uint8)
        )
        assert len(dets) >= 3
        assert all(0.0 <= v <= 1.0 for d in dets for v in d.bbox)


class TestTiledEngineMerging:
    def test_duplicates_across_overlap_are_suppressed(self):
        """Heavy overlap makes neighbouring tiles report the same region.

        Adjacent tiles at 50% overlap produce full-tile boxes with IoU ~0.33, so
        a 0.3 threshold should collapse them.
        """
        inner = FullTileEngine()
        tiles = len(plan_tiles(1280, 1280, 640, 0.5))
        dets = TiledEngine(inner, tile_size=640, overlap=0.5, iou_threshold=0.3).infer(
            np.zeros((1280, 1280, 3), dtype=np.uint8)
        )
        assert inner.calls == tiles
        assert len(dets) < tiles, f"no merging happened: {len(dets)} of {tiles}"

    def test_no_merging_when_boxes_are_disjoint(self):
        """The converse: NMS must not delete genuinely separate objects."""
        inner = FixedDetectionEngine()
        dets = TiledEngine(inner, tile_size=640, overlap=0.0, iou_threshold=0.3).infer(
            np.zeros((1280, 1280, 3), dtype=np.uint8)
        )
        assert len(dets) == 4

    def test_distinct_objects_survive(self):
        inner = FixedDetectionEngine()
        dets = TiledEngine(inner, tile_size=640, overlap=0.0).infer(
            np.zeros((1280, 1280, 3), dtype=np.uint8)
        )
        assert len(dets) == 4        # 2x2 tiles, non-overlapping boxes

    def test_results_sorted_by_confidence(self):
        inner = FixedDetectionEngine()
        dets = TiledEngine(inner, tile_size=640, overlap=0.0).infer(
            np.zeros((1920, 1920, 3), dtype=np.uint8)
        )
        confs = [d.confidence for d in dets]
        assert confs == sorted(confs, reverse=True)

    def test_empty_results(self):
        inner = SilentEngine()
        # Default overlap is 0.2, so a 1280x1280 frame is a 3x3 grid, not 2x2.
        expected_tiles = len(plan_tiles(1280, 1280, 640, 0.2))
        assert TiledEngine(inner, tile_size=640).infer(
            np.zeros((1280, 1280, 3), dtype=np.uint8)
        ) == []
        assert inner.calls == expected_tiles


class TestSafety:
    def test_validated_flag_is_not_upgraded(self):
        """Tiling changes geometry, never whether the model was validated."""
        inner = FixedDetectionEngine(validated=False)
        dets = TiledEngine(inner, tile_size=640).infer(
            np.zeros((1280, 1280, 3), dtype=np.uint8)
        )
        assert dets and all(not d.validated_locally for d in dets)
        assert all(not d.may_drive_treatment for d in dets)

    def test_validated_flag_is_preserved_when_true(self):
        inner = FixedDetectionEngine(validated=True)
        dets = TiledEngine(inner, tile_size=640).infer(
            np.zeros((1280, 1280, 3), dtype=np.uint8)
        )
        assert dets and all(d.may_drive_treatment for d in dets)

    def test_excessive_tile_count_fails_loudly(self):
        """Silently running hundreds of inferences per frame is worse than an error."""
        inner = FixedDetectionEngine()
        tiled = TiledEngine(inner, tile_size=128, overlap=0.5, max_tiles=16)
        with pytest.raises(ValueError, match="max_tiles"):
            tiled.infer(np.zeros((2000, 2000, 3), dtype=np.uint8))

    def test_metadata_passes_through(self):
        inner = FixedDetectionEngine()
        assert TiledEngine(inner).metadata.name == "fixed"

    def test_close_propagates(self):
        class Closable(SilentEngine):
            closed = False

            def close(self):
                self.closed = True

        inner = Closable()
        TiledEngine(inner).close()
        assert inner.closed


class TestConfigWiring:
    def test_not_wrapped_by_default(self):
        inner = FixedDetectionEngine()
        assert maybe_wrap_tiled(inner, InferenceConfig()) is inner

    def test_wrapped_when_enabled(self):
        inner = FixedDetectionEngine()
        wrapped = maybe_wrap_tiled(inner, InferenceConfig(tiled=True))
        assert isinstance(wrapped, TiledEngine)
        assert wrapped.inner is inner

    def test_config_values_are_used(self):
        wrapped = maybe_wrap_tiled(
            FixedDetectionEngine(),
            InferenceConfig(tiled=True, tile_size=320, tile_overlap=0.4, max_tiles=100),
        )
        assert wrapped.tile_size == 320
        assert wrapped.overlap == 0.4
        assert wrapped.max_tiles == 100

    def test_none_engine_stays_none(self):
        assert maybe_wrap_tiled(None, InferenceConfig(tiled=True)) is None
