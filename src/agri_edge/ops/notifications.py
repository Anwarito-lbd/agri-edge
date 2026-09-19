"""NotificationProvider interface + adapters (§98)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .types import Alert


@dataclass
class NotificationResult:
    ok: bool
    channel: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "channel": self.channel, "detail": self.detail}


class NotificationProvider(ABC):
    @abstractmethod
    def send(self, alert: Alert, *, recipient: str = "ops") -> NotificationResult:
        ...


class DashboardNotificationProvider(NotificationProvider):
    """In-process dashboard feed stub."""

    def __init__(self) -> None:
        self.feed: list[dict[str, Any]] = []

    def send(self, alert: Alert, *, recipient: str = "ops") -> NotificationResult:
        item = {"recipient": recipient, "alert": alert.to_dict()}
        self.feed.append(item)
        return NotificationResult(ok=True, channel="dashboard", detail=f"queued for {recipient}")


class LogNotificationProvider(NotificationProvider):
    def __init__(self) -> None:
        self.logs: list[str] = []

    def send(self, alert: Alert, *, recipient: str = "ops") -> NotificationResult:
        line = f"[{alert.severity.value}] {alert.title}: {alert.message} -> {recipient}"
        self.logs.append(line)
        return NotificationResult(ok=True, channel="log", detail=line)


class MultiplexNotificationProvider(NotificationProvider):
    def __init__(self, providers: list[NotificationProvider] | None = None) -> None:
        self.providers = providers or []

    def send(self, alert: Alert, *, recipient: str = "ops") -> NotificationResult:
        details = []
        ok = True
        for p in self.providers:
            r = p.send(alert, recipient=recipient)
            details.append(f"{r.channel}:{r.ok}")
            ok = ok and r.ok
        return NotificationResult(ok=ok, channel="multiplex", detail=",".join(details))
