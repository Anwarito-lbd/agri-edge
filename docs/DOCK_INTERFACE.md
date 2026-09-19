# Charging dock — electrical / software interface (Phase 2)

**Owner (software / handshake):** Anwar  
**Owner (pad, contacts, weather, charge power):** mechanical friend  
**Status:** Designed-only — interface note for Phase 2 hardware; not implemented on aircraft yet  
**Date:** 19 September 2026 (ET)  
**Related:** [PHONE_PI_CONTRACT.md](PHONE_PI_CONTRACT.md) §5.7 `dock`, [MECHANIC_ASSIGNMENT.md](../mechanical/handoff/MECHANIC_ASSIGNMENT.md) Phase 2, [SOFTWARE_COMPLETE_CHECKLIST.md](SOFTWARE_COMPLETE_CHECKLIST.md) Section C

> **Hard rule:** The dock reports status **to the Pi companion** (and the phone only via the same read-only topics). The dock **never** talks to the Pixhawk for flight commands. Phone never commands a power cut.

---

## 1. Purpose

Ground charging station for the **same Phase 1 scouting airframe** so turnaround between scouting flights is faster.

| v1 intent | Detail |
|-----------|--------|
| Same airframe | Contacts / plug bay match Phase 1 power architecture the mechanic builds |
| Simple contacts first | Landing-skid contacts **or** a manual plug bay — pick whichever is safer outdoors |
| Human-supervised land | Operator lands / places the aircraft; dock does not fly the vehicle |
| Autonomous docking | **Not v1** — precision auto-land onto contacts is explicitly out of scope for this revision |

Wireless pad is optional later if contacts prove messy; still human-supervised.

---

## 2. Software boundary

```
[Dock controller / MCU or ground SBC]
        |  status + handshake only
        v
[Pi 5 companion]  --read-only topics-->  [Phone app]
        |
        x  NO path to Pixhawk for arm / mode / mission / RC
```

| Allowed | Forbidden |
|---------|-----------|
| Dock → Pi: present, contacts, charge state, faults, handshake lines | Dock → Pixhawk: any MAVLink / RC / arm / mode |
| Pi → dock: shutdown-ready / abort-shutdown (handshake only) | Phone → dock: power cut, charge start as a flight command |
| Pi → phone: mirror of `dock` topic (read-only) | Phone inventing a command channel “because dock is on the ground” |

Same safety contract as the rest of agri-edge: perception and telemetry **out**; flight authority stays with the pilot / FC.

---

## 3. Status fields (dock → Pi)

Canonical fields for the companion to publish. Names align with the phone contract `dock` topic; extra fields below may appear in the Pi↔dock link and be mapped or omitted on the phone stream.

| Field | Type | Meaning |
|-------|------|---------|
| `present` | bool | Aircraft detected on pad / in cradle (mechanical sense, optical, or load — mechanic chooses) |
| `contact_ok` | bool | Charge / sense contacts closed and polarity / continuity check passed |
| `charging` | bool | Charge current flowing under dock control |
| `charge_pct` | int 0–100 or `null` | Estimated pack SOC if known; else `null` |
| `voltage_v` | float or `null` | Pack or charge-bus voltage when available (preferred when `charge_pct` unknown) |
| `fault_code` | string or `null` | See §3.1; `null` when healthy |
| `pi_shutdown_armed` | bool | Pi has acknowledged “prepare to cut” and entered clean shutdown path |
| `power_cut_safe` | bool | Dock may open the aircraft charge / aux power path without risking mid-write corruption |

At least one of `charge_pct` or `voltage_v` should be populated while `charging` is true when the pack BMS / sense path allows it.

### 3.1 Suggested fault codes

| Code | Meaning |
|------|---------|
| `none` / omit | Healthy |
| `contact_open` | Expected present but contacts not OK |
| `overtemp` | Dock or charge path temperature limit |
| `overcurrent` | Charge current out of range |
| `undervoltage` | Bus / pack below safe charge threshold |
| `polarity` | Reverse / wrong contact mapping detected |
| `handshake_timeout` | Pi did not complete shutdown handshake in time |
| `unsafe_cut_blocked` | Hardware interlock refused cut while Pi not clean |
| `estop` | Local E-stop or interlock open |

Mechanic may add hardware-specific codes; Anwar maps unknown codes to phone `alert` type `dock_unsafe_power` or a generic dock fault banner.

---

## 4. Pi clean shutdown handshake before power cut (**critical**)

The dock **must not** yank 5 V / battery mid-write on the Pi (spool, SD, NVMe). Brief item 06 / mechanic assignment Phase 2 requirement.

### 4.1 Actors

- **Dock controller:** owns the charge contactor / FET that can remove power from the aircraft charge path (and any dock-fed 5 V rail if used on the pad).
- **Pi companion:** owns flush of edge spool, stop of writers, then OS shutdown or “power-cut-safe” ACK.
- **Phone:** displays only (`pi_shutdown_armed`, `power_cut_safe`); **does not** issue the cut.

### 4.2 Sequence (happy path)

```
1. Operator (or dock UI) requests “safe power cut” / end-charge isolation
   OR dock decides charge session complete and wants to open contactor safely.
2. Dock asserts PREPARE_SHUTDOWN to Pi (GPIO / UART / USB CDC — mechanic picks one digital path).
3. Pi receives PREPARE_SHUTDOWN:
   a. Stop accepting new spool writes; finish or cancel in-flight frame writes.
   b. fsync / close open files; stop pipeline processes that hold the disk.
   c. Optionally `systemctl poweroff` or enter a documented “halted, ready for cut” state.
   d. Assert SHUTDOWN_READY to dock (line or message).
4. Dock sets pi_shutdown_armed=true when it sees SHUTDOWN_READY.
5. Dock waits until power_cut_safe criteria met (see timeouts), then opens contactor.
6. Dock publishes power_cut_safe=true briefly, then present/charging update as hardware state changes.
```

