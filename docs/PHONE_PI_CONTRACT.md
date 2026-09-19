# Phone ↔ Pi companion contract (read-only)

**Owner:** Anwar (software)  
**Status:** Designed-only (first design draft) — not implemented as a live link  
**Date:** 19 September 2026 (ET)  
**Related:** [SOFTWARE_COMPLETE_CHECKLIST.md](SOFTWARE_COMPLETE_CHECKLIST.md), [PRODUCT_VISION.md](PRODUCT_VISION.md), [HANDOFF.md](../HANDOFF.md)

> **Hard rule:** The phone companion is a **status and alert** surface. It must **never** arm, change flight mode, upload missions, inject RC overrides, or write MAVLink. Same safety contract as the Pi: perception and telemetry **out**; command authority stays with the pilot / FC.

---

## 1. Goals

- Farmer / operator sees live-enough aircraft + pipeline health on a phone (Wi‑Fi near field, LTE via optional relay later).
- Deliver geo-tagged detections and QA flags without requiring a laptop on the truck bed.
- Carry emergency **alert types** (designed now; push path can be mock first).
- Give the mechanic and future dock software a clear boundary: phone talks to **Pi companion services**, not to the Pixhawk.

## 2. Non-goals (explicit)

| Forbidden | Why |
|-----------|-----|
| Arm / disarm | Pi has no write path; phone must not invent one |
| Mode changes (`GUIDED`, `AUTO`, …) | Flight authority = pilot + FC |
| Mission upload / waypoint write | Same |
| RC override / “fly home from phone” | Emergency UX is **alert the human**, not remote pilot from app v1 |
| NTRIP injection via phone → FC | NTRIP stays on GNSS receiver path |
| Treatment valve commands | Treatment fails closed; payload MCU enforces — phone is not in that loop |

Any API that looks like a command channel is a **bug**, even behind a feature flag.

---

## 3. Topology

```
[Phone app]  --Wi‑Fi (preferred) / LTE-->  [Pi 5 companion HTTP+WS]
                                              |
                                              +-- read-only MAVLink decoder (existing)
                                              +-- edge pipeline spool / detections
                                              +-- env + spray advisory (optional topics)
                                              +-- (Phase 2) dock status agent on ground Pi or same host
```

- **v1 transport:** phone joins aircraft or ground Wi‑Fi AP; talks to Pi on LAN.
- **v1.5:** optional cloud/LTE **relay** that only forwards the same read-only topics (no new verbs).
- Auth: shared secret / pairing token on LAN for MVP; rotate before any demo on public LTE.

## 4. Transports

| Layer | Choice | Notes |
|-------|--------|-------|
| Discovery | mDNS or fixed `http://agri-edge.local:8787` | Document default port in app settings |
| Snapshot / REST | **HTTP JSON** `GET` | Bootstrap + reconnect recovery |
| Live stream | **WebSocket** JSON messages | One multiplexed socket; topic field on each frame |
| Encoding | UTF-8 JSON, camelCase or snake_case — **pick snake_case** to match Python edge | Include `schema_version` on every message |

Suggested base:

- `GET /v1/status` → full snapshot (heartbeat + GPS + battery + last detections summary)
- `GET /v1/detections.geojson` → current mission FeatureCollection
- `WS /v1/stream` → subscription; client sends `{"op":"subscribe","topics":[...]}` only (no command ops)

Reject unknown `op` values. Do not implement `publish` from phone except subscribe/ping.

## 5. Topics (Pi → phone)

All timestamps ISO-8601 UTC. Units in the payload, not implied.

### 5.1 `heartbeat`

```json
{
  "schema_version": 1,
  "topic": "heartbeat",
  "ts": "2026-09-19T14:44:00Z",
  "pi": {"uptime_s": 3600, "pipeline": "running", "model_id": "imageweeds_yolox_s"},
  "link": {"mavlink_ok": true, "gnss_ok": true, "ntrip_ok": false}
}
```

### 5.2 `gps`

```json
{
  "schema_version": 1,
  "topic": "gps",
  "ts": "2026-09-19T14:44:01Z",
  "lat": 53.5461,
  "lon": -113.4938,
  "alt_m_msl": 670.2,
  "alt_m_agl": 12.0,
  "fix_type": 3,
  "satellites": 14,
  "hdop": 0.9,
  "source": "mavlink_readonly"
}
```

### 5.3 `battery`

