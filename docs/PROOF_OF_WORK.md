# Agri-Edge Unified Platform — Proof of Work & Verification Ledger

**Branch:** `feat/unified-agri-edge-platform`  
**Unified Repository Target:** `Anwarito-lbd/agri-edge` (incorporating `feat/batch2`, `cursor/portfolio-proof-4352`, and `Anwarito-lbd/agri-edge-web` unified under `apps/web/`)  
**Truthfulness Policy:** All numerical outputs, test totals, linters, type checks, physics computations, plots, screenshots, and Playwright video recordings listed below were **directly executed and observed** in this workspace. Hardware flights, live Hailo-8 silicon inference, and pressurized spray valves remain **BLOCKED-HARDWARE / NOT FIELD-VALIDATED**.

---

## 1. Unified Code & Architecture Verification Matrix

Executed after integrating `apps/web/`, hardening Windows path/encoding test filters, adding `scripts/simulate_airframe_physics.py` and `tests/test_simulate_airframe_physics.py`, polishing `/hardware` & `/proof`, and generating all visual & documentation assets:

| Component | Command | Observed Result | Notes |
|---|---|---|---|
| Core runtime boundary | `python -m pytest tests/test_runtime_deps.py -q` | **247 passed** | Verifies clean Raspberry Pi runtime (`numpy`, `pyyaml` core) |
| Full Python test suite | `python -m pytest -q` | **2,082 passed, 40 skipped** | Skips cover tests requiring physical camera/Hailo, live Mosquitto, or PostGIS |
| Physics plot generation | `python scripts/simulate_airframe_physics.py` + `pytest tests/test_simulate_airframe_physics.py -v` | **1 passed** (4 PNGs + JSON verified) | Exercises `mechanical/airframe_spec.py`, `geo/`, `sensors/environment.py`, `decision/engine.py` |
| Python linter | `python -m ruff check src tests training workstation mechanical scripts` | **All checks passed!** (0 errors) | Clean across runtime, training, mechanical, and scripts |
| Static type checker | `python -m mypy src/agri_edge --ignore-missing-imports` | **7 pre-existing errors in 5 files** (122 checked) | Under CI ratchet limit (`<= 11` in `.github/workflows/test.yml`) |
| Web TypeScript | `npm run typecheck` (`apps/web/`) | **0 errors** | Next.js `16.3.5` + React `19.2.8` strict check |
| Web ESLint | `npm run lint` (`apps/web/`) | **0 errors** (3 pre-existing warnings) | Pre-existing `react-hooks/set-state-in-effect` warnings in `ops/` pages |
| Web Vitest Suite | `npm test` (`apps/web/`) | **7 files, 124 tests passed** | Covers fail-closed `/api/ops/*` proxy policy, demo datasets, forms, roles, PWA |
| Web Production Build | `OPS_API_URL=http://127.0.0.1:1 npm run build` (`apps/web/`) | **0 errors, 22 routes compiled** | Verified static + App Router SSR/API routes |

---

## 2. Physics, Flight, Spray & ML Optics Outputs (`scripts/simulate_airframe_physics.py`)

Generated directly from repository classes into `docs/proof/physics_sim_summary.json` and mirrored plots in `docs/proof/` & `apps/web/public/proof/`:

### Tier 1 — Parametric 650 mm Scouting X-Quad (`mechanical/airframe_spec.py`)
- **All-Up Weight (`total_mass_g`):** `3,432 g` (`1,100 g` airframe, `600 g` propulsion, `145 g` avionics, `1,250 g` 6S 10Ah battery, `337 g` payload; `100%` estimated weights)
- **Propulsion & Power:** `2,200 g` max thrust per motor -> **`2.564:1` TWR**, **`0.39` hover throttle**, **`411.33 W` total hover power** (including `30 W` avionics), **`+950 g` max extra payload** at `TWR >= 2.0`
- **Endurance & Area Coverage:** **`23.55 min` hover** (`37.68 min` on 6S 16Ah), **`20.55 min` survey flight**, **`46.84 m` swath** at `30 m` AGL, **`67.44 ha/h` raw coverage rate**, **`23.10 ha/battery`**
- **Vibration & Gear Clearance:** `35.0 Hz` payload isolator (`k = 3.87 N/mm` per mount, `0.203 mm` static sag) vs `153.33 Hz` hover blade-pass (`4.38x` isolation ratio) and `226.67 Hz` full throttle; `260 mm` landing leg radius leaves **`0.135 m` optical clearance margin** (`in_frame = False`)
- **Plot:** [`docs/proof/airframe_endurance_physics.png`](proof/airframe_endurance_physics.png)

