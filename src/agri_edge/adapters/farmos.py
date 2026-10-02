"""FarmManagementAdapter interface + FarmOSAdapter stub.

STATUS: payload building SIMULATED; the HTTP path is IMPLEMENTED but only mock-tested
(`adapters/farmos_http.py`, `tests/test_farmos_http.py`) -- never run against a real farmOS.

`FarmOSAdapter` BUILDS farmOS JSON:API payloads and keeps them in an outbox. It makes
**no network call** unless constructed with a client AND `allow_network=True` -- two
deliberate opt-ins, because pushing logs to someone's farm record system is an
externally visible act. Reading fields/plantings (`list_fields`, `list_plantings`) is
gated by the same opt-in. Build a networked adapter with `FarmOSAdapter.from_config(cfg,
allow_network=True)`; see docs/operations/FARMOS_ADAPTER.md.

Payload construction reuses `store.farmos.sidecar_to_log` (already tested) for
observation logs, so there is one definition of "what a detection log looks like".
Licence boundary unchanged: farmOS is GPL-2.0, run unmodified as a separate server,
reached over HTTP only. No farmOS code is imported here.

Credentials: never in this module. A caller supplies a `FarmOSClient` built via
`FarmOSConfig.from_env`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agri_edge.store.farmos import sidecar_to_log

ADAPTER_STATUS = "SIMULATED"      # payload builders; see farmos_http.py for the (mock-tested) client


class FarmOSNetworkDisabled(RuntimeError):
    """Raised when something tries to send without the explicit network opt-in."""


@runtime_checkable
class FarmManagementAdapter(Protocol):
    """What the rest of agri-edge may ask of a farm management system."""

    name: str

    def build_observation_log(self, frame_meta: dict, *, land_asset_id: str = "") -> dict: ...

    def build_treatment_log(self, event: dict, *, land_asset_id: str = "") -> dict: ...

    def queue(self, payload: dict) -> int: ...

    def flush(self) -> list[str]: ...


@runtime_checkable
class FarmDataReader(Protocol):
    """Optional read side: what fields/plantings does the farm system hold?"""

    def list_fields(self) -> list: ...

    def list_plantings(self) -> list: ...


class FarmOSAdapter:
    name = "farmos"
    status = ADAPTER_STATUS

    def __init__(self, client: Any = None, *, allow_network: bool = False,
                 land_asset_id: str = "") -> None:
        self._client = client
        self.allow_network = bool(allow_network)
        self.land_asset_id = land_asset_id
        self.outbox: list[dict] = []
        self.sent_ids: list[str] = []

    @classmethod
    def from_config(cls, cfg: Any, *, allow_network: bool = False,
                    land_asset_id: str = "") -> "FarmOSAdapter":
        """Build an adapter around the real HTTP client.

        With `allow_network=False` (the default) no client is even constructed, so nothing
        can reach the network and credentials are not validated or touched.
        """
        if not allow_network:
            return cls(None, allow_network=False,
                       land_asset_id=land_asset_id or getattr(cfg, "land_asset_id", ""))
        from .farmos_http import FarmOSHttpClient     # lazy: keeps this module I/O-free

        return cls(FarmOSHttpClient(cfg), allow_network=True,
                   land_asset_id=land_asset_id or getattr(cfg, "land_asset_id", ""))

    @property
    def network_enabled(self) -> bool:
        return self._client is not None and self.allow_network

    def _require_network(self, what: str) -> None:
        if not self.network_enabled:
            raise FarmOSNetworkDisabled(
                f"FarmOSAdapter will not {what}: construct with a client AND allow_network=True.")

    # -- reads (network opt-in required) ----------------------------------------------
    def list_fields(self) -> list:
        self._require_network("read fields")
        return list(self._client.list_land_assets())

    def list_plantings(self) -> list:
        self._require_network("read plantings")
        return list(self._client.list_plant_assets())

    # -- payload builders (pure) -------------------------------------------------
    def build_observation_log(self, frame_meta: dict, *, land_asset_id: str = "") -> dict:
        return sidecar_to_log(frame_meta, land_asset_id or self.land_asset_id)

    def build_treatment_log(self, event: dict, *, land_asset_id: str = "") -> dict:
        """A `log--activity` for a (SIMULATED) treatment decision.

        Records what was decided and why, including refusals. `simulated` is stated in
        the notes so the record can never be mistaken for an actual application.
        """
        kind = str(event.get("kind", "unknown"))
        reasons = event.get("reasons") or []
        lat, lon = event.get("lat"), event.get("lon")
        notes = [
            f"agri-edge treatment event: {kind}",
            f"detection {event.get('detection_id', '?')} ({event.get('label', '?')}, "
            f"confidence {event.get('confidence', '?')})",
            "SIMULATION: no chemical or water was applied; a simulated actuator recorded this."
            if event.get("simulated", True) else "REAL APPLICATION (unexpected from this stub).",
        ]
        if reasons:
            notes.append("Refused because: " + ", ".join(str(r) for r in reasons))
        attrs: dict[str, Any] = {
            "name": f"Treatment {kind}: {event.get('label', 'target')}",
            "status": "done",
            "notes": {"value": "\n".join(notes), "format": "default"},
        }
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            attrs["geometry"] = {"value": f"POINT({lon} {lat})"}   # WKT is lon-first
        payload: dict[str, Any] = {"data": {"type": "log--activity", "attributes": attrs}}
        lid = land_asset_id or self.land_asset_id
        if lid:
            payload["data"]["relationships"] = {
                "location": {"data": [{"type": "asset--land", "id": lid}]}}
        return payload

    # -- outbox ---------------------------------------------------------------------
    def queue(self, payload: dict) -> int:
        self.outbox.append(payload)
        return len(self.outbox)

    def flush(self) -> list[str]:
        """Send queued payloads -- only with a client AND allow_network=True."""
        if not self.network_enabled:
            raise FarmOSNetworkDisabled(
                "FarmOSAdapter will not send: construct with a FarmOSClient AND allow_network=True. "
                f"{len(self.outbox)} payload(s) remain queued.")
        ids: list[str] = []
        while self.outbox:
            ids.append(self._client.create_log(self.outbox[0]))
            self.outbox.pop(0)           # only drop after a successful send
        self.sent_ids.extend(ids)
        return ids

    def health(self) -> dict[str, Any]:
        return {"adapter": self.name, "status": self.status,
                "network_enabled": self.network_enabled, "queued": len(self.outbox)}


