"""Variable-rate prescription + safety + feedback maps (§105–109, §158)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .geo import feature, feature_collection
from .types import new_id, utcnow


@dataclass
class SafetyConstraints:
    """Hard limits — fail closed."""
    max_rate_l_ha: float = 200.0
    min_rate_l_ha: float = 0.0
    geofence_required: bool = True
    wind_max_ms: float = 5.0
    buffer_m: float = 10.0
    treatment_gate_required: bool = True
    no_ai_unrestricted_pump: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VariableRatePrescription:
    prescription_id: str
    field_id: str
    product: str
    created_at: str
    cells: list[dict[str, Any]] = field(default_factory=list)
    constraints: SafetyConstraints = field(default_factory=SafetyConstraints)
    synthetic: bool = True
    validated: bool = False
    approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["constraints"] = self.constraints.to_dict()
        return d


def validate_prescription(rx: VariableRatePrescription, *, wind_ms: Optional[float] = None) -> dict[str, Any]:
    """Weather-aware mission validation (§109) — recommend only."""
    issues: list[str] = []
    c = rx.constraints
    for cell in rx.cells:
        rate = float(cell.get("rate_l_ha", 0))
        if rate > c.max_rate_l_ha:
            issues.append(f"rate {rate} exceeds max {c.max_rate_l_ha}")
        if rate < c.min_rate_l_ha:
            issues.append(f"rate {rate} below min {c.min_rate_l_ha}")
    if c.geofence_required and not rx.validated:
        issues.append("geofence/treatment gate not validated")
    # No wind reading is not calm. An application decision made without one is
    # a guess, so the gate fails closed on a missing value exactly as it does
    # on a high one.
    if wind_ms is None:
        issues.append("no wind reading: cannot confirm wind below limit")
    elif wind_ms > c.wind_max_ms:
        issues.append(f"wind {wind_ms} m/s exceeds {c.wind_max_ms}")
    if not c.no_ai_unrestricted_pump:
        issues.append("safety: AI unrestricted pump must remain blocked")
    ok = len(issues) == 0
    return {
        "ok": ok,
        "issues": issues,
        "auto_apply": False,
        "prescription_id": rx.prescription_id,
        "synthetic": rx.synthetic,
    }


def approve_prescription(
    rx: VariableRatePrescription,
    *,
    actor: str = "operator",
    wind_ms: Optional[float] = None,
) -> dict[str, Any]:
    """§158 — safety validate on approve; never auto-apply.

    Approval never marks a prescription validated. Until 24 Sept 2026 this
    took ``force_validated=True`` by default and set ``rx.validated`` before
    checking it, so the geofence/treatment-gate condition could not fail and
    every prescription was approvable. ``validated`` must be earned by a
    separate geofence check, not asserted by the act of approving.
    """
    result = validate_prescription(rx, wind_ms=wind_ms)
    if not result["ok"]:
        return {**result, "approved": False, "actor": actor}
    rx.approved = True
    rx.approved_by = actor
    rx.approved_at = utcnow().isoformat()
    return {
        **result,
        "approved": True,
        "actor": actor,
        "approved_at": rx.approved_at,
        "auto_apply": False,
    }


def list_cells(rx: VariableRatePrescription) -> dict[str, Any]:
    return {
        "prescription_id": rx.prescription_id,
        "field_id": rx.field_id,
        "cells": list(rx.cells),
        "count": len(rx.cells),
        "approved": rx.approved,
        "synthetic": rx.synthetic,
    }


def make_demo_prescription(field_id: str = "field_north") -> VariableRatePrescription:
    return VariableRatePrescription(
        prescription_id=new_id("vra_"),
        field_id=field_id,
        product="water_demo",
        created_at=utcnow().isoformat(),
        cells=[
            {"lat": 45.401, "lon": -75.698, "rate_l_ha": 50.0, "cell_id": "c1"},
            {"lat": 45.402, "lon": -75.697, "rate_l_ha": 80.0, "cell_id": "c2"},
            {"lat": 45.403, "lon": -75.696, "rate_l_ha": 40.0, "cell_id": "c3"},
        ],
        synthetic=True,
        validated=False,
    )


def feedback_maps(
    prescription_id: str,
    cells: Optional[list[dict[str, Any]]] = None,
    *,
    actual_scale: float = 0.92,
) -> dict[str, Any]:
    """§108 commanded / actual / error GeoJSON FeatureCollections from sim segments."""
    cells = cells or [
        {"lat": 45.401, "lon": -75.698, "rate_l_ha": 50.0, "cell_id": "c1"},
        {"lat": 45.402, "lon": -75.697, "rate_l_ha": 80.0, "cell_id": "c2"},
        {"lat": 45.403, "lon": -75.696, "rate_l_ha": 40.0, "cell_id": "c3"},
    ]
    commanded_feats = []
    actual_feats = []
    error_feats = []
    for i, cell in enumerate(cells):
        lat = float(cell["lat"])
        lon = float(cell["lon"])
        commanded = float(cell.get("rate_l_ha", 0))
        # sim segment: slight under-application + small spatial jitter
        actual = round(commanded * actual_scale + (i % 2) * 0.5, 2)
        err = round(actual - commanded, 2)
        cid = cell.get("cell_id", f"seg_{i}")
        geom = {"type": "Point", "coordinates": [lon, lat]}
        commanded_feats.append(
            feature(geom, {"cell_id": cid, "kind": "commanded", "rate_l_ha": commanded, "synthetic": True}, cid)
        )
        actual_feats.append(
            feature(
                {"type": "Point", "coordinates": [lon + 0.00005 * i, lat]},
                {"cell_id": cid, "kind": "actual", "rate_l_ha": actual, "synthetic": True},
                f"{cid}_act",
            )
        )
        error_feats.append(
            feature(geom, {"cell_id": cid, "kind": "error", "error_l_ha": err, "synthetic": True}, f"{cid}_err")
        )
    return {
        "prescription_id": prescription_id,
        "commanded": feature_collection(commanded_feats),
        "actual": feature_collection(actual_feats),
        "error": feature_collection(error_feats),
        "origin": "DERIVED",
        "algorithm_version": "vra_feedback_sim_v1",
        "stub": False,
        "synthetic": True,
    }


# Back-compat alias
def feedback_map_stub(prescription_id: str) -> dict[str, Any]:
    return feedback_maps(prescription_id)
