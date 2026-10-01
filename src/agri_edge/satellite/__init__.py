"""Sentinel-2 crop-health baseline, and where to send the drone.

Free 10 m imagery every ~5 days (Copernicus Sentinel-2 L2A, served as
cloud-optimised GeoTIFFs by Element84's Earth Search STAC API). For each field:
cloud-masked NDVI / NDRE statistics, a per-cell grid, a time series, and change
detection that flags cells declining faster than the rest of the field. Those
cells become scouting targets and a drone coverage plan, so the aircraft flies
where the satellite saw something rather than the whole farm.

* `stac`      scene search (stdlib HTTP)
* `field`     pure numpy: masks, indices, per-cell stats for one scene
* `reader`    reads a field window from the COGs (needs rasterio, `geo` extra)
* `series`    SQLite time series + change detection -> scout targets
* `service`   the whole update for one field

Imagery licence: Copernicus Sentinel data, free and open; attribution
"Contains modified Copernicus Sentinel data [year]" is required on products.
"""

ATTRIBUTION = "Contains modified Copernicus Sentinel data"
