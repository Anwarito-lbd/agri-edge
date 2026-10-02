# Ops Station — optional PostGIS backend

**Status: BENCH** (real PostgreSQL 17 + PostGIS 3.5 on the build box, 2026-10-02; see "Live-service run" below). SQLite stays the default. The PostGIS code (`src/agri_edge/ops/postgis.py`) is exercised against a throwaway local PostGIS in `tests/test_ops_postgis.py`, which is **skipped** when none is reachable. **The compose file `ground_iot/docker-compose.postgis.yml` has never been run** (no Docker on the build box; only its init SQL was applied with `psql`). **Nothing has been run against a production PostGIS.** Not validated against any real hardware or farm.

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

## Live-service run (BENCH, 2026-10-02)

The live tests were run on the build box against **real, throwaway** services — not Docker, not
production, synthetic data only:

```bash
sudo apt-get install -y postgresql postgis mosquitto
sudo pg_ctlcluster 17 main start            # PostgreSQL 17 + PostGIS 3.5
sudo -u postgres psql -c "CREATE DATABASE agriedge_test"
sudo -u postgres psql -d agriedge_test -c "CREATE EXTENSION postgis"
printf 'listener 18830 127.0.0.1\nallow_anonymous true\n' > /tmp/mosq.conf && /usr/sbin/mosquitto -c /tmp/mosq.conf -d
export AGRIEDGE_TEST_PG_URL=postgresql://postgres:<throwaway-password>@127.0.0.1:5432/agriedge_test
export AGRIEDGE_TEST_MQTT=127.0.0.1:18830
pytest tests/test_ops_postgis.py tests/test_ops_ingest_broker.py tests/test_live_services_e2e.py -rs
```

Result: all passed, none skipped; **no bug was found** in the PostGIS store or the live ingest.
`tests/test_live_services_e2e.py` adds the two cases the others did not cover: MQTT publish →
`OpsIngestor` → rows in real PostGIS (replay deduplicated), and an `ST_DWithin` spatial query over
ingested detection geometry. CI job: `docs/ci/live-services.yml` — **not active**; the push token lacked the `workflow`
scope, so it is kept there with activation steps in `docs/ci/README.md`, and has never run on GitHub. What this does **not** show: the `postgis/postgis:16-3.4` image, the repo's
ACL'd Mosquitto config, TLS, load, or any production database.
