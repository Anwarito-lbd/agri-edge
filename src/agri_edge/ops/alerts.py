"""Alert engine: rules, severities, categories, dedupe, ACK/RESOLVE/ESCALATE (§83, §93–99)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .types import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertState,
    TempKind,
    TypedTemperature,
    new_id,
    utcnow,
)


@dataclass
class AlertRule:
    rule_id: str
    category: AlertCategory
    severity: AlertSeverity
    title: str
    source_key_template: str
    predicate: Callable[[dict[str, Any]], bool]
    message_fn: Callable[[dict[str, Any]], str]


# §83 temperature alert thresholds (by TempKind)
TEMP_RULES = {
    TempKind.AIR: {"frost_watch": 2.0, "frost": 0.0, "heat": 35.0},
    TempKind.SOIL: {"cold": 5.0, "hot": 40.0},
    TempKind.CANOPY: {"frost": 0.0, "heat": 38.0},
    TempKind.WATER: {"cold": 2.0, "hot": 30.0},
}


class AlertEngine:
    """§93–99 Alert engine with dedupe window."""

    def __init__(self, dedupe_seconds: float = 600.0) -> None:
        self.dedupe_seconds = dedupe_seconds
        self._alerts: dict[str, Alert] = {}
        self._by_source: dict[str, str] = {}  # source_key -> alert_id

    def evaluate_temperature(
        self,
        temp: TypedTemperature,
        *,
        device_id: str = "",
        farm_id: str = "demo_farm",
        synthetic: bool = False,
    ) -> Optional[Alert]:
        thresholds = TEMP_RULES.get(temp.kind, {})
        sev = None
        title = None
        msg = None
        key = None
        v = temp.value_c
        if temp.kind == TempKind.AIR:
            if v <= thresholds.get("frost", 0.0):
                sev, title = AlertSeverity.CRITICAL, "Air frost risk"
                msg = f"Air temperature {v}°C ≤ frost threshold"
                key = f"temp:air:frost:{device_id}"
            elif v <= thresholds.get("frost_watch", 2.0):
                sev, title = AlertSeverity.WARNING, "Air frost watch"
                msg = f"Air temperature {v}°C in frost watch band"
                key = f"temp:air:frost_watch:{device_id}"
            elif v >= thresholds.get("heat", 35.0):
                sev, title = AlertSeverity.WARNING, "Air heat stress"
                msg = f"Air temperature {v}°C ≥ heat threshold"
                key = f"temp:air:heat:{device_id}"
        elif temp.kind == TempKind.SOIL:
            if v <= thresholds.get("cold", 5.0):
                sev, title = AlertSeverity.INFO, "Soil cold"
                msg = f"Soil temperature {v}°C"
                key = f"temp:soil:cold:{device_id}"
            elif v >= thresholds.get("hot", 40.0):
                sev, title = AlertSeverity.WARNING, "Soil hot"
                msg = f"Soil temperature {v}°C"
                key = f"temp:soil:hot:{device_id}"
        if sev is None or key is None:
            return None
        return self.raise_alert(
            severity=sev,
            category=AlertCategory.WEATHER if temp.kind == TempKind.AIR else AlertCategory.SOIL,
            title=title or "Temperature alert",
            message=msg or "",
            source_key=key,
            device_id=device_id or None,
            farm_id=farm_id,
            synthetic=synthetic,
        )

    def raise_alert(
        self,
        *,
        severity: AlertSeverity,
        category: AlertCategory,
        title: str,
        message: str,
        source_key: str,
        device_id: Optional[str] = None,
        farm_id: str = "demo_farm",
        synthetic: bool = False,
        meta: Optional[dict[str, Any]] = None,
    ) -> Alert:
        # Dedupe: reuse open/ack alert with same source_key
        existing_id = self._by_source.get(source_key)
        if existing_id and existing_id in self._alerts:
            existing = self._alerts[existing_id]
            if existing.state in (AlertState.OPEN, AlertState.ACKNOWLEDGED, AlertState.ESCALATED):
                existing.updated_at = utcnow().isoformat()
                existing.message = message
                existing.severity = severity
                return existing
        alert = Alert(
            alert_id=new_id("al_"),
            severity=severity,
            category=category,
            title=title,
            message=message,
            source_key=source_key,
            device_id=device_id,
            farm_id=farm_id,
            synthetic=synthetic,
            meta=meta or {},
        )
        self._alerts[alert.alert_id] = alert
        self._by_source[source_key] = alert.alert_id
        return alert

    def ack(self, alert_id: str, by: str) -> Alert:
        a = self._require(alert_id)
        a.state = AlertState.ACKNOWLEDGED
        a.ack_by = by
        a.updated_at = utcnow().isoformat()
        return a

    def resolve(self, alert_id: str, by: str) -> Alert:
        a = self._require(alert_id)
        a.state = AlertState.RESOLVED
        a.resolved_by = by
        a.updated_at = utcnow().isoformat()
        return a

    def escalate(self, alert_id: str, by: str) -> Alert:
        a = self._require(alert_id)
        a.state = AlertState.ESCALATED
        a.updated_at = utcnow().isoformat()
        a.meta["escalated_by"] = by
        # bump severity one step if possible
        order = [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY]
        idx = order.index(a.severity) if a.severity in order else 0
        a.severity = order[min(idx + 1, len(order) - 1)]
        return a

    def list_alerts(self, state: Optional[AlertState] = None) -> list[Alert]:
        items = list(self._alerts.values())
        if state:
            items = [a for a in items if a.state == state]
        return sorted(items, key=lambda a: a.created_at, reverse=True)

    def _require(self, alert_id: str) -> Alert:
        if alert_id not in self._alerts:
            raise KeyError(f"unknown alert {alert_id}")
        return self._alerts[alert_id]
