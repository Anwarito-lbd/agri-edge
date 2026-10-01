# Ground IoT stack — Mosquitto + Node-RED

**Decision (19 Sep 2026):** Run **beside** agri-edge with Docker. Do not vendor Node-RED or Mosquitto source into this repo.

## Why
ESP32 soil / weather / pump nodes need a bus. MQTT (Mosquitto) + rule flows (Node-RED) give impressive automation without replacing our edge CV, geofence, or dashboard IP.

## Start
```bash
bash ground_iot/mosquitto/make_passwd.sh   # once: users sensor / agriedge / nodered
cd ground_iot
docker compose up -d
```
- Mosquitto: `127.0.0.1:1883` (MQTT), `9001` (websockets). **No anonymous
  clients**; each role has a password and an ACL (`mosquitto/acl`). Only the
  `nodered` user may publish `…/irrigation/set`.
- Node-RED UI: http://127.0.0.1:1880 — set `adminAuth` in its `settings.js`
  before exposing it; the editor can deploy a flow that opens valves.
- Everything binds to loopback. To reach field devices, enable the TLS listener
  in `mosquitto/mosquitto.conf` and publish 8883 rather than 1883.

Requires Docker Desktop (Stage 0).

## Architecture (ground only)

```
ESP32 ──MQTT──► Mosquitto ──► Node-RED (rules / weather gate)
                    │              │
                    ▼              ▼
              agri-edge API    ESP32 pump/valve
              / companion      (irrigation/set)
```

**Hard boundary:** topics under `…/irrigation/set` are **ground actuators**. Never forward them to Pixhawk / MAVLink. The flight Pi stays read-only toward the aircraft.

## Field devices, one identity each

```bash
# Wi-Fi (ESPHome) soil probe in zone z1: prints the device's secrets.yaml once
python -m agri_edge.iot.provision add soil-01 --farm farm --zone z1 --kind soil
# LoRaWAN node (no MQTT password: it talks to ChirpStack, the bridge republishes)
python -m agri_edge.iot.provision add lora-soil-7 --farm farm --zone far-quarter \
    --kind soil --transport lorawan --dev-eui A84041000181C0DE
python -m agri_edge.iot.provision list
python -m agri_edge.iot.provision revoke soil-01
docker kill -s HUP agriedge-mosquitto      # re-read passwd + acl
```

Each device gets a random password (hash only is stored, Mosquitto `$7$`
format), an ACL block for exactly its zone's topics (a valve node may *read*
`irrigation/set`, never write it), and an entry in `mosquitto/devices.json`,
which the ops station uses to raise a DEVICE alert when a device misses three
of its reporting intervals.

### Firmware
- `firmware/esphome/soil-station.yaml` — ESP32, two capacitive probes (10/30 cm),
  DS18B20 temperatures, battery, deep sleep, one JSON message per wake.
- `firmware/esphome/weather-station.yaml` — BME280, anemometer, vane, rain gauge,
  every 60 s. Wind at 2 m is what gates spraying.
- Both publish the contract payloads exactly (checked in `tests/test_ground_sensors.py`).
  **Calibrate** probes (dry/wet voltages per probe) and the anemometer/rain gauge
  constants before trusting a number.

### LoRaWAN (range beyond Wi-Fi)
- Run ChirpStack v4 unmodified from upstream
  [chirpstack-docker](https://github.com/chirpstack/chirpstack-docker) (US915 for Canada).
- Device profile codec: `lorawan/chirpstack_codec.js`. Payload layout:
  `lorawan/PAYLOAD.md`. Node-side encoder in C: `lorawan/firmware/agriedge_payload.{h,c}`.
- Bridge ChirpStack uplinks onto the contract topics:
  `CHIRPSTACK_MQTT_HOST=… AGRIEDGE_MQTT_HOST=… python -m agri_edge.iot.lorawan ground_iot/mosquitto/devices.json`.
  Unregistered devEUIs are dropped.

## farmOS
Already have a client (`store/farmos.py`). Study farmOS concepts (farm → field → zone → observation); integrate via API later — do not merge farmOS source.

## ThingsBoard / ESPHome
- ThingsBoard: defer (would own the story).
- ESPHome: reference for ESP32 sensor firmware patterns only.

## Topics
See [MQTT_CONTRACT.md](../docs/MQTT_CONTRACT.md).

## agri-edge code
Topic helpers: `src/agri_edge/iot/mqtt_topics.py`  
Optional bridge stub: `src/agri_edge/iot/mqtt_bridge.py`