### 4.3 Timeouts (software defaults — tune on bench)

| Timer | Default | Behaviour on expiry |
|-------|---------|---------------------|
| `T_ack` — Pi must ACK PREPARE_SHUTDOWN | **5 s** | Retry once; then `fault_code=handshake_timeout`; **do not cut** if Pi was recently alive |
| `T_ready` — Pi must assert SHUTDOWN_READY after ACK | **30 s** | `handshake_timeout`; keep power; alert operator |
| `T_cut_hold` — minimum time SHUTDOWN_READY held before cut | **2 s** | Debounce glitches |
| `T_force` — operator override (hardware key / long-press) | N/A | Only after visible warning; still preferred to wait for ready |

Defaults are for a healthy Pi with SD/NVMe spool. Document any change in the dock wiring note.

### 4.4 Mid-spool / Pi busy

If the edge pipeline is mid-write when PREPARE_SHUTDOWN arrives:

1. Pi **does not** ACK “ready” until writers are stopped and files closed.  
2. Dock **keeps power applied** until SHUTDOWN_READY or `T_ready` expiry.  
3. On `T_ready` expiry: keep power, set `fault_code=handshake_timeout`, raise phone alert `dock_unsafe_power` (critical) — operator decides whether to wait, soft-reboot Pi, or use labelled force cut.  
4. **Never** treat “Pi not answering” as “safe to cut” if `present && contact_ok` and the last Pi heartbeat was recent (< `T_ack` window) — assume mid-spool until proven otherwise.

If Pi is already powered down / crashed before PREPARE_SHUTDOWN: dock may use a **separate** “Pi dead / no 5 V rail sense” path with a longer hold and operator confirmation — still not an automatic silent cut on first timeout.

### 4.5 Interlock summary

| Condition | Contactor may open? |
|-----------|---------------------|
| `power_cut_safe == true` after handshake | Yes |
| `handshake_timeout` | No (unless labelled operator force) |
| `fault_code` in {`overtemp`,`overcurrent`,`polarity`} during charge | Open charge path per hardware safety; still prefer Pi handshake if Pi rail would drop |
| Phone button / app | **Never** alone |

---

## 5. Topic shape (matches PHONE_PI_CONTRACT `dock`)

Pi publishes to the phone over the existing companion stream. Snake_case, `schema_version` on every message.

```json
{
  "schema_version": 1,
  "topic": "dock",
  "ts": "2026-09-19T16:00:00Z",
  "present": true,
  "contact_ok": true,
  "charging": true,
  "charge_pct": 72,
  "voltage_v": 22.4,
  "fault_code": null,
  "pi_shutdown_armed": false,
  "power_cut_safe": false
}
```

Notes:

- v1 aircraft missions may always publish `present: false` until Phase 2 hardware exists.  
- `charge_pct` may be `null` when only `voltage_v` is known.  
- Shutdown handshake is **Pi ↔ dock controller**, not phone-commanded.  
- Related alert: `dock_unsafe_power` when the charge path wants a cut while Pi is not clean ([PHONE_PI_CONTRACT.md](PHONE_PI_CONTRACT.md) §6).

Optional REST snapshot field: include the same object under `GET /v1/status` → `dock`.

---

## 6. Pin / contact story (high level — no FEA)

Mechanic owns geometry, materials, weather sealing, and current ratings. Software only needs **stable sense + controllable cut**.

Suggested logical groups (names are roles, not a pinout table):

| Group | Role |
|-------|------|
| **POWER+ / POWER−** | Main charge path into the aircraft pack / charge port the Phase 1 power architecture exposes |
| **SENSE_PRESENT** | Pad occupied / aircraft seated |
| **SENSE_CONTACT** | Continuity / both poles seated (`contact_ok`) |
| **PREPARE_SHUTDOWN** | Dock → Pi digital request |
| **SHUTDOWN_READY** | Pi → dock digital ACK (or UART message carrying the same meaning) |
| **FAULT / ESTOP** | Hardware open = stop charge; independent of software when possible |
| **GND_REF** | Common reference for sense and handshake lines |

Guidance:

- Keep handshake lines **galvanically sensible** relative to Pi GPIO (level shift / isolator as needed — mechanic).  
- Do not invent FEA, spring force, or contact plating here — that belongs in the friend’s CAD + wiring diagram deliverable.  
- Prop-arc clearance and outdoor sealing remain mechanic requirements ([MECHANIC_ASSIGNMENT.md](../mechanical/handoff/MECHANIC_ASSIGNMENT.md)).

---

## 7. Out of scope (this note / v1 dock)

| Out of scope | Why |
|--------------|-----|
| Spray / treatment payload on the dock or airframe | Separate regulated product; software fails closed without local validation |
| Phone-commanded flight | Pi stays MAVLink read-only; phone is status/alerts only |
| Autonomous precision land / auto-dock as v1 | Human-supervised placement or land first |
| Dock talking to Pixhawk | Flight authority stays with pilot + FC |
| Claiming this note = hardware done | Designed interface only until pad + wiring + bench handshake exist |

---

## 8. Acceptance (docs / software side)

- [x] This note exists for the friend (status fields + shutdown handshake + topic shape).  
- [ ] Bench mock: Pi process speaks PREPARE_SHUTDOWN / SHUTDOWN_READY against a USB or GPIO loopback.  
- [ ] Phone mock shows `dock` topic + `dock_unsafe_power` alert (still designed-only until mock live feed lands).  
- [ ] Friend wiring diagram references these field names and timeouts.

---

*Last updated: 19 September 2026 (America/Toronto).*
