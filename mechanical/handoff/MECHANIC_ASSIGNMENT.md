# Mechanic assignment — agri-edge airframe + charging station

**For:** Anwar’s mechanical friend  
**From:** agri-edge software / product (Anwar)  
**Pack date:** 2026-09-19  
**Read first:** this file, then [README.md](README.md) (geometry, STLs, brief table)

> Software is largely complete. Hardware does not exist yet. Your job is the physical aircraft (Phase 1), then a ground charging station for the same airframe (Phase 2).

---

## Roles (crystal clear)

| Owner | Owns |
|-------|------|
| **You (mechanic)** | Airframe, power, vibration isolation, FOV clearance, rangefinder placement, weighed BOM, first flights, **charging station Phase 2**, wiring that interfaces with aircraft power |
| **Anwar** | ML models, phone app UI, VR software, NTRIP accounts, farmOS / cloud, edge pipeline, safety software contracts |

---

## Phase 1 — Flyable scouting quad (**PRIORITY**)

Build to the existing geometry pack. Do not redesign the mission: **scouting**, not mapping-grade photogrammetry, not spray.

### Build to

- Layout: **X-quad**, ~**650 mm** shaft-to-shaft wheelbase; Transport Canada **small RPAS** — stay **under 25 kg** all-up (estimate ~3.4 kg — **weigh real parts**)
- **Pixhawk-class** FC in the sandwich; **Pi 5 + Hailo** in the belly payload enclosure
- Nadir **Camera Module 3 (IMX708)** on **vibration isolators**
- **FOV clearance:** nothing in the camera view pyramid (landing gear on short FOV axis)
- Isolator natural frequency well below prop blade-pass (see README tables)
- **Downward rangefinder** for AGL — on payload plate, **out of FOV**
- Power: real **5 V / 5 A** regulation for the Pi; path to **clean shutdown before cutting flight power** (brief item 06)
- Ground anemometer stays on a **field-edge mast**, not on the airframe (brief item 08)

### Point at the files

| Path | Use |
|------|-----|
| [exports/](exports/) | STLs + GLB + blend — print / tube / packaging reference |
| [renders/](renders/) | Ortho + iso PNGs for orientation |
| [README.md](README.md) | Dimensions, mass estimates, 12-item brief, disclaimers |

**Structural** STLs (`01`–`04`, combined structural) are build reference. **Visual** STLs (`05`–`07`, props/motors/avionics) are envelopes only — do not machine them as flight structure.

### Phase 1 deliverables checklist

- [ ] Photos of assembled airframe (iso, top, belly / camera, FC bay, Pi enclosure)
- [ ] **Weighed BOM** (every major part on a scale; update vs estimate table)
- [ ] Confirm AUW ≪ 25 kg with real weights
- [ ] Bench vibration check against project image-quality metric (brief item 11)
- [ ] **First hover** (manual / FC only — Pi may be present but is not the pilot)
- [ ] **First camera flight** (nadir frames on disk; FOV clear of gear)
- [ ] Note any clearance or thermal issues for Anwar (so `airframe_spec` can be updated and exports regenerated)

### Explicit Phase 1 non-goals

- Spray hardware
- Charging dock (that is Phase 2 — do Phase 1 first)
- Autonomous docking
- Phone app commanding flight

---

## Phase 2 — Charging station / dock

**In scope now for the friend** (supersedes early brief item 12 “do not start the charging dock” as an early *priority* — dock is wanted, but **after** a flyable airframe).

### Intent

A ground charging pad or dock for the **same** Phase 1 airframe so turnaround between scouting flights is faster.

### Recommended approach (simplest safe v1)

1. **Landing-skid contacts** or a **manual plug bay** first  
2. Wireless pad only if contacts prove messy — still keep human-supervised landing  
3. **Autonomous docking later** — do **not** force precision auto-dock in v1

### Requirements

- Survive **outdoor prairie weather** (sun, dust, rain, freeze–thaw — seal and material choices are yours)
- Keep pad / posts / cables **clear of prop arcs** on approach and on the pad
- Honour brief item **06**: **Pi clean shutdown before power cut** — the dock must not yank 5 V / battery mid-write; coordinate with Anwar on the shutdown signal / interlock story
- Software interface note: [docs/DOCK_INTERFACE.md](../../docs/DOCK_INTERFACE.md) (status fields, handshake sequence/timeouts, phone `dock` topic shape, high-level contacts)
- No requirement for autonomous docking in v1
- Interface cleanly with the aircraft power architecture you built in Phase 1

### Phase 2 deliverables

- [ ] CAD of pad/dock + aircraft interface (contacts or plug bay)
- [ ] BOM (weather-rated parts called out)
- [ ] Wiring diagram (aircraft side + dock side; how charge current flows; shutdown / interlock)
- [ ] Short note: how it interfaces with aircraft power and the Pi 5 V rail
- [ ] Photos of prototype on the real airframe (even if contacts are temporary)

---

## Out of scope for mechanic (Anwar owns)

- ML models and training
- Phone app UI
- VR software
- NTRIP accounts / base station subscriptions
- farmOS / WebODM cloud ops
- Any software path that lets the phone **command** the aircraft

---

## Explicit non-goals (early product)

- **Spray hardware** — regulated, different business; software already fails closed without local validation + geofence
- **Autonomously commanding flight from the phone app** — Pi stays read-only toward the FC; phone does not become a second pilot

---

## Safety reminder (why the software is picky)

1. The Pi **never commands** the aircraft.  
2. Treatment **fails closed** without `validated_locally` + geofence.  

Your airframe should assume the companion computer can reboot or lose network mid-flight and the FC still flies its own failsafes.

---

Questions on numbers → change happens in `mechanical/airframe_spec.py` and exports get regenerated — do not hand-edit STLs to “fix” a clearance without updating the spec.
