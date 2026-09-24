"""Sentinel-2 L2A scene search on Element84 Earth Search (STAC API v1)."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
# Earth Search v1 asset keys -> the bands used here.
BANDS = {"red": "red", "nir": "nir", "rededge": "rededge1", "scl": "scl"}


@dataclass
class Band:
    href: str
    scale: float = 1.0
    offset: float = 0.0


@dataclass
class Scene:
    scene_id: str
    datetime: str
    cloud_cover: float | None
    bands: dict[str, Band] = field(default_factory=dict)

    @property
    def date(self) -> str:
        return self.datetime[:10]


def search_body(bbox: list[float], start: str, end: str, max_cloud: float = 40.0,
                limit: int = 100) -> dict:
    return {
        "collections": [COLLECTION],
        "bbox": bbox,
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "limit": limit,
        "sortby": [{"field": "properties.datetime", "direction": "asc"}],
    }


def parse_items(payload: dict) -> list[Scene]:
    """STAC ItemCollection -> scenes that carry every band needed."""
    out = []
    for item in payload.get("features") or []:
        assets = item.get("assets") or {}
        bands: dict[str, Band] = {}
        for name, key in BANDS.items():
            a = assets.get(key)
            if not a or not a.get("href"):
                break
            rb = (a.get("raster:bands") or [{}])[0]
            # L2A processing baseline 04.00+ carries a -0.1 reflectance offset;
            # Earth Search publishes scale/offset per asset. Using them is what
            # keeps a 2021 scene and a 2026 scene comparable.
            bands[name] = Band(a["href"], float(rb.get("scale", 1.0)), float(rb.get("offset", 0.0)))
        else:
            props = item.get("properties") or {}
            out.append(Scene(item.get("id", ""), props.get("datetime", ""),
                             props.get("eo:cloud_cover"), bands))
    return out


def search(bbox: list[float], start: str, end: str, max_cloud: float = 40.0,
           timeout_s: float = 30.0) -> list[Scene]:  # pragma: no cover - network
    req = urllib.request.Request(
        EARTH_SEARCH, data=json.dumps(search_body(bbox, start, end, max_cloud)).encode(),
        method="POST", headers={"Content-Type": "application/json", "User-Agent": "agri-edge/0.1"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return parse_items(json.loads(resp.read().decode("utf-8")))