```json
{
  "schema_version": 1,
  "topic": "battery",
  "ts": "2026-09-19T14:44:01Z",
  "voltage_v": 22.1,
  "current_a": 12.4,
  "remaining_pct": 67,
  "source": "mavlink_readonly"
}
```

### 5.4 `detections` (GeoJSON)

FeatureCollection of georeferenced boxes. Each feature:

- `geometry`: Point (centroid) or Polygon (footprint if available)
- `properties`: `label`, `confidence`, `error_m` (georef budget), `frame_id`, `validated_locally` (bool), `in_treatment_zone` (`true`/`false`/`null`), `qa_flags` (string[])

`null` for `in_treatment_zone` means **unasked** — UI must not show as “clear to treat.”

### 5.5 `qa_flags`

Pipeline quality, not crop advice:

```json
{
  "schema_version": 1,
  "topic": "qa_flags",
  "ts": "2026-09-19T14:44:02Z",
  "flags": ["motion_blur", "low_gnss"],
  "frame_id": "…",
  "severity": "warn"
}
```

Example flag names: `motion_blur`, `low_gnss`, `channel_order_unverified`, `uncalibrated_reflectance`, `model_not_local`, `georef_failed`.

### 5.6 `advisory` (optional)

Mirror of wind-gated spray/scout advisory: `go` | `no_go` | `unknown`, with `reasons[]`. `unknown` if wind missing — same as edge code.

### 5.7 `dock` (Phase 2 — design now)

```json
{
  "schema_version": 1,
  "topic": "dock",
  "ts": "…",
  "present": true,
  "charging": false,
  "charge_pct": null,
  "pi_shutdown_armed": false,
  "power_cut_safe": false
}
```

Phone displays only. Shutdown handshake is **Pi ↔ dock controller**, not phone-commanded power cut.

## 6. Emergency alert types (Pi → phone)

Designed topic `alert`. Severity: `info` | `warn` | `critical`.

| `type` | Meaning | v1 behaviour |
|--------|---------|--------------|
| `link_lost_mavlink` | No healthy FC telemetry for N seconds | Banner + optional push |
| `gnss_degraded` | Fix/sats/HDOP below threshold | Banner |
| `battery_critical` | Remaining % or voltage threshold | Banner + push |
| `qa_critical` | Sustained QA failure (e.g. no usable frames) | Banner |
| `geofence_warning` | Outside flight boundary (telemetry-derived) | Banner — **not** auto-RTL from phone |
| `pipeline_fault` | Edge process crash / watchdog | Banner |
| `dock_unsafe_power` | Phase 2: charge path wants cut while Pi not clean | Critical banner |

Alert message shape:

```json
{
  "schema_version": 1,
  "topic": "alert",
  "ts": "…",
  "id": "uuid",
  "type": "battery_critical",
  "severity": "critical",
  "title": "Battery critical",
  "body": "Remaining 15% — land soon",
  "ackable": true
}
```

Phone may `POST /v1/alerts/{id}/ack` (ack only — still not a vehicle command).

## 7. Phone → Pi (allowed verbs only)

| Verb | Purpose |
|------|---------|
| `subscribe` / `unsubscribe` | WS topic filter |
| `ping` | RTT |
| `ack_alert` | Operator saw the alert |
| `GET` snapshot routes | Recover state |

**No** other verbs. Schema tests should fail CI if a handler named `arm`, `set_mode`, `upload_mission`, etc. appears under the companion API package.

## 8. Implementation plan (software-only)

1. **This doc** signed off by Anwar.  
2. Python **mock Pi** on laptop: replay recorded/fake MAVLink + sample GeoJSON over WS.  
3. Point existing phone UI shell at mock; replace mock JSON files with live client.  
4. On real Pi: thin gateway process reading existing read-only telemetry + spool; publish topics.  
5. Push notifications (FCM/APNs) later — same alert payload, different delivery.

## 9. Acceptance criteria (contract “done enough”)

- [ ] Mock server + phone app show heartbeat, GPS, battery, detections map layer, QA flags  
- [ ] Automated test: companion API package has **zero** MAVLink send/write symbols  
- [ ] UI copy never says “treat” unless `validated_locally && in_treatment_zone === true`  
- [ ] Alert types table implemented as enum in code (even if push is stubbed)  
- [ ] Dock fields documented for mechanic interface note (even if always `present: false` in v1)

---

*Last updated: 19 September 2026 (America/Toronto).*
