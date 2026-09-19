# Stage 1 — Buy list (minimum real imagery)

**Source of prices:** [HARDWARE_PLAN.md](HARDWARE_PLAN.md) Stage 1 (written 16 Sept 2026).  
**Goal:** ~C$400 of parts that produce **real local imagery** to annotate — **no aircraft required.** Carry the camera along a field edge on a pole.

| Item | Spec / notes | Approx. CAD |
|------|----------------|------------:|
| **Raspberry Pi 5, 8 GB** | Not 4 GB — tiling and ONNX want headroom | C$130 |
| **Active Cooler** | Pi 5 throttles without it, silently | C$10 |
| **27 W USB-C PSU** | Official; undervolting corrupts SD cards | C$20 |
| **microSD 128 GB A2** | Or better: NVMe HAT + SSD; spool quota assumes ~64 GB free | C$30 |
| **Camera Module 3** | IMX708 — the sensor `geo/georeference.py` defaults to | C$45 |
| **Camera ribbon, 300–500 mm** | Pi 5 uses the *narrow* connector — verify before ordering | C$10 |
| **Reflectance panel** | Calibrated grey target with a certificate | C$100–150 |

**Stage 1 total:** ~**C$345–395** (plan headline ~C$400).

## What this unblocks

1. `bash scripts/pi_setup.sh`
2. **Camera channel-order check** — `Picamera2Camera.verify_channel_order()` (Picamera2 "RGB888" often delivers BGR)
3. First `calibrated=True` indices via `geo/calibration.py` + the reflectance panel
4. Walk a field → annotate → path to `validated_locally: true`

## Not in Stage 1 (buy later)

| Stage | Item | Approx. CAD |
|------:|------|------------:|
| 2 | AI HAT+ 26 TOPS (Hailo-8) | C$150 |
| 3 | Aircraft / FC / batteries / RC | C$1,200–2,500 |
| 4 | RTK GNSS or NTRIP | C$600–1,600 |
| 5 | Anemometer + PAR | C$150–350 |

Do **Stage 0** first (free): WSL2 Ubuntu 22.04, Docker Desktop, GPU power mode — see HARDWARE_PLAN.
