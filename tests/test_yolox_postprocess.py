"""Tests for YOLOX pre/post-processing.

The decoder is the highest-risk code in the inference path: a wrong grid offset,
a missing stride multiply, or a double sigmoid all produce detections that look
superficially reasonable and are quietly, systematically wrong.

So where possible these tests check against an *independent* reference rather
than against themselves:

* `TestAgainstYoloxReference` compares the numpy decoder to YOLOX's own torch
  `decode_outputs`, on random input. If upstream and this module disagree by more
  than float tolerance, one of them is wrong and the test says so.
* `TestLetterboxAgainstYolox` compares geometry to YOLOX's `preproc`.

Both skip cleanly when torch/YOLOX are absent, so the Pi runtime's test suite
still passes without them.
"""

import numpy as np
import pytest

from agri_edge.inference import yolox

try:  # optional -- laptop only
    import torch as _torch
    from yolox.models.yolo_head import YOLOXHead
    HAVE_YOLOX = True
except Exception:  # pragma: no cover - depends on optional dev deps
    HAVE_YOLOX = False


class TestBuildGrid:
    def test_anchor_count_at_640(self):
        """80x80 + 40x40 + 20x20 = 8400, the canonical YOLOX-640 anchor count."""
        grid, strides = yolox.build_grid((640, 640))
        assert grid.shape == (1, 8400, 2)
        assert strides.shape == (1, 8400, 1)

    def test_stride_blocks_in_head_order(self):
        _, strides = yolox.build_grid((640, 640))
        s = strides[0, :, 0]
        assert (s[:6400] == 8).all()
        assert (s[6400:8000] == 16).all()
        assert (s[8000:] == 32).all()

    def test_grid_is_x_then_y(self):
        """`grid = stack((xv, yv))` -- x first. Swapping transposes every box."""
        grid, _ = yolox.build_grid((640, 640))
        # Within the stride-8 block (80 wide), index 1 is x=1,y=0.
        assert tuple(grid[0, 1]) == (1.0, 0.0)
        assert tuple(grid[0, 80]) == (0.0, 1.0)

    def test_non_square_input(self):
        grid, _ = yolox.build_grid((320, 640))
        expected = (320 // 8) * (640 // 8) + (320 // 16) * (640 // 16) + (320 // 32) * (640 // 32)
        assert grid.shape[1] == expected


class TestDecodeOutputs:
    def test_zero_offsets_land_on_grid_centres(self):
        """dx=dy=0 puts the box at grid*stride; dw=dh=0 gives exp(0)*stride = stride."""
        raw = np.zeros((1, 8400, 7), dtype=np.float32)
        out = yolox.decode_outputs(raw, (640, 640))
        assert tuple(out[0, 0, :4]) == (0.0, 0.0, 8.0, 8.0)
        # index 1 in the stride-8 block is x=1 -> 8 px
        assert tuple(out[0, 1, :4]) == (8.0, 0.0, 8.0, 8.0)

    def test_stride_32_block_scales_by_32(self):
        raw = np.zeros((1, 8400, 7), dtype=np.float32)
        out = yolox.decode_outputs(raw, (640, 640))
        assert out[0, 8000, 2] == 32.0

    def test_obj_and_cls_pass_through_untouched(self):
        """They are already sigmoided in the head. A second sigmoid is a real bug."""
        raw = np.zeros((1, 8400, 7), dtype=np.float32)
        raw[0, 0, 4] = 0.9
        raw[0, 0, 5] = 0.8
        out = yolox.decode_outputs(raw, (640, 640))
        assert out[0, 0, 4] == pytest.approx(0.9)
        assert out[0, 0, 5] == pytest.approx(0.8)

    def test_anchor_count_mismatch_is_explained(self):
        raw = np.zeros((1, 100, 7), dtype=np.float32)
        with pytest.raises(ValueError, match="anchors"):
            yolox.decode_outputs(raw, (640, 640))

    def test_extreme_wh_does_not_overflow(self):
        """exp() is clipped; an unclipped exp(90) becomes inf and poisons NMS."""
        raw = np.zeros((1, 8400, 7), dtype=np.float32)
        raw[0, 0, 2:4] = 90.0
        out = yolox.decode_outputs(raw, (640, 640))
        assert np.isfinite(out).all()


@pytest.mark.skipif(not HAVE_YOLOX, reason="torch/YOLOX not installed (laptop-only dev deps)")
class TestAgainstYoloxReference:
    """Compare the numpy decoder to YOLOX's own torch implementation."""

    def test_matches_upstream_decode(self):
        rng = np.random.default_rng(0)
        raw = rng.normal(0, 1, size=(1, 8400, 7)).astype(np.float32)

        head = YOLOXHead(num_classes=2)
        head.hw = [(80, 80), (40, 40), (20, 20)]
        head.strides = [8, 16, 32]
        reference = head.decode_outputs(_torch.from_numpy(raw), dtype=_torch.float32).numpy()

        mine = yolox.decode_outputs(raw, (640, 640))
        np.testing.assert_allclose(mine, reference, rtol=1e-5, atol=1e-4)

    def test_matches_upstream_on_non_square_input(self):
        rng = np.random.default_rng(1)
        n = (40 * 80) + (20 * 40) + (10 * 20)
        raw = rng.normal(0, 1, size=(1, n, 7)).astype(np.float32)

        head = YOLOXHead(num_classes=2)
        head.hw = [(40, 80), (20, 40), (10, 20)]
        head.strides = [8, 16, 32]
        reference = head.decode_outputs(_torch.from_numpy(raw), dtype=_torch.float32).numpy()

        mine = yolox.decode_outputs(raw, (320, 640))
        np.testing.assert_allclose(mine, reference, rtol=1e-5, atol=1e-4)


class TestLetterbox:
    def test_square_into_square_is_unscaled(self):
        img = np.full((640, 640, 3), 200, dtype=np.uint8)
        chw, ratio = yolox.letterbox(img, (640, 640))
        assert chw.shape == (3, 640, 640)
        assert ratio == 1.0

    def test_preserves_aspect_ratio(self):
        """A 1280x640 image scales by 0.5 and occupies the top half."""
        img = np.full((640, 1280, 3), 200, dtype=np.uint8)
        chw, ratio = yolox.letterbox(img, (640, 640))
        assert ratio == 0.5
        assert chw[0, 100, 100] == pytest.approx(200, abs=1)      # image region
        assert chw[0, 500, 100] == pytest.approx(yolox.PAD_VALUE)  # padding below

    def test_pads_with_114_not_zero(self):
        img = np.full((320, 640, 3), 10, dtype=np.uint8)
        chw, _ = yolox.letterbox(img, (640, 640))
        assert chw[0, 639, 639] == pytest.approx(114.0)

    def test_image_sits_top_left_not_centred(self):
        img = np.full((320, 640, 3), 250, dtype=np.uint8)
        chw, _ = yolox.letterbox(img, (640, 640))
        assert chw[0, 0, 0] == pytest.approx(250, abs=1)          # occupied
        assert chw[0, 639, 0] == pytest.approx(114.0)             # padded

    def test_values_are_not_normalised(self):
        """YOLOX feeds raw 0-255. Dividing by 255 destroys every score."""
        img = np.full((640, 640, 3), 255, dtype=np.uint8)
        chw, _ = yolox.letterbox(img, (640, 640))
        assert chw.max() > 1.5

    def test_grayscale_is_promoted(self):
        chw, _ = yolox.letterbox(np.full((640, 640), 100, dtype=np.uint8), (640, 640))
        assert chw.shape[0] == 1


@pytest.mark.skipif(not HAVE_YOLOX, reason="torch/YOLOX not installed")
class TestLetterboxAgainstYolox:
    def test_ratio_matches_upstream(self):
        from yolox.data.data_augment import preproc

        for shape in [(480, 640), (1080, 1920), (640, 640), (900, 300)]:
            img = np.random.default_rng(0).integers(0, 255, (*shape, 3), dtype=np.uint8)
            _, ref_ratio = preproc(img, (640, 640))
            _, mine = yolox.letterbox(img, (640, 640))
            assert mine == pytest.approx(ref_ratio), f"ratio differs for {shape}"


class TestNms:
    def test_empty(self):
        assert yolox.nms(np.zeros((0, 4)), np.zeros((0,)), 0.5) == []

    def test_suppresses_duplicate(self):
        boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11]], dtype=float)
        assert yolox.nms(boxes, np.array([0.9, 0.8]), 0.5) == [0]

    def test_keeps_disjoint_boxes(self):
        boxes = np.array([[0, 0, 10, 10], [100, 100, 110, 110]], dtype=float)
        assert sorted(yolox.nms(boxes, np.array([0.9, 0.8]), 0.5)) == [0, 1]

    def test_returns_highest_score_first(self):
        boxes = np.array([[0, 0, 10, 10], [100, 100, 110, 110]], dtype=float)
        assert yolox.nms(boxes, np.array([0.3, 0.99]), 0.5)[0] == 1

    def test_threshold_is_respected(self):
        """Boxes at IoU ~0.33: suppressed at 0.3, kept at 0.5."""
        boxes = np.array([[0, 0, 10, 10], [5, 0, 15, 10]], dtype=float)
        scores = np.array([0.9, 0.8])
        assert yolox.nms(boxes, scores, 0.3) == [0]
        assert sorted(yolox.nms(boxes, scores, 0.5)) == [0, 1]


