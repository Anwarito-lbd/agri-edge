# Niche gap analysis — agri-edge vs precision-ag RPAS (2025–26)

**Date:** 19 September 2026 (America/Toronto)  
**Purpose:** Research what the niche expects, what we have, what we build next.  
**Decision owner:** Anwar (decided 19 Sep 2026)

---

## 1. What the niche expects

Canadian / global scouting stacks (SkyFlow, TerraSkyAI, Sairone, Sentera-class payloads, academic UAV+AI papers) converge on:

| Capability | Why farmers care |
|------------|------------------|
| RGB AI detect (weeds, stand, livestock) | Targeted scouting / labour |
| Multispectral indices (NDVI, NDRE, …) | Vigour / N stress before naked eye |
| Radiometric **thermal** | Water stress, irrigation faults, frost |
| Geotagged maps + prescription exports | Act on a zone, not a pretty picture |
| Disease / pest models | Early intervene |
| Edge or fast turnaround | Minutes matter vs overnight cloud |
| Clear ROI / data ownership | Adoption barrier |

Recurring research gaps: domain shift across farms/seasons; confounding drought vs disease vs nutrient; drone-only soil moisture is weak; closed-loop spray is regulated + expensive.

---

## 2. What agri-edge already has (not “sheep only”)

| Layer | Status |
|-------|--------|
| On-device **YOLOX** CV (Apache-2.0) | Livestock + weed models trained |
| Green-on-brown (OpenWeedLocator MIT port) | Classical vegetation, bare Pi |
| Georeference + error budget | Built |
| QA flags | Built |
| Flight vs treatment geofence | Built (fails closed) |
| Wind advisory | Built |
| Companion phone mock (alerts, no fly) | Live on web |
| Mechanic airframe pack | Done |
| Platform rule | New capability ≈ model or sensor, not rewrite |

**Pitch line:** MVP proves the **edge scouting platform**. Sheep/weeds are the first *payloads* on that platform — not the ceiling.

---

## 3. Gap table

| Capability | Competitor norm | agri-edge today | Priority | Build path |
|------------|-----------------|-----------------|----------|------------|
| Weed / livestock RGB AI | Common | **Have** (validate locally) | P0 | Pi Bookworm + field annotate |
| Geo maps + alerts | Common | **Have** (mock live) | P0 | Wire real Pi gateway |
| Thermal / water stress | Sentera-class / FLIR | **Missing** | **P1** | Thermal cam payload + CWSI-style layer (Demo UI now; hardware Next) |
| Multispectral NDVI/NDRE | Mavic 3M / RedEdge | RGB ExG only | **P1** | MS camera Stage+; index pipeline reuse |
| Disease / nutrient AI | Growing | Not started | P1→P2 | Dataset + YOLOX class head; no AGPL Ultralytics |
| Stand count / emergence | Common | Designed-only | P2 | Counting head on RGB |
| Soil moisture | IoT / SAR fusion | Missing | P2 | Ground probe → companion topic (not drone-only) |
| Scene **relations** | Rare / research | Missing | P1 research | **RelateAnything laptop-only** (see RELATE_ANYTHING.md) |
| Spot spray closed-loop | DJI Agras etc. | Out of scope v1 | Later | After validation + regs |
| VR check-in | Niche | Designed Later | Later | After live downlink |

---

## 4. Licence gates (non-negotiable)

| Tech | Code | Weights / data | agri-edge rule |
|------|------|----------------|----------------|
| YOLOX | Apache-2.0 | OK | **Ship on Pi** |
| OpenWeedLocator port | MIT | OK | **Ship on Pi** |
| YOLOv8/v11 | AGPL | — | **Never** link into product |
| **RelateAnything** | Apache-2.0 repo | **DINOv3** weights + Gemma-labelled RA-4M | **Laptop / research only** — not Pi flight image |
| ArduPilot / WebODM | GPL/AGPL | — | Process / Docker boundary only |

---

## 5. 90-day build order (decided)

1. **P0 — Make MVP real:** Bookworm on Vocular Pi 5 + Cam Module 3 → channel order → field annotate → `validated_locally` path.  
2. **P0 — Story:** Vision page + pitch use “platform + Next sensors,” not “sheep app.”  
3. **P1 — Thermal (software first):** Demo thermal/stress layer on site + `docs` sensor contract; hardware BOM for FLIR-class / Pi thermal when budget allows.  
4. **P1 — Multispectral path:** Spec bands + index math in pipeline (reuse calibration/georef).  
5. **P1 — RelateAnything:** Vendor clone on laptop; offline relation pass on spool; “Built with DINOv3” if distributed.  
6. **P2 — Disease / stand / soil probe topics** after P0 validation exists.  
7. **Later —** dock Phase 2, VR, spray.

---

## 6. Explicit non-goals (still)

- Phone arm / mode / mission  
- Spray as day-one product  
- Claiming field accuracy before local validation  
- Shipping RelateAnything on the aircraft computer  

---

*Sources consulted: Sentera 6X Thermal / FLIR program materials; SkyFlow & TerraSkyAI public scouting pages; Sairone / OAFRI fleabane work; UAV+AI reviews on water/nutrient stress and adoption gaps (2024–26 literature).*
