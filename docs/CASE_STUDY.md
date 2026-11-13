# Building Agri-Edge

I wanted a companion computer that could look at a field without being trusted to fly the aircraft, and without being trusted to open a valve because a model was confident. That constraint shaped the repository more than any single feature.

## The split I would not give up

A Raspberry Pi on a survey drone is a Linux userspace process. It will crash, it will stall, and it will eventually run a model that is wrong about a plant. The autopilot already owns attitude, the geofence, the battery failsafe and the trip home. If the Pi can also arm, change mode, or upload a mission, those failsafes depend on a process that is allowed to die. So `telemetry/mavlink_link.py` is read-only on purpose. There is no method on it that could command the vehicle, and the tests look for one. Mission commands, if they ever exist, have to come through `VehicleAdapter` and a safety supervisor that fails closed. They do not exist as a flight path today.

The same instinct applies to spraying. A detection carries `validated_locally`. `may_drive_treatment` is false unless that flag is true and the point has been placed inside the treatment geofence. The treatment engine in `decision/engine.py` goes further: ten gates, a human arm, a human command with a short life, and an actuator object that must be marked simulated or the engine refuses to construct. I have not attached a pump. The simulated actuator appends a dictionary to a list. That is the whole action.

I kept the ground station in the same moral category. Irrigation is a MQTT topic on the ground. It is not bridged onto MAVLink. Node-RED, farmOS, ArduPilot and the website stay outside `src/`. The website is [agri-edge-web](https://github.com/Anwarito-lbd/agri-edge-web). I checked the public deployment while writing this: `https://agri-edge-web.vercel.app` answered, and the page title was “agri-edge — Aerial crop scouting software prototype”. The GitHub repo is private, so I did not re-audit its tree from this machine. The product split is still the one in `docs/architecture/current-system.md`: this repository is the Python brain, that one is the site and the companion.

## Optics, before the model

The mistake I kept almost making was to treat weed detection as a training problem. It is an optics problem first. The pinhole formula in `training/gsd_calculator.py` is small enough to argue with:

ground width equals sensor width over focal length, times altitude. Divide by the pixel count and you have centimetres per pixel.

On the Pi Camera Module 3 that is a 6.45 mm sensor, a 4.74 mm lens and 4608 pixels across. Letterboxing that frame into a 640-pixel network throws away 7.2× of linear resolution before the detector runs. I ran the calculator on 13 November 2026 and saved the stdout. A 3 cm seedling stays above 20 pixels only up to 0.7 m if you downscale the whole frame, and 5.1 m if you tile at native resolution. At a normal 30 m survey height it is a fraction of a pixel either way. No checkpoint repairs that. A 30 cm target at the same height is 33.9 pixels when tiled, which is a different product: mature plants and, at a push, livestock, not seedlings.

Tiling buys the resolution back and spends the blur budget. Whole-frame inference used to hide a few pixels of smear inside the downscale. At native resolution the smear is the smear. The motion script, same day, says that at 30 m and 5 m/s the shutter has 1.77 ms if the smear must stay under one pixel. The rolling-shutter figure uses a 33 ms readout I have marked as “measure this” in the script, and under that assumption mapping-grade geometry is down around 1.3 m/s while a single 30 cm plant, which only occupies a few dozen rows, moves 0.24 px at 5 m/s. Detection and mapping are not the same flight.

An earlier note in `docs/EDGE_PIPELINE.md` quotes 0.6 m and 3.9 m, from a 4056-wide frame. The sensor width in the code was corrected after that. I am quoting the logs, not that paragraph.

## What I found by looking, and by testing

Three dataset problems were worse than a low mAP, because a low mAP at least looks like a warning. One “aerial” weed set was ground-level close-ups and indoor trays. Another labelled the potted specimens and left the wild weeds as background. The sheep set was machine-augmented, which would have leaked across a random split if the same source photo had landed on both sides. The model cards under `models/` are the record of those checks. I did not retrain anything for this write-up. The ONNX files are not in git.

The coverage planner had a quieter bug, and the test is still the best description of it. Lines placed on the boundary vanished, because a vertex sitting on the scan line is counted once by the half-open rule and an edge along the line produces no crossing at all. Spreading a fixed number of lines across the span also opened the spacing past the overlap I thought I had asked for. `coverage_gaps` samples the field on a grid and asks how much of it is farther than half a swath from any pass. That is what caught it. On the notched polygon I used for the portfolio run, the same function still reports 3.12% unseen at an 80-by-80 sample. I am leaving that number visible. A planner that always prints zero is not a check.

An audit later found nine POST handlers pasted inside `do_GET`, including the route that approves a variable-rate prescription. GET returned 500 because `body` did not exist. POST returned 404 because `do_POST` never had the route. The linter had been a command that succeeded when ruff was missing, so the bug sat there. `Makefile` now fails if ruff is absent. I care about that more than about another dashboard page.

## The run I can stand behind

The simulations were real code, and they did not leave a trail a reader could open. `fly --simulate` printed a JSON summary and wrote a spool that git ignores. The coverage planner had no picture. The GSD script printed a table and exited. So I added `scripts/portfolio_demo.py`, which calls those entry points and writes `docs/proof/`. I ran it. I did not type the numbers in afterwards.

The capture demo took twelve synthetic frames. All twelve passed QA. Blur, as Laplacian variance, sat between 188.6 and 190.4 against a threshold of 100. The aircraft model flew 27.52 m east, because it integrates ground speed over wall-clock time and twelve frames at a quarter-second interval do not make a long transect. Every frame got one `vegetation` box at confidence 1.0 from the excess-green stub, and every sidecar said `decision_support_only: true`. The spool tagged them ANOMALY, which is what the pipeline does when a detection exists, and then I deleted the arrays. The pictures in the README are the first of those frames: the row scene, and NDVI of the same array. The NDVI mean is 0.016 because the healthy rows and the stressed patch cancel. The patch is the point of the image. It is not calibrated reflectance.

The treatment cases were eight calls to `TreatmentDecisionEngine.process`. I had a false start worth admitting. The first time, every case was refused for `ACTUATOR_STALE_HEARTBEAT`, including the one I had built to pass. The engine’s clock was frozen at a test timestamp and the actuator’s heartbeat was wall time, which the gate treats as a heartbeat from the future. That is the gate working. I gave both the same clock and ran it again. One case recorded a simulated command. Seven recorded none, for the reasons in `docs/proof/decisions.json`: not armed, model not validated, confidence too low, outside the geofence, mission paused, command expired, position NaN.

Penman-Monteith on FAO-56’s Brussels example returned 3.880 mm/day against the paper’s 3.9. The canola chart next to it is a script I wrote, twenty-one days of temperatures in the demo file, and the rain on 15 June is 18 mm because I typed 18. Depletion fell from 26.8 mm to 10.2 mm. The crop never went into stress. Root growth kept readily available water ahead of the deficit, which is what the chart shows.

`pytest` the same day: 1900 passed, 30 skipped, 37.60 seconds. The skips are live services. SITL did not run. An earlier status note says an ArduCopter SITL build was exercised in September 2026. I am not repeating that claim as something I just watched. The binary is not on this machine.

## What is still unproven

This pass did not scout a field, compile a Hailo model, or open a valve. `docs/status.md` keeps those rows blocked on hardware. The part I trust is the part that can show its refusals. A green detection, a coordinate, and a pump are three different objects, and the code keeps them that way.
