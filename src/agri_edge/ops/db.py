"""Optional SensorReading + Detection stores, selected by DATABASE_URL.

    unset / empty            -> no DB; in-memory OpsStore only (the default, and what tests use)
    sqlite:///path/to.db     -> SQLite (IMPLEMENTED, bundled with Python)
    postgresql://...         -> PostGIS via ops/postgis.py (SIMULATED: exercised only against a
                                local throwaway PostGIS in tests; never against production)

`AGRIEDGE_DB_URL` (documented in .env.example) is honoured when DATABASE_URL is unset.
Both backends implement the same interface (`SensorStoreProtocol` /
`DetectionStoreProtocol` below), so callers never branch on the backend.
psycopg is imported lazily, inside ops/postgis.py, only when a postgresql:// URL is used.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable
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

CREATE TABLE IF NOT EXISTS detections (
    detection_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    label TEXT NOT NULL,
    confidence REAL NOT NULL,
    bbox_json TEXT NOT NULL,
    lat REAL,
    lon REAL,
    model_name TEXT,
    model_version TEXT,
    backend TEXT,
    validated_locally INTEGER NOT NULL DEFAULT 0,
    may_drive_treatment INTEGER NOT NULL DEFAULT 0,
    in_treatment_zone INTEGER,
    farm_id TEXT NOT NULL DEFAULT 'demo_farm',
    mission_id TEXT,
    frame_id TEXT,
    payload_json TEXT,
    synthetic INTEGER NOT NULL DEFAULT 0,
    world_lat REAL,
    world_lon REAL,
    local_x REAL,
    local_y REAL,
    position_uncertainty_m REAL,
    georef_status TEXT
);
CREATE INDEX IF NOT EXISTS idx_detections_ts ON detections(ts);
CREATE INDEX IF NOT EXISTS idx_detections_label ON detections(label);
"""


# Columns added after the first release of the detections table. Applied to an
# existing database file by `_migrate_detections` so older .db files keep working.
_DETECTION_GEOREF_COLUMNS = (
    ("world_lat", "REAL"),
    ("world_lon", "REAL"),
    ("local_x", "REAL"),
    ("local_y", "REAL"),
    ("position_uncertainty_m", "REAL"),
    ("georef_status", "TEXT"),
)


def _migrate_detections(con: sqlite3.Connection) -> None:
    have = {r[1] for r in con.execute("PRAGMA table_info(detections)").fetchall()}
    for name, typ in _DETECTION_GEOREF_COLUMNS:
        if name not in have:
            con.execute(f"ALTER TABLE detections ADD COLUMN {name} {typ}")


def _float_or_none(v: Any) -> Optional[float]:
    return None if v is None else float(v)


@runtime_checkable
class SensorStoreProtocol(Protocol):
    """What every sensor-reading backend (SQLite, PostGIS) provides."""

    def upsert(self, reading: SensorReading) -> None: ...

    def list(self, sensor_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]: ...


@runtime_checkable
class DetectionStoreProtocol(Protocol):
    """What every detection backend (SQLite, PostGIS) provides."""

    def upsert(self, row: dict[str, Any]) -> None: ...

    def list(self, label: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]: ...


def is_postgres_url(database_url: str) -> bool:
    return (database_url or "").lower().startswith(("postgresql://", "postgres://"))


def database_url_from_env() -> str:
    return os.environ.get("DATABASE_URL") or os.environ.get("AGRIEDGE_DB_URL") or ""


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
        _migrate_detections(con)
        con.commit()
        con.close()

    def upsert(self, reading: SensorReading) -> None:
        if hasattr(reading, "to_dict"):
            d = reading.to_dict()
        else:
            d = dict(reading.__dict__)
        quality = d.get("quality") or "GOOD"
        origin = d.get("origin") or "MEASURED"
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
                float(d.get("value", 0.0)),
                d.get("unit") or "",
                quality,
                origin,
                d.get("depth_cm"),
                d.get("temp_kind"),
                1 if d.get("synthetic") else 0,
                d.get("farm_id") or "demo_farm",
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


