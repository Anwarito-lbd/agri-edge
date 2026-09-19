"""Variable-rate prescription + safety constraints + feedback stubs (§105–109)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .types import new_id, utcnow


@dataclass
class SafetyConstraints:
    """Hard limits — fail closed."""
    max_rate_l_ha: float = 200.0
    min_rate_l_ha: float = 0.0
    geofence_required: bool = True
    wind_max_ms: float = 5.0
    buffer_m: float = 10.0
    treatment_gate_required: bool = True  # validated_locally + geofence + arm + freshness
    no_ai_unrestricted_pump: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VariableRatePrescription:
    prescription_id: str
    field_id: str
    product: str
    created_at: str
    cells: list[dict[str, Any]] = field(default_factory=list)  # [{lat,lon,rate_l_ha}]
    constraints: SafetyConstraints = field(default_factory=SafetyConstraints)
    synthetic: bool = True
    validated: bool = False

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
    if wind_ms is not None and wind_ms > c.wind_max_ms:
        issues.append(f"wind {wind_ms} m/s exceeds {c.wind_max_ms}")
    ok = len(issues) == 0
    return {
        "ok": ok,
        "issues": issues,
        "auto_apply": False,
        "prescription_id": rx.prescription_id,
        "synthetic": rx.synthetic,
    }


def make_demo_prescription(field_id: str = "field_north") -> VariableRatePrescription:
    return VariableRatePrescription(
        prescription_id=new_id("vra_"),
        field_id=field_id,
        product="water_demo",
        created_at=utcnow().isoformat(),
        cells=[
            {"lat": 45.401, "lon": -75.698, "rate_l_ha": 50.0},
            {"lat": 45.402, "lon": -75.697, "rate_l_ha": 80.0},
        ],
        synthetic=True,
        validated=False,
    )


def feedback_map_stub(prescription_id: str) -> dict[str, Any]:
    """§108 applied vs prescribed feedback map stub."""
    return {
        "prescription_id": prescription_id,
        "type": "FeatureCollection",
        "features": [],
        "stub": True,
        "synthetic": True,
        "note": "Feedback maps require field application logs — stub only",
    }
