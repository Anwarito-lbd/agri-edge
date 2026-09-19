from __future__ import annotations
"""In-memory Ops store with optional SQLite persistence (§120)."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from .db import get_sensor_db
from .types import (
    Alert,
    CalibrationRecord,
    Device,
    RetentionPolicy,
    SoilObservation,
    WeatherAggregate,
    WeatherObservation,
    utcnow,
)
from .schema import (
    AuditEntry,
    CameraEvent,
    DeviceHealth,
    FlowMeter,
    GreenhouseZone,
    MapAsset,
    ManualObservation,
    MobileNote,
    PestObservation,
    Pump,
    ScoutReport,
    SensorReading,
    ServiceStation,
    RTKStation,
    Tank,
    Task,
    TimelineEvent,
    Valve,
    WaterReading,
    WaterSource,
    WaterUsageEvent,
)
from .alerts import AlertEngine


class OpsStore:
    def __init__(self, sqlite_path: Optional[str] = None) -> None:
        self.devices: dict[str, Device] = {}
        self.weather: list[WeatherObservation] = []
        self.weather_aggs: list[WeatherAggregate] = []
        self.soil: list[SoilObservation] = []
        self.sensors: dict[str, SensorReading] = {}
        self.sensor_readings: list[SensorReading] = []
        self.detections: list[dict] = []
        self.health: dict[str, DeviceHealth] = {}
        self.water_sources: dict[str, WaterSource] = {}
        self.tanks: dict[str, Tank] = {}
        self.pumps: dict[str, Pump] = {}
        self.valves: dict[str, Valve] = {}
        self.flow_meters: dict[str, FlowMeter] = {}
        self.water_readings: list[WaterReading] = []
        self.water_usage: list[WaterUsageEvent] = []
        self.map_assets: dict[str, MapAsset] = {}
        self.rtk: dict[str, RTKStation] = {}
        self.service_stations: dict[str, ServiceStation] = {}
        self.greenhouse: dict[str, GreenhouseZone] = {}
        self.pests: list[PestObservation] = []
        self.cameras: list[CameraEvent] = []
        self.scouts: list[ScoutReport] = []
        self.manual: list[ManualObservation] = []
        self.tasks: dict[str, Task] = {}
        self.timeline: list[TimelineEvent] = []
        self.audit: list[AuditEntry] = []
        self.notes: list[MobileNote] = []
        self.mission_energy: list = []  # MissionEnergyLog §131
        self.vision_events: list = []  # VisionTreatmentEvent §133
        self.calibrations: list[CalibrationRecord] = []
        self.retention = RetentionPolicy()
        self.alerts = AlertEngine()
        self.simulation_mode = True  # §153–154 default for demo
        self.sqlite_path = sqlite_path
        if sqlite_path:
            self._init_sqlite(sqlite_path)

    def _init_sqlite(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.execute(
            """CREATE TABLE IF NOT EXISTS sensor_readings (
                reading_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS weather_obs (
                obs_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS alerts (
                alert_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )"""
        )
        con.commit()
        con.close()

    def persist_sensor(self, reading: SensorReading) -> None:
        self.sensor_readings.append(reading)
        if not self.sqlite_path:
            return
        con = sqlite3.connect(self.sqlite_path)
        con.execute(
            "INSERT OR REPLACE INTO sensor_readings(reading_id, payload) VALUES (?, ?)",
            (reading.reading_id, json.dumps(reading.to_dict())),
        )
        db = get_sensor_db()
        if db is not None:
            db.upsert(reading)
        con.commit()
        con.close()


    def persist_detection(self, row: dict) -> None:
        """Persist a normalized detection dict (SIMULATED / SQLite when DATABASE_URL set)."""
        self.detections.append(row)
        from .db import get_detection_db
        db = get_detection_db()
        if db is not None:
            db.upsert(row)

    def persist_weather(self, obs: WeatherObservation) -> None:
        self.weather.append(obs)
        if not self.sqlite_path:
            return
        con = sqlite3.connect(self.sqlite_path)
        con.execute(
            "INSERT OR REPLACE INTO weather_obs(obs_id, payload) VALUES (?, ?)",
            (obs.obs_id, json.dumps(obs.to_dict())),
        )
        con.commit()
        con.close()

    def add_audit(self, actor: str, action: str, resource: str, detail: str = "", role: str = "operator") -> AuditEntry:
        e = AuditEntry(
            audit_id=f"aud_{len(self.audit)+1:05d}",
            ts=utcnow().isoformat(),
            actor=actor,
            action=action,
            resource=resource,
            detail=detail,
            role=role,
        )
        self.audit.append(e)
        return e

    def overview(self) -> dict[str, Any]:
        open_alerts = [a for a in self.alerts.list_alerts() if a.state.value in ("OPEN", "ACKNOWLEDGED", "ESCALATED")]
        return {
            "simulation": self.simulation_mode,
            "banner": "SIMULATION" if self.simulation_mode else None,
            "device_count": len(self.devices),
            "weather_count": len(self.weather),
            "soil_count": len(self.soil),
            "open_alerts": len(open_alerts),
            "map_layers_enabled": sum(1 for m in self.map_assets.values() if m.enabled),
            "tasks_open": sum(1 for t in self.tasks.values() if t.status == "open"),
            "retention": self.retention.to_dict(),
            "ts": utcnow().isoformat(),
        }


_GLOBAL: Optional[OpsStore] = None


def get_store(sqlite_path: Optional[str] = None) -> OpsStore:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = OpsStore(sqlite_path=sqlite_path)
    return _GLOBAL


def reset_store(sqlite_path: Optional[str] = None) -> OpsStore:
    global _GLOBAL
    _GLOBAL = OpsStore(sqlite_path=sqlite_path)
    return _GLOBAL
