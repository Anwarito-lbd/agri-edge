# MQTT contract — agri-edge ground IoT

**Broker:** Mosquitto (see `ground_iot/`)  
**Scope:** Farm sensors + irrigation actuators on the **ground**. Not aircraft command.

## Topic tree

```
agriedge/farm/{farm_id}/zone/{zone_id}/soil
agriedge/farm/{farm_id}/zone/{zone_id}/weather
agriedge/farm/{farm_id}/zone/{zone_id}/status
agriedge/farm/{farm_id}/zone/{zone_id}/irrigation/set
agriedge/farm/{farm_id}/zone/{zone_id}/irrigation/status
```

Optional later:
```
agriedge/farm/{farm_id}/zone/{zone_id}/thermal_proxy
agriedge/farm/{farm_id}/alerts/{alert_id}
```

Vehicle reports (scouting aircraft → ops station; report-only, no command kind exists):
```
agriedge/farm/{farm_id}/vehicle/{vehicle_id}/detections
agriedge/farm/{farm_id}/vehicle/{vehicle_id}/health
```

## Where messages land

Every topic above except `irrigation/set` is accepted by the ops station through
one function, `agri_edge.ops.ingest.ingest(store, topic, payload)`, used by both
the MQTT subscriber (`AGRIEDGE_MQTT_HOST` set) and `POST /api/ops/ingest`
(`{topic, payload}` or `{messages: [...]}`). `irrigation/set` is a command and is
refused there. Readings are quality-flagged, never dropped; `ts` is optional
(receive time is used) and a future or unparseable `ts` is replaced and flagged.
With `--db`, every accepted message is logged and replayed on restart.

## Payload shape (JSON, snake_case)

### soil (ESP32 → broker)
```json
{
  "schema_version": 1,
  "ts": "2026-09-19T20:00:00Z",
  "moisture_pct": 18.5,
  "temp_c": 16.2,
  "device_id": "esp32-zone1-a"
}
```

Multi-depth probes send `"depths": [{"depth_cm": 10, "moisture_pct": 22.5, "temp_c": 12.0}, ...]`
instead of the top-level `moisture_pct` / `temp_c`. Optional on every kind:
`battery_pct`, `rssi`, `lat`, `lon`.

### weather (station → broker)
```json
{"ts": "…", "device_id": "wx-01", "air_temp_c": 14.2, "rh_pct": 71,
 "wind_ms": 3.1, "wind_dir_deg": 250, "precip_mm": 0.2,
 "pressure_hpa": 1011.6, "solar_wm2": 540}
```

### status (any device → broker)
```json
{"device_id": "soil-01", "battery_pct": 81, "rssi": -72, "uptime_s": 86400,
 "firmware": "esphome-2026.9", "error_code": null}
```

### irrigation/status (valve node → broker)
```json
{"device_id": "valve-z1", "valve_open_pct": 100, "flow_lpm": 38.5}
```

### vehicle detections (aircraft → broker), one message per processed frame
```json
{"schema_version": 1, "ts": "…", "device_id": "scout1",
 "frame": {"sequence": 42, "lat": 50.44, "lon": -104.61, "alt_rel_m": 60, "qa_passed": true},
 "model": {"name": "imageweeds_yolox_s", "version": "1", "validated_locally": false},
 "unplaced": 1,
 "detections": {"type": "FeatureCollection", "features": [
   {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-104.61, 50.44]},
    "properties": {"label": "kochia", "confidence": 0.81, "position_error_m": 1.9}}]}}
```
Only georeferenced detections are features; `unplaced` counts the rest. The ops
station stores the edge's `may_drive_treatment` as `edge_may_drive_treatment` and
never sets its own.

### irrigation/set (Node-RED / backend → ESP32)
```json
{
  "schema_version": 1,
  "ts": "2026-09-19T20:01:00Z",
  "command": "on",
  "duration_s": 300,
  "liters": null,
  "reason": "moisture_below_20_no_rain"
}
```
`command`: `on` | `off` | `pulse` only.

### Forbidden
- Any topic that arms, modes, or missions an aircraft
- Bridging `irrigation/set` into MAVLink
- Treating phone companion as an irrigation commander without auth (add later)

## Example Node-RED flow (logic)
soil moisture → MQTT in → function (moisture < 20?) → HTTP weather check →  
rain expected? → no irrigate / else MQTT out `irrigation/set`

## Security
No anonymous clients (since 24 Sept 2026): `ground_iot/mosquitto/acl` gives
sensors write on readings and read on `irrigation/set`, the `drone` user write
on its two report topics, the `agriedge` backend read-only, and Node-RED alone
write on `irrigation/set`. Per-device credentials: see `ground_iot/README.md`.

## Operations Station topics (§124)

```
agriedge/{farm}/weather/{station}/observations
agriedge/{farm}/soil/{station}/observations
agriedge/{farm}/water/{station}/observations
agriedge/{farm}/irrigation/{controller}/state
agriedge/{farm}/irrigation/{controller}/events
agriedge/{farm}/rtk/{station}/state
agriedge/{farm}/gateway/{gateway}/health
agriedge/{farm}/alerts
```

Vehicle topics (future, same envelope):
```
agriedge/{farm}/{vehicle}/telemetry
agriedge/{farm}/{vehicle}/detections
...
```
