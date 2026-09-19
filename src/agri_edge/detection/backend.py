"""DetectionBackend protocol — no vendor types in the contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from agri_edge.inference.engine import Detection


@dataclass
class InferenceResult:
    """Normalized batch result. Downstream code must only consume this + Detection."""

    detections: list[Detection]
    backend_name: str
    model_name: str = ""
    model_version: str = ""
    latency_ms: float | None = None
    status: str = "IMPLEMENTED"  # IMPLEMENTED | SIMULATED | BLOCKED-HARDWARE
    notes: str = ""
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "detections": [d.to_dict() for d in self.detections],
            "backend_name": self.backend_name,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "latency_ms": self.latency_ms,
            "status": self.status,
            "notes": self.notes,
        }


@runtime_checkable
class DetectionBackend(Protocol):
    """Protocol: image in → InferenceResult out. No HailoRT / ORT session objects."""

    name: str

    def infer(self, image: np.ndarray) -> InferenceResult:
        """Run detection. Must never return vendor-specific objects."""
        ...

    def close(self) -> None:
        ...
