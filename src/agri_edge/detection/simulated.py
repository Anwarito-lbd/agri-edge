"""Deterministic SimulatedBackend for unit tests and CI (IMPLEMENTED)."""
from __future__ import annotations

import numpy as np

from agri_edge.inference.engine import Detection

from .backend import InferenceResult


class SimulatedBackend:
    """Always returns a fixed, non-treatment-eligible detection."""

    name = "simulated"

    def __init__(self, label: str = "weed", confidence: float = 0.9) -> None:
        self.label = label
        self.confidence = confidence

    def infer(self, image: np.ndarray) -> InferenceResult:
        _ = image
        det = Detection(
            label=self.label,
            confidence=self.confidence,
            bbox=(0.4, 0.4, 0.6, 0.6),
            validated_locally=False,
        )
        return InferenceResult(
            detections=[det],
            backend_name=self.name,
            model_name="simulated",
            model_version="0.0.0",
            latency_ms=0.0,
            status="IMPLEMENTED",
            notes="Simulated backend. Never valid for treatment.",
        )

    def close(self) -> None:
        return None
