# Building & Unifying Agri-Edge: Fail-Closed Companion Autonomy, Edge Vision, Airframe Physics & Operations Station

I wanted a companion computer that could survey a field without being trusted to fly the aircraft, and without being trusted to open a valve because a neural network was confident. That constraint shaped every architectural boundary across the Python edge runtime (`src/agri_edge/`), the offline training toolchain (`training/`), the parametric airframe CAD & physics (`mechanical/`), and the unified Next.js Operations Station (`apps/web/`).

---

## 1. The Architectural Split: Autonomy vs. Safety

A Raspberry Pi 5 running Linux userspace processes (camera capture, tile inference, SQLite spooling, MQTT telemetry) will eventually stall, exhaust thermal headroom, or run an uncalibrated model out-of-distribution. The flight controller (Pixhawk/Cube running ArduPilot) owns attitude control, EKF state estimation, hardware geofences, battery failsafe, and RTL.

1. **Read-Only Vehicle Boundary (`src/agri_edge/telemetry/mavlink_link.py`):** The companion subscribes to MAVLink telemetry and implements **zero methods** capable of arming, changing flight modes, or uploading missions (`tests/test_mavlink_faults.py` and `test_architecture_guardrails` verify this boundary). Any future guidance adapter (`src/agri_edge/vehicle/adapter.py`, `safety.py`) passes through a fail-closed `SafetySupervisor` and is non-operational in flight today.
2. **Ten-Gate Spray Interlock (`src/agri_edge/decision/engine.py`):** Every `Detection` carries `validated_locally = False` by default (`src/agri_edge/inference/engine.py`). `TreatmentDecisionEngine` sets `SIMULATION_ONLY = True` and refuses construction unless the actuator explicitly marks `simulated = True`. Even in simulation, applying a command requires all 10 sequential gates: operator arm, payload arm, confidence `>= threshold`, `validated_locally == True`, finite latitude/longitude, fresh level pose, recomputed `TreatmentGeofence.may_treat` (including inner exclusion holes), healthy actuator heartbeat, `TREATMENT_ACTIVE` mission state, and a single unexpired human command.
3. **Ground-Isolated Web & Proxy Control Plane (`apps/web/`):** Originally developed in `Anwarito-lbd/agri-edge-web` and now unified into `apps/web/`, the Operations Station enforces a strict allowlist proxy policy (`apps/web/src/lib/ops-proxy-policy.ts`) that rejects unauthorized write methods, requires session roles for approvals, falls back explicitly to deterministic `DEMO / SIMULATED` datasets (`src/lib/ops-demo.ts`, `src/lib/ops-scenario.ts`) when `OPS_API_URL` is unset, and guarantees via its offline PWA service worker (`public/sw.js`) that `POST`/`PUT`/`PATCH`/`DELETE` requests are **never queued or silently replayed**.

---

## 2. Optics Before Neural Networks

Treating aerial seedling/weed detection as an ML problem before solving pinhole optics leads to false confidence. Using `training/gsd_calculator.py` (`native_gsd_cm`) for the Raspberry Pi Camera Module 3 (`IMX708`: $6.45\text{ mm} \times 3.63\text{ mm}$ active sensor, $4.74\text{ mm}$ focal length, $4608 \times 2592\text{ px}$ at $1.4\,\mu\text{m}$ pixel pitch):

$$\text{Ground Width (m)} = \frac{w_{\text{sensor}}}{f} \cdot h_{\text{AGL}}, \qquad \text{GSD}_{\text{native}} (\text{cm/px}) = \frac{100 \cdot w_{\text{ground}}}{N_x}$$

Letterboxing the $4608$-pixel native frame down to a $640 \times 640$ YOLOX-s input throws away **$7.2\times$ of linear spatial resolution** before inference begins:

