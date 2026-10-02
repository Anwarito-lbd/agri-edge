# Water-only bench test plan — Phase 1 airframe

**Status: BLOCKED-HARDWARE.** Nothing in this plan has been executed. There is no pump, nozzle,
relay or stand in this repository's possession, no data, and no result. This document is a
procedure and a template, nothing more. It moves to **BENCH** only when the tests below have been
run on real hardware and the filled-in data sheets are attached to the repo (see §10). It never moves to VALIDATED, and says nothing about field performance.

**Applies to:** the friend's Phase 1 airframe (`mechanical/handoff/MECHANIC_ASSIGNMENT.md`),
as a **stand-mounted rig**. **Prepared:** 2026-10-02. **Owner / approver:** Anwar + the mechanic
(names and sign-off in §10).

> **Scope reconciliation (read first).** Today's handoff packet says Phase 1 is *scouting, not
> spray* and lists "Spray hardware" as out of scope (`MECHANIC_ASSIGNMENT.md`;
> `FRIEND_PRESENTATION.md` §5 "Spray / treatment payload on day one"). This plan does **not**
> change that. It is an optional **bench rig** to learn about water dosing hardware (pump,
> nozzle, relay, latency) with nothing flying. Running it needs Anwar's and the mechanic's
> explicit agreement; the Phase 1 scouting build is unaffected whether or not it is run.

---

## 1. Objectives

| ID | Objective | Output |
|----|-----------|--------|
| O1 | Measure the **flow rate** of the chosen pump + nozzle on water, and how repeatable it is | L/min mean, SD, CV per setting |
| O2 | Measure **command → response latency** of a bench relay driving the pump (electrical and hydraulic) | ms: min / median / p95 / max |
| O3 | Confirm the actuator path **fails safe**: default-off at boot, off on control-link loss, off on E-stop | pass/fail per check |
| O4 | Confirm containment: **no leaks**, no water reaching electronics | pass/fail |
| O5 | Produce numbers the software can use: the placement error a latency implies (§6.4) | table |

**Non-objectives:** no flight, no hover, no thrust test, no spray-pattern/drift/droplet-size
claims, no chemical or dyed/additive liquid, no AI or camera in the loop, no Transport Canada
compliance finding.

## 2. Ground rules (hard)

1. **Water only.** Clean tap water. No chemicals, no fertiliser, no surfactant, no dye or additive of any kind.
2. **No flight.** The airframe is clamped to a stand, **propellers physically removed** (not just "disarmed"), flight battery **disconnected**; the FC may be powered from USB/bench supply only if the test needs it, and motor outputs stay unconnected.
3. **No AI in the loop.** No camera, model, detection, georeference or `TreatmentDecisionEngine` output is connected to anything on this bench. Commands come from a fixed, human-started test script (§6). Detections cannot start a pump.
4. **Separate from the engine on purpose.** `TreatmentDecisionEngine` refuses any actuator that is not `simulated=True`, and that refusal stays. The bench relay is a standalone harness, never passed to the engine (§6.1).
5. **Hardware E-stop wins.** The pump's power path goes through a physical E-stop and key switch that no software can bypass.
6. **Companion MAVLink stays read-only.** Nothing on the bench writes to the flight controller.
7. **Two people:** one runs the test, one stands by the E-stop and watches the water. Nobody tests alone.

## 3. Safety

