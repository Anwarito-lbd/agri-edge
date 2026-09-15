# Procurement decision memo — Canadian agricultural RPAS programme

**Date: 13 September 2026 | Prices are indicative Canadian planning figures before
tax, not quotations. Enterprise systems are quote-based and move quickly.**

---

## 1. Decision being made

Whether, and in what order, to commit capital to an agricultural drone programme
when crop, field size, province and budget are not yet fixed.

**Recommendation: approve stage 1 and stage 2 only (C$14k–26k combined). Defer
stages 3–6 behind explicit gates.** The staged structure exists because the failure
mode in this sector is not buying the wrong drone — it is accumulating hardware
before proving that the information changes a management decision.

---

## 2. Approve now

### Stage 1 — Multispectral mapping starter — C$10,000–16,000

| Item | Qty | Planning allowance | Note |
|---|---:|---:|---|
| DJI Mavic 3 Multispectral | 1 | C$6,033–6,529 | Volatus C$6,033 (Basic 1 yr) / C$6,529 (Plus); DroneLabs C$6,245 |
| M3 Enterprise flight batteries | 4–6 | C$1,000–2,000 | Base package ships with minimal batteries; this is the throughput constraint |
| Rugged laptop, 32–64 GB RAM | 1 | C$2,000–4,500 | Mission planning **and** photogrammetry node |
| 2 TB rugged NVMe SSD | 2 | C$400–700 | Field copies; do not rely on microSD |
| RTK / NTRIP subscription or base | 1 | C$0–1,500 | Province-dependent; some networks are free |
| Pilot certification (Basic or Advanced) | 1–2 | C$500–1,500 | See §5 — the fee is not the cost |

**Why the M3M and not something cheaper:** it is the lowest-complexity path to
calibrated multispectral data. Assembling an equivalent RGB+4-band radiometric
payload yourself costs more in engineering time than the aircraft costs in cash.

**Why the M3M and not something better:** nothing more expensive answers the
stage-1 question — *does drone imagery produce actionable agronomic information on
our crops?* — any more definitively.

### Stage 2 — Raspberry Pi / Pixhawk research platform — C$4,000–10,000

| Item | Qty | Planning allowance | Note |
|---|---:|---:|---|
| Raspberry Pi 5, 8 GB | 2 | C$250–350 | Flight unit + bench spare |
| Raspberry Pi AI HAT+ **26 TOPS** | 2 | C$300–500 | **Not** the 40-TOPS HAT+ 2 — see §4 |
| Holybro Pixhawk 6X or Cube Orange+ | 1–2 | C$400–800 ea | Redundant IMUs, adequate serial ports |
| Custom 7-inch airframe, ESCs, motors, batteries | 1 | C$800–1,500 | Cheap to crash, which is the point |
| Pi Camera Module 3 + global-shutter camera | 2 | C$100–300 | Rolling shutter is unacceptable for fast row imagery |
| u-blox ZED-F9P rover/base | 2 | C$600–1,500 | Economical RTK for custom platforms |
| Telemetry, FPV goggles, controller, spares | — | C$800–2,000 | Separate pilot feed from the science camera |

**Why build at all when the M3M exists:** the M3M is a closed appliance. Stage 2
buys access to MAVLink, ROS, custom sensors and your own inference pipeline, at a
price where crashes are a line item rather than an incident.

---

## 3. Defer behind gates

| Stage | Spend | Gate that must be passed first |
|---|---:|---|
| Research sensor upgrade (MicaSense RedEdge-P ~C$10–15k; Altum-PT ~C$20–30k) | C$10k–30k | A specific analysis is demonstrably blocked by the M3M's 5 MP bands or its lack of thermal |
| Matrice 400 multisensor platform | C$20k–30k + payload | A payload has been chosen that the M3M cannot carry and that has a proven use |
| VTOL broad-acre (Trinity Pro / WingtraRAY) | C$40k–90k+ | Hectares-per-mission is the measured bottleneck — see §6 |
| Level 1 Complex BVLOS + RPOC | +C$10k–50k | Crew relocation and VLOS repositioning time is the measured bottleneck |
| Agras T50 spraying | C$35k–65k | Label eligibility, provincial applicator certification, **and** per-hectare economics all confirmed |

Note that these are **independent**, not sequential. VTOL, BVLOS and spraying solve
three different bottlenecks. Most programmes need at most one.

---

## 4. Three specification calls worth stating explicitly

