"""YOLOX pre- and post-processing, in pure numpy.

Shared by the ONNX and Hailo engines: the network head is identical, only the
execution backend differs, so the decode lives here rather than being duplicated
(and drifting) in each.

Pure numpy on purpose. The Pi runtime's core dependencies are numpy and PyYAML;
pulling torch onto the aircraft to reshape a tensor would be absurd.

Everything here mirrors YOLOX's own implementation exactly, because "close
enough" produces boxes that are plausibly placed and consistently wrong:

* Letterbox pads with **114**, not 0, and puts the image at the **top-left**,
  not centred (`yolox/data/data_augment.py::preproc`).
* Input is **not** divided by 255. YOLOX feeds raw 0-255 values.
* The exported ONNX output is **undecoded** -- `tools/export_onnx.py` leaves
  `decode_in_inference = False`, so the grid/stride decode happens here.
* Objectness and class scores **are** already sigmoided inside the head
  (`yolo_head.py:188`); applying sigmoid again silently compresses every score
  toward 0.5 and wrecks the confidence threshold.
"""

from __future__ import annotations

import numpy as np

# Feature-map strides, in the order the head concatenates them.
# At 640x640 this is 80*80 + 40*40 + 20*20 = 8400 anchors.
DEFAULT_STRIDES = (8, 16, 32)
PAD_VALUE = 114


def letterbox(
    image: np.ndarray, input_size: tuple[int, int]
) -> tuple[np.ndarray, float]:
    """Resize preserving aspect ratio and pad to `input_size`.

    Returns `(chw_float32, ratio)`. Keep `ratio` -- it is what maps detections
    back to original-image coordinates. Losing it is the classic "boxes are close
    but consistently offset" bug.

    `input_size` is (height, width), matching YOLOX's convention.
    """
    ih, iw = input_size
    h, w = image.shape[:2]

    if image.ndim == 2:
        image = image[:, :, None]
    channels = image.shape[2]

    ratio = min(ih / h, iw / w)
    nh, nw = int(h * ratio), int(w * ratio)

    resized = _resize_bilinear(image, nh, nw)

    padded = np.full((ih, iw, channels), PAD_VALUE, dtype=np.float32)
    padded[:nh, :nw] = resized            # top-left, not centred

    chw = np.ascontiguousarray(padded.transpose(2, 0, 1), dtype=np.float32)
    return chw, ratio


def _resize_bilinear(image: np.ndarray, nh: int, nw: int) -> np.ndarray:
    """Bilinear resize, numpy-only.

    OpenCV's INTER_LINEAR is what YOLOX uses and is preferable when the `cv`
    extra is installed; this exists so the Pi runtime works without it. Nearest
    neighbour would be cheaper but visibly degrades small-object recall, and
    small objects are the entire problem here.
    """
    h, w = image.shape[:2]
    if (h, w) == (nh, nw):
        return image.astype(np.float32)

    src = image.astype(np.float32)

    # Half-pixel centres, matching the usual bilinear convention.
    y = (np.arange(nh, dtype=np.float32) + 0.5) * (h / nh) - 0.5
    x = (np.arange(nw, dtype=np.float32) + 0.5) * (w / nw) - 0.5
    y = np.clip(y, 0, h - 1)
    x = np.clip(x, 0, w - 1)

    y0 = np.floor(y).astype(np.int32)
    x0 = np.floor(x).astype(np.int32)
    y1 = np.minimum(y0 + 1, h - 1)
    x1 = np.minimum(x0 + 1, w - 1)

    wy = (y - y0)[:, None, None]
    wx = (x - x0)[None, :, None]

    top = src[y0][:, x0] * (1 - wx) + src[y0][:, x1] * wx
    bot = src[y1][:, x0] * (1 - wx) + src[y1][:, x1] * wx
    return top * (1 - wy) + bot * wy


def build_grid(
    input_size: tuple[int, int], strides: tuple[int, ...] = DEFAULT_STRIDES
) -> tuple[np.ndarray, np.ndarray]:
    """Anchor centres and their strides, concatenated in head order.

    Returns `(grid[N, 2] as (x, y), strides[N, 1])`.
    """
    ih, iw = input_size
    grids, expanded = [], []
    for stride in strides:
        hsize, wsize = ih // stride, iw // stride
        yv, xv = np.meshgrid(np.arange(hsize), np.arange(wsize), indexing="ij")
        grid = np.stack((xv, yv), axis=2).reshape(1, -1, 2)
        grids.append(grid)
        expanded.append(np.full((1, grid.shape[1], 1), stride, dtype=np.float32))
    return (
        np.concatenate(grids, axis=1).astype(np.float32),
        np.concatenate(expanded, axis=1),
    )