- At **$30\text{ m}$ AGL**, $\text{GSD}_{\text{native}} = 0.886\text{ cm/px}$ ($40.82\text{ m}$ ground width). A $3\text{ cm}$ seedling occupies **$3.39\text{ px}$ tiled** and only **$0.47\text{ px}$ whole-frame** — physically unresolvable regardless of model architecture. Requiring a $20\text{ px}$ detection floor caps $3\text{ cm}$ seedling detection at **$0.7\text{ m}$ whole-frame** and **$5.1\text{ m}$ tiled**.
- A **$30\text{ cm}$ mature weed** stays above $20\text{ px}$ up to **$7.1\text{ m}$ whole-frame** vs. **$50.8\text{ m}$ tiled**, while a **$120\text{ cm}$ sheep** remains detectable up to **$24.6\text{ m}$ AGL** whole-frame (and $200\text{ cm}$ cattle up to **$41.0\text{ m}$**).

Reclaiming resolution via overlapping native $640 \times 640$ tiles (`src/agri_edge/inference/tiling.py`) shifts the constraint onto **motion blur and rolling-shutter skew** (`training/motion_budget.py`):
- Whole-frame downscaling hid up to $7.2\text{ px}$ of motion smear inside $1$ network pixel. At native resolution, keeping smear $\le 1\text{ px}$ at $30\text{ m}$ AGL and $5\text{ m/s}$ leaves an exposure budget of $1.77\text{ ms}$ (and $2.31\text{ ms}$ under `Airframe().performance()`'s $1.155\text{ cm/px}$ nominal survey model).
- Assuming an uncalibrated $\sim 33\text{ ms}$ full-frame rolling-shutter readout on `IMX708` (`READOUT_S["imx708"]`), full-frame geometry exceeds $5\text{ px}$ skew above $1.3\text{ m/s}$, motivating `IMX296` global shutter or slower photogrammetry passes vs. rapid scouting.

---

## 3. ML Training Pipeline & Honest Dataset Audits (`training/`, `models/`)

Every detector uses **Megvii YOLOX-s** (`depth=0.33`, `width=0.50`, `8.94M` parameters, Apache-2.0 — deliberately excluding AGPL/GPL detectors per `NOTICE.md`) exported to static `640x640` ONNX opset 11 with **raw head output** (`decode_in_inference = False`), explicit SiLU expansion, and host-side class-wise NMS in pure NumPy (`src/agri_edge/inference/yolox.py`). Crucially, `training/evaluate.py` benchmarks the **deployed `OnnxEngine`** (with `PAD_VALUE = 114` RGB uint8 letterboxing), never the training-only PyTorch path.

Two engineering fixes keep long local GPU runs (`YOLOX` checkpoints) resilient without touching gitignored `vendor/YOLOX`:
1. `training/train_resilient.py` catches transient `cuDNN`/`CUDA` runtime faults and automatically appends `--resume`, refusing to treat YOLOX's `finally:` exit banner as completion unless the final epoch appears in `train_log.txt`.
2. Each `training/exps/*_yolox_s.py` allowlists NumPy scalars in `torch.serialization.add_safe_globals` for PyTorch 2.6+ `--resume`, and stubs `yolox.layers.fast_coco_eval_api` to `None` so evaluation cleanly uses `pycocotools` without requiring MSVC/ninja JIT builds on Windows.

Auditing the imagery uncovered dataset failure modes that aggregate mAP hides:
- **`aerial_sheep_yolox_s` (Public Domain, `5,603` test GT boxes across `174` images):** Source photos contained up to `105` sheep per frame (`mean = 31`), silently truncating against YOLOX's default `max_labels = 50` and turning real sheep into background negatives. Raising `MAX_LABELS = 150` / `MAX_LABELS_MOSAIC = 450` and preventing `.rf.` augmented leakage across splits achieved **AP@.50 = `0.9049`**, **AP@.50:.95 = `0.4664`**, viable on a bare Raspberry Pi CPU without Hailo acceleration.
- **`imageweeds_yolox_s` (CC BY 4.0, `306` test GT boxes across `70` nadir images, 150 epochs):** Genuine $5472 \times 3648$ field plots of 5 Canadian Prairie herbicide-resistant species (`ragweed`, `waterhemp`, `horseweed`, `redrootpigweed`, `kochia`), deterministic SHA-256 split by source plot. Only transplanted potted weeds were annotated while natural weeds trained as background, causing the species head to favor dominant classes (`horseweed 0.7926`, `ragweed 0.6418`, `kochia 0.6245`; `redrootpigweed 0.1534`, `waterhemp 0.0726`; overall **5-class AP@.50 = `0.4570` / AP@.50:.95 = `0.2590`**). Collapsing predictions via `collapse_labels_to: weed` demonstrates solid localization (**binary `weed` AP@.50 = `0.673` / AP@.50:.95 = `0.375`**).
- **`weed_crop_yolox_s` (CC BY 4.0, `781` test GT boxes across `118` images):** Severe 95% weed / 5% crop imbalance where **98.3% of `crop` labels come from indoor propagation trays** ($\sim 30$–$80\text{ cm}$ range). Aggregate **AP@.50 = `0.6893` / AP@.50:.95 = `0.3924`** (`crop 0.6301`, `weed 0.7485`) serves strictly as **pipeline proof** (`validated_locally: false`).

---

## 4. Three Drone Platform Tiers, CAD & Flight/Spray Physics

In `mechanical/airframe_spec.py` (and `mechanical/blender_airframe.py` + STL/GLB exports), `docs/source/research-report.md`, and `docs/mechanical/WATER_ONLY_BENCH_TEST_PLAN.md`, the platform spans three operational tiers:

1. **Tier 1 — Parametric 650 mm Scouting X-Quad (`mechanical/airframe_spec.py`):** $3,432\text{ g}$ baseline AUW (`100%` estimated mass budget), `15 in` 2-blade props ($79\text{ mm}$ / $20.6\%$ tip gap), $2200\text{ g}$ max thrust/motor ($2.56:1$ TWR, $39\%$ hover throttle, $411.3\text{ W}$ hover power including $30\text{ W}$ avionics), $6\text{S }10\text{ Ah}$ battery ($80\%$ usable) yielding **$23.55\text{ min}$** total / **$20.55\text{ min}$** survey endurance and **$23.10\text{ ha/battery}$**. Its $35\text{ Hz}$ payload isolator ($k = 3.87\text{ N/mm}$ each, $0.20\text{ mm}$ sag) sits $4.38\times$ below the $153.3\text{ Hz}$ hover blade-pass frequency, and landing gear legs at $260\text{ mm}$ radius keep a $135\text{ mm}$ clearance margin outside the IMX708 view pyramid.
2. **Tier 2 — Broad-Acre Survey / VTOL Class (`docs/source/research-report.md`):** Long-endurance fixed-wing/QuadPlane survey profile modeled with `src/agri_edge/geo/coverage.py` boustrophedon planning (`best_heading` minimizing turn overhead) and `src/agri_edge/geo/georeference.py` full ZYX body-to-NED ray-plane ground intersection (because at $30\text{ m}$ AGL, a $10^\circ$ roll displaces the principal point by **$5.29\text{ m}$**, making flat GSD offsets unacceptable).
3. **Tier 3 — Precision Spot-Spray Actuation Class (`WATER_ONLY_BENCH_TEST_PLAN.md`, `geofence.py`, `environment.py`):** Feed-forward pump flow governed by $Q = R \cdot v \cdot W \cdot 0.006$ ($7.68\text{ L/min}$ at $R=20\text{ L/ha}$, $v=8\text{ m/s}$, $W=8\text{ m}$ swath), closed-loop gated by ground-mast wind sensors via `EnvironmentReading.spray_advisory`: rejecting airframe wind (`wind_source="airframe"`), flagging calm temperature inversions ($w < 0.83\text{ m/s}$) and excessive wind ($w > 5.56\text{ m/s}$) or evaporation risk ($T > 30^\circ\text{C}$, $\text{RH} < 40\%$, $\text{VPD} > 2.0\text{ kPa}$) as `poor`.

---

## 5. What Remains Unproven (Strict Honesty Contract)

Hardware execution rows in `docs/status.md` and `docs/mechanical/WATER_ONLY_BENCH_TEST_PLAN.md` remain **BLOCKED-HARDWARE / NOT FIELD-VALIDATED**:
- No physical Raspberry Pi + IMX708 + Hailo-8 bench or flight capture has run yet (`Picamera2Camera.verify_channel_order()` and reflectance-panel radiometric calibration are software-ready).
- No `.hef` model has executed on live Hailo silicon (only x86\_64 WSL2 preflight dry-run).
- No pump bench flow test or outdoor spraying has occurred; `validated_locally` remains `false` across all models in `ai/model_registry/registry.json`.
