# Target architecture — agri-edge as the brain

**Status:** North-star (19 Sep 2026). Parts exist today; dashed = Next/Later.  
**Rule:** agri-edge **connects** IoT, edge vehicle, records, and guidance. We do **not** merge Mosquitto/Node-RED/farmOS/ArduPilot/AgOpenGPS source into the product — we integrate at MQTT / HTTP / MAVLink / GPS boundaries.

```
                         AGRI-EDGE (brain)
                            │
              ┌─────────────┴─────────────┐
              │                           │
        FARM / IoT                    EDGE VEHICLE
              │                           │
     ESP32 sensors                  Raspberry Pi 5
              │                      + Hailo AI HAT
              ↓                           │
         Mosquitto                     Camera
           MQTT                           │
              │                           ↓
        ┌─────┴─────┐             YOLOX detector
        ↓           ↓                    │
    Node-RED    Agri-Edge API             ↓
                    │              Hailo inference
                    │                    │
                PostgreSQL               ↓
                    │              Weed detections
                    │                    │
                    │             OpenWeedLocator
                    │               (green-on-brown)
                    │                    │
                    │         treatment / actuator *
                    │
                    ├──────── MAVLink ** ──────────┐
                    │                               ↓
                    │                           ArduPilot
                    │                        Rover / Drone
                    │
                    └──────── GPS / guidance ──────┐
                                                    ↓
                                                AgOpenGPS
                                                    │
                                                    ↓
                                                  farmOS
                                          farm records / history
```

\* **Treatment / actuator:** fails closed. Requires `validated_locally` + treatment geofence. **Not** day-one spray product.  
\*\* **MAVLink from companion:** **read-only** toward the aircraft (existing hard rule). Flight authority stays pilot + FC.  
**Irrigation pumps/valves:** ground MQTT `…/irrigation/set` only — never MAVLink.

---

## What is already real

| Block | Today |
|-------|--------|
| Edge CV (YOLOX + green-on-brown) | Code + models |
| Georef, QA, geofence, wind advisory | Code |
| Companion mock + website | Live |
| farmOS **client** | Stub-tested; push spool |
| Ground IoT compose | `ground_iot/` Mosquitto + Node-RED |
| MQTT topic contract | `docs/MQTT_CONTRACT.md` |
| Thermal / MS index math | `sensors/` (needs cameras for field) |
| ArduPilot | Vendor + `sitl.sh` (needs WSL) |
| AgOpenGPS | Design reference for geofence (not live link yet) |

## What we build next (order)

1. Pi Bookworm + camera validate (Vocular hardware)  
2. Bring up `ground_iot` Docker → Node-RED soil→weather→irrigate demo  
3. PostgreSQL schema sketch (farm → field → zone → readings) behind Agri-Edge API  
4. Live phone ↔ Pi gateway (read-only topics)  
5. Hailo HEF when AI HAT present  
6. farmOS live Docker + richer observation push  
7. AgOpenGPS / guidance **interface note** (study concepts; optional NMEA/UDP later)  
8. Treatment actuator path only after local validation  

## Explicit non-goals

- Merging ThingsBoard as the product UI  
- Vendoring Node-RED / farmOS / ArduPilot into `src/`  
- Phone arm / mode / mission  
- Claiming spray-ready before `validated_locally`  

## Related docs

- [GROUND_IOT](../ground_iot/README.md) · [MQTT_CONTRACT.md](MQTT_CONTRACT.md)  
- [NICHE_GAP_ANALYSIS.md](NICHE_GAP_ANALYSIS.md) · [PHONE_PI_CONTRACT.md](PHONE_PI_CONTRACT.md)  
- [DOCK_INTERFACE.md](DOCK_INTERFACE.md) · [SENSING_P1.md](SENSING_P1.md)
