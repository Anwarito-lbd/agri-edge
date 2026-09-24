"""Hailo on-device-NMS decoding, tested without the NPU.

Finding F12 of docs/audit-2026-09-24.md. The HailoEngine had never run on
hardware and would have failed on its first detection:

* `np.asarray(results[...])` on HailoRT's NMS-by-class output -- a list of
  per-class arrays of DIFFERENT lengths -- raises ValueError on NumPy >= 1.24;
* NMS was detected as `len(shape) != 2`, which calls a raw (H, W, C) YOLOX
  head an NMS output;
* `collapse_labels_to` was ignored on this path.

The decoder is now a pure function so the part that can be wrong without a
device is tested without one.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from agri_edge.inference.engine import _is_nms_output, decode_hailo_nms

NAMES = ["kochia", "ragweed", "horseweed"]


def _ragged_output():
    """Batch of one; three classes holding 2, 0 and 1 boxes."""
    return [[
        np.array([[0.10, 0.10, 0.20, 0.20, 0.90],
                  [0.50, 0.50, 0.60, 0.60, 0.20]], dtype=np.float32),
        np.zeros((0, 5), dtype=np.float32),
        np.array([[0.30, 0.40, 0.50, 0.60, 0.75]], dtype=np.float32),
    ]]


def _decode(raw, **kw):
    args = dict(input_size=(640, 640), original_shape=(640, 640), ratio=1.0,
                class_names=NAMES, confidence_threshold=0.5, validated_locally=False)
    args.update(kw)
    return decode_hailo_nms(raw, **args)


def test_ragged_output_is_what_used_to_crash():
    with pytest.raises(ValueError):
        np.asarray(_ragged_output())


def test_ragged_output_decodes():
    dets = _decode(_ragged_output())
    assert [d.label for d in dets] == ["kochia", "horseweed"]
    k = dets[0]
    # y-first in, xyxy out
    assert k.bbox == pytest.approx((0.10, 0.10, 0.20, 0.20))
    h = dets[1]
    assert h.bbox == pytest.approx((0.40, 0.30, 0.60, 0.50))
    assert h.confidence == pytest.approx(0.75)


def test_unbatched_output_decodes_the_same():
    assert [d.label for d in _decode(_ragged_output()[0])] == ["kochia", "horseweed"]


def test_no_detections_at_all():
    empty = [[np.zeros((0, 5), dtype=np.float32) for _ in NAMES]]
    assert _decode(empty) == []


def test_collapse_keeps_the_predicted_class():
    dets = _decode(_ragged_output(), collapse_to="weed")
    assert {d.label for d in dets} == {"weed"}
    assert [d.source_label for d in dets] == ["kochia", "horseweed"]


def test_letterbox_ratio_maps_back_to_the_original_frame():
    # A 1280x960 frame letterboxed into 640x640 at ratio 0.5 (top-left pad).
    raw = [[np.array([[0.25, 0.25, 0.5, 0.5, 0.9]], dtype=np.float32)]]
    (d,) = _decode(raw, class_names=["weed"], original_shape=(960, 1280), ratio=0.5)
    assert d.bbox == pytest.approx((320 / 1280, 320 / 960, 640 / 1280, 640 / 960))


def test_validation_flag_is_carried_not_invented():
    assert all(not d.validated_locally for d in _decode(_ragged_output()))


def _info(order=None, shape=(80, 80, 85), name="yolox/conv"):
    fmt = SimpleNamespace(order=order) if order is not None else None
    return SimpleNamespace(format=fmt, shape=shape, name=name)


def test_raw_head_is_not_mistaken_for_nms():
    assert _is_nms_output(_info(order="FormatOrder.NHWC")) is False


def test_nms_format_order_is_recognised():
    assert _is_nms_output(_info(order="FormatOrder.HAILO_NMS_BY_CLASS", shape=(3, 5, 100)))