| Hazard | Control (must be in place **before** any pump runs) |
|--------|---------------------------------------------------|
| Spinning props | Props **removed** and stored away from the bench; motor power leads unplugged from ESCs or flight battery disconnected. Photograph the bare motors before starting. |
| Electric shock (water + mains) | Any mains-powered item (bench supply, scale, charger, laptop) on a **GFCI-protected** outlet (tested with its TEST button at the start of every session). Pump on **low-voltage DC only** (≤ 24 V, rated by the pump's datasheet, **TBD** until the part is chosen). |
| Water on electronics | Pi / FC / relay board / battery on the **opposite side** of the airframe from nozzle and tank, above the tray's rim; relay in a closed enclosure; drip loops on every cable; tank, hoses and nozzle sit **inside a containment tray** sized ≥ 110 % of the total water volume on the rig. |
| Battery fire | No LiPo connected to the pump circuit; pump fed from a **current-limited bench supply** (limit set to ~120 % of pump rated current, **TBD**) with an inline fuse. Any LiPo present is disconnected and stored in a charging bag. |
| Relay / inductive kick | Flyback diode across the pump; relay contacts rated ≥ 2× pump stall current (**TBD**). |
| Pressure / hose burst | Hose, fittings and clamps rated above pump max pressure (**TBD from datasheet**); fit a pressure relief or never dead-head the pump; first run with the nozzle removed and the outlet pointed into the tray. |
| Spray into eyes | Safety glasses; nobody stands in front of the nozzle; spray aimed into the tray only, with a splash guard behind it. |
| Slips | Mop and towels at hand; wipe the floor between runs; no extension-cord loops across the floor. |
| Runaway pump | Hardware E-stop (normally-closed in series with pump supply), software watchdog (§6.3), manual shut-off valve on the tank outlet. |

**Stop conditions (abort immediately and use the E-stop):** any leak reaching a connector or board, smell/smoke/heat from any electronics, GFCI trips, unexplained pump run, anyone out of position, anything not in this plan.

## 4. Equipment (to be named by the mechanic; all **TBD**)

Pump (model, voltage, rated flow/pressure) · nozzle (model, rated flow at rated pressure) · tank (≤ the volume the tray can contain) · hoses, clamps, shut-off valve · flow meter (optional; pulse-output) · pressure gauge or sensor (optional) · precision scale (±1 g or better) or a graduated cylinder with ±1 mL graduations · stopwatch / timestamped log · bench supply with current limit, fuse, **physical E-stop + key switch** · relay or MOSFET module + enclosure + flyback diode · bench controller (a Pi GPIO or microcontroller, **not** the flight controller) · oscilloscope or logic analyser (≥ 1 MS/s, 2 channels) for §6.2 · camera ≥ 120 fps with a visible LED for the optional hydraulic-onset method · containment tray, splash guard, spill kit, safety glasses · GFCI outlet/adapter and a tester · multimeter.

## 5. Flow-rate check (pump + nozzle) — O1

**Method (gravimetric):** water mass ÷ time. 1 g of tap water ≈ 1 mL (note water temperature on the sheet; ignore the < 1 % density effect, and say so).

1. Fill the tank to a marked level; record tank level and head height (tank water surface to nozzle, cm).
2. Place a collection container on the scale **inside the tray**; tare.
3. Set supply voltage to setting S (see below). Run the pump **into the container** for a fixed T = 30 s using the bench script (§6) or a manual switch; stop with the relay, not the E-stop.
4. Read the mass; compute Q = mass_g / T_s × 0.06 (L/min). Empty and re-tare between repeats.
5. **N = 5 repeats per setting.** Settings S: rated supply voltage; −10 % ; −20 % (battery sag representation). **No setting above the pump's rated voltage.**
6. Record pressure and flow-meter readings if fitted.
7. **Leak check:** dry paper towel under every joint; run at the highest setting for 10 minutes; inspect.
8. **Repeat 3–7 with the nozzle fitted**, then once with no nozzle (open hose) for the pump's own free flow.

**Reference arithmetic the software already uses** (`geo/geofence.py: spray_flow_l_min`): Q = R × v × W × 0.006, with R in L/ha, v in m/s, W in m. Worked example from the research report: 20 L/ha at 8 m/s with an 8 m swath → 7.68 L/min. The bench measures what the hardware *actually* delivers; the formula only says what rate would be needed. A real controller would close the loop on a flow meter and must never infer application from pump PWM.

**Pass/fail (proposals — Anwar + mechanic must confirm or replace them before the first run, and write the final values on the sheet):**

| Check | Pass |
|-------|------|
| Mean Q at rated voltage vs. the nozzle's datasheet rate at the measured pressure | within ±10 % (**datasheet value TBD**) |
| Repeatability, CV = SD / mean over N = 5 | ≤ 5 % |
| Flow vs. supply voltage | monotonic and recorded; any non-monotonic result is a FAIL to investigate |
| Leaks | none visible at any joint over 10 min; towels dry |
| Water on any electronics | none |

## 6. Command-response latency — O2, O3

### 6.1 Harness (clearly separate from the AI path)

```
  fixed test script  ──►  bench controller GPIO  ──►  relay/MOSFET  ──►  pump (low-voltage DC, via E-stop + key switch)
  (human-started)           (NOT the flight controller)                      │
        │                                                                    └─► nozzle ─► tray
        └──► log: monotonic timestamp of every command + scope/camera trigger
```

* The bench relay driver exposes the **same shape** as the simulation's actuator port — `health()` and `execute(record)` — so the timing code can be reused, but it is **its own class in the bench script**, never imported into `agri_edge.decision` and **never given to `TreatmentDecisionEngine`**, which would refuse it (`simulated` must be `True`). Do not weaken that refusal for the bench.
* Inputs to the script: a command list (ON/OFF, durations). **No detections, no camera, no model output** can reach it.
* Default state is **OFF**: relay normally-open, GPIO initialised low, pull-down fitted.
* The script has a **watchdog**: if it stops sending its heartbeat tick for > W ms (W = 200 ms proposed, **TBD**), the driver de-energises the relay.

### 6.2 Latency measurements

| Metric | Definition | Instrument |
|--------|-----------|------------|
| L1 electrical-on | script's command timestamp → pump terminal voltage reaches 90 % of supply | scope: ch1 = GPIO line (trigger), ch2 = pump terminals |
| L2 electrical-off | OFF command → pump terminal voltage falls to 10 % | scope, same wiring |
| L3 hydraulic-on (optional) | command → first water leaves the nozzle | ≥ 120 fps camera with an LED driven by the same GPIO in view; count frames |
| L4 hydraulic-off (optional) | OFF command → flow stops (last continuous stream; note dribble separately) | same camera |
| L5 watchdog | stop sending ticks → pump terminal voltage < 10 % | scope |

Procedure: pump running into the tray; **N = 30** ON commands and **30** OFF commands with random 1–3 s gaps (seeded, recorded). Report min / median / p95 / max for each metric. Camera frame period (e.g. 8.3 ms at 120 fps) is the resolution of L3/L4 and must be stated with the result.

### 6.3 Fail-safe checks (each must pass; any failure stops the session)

| ID | Check | Pass |
|----|-------|------|
| F1 | Power up with the controller disconnected, then connected | pump never runs at power-up or at script start before the first ON |
| F2 | Kill the script process (`kill -9`) mid-run | pump off within W ms + L2 (L5 measured) |
| F3 | Unplug the controller-to-relay signal wire mid-run | pump off (pull-down works) |
| F4 | Press the hardware E-stop mid-run | pump off immediately; script cannot restart it until the E-stop is reset and the key switch cycled |
| F5 | Turn the key switch to disarm mid-run | pump off; ON command has no effect |
| F6 | Controller reboot mid-run | pump off during and after reboot until a new ON |

### 6.4 What the latency means for placement (for O5)

Placement error along track = ground speed × latency. At design speed v_design (**TBD**, from the airframe plan) and the measured p95 hydraulic latency L:

| v (m/s) | L = 50 ms | L = 100 ms | L = 200 ms | L (measured p95) |
|---------|-----------|------------|------------|------------------|
| 2 | 0.10 m | 0.20 m | 0.40 m | fill in |
| 5 | 0.25 m | 0.50 m | 1.00 m | fill in |
| 8 | 0.40 m | 0.80 m | 1.60 m | fill in |

The decision engine's default `max_position_uncertainty_m` is **1.0 m**; a latency-induced placement error adds to georeference uncertainty, it does not replace it. This table is arithmetic, not a result.

**Pass/fail (proposals, to be confirmed before the run):**

| Check | Pass |
|-------|------|
| L1, L2 median | ≤ 20 ms; p95 ≤ 50 ms (electrical) |
| L3, L4 p95 (if measured) | ≤ 200 ms, or a value with v_design × p95 ≤ 0.5 m, whichever is stricter (**v_design TBD**) |
| F1–F6 | all pass |
| L5 | ≤ W + 50 ms |

## 7. Transport Canada note (no compliance claim)

This bench plan involves **no flight**, so it is not an RPAS operation. **Any flight** of this
airframe — with or without liquid — falls under the Canadian Aviation Regulations **Part IX**,
which Transport Canada's AIM says "apply regardless of the purpose of the RPAS use (e.g.,
recreational, commercial, work and research)" (TC AIM 2026-1, RPA chapter). That includes the applicable
aircraft registration, pilot certification, operating-category and any authorisation rules for
the size and operation planned. **Whether a liquid-dispensing payload changes which
authorisation is needed has not been determined here and must be confirmed with Transport
Canada before any flight.** This repository claims **no** RPAS compliance, and nothing in this
plan should be read as showing the airframe is airworthy or legal to fly. Health Canada's 2026
policy on drone pesticide application concerns pesticides, which this plan does not use.

