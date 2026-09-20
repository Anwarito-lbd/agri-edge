# ADR-0001 — Flight stack

**Status:** Accepted for near-term · PX4 deferred  
**Date:** 2026-09-19

## Context
Master spec prefers Pixhawk/PX4/ROS2 long-term for heavy-lift research. Repo today has ArduPilot vendor + `sitl.sh` and a **read-only** MAVLink companion link. Dual production autopilot support early would split effort.

## Decision
1. **Keep ArduPilot SITL + existing MAVLink read-only code functional.**
2. Introduce `VehicleAdapter` interface before adding mission/arm commands.
3. Document PX4 as **evaluation track** after SITL + adapter are green (Milestone B).
4. Do **not** delete ArduPilot integration to chase the diagram.

## Companion authority (product)
Until an explicit product decision + safety supervisor lands: **Pi must not write MAVLink.** Mission upload/arm remain FC/GCS or future gated adapter paths — never YOLO→motor.

## Consequences
- Short-term: finish `sitl.sh` on WSL; wrap reads behind adapter.
- Medium-term: ADR update if PX4 wins bake-off (SITL, ROS2, licensing, hardware).
