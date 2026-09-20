"""3D scene API + optional VR status (§115–116, §159) — Cesium-ready JSON, no real VR."""
from __future__ import annotations

from typing import Any


def scene(farm_id: str = "demo_farm", store: Any = None) -> dict[str, Any]:
    """Return terrain/fields/vehicles/stations JSON suitable for Cesium later."""
    fields = [
        {
            "id": "field_north",
            "name": "North Field",
            "polygon": [
                [-75.70, 45.40, 90.0],
                [-75.69, 45.40, 90.0],
                [-75.69, 45.41, 91.0],
                [-75.70, 45.41, 91.0],
                [-75.70, 45.40, 90.0],
            ],
            "synthetic": True,
        }
    ]
    vehicles = [
        {
            "id": "ugv_sim_1",
            "kind": "ugv",
            "position": [-75.697, 45.402, 90.5],
            "heading_deg": 45.0,
            "status": "idle",
            "synthetic": True,
        }
    ]
    stations = [
        {"id": "wx1", "kind": "weather", "position": [-75.697, 45.402, 92.0], "synthetic": True},
        {"id": "soil1", "kind": "soil", "position": [-75.696, 45.403, 90.0], "synthetic": True},
        {"id": "svc1", "kind": "service", "position": [-75.701, 45.399, 90.0], "synthetic": True},
    ]
    if store is not None:
        for sid, s in getattr(store, "service_stations", {}).items():
            stations.append({
                "id": sid,
                "kind": "service",
                "position": [s.lon, s.lat, 90.0],
                "status": s.status,
                "synthetic": s.synthetic,
            })
        for rid, r in getattr(store, "rtk", {}).items():
            stations.append({
                "id": rid,
                "kind": "rtk",
                "position": [r.lon, r.lat, 95.0],
                "synthetic": r.synthetic,
            })
    return {
        "farm_id": farm_id,
        "format": "agri_edge_scene_v1",
        "cesium_ready": True,
        "terrain": {
            "provider": "ellipsoid",
            "height_m": 90.0,
            "bounds": {"west": -75.70, "south": 45.40, "east": -75.69, "north": 45.41},
            "synthetic": True,
        },
        "fields": fields,
        "vehicles": vehicles,
        "stations": stations,
        "vr_supported": False,
        "safety_critical": False,
        "stub": False,
        "synthetic": True,
        "note": "Simulation scene for Cesium; not live telemetry",
    }


def vr_status() -> dict[str, Any]:
    """§116 optional VR — non-safety-critical; unsupported in sim."""
    return {
        "supported": False,
        "reason": "VR headset integration out of MVP software scope; non-safety-critical optional feature",
        "safety_critical": False,
        "synthetic": True,
    }


# Back-compat
def scene_stub(farm_id: str = "demo_farm") -> dict[str, Any]:
    return scene(farm_id)


