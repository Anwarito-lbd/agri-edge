# PX4 evaluation note (companion to ADR-0001)

**Status:** evaluation only · **Date:** 2026-10-02 · **Decision: unchanged.**
**ArduPilot SITL stays the primary and only supported path.** PX4 is a long-term evaluation
track (ADR-0001 item 3). Nothing here adds PX4 code, a PX4 dependency, or dual support.

Evidence labels used below: **VERIFIED-SOURCE** = read from the cited source on 2026-10-02;
**REPO** = true of this repository's code today; **UNVERIFIED** = plausible/general knowledge
that was not checked against a source or a run. No PX4 SITL or hardware run exists in this
repository; every PX4 behaviour claim about *our* integration is therefore UNVERIFIED.

## What would have to be true to switch

Switching is worth a second look only if one of these becomes a real requirement:

1. We must ship **proprietary changes to the flight controller firmware** and cannot publish them
   (GPL-3.0 vs BSD-3-Clause, see the licence row).
2. A **ROS 2 / uXRCE-DDS** companion architecture becomes the integration path (Profile B, Jetson-class).
3. A chosen **Pixhawk-standard board** is better supported on PX4 than on ArduPilot for the target airframe.
4. A funder/customer requires the **Dronecode/Linux Foundation** governance model.

None of these is true today: the product's differentiation is above the autopilot (detection,
georeferencing, decision gate), and the companion link is MAVLink **read-only**.

## Criteria table

| Criterion | ArduPilot (current) | PX4 (evaluation) | Evidence |
|---|---|---|---|
| **Licence** | GPL-3.0 | BSD-3-Clause | VERIFIED-SOURCE: GitHub API `license.spdx_id` for `ArduPilot/ardupilot` and `PX4/PX4-Autopilot` ([1][9]). Implication (modified firmware distributed with a vehicle must offer source under GPL-3; BSD does not) is the usual reading, from [6]; **not legal advice, UNVERIFIED by counsel.** Our code runs on a *separate* companion computer talking MAVLink, which [6] describes as unaffected by GPL-3 — also UNVERIFIED by counsel. |
| **MAVLink compatibility** | Speaks MAVLink; SITL (`scripts/sitl.sh`) is what the repo's telemetry code was run against (14/14 checks, 10 frames, per `docs/status.md`). | Speaks MAVLink and also uXRCE-DDS/ROS 2 ([4]). | ArduPilot: **REPO** (run). PX4 MAVLink support: VERIFIED-SOURCE [3][4]. That `telemetry/mavlink_link.py` works unchanged on PX4: **UNVERIFIED, never run.** |
| **Companion integration** | Pi 5 + pymavlink, read-only (`telemetry/mavlink_link.py`, `vehicle/ardupilot.py`). | Companion computers over MAVLink or uXRCE-DDS; MAVSDK, ROS 2, MAVROS, mavlink-router listed in the PX4 guide ([4]). | PX4: VERIFIED-SOURCE [4]. Our link reads only the common-dialect messages `GLOBAL_POSITION_INT`, `GPS_RAW_INT`, `ATTITUDE`, `VFR_HUD`, `SYS_STATUS` (**REPO**, `mavlink_link.py`); PX4 emitting the same with the same semantics/units is **UNVERIFIED**. Flight-mode decoding from HEARTBEAT `custom_mode` is autopilot-specific, so a PX4 `VehicleAdapter` would need its own mapping (**UNVERIFIED** extent). |
| **Pixhawk board targets** | Open-hardware list includes Holybro Pixhawk 4 / 6C / 6X, CubePilot Cube Orange, CUAV V5+/6X and many more; very wide board list including closed-hardware and Linux boards ([5]). | Pixhawk-standard boards FMUv3–FMUv6X(-RT), e.g. Holybro Pixhawk 6C / 6X / 5X / 4, Hex Cube Black, mRo Pixracer ([3]). | VERIFIED-SOURCE [3][5]. The *friend's* chosen FC is not recorded in this repo (HARDWARE_PLAN says "Pixhawk-class"); compatibility with either stack is therefore **UNVERIFIED** until a model is named. |
| **Community / activity** | 15,973 stars, 21,487 forks, 3,247 open issues; last push 2026-10-02; latest Copter release `Copter-4.7.1` (2026-09-03). | 12,729 stars, 16,099 forks, 405 open issues; last push 2026-10-02; latest release `v1.17.0` (2026-05-13). | VERIFIED-SOURCE: GitHub REST API snapshot taken 2026-10-02 [1][9]. Stars/issues are popularity proxies, **not quality or fitness evidence**. |
| **Governance** | ArduPilot project (community, partner-supported). | Dronecode Foundation, a Linux Foundation project ([2][7]). | PX4: VERIFIED-SOURCE [7]. ArduPilot governance detail: **UNVERIFIED** (not read). |
| **Simulation** | ArduCopter SITL built and run in WSL2 here (`scripts/sitl.sh`, `tests/test_sitl.py`). | SITL and HIL exist per [2][7]. | ArduPilot: **REPO**. PX4: VERIFIED-SOURCE that it exists; **never run here**. |
| **Agriculture-specific features** (spray control, terrain following, survey grid) | Not evaluated for this product. | Not evaluated for this product. | **UNVERIFIED** both ways — deliberately out of scope: the autopilot never gets a treatment command from this repo. |
| **Safety certification** | None claimed. | None claimed. | OpenFly's comparison records "no certification evidence in the indexed sources" for both ([8]); we infer nothing. |

