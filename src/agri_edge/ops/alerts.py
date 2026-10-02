"""Alert engine: rules, severities, categories, dedupe, ACK/RESOLVE/ESCALATE (§83, §93–99)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


class InvalidTransition(ValueError):
    """An alert action that its current state does not allow."""


# RESOLVED is terminal for operator actions: acknowledging a resolved alert used
# to flip it back to ACKNOWLEDGED, so a late click on a stale page re-opened
# something already dealt with. A condition that recurs re-opens it through
# raise_alert instead, where the source says so.
_ALLOWED: dict[str, set[AlertState]] = {
    "ack": {AlertState.OPEN, AlertState.ESCALATED},
    "resolve": {AlertState.OPEN, AlertState.ACKNOWLEDGED, AlertState.ESCALATED},
    "escalate": {AlertState.OPEN, AlertState.ACKNOWLEDGED},
}


class AlertEngine:
    """§93–99 Alert engine with dedupe window.

    ``dedupe_seconds`` is how long after resolution a recurrence of the same
    source re-opens that alert instead of raising a new one -- so a sensor
    flapping around a threshold produces one alert with a reopen count, not an
    alert storm. Recurrence is never suppressed: a frost alert that comes back
    must be seen.
    """

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
            if existing.state == AlertState.RESOLVED and self._within_dedupe(existing):
                existing.state = AlertState.OPEN
                existing.updated_at = utcnow().isoformat()
                existing.message = message
                existing.severity = severity
                existing.meta["reopened"] = int(existing.meta.get("reopened", 0)) + 1
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

    def _within_dedupe(self, alert: Alert) -> bool:
        try:
            resolved_at = datetime.fromisoformat(alert.updated_at)
        except (TypeError, ValueError):
            return False
        return (utcnow() - resolved_at).total_seconds() <= self.dedupe_seconds

    def _transition(self, alert_id: str, action: str) -> Alert:
        a = self._require(alert_id)
        if a.state not in _ALLOWED[action]:
            raise InvalidTransition(f"cannot {action} alert {alert_id} in state {a.state.value}")
        return a

    def ack(self, alert_id: str, by: str) -> Alert:
        a = self._transition(alert_id, "ack")
        a.state = AlertState.ACKNOWLEDGED
        a.ack_by = by
        a.updated_at = utcnow().isoformat()
        return a

    def resolve(self, alert_id: str, by: str) -> Alert:
        a = self._transition(alert_id, "resolve")
        a.state = AlertState.RESOLVED
        a.resolved_by = by
        a.updated_at = utcnow().isoformat()
        return a

    def escalate(self, alert_id: str, by: str) -> Alert:
        a = self._transition(alert_id, "escalate")
        a.state = AlertState.ESCALATED
        a.updated_at = utcnow().isoformat()
        a.meta["escalated_by"] = by
        # bump severity one step if possible
        order = [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY]
        idx = order.index(a.severity) if a.severity in order else 0
        a.severity = order[min(idx + 1, len(order) - 1)]
        return a

    def resolve_by_source(self, source_key: str, by: str) -> Optional[Alert]:
        """Resolve the live alert for `source_key`, if any (a condition that cleared)."""
        aid = self._by_source.get(source_key)
        a = self._alerts.get(aid) if aid else None
        if a is None or a.state == AlertState.RESOLVED:
            return None
        return self.resolve(a.alert_id, by)

    def list_alerts(self, state: Optional[AlertState] = None) -> list[Alert]:
        items = list(self._alerts.values())
        if state:
            items = [a for a in items if a.state == state]
        return sorted(items, key=lambda a: a.created_at, reverse=True)

    def _require(self, alert_id: str) -> Alert:
        if alert_id not in self._alerts:
            raise KeyError(f"unknown alert {alert_id}")
        return self._alerts[alert_id]
