"""Approval-gated export bundles."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Optional

from . import isoxml, shapefile
from .grid import RateGrid

FORMATS = ("isoxml", "shapefile", "geojson")


class NotApproved(PermissionError):
    """Export of a prescription nobody approved."""


def approve(g: RateGrid, actor: str, wind_ms: Optional[float]) -> dict:
    """The human gate. Same rules as ops/vra.approve_prescription: the grid must
    be validated (clipped to a treatment boundary, and -- for spot spray -- from
    a locally validated model), and a measured wind below the limit must be
    supplied. Nothing is marked validated by approving."""
    issues = list(g.issues)
    if not g.validated and not issues:
        issues.append("prescription not validated")
    if wind_ms is None:
        issues.append("no wind reading: cannot confirm wind below limit")
    elif wind_ms > g.constraints.wind_max_ms:
        issues.append(f"wind {wind_ms} m/s exceeds {g.constraints.wind_max_ms}")
    if issues:
        return {"approved": False, "issues": issues}
    g.approved, g.approved_by = True, actor
    g.approved_at = datetime.now(timezone.utc).isoformat()
    return {"approved": True, "issues": [], "approved_by": actor, "approved_at": g.approved_at}


def export_zip(g: RateGrid, boundary: dict, fmt: str, *, field_name: str,
               farm_name: str = "Farm") -> bytes:
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {FORMATS}")
    if not g.approved:
        raise NotApproved("prescription must be approved before export")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", (
            f"Prescription {g.prescription_id} for {field_name}: {g.product}, {g.unit}.\n"
            f"Approved by {g.approved_by} at {g.approved_at}.\n"
            "Cells outside the treatment area are 0. Check the map on the terminal before use.\n"))
        z.writestr("summary.json", json.dumps(g.summary(), indent=2))
        if fmt == "isoxml":
            xml, binary = isoxml.taskdata_xml(g, boundary, field_name=field_name, farm_name=farm_name)
            z.writestr("TASKDATA/TASKDATA.XML", xml)
            z.writestr("TASKDATA/GRD00001.BIN", binary)
        elif fmt == "shapefile":
            polys, recs = [], []
            for r in range(g.rows):
                for c in range(g.cols):
                    if not g.applicable[r, c]:
                        continue
                    polys.append([(lon, lat) for lat, lon in g.cell_latlon(r, c)])
                    recs.append({"RATE": float(g.rates[r, c]), "UNIT": g.unit, "CELL": f"{r}_{c}"})
            files = shapefile.write(polys, recs, [("RATE", "N", 12, 2), ("UNIT", "C", 8, 0),
                                                  ("CELL", "C", 12, 0)])
            for ext, data in files.items():
                z.writestr(f"rx_{g.field_id}{ext}", data)
        else:
            z.writestr(f"rx_{g.field_id}.geojson", json.dumps(g.geojson()))
    return buf.getvalue()
