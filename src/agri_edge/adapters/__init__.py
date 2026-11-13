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
from .agopengps_pgn import PgnParseError
from .agopengps_udp import AgOpenGpsReadOnlyAdapter, AgOpenGpsUdpListener
from .farmos import (
    FarmDataReader,
    FarmManagementAdapter,
    FarmOSAdapter,
    FarmOSNetworkDisabled,
)

__all__ = [
    "AgOpenGpsReadOnlyAdapter",
    "AgOpenGpsUdpListener",
    "PgnParseError",
    "AgOpenGpsAdapterStub",
    "FarmDataReader",
    "FarmManagementAdapter",
    "FarmOSAdapter",
    "FarmOSNetworkDisabled",
    "GuidanceAdapter",
    "GuidanceCommandRefused",
    "GuidanceState",
    "GuidanceTrack",
]
