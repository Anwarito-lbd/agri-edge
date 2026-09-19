"""Entity models for water, map, greenhouse, pest, tasks, audit (§87–116, §140–152)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from .types import DeviceType, DataOrigin, QualityFlag, new_id, utcnow


@dataclass
class WaterSource:
    source_id: str
    name: str
    kind: str = "well"  # well|pond|municipal|canal
    farm_id: str = "demo_farm"
    lat: Optional[float] = None
    lon: Optional[float] = None
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Tank:
    tank_id: str
    name: str
    capacity_l: float
    level_pct: float = 0.0
    source_id: Optional[str] = None
    farm_id: str = "demo_farm"
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Pump:
    pump_id: str
    name: str
    rated_lpm: float
    running: bool = False
    farm_id: str = "demo_farm"
    # SAFETY: never AI-unrestricted; ground MQTT only
    command_channel: str = "mqtt_ground_only"
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Valve:
    valve_id: str
    name: str
    zone_id: str
    open_pct: float = 0.0
    farm_id: str = "demo_farm"
    command_channel: str = "mqtt_ground_only"
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FlowMeter:
    meter_id: str
    name: str
    zone_id: Optional[str] = None
    last_lpm: float = 0.0
    total_l: float = 0.0
    farm_id: str = "demo_farm"
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WaterReading:
    reading_id: str
    meter_id: str
    ts: str
    flow_lpm: float
    total_l: Optional[float] = None
    quality: QualityFlag = QualityFlag.GOOD
    origin: DataOrigin = DataOrigin.MEASURED
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quality"] = self.quality.value
        d["origin"] = self.origin.value
        return d


@dataclass
class WaterUsageEvent:
    event_id: str
    zone_id: str
    start_ts: str
    end_ts: Optional[str] = None
    volume_l: float = 0.0
    reason: str = "irrigation"
    synthetic: bool = False
    farm_id: str = "demo_farm"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SensorReading:
    """§120 generic sensor DB shape."""
    reading_id: str
    sensor_id: str
    ts: str
    metric: str
    value: float
    unit: str
    quality: QualityFlag = QualityFlag.GOOD
    origin: DataOrigin = DataOrigin.MEASURED
    depth_cm: Optional[float] = None
    temp_kind: Optional[str] = None
    synthetic: bool = False
    farm_id: str = "demo_farm"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quality"] = self.quality.value
        d["origin"] = self.origin.value
        return d


@dataclass
class DeviceHealth:
    """§125"""
    device_id: str
    ts: str
    online: bool = True
    battery_pct: Optional[float] = None
    signal_rssi: Optional[float] = None
    uptime_s: Optional[float] = None
    firmware: Optional[str] = None
    error_code: Optional[str] = None
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MapAsset:
    """§88–92, §114 MapCatalogue."""
    asset_id: str
    name: str
    layer_kind: str  # field|zone|station|prescription|health|microclimate|odm|catalogue
    geojson: Optional[dict[str, Any]] = None
    geotiff_path: Optional[str] = None
    enabled: bool = True
    farm_id: str = "demo_farm"
    time_range: Optional[str] = None  # now|hour|today|week|custom
    synthetic: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RTKStation:
    """§103"""
    station_id: str
    name: str
    kind: str = "base"  # base|rover
    lat: float = 0.0
    lon: float = 0.0
    fix_quality: str = "unknown"
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ServiceStation:
    """§104 — model only; no physical dock servicing automation."""
    station_id: str
    name: str
    lat: float
    lon: float
    status: str = "idle"  # idle|occupied|maintenance|offline
    capabilities: list[str] = field(default_factory=lambda: ["charge_contact", "status_telemetry"])
    # Physical dock servicing is NOT automated here
    servicing_automated: bool = False
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GreenhouseZone:
    """§140 — models capable; actuators NOT automated."""
    zone_id: str
    name: str
    target_air_c: Optional[float] = None
    target_rh_pct: Optional[float] = None
    actuators_automated: bool = False  # always False by policy
    farm_id: str = "demo_farm"
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["actuators_automated"] = False
        return d


@dataclass
class PestObservation:
    """§141"""
    obs_id: str
    ts: str
    species: str
    count: int = 1
    lat: Optional[float] = None
    lon: Optional[float] = None
    zone_id: Optional[str] = None
    source: str = "manual"  # manual|camera|scout
    synthetic: bool = False
    farm_id: str = "demo_farm"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CameraEvent:
    """§142"""
    event_id: str
    camera_id: str
    ts: str
    label: str
    confidence: float = 0.0
    image_path: Optional[str] = None
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoutReport:
    """§143"""
    report_id: str
    ts: str
    scout_id: str
    notes: str
    zone_id: Optional[str] = None
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ManualObservation:
    """§144"""
    obs_id: str
    ts: str
    observer: str
    text: str
    category: str = "general"
    lat: Optional[float] = None
    lon: Optional[float] = None
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Task:
    """§145"""
    task_id: str
    title: str
    status: str = "open"  # open|in_progress|done|cancelled
    assignee: Optional[str] = None
    due: Optional[str] = None
    priority: str = "normal"
    farm_id: str = "demo_farm"
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TimelineEvent:
    """§146"""
    event_id: str
    ts: str
    kind: str
    summary: str
    ref_id: Optional[str] = None
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEntry:
    """§151"""
    audit_id: str
    ts: str
    actor: str
    action: str
    resource: str
    detail: str = ""
    role: str = "operator"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MobileNote:
    """§149"""
    note_id: str
    ts: str
    author: str
    text: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
