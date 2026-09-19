"""Optional SQLite SensorReading store when DATABASE_URL=sqlite:///... (§120 + master #8).

In-memory OpsStore remains the default for tests.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from .schema import SensorReading

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS sensor_readings (
    reading_id TEXT PRIMARY KEY,
    sensor_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    quality TEXT NOT NULL,
    origin TEXT NOT NULL,
    depth_cm REAL,
    temp_kind TEXT,
    synthetic INTEGER NOT NULL DEFAULT 0,
    farm_id TEXT NOT NULL DEFAULT 'demo_farm'
);
CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor_ts
    ON sensor_readings(sensor_id, ts);
"""


def parse_sqlite_path(database_url: str) -> Optional[str]:
    if not database_url:
        return None
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///") :] or None
    parsed = urlparse(database_url)
    if parsed.scheme == "sqlite":
        return parsed.path.lstrip("/") or None
    return None


class SensorReadingStore:
    """SQLite-backed SensorReading persistence."""

    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.executescript(SCHEMA_SQLITE)
        con.commit()
        con.close()

    def upsert(self, reading: SensorReading) -> None:
        d = reading.to_dict() if hasattr(reading, "to_dict") else dict(reading.__dict__)
        quality = d.get("quality")
        origin = d.get("origin")
        if hasattr(quality, "value"):
            quality = quality.value
        if hasattr(origin, "value"):
            origin = origin.value
        con = sqlite3.connect(self.path)
        con.execute(
            """INSERT OR REPLACE INTO sensor_readings(
                reading_id, sensor_id, ts, metric, value, unit, quality, origin,
                depth_cm, temp_kind, synthetic, farm_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                d.get("reading_id"),
                d.get("sensor_id"),
                d.get("ts"),
                d.get("metric"),
                float(d.get("value")),
                d.get("unit"),
                quality or "GOOD",
                origin or "MEASURED",
                d.get("depth_cm"),
                d.get("temp_kind"),
                1 if d.get("synthetic") else 0,
                d.get("farm_id", "demo_farm"),
            ),
        )
        con.commit()
        con.close()

    def list(self, sensor_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        if sensor_id:
            rows = con.execute(
                "SELECT * FROM sensor_readings WHERE sensor_id=? ORDER BY ts DESC LIMIT ?",
                (sensor_id, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM sensor_readings ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        con.close()
        return [dict(r) for r in rows]


_SENSOR_DB: Optional[SensorReadingStore] = None


def get_sensor_db(database_url: Optional[str] = None) -> Optional[SensorReadingStore]:
    """Return SQLite store when DATABASE_URL is sqlite:///; else None (in-memory default)."""
    global _SENSOR_DB
    url = database_url if database_url is not None else os.environ.get("DATABASE_URL", "")
    path = parse_sqlite_path(url or "")
    if not path:
        return None
    if _SENSOR_DB is None or _SENSOR_DB.path != path:
        _SENSOR_DB = SensorReadingStore(path)
    return _SENSOR_DB


def reset_sensor_db() -> None:
    global _SENSOR_DB
    _SENSOR_DB = None
