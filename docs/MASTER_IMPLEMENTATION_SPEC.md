# MASTER IMPLEMENTATION SPEC (governing)

**Source:** product owner brief 19 Sep 2026. Full phase text retained in conversation; this file is the durable summary agents must follow.

## Mission
Closed loop: SENSE → UNDERSTAND → GEOREFERENCE → DECIDE → SAFETY → ACT → MEASURE → LOG → MAP → LEARN. Agri-Edge is the integration brain; third parties are components.

## Rules
1. AI never directly controls flight motors / LLM never drives FC actuators.
2. FC owns attitude, mixing, failsafes. Linux may later command missions only through adapters + safety.
3. Payload safety independent of AI confidence alone.
4. Every external system behind an adapter interface.

## Current vs future
- **Today:** Pi companion **MAVLink read-only**; treatment gated; ground MQTT irrigation separate.
- **Later:** VehicleAdapter may expose mission/arm for SITL and approved ops — never bypass safety supervisor.
- **Edge Profile A (now):** Pi 5 + Hailo. **Profile B (later):** Jetson-class. Do not block MVP on Jetson.
- **Autopilot:** Keep ArduPilot SITL working; ADR-0001 for PX4 long-term; do not dual-support in product early.

## Immediate priority order
1. Repo audit (Phase 0)  
2. Dev environment + CI  
3. Validate YOLOX pipeline  
4. YOLOX → ONNX → Hailo HEF → Pi inference  
5. Camera → Hailo live  
6. Normalized Detection API  
7. MQTT (vehicle + ground)  
8. Backend/PostGIS  
9. Dashboard decisions UI  
10. ArduPilot SITL + VehicleAdapter  
… then georef hardening, tracking, decision/safety, simulated actuator, OWL integration, water-only bench, mapping, farmOS, AgOpenGPS, PX4 eval.

## First meaningful product milestone
REAL CAMERA → Pi 5 → Hailo → YOLOX → normalized detections → MQTT → dashboard. No autonomous physical treatment until that is reliable.

## Definition of done
Implementation + tests + docs + no secrets. Hardware tasks need explicit VALIDATED status (IMPLEMENTED / SIMULATED / BENCH / HARDWARE / FIELD).
