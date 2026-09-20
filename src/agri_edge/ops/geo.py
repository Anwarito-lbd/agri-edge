"""Farm GeoJSON layers + enable/disable (§88–92, §100–104). Standard formats only."""
from __future__ import annotations

from typing import Any, Optional

from .schema import MapAsset


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
            name="Microclimate",
            layer_kind="microclimate",
            geojson=build_microclimate_grid(),
            enabled=True,
            farm_id=farm_id,
            time_range="today",
            synthetic=True,
            meta={"stub": False, "origin": "DERIVED", "algorithm_version": "microclimate_idw_v1"},
        ),
        build_crop_health_asset(farm_id),
    ]




def build_microclimate_grid(
    weather_points: list[dict] | None = None,
    soil_points: list[dict] | None = None,
    *,
    grid: int = 4,
) -> dict:
    """§110 Interpolated microclimate FeatureCollection from point samples."""
    weather_points = weather_points or [
        {"lon": -75.698, "lat": 45.402, "air_temp_c": 18.5, "rh_pct": 60.0},
        {"lon": -75.696, "lat": 45.404, "air_temp_c": 19.2, "rh_pct": 55.0},
    ]
    soil_points = soil_points or [
        {"lon": -75.697, "lat": 45.403, "soil_temp_c": 14.0, "moisture_pct": 28.0},
    ]
    measured = []
    for i, p in enumerate(weather_points):
        measured.append(feature(
            {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
            {"kind": "measured", "source": "weather", "air_temp_c": p.get("air_temp_c"),
             "rh_pct": p.get("rh_pct"), "uncertainty_c": 0.2, "synthetic": True},
            f"wx_m_{i}",
        ))
    for i, p in enumerate(soil_points):
        measured.append(feature(
            {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
            {"kind": "measured", "source": "soil", "soil_temp_c": p.get("soil_temp_c"),
             "moisture_pct": p.get("moisture_pct"), "uncertainty_c": 0.3, "synthetic": True},
            f"soil_m_{i}",
        ))
    # simple IDW-ish grid over field bounds
    west, south, east, north = -75.700, 45.400, -75.690, 45.410
    interp = []
    anchors = weather_points
    for yi in range(grid):
        for xi in range(grid):
            lon = west + (east - west) * (xi + 0.5) / grid
            lat = south + (north - south) * (yi + 0.5) / grid
            # distance-weighted mean
            num = den = 0.0
            for a in anchors:
                d2 = (lon - a["lon"]) ** 2 + (lat - a["lat"]) ** 2 + 1e-12
                w = 1.0 / d2
                num += w * float(a.get("air_temp_c", 18.0))
                den += w
            t = num / den
            # uncertainty grows with distance from nearest measured point
            nearest = min(((lon - a["lon"]) ** 2 + (lat - a["lat"]) ** 2) ** 0.5 for a in anchors)
            unc = round(0.5 + nearest * 200.0, 2)
            interp.append(feature(
                {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                {"kind": "interpolated", "air_temp_c": round(t, 2), "uncertainty_c": unc,
                 "origin": "DERIVED", "algorithm_version": "microclimate_idw_v1", "synthetic": True},
                f"mc_{yi}_{xi}",
            ))
    return {
        **feature_collection(measured + interp),
        "measured_count": len(measured),
        "interpolated_count": len(interp),
        "origin": "DERIVED",
        "algorithm_version": "microclimate_idw_v1",
        "synthetic": True,
        "stub": False,
    }


def build_crop_health_asset(farm_id: str = "demo_farm") -> "MapAsset":
    """§111 Crop health MapAsset with NDVI path metadata + quality fields."""
    return MapAsset(
        asset_id="layer_crop_health",
        name="Crop health NDVI",
        layer_kind="health",
        geotiff_path="sim://maps/demo_farm/ndvi_latest.tif",
        enabled=True,
        farm_id=farm_id,
        time_range="week",
        synthetic=True,
        meta={
            "product": "NDVI",
            "path": "sim://maps/demo_farm/ndvi_latest.tif",
            "format": "GeoTIFF",
            "quality": {"cloud_pct": 2.0, "coverage_pct": 98.5, "score": 0.96},
            "origin": "DERIVED",
            "algorithm_version": "ndvi_sim_v1",
            "stub": False,
        },
    )


TIME_RANGES = ("now", "hour", "today", "week", "month", "custom")


def filter_by_time_range(assets: list[MapAsset], time_range: str) -> list[MapAsset]:
    if time_range not in TIME_RANGES:
        raise ValueError(f"unsupported time_range {time_range}; use {TIME_RANGES}")
    # Stub: return enabled assets tagged with matching or broader range
    return [a for a in assets if a.enabled and (a.time_range in (None, time_range, "now") or time_range == "custom")]
