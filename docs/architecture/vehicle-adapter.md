# VehicleAdapter

**Status:** IMPLEMENTED (interface + ArduPilotAdapter stub) · physical FC commands = BLOCKED-HARDWARE.

## Rules
- Companion MAVLink remains **read-only** by default
- Command methods (`arm`, `disarm`, `set_mode`, `upload_mission`) go through `SafetySupervisor` and **fail closed**
- SITL/sim may enable commands only when `allow_commands=True` and `require_sitl` satisfied
- Never wire YOLO/LLM → motors
