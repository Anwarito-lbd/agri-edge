"""Laptop-only scene-relation hooks (RelateAnything).

DINOv3-licensed weights + Gemma annotation lineage — NOT for the Pi flight
image. See docs/RELATE_ANYTHING.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping


class NotConfiguredError(RuntimeError):
    """Vendor tree or weights missing, or running on a Pi."""


def _is_raspberry_pi() -> bool:
    model = Path("/proc/device-tree/model")
    if not model.is_file():
        return False
    try:
        text = model.read_text(errors="ignore")
    except OSError:
        return False
    return "raspberry pi" in text.lower()


def assert_laptop_only() -> None:
    if _is_raspberry_pi():
        raise NotConfiguredError(
            "RelateAnything is laptop/research only — refused on Raspberry Pi"
        )


def vendor_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path.cwd()
    return root / "vendor" / "RelateAnything"


def relation_feature(
    subject: str,
    predicate: str,
    obj: str,
    *,
    confidence: float | None = None,
    frame_id: str = "offline",
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """GeoJSON property schema for one subject-predicate-object triple."""
    props: dict[str, Any] = {
        "kind": "relation",
        "subject": subject,
        "predicate": predicate,
        "object": obj,
        "confidence": confidence,
        "frame_id": frame_id,
        "source": "relate_anything_laptop",
        "licence_gate": "DINOv3+Gemma — not Pi runtime",
    }
    if extra:
        props.update(dict(extra))
    return props


def relations_to_geojson(
    relations: Iterable[Mapping[str, Any]],
    *,
    lon: float = 0.0,
    lat: float = 0.0,
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": dict(r),
            }
            for r in relations
        ],
    }


def run_offline(spool_dir: str | Path, repo_root: Path | None = None) -> dict[str, Any]:
    """Offline relation pass. Raises until vendor/RelateAnything is present."""
    assert_laptop_only()
    spool = Path(spool_dir)
    if not spool.is_dir():
        raise FileNotFoundError(f"spool_dir not found: {spool}")
    vendor = vendor_root(repo_root)
    if not vendor.is_dir():
        raise NotConfiguredError(
            f"Missing {vendor} — clone https://github.com/Maelic/RelateAnything "
            "into vendor/ on the laptop (gitignored). Accept DINOv3 notices."
        )
    raise NotConfiguredError(
        "RelateAnything vendor present but weights/runtime wiring not configured yet; "
        "schema helpers are ready (relation_feature / relations_to_geojson)."
    )
