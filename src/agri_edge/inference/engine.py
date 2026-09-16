"""Edge inference.

Backends: ONNX Runtime (portable), Hailo (the AI HAT+ NPU), and a deterministic
simulated backend for testing the surrounding pipeline.

THE RULE THIS MODULE ENFORCES
-----------------------------
Every Detection carries `validated_locally`. It is False unless the model's
metadata declares a completed local validation, and `Detection.may_drive_treatment`
is False whenever it is False.

This is not decoration. A weed model trained on DeepWeeds is trained on Australian
species in Australian conditions; PlantVillage is single leaves on plain
backgrounds and is not aerial field imagery at all. Neither is evidence of
performance on Saskatchewan canola. A false positive used for scouting costs a
walk; the same false positive wired to a sprayer costs chemical, crop or an
environmental incident. So the flag travels with the detection, all the way to
whatever would act on it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import yolox

log = logging.getLogger("agri_edge.inference")


@dataclass
class Detection:
    label: str
    confidence: float
    # Normalised xyxy in [0, 1] so the box survives any later resize.
    bbox: tuple[float, float, float, float]
    validated_locally: bool = False

    # The class the model actually predicted, when `label` has been collapsed to
    # a coarser one (see InferenceConfig.collapse_labels_to). Collapsing must not
    # destroy evidence: the reported label is what we are willing to claim, and
    # this is what the network said. None when no collapsing happened.
    source_label: str | None = None

    # Where on the ground this detection is, filled in by
    # `geo.georeference.georeference_detections` when telemetry and camera
    # intrinsics are both available. None means it was NOT georeferenced -- never
    # a default or a guess, because a fabricated position is worse than none.
    # `geo_error` says why, when there is a reason worth recording.
    lat: float | None = None
    lon: float | None = None
    position_error_m: float | None = None
    geo_error: str | None = None

    # Whether this detection sits inside the TREATMENT geofence -- the boundary
    # inside the flight boundary, where application is permitted (see
    # geo/geofence.py). None means the question was never asked.
    in_treatment_zone: bool | None = None

    @property
    def has_position(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def may_drive_treatment(self) -> bool:
        """Whether this detection is permitted to generate a treatment prescription.

        **Two independent conditions, both required**, following the safety
        architecture in the research report: the model may propose, deterministic
        geometry decides whether the proposal may be executed.

        1. `validated_locally` -- the model has been checked against local field
           imagery. Without it, the detection is decision support only.
        2. `in_treatment_zone is True` -- the detection has a known position AND
           that position is inside the treatment boundary.

        Condition 2 **fails closed**. `None` means the question was never asked --
        no geofence configured, or the detection could not be georeferenced -- and
        an unasked question is not a yes. So enabling treatment requires
        deliberately defining a boundary and successfully placing the detection
        inside it; neither can be arrived at by accident.
        """
        return self.validated_locally and self.in_treatment_zone is True

    def to_dict(self) -> dict:
        out = {
            "label": self.label,
            "confidence": round(float(self.confidence), 4),
            "bbox": [round(float(v), 5) for v in self.bbox],
            "validated_locally": self.validated_locally,
            "may_drive_treatment": self.may_drive_treatment,
        }
        if self.source_label is not None:
            out["source_label"] = self.source_label
        if self.has_position:
            out["lat"] = round(float(self.lat), 7)     # ~1 cm, finer than any GNSS here
            out["lon"] = round(float(self.lon), 7)
            if self.position_error_m is not None:
                out["position_error_m"] = self.position_error_m
        elif self.geo_error is not None:
            out["geo_error"] = self.geo_error
        if self.in_treatment_zone is not None:
            out["in_treatment_zone"] = self.in_treatment_zone
        return out


@dataclass
class ModelMetadata:
    """Provenance for a model, stored beside the weights as `<model>.meta.json`.

    Without this, nobody six months from now can say what a detection was produced
    by, or whether it was ever checked against ground truth.
    """

    name: str = "unknown"
    version: str = "0.0.0"
    trained_on: list[str] = field(default_factory=list)
    class_names: list[str] = field(default_factory=list)
    # Set true ONLY after validation against local field observations, recorded
    # by crop, growth stage, location, season, altitude and lighting.
    validated_locally: bool = False
    validation_notes: str = ""

    @classmethod
    def load_beside(cls, model_path: Path) -> "ModelMetadata":
        meta_path = model_path.with_suffix(model_path.suffix + ".meta.json")
        if not meta_path.exists():
            return cls(name=model_path.stem, validation_notes="No metadata file found.")
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


class InferenceEngine:
    def __init__(self, metadata: ModelMetadata | None = None):
        self.metadata = metadata or ModelMetadata()

    def infer(self, image: np.ndarray) -> list[Detection]:
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - trivial
        pass


def _letterbox(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour resize, used only by the simulated backend.

    Real inference uses `yolox.letterbox`, which preserves aspect ratio and
    returns the scale factor needed to map detections back to original-image
    coordinates. This cheaper version is fine for the simulated engine, which
    produces no coordinates anyone acts on.
    """
    h, w = image.shape[:2]
    tw, th = size
    yi = (np.linspace(0, h - 1, th)).astype(np.int32)
    xi = (np.linspace(0, w - 1, tw)).astype(np.int32)
    return image[yi][:, xi]


