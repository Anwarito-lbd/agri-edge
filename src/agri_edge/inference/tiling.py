"""Tiled inference: run a detector over slices of a frame at native resolution.

WHY THIS EXISTS
---------------
Letterboxing a 4056x3040 camera frame down to the network's 640x640 input throws
away 6.3x of linear resolution before the detector sees anything. For small
targets that is the difference between detectable and invisible:

    3 cm weed seedling, Pi Camera Module 3, >= 20 px needed
        whole-frame inference ... resolvable only below  0.6 m AGL
        tiled inference ........ resolvable below        3.9 m AGL

    25 cm mature weed
        whole-frame ............ below  5.1 m AGL
        tiled .................. below 32.0 m AGL

At normal survey altitude the whole-frame path cannot see weeds at all. This is
optics, not model quality -- no amount of training recovers a two-pixel object.
(`training/gsd_calculator.py` computes these ceilings for your camera and target.)

Tiling cuts the frame into overlapping native-resolution tiles and runs the
detector on each, buying back the full 6.3x. The cost is real: N tiles means N
inferences per frame. Measure it with `training/benchmark.py` before assuming a
frame rate.

This wraps any `InferenceEngine`, so it works identically over ONNX on the CPU
and over the Hailo NPU.
"""

from __future__ import annotations

import numpy as np

from .engine import Detection, InferenceEngine
from .yolox import nms


def plan_tiles(
    width: int, height: int, tile: int, overlap: float
) -> list[tuple[int, int, int, int]]:
    """Cover a WxH frame with `tile`-sized windows overlapping by `overlap`.

    Returns `(x0, y0, x1, y1)` in pixels. The last row and column are pulled back
    flush with the frame edge rather than padded, so every tile is full-sized and
    no detector ever sees a band of padding it might hallucinate against.

    Overlap exists so that an object straddling a tile boundary is whole in at
    least one tile. It should exceed the largest target's fraction of a tile.
    """
    if not 0.0 <= overlap < 1.0:
        raise ValueError(f"overlap must be in [0, 1), got {overlap}")

    stride = max(1, int(tile * (1.0 - overlap)))
    xs = list(range(0, max(1, width - tile + 1), stride))
    ys = list(range(0, max(1, height - tile + 1), stride))

    # Ensure the right/bottom edges are covered.
    if not xs or xs[-1] + tile < width:
        xs.append(max(0, width - tile))
    if not ys or ys[-1] + tile < height:
        ys.append(max(0, height - tile))

    boxes = []
    for y in sorted(set(ys)):
        for x in sorted(set(xs)):
            boxes.append((x, y, min(x + tile, width), min(y + tile, height)))
    return boxes


class TiledEngine(InferenceEngine):
    """Runs an inner engine over overlapping tiles and merges the results.

    Detections come back normalised to the **original frame**, exactly as a
    non-tiled engine would return them, so nothing downstream needs to know
    tiling happened.
    """

    def __init__(
        self,
        inner: InferenceEngine,
        tile_size: int = 640,
        overlap: float = 0.2,
        iou_threshold: float = 0.45,
        max_tiles: int = 64,
    ):
        super().__init__(inner.metadata)
        self.inner = inner
        self.tile_size = tile_size
        self.overlap = overlap
        self.iou_threshold = iou_threshold
        # A guard, not a tuning knob: a 4056x3040 frame at 640/0.2 is 56 tiles.
        # Silently running 400 inferences per frame on an aircraft is worse than
        # failing loudly.
        self.max_tiles = max_tiles

    @property
    def class_names(self) -> list[str]:
        return getattr(self.inner, "class_names", self.metadata.class_names)

    def infer(self, image: np.ndarray) -> list[Detection]:
        h, w = image.shape[:2]

        # Nothing to gain from tiling a frame no larger than one tile.
        if w <= self.tile_size and h <= self.tile_size:
            return self.inner.infer(image)

        tiles = plan_tiles(w, h, self.tile_size, self.overlap)
        if len(tiles) > self.max_tiles:
            raise ValueError(
                f"{len(tiles)} tiles for a {w}x{h} frame exceeds max_tiles={self.max_tiles}. "
                f"That is {len(tiles)} inferences per frame. Raise max_tiles deliberately, "
                f"reduce the capture resolution, or increase tile_size."
            )

        collected: list[Detection] = []
        for x0, y0, x1, y1 in tiles:
            crop = image[y0:y1, x0:x1]
            ch, cw = crop.shape[:2]

            for det in self.inner.infer(crop):
                # tile-normalised -> tile pixels -> frame pixels -> frame-normalised
                bx0, by0, bx1, by1 = det.bbox
                gx0 = (bx0 * cw + x0) / w
                gy0 = (by0 * ch + y0) / h
                gx1 = (bx1 * cw + x0) / w
                gy1 = (by1 * ch + y0) / h
                collected.append(
                    Detection(
                        label=det.label,
                        confidence=det.confidence,
                        bbox=(gx0, gy0, gx1, gy1),
                        # Never upgraded here. Tiling changes geometry, not
                        # whether the model has been validated.
                        validated_locally=det.validated_locally,
                    )
                )

        return self._merge(collected)

    def _merge(self, dets: list[Detection]) -> list[Detection]:
        """Class-wise NMS across tiles.

        Overlap means an object near a boundary is detected twice. Suppression is
        per class, since a crop box and a weed box may legitimately overlap.
        """
        if len(dets) <= 1:
            return dets

        boxes = np.array([d.bbox for d in dets], dtype=np.float64)
        scores = np.array([d.confidence for d in dets], dtype=np.float64)
        labels = np.array([d.label for d in dets])

        keep: list[int] = []
        for label in np.unique(labels):
            idx = np.nonzero(labels == label)[0]
            for k in nms(boxes[idx], scores[idx], self.iou_threshold):
                keep.append(int(idx[k]))

        keep.sort(key=lambda i: -scores[i])
        return [dets[i] for i in keep]

    def close(self) -> None:
        self.inner.close()


def maybe_wrap_tiled(engine: InferenceEngine | None, cfg) -> InferenceEngine | None:
    """Wrap an engine for tiled inference when the config asks for it."""
    if engine is None or not getattr(cfg, "tiled", False):
        return engine
    return TiledEngine(
        engine,
        tile_size=getattr(cfg, "tile_size", 640),
        overlap=getattr(cfg, "tile_overlap", 0.2),
        max_tiles=getattr(cfg, "max_tiles", 64),
    )
