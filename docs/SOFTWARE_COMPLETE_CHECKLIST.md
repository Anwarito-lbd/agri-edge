# Software complete checklist — agri-edge

**Owner:** Anwar (software / product)  
**Audience:** Anwar — honest inventory before friend builds metal  
**Date:** 19 September 2026 (ET)  
**Sources:** [HANDOFF.md](../HANDOFF.md), [PRODUCT_VISION.md](PRODUCT_VISION.md), [PITCH.md](PITCH.md), [MECHANIC_ASSIGNMENT.md](../mechanical/handoff/MECHANIC_ASSIGNMENT.md)

> **Blunt summary:** Core edge pipeline and safety contracts are **Built+tested** without aircraft. Product surfaces Anwar owns are **mixed** — marketing site and phone UI shell exist; live telemetry/alerts, farmer maps, dock software, and VR are **not** ready. Do **not** tell anyone “software is 100% done.” Hand friend metal when the Section C gate items are finished, not when CI is green.

**Status labels used below**

| Label | Meaning |
|-------|---------|
| **Built+tested** | Code exists; unit/integration tests pass on this box (no real aircraft required) |
| **Trained** | Model weights + eval numbers exist; field validity is a separate bar |
| **Designed-only** | Spec / roadmap / UI mock — little or no production implementation |
| **Not started** | No meaningful design or code yet |
| **Blocked on hardware** | Software scaffolding exists; cannot become true without Pi/camera/aircraft/services |

---

## A. Core agri-edge (mostly DONE)

Edge runtime: capture → QA → inference → indices → spool → provenance. ~606 tests. Permissive-only licence boundary. Pi cannot command the aircraft (MAVLink read-only by construction).

### Built+tested

| Item | Notes |
|------|--------|
| Edge pipeline | Integration-tested end-to-end on stubs / fake telemetry |
| YOLOX numpy decode / letterbox / NMS | Verified vs YOLOX torch to ~1e-5 |
| Tiled inference | ~2.3× more detections than whole-frame in tests |
| Green-on-brown (GoB / ExG) | Classical path; faster than YOLOX; no NPU |
| Detection georeference | Ray-plane → lat/lon + error budget |
| Coverage planning | Boustrophedon + heading search; gap checker caught real bugs |
| Reflectance calibration | Empirical-line from panel → `calibrated=True` path |
| Treatment geofence | Flight vs treatment GeoJSON; fails closed with treatment gate |
| NTRIP client | Corrections → GNSS receiver serial; **never** MAVLink write |
| Env / spray advisory | Wind-first; refuses verdict without wind |
| MAVLink read-only link | Fault-injected against real protocol; no write methods |
| farmOS / WebODM clients | Written; **stub-tested** only (no live Docker here) |
| CI | Lean (import boundary) + extras jobs |
| `airframe_spec` + Blender / STL pack | Geometry exports for mechanic handoff |

### Trained (with limitations — do not oversell)

| Model | Result | Honest limitation |
|-------|--------|-------------------|
| `aerial_sheep_yolox_s` | sheep AP@.50 **0.905** on 5,603 boxes; runs on bare Pi | Other people’s sheep imagery — still need local validation for product claims |
| `imageweeds_yolox_s` | species AP@.50 **0.457**; binary weed **0.673** | Labels are potted specimens; precision understates field reality. horseweed/ragweed/kochia usable; **redrootpigweed / waterhemp are not IDs** — treat as “a weed” |
| `weed_crop_yolox_s` | weed AP@.50 **0.749** | **Pipeline proof only.** Source set is not aerial (trays + ground close-ups). Never quote as field performance |

### Designed-only (software path exists on paper / scripts)

| Item | Notes |
|------|--------|
| Hailo HEF compile / runtime path | Scripts + engine stubs; needs **WSL + Hailo hardware** to become Built+tested |

### Blocked on hardware (scaffolding ≠ done)

| Item | Why blocked |
|------|-------------|
| Pi camera channel-order verify | Picamera2 “RGB888” may be BGR; never confirmed on real camera — half the indices are R/B-asymmetric |
| `validated_locally: true` | Deliberately unset until Anwar’s own fields are annotated and models revalidated |
| Real SITL | No compiler / WSL / Docker on prior box; `sitl.sh` refuses early; `fake_autopilot` ≠ autopilot |
| Real WebODM / farmOS | Clients stub-tested; servers’ acceptance of requests **not** proven |

**Section A verdict:** Core scouting pipeline software is in good shape for a **software MVP**. It is **not** field-complete. Hardware + local validation are the real remaining bar for Section A claims in a demo or pitch.

---

## B. Product surfaces Anwar owns

