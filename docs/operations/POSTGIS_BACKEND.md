# Ops Station — optional PostGIS backend

**Status: SIMULATED.** SQLite stays the default. The PostGIS code (`src/agri_edge/ops/postgis.py`) is exercised only against a throwaway local PostGIS in `tests/test_ops_postgis.py`, which is **skipped** when none is reachable. **The compose file `ground_iot/docker-compose.postgis.yml` has never been run.** **Nothing has been run against a production PostGIS.** Not validated against any real hardware or farm.

## Selecting a backend (`DATABASE_URL`)

`ops.db.get_sensor_db()` / `get_detection_db()` choose by URL. `DATABASE_URL` is read first; `AGRIEDGE_DB_URL` is the fallback.

| Value | Backend |
|-------|---------|
| unset / empty | no database; in-memory `OpsStore` only (default, what tests use) |
| `sqlite:///path/to.db` | SQLite (bundled with Python) |
| `postgresql://…` or `postgres://…` | PostGIS via `ops/postgis.py` |

Both backends implement the same interface (`SensorStoreProtocol`, `DetectionStoreProtocol`), so callers never branch on the backend. Writes are idempotent on `reading_id` / `detection_id`.

`psycopg` v3 is imported lazily, only when a `postgresql://` URL is used (`pip install "psycopg[binary]"`), so the Pi runtime still installs with numpy + PyYAML only.

## Schema

`docs/operations/schema_postgis.sql` is the single source of truth. `PostgisStore.ensure_schema()` applies it idempotently (`CREATE … IF NOT EXISTS`). Sensor readings have foreign keys to devices/farms, so a write first upserts a minimal placeholder device/farm row. The `detections` table holds the georeferenced world position (`geom`, `world_lat/lon`, `local_x/y`, `position_uncertainty_m`, `georef_status`); these are NULL when a detection was not georeferenced — never a guess. Older SQLite files gain the new detection columns via an automatic migration.

## Compose file (never run)

```bash
export POSTGRES_PASSWORD='<choose one>'      # no default, by design: compose refuses to start without it
docker compose -f ground_iot/docker-compose.postgis.yml up -d
export DATABASE_URL="postgresql://agriedge:${POSTGRES_PASSWORD}@127.0.0.1:5432/agriedge"
```

* Image `postgis/postgis:16-3.4`, port bound to **127.0.0.1 only**. Do not expose 5432 to a farm LAN without TLS and a real role/ACL design.
* The init script mounts the same `schema_postgis.sql`; Postgres only runs init scripts on an empty data volume, `ensure_schema()` covers later additions.
* No credential is committed in this repository.

## Tests

```bash
AGRIEDGE_TEST_PG_URL=postgresql://user:pw@127.0.0.1:5432/scratch python -m pytest tests/test_ops_postgis.py
```

Without `AGRIEDGE_TEST_PG_URL` (or if the server/PostGIS extension is unreachable) the live tests skip; selection, URL parsing and SQLite-default tests still run. Use a scratch database, never production.

Related: `MQTT_INGEST.md`, `OPERATIONS_STATION.md`.
