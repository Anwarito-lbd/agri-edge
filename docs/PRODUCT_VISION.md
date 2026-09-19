# agri-edge — Product vision (website / roadmap)

Short public-facing roadmap. For the investor pitch see [PITCH.md](PITCH.md). For the builder see [../mechanical/handoff/MECHANIC_ASSIGNMENT.md](../mechanical/handoff/MECHANIC_ASSIGNMENT.md).

**Positioning:** companion-computer platform + scouting RPAS for Canadian farms — weeds, livestock, vigour — with edge QA and geo-mapped detections. Not a spray robot on day one.

---

## Geo mapping

Every detection that can be georeferenced becomes a map object — lat/lon plus an error budget — so a farmer sees *where* the model looked, not only a thumbnail.

- **Now:** edge spool with provenance; ray-plane georeferencing; coverage planning; treatment vs flight geofence for any future actuation.
- **Next:** farmer-facing geo maps in the phone/app (fields, detection layers, mission footprints).
- **Later:** deeper farmOS automation — structured events and layers into the farm system of record.

Public models are scaffolding. Shipping maps that drive decisions requires imagery from *your* fields and `validated_locally`.

---

## Weather adaptation

Prairie weather changes the mission before the model does.

- **Now:** environment sensors on the airframe (clean-air boom); ground anemometer for wind (not on the aircraft — downwash ruins it); wind-first spray/scout advisory that refuses a verdict without wind.
- **Next:** weather-gated missions — clear go / no-go and advisory surfaces in the companion app before launch.
- **Later:** autonomous weather replan (full adapt). Advisory exists; closed-loop replan is roadmap, not current software.

---

## Emergency alerts + VR

Two different needs often get one label:

| Need | Right tool | Horizon |
|------|------------|---------|
| Something looks wrong *now* | Phone alert + live status / video path | **Later** (alerts); live downlink before VR |
| Review the farm *after* | Photogrammetry mesh + VR / WebXR viewer | **Later** |

- **Now:** phone companion concept for **alerts & status**, read-only toward the aircraft. Pi never commands flight.
- **Next:** richer status and farmer maps; weather gates.
- **Later:** emergency phone alerts when an anomaly is flagged; VR first-person / situational check as a presentation layer over imagery and maps — not a substitute for a live downlink when seconds matter.

---

## Safety (always on)

1. **Pi never commands the aircraft** — MAVLink read-only by construction.
2. **Treatment fails closed** without `validated_locally` **and** geofence membership. An unasked question is not a yes.

---

## Mechanical roadmap (friend)

| Phase | Deliverable |
|-------|-------------|
| **1 (priority)** | Flyable scouting quad to the handoff pack |
| **2** | Charging station / dock for the same airframe (simple contacts or plug bay first) |

Out of scope for early hardware: spray payload; autonomous docking as a v1 requirement; phone-commanded flight.
