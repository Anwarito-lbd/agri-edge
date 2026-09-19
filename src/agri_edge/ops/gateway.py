"""Offline gateway model + sync-without-dupe stub (§117–118).

Transport abstraction note: Ops Station is transport-agnostic (MQTT/HTTP/LoRa);
gateway buffers when uplink is down and syncs with idempotent keys.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .types import new_id, utcnow


TRANSPORT_NOTE = (
    "§117 Transport abstraction: domain models do not depend on MQTT vs HTTP vs LoRa. "
    "Adapters publish/subscribe; Ops Station consumes normalized observations."
)


@dataclass
class BufferedMessage:
    msg_id: str
    idempotency_key: str
    topic: str
    payload: dict[str, Any]
    created_at: str
    synced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OfflineGateway:
    """§118 offline buffer with sync-without-dupe via idempotency_key."""

    def __init__(self) -> None:
        self.buffer: list[BufferedMessage] = []
        self._seen_keys: set[str] = set()
        self.online = True

    def enqueue(self, topic: str, payload: dict[str, Any], *, idempotency_key: Optional[str] = None) -> BufferedMessage:
        key = idempotency_key or payload.get("obs_id") or payload.get("reading_id") or new_id("ik_")
        if key in self._seen_keys:
            # duplicate — return existing
            for m in self.buffer:
                if m.idempotency_key == key:
                    return m
        msg = BufferedMessage(
            msg_id=new_id("gw_"),
            idempotency_key=str(key),
            topic=topic,
            payload=payload,
            created_at=utcnow().isoformat(),
            synced=False,
        )
        self.buffer.append(msg)
        self._seen_keys.add(str(key))
        return msg

    def sync(self) -> dict[str, Any]:
        """Mark unsynced messages as synced; skip dupes by key."""
        synced = 0
        skipped = 0
        seen_this_pass: set[str] = set()
        for m in self.buffer:
            if m.synced:
                continue
            if m.idempotency_key in seen_this_pass:
                skipped += 1
                m.synced = True
                continue
            seen_this_pass.add(m.idempotency_key)
            m.synced = True
            synced += 1
        return {"synced": synced, "skipped_dupes": skipped, "online": self.online, "transport_note": TRANSPORT_NOTE}

    def status(self) -> dict[str, Any]:
        return {
            "online": self.online,
            "buffered": len(self.buffer),
            "unsynced": sum(1 for m in self.buffer if not m.synced),
            "transport_note": TRANSPORT_NOTE,
        }
