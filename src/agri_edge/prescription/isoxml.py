"""ISO 11783-10 task data: a grid-type-2 prescription for ISOBUS task controllers.

Output is a TASKDATA folder: TASKDATA.XML plus GRD00001.BIN.

* One task (TSK) on one partfield (PFD) whose boundary (PLN) is the treatment
  boundary, holes included as interior rings.
* Grid type 2: each cell of GRD00001.BIN holds the process-data value itself
  as a little-endian signed 32-bit integer, for the single PDV of treatment
  zone 1. Cells run from the south-west corner, east along a row, rows
  northward.
* Rates go out as DDI 0x0001 (setpoint volume per area, mm3/m2; 1 L/ha =
  100 mm3/m2) or DDI 0x0006 (setpoint mass per area, mg/m2; 1 kg/ha = 100 mg/m2).
* Position lost and out of field both point at treatment zone 2, whose rate is
  zero: when the controller does not know where it is, it applies nothing.

Written from the published structure of ISO 11783-10 v4; checked here for
well-formedness, references and binary layout. **Load it on the actual task
controller before relying on it** -- terminal implementations differ.
"""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET

import numpy as np

from .grid import RateGrid

DDI = {"L/ha": ("0001", 100.0), "kg/ha": ("0006", 100.0)}


def grid_binary(g: RateGrid) -> bytes:
    """Row 0 of `rates` is the southern row, so row-major order is already
    south-to-north, west-to-east."""
    _, factor = DDI[g.unit]
    vals = np.rint(g.rates * factor).astype("<i4")
    return vals.tobytes(order="C")


def taskdata_xml(g: RateGrid, boundary: dict, *, field_name: str, farm_name: str = "Farm",
                 grid_file: str = "GRD00001") -> tuple[bytes, bytes]:
    if g.unit not in DDI:
        raise ValueError(f"unit {g.unit!r} has no ISOBUS DDI here; use one of {sorted(DDI)}")
    ddi, _ = DDI[g.unit]
    binary = grid_binary(g)
    root = ET.Element("ISO11783_TaskData", {
        "VersionMajor": "4", "VersionMinor": "3", "DataTransferOrigin": "1",
        "ManagementSoftwareManufacturer": "agri-edge", "ManagementSoftwareVersion": "0.1",
    })
    ET.SubElement(root, "CTR", {"A": "CTR1", "B": farm_name[:32]})
    ET.SubElement(root, "FRM", {"A": "FRM1", "B": farm_name[:32], "I": "CTR1"})
    area_m2 = int(round(float(g.applicable.sum()) * g.cell_m * g.cell_m))
    pfd = ET.SubElement(root, "PFD", {"A": "PFD1", "C": field_name[:32], "D": str(max(area_m2, 1)),
                                      "E": "CTR1", "F": "FRM1"})
    pln = ET.SubElement(pfd, "PLN", {"A": "1"})
    for i, ring in enumerate(boundary["coordinates"]):
        lsg = ET.SubElement(pln, "LSG", {"A": "1" if i == 0 else "2"})
        for lon, lat in ring:
            ET.SubElement(lsg, "PNT", {"A": "2", "C": f"{lat:.9f}", "D": f"{lon:.9f}"})
    ET.SubElement(root, "PDT", {"A": "PDT1", "B": g.product[:32]})
    tsk = ET.SubElement(root, "TSK", {"A": "TSK1", "B": f"{field_name} {g.product}"[:32],
                                      "C": "CTR1", "D": "FRM1", "E": "PFD1", "G": "1",
                                      "H": "1", "I": "2", "J": "2"})
    tz1 = ET.SubElement(tsk, "TZN", {"A": "1", "B": "prescription"})
    ET.SubElement(tz1, "PDV", {"A": ddi, "B": "0", "C": "PDT1"})
    tz2 = ET.SubElement(tsk, "TZN", {"A": "2", "B": "off"})
    ET.SubElement(tz2, "PDV", {"A": ddi, "B": "0", "C": "PDT1"})
    north_deg, east_deg = g.cell_deg
    ET.SubElement(tsk, "GRD", {
        "A": f"{g.origin[0]:.9f}", "B": f"{g.origin[1]:.9f}",
        "C": f"{north_deg:.12f}", "D": f"{east_deg:.12f}",
        "E": str(g.cols), "F": str(g.rows), "G": grid_file, "H": str(len(binary)),
        "I": "2", "J": "1",
    })
    xml = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
    return xml, binary


def read_grid(xml: bytes, binary: bytes) -> tuple[dict, np.ndarray]:
    """Parse our own output back: (GRD attributes, rates in the task's units)."""
    root = ET.fromstring(xml)
    grd = root.find("TSK/GRD")
    if grd is None:
        raise ValueError("no GRD in task")
    cols, rows = int(grd.get("E", 0)), int(grd.get("F", 0))
    if len(binary) != int(grd.get("H", -1)) or len(binary) != rows * cols * 4:
        raise ValueError("grid binary length does not match GRD")
    vals = np.array(struct.unpack(f"<{rows * cols}i", binary)).reshape(rows, cols) / 100.0
    return dict(grd.attrib), vals
