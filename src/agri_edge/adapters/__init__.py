"""External-system adapters (master spec Rule 4: every external system behind an interface).

Nothing here talks to the network unless the caller explicitly opts in.
"""
from __future__ import annotations

from .agopengps import (
    AgOpenGpsAdapterStub,
    GuidanceAdapter,
    GuidanceCommandRefused,
    GuidanceState,
    GuidanceTrack,
)
from .farmos import (
    FarmManagementAdapter,
    FarmOSAdapter,
    FarmOSNetworkDisabled,
)

__all__ = [
    "AgOpenGpsAdapterStub",
    "FarmManagementAdapter",
    "FarmOSAdapter",
    "FarmOSNetworkDisabled",
    "GuidanceAdapter",
    "GuidanceCommandRefused",
    "GuidanceState",
    "GuidanceTrack",
]
