-- PostGIS-ready schema for Agri-Edge Ops Station (optional production path)
-- Companion to src/agri_edge/ops/db.py SQLite SensorReading store.
-- Enable: CREATE EXTENSION IF NOT EXISTS postgis;

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS farms (
    farm_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    geom geometry(MultiPolygon, 4326),
    synthetic BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    farm_id TEXT REFERENCES farms(farm_id),
    device_type TEXT NOT NULL,
    name TEXT,
    geom geometry(Point, 4326),
    synthetic BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    reading_id TEXT PRIMARY KEY,
    sensor_id TEXT NOT NULL REFERENCES devices(device_id),
    ts TIMESTAMPTZ NOT NULL,
    metric TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL,
    quality TEXT NOT NULL,
    origin TEXT NOT NULL,
    depth_cm DOUBLE PRECISION,
    temp_kind TEXT,
    geom geometry(Point, 4326),
    synthetic BOOLEAN DEFAULT FALSE,
    farm_id TEXT DEFAULT 'demo_farm'
);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor_ts ON sensor_readings (sensor_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_sensor_readings_geom ON sensor_readings USING GIST (geom);

CREATE TABLE IF NOT EXISTS map_assets (
    asset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    layer_kind TEXT NOT NULL,
    geojson JSONB,
    geotiff_path TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    farm_id TEXT DEFAULT 'demo_farm',
    time_range TEXT,
    geom geometry(Geometry, 4326),
    synthetic BOOLEAN DEFAULT FALSE,
    meta JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_map_assets_geom ON map_assets USING GIST (geom);

CREATE TABLE IF NOT EXISTS water_usage_events (
    event_id TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL,
    start_ts TIMESTAMPTZ NOT NULL,
    end_ts TIMESTAMPTZ,
    volume_l DOUBLE PRECISION NOT NULL DEFAULT 0,
    commanded_volume_l DOUBLE PRECISION,
    measured_volume_l DOUBLE PRECISION,
    reason TEXT DEFAULT 'irrigation',
    farm_id TEXT DEFAULT 'demo_farm',
    synthetic BOOLEAN DEFAULT FALSE
);

-- Normalized detections (Detection API). SIMULATED until deployed to a real PostGIS.
-- `geom` is the WORLD position from geo/georef.py (flat-ground model); NULL when the
-- detection was not georeferenced or its pose was rejected -- never a guess.
CREATE TABLE IF NOT EXISTS detections (
    detection_id TEXT PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    label TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    bbox JSONB NOT NULL,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    geom geometry(Point, 4326),
    model_name TEXT,
    model_version TEXT,
    backend TEXT,
    validated_locally BOOLEAN NOT NULL DEFAULT FALSE,
    may_drive_treatment BOOLEAN NOT NULL DEFAULT FALSE,
    in_treatment_zone BOOLEAN,
    farm_id TEXT DEFAULT 'demo_farm',
    mission_id TEXT,
    frame_id TEXT,
    payload JSONB DEFAULT '{}'::jsonb,
    synthetic BOOLEAN DEFAULT FALSE,
    world_lat DOUBLE PRECISION,
    world_lon DOUBLE PRECISION,
    local_x DOUBLE PRECISION,
    local_y DOUBLE PRECISION,
    position_uncertainty_m DOUBLE PRECISION,
    georef_status TEXT
);

CREATE INDEX IF NOT EXISTS idx_detections_ts ON detections (ts DESC);
CREATE INDEX IF NOT EXISTS idx_detections_geom ON detections USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_detections_label ON detections (label);

-- Notes:
-- * Application defaults to in-memory OpsStore for tests.
-- * Set DATABASE_URL=sqlite:///path/to.db to use db.SensorReadingStore.
-- * Set DATABASE_URL=postgresql://... to use ops/postgis.py PostgisStore (SIMULATED:
--   tested only against a throwaway local PostGIS, never production).
-- * ground_iot/docker-compose.postgis.yml loads this file as the init script.
