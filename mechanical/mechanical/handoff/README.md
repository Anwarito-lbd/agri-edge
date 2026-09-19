# Agri-Edge airframe — mechanic handoff pack

**For:** Anwar's mechanical friend building the scouting drone  
**From:** software-derived geometry in `mechanical/airframe_spec.py` (not a hand sketch)  
**Date pack built:** 2026-09-19

> **This pack is clearance / geometry / packaging guidance.**  
> It is **NOT** a structural FEA analysis. Arm stiffness, plate cracking, fastener
> sizing, and material allowables are your call as the builder. The software only
> cares that clearances, tip gap, vibration isolation frequency, and mass stay
> inside the numbers below.

---

## 1. Overall architecture

| Item | Spec |
|------|------|
| Layout | **X-quad**, motor shaft–to–shaft wheelbase **650 mm** |
| Class | Transport Canada **small RPAS** — stay **under 25 kg** all-up |
| Autopilot | Pixhawk-class flight controller (avionics bay in sandwich) |
| Compute / camera | **Raspberry Pi 5 + Hailo AI HAT** in a belly payload enclosure |
| Camera | Pi **Camera Module 3 (IMX708)**, nadir, on **vibration isolators** |
| Mission | Field scouting / weed detection (not mapping-grade photogrammetry) |

All-up mass in the current estimate table: **~3.43 kg**. That is almost entirely
**unweighed estimates** until parts hit a scale — size the airframe against real
weights (brief item 02).

---

## 2. Key dimensions (from `airframe_spec`)

### Rotors / frame

| Quantity | Value | Notes |
|----------|-------|-------|
| Wheelbase (diagonal, shaft–shaft) | **650 mm** | X layout |
| Propeller | **15 in** (2-blade) | Tip gap ~**79 mm** (~21% of diameter) |
| Adjacent motor spacing | ~460 mm | Must keep tip gap ≥ ~10% of diameter |
| Body plate (L × W) | **220 × 180 mm** | Sandwich plates |
| Plate gap | **45 mm** | Between top and bottom plate |
| Arm OD (model) | **25 mm** | Tube envelope in the Blender model |
| Motor height (envelope) | **50 mm** | Visual packaging |

### Camera / landing gear / FOV

Sensor: IMX708, focal length 4.74 mm → half-angles from nadir:

| Axis | Half-angle |
|------|------------|
| Long (image width) | **38.0°** |
| Short (image height) | **30.3°** |
| Corners (worst) | **44.3°** |

| Quantity | Value |
|----------|-------|
| Payload drop under bottom plate | **60 mm** (isolator stack) |
| Lens drop under payload | **35 mm** |
| Lens height above feet | **~160 mm** |
| Landing-gear foot radius | **260 mm** from optical axis |
| Leg azimuth in image frame | **90°** (legs on **short** FOV axis) |
| Pyramid needs at that azimuth | **~94 mm** radius → margin **~166 mm** |
| Pyramid needs at a corner | **~156 mm** → still clear at 260 mm |

**Non-negotiable:** no landing gear, boom, antenna, or rangefinder in the camera
FOV. Put legs on the short axis of the sensor; keep anything below the lens
outside the view pyramid.

### Vibration isolation (blade-pass)

| Quantity | Value |
|----------|-------|
| Hover RPM (design) | ~4600 → blade-pass **~153 Hz** (2 blades) |
| Full-throttle RPM | ~6800 → blade-pass **~227 Hz** |
| Isolator target (payload) | **~35 Hz** natural frequency |
| Isolation ratio at hover | **~4.4×** (want ≥ 3×) |
| Per-mount spring rate (4 mounts, 0.32 kg isolated) | **~3.87 N/mm** |
| Static sag under 1 g | **~0.20 mm** |

Frame structural modes should sit **above** full-throttle blade-pass (~227 Hz).
This pack does **not** prove that — it only sizes the isolator frequency.

### Sensors placement notes

- **Downward rangefinder** for AGL (height above terrain, not takeoff point) —
  on the payload plate, **out of FOV**.
- **Anemometer / wind vane on the ground**, field-edge mast — **not on the
  airframe** (downwash ruins the reading). Brief item 08.
- Environment temp/humidity boom can sit on the airframe in clean air, away from
  Pi exhaust / motors / battery (brief item 07).

---

## 3. What is in this folder

```
mechanical/handoff/
  README.md                 ← this file
  scripts/export_airframe.py
  exports/                  ← meshes + blend + glb
  renders/                  ← orthographic / iso PNGs
```

### `exports/` — STL / GLB inventory

**Units:** Blender / STL scale is **metres** (1 Blender unit = 1 m). In a slicer
or CAD, scale ×1000 for millimetres if your tool assumes mm.