### Tier 2 — Coverage Planning & 3D Ray-Plane Georeferencing (`geo/coverage.py`, `geo/georeference.py`)
- **Boustrophedon Survey (`9.12 ha` notched polygon):** `0.0°` optimal heading, `7` passes at `37.47 m` effective swath (`20%` overlap of `46.84 m`), `2,490 m` line + `225 m` turn = `2,715 m` total, **`0.000` unvisited gap** on outer contour under `46.84 m` swath
- **Attitude Sensitivity:** At `30 m` AGL, a `10°` aircraft roll shifts the camera principal point on the ground plane by **`5.29 m`**
- **Geofence Interlock (`TreatmentGeofence` with exclusion hole):** `2` inside-zone points permitted (`may_treat = True`), `2` outer/hole points refused (`may_treat = False`)
- **Plot:** [`docs/proof/georef_3d_trajectory.png`](proof/georef_3d_trajectory.png)

### Tier 3 — Spray Flow Rate & Wind Advisory Envelope (`WATER_ONLY_BENCH_TEST_PLAN.md`, `sensors/environment.py`)
- **Feed-Forward Pump Curve:** `Q = R * v * W * 0.006` -> **`7.68 L/min`** at `R = 20 L/ha`, `v = 8 m/s`, `W = 8 m` swath (`23.04 ha/h`)
- **Wind-Source Gate:** `EnvironmentReading.spray_advisory` rejects `wind_source = "airframe"` (`unknown`), flags calm inversions (`w < 0.83 m/s`) and high wind (`w > 5.56 m/s`) or high VPD (`> 2.0 kPa` / `T > 30°C`, `RH < 40%`) as `poor`
- **Plot:** [`docs/proof/spray_drift_envelope.png`](proof/spray_drift_envelope.png)

