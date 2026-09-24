"""Notice a field device that has gone quiet.

The registry (`iot/provision.py`, devices.json) says which devices should be
reporting and how often. A device silent for three of its intervals raises a
DEVICE alert; one that has never reported at all is flagged too. Without this a
dead soil probe looks exactly like a field that has not changed.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..iot.provision import load_registry
from .store import OpsStore
from .types import AlertCategory, AlertSeverity

DEFAULT_REGISTRY = Path(__file__).resolve().parents[3] / "ground_iot" / "mosquitto" / "devices.json"


def registry_path() -> Path:
    return Path(os.environ.get("AGRIEDGE_DEVICE_REGISTRY") or DEFAULT_REGISTRY)


def check(store: OpsStore, registry: dict | None = None, now: datetime | None = None) -> list[dict]:
    registry = registry if registry is not None else load_registry(registry_path())
    now = now or datetime.now(timezone.utc)
    out = []
    for dev_id, d in sorted(registry.items()):
        interval = int(d.get("interval_s") or 900)
        seen = store.devices.get(dev_id)
        last = None
        if seen and seen.last_seen:
            try:
                last = datetime.fromisoformat(seen.last_seen)
            except ValueError:
                last = None
        silent = last is None or now - last > timedelta(seconds=3 * interval)
        status = {"device_id": dev_id, "kind": d.get("kind"), "zone": d.get("zone"),
                  "last_seen": last.isoformat() if last else None, "online": not silent}
        out.append(status)
        if silent:
            what = "has never reported" if last is None else f"last reported {last.isoformat()}"
            store.alerts.raise_alert(
                severity=AlertSeverity.WARNING, category=AlertCategory.DEVICE,
                title=f"{dev_id} is silent",
                message=f"{d.get('kind')} device in zone {d.get('zone')} {what}; expected every "
                        f"{interval // 60} min. Check its battery, radio and mounting.",
                source_key=f"device:offline:{dev_id}", device_id=dev_id,
                farm_id=str(d.get("farm") or "farm"),
            )
    return out
