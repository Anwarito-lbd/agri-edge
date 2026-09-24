"""Read one field's window from Sentinel-2 COGs, resampled onto a lon/lat grid.

Needs rasterio (the `geo` extra). The COGs are public on AWS (no credentials),
and only the tiles overlapping the field are fetched -- a quarter section is a
few hundred kilobytes per band, not the 100 km scene.

Every band is warped onto one EPSG:4326 grid at ~10 m spacing over the field's
bounding box: the 10 m bands (red, NIR) bilinearly, the 20 m ones (red edge)
bilinearly, and the scene classification (SCL) by nearest neighbour, because
averaging class codes produces classes that do not exist.
"""

from __future__ import annotations

import math

import numpy as np

from .field import Boundary
from .stac import Scene


def field_grid(boundary: Boundary, res_m: float = 10.0, pad_m: float = 20.0):
    west, south, east, north = boundary.bbox
    lat_c = (south + north) / 2
    dlat = res_m / 111_320.0
    dlon = res_m / (111_320.0 * math.cos(math.radians(lat_c)))
    west -= pad_m / res_m * dlon
    east += pad_m / res_m * dlon
    south -= pad_m / res_m * dlat
    north += pad_m / res_m * dlat
    width = max(1, math.ceil((east - west) / dlon))
    height = max(1, math.ceil((north - south) / dlat))
    lons = west + (np.arange(width) + 0.5) * dlon
    lats = north - (np.arange(height) + 0.5) * dlat
    lon2, lat2 = np.meshgrid(lons, lats)
    return (west, north, dlon, dlat, width, height), lat2, lon2


def read_field(scene: Scene, boundary: Boundary, res_m: float = 10.0):
    """-> (bands dict of reflectance / SCL arrays, lats, lons)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT

    (west, north, dlon, dlat, width, height), lats, lons = field_grid(boundary, res_m)
    transform = from_origin(west, north, dlon, dlat)
    bands: dict[str, np.ndarray] = {}
    env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "AWS_NO_SIGN_REQUEST": "YES",
           "GDAL_HTTP_MULTIRANGE": "YES", "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES"}
    with rasterio.Env(**env):
        for name, band in scene.bands.items():
            is_class = name == "scl"
            with rasterio.open(band.href) as src:
                with WarpedVRT(src, crs="EPSG:4326", transform=transform, width=width,
                               height=height, src_nodata=src.nodata,
                               resampling=Resampling.nearest if is_class else Resampling.bilinear) as vrt:
                    arr = vrt.read(1, masked=True)
            if is_class:
                bands[name] = np.ma.filled(arr, 0).astype(np.int64)     # 0 = no data
            else:
                ref = arr.astype(np.float64) * band.scale + band.offset
                bands[name] = np.ma.filled(ref, np.nan)
    return bands, lats, lons
