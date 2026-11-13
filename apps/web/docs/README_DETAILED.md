# agri-edge-web

Product website for **agri-edge** — a Canadian agricultural RPAS companion
computer (Raspberry Pi 5 + Hailo AI HAT + Pixhawk/Cube, under 25 kg).

## Stack

- Next.js (App Router) + TypeScript + Tailwind CSS
- Static marketing pages; dashboard and companion UI are labeled demos
- Ops Station UI under `/ops` proxies to the engineering Ops API

## Pages

| Route | Purpose |
|---|---|
| `/` | Home (design v2): hero, For growers / For investors switch (`?aud=grower`, investors by default), status strip, evidence, safety, honest stage |
| `/product` | Modules, read-only architecture, evidence table, safety principles |
| `/vision` | Staged roadmap, no dates; later stages are planned, not started |
| `/about` | Principles, stage milestones, placeholder team cards, contact (EN/FR) |
| `/pricing` | Evaluation / Pilot / Programme; no prices ("Contact us for pilot pricing") (EN/FR) |
| `/proof` | Gallery of real pipeline / CAD images with honest captions |
| `/hardware` | Airframe views + staged hardware plan |
| `/dashboard` | Mock field dashboard (**Demo**) |
| `/app` | Mobile companion shell with safety banner |
| `/login` | Log in to the ops station (accounts are made on the station) |
| `/ops` | Operations Station overview |
| `/ops/recommendations` | Recommendations that say why, what is missing, confidence and sources |
| `/ops/map` | Farm map: fields, detections, satellite decline patches, prescription grid (toggle; list view) |
| `/ops/fields` | Fields: crop, seeding date, soil, boundary; satellite refresh |
| `/ops/prescriptions` | Build → approve (agronomist, measured wind) → download ISOXML / shapefile |
| `/ops/live` | Live devices / health / open alerts |
| `/ops/weather` | Weather observations + derived |
| `/ops/sensors` | Soil / sensor readings |
| `/ops/alerts` | Alerts: acknowledge / escalate / resolve, recorded under the logged-in name |

## Ops Station + Ops API

The Next.js app never invents farm metrics. Browser calls same-origin
`/api/ops/...`, which proxies to the engineering Ops API:

```
GET/POST /api/ops/[...path]  →  ${OPS_API_URL}/api/ops/...
```

If `OPS_API_URL` is **unset** (the Vercel default), `/ops` runs in a clearly
labelled **DEMO / SIMULATED** mode: deterministic synthetic sample data from
`src/lib/ops-demo.ts` (every payload `synthetic: true`), a "DEMO MODE" banner,
and writes refused. If it is set and reachable, the live API is used; if it is
set but unreachable, reads fall back to the same flagged demo data (`OPS_DEMO=0`
keeps the strict 503). For local development against the Python backend set
`OPS_API_URL=http://127.0.0.1:8765`.

Reads are forwarded as-is. Writes are forwarded only if they are:

- `POST` with `Content-Type: application/json`;
- from this site (the `Origin` must match the `Host` / `X-Forwarded-Host`);
- to a route on the allowlist in `src/lib/ops-proxy-policy.ts`.

`seed`, `detections`, `ingest` and `auth/users` are never reachable through
the app. Neither is anything naming a vehicle action (`arm`, `takeoff`,
`mission`, `pump`, ...).

### Logins

When the ops station has users (`python -m agri_edge.ops.auth add-user NAME
--role admin --db ops.sqlite`), the app's `/login` posts to it and keeps the
session token in an **httpOnly, SameSite=Strict** cookie (`ae_session`). The
token is never readable by page scripts. The proxy forwards it upstream as
`Authorization: Bearer ...`. The ops API decides what each role may do and
writes the person's name into the audit log. Roles run viewer < operator <
agronomist < admin, plus auditor.

