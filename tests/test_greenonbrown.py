"""Tests for the green-on-brown backend ported from OpenWeedLocator.

Three things here are worth more than they look:

* **Channel order.** Exactly half the indices are symmetric in red and blue, so
  an RGB/BGR mix-up leaves ExG and nExG working perfectly while silently
  corrupting ExGR and MaxG. A test that only exercised `exg` would pass against
  genuinely broken code, and so would a single-pixel test of MaxG.
* **The upper bound.** The indices saturate at 255, so an upper threshold of
  OpenWeedLocator's 250 discards the *greenest* pixels in the frame. This was a
  real bug in this file, caught by a synthetic pure-green blob.
* **The safety gate.** No amount of threshold tuning makes this a validated
  detector, and `may_drive_treatment` must stay False regardless.
"""

import numpy as np
import pytest

from agri_edge.inference.greenonbrown import (
    INDICES,
    GreenOnBrownEngine,
    _label_numpy,
    excess_green,
    excess_green_red,
    label_components,
    max_green,
    normalised_excess_green,
    threshold_absolute,
)


def soil_frame(h=120, w=160, rgb=(120, 90, 60)):
    """Brown soil: ExG = 2*90 - 120 - 60 = 0."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = rgb
    return img


def with_blob(img, y0, y1, x0, x1, rgb=(40, 200, 40)):
    out = img.copy()
    out[y0:y1, x0:x1] = rgb
    return out


class TestIndices:
    def test_exg_matches_hand_computed_value(self):
        px = np.array([[[10, 100, 20]]], dtype=np.uint8)   # R=10 G=100 B=20
        assert excess_green(px)[0, 0] == pytest.approx(2 * 100 - 10 - 20)

    def test_exg_is_symmetric_in_red_and_blue(self):
        """2G - R - B cannot tell R from B, so a channel swap is harmless here."""
        rgb = np.array([[[10, 100, 20]]], dtype=np.uint8)
        bgr = rgb[..., ::-1].copy()
        assert excess_green(rgb)[0, 0] == excess_green(bgr)[0, 0]

    def test_normalised_exg_is_also_symmetric(self):
        """(2G-R-B)/(R+G+B): numerator and denominator are both R/B-symmetric."""
        rgb = np.array([[[10, 100, 20]]], dtype=np.uint8)
        bgr = rgb[..., ::-1].copy()
        assert normalised_excess_green(rgb)[0, 0] == normalised_excess_green(bgr)[0, 0]

    @pytest.mark.parametrize("fn", [excess_green_red, max_green])
    def test_weighted_indices_are_not_symmetric(self, fn):
        """The reason the indices are rewritten for RGB rather than wrapped.

        Half the indices here are R/B-symmetric and half are not, which is why a
        channel mix-up is dangerous: it would half-work.

        Note the multi-pixel image. MaxG rescales by its own frame maximum, so on
        a 1x1 input every value normalises to 255 and the asymmetry vanishes --
        a single-pixel test would pass against genuinely broken code.
        """
        rgb = np.array([[[10, 100, 20], [200, 30, 5]]], dtype=np.uint8)
        bgr = rgb[..., ::-1].copy()
        assert not np.allclose(fn(rgb), fn(bgr))

    def test_soil_scores_below_vegetation_for_every_index(self):
        soil = np.array([[[120, 90, 60]]], dtype=np.uint8)
        leaf = np.array([[[40, 200, 40]]], dtype=np.uint8)
        both = np.concatenate([soil, leaf], axis=1)
        for name, fn in INDICES.items():
            out = fn(both)
            assert out[0, 1] > out[0, 0], f"{name} did not rank leaf above soil"

    def test_indices_stay_in_range(self):
        rng = np.random.default_rng(0)
        img = rng.integers(0, 256, size=(40, 40, 3), dtype=np.uint8)
        for name, fn in INDICES.items():
            out = fn(img)
            assert out.min() >= 0 and out.max() <= 255, name


class TestThresholding:
    def test_upper_bound_excludes_rather_than_clamps(self):
        """Regression: pure green saturates ExG to 255 and a 250 ceiling drops it.

        OpenWeedLocator clips into its band; this thresholds on it. Carrying the
        250 default across would have silently discarded the strongest signal.
        """
        index = np.array([[0.0, 100.0, 255.0]])
        assert threshold_absolute(index, 30, 250).tolist() == [[0, 1, 0]]
        assert threshold_absolute(index, 30, 255).tolist() == [[0, 1, 1]]

    def test_engine_default_does_not_drop_saturated_green(self):
        img = with_blob(soil_frame(), 20, 60, 30, 90, rgb=(0, 255, 0))
        assert len(GreenOnBrownEngine(min_area_px=10).infer(img)) == 1


class TestLabelling:
    def test_numpy_fallback_agrees_with_opencv(self):
        """The fallback exists so this works without cv2; it must not differ."""
        cv2 = pytest.importorskip("cv2")
        rng = np.random.default_rng(3)
        mask = (rng.random((60, 80)) > 0.75).astype(np.uint8)
        _, n_np = _label_numpy(mask)
        _, n_cv = label_components(mask)
        assert n_np == n_cv

    def test_two_separated_blobs_are_two_components(self):
        mask = np.zeros((40, 60), dtype=np.uint8)
        mask[5:15, 5:15] = 1
        mask[25:35, 40:50] = 1
        _, n = _label_numpy(mask)
        assert n == 2

    def test_touching_blobs_are_one_component(self):
        mask = np.zeros((20, 20), dtype=np.uint8)
        mask[5:10, 5:15] = 1
        _, n = _label_numpy(mask)
        assert n == 1

    def test_empty_mask_has_no_components(self):
        _, n = _label_numpy(np.zeros((10, 10), dtype=np.uint8))
        assert n == 0


class TestEngine:
    def test_finds_both_blobs_with_correct_boxes(self):
        img = with_blob(with_blob(soil_frame(120, 160), 20, 40, 30, 60),
                        80, 100, 100, 140)
        dets = GreenOnBrownEngine(min_area_px=50).infer(img)
        assert len(dets) == 2
        # Boxes are normalised; the first blob spans x 30-60 of 160, y 20-40 of 120.
        boxes = sorted(d.bbox for d in dets)
        assert boxes[0][0] == pytest.approx(30 / 160, abs=0.02)
        assert boxes[0][1] == pytest.approx(20 / 120, abs=0.02)

    def test_bare_soil_yields_nothing(self):
        assert GreenOnBrownEngine().infer(soil_frame()) == []

    def test_min_area_filters_specks(self):
        img = with_blob(soil_frame(), 10, 13, 10, 13)   # 9 px
        assert GreenOnBrownEngine(min_area_px=100).infer(img) == []
        assert len(GreenOnBrownEngine(min_area_px=4).infer(img)) == 1

    def test_detections_are_capped_largest_first(self):
        """A frame of pond algae must not produce a multi-megabyte sidecar."""
        img = soil_frame(200, 200)
        for i in range(8):
            y = 10 + i * 22
            img = with_blob(img, y, y + 4 + i, 10, 14 + i)   # increasing size
        dets = GreenOnBrownEngine(min_area_px=1, max_detections=3).infer(img)
        assert len(dets) == 3
        areas = [(d.bbox[2] - d.bbox[0]) * (d.bbox[3] - d.bbox[1]) for d in dets]
        assert areas == sorted(areas, reverse=True), "cap must keep the largest"

    def test_safety_gate_holds(self):
        """There is no model here, so this can never be treatment-authorising."""
        img = with_blob(soil_frame(), 20, 60, 30, 90)
        for d in GreenOnBrownEngine(min_area_px=10).infer(img):
            assert d.validated_locally is False
            assert d.may_drive_treatment is False

    def test_default_label_is_vegetation_not_weed(self):
        """It detects green. Calling it 'weed' is a claim about the ground."""
        img = with_blob(soil_frame(), 20, 60, 30, 90)
        assert GreenOnBrownEngine(min_area_px=10).infer(img)[0].label == "vegetation"

    def test_confidence_rises_with_greenness(self):
        faint = with_blob(soil_frame(), 20, 60, 30, 90, rgb=(90, 130, 90))
        vivid = with_blob(soil_frame(), 20, 60, 30, 90, rgb=(20, 240, 20))
        eng = GreenOnBrownEngine(min_area_px=10)
        assert eng.infer(faint)[0].confidence < eng.infer(vivid)[0].confidence

    def test_confidence_threshold_filters(self):
        img = with_blob(soil_frame(), 20, 60, 30, 90, rgb=(90, 130, 90))
        assert GreenOnBrownEngine(min_area_px=10, confidence_threshold=0.99).infer(img) == []

    def test_single_band_input_is_rejected(self):
        """A colour index on one band is meaningless; fail loudly rather than return []."""
        with pytest.raises(ValueError, match="RGB"):
            GreenOnBrownEngine().infer(np.zeros((20, 20), dtype=np.uint8))

    @pytest.mark.parametrize("kwargs", [{"index": "nope"}, {"threshold_mode": "nope"}])
    def test_unknown_options_are_rejected_at_construction(self, kwargs):
        with pytest.raises(ValueError):
            GreenOnBrownEngine(**kwargs)

    def test_metadata_records_what_it_cannot_do(self):
        meta = GreenOnBrownEngine().metadata
        assert meta.validated_locally is False
        assert "not weeds" in meta.validation_notes


class TestConfigWiring:
    def test_backend_builds_from_config(self):
        from agri_edge.config import InferenceConfig
        from agri_edge.inference.engine import build_engine

        eng = build_engine(
            InferenceConfig(enabled=True, backend="greenonbrown", class_names=["weed"])
        )
        assert isinstance(eng, GreenOnBrownEngine)
        assert eng.label == "weed"

    def test_config_default_upper_bound_is_255(self):
        from agri_edge.config import InferenceConfig

        assert InferenceConfig().green_index_max == 255.0
