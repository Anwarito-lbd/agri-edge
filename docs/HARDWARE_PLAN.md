# Hardware plan

Written 16 Sept 2026. Every software gap this project had is now closed, and
**everything remaining is blocked on hardware that does not exist yet.**

This is ordered by what each purchase *unblocks*, not by what is exciting. A
surprising amount of the code is written and waiting on a specific part.

> **The question that was never answered.** In the first session the hardware
> answer was "Nothing yet" *and* "Pi 5 + Pi Camera + AI HAT+" simultaneously.
> Everything below assumes **nothing exists**. If some of it is already on a
> shelf, skip those rows — but say which, because it changes the order.

---

## Stage 0 — DONE, 20 September 2026

Free, and it unblocked four things that had been stuck since the first session.

| Item | Why | Cost |
|---|---|---|
| **WSL2 + Ubuntu 22.04** | ✅ **installed** — Ubuntu 22.04.5, x86_64, **Python 3.10.12** (exactly what the Hailo Dataflow Compiler wants), 20 cores, 955 GB free. Toolchain in: gcc, g++, make, cmake, pip, plus ArduPilot's SITL prerequisites. | free |
| **Docker Desktop** | ⏳ still absent. WebODM and farmOS both run as containers; their clients are written and tested against stubs and neither has met a real server. | free |
| **Fix the GPU power mode** | ⏳ Windows → Best performance, NitroSense → Performance, NVIDIA panel → Prefer maximum performance. Retraining is ~18× slower without it. | free |

**What installing it actually found.** Both shell scripts in `scripts/` were
unrunnable on Linux — `core.autocrlf=true` had rewritten them to CRLF, so bash
read `set -euo pipefail` as `pipefail<CR>`. They had never been executed on
Linux because there had never been a Linux to execute them on. `.gitattributes`
now pins LF and two tests assert it.

**Verified since:** `scripts/hailo_compile.sh --dry-run` passes preflight for
all three targets (`hailo8l`, `hailo8`, `hailo10h`) inside WSL, against the
exported `imageweeds_yolox_s.onnx` and 391 calibration images.

**The one step left on the Hailo path** is the Dataflow Compiler wheel itself.
It is not on PyPI — it sits behind a free account at
<https://hailo.ai/developer-zone/>, and downloading it needs a sign-in. Then:

```bash
python3 -m venv ~/hailo-venv
~/hailo-venv/bin/pip install hailo_dataflow_compiler-*.whl
~/hailo-venv/bin/pip install -e vendor/hailo_model_zoo
source ~/hailo-venv/bin/activate
bash scripts/hailo_compile.sh --arch hailo8     --model models/imageweeds_yolox_s.onnx     --calib data/imageweeds/train/images --classes 5
```

---

## Stage 1 — The minimum that produces real imagery (~C$400)

This is the smallest purchase that turns the project from scaffolding into
something that has seen a real field. **It does not need an aircraft.** Carry the
camera along a field edge on a pole and you have local imagery to annotate, which
is the single highest-value thing missing.

| Item | Spec | Approx. | Unblocks |
|---|---|---:|---|
| Raspberry Pi 5, 8 GB | not 4 GB — tiling and ONNX want headroom | C$130 | `scripts/pi_setup.sh` |
| Active Cooler | the Pi 5 throttles without it, silently | C$10 | sustained inference |
| 27 W USB-C PSU | official; undervolting corrupts SD cards | C$20 | |
| microSD 128 GB A2 | or better, an NVMe HAT + SSD | C$30 | spool quota assumes ~64 GB free |
| **Camera Module 3** | IMX708, the sensor `geo/georeference.py` defaults to | C$45 | `Picamera2Camera`, **channel-order check** |
| Camera ribbon, 300–500 mm | the Pi 5 uses the *narrow* connector — check this | C$10 | |
| **Reflectance panel** | a calibrated grey target with a certificate | C$100–150 | `geo/calibration.py` — every index is `calibrated=False` until this exists |

**First jobs, in order:**

1. `bash scripts/pi_setup.sh`
2. **Verify camera channel order.** `Picamera2Camera.verify_channel_order()`.
   Picamera2's "RGB888" delivers BGR. We swap by default and it has never been
   confirmed on hardware. Half the vegetation indices are R/B-symmetric and half
   are not, so a mix-up would *half* work — the worst kind of bug.
3. Shoot the reflectance panel, run `compute_gains`, and get the first
   `calibrated=True` index this project has ever produced.
4. Walk a field with the camera on a pole. **Annotate what comes back.** This is
   the only path to `validated_locally: true`.

---

## Stage 2 — Makes the weed mission flyable (~C$150)

| Item | Approx. | Unblocks |
|---|---:|---|
| **AI HAT+ 26 TOPS** (Hailo-8) | C$150 | `HailoEngine`, tiled inference at survey altitude |