class TestCxcywhToXyxy:
    def test_hand_computed(self):
        box = np.array([[100.0, 100.0, 40.0, 20.0]])
        np.testing.assert_allclose(yolox.cxcywh_to_xyxy(box), [[80.0, 90.0, 120.0, 110.0]])


class TestPostprocess:
    def _raw_with_one_box(self, cx, cy, w, h, score=0.9, cls=1, nc=2):
        """Build a raw head tensor containing a single confident box."""
        raw = np.zeros((1, 8400, 5 + nc), dtype=np.float32)
        raw[..., 4] = 0.0
        grid, strides = yolox.build_grid((640, 640))
        # Use anchor 0 (grid 0,0, stride 8) and solve for the raw offsets.
        raw[0, 0, 0] = cx / 8.0
        raw[0, 0, 1] = cy / 8.0
        raw[0, 0, 2] = np.log(w / 8.0)
        raw[0, 0, 3] = np.log(h / 8.0)
        raw[0, 0, 4] = 1.0
        raw[0, 0, 5 + cls] = score
        return raw

    def test_single_box_round_trips_to_normalised_coords(self):
        raw = self._raw_with_one_box(320.0, 320.0, 64.0, 64.0)
        boxes, scores, ids = yolox.postprocess(
            raw, original_shape=(640, 640), ratio=1.0, input_size=(640, 640),
            score_threshold=0.5,
        )
        assert len(boxes) == 1
        np.testing.assert_allclose(boxes[0], [288 / 640, 288 / 640, 352 / 640, 352 / 640], atol=1e-4)
        assert scores[0] == pytest.approx(0.9)
        assert ids[0] == 1

    def test_boxes_are_normalised_to_unit_range(self):
        raw = self._raw_with_one_box(320.0, 320.0, 64.0, 64.0)
        boxes, _, _ = yolox.postprocess(
            raw, (640, 640), 1.0, (640, 640), score_threshold=0.5
        )
        assert (boxes >= 0).all() and (boxes <= 1).all()

    def test_ratio_is_undone(self):
        """A 1280x1280 original letterboxed at ratio 0.5 maps back to the same
        normalised position -- which is the whole point of normalised bboxes."""
        raw = self._raw_with_one_box(320.0, 320.0, 64.0, 64.0)
        boxes, _, _ = yolox.postprocess(
            raw, original_shape=(1280, 1280), ratio=0.5, input_size=(640, 640),
            score_threshold=0.5,
        )
        np.testing.assert_allclose(boxes[0], [288 / 640, 288 / 640, 352 / 640, 352 / 640], atol=1e-4)

    def test_score_threshold_filters(self):
        raw = self._raw_with_one_box(320.0, 320.0, 64.0, 64.0, score=0.3)
        boxes, _, _ = yolox.postprocess(raw, (640, 640), 1.0, (640, 640), score_threshold=0.5)
        assert len(boxes) == 0

    def test_score_is_obj_times_cls(self):
        raw = self._raw_with_one_box(320.0, 320.0, 64.0, 64.0, score=0.8)
        raw[0, 0, 4] = 0.5   # objectness
        _, scores, _ = yolox.postprocess(raw, (640, 640), 1.0, (640, 640), score_threshold=0.1)
        assert scores[0] == pytest.approx(0.4)

    def test_nms_is_class_wise(self):
        """Overlapping crop and weed boxes must both survive -- they legitimately
        co-occur, and cross-class suppression would delete one."""
        raw = np.zeros((1, 8400, 7), dtype=np.float32)
        for anchor, cls in ((0, 0), (1, 1)):
            raw[0, anchor, 0] = 320.0 / 8.0 - (0 if anchor == 0 else 1)
            raw[0, anchor, 1] = 320.0 / 8.0
            raw[0, anchor, 2] = np.log(64.0 / 8.0)
            raw[0, anchor, 3] = np.log(64.0 / 8.0)
            raw[0, anchor, 4] = 1.0
            raw[0, anchor, 5 + cls] = 0.9
        boxes, _, ids = yolox.postprocess(raw, (640, 640), 1.0, (640, 640), score_threshold=0.5)
        assert sorted(ids) == [0, 1]

    def test_no_detections_returns_empty_arrays(self):
        raw = np.zeros((1, 8400, 7), dtype=np.float32)
        boxes, scores, ids = yolox.postprocess(raw, (640, 640), 1.0, (640, 640))
        assert boxes.shape == (0, 4) and len(scores) == 0 and len(ids) == 0

    def test_max_detections_caps_output(self):
        rng = np.random.default_rng(3)
        raw = np.zeros((1, 8400, 7), dtype=np.float32)
        raw[0, :, 0:2] = rng.uniform(0, 80, size=(8400, 2))
        raw[0, :, 2:4] = np.log(2.0)
        raw[0, :, 4] = 1.0
        raw[0, :, 5] = 0.99
        boxes, _, _ = yolox.postprocess(
            raw, (640, 640), 1.0, (640, 640), score_threshold=0.5,
            iou_threshold=0.99, max_detections=10,
        )
        assert len(boxes) <= 10