Sources (retrieved 2026-10-02): Transport Canada, *AIM 2026-1, RPA — Remotely Piloted Aircraft*
(https://tc.canada.ca/sites/default/files/2026-03/aim-2026-1_rpa_en.pdf);
Health Canada, *Pesticide application by drones*
(https://www.canada.ca/en/health-canada/services/publications/product-safety/pesticide-application-drones.html).

## 8. Data-recording template

Copy this table into `docs/mechanical/bench_runs/<YYYY-MM-DD>_<initials>.md` (or a CSV with the same columns) per session. Fill every cell; write "n/a" rather than leaving blanks.

**Session header**

| Field | Value |
|-------|-------|
| Date / time / location | |
| Operator / spotter | |
| Airframe id / configuration (props OFF confirmed Y/N, photo ref) | |
| Pump (make/model/rated V/I/flow/pressure) | |
| Nozzle (make/model/rated flow @ pressure) | |
| Water (source, temperature °C) · liquid is plain water only (Y/N) | |
| Supply (bench PSU model, voltage set, current limit) · GFCI tested (Y/N) | |
| Tank level start/end · head height (cm) | |
| Bench controller / script commit hash | |
| Instrument ids & calibration dates (scale, scope, camera fps) | |
| Pass/fail thresholds in force (copy from §5/§6, note changes + who agreed) | |

**Flow runs (§5)** — columns: `run_id, setting_V, nozzle(Y/N), repeat, T_s, mass_g, Q_L_min, pressure, flow_meter, leak_seen(Y/N), notes`

**Latency runs (§6.2)** — columns: `run_id, cmd(ON/OFF), t_cmd_monotonic_ns, L1_ms, L2_ms, L3_ms, L4_ms, scope_file, video_file, notes`

**Fail-safe checks (§6.3)** — columns: `check, performed(Y/N), result(PASS/FAIL), time_to_off_ms, notes`

**Summary** — columns: `metric, n, min, median, p95, max, threshold, PASS/FAIL`

**Deviations / incidents / near-misses:** free text — anything not following this plan.

## 9. Order of work

1. Mechanic names the parts (§4); fill the TBDs in §3/§5/§6 and agree thresholds with Anwar.
2. Dry run with **no water** (relay + script + scope only, pump disconnected, dummy load) → F1–F6 and L1/L2/L5.
3. Water, no nozzle → §5 free flow, leak check.
4. Water with nozzle → §5, then §6 latency (L3/L4 optional).
5. Fill the data sheets, summarise, sign off (§10).

## 10. Status transitions and sign-off

| Label | Meaning here |
|-------|--------------|
| **BLOCKED-HARDWARE** (today) | plan only; no rig, no data |
| **BENCH** | §5 and §6 executed on real hardware, filled sheets committed, deviations listed, all pass/fail rows resolved |
| VALIDATED / FIELD | **not reachable from this plan**; needs flight authorisation and field evidence that do not exist |

A failed check keeps the status at BLOCKED-HARDWARE and files the failure; it is not rounded up.

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Operator | | | |
| Spotter | | | |
| Approver (Anwar) | | | |
