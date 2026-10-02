# Ops Station — live MQTT ingest

**Status: SIMULATED.** Exercised against an in-memory broker in tests, and (optionally) a local Mosquitto with synthetic publishers (`tests/test_ops_ingest_broker.py`, skipped when no broker is reachable). No real sensor, gateway, radio or farm network has ever fed it. Not validated against any real hardware or farm.

Code: `src/agri_edge/ops/live_ingest.py` (`OpsIngestor`, `IngestConfig`), `src/agri_edge/iot/transport.py` (transports), `src/agri_edge/iot/mqtt_topics.py` (topic parsing). Topic contract: `docs/MQTT_CONTRACT.md` ("Operations Station topics").

## Relationship to `ops/ingest.py` (master's `ingest()`)

There are two ingest paths in the Ops Station. They are deliberately separate and
do not share state, so neither can change the other's behaviour.

| | `ops/ingest.py` -> `ingest(store, topic, payload)` | `ops/live_ingest.py` -> `OpsIngestor` |
|---|---|---|
| Used by | `POST /api/ops/ingest` and `ops/mqtt_ingest.py` (the `AGRIEDGE_MQTT_HOST` subscriber started by `serve()`) | `scripts/ops_mqtt_ingest.py`, `scripts/ops_sim_publish.py --mqtt`, tests |
| Topic scheme | `agriedge/farm/{farm}/zone/{zone}/...` and `agriedge/farm/{farm}/vehicle/{id}/...` (`iot.mqtt_topics.parse_topic`) | `agriedge/{farm}/{category}/{device}/{leaf}` (`iot.mqtt_topics.parse_ops_topic`) |
| Role | The simple path: validate, quality-flag, store | The broker path: adds dedupe on (category, farm, device, timestamp), per-device quality merge (worse of device claim and server check wins), out-of-order handling, and alert raise/resolve |
| Durability | SQLite `ingest_log`, replayed at startup | Deterministic record ids, so a replay is an idempotent upsert in SQLite/PostGIS; in-memory dedupe LRU |
| Safety | refuses `irrigation/set` | subscribe-only (no publish path); refuses command topics and payloads carrying `command`/`set`/`arm`/`mode`/... on state topics; `may_drive_treatment` is always False |

Both write into the same `OpsStore` via `persist_sensor` / `persist_detection` (which
are idempotent on id, and honour `store.replaying`). Validation code is **not**
shared: the two use different topic schemes and payload contracts, and
`OpsIngestor` rejects (rather than flags and keeps) malformed input. Unifying them
would change master's endpoint behaviour, which master's tests pin, so that is left
as future work. Do not run both subscribers against the same broker topics for the
same devices without choosing one topic scheme per device, or readings are stored twice.

## Topics

The ingestor subscribes to exactly these filters (`OPS_INGEST_SUBSCRIPTIONS`):

| Filter | Category |
|--------|----------|
| `agriedge/+/weather/+/observations` | weather |
| `agriedge/+/soil/+/observations` | soil |
| `agriedge/+/water/+/observations` | water |
| `agriedge/+/irrigation/+/state` | irrigation (read-only state mirror) |
| `agriedge/+/rtk/+/state` | RTK station |
| `agriedge/+/gateway/+/health` | gateway health |
| `agriedge/+/+/detections` | vehicle detections |

## Pipeline: parse → validate → dedupe → store

1. **Parse topic** (`parse_ops_topic`). Unknown shapes, wildcards/empty segments and forbidden segments are rejected.
2. **Decode payload.** Max 64 KiB; must be a JSON object.
3. **Validate.** A payload `device_id` must match the topic. `ts` is required ISO-8601 with an explicit offset (naive rejected; more than `max_future_s` ahead rejected). Bare `temperature` / `temp` / `temp_c` / `temperature_c` keys are rejected — only typed `air_temp_c`, `soil_temp_c`, `water_temp_c`, `canopy_temp_c` are accepted. NaN/inf and wrong types are rejected. `synthetic` must be a bool; `synthetic: true` is carried onto every record it produces (origin SIMULATED). Rejects are counted and listed, never coerced into a plausible reading.
4. **Dedupe.** Key = (category, farm, device, UTC timestamp[, frame_id for detections]) in a bounded LRU. Record ids are deterministic hashes of the same key plus metric/depth, so a replay after a restart is an idempotent upsert, not a second row. Out-of-order (buffered) messages are accepted and inserted in timestamp order; messages older than `alert_max_age_s` (default 900 s) are stored but raise **no alert**.
5. **Store.** Written to `OpsStore` and, when `DATABASE_URL` is set, to the SQLite/PostGIS backend (see `POSTGIS_BACKEND.md`). Alerts are raised/resolved from the new data.

Each message yields a result with status `accepted | duplicate | rejected | ignored`; `ingestor.stats` holds the per-category counts.

## Quality flags

A payload `quality` may be `GOOD`, `QUESTIONABLE` or `BAD` (anything else is rejected). The flag stored is the **worse** of the device claim and the server-side checks (range, stuck, jump, low battery, weak signal, calibration overdue). A device can downgrade its own data; it can never upgrade it.

## Safety: subscribe-only, refuses command topics

* `OpsIngestor` has **no publish path**. Irrigation is ingested as *state* only; a state payload carrying `command`, `cmd`, `set`, `arm`, `mode`, `mission` or `setpoint` is rejected (`command_field_on_state_topic:<key>`).
* Topics containing the segments `mavlink, arm, mode, mission, rtl, aircraft, pixhawk, disarm` are rejected at parse time; `irrigation/<id>/set` is not a recognised ingest topic.
* The only publisher in the tree is the synthetic simulator; `assert_publishable()` in `transport.py` refuses `set`/`cmd`/`command` leaves and every forbidden segment.
* An ingested detection always has `may_drive_treatment=False` and `in_treatment_zone=None`, whatever the publisher claimed (the claim is kept under `payload.claimed`). Only `agri_edge.decision.engine` decides, from its own gates (itself simulated-actuator only).

## Running it

```bash
# against a broker (e.g. ground_iot Mosquitto); MQTT_USERNAME / MQTT_PASSWORD from the environment
pip install paho-mqtt            # imported lazily, only for a real broker
python scripts/ops_mqtt_ingest.py --host 127.0.0.1 --port 1883 --serve

# no broker: in-memory transport + synthetic publisher
python scripts/ops_mqtt_ingest.py --loopback --serve
```

Options: `--farm <id>` (repeatable filter), `--duration N`, `--api-host/--api-port`. `--serve` also serves the Ops API/UI, which keeps the SIMULATION banner on. Persistence follows `DATABASE_URL`.

## Round trip with the synthetic publisher

```bash
# terminal 1: ingest
python scripts/ops_mqtt_ingest.py --host 127.0.0.1 --port 1883
# terminal 2: publish synthetic data topics (never command topics)
python scripts/ops_sim_publish.py --mqtt --host 127.0.0.1 --port 1883 [--frost] [--replay]

# self-contained version: publish -> in-memory broker -> OpsIngestor -> store, then print
python scripts/ops_sim_publish.py --mqtt --loopback --replay
```

`--replay` sends every message twice to demonstrate dedupe; `--frost` publishes a sub-zero air temperature to demonstrate the alert. All published data is `synthetic: true`.

## Tests

`tests/test_ops_ingest.py` (in-memory, always run) and `tests/test_ops_ingest_broker.py` (real broker via paho; skipped unless one is reachable, set `AGRIEDGE_TEST_MQTT=host:port`).
