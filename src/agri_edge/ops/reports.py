"""Tasks timeline reports daily brief — factual data only (§145–148)."""
from __future__ import annotations

from typing import Any

from .types import utcnow
from .schema import TimelineEvent


def build_timeline(store: Any) -> list[dict[str, Any]]:
    events: list[TimelineEvent] = list(store.timeline)
    for a in store.alerts.list_alerts()[:20]:
        events.append(
            TimelineEvent(
                event_id=f"tl_alert_{a.alert_id}",
                ts=a.created_at,
                kind="alert",
                summary=f"{a.severity.value}: {a.title}",
                ref_id=a.alert_id,
                synthetic=a.synthetic,
            )
        )
    for w in store.weather[-5:]:
        events.append(
            TimelineEvent(
                event_id=f"tl_wx_{w.obs_id}",
                ts=w.ts,
                kind="weather",
                summary=f"Weather obs {w.station_id}",
                ref_id=w.obs_id,
                synthetic=w.synthetic,
            )
        )
    events.sort(key=lambda e: e.ts, reverse=True)
    return [e.to_dict() for e in events]


def daily_brief(store: Any) -> dict[str, Any]:
    """§148 — from factual store data only; no invented narrative scores."""
    ov = store.overview()
    open_alerts = [a.to_dict() for a in store.alerts.list_alerts() if a.state.value != "RESOLVED"]
    latest_wx = store.weather[-1].to_dict() if store.weather else None
    return {
        "date": utcnow().date().isoformat(),
        "simulation": store.simulation_mode,
        "banner": "SIMULATION" if store.simulation_mode else None,
        "facts": {
            "devices": ov["device_count"],
            "open_alerts": ov["open_alerts"],
            "weather_obs": ov["weather_count"],
            "soil_obs": ov["soil_count"],
            "tasks_open": ov["tasks_open"],
        },
        "latest_weather": latest_wx,
        "open_alert_titles": [a["title"] for a in open_alerts],
        "note": "Brief lists factual counts only; no generated prose claims",
    }


def report_summary(store: Any) -> dict[str, Any]:
    return {
        "generated_at": utcnow().isoformat(),
        "simulation": store.simulation_mode,
        "sections": {
            "overview": store.overview(),
            "alerts": [a.to_dict() for a in store.alerts.list_alerts()],
            "tasks": [t.to_dict() for t in store.tasks.values()],
            "timeline": build_timeline(store)[:50],
        },
    }
