"""Normalized Detection API — backends must not leak vendor types."""
from __future__ import annotations

import numpy as np

from agri_edge.detection import (
    CpuOnnxBackend,
    Detection,
    DetectionBackend,
    HailoBackend,
    InferenceResult,
    SimulatedBackend,
)


def test_simulated_backend_protocol_and_fail_closed_treatment():
    backend: DetectionBackend = SimulatedBackend(label="weed", confidence=0.91)
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    result = backend.infer(img)
    assert isinstance(result, InferenceResult)
    assert result.backend_name == "simulated"
    assert result.status == "IMPLEMENTED"
    assert len(result.detections) == 1
    det = result.detections[0]
    assert isinstance(det, Detection)
    assert det.label == "weed"
    assert det.validated_locally is False
    assert det.may_drive_treatment is False
    # No vendor types in result extras / detections
    assert "hailo" not in type(det).__module__.lower()
    backend.close()


def test_cpu_onnx_stub_without_model_returns_empty():
    backend = CpuOnnxBackend(model_path=None)
    result = backend.infer(np.zeros((32, 32, 3), dtype=np.uint8))
    assert result.backend_name == "cpu_onnx"
    assert result.status == "SIMULATED"
    assert result.detections == []
    backend.close()


def test_hailo_backend_blocked_without_hardware():
    backend = HailoBackend(model_path=None)
    result = backend.infer(np.zeros((32, 32, 3), dtype=np.uint8))
    assert result.backend_name == "hailo"
    assert result.status == "BLOCKED-HARDWARE"
    assert result.detections == []
    # Ensure we did not import hailort as a side effect of constructing the stub
    import sys

    assert "hailort" not in sys.modules
    assert "hailo_platform" not in sys.modules
    backend.close()


def test_inference_result_to_dict_serializable():
    result = SimulatedBackend().infer(np.zeros((8, 8, 3), dtype=np.uint8))
    d = result.to_dict()
    assert d["backend_name"] == "simulated"
    assert isinstance(d["detections"], list)
    assert "bbox" in d["detections"][0]