## Impact on this repo if PX4 were ever adopted

* `VehicleAdapter` (`src/agri_edge/vehicle/`) is the seam: a `Px4Adapter` would sit beside
  `ArduPilotAdapter`; nothing upstream of the adapter changes.
* Companion MAVLink stays **read-only** until the product-level decision and safety supervisor
  that ADR-0001 already requires. No AI output drives motors under either stack.
* The decision gate (`decision/engine.py`), geofence and georeferencing are autopilot-agnostic.
* Work to assess first: a PX4 SITL run of `tests/test_sitl.py`-style checks, and a HEARTBEAT mode map.

## Proposed bake-off (not started — BLOCKED on time/hardware, not on design)

1. Run PX4 SITL (multicopter) in WSL2 and replay the existing telemetry-pipeline checks.
2. Record: do all five messages arrive at usable rates with the units `mavlink_link.py` assumes?
3. Compare against the same checks on ArduCopter SITL.
4. Revisit this table; only then propose an ADR change.

Until step 1 is done, every PX4 integration claim above stays **UNVERIFIED**.

## Sources (retrieved 2026-10-02)

1. GitHub REST API, `PX4/PX4-Autopilot` — license BSD-3-Clause; stars/forks/issues/pushed_at; latest release `v1.17.0`. https://api.github.com/repos/PX4/PX4-Autopilot
2. PX4-Autopilot README (BSD-3, Dronecode/Linux Foundation, MAVLink + DDS/ROS 2, SITL/HIL). https://github.com/PX4/PX4-Autopilot
3. PX4 User Guide, Pixhawk Standard Autopilots (FMUv3–FMUv6X-RT board list). https://docs.px4.io/main/en/flight_controller/autopilot_pixhawk_standard.html
4. PX4 Guide v1.16, Companion Computers (MAVLink/uXRCE-DDS, MAVSDK, ROS 2, MAVROS, MAVLink Router). https://docs.px4.io/v1.16/en/companion_computer/index
5. ArduPilot Copter docs, Choosing an Autopilot (board lists; Linux boards). https://ardupilot.org/copter/docs/common-autopilots.html
6. Projects House, "PX4 vs ArduPilot: Choosing Drone Firmware" (licence implications; secondary source). https://www.projects-house.com/articles/drone-development/px4-vs-ardupilot/
7. Dronecode / Linux Foundation governance statement in [2].
8. OpenFly Tech Hub, "PX4 vs ArduPilot Flight Stacks - Evidence Comparison" (GitHub-API licence record; "certification: unknown"). https://openfly.win/comparisons/px4-vs-ardupilot/
9. GitHub REST API, `ArduPilot/ardupilot` (GPL-3.0; counts; `Copter-4.7.1`). https://api.github.com/repos/ArduPilot/ardupilot
