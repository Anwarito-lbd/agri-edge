"""Maintenance engine + alerts (§128–129)."""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Optional

from .types import AlertCategory, AlertSeverity, CalibrationRecord, new_id, utcnow
from .alerts import AlertEngine


@dataclass
class MaintenanceSchedule:
    schedule_id: str
    device_id: str
    title: str
    interval_days: float
    last_done: Optional[str] = None
    next_due: Optional[str] = None
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def days_between(iso_a: str, iso_b: Optional[str] = None) -> float:
    a = datetime.fromisoformat(iso_a.replace("Z", "+00:00"))
    b = datetime.fromisoformat((iso_b or utcnow().isoformat()).replace("Z", "+00:00"))
    return (b - a).total_seconds() / 86400.0


def check_calibration_due(
    records: list[CalibrationRecord],
    engine: AlertEngine,
    *,
    max_days: float = 365.0,
) -> list[dict[str, Any]]:
    out = []
    for rec in records:
        if not rec.next_due and not rec.calibrated_at:
            continue
        ref = rec.next_due or rec.calibrated_at
        # if next_due in past relative to now
        overdue = False
        try:
            due = datetime.fromisoformat(ref.replace("Z", "+00:00"))
            overdue = due < datetime.now(timezone.utc)
        except ValueError:
            overdue = days_between(rec.calibrated_at) > max_days
        if overdue or days_between(rec.calibrated_at) > max_days:
            alert = engine.raise_alert(
                severity=AlertSeverity.WARNING,
                category=AlertCategory.MAINTENANCE,
                title="Calibration overdue",
                message=f"Device {rec.device_id} calibration overdue",
                source_key=f"maint:cal:{rec.device_id}",
                device_id=rec.device_id,
                synthetic=rec.synthetic,
            )
            out.append({"device_id": rec.device_id, "alert_id": alert.alert_id, "overdue": True})
    return out


def default_schedules() -> list[MaintenanceSchedule]:
    return [
        MaintenanceSchedule(
            schedule_id="ms1",
            device_id="soil1",
            title="Soil probe calibration",
            interval_days=365,
            last_done="2025-01-01T00:00:00+00:00",
            next_due="2026-01-01T00:00:00+00:00",
            synthetic=True,
        ),
        MaintenanceSchedule(
            schedule_id="ms2",
            device_id="wx1",
            title="Weather station service",
            interval_days=180,
            last_done="2026-06-01T00:00:00+00:00",
            next_due="2026-12-01T00:00:00+00:00",
            synthetic=True,
        ),
    ]
