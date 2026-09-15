# Use-case roadmap — what this drone can solve, and what each costs

The ambition is right. One drone *can* serve many farm use cases — but only if it
is built as a **platform** rather than as a pile of features. That is what the
architecture already is, and this document maps what is nearly free, what is a
few days, and what is a separate product.

---

## The key insight: the platform is the product

The pipeline is **use-case agnostic**:

```
capture → QA → inference → indices → spool → provenance → upload
```

Nothing in it knows what a weed is. Swap the `.onnx` file and the same pipeline
detects disease, counts plants, finds livestock, or inspects fences. Add an I2C
sensor and its reading lands in every frame's provenance record automatically.

**So a new use case is usually a model file or a sensor — not a rebuild.** That is
why the architecture work matters more than any individual detector: it is what
makes "solve many problems" achievable for two people instead of fantasy.

The limit is not the software. It is **data, optics and regulation**, in that
order.

---

## Tier 0 — already working

| Use case | Status |
|---|---|
| Weed detection (binary, seedlings) | Model 1 trained, weed AP@.50 = 0.749 |
| Weed species ID (5 prairie species) | Model 2 in training |
| Crop vigour — NDVI, NDRE, GNDVI, SAVI, ExG | `geo/indices.py`, tested |
| Management-zone mapping | `management_zones()`, quantile-based |
| Air temperature, humidity, pressure | BME280 support, in every frame |
| Dew point, vapour pressure deficit | Derived, no extra hardware |
| **Spray-condition advisory** | VPD/temp/RH → ok / caution / poor |
| Image quality gating | Blur, exposure, GNSS, band completeness, tilt |
| Store-and-forward uplink | Metadata-first, priority-ordered |
| Full provenance on every frame | Telemetry, QA, model version, CRS |

---

## Tier 1 — days each, no architecture change

Each is **a trained model dropped into the existing pipeline.** The work is
finding or building a dataset, not writing code.

| Use case | What it needs | Honest difficulty |
|---|---|---|
| Crop stand counting / emergence | Detector + a counting pass | Easy — same as weeds |
| Plant disease from the air | An *aerial* disease dataset | Medium — most public sets are close-up leaves, which do not transfer |
| Pest / insect damage | Damage-pattern dataset | Medium — damage is easier to see than insects |
| Livestock counting & location | Detector, larger targets | **Easy** — cattle are huge compared to weeds, so optics are forgiving |
| Fence / irrigation / infrastructure inspection | Detector or just imagery review | Easy |
| Lodging (flattened crop) detection | Segmentation | Medium |
| Crop row / gap mapping | Classical CV, no ML needed | Easy |

**Add-on sensors, hours each:**

| Sensor | Why | Cost |
|---|---|---|
| Anemometer (wind speed/direction) | **Required on spray records** — the compliance checklist demands it and we still lack it | ~C$50–200 |
| PAR / incident light | Makes multispectral comparable across dates — currently the biggest weakness in index work | ~C$100 |
| Rangefinder / lidar altimeter | Terrain following; keeps GSD constant over slopes | ~C$50–150 |

---

## Tier 2 — weeks, new subsystem

| Use case | Reality |
|---|---|
| **3D mapping / photogrammetry** | Already solved by OpenDroneMap or Metashape. Runs on the **workstation, never the Pi**. Work is integration and flight planning, not algorithms. |
| **Thermal / canopy temperature** | Genuine irrigation-stress signal. Needs a radiometric thermal camera (C$3–8k). The best available proxy for crop water status. |
| Volume estimation (silage, stockpiles) | Falls out of photogrammetry once it exists |
| Variable-rate prescription maps | Indices + zones → GeoTIFF/shapefile the sprayer reads. Half-built already. |
| **Live video downlink** | For your emergency use case this beats VR — see below |
| Multi-date change detection | Needs the RTK/PPK discipline already designed for |

---

## Tier 3 — months, or a separate product

Be honest with yourselves about these. Each is a company's worth of work.

| Use case | Why it is hard |
|---|---|
| **Soil moisture** | See below — the ask is right, the method has to change |
| Autonomous docking / charging | Commercial docks (DJI Dock class) cost ~C$100k. Mechanically hard: precision landing, weather sealing, battery swap or contact charging. Your friend's domain, and a product in itself. |
| VR review environment | Technically a Three.js/WebXR viewer over a photogrammetry mesh. Weeks of work, and see the emergency note below. |
| Aerial spraying | Regulated. Needs an Agras-class airframe, medium-RPAS rules, provincial applicator certification. A different business. |
| Yield prediction | Needs multiple seasons of *your own* ground-truthed data. Cannot be shortcut. |
| Fully autonomous BVLOS operation | Level 1 Complex + RPOC. See the compliance checklist. |

---

## Two asks that need reframing

### "See if the soil is dry"

Right question, wrong instrument. **A camera on a drone cannot measure soil
moisture.** What it can see:

- **Thermal** — dry soil and water-stressed canopy run hotter. A *proxy*, and a
  decent one, but confounded by air temperature, wind, and time of day.
- **NDVI/NDRE** — show the crop's *response* to water stress, days after it starts.
- **Visible soil colour** — wet soil is darker. Confounded by soil type, residue
  and shadow.

None is volumetric water content.

**What actually works, and is buildable:** a small network of **in-ground LoRa
soil probes** (capacitive moisture + temperature, ~C$40–80 each) reporting to a
gateway. The drone flies the *spatial* pattern; the probes give *absolute truth*
at a few points; you calibrate one against the other.

That is a genuinely strong product — spatial coverage plus ground truth is better
than either alone, and it is the standard approach in commercial precision ag.
It also fits this architecture: probe readings are another sensor stream landing
in the same provenance record.

### "VR for emergencies"

Two different needs wearing one label:

- **Emergency, happening now** — you want *live video* with position, on a phone
  or laptop, in seconds. VR is slower to put on and adds nothing. Build the live
  downlink (Tier 2).
- **Reviewing the farm, later** — a 3D model in VR is genuinely nice: walking a
  field boundary, inspecting a roof, showing an agronomist. That is a viewer on
  top of photogrammetry, so it needs Tier 2 done first anyway.

Build the downlink first. VR is a presentation layer over work you have not done
yet.

---

## What I would actually sequence

For two people, with one writing all the code:

1. **Finish the weed species model.** Nearly done. It is a real product.
2. **Anemometer + PAR sensor.** Hours of work; one is a legal requirement for
   spraying, the other fixes the weakest part of the index pipeline.
3. **Fly your own fields and annotate.** Everything above is scaffolding until
   the model has seen your crops. This is also the only path to
   `validated_locally: true`.
4. **Add one Tier-1 detector** that a customer actually asks for. Livestock
   counting is the easiest win — big targets, forgiving optics.
5. **Then** photogrammetry, thermal, or the soil-probe network, depending on what
   customers pay for.

The trap is not ambition. It is building six half-features instead of one that
someone pays for — and then discovering the imagery never supported any of them.
Every tier above stays open because the platform does not care which model it is
running.
