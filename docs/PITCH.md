# agri-edge — Founder pitch

**Audience:** investors, partners, demo rooms  
**Team:** two people — software/product (Anwar) + mechanical (friend)  
**Market:** Canadian agriculture / prairie scouting  
**Date:** 19 September 2026

---

## 1. One-liner

**agri-edge** is a smart-agriculture companion-computer platform and scouting RPAS that makes farming decisions easier — weeds, livestock, vigour — not a spray robot on day one.

---

## 2. Problem

Farmers still walk or fly fields and then wait. Imagery without edge quality checks and local ML is slow to turn into a decision. Public models were trained on other people’s fields — they do not equal Canadian crops, growth stages, or light. And treatment without local validation plus a geofence is dangerous: a false positive on a map is a wasted trip; the same false positive wired to hardware is wasted chemical, crop damage, or an environmental incident.

---

## 3. Solution

**agri-edge** puts perception next to the autopilot, not instead of it:

- **Raspberry Pi 5 + Hailo** companion computer beside a **Pixhawk-class** flight controller
- Pipeline: **edge → workstation → cloud** (capture, QA, inference, indices, spool, provenance)
- **Phone companion** for alerts and status (read-only toward the aircraft)
- **Geo-mapped detections** — pixels to lat/lon with an error budget
- **Weather-aware mission advice** (wind-first spray advisory; advisory exists today)
- **Roadmap:** VR / first-person situational check when something looks wrong (emergency path)

Safety is structural, not marketing:

1. The Pi **never commands** the aircraft (MAVLink is read-only by construction; tests assert no write path).
2. Treatment **fails closed** without `validated_locally` **and** a treatment geofence.

---

## 4. What’s already built (software)

Honest inventory from the project handoff — no hardware required to run the suite:

- Edge pipeline: capture → QA → inference → indices → spool → provenance (integration-tested)
- Models: livestock sheep AP@.50 **0.905** (runs on a bare Pi); prairie weeds (species + binary); seedling binary as pipeline proof
- Detection **georeferencing** (ray-plane → lat/lon + error budget)
- **Coverage planning** (boustrophedon, heading search, gap checks)
- Treatment **geofence** (flight vs treatment boundary, GeoJSON, wired into the pipeline)
- **NTRIP / RTK** client (corrections to the GNSS receiver, never injected as autopilot writes)
- farmOS / WebODM clients (written; stub-tested)
- Spray-condition advisory (wind-gated; refuses a verdict without wind)
- MAVLink telemetry fault-injected against the real protocol
- **600+ tests**, lean Pi dependency boundary (numpy + PyYAML at import)
- Airframe **geometry pack** for the builder (STLs, GLB, FOV / tip-gap / isolator numbers)

Everything remaining that blocks a field demo is **hardware that does not exist yet**.

---

## 5. What’s missing (honest)

- Physical aircraft + nadir camera + (Phase 2) charging pad / dock
- Local field validation on Anwar’s crops (`validated_locally` is nowhere set to true — by design until then)
- Live phone ↔ drone link (status path sketched; live link not shipped)
- VR viewer (roadmap presentation layer, not a day-one deliverable)
- Autonomous weather replan (advisory exists; full mission adapt is roadmap)

---

## 6. Two-person split

| Who | Owns |
|-----|------|
| **Anwar** | Software, product, models, phone/app UI, cloud integrations, safety contracts, farmer-facing maps |
| **Mechanical friend** | Airframe, power, vibration isolation, FOV clearance, sensors placement, **charging station (Phase 2)**, hardware integration |

Software is largely complete for a scouting MVP. The ask to the builder is the flyable airframe first — then the dock.

---

## 7. Product vision layers

| Layer | Horizon | What the farmer gets |
|-------|---------|----------------------|
| Scouting drone + edge detections + geo-mapped spool + phone status (read-only) | **Now** | Walk less; see weeds / livestock / vigour with provenance; aircraft stays under autopilot safety logic |
| Charging station / dock; weather-gated missions; farmer geo maps in the app | **Next** | Faster turnaround between flights; don’t launch into bad spray/scout weather; maps they can act on |
| Emergency phone alerts + VR first-person / situational check on anomaly; deeper farmOS automation | **Later** | When something looks wrong, get eyes on it fast; push structured events into the farm system of record |

Spray hardware and phone-commanded flight are **explicit non-goals** early.

---

## 8. Ask

1. **Build the airframe** to the mechanical handoff pack (`mechanical/handoff/` — STLs, GLB, README, assignment).
2. **Optional Phase 2:** design and build a **charging station / dock** for the same airframe (contacts or simple plug bay first; no forced autonomous docking in v1).

Partners and investors: we are selling a **decision platform** with a clear Canadian-ag wedge — not a spray promise we cannot safely keep yet.

---

*Related:* [PRODUCT_VISION.md](PRODUCT_VISION.md) · [HANDOFF.md](../HANDOFF.md) · [mechanical/handoff/MECHANIC_ASSIGNMENT.md](../mechanical/handoff/MECHANIC_ASSIGNMENT.md)
