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
        "zones": zone_table(store),
        # Latest controller STATE received over ground MQTT (read-only mirror).
        "controller_state": list((getattr(store, "irrigation_state", None) or {}).values()),
        "safety": {
            "ai_unrestricted_pump": False,
            "command_channel": "mqtt_ground_only",
            "auto_execute": False,
        },
    }



def zone_table(store) -> list[dict]:
    """§157 zone rows for irrigation UI."""
    moist_by_zone: dict[str, list[float]] = {}
    for s in getattr(store, "soil", []) or []:
        z = getattr(s, "zone_id", None) or "zone_a"
        mp = getattr(s, "moisture_pct", None)
        if mp is not None:
            moist_by_zone.setdefault(z, []).append(float(mp))
    valve_by_zone = {v.zone_id: v for v in store.valves.values()}
    meter_by_zone = {}
    meters = getattr(store, "flow_meters", None) or getattr(store, "flow_meters", {})
    for m in meters.values():
        z = getattr(m, "zone_id", None)
        if z:
            meter_by_zone[z] = m
    zones = sorted(set(list(moist_by_zone) + list(valve_by_zone) + list(meter_by_zone)) or {"zone_a"})
    # pick rule function
    rule = globals().get("rule_based_irrigation") or globals().get("rule_based_irrigation")
    rows = []
    for z in zones:
        vals = moist_by_zone.get(z, [])
        avg = sum(vals) / len(vals) if vals else None
        rec = rule(moisture_pct=avg, zone_id=z) if rule else None
        v = valve_by_zone.get(z)
        fm = meter_by_zone.get(z)
        rows.append({
            "zone_id": z,
            "avg_moisture_pct": avg,
            "valve_id": getattr(v, "valve_id", None) if v else None,
            "valve_open_pct": getattr(v, "open_pct", None) if v else None,
            "flow_lpm": getattr(fm, "last_lpm", None) if fm else None,
            "recommendation": rec.to_dict() if rec and hasattr(rec, "to_dict") else None,
            "auto_execute": False,
            "synthetic": True,
        })
    return rows
