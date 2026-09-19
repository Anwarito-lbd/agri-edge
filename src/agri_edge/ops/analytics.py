"""Battery/energy/water/application analytics stubs + KPI API (§130–134).

Transparent formulas only — no fake health score.
"""
from __future__ import annotations

from typing import Any, Optional


def battery_analytics(store: Any) -> dict[str, Any]:
    rows = []
    for d in store.devices.values():
        if d.battery_pct is None:
            continue
        rows.append({
            "device_id": d.device_id,
            "battery_pct": d.battery_pct,
            "formula": "battery_pct from last DeviceHealth/Device telemetry",
            "synthetic": d.synthetic,
        })
    return {"metric": "battery", "items": rows, "stub": True}


def energy_analytics_stub(store: Any) -> dict[str, Any]:
    return {
        "metric": "energy",
        "kwh_today": None,
        "formula": "sum(energy_meter.kwh) — no meters in sim yet",
        "stub": True,
        "synthetic": True,
    }


def water_analytics(store: Any) -> dict[str, Any]:
    total = sum(e.volume_l for e in store.water_usage)
    return {
        "metric": "water",
        "usage_events": len(store.water_usage),
        "volume_l_total": total,
        "formula": "sum(WaterUsageEvent.volume_l)",
        "stub": len(store.water_usage) == 0,
        "synthetic": True,
    }


def application_analytics_stub(store: Any) -> dict[str, Any]:
    return {
        "metric": "application",
        "ha_treated": None,
        "formula": "sum(prescription.applied_ha) from field logs",
        "stub": True,
        "synthetic": True,
    }


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
            {
                "id": "devices_online",
                "label": "Devices online",
                "value": online,
                "formula": "count(DeviceHealth.online==True)",
            },
            {
                "id": "device_total",
                "label": "Devices total",
                "value": devices,
                "formula": "count(Device)",
            },
            {
                "id": "open_alerts",
                "label": "Open alerts",
                "value": open_alerts,
                "formula": "count(Alert.state != RESOLVED)",
            },
            {
                "id": "weather_obs",
                "label": "Weather observations",
                "value": wx_n,
                "formula": "count(WeatherObservation)",
            },
            {
                "id": "soil_obs",
                "label": "Soil observations",
                "value": soil_n,
                "formula": "count(SoilObservation)",
            },
        ],
        "note": "No composite health score — formulas are explicit per KPI",
        "health_score": None,
    }