| Variable | Meaning |
|---|---|
| `OPS_API_URL` | Ops API base URL. Unset = DEMO / SIMULATED mode (synthetic sample data). |
| `OPS_DEMO` | `1` forces demo data; `0` disables the demo fallback when the API is unreachable. |
| `OPS_AUTH=1` | Redirect `/ops/*` to `/login` when there is no session cookie. Leave it unset for a station without users. |
| `OPS_ALLOW_WRITES=1` | Allow writes **without** a session (only for a station that has no users). With a session, the ops API's roles decide. |
| `AGRIEDGE_COOKIE_SECURE` | The cookie is `Secure` in production builds by default, so browsers only send it over HTTPS (or to `localhost`). On a farm LAN served over plain `http://192.168...`, set `0`, or better, put the app behind HTTPS. |

### Offline and French

- `public/sw.js` (production builds only) keeps the last answer to each ops
  read and shows it offline with an "Offline — data saved at HH:MM" banner.
- Writes are never cached or queued: an approval made offline fails
  visibly.
- Logging out drops the cached data.
- The public site (home, vision, about, pricing, header, footer) and the ops screens are in English and French. The toggle in the header sets the
  `lang` cookie. A test fails if any English string lacks a French one.

Companion mock-Pi routes under `/api/v1/*` are separate and untouched.

### Run Ops API (engineering tree)

```bash
cd /path/to/agri-edge   # e.g. agri-edge-repo
python -m pip install -e ".[dev]"   # or set PYTHONPATH=src
python -m agri_edge.ops.api
# listens on http://127.0.0.1:8765
# JSON: http://127.0.0.1:8765/api/ops/overview
```

Then in this web app:

```bash
export OPS_API_URL=http://127.0.0.1:8765   # optional; this is the default
npm run dev
# open http://localhost:3000/ops
```

Without `OPS_API_URL`, `/ops` shows a **DEMO MODE** banner and synthetic
sample data. It is a software prototype, simulated and bench-tested; the sample
data is not farm telemetry and is not a measurement.

## Proof assets

Copied from the engineering tree into `public/proof/`:

- `airframe_iso.png`, `airframe_top.png`, `airframe_side.png`
- `gob_vs_yolox.jpg`
- `sheep_gt.jpg`, `pred_sheep_1.jpg`
- `pred_weed_1.jpg`, `pred_weeds_species_1.jpg`

## Contact address

No contact address is committed. Set `NEXT_PUBLIC_CONTACT_EMAIL` (see
`.env.example`) and the contact card on `/about#contact` becomes a `mailto:` link;
until then it shows the placeholder `hello@[domain to be set]` (marked
`data-todo="contact-email"`). The "Talk to us" buttons elsewhere link to that card.

## Design v2

Source of truth is the design bot's `agri-edge-design-v2` (SPEC.md, DESIGN.md). In the repo:

- Tokens: `src/styles/tokens.css` + `tokens.json` (checked against each other by `tests/tokens.test.ts`),
  exposed to Tailwind through `@theme` in `src/app/globals.css`. Older `--ae-*` names are aliased there.
- Component CSS: `src/app/v2.css` (marketing pages, scoped under `.v2`) and `src/app/ops-v2.css`
  (ops shell, scoped under `.opsx`). Both are the design CSS with every selector prefixed, so the
  farmer app and older pages keep their styles.
- Copy: `src/lib/i18n-design.ts` holds the design strings (`d.k…`, EN + FR). **The French is not
  native-reviewed.**
- Logo and favicons: `public/brand/`. No analytics and no A/B harness are wired (PIPEDA / Law 25 decision pending).

## Develop

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
npm start
```

## Product truth (do not invent)

- Sheep model AP@.50 **0.905**; imageweeds species ~**0.457** / binary weed **0.673**
- `weed_crop` is pipeline proof only (not field aerial)
- Companion never commands the aircraft (MAVLink read-only)
- Treatment needs `validated_locally` AND geofence
- No spray-as-shipped claim; permissive YOLOX only (no Ultralytics AGPL)

Repo: https://github.com/Anwarito-lbd/agri-edge-web
