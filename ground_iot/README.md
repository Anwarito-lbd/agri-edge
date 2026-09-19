# Ground IoT stack — Mosquitto + Node-RED

**Decision (19 Sep 2026):** Run **beside** agri-edge with Docker. Do not vendor Node-RED or Mosquitto source into this repo.

## Why
ESP32 soil / weather / pump nodes need a bus. MQTT (Mosquitto) + rule flows (Node-RED) give impressive automation without replacing our edge CV, geofence, or dashboard IP.

## Start
```bash
cd ground_iot
docker compose up -d
```
- Mosquitto: `localhost:1883` (MQTT), `9001` (websockets)
- Node-RED UI: http://localhost:1880

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