| File | Role | Use |
|------|------|-----|
| `00_combined_structural.stl` | **structural** | Plates + arms + landing gear + camera mount joined |
| `00_combined_all_reference.stl` | mixed | Full overview including visual props/avionics |
| `01_plates_structural.stl` | **structural** | Top/bottom plates + standoffs |
| `02_arms_structural.stl` | **structural** | Four arms |
| `03_landing_gear_structural.stl` | **structural** | Legs + feet (FOV-critical) |
| `04_camera_mount_structural.stl` | **structural** | Isolators + enclosure + camera body |
| `05_motors_visual.stl` | **visual** | Motor envelopes for packaging only |
| `06_props_visual.stl` | **visual** | Blades + swept discs — **tip-gap / clearance only** |
| `07_avionics_payload_visual.stl` | **visual** | Battery, Pi/Hailo, regulator, rangefinder, env boom |
| `agri_edge_airframe.glb` | web | Browser / glTF viewers |
| `agri_edge_airframe.blend` | source | Regenerated from `airframe_spec` |
| `EXPORT_MANIFEST.txt` | index | Same list with byte sizes |

**Structural** = intended build / print / tube-layout reference.  
**Visual** = do not machine or FEA these as flight structure; they show envelopes
and clearances.

### `renders/`

| File | View |
|------|------|
| `airframe_iso.png` | Perspective-ish iso overview |
| `airframe_top.png` | Ortho top (nose up) |
| `airframe_front.png` | Ortho front |
| `airframe_side.png` | Ortho side |

---

## 4. The 12-item airframe brief (non-negotiables)

Source: `docs/progress-report-and-airframe-brief.html`. Every item comes from
something the software measures or enforces.

| # | Item | What it means for the build |
|---|------|-----------------------------|
| 01 | Settle the mission before the airframe | Scouting first — not mapping. Mapping needs ~3× airtime and a different mass story. |
| 02 | Lock a payload budget and **weigh** parts | Estimates until on a scale. Stay **decisively under 25 kg**. |
| 03 | Camera mount: nadir, rigid, isolated | Lens looks straight down; plate stiff; soft mounts between plate and airframe. |
| 04 | Vibration isolation vs blade-pass | Mount resonance **well below** prop blade-pass (see table above). Rolling shutter turns vibe into wobble that looks like a software bug. |
| 05 | Thermal for Prairie summer | Light-coloured enclosure; Pi + Hailo get hot in sun — throttling kills ground speed quietly. |
| 06 | Power: **5 V at 5 A**, clean shutdown | Real regulator + bulk caps; orderly Pi shutdown before cutting flight power. |
| 07 | Weather sensor where it can read weather | Boom in clean air; away from Pi exhaust, motors, battery. |
| 08 | **Ground weather mast** | Wind speed/direction for spray records: **anemometer on the ground, not the drone**. |
| 09 | Landing gear + lens clearance + **rangefinder** | **No gear in FOV.** Downward rangefinder for **AGL**, also out of FOV. |
| 10 | Register the aircraft and mark it | Transport Canada registration / physical marking. |
| 11 | Bench-test vibration with our quality metric | Shake the mount on the bench; use the project's image-quality metric before first flight. |
| 12 | Do not start the charging dock | Out of scope for this airframe pass. |

**Especially call out to the builder:**

1. **No landing gear in camera FOV** (item 09).  
2. **Isolator natural frequency vs blade-pass** (item 04).  
3. **Rangefinder for AGL** on the payload plate, clear of the pyramid (item 09).  
4. **Anemometer on the ground mast**, never on the airframe (item 08).

---

## 5. Mass budget notes (estimates until weighed)

Current `MassBudget` roll-up (~**3432 g**):

| Group | Est. grams |
|-------|------------|
| Energy (6S 10 Ah) | 1250 |
| Airframe (frame + gear + wiring) | 1100 |
| Propulsion (motors, ESC, props) | 600 |
| Payload (Pi, Hailo, cooler, cam, enclosure, sensors, regulator) | 337 |
| Avionics (FC, GNSS, radios, RX) | 145 |

- **100% of this mass is currently `weighed=False`.** Treat AUW, T/W, and
  endurance as provisional until you weigh the kit.
- Soft targets from the checks: T/W ≥ 2.0, hover ≤ ~60% available thrust,
  AUW ≪ 25 kg (we are at ~3.4 kg estimated).

---

## 6. How to regenerate exports (optional)

On a machine with Blender and this repo:

```bash
blender -b -P mechanical/handoff/scripts/export_airframe.py -- --out mechanical/handoff/exports
```

That rebuilds from `mechanical/airframe_spec.py` via `mechanical/blender_airframe.py`,
then writes the STLs / GLB / blend above.

To rebuild the four PNGs:

```bash
blender -b -P mechanical/blender_airframe.py -- --out runs/airframe
```

---

## 7. Explicit disclaimer (again)

- Clearances, tip gap, FOV pyramid, isolator frequency, and mass **estimates**: yes.  
- Structural FEA, fatigue, crashworthiness, certified materials: **no — not in this pack.**  
- Props, motors, and avionics meshes are **visual envelopes**, not production CAD.

Questions on numbers → change `mechanical/airframe_spec.py` and regenerate; do not
hand-edit the STLs to “fix” a clearance without updating the spec.