Not the 13-TOPS `hailo8l` and not the 40-TOPS AI HAT+ 2 — the 26 is the right
point. The newer board's advantage is local LLM work this pipeline does not do.

**Why it is a requirement, not an upgrade:** tiling a 4056 px frame is 48
inferences. On the Pi's CPU that is seconds per frame, which caps ground speed
around 1.5 m/s — not a survey flight. On the Hailo it is ~288 ms.

**Livestock is the exception.** A cow is detectable at 41 m whole-frame, so
`aerial_sheep_yolox_s` (AP@.50 **0.905**) runs usefully on a bare Pi with no
accelerator at all. If money is tight, *that* is the demo to build first.

Then: `bash scripts/hailo_compile.sh --arch hailo8` **in WSL2**, test the `.hef`
standalone through `vendor/hailo-rpi5-examples` **before** switching config to
`backend: hailo`, and finally
`python training/benchmark.py --backend hailo --tiled --capture-width 4056` —
the number that actually sets flight parameters.

---

## Stage 3 — The aircraft (~C$1,200–2,500)

Your friend's domain; the airframe brief in
[progress-report-and-airframe-brief.html](progress-report-and-airframe-brief.html)
covers the mechanical side in twelve numbered items. What the *software* needs
from it:

| Item | Approx. | Unblocks |
|---|---:|---|
| Pixhawk-class flight controller (6C or Cube) | C$250–600 | real `MavlinkTelemetry`, `--sitl` becomes a real flight |
| Airframe, motors, ESCs, props | C$400–900 | |
| Batteries + charger | C$250–500 | |
| RC transmitter/receiver | C$200–400 | |
| Telemetry radio | C$60–120 | |
| **Downward rangefinder / lidar altimeter** | C$60–150 | **AGL altitude.** Until this exists, `alt_rel_m` is height above *home*, and on a slope every georeferenced position is systematically wrong |

**Keep the aircraft under 25 kg.** Above it is Transport Canada's medium-drone
class and a different regulatory project entirely.

---

## Stage 4 — Centimetre positioning (~C$600–1,600)

| Item | Approx. | Unblocks |
|---|---:|---|
| RTK GNSS rover + base, or an NTRIP subscription | C$600–1,600 | `qa.require_rtk_fixed`, `telemetry/ntrip.py` |

`require_rtk_fixed` exists, is tested, and **cannot pass today** because nothing
delivers corrections. `telemetry/ntrip.py` is written and waiting.

Corrections go to the **GNSS receiver's own serial input**, not through the
flight controller — the MAVLink link stays read-only by construction. Wire the
receiver accordingly.

A public NTRIP network (where one covers the field) is far cheaper than a base
station and removes a box from the truck. Check coverage before buying a base.

---

## Stage 5 — Compliance and calibration (~C$150–350)

| Item | Approx. | Unblocks |
|---|---:|---|
| **Anemometer + wind vane on a field-edge mast** | C$50–200 | `spray_advisory()` |
| PAR / incident light sensor | C$100 | cross-date index comparison without panels |

The spray advisory now **refuses to give a verdict without wind** — correctly,
since wind dominates drift and Canadian spray records require speed and
direction. A handheld meter works to start; the mast is airframe brief item 08.

**It must be on the ground.** An anemometer bolted to the aircraft measures its
own downwash. The code rejects `wind_source: airframe` outright.

---

## Money, staged

| Stage | Cost | What you get |
|---|---:|---|
| 0 | free | SITL, Hailo compiler, WebODM, farmOS, fast retraining |
| 1 | ~C$400 | **Real local imagery to annotate.** The thing that matters most. |
| 2 | ~C$150 | The weed mission becomes flyable |
| 3 | C$1,200–2,500 | An aircraft |
| 4 | C$600–1,600 | Centimetre positioning, cross-date comparison |
| 5 | C$150–350 | Legal spray records |
| **Total** | **~C$2,500–5,000** | |

For contrast, the 120 kg spray platform in `deep-research-report (8).md` budgets
**US$75,000** for one prototype and US$1.2–3.5M for a real programme. Staying
under 25 kg is what makes this affordable by two people.

---

## The honest summary

**Stage 0 costs nothing and unblocks four things. Do it this week.**

**Stage 1 is the one that matters.** Every model in this repo is trained on other
people's fields, in one season, and in two cases the dataset was not what its
name claimed. `validated_locally` is false everywhere and cannot become true
without local imagery. A C$400 camera on a pole gets you that *without an
aircraft*, and until it exists everything else is scaffolding.

Nothing on this list makes a detection permitted to drive a treatment. That needs
local validation **and** a defined treatment boundary, and it fails closed
without both — deliberately.