def decode_outputs(
    raw: np.ndarray,
    input_size: tuple[int, int],
    strides: tuple[int, ...] = DEFAULT_STRIDES,
) -> np.ndarray:
    """Undecoded head output -> boxes in input-space pixels.

    `raw` is `[batch, n_anchors, 5 + n_classes]` as `(dx, dy, dw, dh, obj, cls...)`.
    Returns the same shape with `(cx, cy, w, h)` in pixels:

        xy = (dx + grid) * stride
        wh = exp(dw) * stride

    `obj` and `cls` pass through untouched -- they are already sigmoided.
    """
    raw = np.atleast_3d(np.asarray(raw, dtype=np.float32))
    if raw.ndim == 2:
        raw = raw[None, ...]

    grid, stride = build_grid(input_size, strides)
    n = raw.shape[1]
    if grid.shape[1] != n:
        raise ValueError(
            f"Model produced {n} anchors but a {input_size[0]}x{input_size[1]} input "
            f"with strides {strides} implies {grid.shape[1]}. The exported input size "
            "and the configured input_size disagree."
        )

    out = raw.copy()
    out[..., 0:2] = (raw[..., 0:2] + grid) * stride
    out[..., 2:4] = np.exp(np.clip(raw[..., 2:4], -20, 20)) * stride
    return out


def cxcywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    out = np.empty_like(boxes)
    half_w = boxes[..., 2] / 2.0
    half_h = boxes[..., 3] / 2.0
    out[..., 0] = boxes[..., 0] - half_w
    out[..., 1] = boxes[..., 1] - half_h
    out[..., 2] = boxes[..., 0] + half_w
    out[..., 3] = boxes[..., 1] + half_h
    return out


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """Greedy non-maximum suppression. Returns kept indices, best score first."""
    if len(boxes) == 0:
        return []

    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]

    keep: list[int] = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        if order.size == 1:
            break
        rest = order[1:]

        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])

        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        union = areas[i] + areas[rest] - inter
        iou = np.where(union > 0, inter / np.maximum(union, 1e-9), 0.0)

        order = rest[iou <= iou_threshold]

    return keep


def postprocess(
    raw: np.ndarray,
    original_shape: tuple[int, int],
    ratio: float,
    input_size: tuple[int, int],
    score_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    strides: tuple[int, ...] = DEFAULT_STRIDES,
    max_detections: int = 300,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Full post-process: decode, threshold, class-wise NMS, normalise.

    Returns `(boxes_xyxy_normalised[N, 4], scores[N], class_ids[N])`, with boxes
    normalised to [0, 1] against the **original** image -- so they survive any
    later resize, which is what `Detection.bbox` promises.

    NMS is class-wise: a crop box and a weed box may legitimately overlap, and
    suppressing across classes would delete one of them.
    """
    decoded = decode_outputs(raw, input_size, strides)[0]

    boxes = cxcywh_to_xyxy(decoded[:, :4])
    obj = decoded[:, 4]
    cls_scores = decoded[:, 5:]

    if cls_scores.shape[1] == 0:
        return np.zeros((0, 4)), np.zeros((0,)), np.zeros((0,), dtype=int)

    class_ids = cls_scores.argmax(axis=1)
    # Both factors are already sigmoided in the head. Do not sigmoid again.
    scores = obj * cls_scores[np.arange(len(class_ids)), class_ids]

    mask = scores >= score_threshold
    boxes, scores, class_ids = boxes[mask], scores[mask], class_ids[mask]
    if len(boxes) == 0:
        return np.zeros((0, 4)), np.zeros((0,)), np.zeros((0,), dtype=int)

    # Undo the letterbox: padded input-space pixels -> original-image pixels.
    boxes = boxes / ratio

    oh, ow = original_shape
    boxes[:, 0::2] = np.clip(boxes[:, 0::2], 0, ow)
    boxes[:, 1::2] = np.clip(boxes[:, 1::2], 0, oh)

    keep_all: list[int] = []
    for c in np.unique(class_ids):
        idx = np.nonzero(class_ids == c)[0]
        kept = nms(boxes[idx], scores[idx], iou_threshold)
        keep_all.extend(idx[k] for k in kept)

    keep_all.sort(key=lambda i: -scores[i])
    keep_all = keep_all[:max_detections]

    boxes, scores, class_ids = boxes[keep_all], scores[keep_all], class_ids[keep_all]

    normalised = np.empty_like(boxes)
    normalised[:, 0::2] = boxes[:, 0::2] / ow
    normalised[:, 1::2] = boxes[:, 1::2] / oh

    return normalised, scores, class_ids
