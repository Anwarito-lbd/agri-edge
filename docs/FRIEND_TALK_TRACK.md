# Talk track — ~5–7 minutes (friend meeting)

**Goal:** Show what’s real, what he builds, what you do next. Stay honest.

---

### 0:00 — Open (30s)
“agri-edge is a Canadian farm scouting drone stack — companion computer on a Pi, Pixhawk flies. We scout weeds/livestock/vigour. We are **not** shipping spray on day one.”

### 0:30 — What’s already built (2 min)
- “Software pipeline is real: detect, QA, geo, geofence, tests. Pi cannot command the plane.”
- Open **https://agri-edge-web.vercel.app** — site + proof.
- Open **/app** — “This is the farmer phone UI on a **mock** live feed. Alerts and status only — no arm button on purpose.”
- Open **/proof** or desktop renders — “This is the airframe pack for you.”

### 2:30 — Your job (2 min)
- Open `mechanical/handoff/MECHANIC_ASSIGNMENT.md` + `renders/`.
- “Phase 1: flyable scouting quad under 25 kg, mount for Pi 5 + Camera Module 3, rangefinder for height.”
- “Phase 2 later: charging dock — docs/DOCK_INTERFACE.md — Pi must shut down clean before power cut.”

### 4:30 — My next steps (1 min)
- “I already have the Pi 5 and Camera Module 3 from Vocular. Tomorrow I flash Bookworm Linux (not QNX), run setup, verify the camera, then field imagery.”
- “Until we annotate our own fields, we don’t claim validated_locally.”

### 5:30 — Ask + close (1 min)
- “Any blockers in the STLs or mounts?”
- “Can we lock Phase 1 BOM and a first flyable date?”
- “Spray, phone flying the drone, auto-dock — out of scope for v1.”

### If asked “is software 100% done?”
“MVP and pitch ready. Field-complete only after Pi imagery and local validation. Your metal is the critical path for a flying demo.”