def _to_model_input(image: np.ndarray) -> np.ndarray:
    """Coerce a captured frame to the 3-channel uint8 layout the model expects.

    Multispectral frames carry more than three bands; the detector was trained on
    RGB, so take the first three. Doing this explicitly here beats letting a
    5-band array reach the session and fail with a shape error 40 frames into a
    flight.
    """
    if image.ndim == 2:
        return np.repeat(image[:, :, None], 3, axis=2)
    if image.shape[2] >= 3:
        return image[:, :, :3]
    return np.repeat(image[:, :, :1], 3, axis=2)


def detections_from_raw(
    raw: np.ndarray,
    original_shape: tuple[int, int],
    ratio: float,
    input_size: tuple[int, int],
    class_names: list[str],
    confidence_threshold: float,
    iou_threshold: float,
    validated_locally: bool,
    collapse_to: str | None = None,
) -> list[Detection]:
    """Decode a raw YOLOX head into `Detection`s.

    Shared by the ONNX and Hailo engines: the network head is identical, only the
    backend that produced `raw` differs. A module-level function rather than a
    method on one engine that the other borrows, so neither owns it and the
    sharing is explicit.

    `validated_locally` is threaded through rather than read from a global,
    because it is the flag that decides whether these detections may influence
    chemical application. Passing it explicitly makes it impossible to construct
    a Detection here without having decided that question.

    `collapse_to` reports every class under one label while keeping the predicted
    class in `source_label`. Use it when a model localises well but its class
    discrimination is not good enough to act on -- see
    `models/imageweeds_yolox_s_CARD.md`, where collapsing five weed species to
    `weed` doubles measured AP@.50 because the boxes were always right and only
    the species label was wrong.
    """
    boxes, scores, class_ids = yolox.postprocess(
        raw,
        original_shape=original_shape,
        ratio=ratio,
        input_size=input_size,
        score_threshold=confidence_threshold,
        iou_threshold=iou_threshold,
    )

    out = []
    for b, score, c in zip(boxes, scores, class_ids):
        predicted = (
            class_names[int(c)] if int(c) < len(class_names) else f"class_{int(c)}"
        )
        out.append(
            Detection(
                label=collapse_to or predicted,
                confidence=float(score),
                bbox=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                validated_locally=validated_locally,
                source_label=predicted if collapse_to else None,
            )
        )
    return out


class SimulatedEngine(InferenceEngine):
    """Deterministic detector for pipeline tests.

    Finds high-excess-green blobs by simple thresholding. It is not a weed
    detector and must never be presented as one; it exists so the plumbing around
    inference can be tested without a model file.
    """

    def __init__(self, label: str = "vegetation", threshold: float = 0.55):
        super().__init__(
            ModelMetadata(
                name="simulated",
                version="0.0.0",
                trained_on=["synthetic"],
                class_names=[label],
                validated_locally=False,
                validation_notes="Simulated backend. Never valid for treatment decisions.",
            )
        )
        self.label = label
        self.threshold = threshold

    def infer(self, image: np.ndarray) -> list[Detection]:
        small = _letterbox(image, (64, 64)).astype(np.float64)
        if small.ndim == 3 and small.shape[2] >= 3:
            score = small[..., 1] / (small.sum(axis=2) + 1e-9)
        else:
            gray = small if small.ndim == 2 else small.mean(axis=2)
            score = gray / 255.0

        mask = score > (self.threshold * score.max() if score.max() > 0 else 1.0)
        if not mask.any():
            return []

        ys, xs = np.nonzero(mask)
        h, w = mask.shape
        bbox = (xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h)
        conf = float(mask.mean())
        return [
            Detection(
                label=self.label,
                confidence=conf,
                bbox=bbox,
                validated_locally=self.metadata.validated_locally,
            )
        ]