Must **design fully**; build what can ship **without aircraft**. Status + next software deliverable for each.

| # | Surface | Status | Next software deliverable (no aircraft required) |
|---|---------|--------|--------------------------------------------------|
| 1 | Marketing site + proof | **Built+tested** (`agri-edge-web`) | Keep site honest: link this checklist / pitch; refresh proof artefacts when models or handoff pack change |
| 2 | Phone companion `/app` | **UI shell Built** (mock data); protocol **Designed-only** → see [PHONE_PI_CONTRACT.md](PHONE_PI_CONTRACT.md) | Design+implement read-only WebSocket/HTTP client against a **laptop mock Pi** server; heartbeats, GPS, battery, GeoJSON detections, QA flags — **no** arm/mode/mission |
| 3 | Geo mapping UI | Georeference **Built+tested** in pipeline; farmer map UI **Designed / partial** (dashboard mock) | Wireframes or implemented map mock on site: fields, detection layer, mission footprint, error-budget display |
| 4 | Weather-adaptive missions | Advisory **Built+tested**; full replan **Designed-only** | Surface go/no-go + advisory in companion app from env/advisory APIs; do **not** pretend closed-loop replan exists |
| 5 | Emergency phone alerts | **Designed-only** | Spec alert types + push/SMS path in contract doc; implement mock alert feed in app before live LTE |
| 6 | VR situational view | **Designed-only (Later)** | Out of MVP gate; optional WebXR sketch only if time — not a handoff blocker |
| 7 | Charging station software | **Designed-only**; mechanic builds hardware Phase 2 | Write dock electrical/software interface note (status, charge state, Pi shutdown handshake) for friend — see Section C |

**Section B verdict:** Anwar’s public face (site) is ahead of the operator product (live phone↔Pi, maps, alerts, dock). Closing B.2–B.5 design + mocks is the software work that matters **before** metal, not Hailo HEF polish.

---

## C. Definition of “Anwar’s side complete enough to hand friend metal”

Finish these in **software/docs** before asking the friend to cut carbon / buy motors. Mechanical Phase 1 can start from the existing STL pack; this list is what Anwar should not leave half-written so the friend is not guessing interfaces.

| Done? | Gate item | Notes |
|-------|-----------|--------|
| [x] | Mechanic handoff pack STLs + README | `mechanical/handoff/` exports + README + assignment — **done** |
| [ ] | `PITCH.md` + `MECHANIC_ASSIGNMENT.md` + `PRODUCT_VISION.md` | Files **exist** under `docs/` and `mechanical/handoff/` as of 19 Sep 2026 — treat this checkbox as **content-complete / reviewed by Anwar**, not “file missing”. Re-read and tick when you sign off. |
| [ ] | Software API/contracts doc for phone↔Pi (read-only telemetry, alerts) | **Create/finish** [PHONE_PI_CONTRACT.md](PHONE_PI_CONTRACT.md) — this checklist assumes first draft lands with it |
| [ ] | Charging dock electrical/software interface note for friend | Short note: dock status, charge state, **Pi clean shutdown before power cut**; pin/handshake story — Anwar owns software side of the handshake |
| [ ] | Geo map + alert UX wireframes or implemented mocks on site | Dashboard mock is not enough until map + alert flows are visible to a non-coder |

**When Section C is all checked:** friend has geometry + role clarity + interface notes; Anwar has not claimed live telemetry or field-validated treatment. **Then** hand metal.

**Still not required for metal handoff:** Hailo HEF on device, real SITL, real WebODM, VR, spray hardware, autonomous docking, `validated_locally`.

---

## D. What “done” is *not*

- Green pytest ≠ flown aircraft  
- Stub farmOS/WebODM ≠ integrated ops stack  
- Sheep AP 0.905 ≠ Canadian livestock product claim without local data  
- Advisory ≠ weather replan  
- Phone UI shell ≠ phone↔Pi protocol  
- Designed dock handshake ≠ Phase 2 hardware  

Be blunt in pitches: **software MVP for scouting perception is largely built; operator product and hardware validation are not.**

---

## E. Suggested Anwar order (software-only week)

1. Sign off / tick Section C vision+pitch+mechanic docs after one careful read.  
2. Finish and publish `PHONE_PI_CONTRACT.md`; stand up a mock Pi telemetry server for the phone app.  
3. Map + alert UX mocks on `agri-edge-web` (or companion `/app`).  
4. One-page **dock interface note** for friend (shutdown interlock + status topics).  
5. Only then: WSL/Docker/Hailo compile path — useful, **not** the metal gate.

---

*Last updated: 19 September 2026 (America/Toronto).*
