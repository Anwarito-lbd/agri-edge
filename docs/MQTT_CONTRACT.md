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

## Security (MVP → next)
MVP compose uses `allow_anonymous` for laptop demos only. Before any real farm: require username/password or TLS, and ACL so ESP32 cannot publish `irrigation/set` for other zones.
