# Next actions

Ordered plan after the software/docs push. Details and rationale live in [HARDWARE_PLAN.md](HARDWARE_PLAN.md), [HANDOFF.md](../HANDOFF.md), and [PRODUCT_VISION.md](PRODUCT_VISION.md).

## This week (free — Stage 0)

1. Install **WSL2 + Ubuntu 22.04** (admin PowerShell: `wsl --install -d Ubuntu-22.04`, reboot).
2. Install **Docker Desktop**.
3. Fix **GPU power mode** (Windows Best performance / NitroSense Performance / NVIDIA Prefer maximum performance).
4. Unblocks: `scripts/sitl.sh`, `scripts/hailo_compile.sh`, real WebODM + farmOS, faster retraining.

## Buy / build Stage 1 (~C$400)

5. Order the [STAGE1_BUY_LIST.md](STAGE1_BUY_LIST.md) kit (Pi 5 8GB, cooler, PSU, SD, Camera Module 3, ribbon, reflectance panel).
6. On hardware: `bash scripts/pi_setup.sh` → **verify camera channel order** → shoot panel → `compute_gains` → first calibrated indices.
7. Walk a field edge with the camera on a pole; **annotate** local imagery (only path to `validated_locally`).

## Then (Stages 2–5 + product)

8. **Stage 2:** AI HAT+ 26 TOPS; compile HEF in WSL2; benchmark tiled Hailo inference.
9. **Stage 3 (mechanical friend):** flyable scouting quad to the handoff pack (FC, airframe, power, RC, telemetry, **downward rangefinder** for AGL). Keep under 25 kg.
10. **Stage 4:** RTK / NTRIP for centimetre positioning and `qa.require_rtk_fixed`.
11. **Stage 5:** ground anemometer (+ optional PAR) for legal spray records / wind-gated advisory.

## Product / app later (from PRODUCT_VISION)

12. Farmer-facing **geo maps** in the phone companion (fields, detection layers, mission footprints).
13. **Weather-gated** missions in the companion app (go / no-go before launch).
14. Deeper **farmOS** automation (structured events and layers).
15. **Emergency phone alerts** when anomalies are flagged; **VR / WebXR** review over imagery/maps (after a real live-downlink path if seconds matter).
16. Mechanical **phase 2:** charging station / dock for the same airframe (simple contacts first). Out of scope early: spray payload, autonomous docking as v1, phone-commanded flight.

## Deliberately not doing

- No ROS 2 / Jetson / PX4 as the core stack (numpy-only Pi boundary is test-enforced).
- No spray hardware yet (regulatory + cost).
- No `validated_locally: true` until local field validation exists.
