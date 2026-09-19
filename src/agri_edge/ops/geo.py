"""Farm GeoJSON layers + enable/disable (§88–92, §100–104). Standard formats only."""
from __future__ import annotations

from typing import Any, Optional

from .schema import MapAsset
from .types import new_id


def feature(geom: dict[str, Any], properties: dict[str, Any], fid: Optional[str] = None) -> dict[str, Any]:
    f: dict[str, Any] = {"type": "Feature", "geometry": geom, "properties": properties}
    if fid:
        f["id"] = fid
    return f


def feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def demo_farm_geojson(farm_id: str = "demo_farm") -> dict[str, Any]:
    """Synthetic demo farm near Ottawa-ish coords — always synthetic."""
    field = feature(
        {
            "type": "Polygon",
            "coordinates": [[
                [-75.70, 45.40],
                [-75.69, 45.40],
                [-75.69, 45.41],
                [-75.70, 45.41],
                [-75.70, 45.40],
            ]],
        },
        {"name": "North Field", "farm_id": farm_id, "layer": "field", "synthetic": True},
        "field_north",
    )
    zone_a = feature(
        {
            "type": "Polygon",
            "coordinates": [[
                [-75.700, 45.400],
                [-75.695, 45.400],
                [-75.695, 45.405],
                [-75.700, 45.405],
                [-75.700, 45.400],
            ]],
        },
        {"name": "Zone A", "farm_id": farm_id, "layer": "zone", "synthetic": True},
        "zone_a",
    )
    wx = feature(
        {"type": "Point", "coordinates": [-75.697, 45.402]},
        {"name": "WX-1", "layer": "weather_station", "device_type": "weather_station", "synthetic": True},
        "wx1",
    )
    soil = feature(
        {"type": "Point", "coordinates": [-75.696, 45.403]},
        {"name": "SOIL-1", "layer": "soil_probe", "device_type": "soil_probe", "synthetic": True},
        "soil1",
    )
    return feature_collection([field, zone_a, wx, soil])


def default_map_assets(farm_id: str = "demo_farm") -> list[MapAsset]:
    fc = demo_farm_geojson(farm_id)
    return [
        MapAsset(
            asset_id="layer_fields",
            name="Fields",
            layer_kind="field",
            geojson=feature_collection([f for f in fc["features"] if f["properties"].get("layer") == "field"]),
            enabled=True,
            farm_id=farm_id,
            time_range="now",
            synthetic=True,
        ),
        MapAsset(
            asset_id="layer_zones",
            name="Zones",
            layer_kind="zone",
            geojson=feature_collection([f for f in fc["features"] if f["properties"].get("layer") == "zone"]),
            enabled=True,
            farm_id=farm_id,
            time_range="now",
            synthetic=True,
        ),
        MapAsset(
            asset_id="layer_stations",
            name="Stations",
            layer_kind="station",
            geojson=feature_collection(
                [f for f in fc["features"] if f["properties"].get("layer") in ("weather_station", "soil_probe")]
            ),
            enabled=True,
            farm_id=farm_id,
            time_range="now",
            synthetic=True,
        ),
        MapAsset(
            asset_id="layer_microclimate",
            name="Microclimate (stub)",
            layer_kind="microclimate",
            geojson=feature_collection([]),
            enabled=False,
            farm_id=farm_id,
            time_range="today",
            synthetic=True,
            meta={"stub": True},
        ),
        MapAsset(
            asset_id="layer_crop_health",
            name="Crop health (stub)",
            layer_kind="health",
            geotiff_path="s3://stub/health.tif",
            enabled=False,
            farm_id=farm_id,
            time_range="week",
            synthetic=True,
            meta={"stub": True, "format": "GeoTIFF path string only"},
        ),
    ]


TIME_RANGES = ("now", "hour", "today", "week", "month", "custom")


def filter_by_time_range(assets: list[MapAsset], time_range: str) -> list[MapAsset]:
    if time_range not in TIME_RANGES:
        raise ValueError(f"unsupported time_range {time_range}; use {TIME_RANGES}")
    # Stub: return enabled assets tagged with matching or broader range
    return [a for a in assets if a.enabled and (a.time_range in (None, time_range, "now") or time_range == "custom")]