### ML Model Cards & IMX708 Pinhole Optics (`models/*_CARD.md`, `training/gsd_calculator.py`, `training/motion_budget.py`)
- `aerial_sheep_yolox_s`: **AP@.50 `0.9049`**, **AP@.50:.95 `0.4664`** (`5,603` test GT boxes, Public Domain)
- `imageweeds_yolox_s`: **AP@.50 `0.4570` / `0.673` binary**, **AP@.50:.95 `0.2590` / `0.375`** (`306` test GT boxes, CC BY 4.0)
- `weed_crop_yolox_s`: **AP@.50 `0.6893`**, **AP@.50:.95 `0.3924`** (`781` test GT boxes, CC BY 4.0, indoor propagation tray caveat)
- `IMX708` (`6.45 mm`, `4.74 mm`, `4608 px`) -> `640 px` input = **`7.2x` linear downscale**; native GSD at `30 m` = **`0.886 cm/px`** (`1.77 ms` max exposure @ `5 m/s`, or `2.309 ms` at `Airframe.performance()`'s `1.155 cm/px` survey model)
- **Plot:** [`docs/proof/ml_models_optics_envelope.png`](proof/ml_models_optics_envelope.png)

---

## 3. Standalone Pipeline Demo Artifacts (`scripts/portfolio_demo.py`)

Verified existing outputs in `docs/proof/summary.json`, `coverage.json`, `decisions.json`, `agronomy.json`:
- `coverage.json`: `90°` heading, `18` lines, `4,188 m` total (`3,780 m` line + `408 m` turn), `905.6 s`, `3.12%` gap (`80x80` grid)
- `cli_fly.log` & `frames.json`: `12/12/12` simulated 5-band frames (`320x240`), Laplacian `188.6–190.4` (`>100` QA threshold), `27.52 m` travel, uncalibrated NDVI `[-0.505, 0.674]` (`calibrated: false`), `validated_locally: false`
- `decisions.json`: `1` allowed, `7` blocked across all safety interlock failure modes (`NOT_OPERATOR_ARMED`, `MODEL_NOT_VALIDATED`, `CONFIDENCE_BELOW_THRESHOLD`, `OUTSIDE_TREATMENT_GEOFENCE`, `MISSION_STATE_NOT_PERMITTED`, `COMMAND_EXPIRED`, `POSITION_INVALID`)
- `agronomy.json`: FAO-56 Example 18 Brussels **`3.880 mm/day`** (published reference `3.9 mm/day`); 21-day canola balance (`26.8 -> 10.2 -> 20.1 mm`)

---

## 4. Headless Browser Screenshots & Video Walkthrough (`apps/web/`)

Captured with headless Chromium Playwright against `next start -p 3100` (`OPS_DEMO_DEFAULT=1`), with every PNG/SVG/GIF/MP4 visually inspected:

| Artifact | Dimensions / Format | Purpose |
|---|---|---|
| [`docs/proof/agri-edge-walkthrough.mp4`](proof/agri-edge-walkthrough.mp4) | `1280x720` H.264 (`1.85 MB`) | ~27s end-to-end interactive UI walkthrough across `/`, `/hardware`, `/proof`, `/ops`, `/ops/map` |
| [`docs/proof/agri-edge-walkthrough.webm`](proof/agri-edge-walkthrough.webm) | `1280x720` VP8 (`5.63 MB`) | Raw Playwright `recordVideo` capture |
| [`docs/proof/agri-edge-walkthrough.gif`](proof/agri-edge-walkthrough.gif) | `760px`, 10 fps (`5.96 MB`) | Lightweight README inline walkthrough preview |
| [`docs/proof/web_home_desktop.png`](proof/web_home_desktop.png) | `1440x900` PNG | Unified landing page |
| [`docs/proof/web_hardware_desktop.png`](proof/web_hardware_desktop.png) | `1440x900` PNG | Airframe CAD + 3 Drone Tiers + YOLOX-s Model Cards |
| [`docs/proof/web_proof_desktop.png`](proof/web_proof_desktop.png) | `1440x900` PNG | Proof gallery top view |
| [`docs/proof/web_proof_physics_desktop.png`](proof/web_proof_physics_desktop.png) | `1440x900` PNG | Uncropped simulation plots + concept hero banner |
| [`docs/proof/web_ops_desktop.png`](proof/web_ops_desktop.png) | `1440x900` PNG | Operations dashboard (SIMULATED demo banner active) |
| [`docs/proof/web_ops_map_desktop.png`](proof/web_ops_map_desktop.png) | `1440x900` PNG | Interactive Leaflet polygon/layer map view |
| [`docs/proof/web_home_mobile.png`](proof/web_home_mobile.png) | `390x844` PNG | Responsive mobile landing check (zero overflow) |
| [`docs/proof/web_ops_mobile.png`](proof/web_ops_mobile.png) | `390x844` PNG | Responsive mobile operations dashboard check |
| [`docs/images/agri-edge-fleet-hero.png`](images/agri-edge-fleet-hero.png) | `1376x768` PNG (`1.97 MB`) | Concept / illustrative fleet + station visual art (explicitly labeled non-telemetry) |

---

## 5. Explicit Unproven / Hardware-Blocked Scope

Per `docs/status.md` and `docs/mechanical/WATER_ONLY_BENCH_TEST_PLAN.md`:
1. **No physical aircraft flight** has taken place (Pixhawk/Cube MAVLink was only exercised with ArduCopter SITL + synthetic telemetry).
2. **No Raspberry Pi 5 + IMX708 + AI HAT+ (Hailo-8 `.hef`) capture** has run on live embedded silicon.
3. **No pressurized bench pump or outdoor nozzle spraying** has executed; `TreatmentDecisionEngine.SIMULATION_ONLY` remains `True` and `validated_locally` remains `False`.
4. **No live field farmOS / AgOpenGPS hardware capture** has run (verified strictly over loopback mock servers and UDP fixtures).
