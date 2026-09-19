"""Battery/energy/water/application analytics + KPI API (§130–134).

Transparent formulas only — no fake health score.
"""
from __future__ import annotations

from typing import Any, Optional


def battery_analytics(store: Any) -> dict[str, Any]:
    """§130 full pack identity from DeviceHealth seed."""
    rows = []
    for device_id, h in store.health.items():
        if h.battery_pct is None and getattr(h, "pack_id", None) is None:
            # fall back to device telemetry
            d = store.devices.get(device_id)
            if d is None or d.battery_pct is None:
                continue
            rows.append({
                "device_id": device_id,
                "battery_pct": d.battery_pct,
                "pack_id": None,
                "cycles": None,
                "soh": None,
                "formula": "battery_pct from Device telemetry (no DeviceHealth pack)",
                "synthetic": d.synthetic,
            })
            continue
        rows.append({
            "device_id": device_id,
            "battery_pct": h.battery_pct,
            "pack_id": h.pack_id,
            "cycles": h.cycles,
            "soh": h.soh,
            "formula": "pack_id/cycles/soh/battery_pct from DeviceHealth",
            "synthetic": h.synthetic,
        })
    return {"metric": "battery", "items": rows, "stub": False, "synthetic": True}


def energy_analytics(store: Any) -> dict[str, Any]:
    """§131 energy_per_mission from seeded mission log."""
    logs = list(getattr(store, "mission_energy", []) or [])
    per_mission = [
        {
            "mission_id": m.mission_id,
            "vehicle_id": m.vehicle_id,
            "energy_kwh": m.energy_kwh,
            "duration_s": m.duration_s,
            "ts": m.ts,
            "synthetic": m.synthetic,
        }
        for m in logs
    ]
    total = sum(m.energy_kwh for m in logs)
    return {
        "metric": "energy",
        "energy_per_mission": per_mission,
        "kwh_total": round(total, 4),
        "mission_count": len(logs),
        "formula": "sum(MissionEnergyLog.energy_kwh) / per-mission list from seed",
        "stub": False,
        "synthetic": True,
    }


# Back-compat alias
def energy_analytics_stub(store: Any) -> dict[str, Any]:
    return energy_analytics(store)


def water_analytics(store: Any) -> dict[str, Any]:
    """§132 commanded vs measured + mismatch alert hook."""
    events = []
    mismatches = []
    total = 0.0
    for e in store.water_usage:
        commanded = e.commanded_volume_l
        measured = e.measured_volume_l if e.measured_volume_l is not None else e.volume_l
        volume = e.volume_l
        total += volume
        mismatch = None
        if commanded is not None and measured is not None:
            delta = measured - commanded
            mismatch = {
                "delta_l": round(delta, 3),
                "pct": round(100.0 * delta / commanded, 2) if commanded else None,
                "alert": abs(delta) > max(5.0, 0.1 * abs(commanded)),
            }
            if mismatch["alert"]:
                mismatches.append({
                    "event_id": e.event_id,
                    "zone_id": e.zone_id,
                    **mismatch,
                })
        events.append({
            "event_id": e.event_id,
            "zone_id": e.zone_id,
            "volume_l": volume,
            "commanded_volume_l": commanded,
            "measured_volume_l": measured,
            "mismatch": mismatch,
            "synthetic": e.synthetic,
        })
    return {
        "metric": "water",
        "usage_events": len(events),
        "volume_l_total": total,
        "events": events,
        "mismatches": mismatches,
        "mismatch_alert_hook": "raise AlertCategory.WATER when mismatch.alert",
        "formula": "commanded_volume_l vs measured_volume_l; alert if |delta| > max(5L, 10%)",
        "stub": False,
        "synthetic": True,
    }


def application_analytics(store: Any) -> dict[str, Any]:
    """§133 weeds detected/treated/skipped from sim vision + treatment events."""
    events = list(getattr(store, "vision_events", []) or [])
    detected = sum(1 for e in events if e.kind in ("weed_detected", "detected"))
    treated = sum(1 for e in events if e.kind in ("treated", "weed_treated"))
    skipped = sum(1 for e in events if e.kind in ("skipped", "weed_skipped"))
    return {
        "metric": "application",
        "weeds_detected": detected,
        "weeds_treated": treated,
        "weeds_skipped": skipped,
        "events": [e.to_dict() for e in events],
        "ha_treated": round(treated * 0.001, 4),  # sim cell area proxy
        "formula": "count(VisionTreatmentEvent.kind) from sim vision + treatment",
        "stub": False,
        "synthetic": True,
    }


def application_analytics_stub(store: Any) -> dict[str, Any]:
    return application_analytics(store)


def kpi_page(store: Any) -> dict[str, Any]:
    """§134 KPI page — transparent formulas, NO fake health score."""
    open_alerts = len([a for a in store.alerts.list_alerts() if a.state.value != "RESOLVED"])
    online = sum(1 for h in store.health.values() if h.online)
    devices = len(store.devices)
    soil_n = len(store.soil)
    wx_n = len(store.weather)
    return {
        "banner": "SIMULATION" if store.simulation_mode else None,
        "simulation": store.simulation_mode,
        "kpis": [
            {"id": "devices_online", "label": "Devices online", "value": online,
             "formula": "count(DeviceHealth.online==True)"},
            {"id": "device_total", "label": "Devices total", "value": devices,
             "formula": "count(Device)"},
            {"id": "open_alerts", "label": "Open alerts", "value": open_alerts,
             "formula": "count(Alert.state != RESOLVED)"},
            {"id": "weather_obs", "label": "Weather observations", "value": wx_n,
             "formula": "count(WeatherObservation)"},
            {"id": "soil_obs", "label": "Soil observations", "value": soil_n,
             "formula": "count(SoilObservation)"},
        ],
        "note": "No composite health score — formulas are explicit per KPI",
        "health_score": None,
    }