**Buy the 26-TOPS AI HAT+, not the 40-TOPS AI HAT+ 2.** The HAT+ 2 (Hailo-10H,
8 GB, released January 2026) is the newer and more impressive part, but Raspberry
Pi's own materials state its computer-vision performance is roughly on par with the
26-TOPS predecessor — its advantage is local LLM and VLM work. Agricultural
detection and segmentation is conventional CV. Buy the cheaper part.

**Derate every published endurance figure before you plan missions.** The Matrice
400's "6 kg payload" and "59 min flight time" are mutually exclusive: DJI's own
figures are 59 min carrying only an H30T, 44 min at 3 kg and **31 min at 6 kg**.
Plan a loaded M400 at roughly half its headline endurance. The same caution applies
to the M3M's 43-minute class figure, which is not a mapping figure.

**Separate the pilot feed from the science camera on any FPV build.** A compressed,
wide-angle, low-latency pilot feed is for flying. Quantitative measurement needs a
dedicated nadir camera. Deriving agronomy from the FPV stream introduces radiometric
and geometric error for no saving.

---

## 5. Costs the capital plan will miss

Every one of these is absent from a naive hardware budget and several are largest
exactly where the hardware is most expensive.

| Recurring item | Why it bites |
|---|---|
| **Software renewal** | The M3M bundle includes only 3 months of DJI Terra and 1 year of SmartFarm. Year two is a fresh line. Pix4Dfields is a subscription. |
| **Insurance** | Commercial RPAS liability is effectively required at RPOC scale and is frequently demanded by landowners and clients. |
| **Batteries as consumables** | Finite cycle life. On an Agras operation, replacement packs are plausibly a fifth of annual cost, yet they appear once, as capital. |
| **Certification, properly costed** | The Level 1 Complex *fees* are C$50.85 (exam) + C$125 (issuance) + about C$10 (prerequisite Advanced exam). The *costs* are the mandatory 20 h ground school and the flight review, which are purchased services. Budget four figures per pilot. |
| **RPOC upkeep** | Maintenance programme, document control, SOPs, recurrent training every two years, accountable-executive time. |
| **Connectivity** | LTE only where coverage justifies it; otherwise store-and-forward. |

---

## 6. The VTOL crossover, quantified

The tier structure rests on area efficiency, so here is the arithmetic the decision
actually turns on:

| Platform | Area per flight | Implied fit |
|---|---|---|
| M3M at 100 m AGL | ~50–70 ha | Under a few hundred hectares per survey |
| M3M at 180 m AGL | up to ~200 ha | Coarse vigour only |
| Trinity Pro | ~700 ha, or a 100 km corridor | Broad-acre |

**Crossover test:** count the battery swaps and relocations per survey at your
required GSD. When a single survey stops fitting in one field visit, the
multirotor has become the bottleneck and stage 4 is justified. Until then it is not,
regardless of how attractive the endurance figure looks.

---

## 7. Spraying — when it wins and when it does not

Health Canada's SPN2026-02 (30 June 2026) removed the label barrier, which improves
the commercial case but does not make the economics automatic.

- **Break-even:** roughly C$45/ha billed less roughly C$15/ha operating gives about
  C$30/ha margin. Against C$45,000 year-one cost, that is about **1,500 ha in year one.**
- **Wins on:** wet or soft ground, small and irregular parcels, steep or terraced
  sites, late-canopy timing where a ground rig causes damage, and spot treatment.
- **Loses on:** open, dry, large broad-acre, where a ground sprayer's throughput is
  not close.
- **Regulatory weight:** a T50 exceeds 25 kg in operational configuration, placing it
  in the **medium-RPAS** regime. A simple small-drone Basic operation is not a valid
  planning assumption.

Buy an integrated agricultural spray system. Do not build the liquid-dispensing
subsystem around a Raspberry Pi — pump calibration, flow sensing, droplet size,
downwash interaction, chemical compatibility and fail-safe shutoff are all
safety-critical and all regulated.

---

## 8. Canadian supply channel

Volatus Drones Canada, DroneLabs, DroneDynamics, Drone Spray Canada, DronePoint,
SkyFlow, Measur Canada, Hoskin Scientific (rental), Cansel, Dronexperts.

Get **three written quotes** for anything above C$10,000, and confirm what is
actually in the box — battery count, RTK module, software term and training are
where package prices diverge most.

---

## 9. Decision requested

1. **Approve** stage 1 + stage 2: **C$14,000–26,000**.
2. **Defer** stages 3–6 pending the gates in §3.
3. **Assign** an owner for the regulatory file, with a review before 31 March 2027
   — NPA 2026-005 is expected to produce a final Remote ID rule and a new
   designated-airspace power.
4. **Resolve** crop, field size, province and target GSD before releasing stage 3
   funds. Each can move the answer by a full tier.
