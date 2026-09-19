"""Normalized Detection API — backends never leak Hailo/ONNX types downstream."""
from __future__ import annotations

from agri_edge.inference.engine import Detection

from .backend import DetectionBackend, InferenceResult
from .cpu_onnx import CpuOnnxBackend
from .hailo_backend import HailoBackend
from .simulated import SimulatedBackend

__all__ = [
    "Detection",
    "DetectionBackend",
    "InferenceResult",
    "CpuOnnxBackend",
    "HailoBackend",
    "SimulatedBackend",
]