class OnnxEngine(InferenceEngine):
    """ONNX Runtime backend. Requires the optional `onnx` extra."""

    def __init__(self, model_path: Path, input_size=(640, 640), confidence_threshold=0.5,
                 class_names: list[str] | None = None, iou_threshold: float = 0.45,
                 collapse_labels_to: str | None = None):
        super().__init__(ModelMetadata.load_beside(Path(model_path)))
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "onnxruntime is required for the onnx backend. "
                "Install with: pip install 'agri-edge[onnx]'"
            ) from exc
        self._session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name
        self.input_size = tuple(input_size)
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.class_names = class_names or self.metadata.class_names
        self.collapse_labels_to = collapse_labels_to

        # The exported input size is authoritative; a config that disagrees means
        # every box comes out wrong. Trust the model, and say so.
        shape = self._session.get_inputs()[0].shape
        if len(shape) == 4 and all(isinstance(d, int) for d in shape[2:]):
            exported = (int(shape[2]), int(shape[3]))
            if exported != self.input_size:
                log.warning(
                    "Config input_size %s disagrees with the exported model (%s). "
                    "Using the model's.", self.input_size, exported
                )
                self.input_size = exported

    def infer(self, image: np.ndarray) -> list[Detection]:
        rgb = _to_model_input(image)
        original_shape = rgb.shape[:2]

        # YOLOX feeds raw 0-255 values -- there is no /255 here, deliberately.
        chw, ratio = yolox.letterbox(rgb, self.input_size)
        outputs = self._session.run(None, {self._input_name: chw[None, ...]})

        return self._to_detections(outputs[0], original_shape, ratio)

    def _to_detections(
        self, raw: np.ndarray, original_shape: tuple[int, int], ratio: float
    ) -> list[Detection]:
        return detections_from_raw(
            raw,
            original_shape=original_shape,
            ratio=ratio,
            input_size=self.input_size,
            class_names=self.class_names,
            confidence_threshold=self.confidence_threshold,
            iou_threshold=self.iou_threshold,
            # The safety contract: a detection is decision support until the
            # model behind it has been validated on local imagery.
            validated_locally=self.metadata.validated_locally,
            collapse_to=self.collapse_labels_to,
        )


class HailoEngine(InferenceEngine):
    """Hailo NPU backend for the Raspberry Pi AI HAT+.

    Note on part selection: for conventional agricultural detection and
    segmentation the 26-TOPS AI HAT+ is the right buy. The 40-TOPS AI HAT+ 2
    (Hailo-10H, 8 GB) delivers roughly comparable computer-vision throughput --
    its advantage is local LLM and VLM work, which this pipeline does not do.

    Requires HailoRT and a compiled .hef. Model compilation is part of the
    deployment workflow, not an afterthought: a PyTorch model must go through
    ONNX and the Hailo compiler, and not every operator survives the trip.
    """

    def __init__(self, hef_path: Path, confidence_threshold: float = 0.5,
                 class_names: list[str] | None = None, input_size=(640, 640),
                 iou_threshold: float = 0.45, collapse_labels_to: str | None = None):
        super().__init__(ModelMetadata.load_beside(Path(hef_path)))
        try:  # pragma: no cover - requires hardware
            from hailo_platform import (
                HEF,
                ConfigureParams,
                HailoStreamInterface,
                InputVStreamParams,
                OutputVStreamParams,
                VDevice,
            )
        except ImportError as exc:
            raise RuntimeError(
                "HailoRT is required for the hailo backend. Install the Raspberry Pi "
                "AI software stack (`sudo apt install hailo-all`); see "
                "raspberrypi.com/documentation/accessories/ai-hat-plus.html."
            ) from exc

        self.hef_path = Path(hef_path)
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.input_size = tuple(input_size)
        self.class_names = class_names or self.metadata.class_names
        self.collapse_labels_to = collapse_labels_to

        # pragma: no cover below -- everything here needs the NPU present.
        self._hef = HEF(str(self.hef_path))
        self._target = VDevice()
        cfg = ConfigureParams.create_from_hef(
            self._hef, interface=HailoStreamInterface.PCIe
        )
        self._network_group = self._target.configure(self._hef, cfg)[0]
        self._ng_params = self._network_group.create_params()
        self._in_params = InputVStreamParams.make(self._network_group)
        self._out_params = OutputVStreamParams.make(self._network_group)

        in_info = self._hef.get_input_vstream_infos()[0]
        self._input_name = in_info.name
        # The .hef is authoritative about its own input geometry.
        self.input_size = (int(in_info.shape[0]), int(in_info.shape[1]))

        out_infos = self._hef.get_output_vstream_infos()
        self._output_name = out_infos[0].name
        # A .hef compiled with NMS baked in emits final boxes rather than the raw
        # head. Detect which we got once, here, instead of guessing per frame.
        self._nms_on_device = len(out_infos[0].shape) != 2
        log.info(
            "Hailo: %s, input %s, output %s, on-device NMS=%s",
            self.hef_path.name, self.input_size, out_infos[0].shape, self._nms_on_device,
        )

    def infer(self, image: np.ndarray) -> list[Detection]:  # pragma: no cover - hardware
        from hailo_platform import InferVStreams

        rgb = _to_model_input(image)
        original_shape = rgb.shape[:2]

        chw, ratio = yolox.letterbox(rgb, self.input_size)
        # HailoRT wants NHWC uint8, not the NCHW float32 ONNX Runtime takes.
        nhwc = np.ascontiguousarray(
            chw.transpose(1, 2, 0)[None, ...].astype(np.uint8)
        )

        with InferVStreams(self._network_group, self._in_params, self._out_params) as pipe:
            with self._network_group.activate(self._ng_params):
                results = pipe.infer({self._input_name: nhwc})

        raw = np.asarray(results[self._output_name])
        if self._nms_on_device:
            return self._decode_device_nms(raw, original_shape, ratio)
        return detections_from_raw(
            raw,
            original_shape=original_shape,
            ratio=ratio,
            input_size=self.input_size,
            class_names=self.class_names,
            confidence_threshold=self.confidence_threshold,
            iou_threshold=self.iou_threshold,
            validated_locally=self.metadata.validated_locally,
            collapse_to=self.collapse_labels_to,
        )

    def _decode_device_nms(
        self, raw: np.ndarray, original_shape: tuple[int, int], ratio: float
    ) -> list[Detection]:  # pragma: no cover - hardware
        """Handle a .hef whose NMS ran on the NPU.

        Output is per-class lists of `[y_min, x_min, y_max, x_max, score]`,
        normalised to the letterboxed input -- note the y-first ordering, which is
        not the xyxy used everywhere else here.
        """
        ih, iw = self.input_size
        oh, ow = original_shape
        dets: list[Detection] = []

        per_class = raw[0] if raw.ndim > 1 and isinstance(raw[0], (list, np.ndarray)) else raw
        for class_id, boxes in enumerate(per_class):
            for box in np.atleast_2d(np.asarray(boxes)):
                if box.size < 5:
                    continue
                y0, x0, y1, x1, score = (float(v) for v in box[:5])
                if score < self.confidence_threshold:
                    continue
                # normalised-in-letterbox -> input pixels -> original -> normalised
                px = np.array([x0 * iw, y0 * ih, x1 * iw, y1 * ih]) / ratio
                dets.append(
                    Detection(
                        label=(
                            self.class_names[class_id]
                            if class_id < len(self.class_names)
                            else f"class_{class_id}"
                        ),
                        confidence=score,
                        bbox=(
                            float(np.clip(px[0] / ow, 0, 1)),
                            float(np.clip(px[1] / oh, 0, 1)),
                            float(np.clip(px[2] / ow, 0, 1)),
                            float(np.clip(px[3] / oh, 0, 1)),
                        ),
                        validated_locally=self.metadata.validated_locally,
                    )
                )
        return dets

    def close(self) -> None:  # pragma: no cover - hardware
        target = getattr(self, "_target", None)
        if target is not None:
            target.release()