class DetectionStore:
    """SQLite-backed detection persistence (normalized Detection API rows)."""

    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.executescript(SCHEMA_SQLITE)
        _migrate_detections(con)
        con.commit()
        con.close()

    def upsert(self, row: dict[str, Any]) -> None:
        bbox = row.get("bbox") or row.get("bbox_xyxy") or [0, 0, 0, 0]
        if isinstance(bbox, (list, tuple)):
            bbox_json = json.dumps([float(x) for x in bbox])
        else:
            bbox_json = json.dumps(bbox)
        con = sqlite3.connect(self.path)
        con.execute(
            """INSERT OR REPLACE INTO detections(
                detection_id, ts, label, confidence, bbox_json, lat, lon,
                model_name, model_version, backend, validated_locally,
                may_drive_treatment, in_treatment_zone, farm_id, mission_id,
                frame_id, payload_json, synthetic,
                world_lat, world_lon, local_x, local_y, position_uncertainty_m, georef_status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row.get("detection_id") or row.get("id"),
                row.get("ts") or "",
                row.get("label") or "unknown",
                float(row.get("confidence") or 0.0),
                bbox_json,
                row.get("lat"),
                row.get("lon"),
                row.get("model_name"),
                row.get("model_version"),
                row.get("backend"),
                1 if row.get("validated_locally") else 0,
                1 if row.get("may_drive_treatment") else 0,
                None if row.get("in_treatment_zone") is None else (1 if row.get("in_treatment_zone") else 0),
                row.get("farm_id") or "demo_farm",
                row.get("mission_id"),
                row.get("frame_id"),
                json.dumps(row.get("payload") or {}),
                1 if row.get("synthetic") else 0,
                _float_or_none(row.get("world_lat")),
                _float_or_none(row.get("world_lon")),
                _float_or_none(row.get("local_x")),
                _float_or_none(row.get("local_y")),
                _float_or_none(row.get("position_uncertainty_m")),
                row.get("georef_status"),
            ),
        )
        con.commit()
        con.close()

    def list(self, label: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        if label:
            rows = con.execute(
                "SELECT * FROM detections WHERE label=? ORDER BY ts DESC LIMIT ?",
                (label, limit),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM detections ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        con.close()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["bbox"] = json.loads(d.pop("bbox_json"))
            except Exception:
                d["bbox"] = d.pop("bbox_json", None)
            d["validated_locally"] = bool(d.get("validated_locally"))
            d["may_drive_treatment"] = bool(d.get("may_drive_treatment"))
            if d.get("in_treatment_zone") is not None:
                d["in_treatment_zone"] = bool(d["in_treatment_zone"])
            d["synthetic"] = bool(d.get("synthetic"))
            out.append(d)
        return out


_SENSOR_DB: Optional[SensorStoreProtocol] = None
_DET_DB: Optional[DetectionStoreProtocol] = None
_SENSOR_KEY: Optional[str] = None
_DET_KEY: Optional[str] = None


def _postgres_stores(url: str):
    from .postgis import PostgisStore  # lazy: psycopg only when a postgresql:// URL is used

    return PostgisStore(url)


def get_sensor_db(database_url: Optional[str] = None) -> Optional[SensorStoreProtocol]:
    """Return the configured sensor store (SQLite or PostGIS), else None."""
    global _SENSOR_DB, _SENSOR_KEY
    url = database_url if database_url is not None else database_url_from_env()
    if is_postgres_url(url):
        if _SENSOR_DB is None or _SENSOR_KEY != url:
            _SENSOR_DB = _postgres_stores(url).sensors
            _SENSOR_KEY = url
        return _SENSOR_DB
    path = parse_sqlite_path(url or "")
    if not path:
        return None
    if _SENSOR_DB is None or _SENSOR_KEY != path:
        _SENSOR_DB = SensorReadingStore(path)
        _SENSOR_KEY = path
    return _SENSOR_DB


def get_detection_db(database_url: Optional[str] = None) -> Optional[DetectionStoreProtocol]:
    global _DET_DB, _DET_KEY
    url = database_url if database_url is not None else database_url_from_env()
    if is_postgres_url(url):
        if _DET_DB is None or _DET_KEY != url:
            _DET_DB = _postgres_stores(url).detections
            _DET_KEY = url
        return _DET_DB
    path = parse_sqlite_path(url or "")
    if not path:
        return None
    if _DET_DB is None or _DET_KEY != path:
        _DET_DB = DetectionStore(path)
        _DET_KEY = path
    return _DET_DB


def reset_sensor_db() -> None:
    global _SENSOR_DB, _DET_DB, _SENSOR_KEY, _DET_KEY
    _SENSOR_DB = None
    _DET_DB = None
    _SENSOR_KEY = None
    _DET_KEY = None
