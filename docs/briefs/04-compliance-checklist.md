# Canadian agricultural RPAS compliance checklist

**Current to 13 September 2026. Re-verify before 31 March 2027** — three material
changes landed in the preceding twelve months and a fourth is pending.

This is an operational checklist derived from published Transport Canada and Health
Canada material. It is not legal advice, and it does not replace reading the
applicable regulation, the product label, or your provincial requirements.

---

## A. Before the first flight — aircraft and pilot

- [ ] **Register the aircraft** with Transport Canada (required at 250 g and above)
      and mark the registration number on it.
- [ ] **Hold the right pilot certificate** for the intended operation (see §B).
- [ ] **Microdrones under 250 g** need no registration or certificate — but airspace
      restrictions, Class F restricted airspace and NOTAMs still apply, and the pilot
      is still responsible for safe and lawful operation.
- [ ] **Commercial liability insurance** in place, and confirm whether landowners or
      clients impose their own minimum.
- [ ] **Reserve physical space, power and a serial port for a Remote ID module** on
      any custom build. See §F.

## B. Choose the correct operating category

| Intended operation | Pathway |
|---|---|
| VLOS, 250 g–25 kg, uncontrolled airspace, meeting all Basic conditions | **Basic** |
| Controlled airspace; near or over people where permitted; EVLOS; VLOS with a medium 25–150 kg aircraft | **Advanced** |
| EVLOS with a small RPAS, uncontrolled airspace, qualified visual observer | **Advanced** (observer needs at least the Basic qualification) |
| Lower-risk BVLOS in qualifying rural/uncontrolled areas | **Level 1 Complex** + RPOC |
| Anything outside the above | **SFOC-RPAS** or other applicable approval |

- [ ] **Controlled airspace?** Obtain NAV CANADA authorisation through **NAV Drone**,
      or DND authorisation as applicable. Allow lead time.
- [ ] **An Agras T50 exceeds 25 kg operationally** — it is a **medium RPAS**. Do not
      plan it as a small-drone Basic operation.
- [ ] **FPV goggles are not a substitute for visual observation of the aircraft.**
      Design the operation around the applicable VLOS/EVLOS/BVLOS rule set.

## C. Level 1 Complex BVLOS — the full burden

Only pursue this once VLOS economics are proven.

**Pilot:**
- [ ] At least 18 years old
- [ ] Pass the **Advanced operations exam** (prerequisite, about C$10)
- [ ] Complete **at least 20 hours of ground school** (purchased course)
- [ ] Pass the **Level 1 Complex exam** — **C$50.85** per attempt
- [ ] Complete the **flight review** (charged by the reviewer, not Transport Canada)
- [ ] Pay the **C$125 certificate issuance fee**
- [ ] Certificate does not expire, but complete **one TC-recognised renewal activity
      every two years**

> Budget four figures per pilot. The ground school and flight review dominate; the
> C$176 of government fees is the small part.

**Organisation — RPAS Operator Certificate (RPOC):**
- [ ] Named accountable executive
- [ ] Documented SOPs proportionate to operational complexity
- [ ] Training programme
- [ ] Maintenance programme and records
- [ ] Operational risk assessment process

**Operational limits for Level 1 Complex:**
- [ ] Uncontrolled airspace only
- [ ] Normally at or below **122 m / 400 ft AGL**
- [ ] Small or medium RPAS: qualifying unpopulated areas **more than 1 km from a
      populated area**
- [ ] Qualifying small aircraft with an accepted pre-validated declaration may
      operate over **sparsely populated** areas
- [ ] Maintain the specified separation from relevant aerodrome centres
- [ ] Aircraft declaration / pre-validated declaration in place as required

> Treat this as an aviation programme, not an extension of recreational flying.

## D. Spraying — Health Canada SPN2026-02 (30 June 2026)

**Eligibility of the product — check all three:**
- [ ] The product is **already registered for conventional aerial application**
- [ ] The label does **not** say "do not apply by air"
- [ ] The label does **not** explicitly prohibit RPAS use

> If any of these fails, it cannot be applied by drone under this policy. No separate
> RPAS label amendment is needed when all three pass.

**Follow the aerial label:**
- [ ] Application rate
- [ ] Spray volume
- [ ] Retreatment interval
- [ ] **Buffer zones — specifically those established for conventionally piloted
      _rotary_ aircraft.** This is the binding figure, applied as an interim
      precaution until RPAS-specific spray drift models exist. Where a label gives
      separate fixed-wing and rotary buffers, **the rotary buffer applies.**
- [ ] All other label conditions

**Crew and worker protection:**
- [ ] The person **mixing** the pesticide is **not** simultaneously the pilot, except
      for the limited loading situations the label allows
- [ ] Minimum PPE worn, plus any product-specific requirements
- [ ] Mixing/loading and maintenance treated as key exposure activities
- [ ] **No crew positioned downwind of the spraying aircraft**

**Other authorities:**
- [ ] Provincial/territorial **pesticide applicator certification** held
- [ ] Provincial/territorial permits obtained
- [ ] Transport Canada obligations satisfied **independently** — SPN2026-02 changes
      pesticide policy, not aviation rules

**Equipment:**
- [ ] Spray system correctly calibrated for a uniform pattern across the treated area
- [ ] Nozzle/atomiser calibration recorded
- [ ] Tank volume and flow reconciled against area treated

