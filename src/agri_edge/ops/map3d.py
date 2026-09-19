"""Optional 3D/VR API stub only (§115–116) — last priority, no real VR."""
from __future__ import annotations

from typing import Any


def scene_stub(farm_id: str = "demo_farm") -> dict[str, Any]:
    return {
        "farm_id": farm_id,
        "stub": True,
        "format": "glTF path placeholder",
        "url": None,
        "vr_supported": False,
        "note": "3D/VR intentionally stub-only; not in MVP",
        "synthetic": True,
    }