class TestLabelCollapsing:
    """Reporting a coarser label than the model predicted.

    `imageweeds_yolox_s` localises weeds well but puts 76% of its predictions in
    one of its five species classes. Collapsing to `weed` takes measured AP@.50
    from 0.246 to 0.520 -- the boxes were always right, only the species was
    wrong. The rule these tests pin down: collapsing changes what is *claimed*,
    never what was *observed*, so the predicted class has to survive.
    """

    @staticmethod
    def _raw_with_one_box(class_id: int, n_classes: int = 5) -> np.ndarray:
        raw = np.zeros((1, 8400, 5 + n_classes), dtype=np.float32)
        raw[0, 0, 0:2] = 20.0            # grid-space centre
        raw[0, 0, 2:4] = np.log(4.0)     # w, h
        raw[0, 0, 4] = 1.0               # objectness
        raw[0, 0, 5 + class_id] = 1.0    # class score
        return raw

    NAMES = ["ragweed", "waterhemp", "horseweed", "redrootpigweed", "kochia"]

    def _decode(self, class_id: int, collapse_to):
        from agri_edge.inference.engine import detections_from_raw

        return detections_from_raw(
            self._raw_with_one_box(class_id),
            original_shape=(640, 640),
            ratio=1.0,
            input_size=(640, 640),
            class_names=self.NAMES,
            confidence_threshold=0.5,
            iou_threshold=0.45,
            validated_locally=False,
            collapse_to=collapse_to,
        )

    def test_without_collapsing_the_model_class_is_reported(self):
        dets = self._decode(class_id=2, collapse_to=None)
        assert [d.label for d in dets] == ["horseweed"]
        assert dets[0].source_label is None

    def test_collapsing_reports_the_coarse_label(self):
        dets = self._decode(class_id=2, collapse_to="weed")
        assert [d.label for d in dets] == ["weed"]

    def test_collapsing_preserves_the_predicted_class(self):
        """The whole point: we stop *claiming* a species, we do not stop recording it."""
        dets = self._decode(class_id=4, collapse_to="weed")
        assert dets[0].source_label == "kochia"
        assert dets[0].to_dict()["source_label"] == "kochia"

    def test_collapsing_does_not_touch_the_safety_gate(self):
        """Relabelling must not become a way to launder an unvalidated model."""
        dets = self._decode(class_id=0, collapse_to="weed")
        assert dets[0].validated_locally is False
        assert dets[0].may_drive_treatment is False

    def test_collapsing_does_not_move_the_box(self):
        plain = self._decode(class_id=3, collapse_to=None)
        collapsed = self._decode(class_id=3, collapse_to="weed")
        assert plain[0].bbox == collapsed[0].bbox

    def test_sidecar_omits_source_label_when_not_collapsing(self):
        """An always-present null would imply collapsing happened and produced nothing."""
        assert "source_label" not in self._decode(class_id=1, collapse_to=None)[0].to_dict()

    def test_config_defaults_to_no_collapsing(self):
        from agri_edge.config import InferenceConfig

        assert InferenceConfig().collapse_labels_to is None