def build_engine(cfg) -> InferenceEngine | None:
    """Construct the configured engine, or None when inference is disabled.

    Wraps the result for tiled inference when `cfg.tiled` is set -- see
    `agri_edge.inference.tiling` for why that is often not optional.
    """
    from .tiling import maybe_wrap_tiled

    return maybe_wrap_tiled(_build_backend(cfg), cfg)


def _build_backend(cfg) -> InferenceEngine | None:
    if not cfg.enabled:
        return None
    backend = (cfg.backend or "simulated").lower()
    if backend == "simulated":
        return SimulatedEngine()
    if backend == "greenonbrown":
        # Imported here rather than at module top so the backend stays optional
        # and this module keeps its numpy-only import surface.
        from .greenonbrown import GreenOnBrownEngine

        return GreenOnBrownEngine(
            index=cfg.green_index,
            threshold_mode=cfg.green_threshold_mode,
            index_min=cfg.green_index_min,
            index_max=cfg.green_index_max,
            min_area_px=cfg.green_min_area_px,
            max_detections=cfg.green_max_detections,
            label=(cfg.class_names[0] if cfg.class_names else "vegetation"),
            confidence_threshold=cfg.confidence_threshold,
        )
    if backend == "onnx":
        if cfg.model_path is None:
            raise ValueError("inference.model_path is required for the onnx backend.")
        return OnnxEngine(
            Path(cfg.model_path),
            input_size=tuple(cfg.input_size),
            confidence_threshold=cfg.confidence_threshold,
            class_names=cfg.class_names,
            collapse_labels_to=cfg.collapse_labels_to,
        )
    if backend == "hailo":
        if cfg.model_path is None:
            raise ValueError("inference.model_path (.hef) is required for the hailo backend.")
        return HailoEngine(
            Path(cfg.model_path),
            input_size=tuple(cfg.input_size),
            confidence_threshold=cfg.confidence_threshold,
            class_names=cfg.class_names,
            collapse_labels_to=cfg.collapse_labels_to,
        )
    raise ValueError(f"Unknown inference backend '{cfg.backend}'.")