## E. Every flight — operational record

- [ ] Site survey and airspace check (NAV Drone)
- [ ] NOTAMs and Class F restricted airspace checked
- [ ] Weather recorded: **wind speed and direction, temperature, humidity**
- [ ] Weather limits applied for **both airframe and measurement quality** — wind
      within airframe limits can still ruin photogrammetry through attitude change
      and motion blur; changing cloud cover invalidates multispectral comparison
      across dates; thermal shifts with time of day, wind and soil moisture
- [ ] Geofence, lost-link, battery and navigation failsafes configured **on the
      autopilot**, independent of any companion computer
- [ ] Watercourses and sensitive habitats geofenced; label buffers loaded as
      exclusion zones
- [ ] Flight logs, battery cycles, firmware configuration and maintenance records
      retained
- [ ] Application log tied to the GPS track (spray operations)

## F. Pending — NPA 2026-005

Published **8 June 2026**; the comment period **closed 9 September 2026**. Not
current law, but the next step is a final rule.

- [ ] **Remote ID** proposed as mandatory for most operations, scaled by aircraft
      weight, **including FPV and model aircraft**. Legacy and home-built aircraft
      would comply via a retrofitted broadcast module.
- [ ] **Community-Based Organizations** with permanent flying sites would be exempt.
- [ ] **Designated RPAS airspace** — a proposed regulator power to restrict drone
      operations **below 122 m / 400 ft**. This is the element with the most direct
      agricultural exposure, since it covers the altitude band all agricultural
      missions occupy. Assess whether your operating areas are plausible candidates.
- [ ] Action now: assume Remote ID is coming, budget the retrofit, and do not design
      an airframe that cannot accept a module.

## G. Privacy and data

- [ ] Camera pointed at the field — not neighbouring homes or roads
- [ ] Identifiable imagery not retained beyond agronomic need
- [ ] People and number plates blurred in any externally shared imagery
- [ ] Documented retention period
- [ ] Employee and contractor access limited
- [ ] Recurrent operations disclosed to neighbouring landowners where appropriate
- [ ] Federal and applicable provincial private-sector privacy obligations assessed
      for your organisation — agricultural land is not automatically outside privacy law

**Contracts with analytics, agronomy and drone-service providers must state:**
- [ ] Ownership of raw imagery, derived maps, field boundaries, yield data, and
      trained models
- [ ] Whether your data may be pooled for the vendor's model training
- [ ] Where copies are stored
- [ ] Deletion rights and breach notification
- [ ] Export and portability — retain your own copy in **GeoTIFF/COG, GeoJSON/
      GeoPackage and CSV**, not only in a proprietary dashboard

## H. Cybersecurity for Raspberry Pi and custom systems

- [ ] Unique per-device credentials
- [ ] Password SSH disabled; key-based authentication only
- [ ] Encrypted transport
- [ ] Mission and model files signed or checksummed
- [ ] Payload and safety-critical networks separated where feasible
- [ ] Read-only or immutable system images on production aircraft
- [ ] Flight controller never exposed directly to the public internet
- [ ] LTE access terminated through a VPN or authenticated service — **never open
      MAVLink ports globally**

## I. The analytics gate

- [ ] Models validated against field observations **by crop, growth stage, location,
      season, camera altitude and lighting** before being allowed to generate
      treatment prescriptions
- [ ] A model trained on public data (DeepWeeds is Australian species; PlantVillage
      is single leaves on plain backgrounds) is **not** evidence of performance on
      Canadian field imagery
- [ ] **Human agronomist approval between analytics and any treatment.** A
      false-positive weed map is a wasted scouting trip; the same false positive
      wired to a sprayer is wasted chemical, crop damage or an environmental incident
- [ ] Object detection is never the sole collision-avoidance mechanism
- [ ] A Raspberry Pi is never the only path to return-to-home, attitude control or
      flight termination

---

## Sources

- [2025 summary of changes to Canada's drone regulations — Transport Canada](https://tc.canada.ca/en/aviation/drone-safety/2025-summary-changes-canada-drone-regulations)
- [Getting a drone pilot certificate — Transport Canada](https://tc.canada.ca/en/aviation/drone-safety/drone-pilot-licensing/getting-drone-pilot-certificate)
- [Summary of NPA 2026-005 information sessions — Transport Canada](https://tc.canada.ca/en/aviation/drone-safety/summary-notice-proposed-amendment-npa-2026-005-information-sessions)
- [SPN2026-02, Allowing pesticide application by RPAS — Health Canada](https://www.canada.ca/en/health-canada/services/consumer-product-safety/reports-publications/pesticides-pest-management/policies-guidelines/science-policy-notes/2026/allowing-pesticide-application-remotely-piloted-aircraft-systems-rpas-drones-products-registered-aerial.html)
- [Navigating Canada's new legal landscape for drones — Miller Thomson](https://www.millerthomson.com/en/insights/transportation-and-logistics/navigating-canadas-new-legal-landscape-drones/)
- [Transport Canada proposes Remote ID, CBOs and designated RPAS airspace — MLT Aikins](https://www.mltaikins.com/insights/transport-canada-proposes-rpas-airspace-regulations/)
