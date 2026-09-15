# Canadian smart agriculture: decision one-pager

**Date: 13 September 2026. Verify regulatory content before relying on this after 31 March 2027.**

---

## The situation

Two regulatory changes have made agricultural drones materially more practical in
Canada than they were two years ago:

- **4 November 2025** — CARs amendments (SOR/2025-70) created **Level 1 Complex**,
  a defined pathway for lower-risk BVLOS, and extended Advanced privileges to
  medium drones, EVLOS and sheltered operations.
- **30 June 2026** — Health Canada **SPN2026-02** permits drone application of any
  pesticide already registered for conventional aerial application, with no
  separate RPAS label amendment. Products not registered for aerial application
  remain off-limits.

One change is still pending: **NPA 2026-005** (published 8 June 2026, comments
closed 9 September 2026) proposes mandatory Remote ID, a community-organisation
framework, and a new regulator power to designate restricted drone airspace below
400 ft. Assume Remote ID is coming; design for retrofit.

## The recommendation

**Do not buy one drone that does everything. Buy the cheapest platform that can
answer the question, prove it changes a decision, then buy the thing that removes
the measured bottleneck.**

| Stage | Buy | Budget (year one) | Gate to pass before the next stage |
|---|---|---:|---|
| 1. Prove the agronomy | DJI Mavic 3 Multispectral + batteries + laptop | **C$10k–16k** | Two or three decisions measurably changed by the imagery |
| 2. Prove custom ML | Raspberry Pi 5 + AI HAT+ 26 TOPS + Pixhawk airframe | **C$4k–10k** | A model validated on *your* crops, not public datasets |
| 3. Remove the bottleneck | Whichever one the data says: MicaSense/thermal payload, Matrice 400, or VTOL | **C$30k–90k** | The bottleneck is measured, not assumed |
| 4. Area coverage | Trinity Pro or WingtraRAY VTOL | **C$40k–90k+** | Hectares per mission is the binding constraint |
| 5. BVLOS | Level 1 Complex certification + RPOC | **+C$10k–50k** | VLOS relocation and crew time is the binding constraint |
| 6. Spraying | Agras T50 class | **C$35k–65k** | Label, provincial certification and per-hectare economics all confirmed |

Stages 4, 5 and 6 are independent of each other. Most organisations never need all three.

## Does it pay? — illustrative break-even

*Assumptions are illustrative and must be replaced with your own crop, area and input costs.*

**Stage 1, 2,000 ha of broad-acre:** C$12,000 year-one capital amortised over three
years is C$4,000/yr. Flown five times per season, that is roughly **C$0.40 per
hectare-pass** before labour. A 2% nitrogen-rate improvement on a C$120/ha nitrogen
bill returns C$2.40/ha — about **C$4,800/yr on 2,000 ha**. One avoided blanket
fungicide pass on 500 ha at C$50/ha returns C$25,000. Stage 1 pays back inside a
season on plausible numbers; if it does not on yours, do not proceed to stage 3.

**Stage 6, custom spraying:** at roughly C$45/ha billed and C$15/ha operating cost,
the margin is C$30/ha. Against C$45,000 of year-one cost, break-even is about
**1,500 ha sprayed in year one.** A drone sprayer wins on wet or soft fields, small
or irregular parcels, steep ground, and late-canopy timing where a ground rig would
cause damage. It loses badly against a ground sprayer on open broad-acre throughput.
If your acres are flat, dry and large, do not buy one.

## Coverage, for sizing

| Platform | Area per flight | Use when |
|---|---|---|
| M3M at 100 m AGL | ~50–70 ha | Fields under a few hundred hectares, fine detail needed |
| M3M at 180 m AGL | up to ~200 ha | Coarse vigour mapping |
| Trinity Pro VTOL | ~700 ha, or a 100 km corridor | Broad-acre; the multirotor has become the bottleneck |

## Architecture in one line

**Edge first for flight-time decisions, workstation first for photogrammetry, cloud
for scale.** The Raspberry Pi is a companion computer that handles image QA,
detection and telemetry — it is never the flight controller, and the aircraft must
fly its safety logic correctly with the Pi rebooted and the network gone.

## The three rules that matter most

1. **A model is a sensor, not a decision.** Public datasets (DeepWeeds, PlantVillage)
   are for building the pipeline, not for making Canadian agronomic calls. Validate
   on local imagery, by crop and growth stage, before any output touches a sprayer.
2. **Keep a human agronomy gate between analytics and treatment.** A false positive
   is a wasted scouting trip; the same false positive wired to a sprayer is wasted
   chemical, crop damage or an environmental incident.
3. **Budget the operating cost, not just the capital.** Software renewal, insurance,
   battery replacement and RPOC upkeep are absent from most capital plans and are
   largest exactly where the capital is largest.

## What is still unspecified

Crop, average field size, province, connectivity, target ground-sampling distance,
and whether the commercial value is stress detection, stand counting, weed mapping,
water management, variable-rate prescription, documentation or spraying. Each of
these can move the recommended system by a full tier. **Settle the mission before
the airframe.**
