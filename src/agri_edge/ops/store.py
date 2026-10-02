"""In-memory Ops store with optional SQLite persistence (section 120)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from .db import get_sensor_db
from .types import (
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
        # Messages accepted through ops/ingest.py since start (replay included).
        self.live_messages = 0
        # True while ops/ingest.replay_ingest_log rebuilds state: the log is the
        # durable record, so replayed readings must not be written again.
        self.replaying = False
        # Latest STATE reported by each irrigation controller over ground MQTT
        # (read-only mirror; the Ops Station never commands through this).
        self.irrigation_state: dict[str, dict] = {}
        # Held by the MQTT ingest thread while it mutates, and by the HTTP handler
        # while it reads, so a GET never iterates a dict mid-insert.
        self.lock = threading.RLock()
        # Filled in by ops.live_ingest.OpsIngestor when one is attached.
        self.ingest_stats: dict = {}
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
        # Every message accepted by ops/ingest.py, in arrival order. Replayed on
        # startup; the per-kind tables above are derived views of it.
        con.execute(
            """CREATE TABLE IF NOT EXISTS ingest_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL
            )"""
        )
        con.commit()
        con.close()

    def persist_sensor(self, reading: SensorReading) -> None:
        """Append in memory; mirror to SQLite (legacy path) and to DATABASE_URL.

        `DATABASE_URL` selects the backend: sqlite:/// -> SQLite, postgresql:// ->
        PostGIS (see ops/db.py `get_sensor_db`). Unset -> memory only (default).
        Writes are idempotent on `reading_id`, so a replayed/buffered message
        does not duplicate a row. While `replaying` (ingest-log rebuild) nothing
        is written: the log is the durable record.
        """
        self.sensor_readings.append(reading)
        if self.replaying:
            return
        if self.sqlite_path:
            con = sqlite3.connect(self.sqlite_path)
            con.execute(
                "INSERT OR REPLACE INTO sensor_readings(reading_id, payload) VALUES (?, ?)",
                (reading.reading_id, json.dumps(reading.to_dict())),
            )
            con.commit()
            con.close()
        db = get_sensor_db()
        if db is not None:
            db.upsert(reading)

    def persist_detection(self, row: dict) -> None:
        """Persist a normalized detection dict (SIMULATED / SQLite when DATABASE_URL set)."""
        did = row.get("detection_id")
        if did is not None:   # idempotent on id: a replay replaces, never duplicates
            self.detections[:] = [d for d in self.detections if d.get("detection_id") != did]
        self.detections.append(row)
        if self.replaying:
            return
        from .db import get_detection_db
        db = get_detection_db()
        if db is not None:
            db.upsert(row)

    def persist_weather(self, obs: WeatherObservation) -> None:
        self.weather.append(obs)
        if not self.sqlite_path or self.replaying:
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
            "live_messages": self.live_messages,
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
