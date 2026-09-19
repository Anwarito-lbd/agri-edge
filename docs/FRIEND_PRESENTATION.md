# agri-edge — Friend presentation

**For:** mechanical friend (Phase 1 airframe)  
**From:** Anwar (software / product)  
**Date:** 19 September 2026  
**Live site:** https://agri-edge-web.vercel.app  
**Code:** https://github.com/Anwarito-lbd/agri-edge · https://github.com/Anwarito-lbd/agri-edge-web

---

## 1. One-liner

**agri-edge** is a Canadian RPAS companion-computer scouting platform (weeds, livestock, vigour) — Pi 5 + camera + Pixhawk, under 25 kg. Software scouts and alerts; the pilot/FC flies. **Not a spray robot on day one.**

---

## 1b. Platform, not “sheep app”

Competitors sell thermal + multispectral + stress maps. We **already** have on-device CV, geo, QA, and safety. Sheep/weeds are the first models on a **platform**. Next: thermal, multispectral, disease — and laptop-side scene relations ([RelateAnything](RELATE_ANYTHING.md), licence-gated). Full gap table: [NICHE_GAP_ANALYSIS.md](NICHE_GAP_ANALYSIS.md).

## 2. What is DONE (Anwar’s side)

| Area | Status |
|------|--------|
| Edge pipeline (capture → QA → inference → indices → spool) | Built + tested (~606 tests) |
| Safety: Pi **read-only** to aircraft; treatment locked until `validated_locally` + geofence | Enforced in code |
| Models (YOLOX Apache-2.0) + green-on-brown (OpenWeedLocator MIT port) | Trained / ported — still need **local** field validation |
| Georeference, coverage planning, geofence (AgOpenGPS-inspired) | Built |
| Product website (NAV CANADA–clean) + proof + dashboard map | Live on Vercel |
| Phone companion `/app` | Live **mock Pi** feed (SSE) — status/alerts only, **cannot arm/fly** |
| Mechanic handoff: STLs, GLB, Blender, product renders | In `mechanical/handoff/` |
| Docs: pitch, vision, phone↔Pi contract, dock interface, Stage 1 buy list | Written |

**Honest limit:** software is **MVP / pitch ready**, not field-complete. `validated_locally` stays false until real Canadian imagery is annotated.

---

## 3. What YOU build

### Phase 1 — flyable scouting quad (now)
Follow **`mechanical/handoff/MECHANIC_ASSIGNMENT.md`** and the renders in `mechanical/handoff/renders/`.

- Airframe to `airframe_spec` / exports (under 25 kg)
- FC (Pixhawk-class), power, RC, telemetry
- Mount for **Pi 5 + Camera Module 3** (downward / survey geometry)
- Downward rangefinder for AGL (needed for georef quality)

### Phase 2 — charging dock (later)
Simple contacts first. Software handshake: **`docs/DOCK_INTERFACE.md`** (Pi clean shutdown before power cut). No autonomous docking as v1.

---

## 4. What Anwar does next

1. **Tomorrow+:** Flash **Raspberry Pi OS Bookworm 64-bit** on a spare SD (keep Vocular QNX card). Same Pi 5 + Camera Module 3.
2. Run `scripts/pi_setup.sh` → camera channel-order check → green-on-brown smoke.
3. Reflectance panel + field-edge walk → annotate → path to `validated_locally`.
4. Optional: WSL2 + Docker (SITL / WebODM); AI HAT later for Hailo speed.
5. Wire live phone↔real Pi (mock already proves the UX).

---

## 5. Out of scope (friend + product v1)

- Spray / treatment payload on day one  
- Phone commanding flight (arm / mode / mission)  
- Autonomous precision docking as v1  
- Claiming field weed-species accuracy before local validation  

---

## 6. Links to open in the meeting

| What | Where |
|------|--------|
| Live site | https://agri-edge-web.vercel.app |
| Companion mock | https://agri-edge-web.vercel.app/app |
| Proof / airframe shots | https://agri-edge-web.vercel.app/proof |
| Engineering repo | https://github.com/Anwarito-lbd/agri-edge |
| Website repo | https://github.com/Anwarito-lbd/agri-edge-web |
| Your assignment | `mechanical/handoff/MECHANIC_ASSIGNMENT.md` |
| Dock note | `docs/DOCK_INTERFACE.md` |
| Pitch | `docs/PITCH.md` |

Local folder: `Desktop\agricultrul\`

---

## 7. Ask for tomorrow

1. Walk the **renders + STLs** together — anything unclear in geometry/mounts?  
2. Agree **Phase 1 BOM + rough timeline**.  
3. Confirm Pi/camera mount and CG with the existing Blender pack.  
4. Park Phase 2 dock until Phase 1 flies.

---

*Pi flash + first camera validation: scheduled after this meeting.*
