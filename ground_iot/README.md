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
