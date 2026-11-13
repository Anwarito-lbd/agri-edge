/**
 * What the ops proxy is allowed to forward.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * `/api/ops/[...path]` forwards straight to the ops API. Until now it forwarded
 * *everything*, on GET and POST, with no authentication, no session and no
 * middleware anywhere in the app. That included:
 *
 *   POST /api/ops/vra/approve        the human-in-the-loop gate that authorises
 *                                    a variable-rate prescription
 *   POST /api/ops/mapfield/approve   approves a mapping workflow
 *   POST /api/ops/mapfield/execute   starts one
 *
 * So anyone who could reach the Next server could approve a prescription, and
 * the audit record would name whatever `actor` string they sent. The master
 * spec asks for role permissions (§150) and deliberate confirmation on
 * high-consequence commands (§152); neither existed here.
 *
 * The rest of the application is careful about exactly this -- the command
 * route rejects all five verbs with 403, and the alert-ack route refuses any
 * body carrying a forbidden op. The generic proxy was the hole in an otherwise
 * consistent posture, and it was the one route with no tests.
 *
 * THE RULE
 * --------
 * Reads forward. Writes fail closed and name themselves in the refusal. A write
 * is enabled only by setting OPS_ALLOW_WRITES=1 on the server, which is a
 * deliberate act by whoever runs it rather than a default.
 *
 * This is not authentication. It is the smaller, honest thing: the proxy no
 * longer hands out authority it was never asked to hand out. Real roles belong
 * upstream in the ops API, next to the audit log that records them.
 */

/**
 * Upstream paths that change state and that a person may reach through this
 * app. Matched on the joined path segments; `*` matches one segment.
 *
 * Kept in step with the ops API's POST routes by tests/proxy-contract.test.ts
 * (UPSTREAM_POST_ROUTES there is copied from agri_edge/ops/auth.py POST_ROLES).
 *
 * Deliberately absent (24 Sept 2026):
 *   seed        wipes the whole station and reseeds demo data
 *   detections  raw detection ingest -- could plant rows with safety flags
 *   ingest      the machine door (aircraft, sensors), not a person's
 *   auth/users  user administration stays on the station
 */
export const MUTATING_OPS_PATHS: readonly string[] = [
  "alerts/ack",
  "alerts/resolve",
  "alerts/escalate",
  "notes",
  "scouts",
  "manual",
  "cameras",
  "map/layers/toggle",
  "satellite/refresh",
  "odm/submit",
  "mapfield/create",
  "mapfield/validate",
  "mapfield/approve",
  "mapfield/execute",
  "irrigation/recommend",
  "fields",
  "prescriptions",
  "prescriptions/*/approve",
  "vra/approve",
];

function matchesAllowlist(path: string): boolean {
  const segs = path.split("/");
  return MUTATING_OPS_PATHS.some((pattern) => {
    const p = pattern.split("/");
    return p.length === segs.length && p.every((s, i) => s === "*" || s === segs[i]);
  });
}

/**
 * Anything that looks like it touches the aircraft. These are refused on every
 * verb, allowlist or not -- the companion never commands a vehicle, and no
 * environment variable may turn that off.
 */
export const NEVER_PROXY: readonly string[] = [
  "arm",
  "disarm",
  "takeoff",
  "land",
  "rtl",
  "set_mode",
  "mission/start",
  "mavlink",
  "servo",
  "actuator",
  "spray",
  "pump",
  "valve",
];

export type ProxyVerdict =
  | { allowed: true }
  | { allowed: false; status: number; error: string; message: string };

export function writesEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.OPS_ALLOW_WRITES === "1" || env.OPS_ALLOW_WRITES === "true";
}

/**
 * A vehicle word anywhere in the path, as a whole segment (so `farm` does not
 * trip `arm`), or a multi-segment entry as a contiguous run. The old check only
 * looked at the path's start, so `x/arm` or `vehicle/takeoff` slipped past.
 */
