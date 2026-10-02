"""PostGIS backend for the Ops stores (same interface as the SQLite ones).

STATUS: SIMULATED. Exercised only against a throwaway local PostGIS in
`tests/test_ops_postgis.py` (skipped when none is reachable). It has never been
pointed at a production database and nothing here is VALIDATED.

SELECTION
---------
`ops.db.get_sensor_db()` / `get_detection_db()` return these when `DATABASE_URL`
(or `AGRIEDGE_DB_URL`) starts with `postgresql://`. SQLite stays the default.

LAZY IMPORT
-----------
`psycopg` (v3, `pip install "psycopg[binary]"`) is imported inside `_connect`, not
at module level, so the Pi runtime keeps installing with numpy + PyYAML only and
`tests/test_runtime_deps.py` keeps passing.

SCHEMA
------
Created from `docs/operations/schema_postgis.sql` (the single source of truth; the
docker-compose.postgis.yml init mounts the same file). `PostgisStore.ensure_schema`
is idempotent (`CREATE ... IF NOT EXISTS`). sensor_readings has foreign keys to
devices/farms, so a write first upserts a minimal placeholder row for the device
and farm (`ON CONFLICT DO NOTHING`) -- an unknown device must not drop a reading.

CREDENTIALS
-----------
Only ever from the URL the operator supplies in the environment. No default
password exists in this repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .schema import SensorReading

SCHEMA_SQL_PATH = Path(__file__).resolve().parents[3] / "docs" / "operations" / "schema_postgis.sql"


def _connect(url: str, **kw: Any) -> Any:
    try:
        import psycopg
    except ImportError as e:
        raise ImportError(
            'psycopg is required for DATABASE_URL=postgresql://... ; pip install "psycopg[binary]"'
        ) from e
    return psycopg.connect(url, **kw)


def postgres_reachable(url: str, timeout_s: int = 2) -> bool:
    """True when psycopg is installed AND the server accepts a connection AND PostGIS exists."""
    try:
        with _connect(url, connect_timeout=timeout_s, autocommit=True) as con:
            con.execute("SELECT 1")
            row = con.execute(
                "SELECT 1 FROM pg_available_extensions WHERE name='postgis'"
            ).fetchone()
            return row is not None
    except Exception:
        return False


def _norm(v: Any) -> Any:
    return v.value if hasattr(v, "value") else v


def _utc_iso(ts: Any) -> Any:
    """TIMESTAMPTZ comes back in the *session* zone; report UTC like the SQLite path does."""
    if hasattr(ts, "astimezone"):
        from datetime import timezone

        return ts.astimezone(timezone.utc).isoformat()
    return ts


class PostgisSensorStore:
    def __init__(self, url: str) -> None:
        self.url = url

    def upsert(self, reading: SensorReading) -> None:
        d = reading.to_dict() if hasattr(reading, "to_dict") else dict(reading.__dict__)
        farm = d.get("farm_id") or "demo_farm"
        sensor = d.get("sensor_id")
        with _connect(self.url) as con:
            con.execute(
                "INSERT INTO farms(farm_id, name, synthetic) VALUES (%s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (farm, farm, bool(d.get("synthetic"))),
            )
            con.execute(
                "INSERT INTO devices(device_id, farm_id, device_type, name, synthetic) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (sensor, farm, "unknown", sensor, bool(d.get("synthetic"))),
            )
            con.execute(
                """INSERT INTO sensor_readings(
                       reading_id, sensor_id, ts, metric, value, unit, quality, origin,
                       depth_cm, temp_kind, synthetic, farm_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (reading_id) DO UPDATE SET
                       value=EXCLUDED.value, unit=EXCLUDED.unit, quality=EXCLUDED.quality,
                       origin=EXCLUDED.origin, depth_cm=EXCLUDED.depth_cm,
                       temp_kind=EXCLUDED.temp_kind, synthetic=EXCLUDED.synthetic""",
                (
                    d.get("reading_id"),
                    sensor,
                    d.get("ts"),
                    d.get("metric"),
                    float(d.get("value", 0.0)),
                    d.get("unit") or "",
                    _norm(d.get("quality")) or "GOOD",
                    _norm(d.get("origin")) or "MEASURED",
                    d.get("depth_cm"),
                    d.get("temp_kind"),
                    bool(d.get("synthetic")),
                    farm,
                ),
            )

    def list(self, sensor_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = (
            "SELECT reading_id, sensor_id, ts, metric, value, unit, quality, origin, depth_cm, "
            "temp_kind, synthetic, farm_id FROM sensor_readings "
        )
        args: list[Any] = []
        if sensor_id:
            sql += "WHERE sensor_id=%s "
            args.append(sensor_id)
        sql += "ORDER BY ts DESC LIMIT %s"
        args.append(limit)
        with _connect(self.url) as con:
            rows = con.execute(sql, args).fetchall()
        cols = ["reading_id", "sensor_id", "ts", "metric", "value", "unit", "quality",
                "origin", "depth_cm", "temp_kind", "synthetic", "farm_id"]
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            d["ts"] = _utc_iso(d["ts"])
            out.append(d)
        return out


class PostgisDetectionStore:
    def __init__(self, url: str) -> None:
        self.url = url

    def upsert(self, row: dict[str, Any]) -> None:
        bbox = row.get("bbox") or row.get("bbox_xyxy") or [0, 0, 0, 0]
        bbox = [float(x) for x in bbox] if isinstance(bbox, (list, tuple)) else bbox
        # `geom` only from a real georeferenced world position; never from 0,0 defaults.
        lat = row.get("world_lat") if row.get("world_lat") is not None else row.get("lat")
        lon = row.get("world_lon") if row.get("world_lon") is not None else row.get("lon")
        has_geom = lat is not None and lon is not None
        with _connect(self.url) as con:
            con.execute(
                """INSERT INTO detections(
                       detection_id, ts, label, confidence, bbox, lat, lon, geom, model_name,
                       model_version, backend, validated_locally, may_drive_treatment,
                       in_treatment_zone, farm_id, mission_id, frame_id, payload, synthetic,
                       world_lat, world_lon, local_x, local_y, position_uncertainty_m,
                       georef_status)
                   VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,
                           CASE WHEN %s THEN ST_SetSRID(ST_MakePoint(%s,%s),4326) END,
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (detection_id) DO UPDATE SET
                       ts=EXCLUDED.ts, label=EXCLUDED.label, confidence=EXCLUDED.confidence,
                       bbox=EXCLUDED.bbox, lat=EXCLUDED.lat, lon=EXCLUDED.lon,
                       geom=EXCLUDED.geom, validated_locally=EXCLUDED.validated_locally,
                       may_drive_treatment=EXCLUDED.may_drive_treatment,
                       in_treatment_zone=EXCLUDED.in_treatment_zone,
                       world_lat=EXCLUDED.world_lat, world_lon=EXCLUDED.world_lon,
                       local_x=EXCLUDED.local_x, local_y=EXCLUDED.local_y,
                       position_uncertainty_m=EXCLUDED.position_uncertainty_m,
                       georef_status=EXCLUDED.georef_status, payload=EXCLUDED.payload""",
                (
                    row.get("detection_id") or row.get("id"),
                    row.get("ts") or None,
                    row.get("label") or "unknown",
                    float(row.get("confidence") or 0.0),
                    json.dumps(bbox),
                    row.get("lat"),
                    row.get("lon"),
                    has_geom,
                    lon,
                    lat,
                    row.get("model_name"),
                    row.get("model_version"),
                    row.get("backend"),
                    bool(row.get("validated_locally")),
                    bool(row.get("may_drive_treatment")),
                    row.get("in_treatment_zone"),
                    row.get("farm_id") or "demo_farm",
                    row.get("mission_id"),
                    row.get("frame_id"),
                    json.dumps(row.get("payload") or {}),
                    bool(row.get("synthetic")),
                    row.get("world_lat"),
                    row.get("world_lon"),
                    row.get("local_x"),
                    row.get("local_y"),
                    row.get("position_uncertainty_m"),
                    row.get("georef_status"),
                ),
            )

    def list(self, label: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        sql = (
            "SELECT detection_id, ts, label, confidence, bbox, lat, lon, model_name, "
            "model_version, backend, validated_locally, may_drive_treatment, in_treatment_zone, "
            "farm_id, mission_id, frame_id, synthetic, world_lat, world_lon, local_x, local_y, "
            "position_uncertainty_m, georef_status FROM detections "
        )
        args: list[Any] = []
        if label:
            sql += "WHERE label=%s "
            args.append(label)
        sql += "ORDER BY ts DESC LIMIT %s"
        args.append(limit)
        cols = ["detection_id", "ts", "label", "confidence", "bbox", "lat", "lon", "model_name",
                "model_version", "backend", "validated_locally", "may_drive_treatment",
                "in_treatment_zone", "farm_id", "mission_id", "frame_id", "synthetic",
                "world_lat", "world_lon", "local_x", "local_y", "position_uncertainty_m",
                "georef_status"]
        with _connect(self.url) as con:
            rows = con.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(zip(cols, r))
            d["ts"] = _utc_iso(d["ts"])
            out.append(d)
        return out


class PostgisStore:
    """Bundle of the sensor + detection stores over one URL, schema ensured on init."""

    def __init__(self, url: str, *, ensure_schema: bool = True) -> None:
        self.url = url
        if ensure_schema:
            self.ensure_schema()
        self.sensors = PostgisSensorStore(url)
        self.detections = PostgisDetectionStore(url)

    def ensure_schema(self) -> None:
        sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
        with _connect(self.url) as con:
            con.execute(sql)

    # Same two-method interface as SQLite stores, for callers that want one object.
    def upsert(self, reading: SensorReading) -> None:
        self.sensors.upsert(reading)

    def list(self, sensor_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        return self.sensors.list(sensor_id, limit)
