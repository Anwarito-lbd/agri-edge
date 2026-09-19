# Product vision — agri-edge

**One-liner:** Canadian RPAS companion-computer scouting — edge AI, geo maps, alerts. Pilot/FC flies; phone never arms. Not a spray robot on day one.

**Platform rule:** A new capability is usually a **model file or sensor**, not a rewrite. Sheep/weeds prove the pipe; thermal/MS/relations plug in next.

See also: [NICHE_GAP_ANALYSIS.md](NICHE_GAP_ANALYSIS.md), [RELATE_ANYTHING.md](RELATE_ANYTHING.md), [PHONE_PI_CONTRACT.md](PHONE_PI_CONTRACT.md), [DOCK_INTERFACE.md](DOCK_INTERFACE.md).

---

## Now (ship / demo)

| Capability | Notes |
|------------|--------|
| Edge RGB detect (YOLOX) | Livestock + weeds — validate on own fields |
| Green-on-brown (ExG) | Fallow / vegetation without NPU |
| Georef + QA + geofence + wind advisory | Safety contracts |
| Website + proof + dashboard map | Live |
| Companion `/app` mock Pi | Alerts/status only |
| Mechanic Phase 1 pack | STLs / renders |

## Next (design + build without claiming live hardware)

| Capability | Blocker |
|------------|---------|
| **Thermal / water-stress layer** | Thermal camera payload; Demo UI first |
| **Multispectral NDVI/NDRE** | MS camera; index pipeline |
| Live phone ↔ real Pi | Bookworm + gateway |
| Disease / nutrient heads | Datasets + local labels |
| **RelateAnything relations** | Laptop only; DINOv3 licence |
| Charging dock handshake | Friend Phase 2 + DOCK_INTERFACE |

## Later

| Capability | Notes |
|------------|--------|
| Soil moisture probe fusion | Ground IoT topic |
| Stand count / emergence | RGB counting |
| Spot-spray closed loop | Regs + validation first |
| VR situational view | After live downlink |
| Hailo HEF speed | AI HAT+ |

## Demo vs Hardware-blocked

- **Demo OK:** mock thermal/stress tiles, mock MS indices, mock relation insights — labelled Demo.  
- **Hardware-blocked:** real °C maps, true NDVI, `validated_locally: true`, live LTE alerts.
