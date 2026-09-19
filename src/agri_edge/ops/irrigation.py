"""Irrigation dashboard + rule-based algorithm skeleton — no ML (§138–139).

SAFETY: irrigation commands = ground MQTT only. No AI→unrestricted pump.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional


@dataclass
class IrrigationRecommendation:
    zone_id: str
    action: str  # none|review|suggest_irrigate
    reason: str
    suggested_mm: float = 0.0
    auto_execute: bool = False  # always False
    channel: str = "mqtt_ground_only"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["auto_execute"] = False
        return d


def rule_based_irrigation(
    *,
    moisture_pct: Optional[float],
    threshold_low: float = 20.0,
    threshold_high: float = 40.0,
    zone_id: str = "zone_a",
    frost_level: str = "none",
) -> IrrigationRecommendation:
    """Simple threshold rules — skeleton only, never auto-executes."""
    if frost_level in ("light", "hard", "watch"):
        return IrrigationRecommendation(
            zone_id=zone_id,
            action="none",
            reason="Frost workflow active — do not auto-irrigate",
            suggested_mm=0.0,
        )
    if moisture_pct is None:
        return IrrigationRecommendation(zone_id=zone_id, action="review", reason="Missing soil moisture")
    if moisture_pct < threshold_low:
        return IrrigationRecommendation(
            zone_id=zone_id,
            action="suggest_irrigate",
            reason=f"Moisture {moisture_pct}% < {threshold_low}%",
            suggested_mm=10.0,
        )
    if moisture_pct > threshold_high:
        return IrrigationRecommendation(
            zone_id=zone_id,
            action="none",
            reason=f"Moisture {moisture_pct}% above high threshold",
        )
    return IrrigationRecommendation(zone_id=zone_id, action="none", reason="Moisture in band")


def irrigation_dashboard(store: Any) -> dict[str, Any]:
    moistures = [s.moisture_pct for s in store.soil if s.moisture_pct is not None]
    avg = sum(moistures) / len(moistures) if moistures else None
    rec = rule_based_irrigation(moisture_pct=avg)
    return {
        "simulation": getattr(store, "simulation_mode", True),
        "banner": "SIMULATION",
        "tanks": [t.to_dict() for t in store.tanks.values()],
        "pumps": [p.to_dict() for p in store.pumps.values()],
        "valves": [v.to_dict() for v in store.valves.values()],
        "flow_meters": [f.to_dict() for f in store.flow_meters.values()],
        "avg_moisture_pct": avg,
        "recommendation": rec.to_dict(),
        "safety": {
            "ai_unrestricted_pump": False,
            "command_channel": "mqtt_ground_only",
            "auto_execute": False,
        },
    }