function touchesVehicle(segments: string[]): boolean {
  const segs = segments.map((s) => s.toLowerCase());
  return NEVER_PROXY.some((entry) => {
    const e = entry.split("/");
    for (let i = 0; i + e.length <= segs.length; i++) {
      if (e.every((w, j) => segs[i + j] === w)) return true;
    }
    return false;
  });
}

/**
 * Checks on the request itself, for writes:
 *
 * - Content-Type must be JSON. A cross-site `text/plain` or form POST needs no
 *   CORS preflight, so it is exactly what a hostile page can send; the proxy
 *   used to read any body and forward it as JSON.
 * - A browser always sends Origin on a cross-site POST. If it names another
 *   host, refuse.
 */
export function checkWriteRequest(
  method: string,
  headers: Headers,
  requestUrl: string,
): ProxyVerdict {
  if (method !== "POST") return { allowed: true };
  const ctype = (headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  if (ctype !== "application/json") {
    return {
      allowed: false,
      status: 415,
      error: "json_only",
      message: "Writes must be sent as application/json.",
    };
  }
  const origin = headers.get("origin");
  if (origin) {
    // The host the browser addressed is in the Host header (or, behind a
    // reverse proxy, X-Forwarded-Host). `next start` builds request.url from
    // its own bind address instead, so comparing against the URL alone
    // refused every same-origin login on a LAN IP or behind a proxy.
    // A browser cannot set either header on a cross-site request.
    const hosts = new Set<string>();
    for (const h of [headers.get("x-forwarded-host"), headers.get("host")]) {
      for (const part of (h || "").split(",")) if (part.trim()) hosts.add(part.trim().toLowerCase());
    }
    let same = false;
    try {
      hosts.add(new URL(requestUrl).host.toLowerCase());
      same = hosts.has(new URL(origin).host.toLowerCase());
    } catch {
      same = false;
    }
    if (!same) {
      return {
        allowed: false,
        status: 403,
        error: "cross_origin",
        message: "Cross-origin writes are refused.",
      };
    }
  }
  return { allowed: true };
}

/**
 * Decide whether a request may be forwarded.
 *
 * `segments` are the raw path segments after `/api/ops/`.
 */
export function checkProxy(
  segments: string[],
  method: string,
  env: NodeJS.ProcessEnv = process.env,
  opts: { hasSession?: boolean } = {},
): ProxyVerdict {
  const path = segments.join("/").toLowerCase();

  // Path traversal, before anything else. encodeURIComponent on each segment
  // already neutralises this upstream, but a segment of ".." should never have
  // been accepted in the first place and saying so is cheaper than relying on
  // an encoding detail staying correct.
  if (segments.some((s) => s === ".." || s === "." || s.includes("\0"))) {
    return {
      allowed: false,
      status: 400,
      error: "bad_path",
      message: "Path segments may not traverse.",
    };
  }

  if (touchesVehicle(segments)) {
    return {
      allowed: false,
      status: 403,
      error: "forbidden_op",
      message:
        "The companion never commands a vehicle. This path is refused on every " +
        "method and cannot be enabled by configuration.",
    };
  }

  if (method === "GET") return { allowed: true };

  if (!matchesAllowlist(path)) {
    // An unknown write. Fail closed: a path that is not recognised is not
    // proven safe, and the upstream will 404 it anyway if it is harmless.
    return {
      allowed: false,
      status: 403,
      error: "write_not_allowlisted",
      message:
        `POST /api/ops/${path} is not on the proxy's write allowlist. ` +
        "Add it to MUTATING_OPS_PATHS if it is meant to be reachable.",
    };
  }

  // A logged-in person's writes go through: the ops API checks their role and
  // audits them under their name. Without a session, writes still need the
  // server operator's explicit OPS_ALLOW_WRITES (the station's open dev mode).
  if (!opts.hasSession && !writesEnabled(env)) {
    return {
      allowed: false,
      status: 403,
      error: "writes_disabled",
      message:
        `POST /api/ops/${path} changes state upstream. Log in first; ` +
        "without a session this server forwards reads only (OPS_ALLOW_WRITES=1 " +
        "enables anonymous writes against a station in open dev mode).",
    };
  }

  return { allowed: true };
}
