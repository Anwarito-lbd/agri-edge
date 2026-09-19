"""Ops Station foundational types (§79–87, §93–99, §117–126, §153)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import uuid


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}" if prefix else uuid.uuid4().hex[:12]


class DeviceType(str, Enum):
    """§80 — all Ops Station device roles."""
    WEATHER_STATION = "weather_station"
    SOIL_PROBE = "soil_probe"
    SOIL_MULTI_DEPTH = "soil_multi_depth"
    FLOW_METER = "flow_meter"
    WATER_TANK = "water_tank"
    PUMP = "pump"
    VALVE = "valve"
    GATEWAY = "gateway"
    RTK_BASE = "rtk_base"
    RTK_ROVER = "rtk_rover"
    SERVICE_STATION = "service_station"
    CAMERA_TRAP = "camera_trap"
    SCOUT_DRONE = "scout_drone"
    SPRAY_DRONE = "spray_drone"
    GREENHOUSE_SENSOR = "greenhouse_sensor"
    GREENHOUSE_ACTUATOR = "greenhouse_actuator"  # model only; never auto-driven
    HANDHELD = "handheld"
    ENERGY_METER = "energy_meter"
    UNKNOWN = "unknown"


class TempKind(str, Enum):
    """§82 — typed temperatures; never bare ambiguous 'temperature'."""
    AIR = "air"
    SOIL = "soil"
    CANOPY = "canopy"
    WATER = "water"
    DEWPOINT = "dewpoint"
    WET_BULB = "wet_bulb"
    BLACK_GLOBE = "black_globe"
    STORAGE = "storage"


class DataOrigin(str, Enum):
    MEASURED = "MEASURED"
    DERIVED = "DERIVED"
    FORECAST = "FORECAST"
    MANUAL = "MANUAL"
    SIMULATED = "SIMULATED"


class QualityFlag(str, Enum):
    """§126"""
    GOOD = "GOOD"
    QUESTIONABLE = "QUESTIONABLE"
    BAD = "BAD"
    MISSING = "MISSING"
    STUCK = "STUCK"
    JUMP = "JUMP"
    CAL_OVERDUE = "CAL_OVERDUE"
    LOW_BATTERY = "LOW_BATTERY"
    WEAK_SIGNAL = "WEAK_SIGNAL"


class AlertSeverity(str, Enum):
    """§94"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


class AlertCategory(str, Enum):
    """§95"""
    WEATHER = "WEATHER"
    SOIL = "SOIL"
    WATER = "WATER"
    DEVICE = "DEVICE"
    MAINTENANCE = "MAINTENANCE"
    CROP = "CROP"
    PEST = "PEST"
    SAFETY = "SAFETY"
    IRRIGATION = "IRRIGATION"
    ENERGY = "ENERGY"
    SYSTEM = "SYSTEM"


class AlertState(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    SUPPRESSED = "SUPPRESSED"


class Role(str, Enum):
    """§150"""
    VIEWER = "viewer"
    OPERATOR = "operator"
    AGRONOMIST = "agronomist"
    ADMIN = "admin"
    AUDITOR = "auditor"


ALGORITHM_VERSION = "ops-derived-1.0.0"


@dataclass
class TypedTemperature:
    value_c: float
    kind: TempKind
    origin: DataOrigin = DataOrigin.MEASURED
    algorithm_version: Optional[str] = None
    quality: QualityFlag = QualityFlag.GOOD

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_c": self.value_c,
            "kind": self.kind.value,
            "origin": self.origin.value,
            "algorithm_version": self.algorithm_version,
            "quality": self.quality.value,
        }


@dataclass
class Device:
    device_id: str
    device_type: DeviceType
    name: str
    farm_id: str = "demo_farm"
    zone_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    battery_pct: Optional[float] = None
    signal_rssi: Optional[float] = None
    last_seen: Optional[str] = None
    synthetic: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["device_type"] = self.device_type.value
        return d


@dataclass
class WeatherObservation:
    """§81 — raw weather observation (aggregates stored separately)."""
    obs_id: str
    station_id: str
    ts: str
    air_temp: Optional[TypedTemperature] = None
    rh_pct: Optional[float] = None
    wind_ms: Optional[float] = None
    wind_dir_deg: Optional[float] = None
    precip_mm: Optional[float] = None
    pressure_hpa: Optional[float] = None
    solar_wm2: Optional[float] = None
    quality: QualityFlag = QualityFlag.GOOD
    origin: DataOrigin = DataOrigin.MEASURED
    synthetic: bool = False
    farm_id: str = "demo_farm"

    def to_dict(self) -> dict[str, Any]:
        d = {
            "obs_id": self.obs_id,
            "station_id": self.station_id,
            "ts": self.ts,
            "rh_pct": self.rh_pct,
            "wind_ms": self.wind_ms,
            "wind_dir_deg": self.wind_dir_deg,
            "precip_mm": self.precip_mm,
            "pressure_hpa": self.pressure_hpa,
            "solar_wm2": self.solar_wm2,
            "quality": self.quality.value,
            "origin": self.origin.value,
            "synthetic": self.synthetic,
            "farm_id": self.farm_id,
            "air_temp": self.air_temp.to_dict() if self.air_temp else None,
        }
        return d


@dataclass
class WeatherAggregate:
    """§81 — aggregates kept separate from raw."""
    agg_id: str
    station_id: str
    period: str  # hour|day
    start_ts: str
    end_ts: str
    air_temp_min_c: Optional[float] = None
    air_temp_max_c: Optional[float] = None
    air_temp_mean_c: Optional[float] = None
    precip_sum_mm: Optional[float] = None
    wind_max_ms: Optional[float] = None
    sample_count: int = 0
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SoilObservation:
    """§85 — multi-depth soil."""
    obs_id: str
    probe_id: str
    ts: str
    depth_cm: float
    moisture_pct: Optional[float] = None
    soil_temp: Optional[TypedTemperature] = None
    ec_ds_m: Optional[float] = None
    ph: Optional[float] = None
    quality: QualityFlag = QualityFlag.GOOD
    origin: DataOrigin = DataOrigin.MEASURED
    synthetic: bool = False
    farm_id: str = "demo_farm"
    zone_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["quality"] = self.quality.value
        d["origin"] = self.origin.value
        if self.soil_temp:
            d["soil_temp"] = self.soil_temp.to_dict()
        return d


@dataclass
class Alert:
    alert_id: str
    severity: AlertSeverity
    category: AlertCategory
    title: str
    message: str
    state: AlertState = AlertState.OPEN
    source_key: str = ""  # for dedupe
    device_id: Optional[str] = None
    farm_id: str = "demo_farm"
    created_at: str = field(default_factory=lambda: utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: utcnow().isoformat())
    ack_by: Optional[str] = None
    resolved_by: Optional[str] = None
    synthetic: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["category"] = self.category.value
        d["state"] = self.state.value
        return d


@dataclass
class CalibrationRecord:
    """§127"""
    cal_id: str
    device_id: str
    calibrated_at: str
    next_due: Optional[str] = None
    method: str = "factory"
    notes: str = ""
    synthetic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetentionPolicy:
    """§119"""
    raw_days: int = 90
    aggregate_days: int = 730
    alert_days: int = 365
    audit_days: int = 1095

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
