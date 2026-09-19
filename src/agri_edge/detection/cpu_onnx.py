"""CpuOnnxBackend — portable ONNX Runtime path (IMPLEMENTED when ORT + model present)."""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .backend import InferenceResult


class CpuOnnxBackend:
    name = "cpu_onnx"

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        class_names: list[str] | None = None,
        confidence_threshold: float = 0.25,
        input_size: tuple[int, int] = (640, 640),
        allow_missing: bool = True,
    ) -> None:
        self.model_path = Path(model_path) if model_path else None
        self.class_names = class_names or []
        self.confidence_threshold = confidence_threshold
        self.input_size = input_size
        self._engine = None
        self._status = "SIMULATED"
        self._notes = "No model loaded; returns empty detections (stub)."
        if self.model_path and self.model_path.is_file():
            try:
                from agri_edge.inference.engine import OnnxEngine

                self._engine = OnnxEngine(
                    self.model_path,
                    input_size=self.input_size,
                    confidence_threshold=self.confidence_threshold,
                    class_names=self.class_names or None,
                )
                self._status = "IMPLEMENTED"
                self._notes = "ONNX Runtime backend; host decode + NMS."
            except Exception as exc:  # pragma: no cover - optional dep
                if not allow_missing:
                    raise
                self._notes = f"OnnxEngine unavailable ({exc}); stub mode."

    def infer(self, image: np.ndarray) -> InferenceResult:
        t0 = time.perf_counter()
        dets: list = []
        model_name = self.model_path.stem if self.model_path else "cpu_onnx_stub"
        version = "0.0.0"
        if self._engine is not None:
            dets = self._engine.infer(image)
            meta = getattr(self._engine, "metadata", None)
            if meta is not None:
                model_name = getattr(meta, "name", model_name) or model_name
                version = getattr(meta, "version", version) or version
        ms = (time.perf_counter() - t0) * 1000.0
        return InferenceResult(
            detections=dets,
            backend_name=self.name,
            model_name=model_name,
            model_version=version,
            latency_ms=ms,
            status=self._status,
            notes=self._notes,
        )

    def close(self) -> None:
        if self._engine is not None:
            self._engine.close()
