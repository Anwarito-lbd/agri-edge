/**
 * Module-level mutable mock Pi companion state.
 * Demo only — never implies a live aircraft. Read-only toward FC.
 */

import { DEMO_DETECTIONS, DEMO_MAP_CENTER } from "@/lib/demo-geo";
import {
  SCHEMA_VERSION,
  type AdvisoryMsg,
  type AlertMsg,
  type AlertType,
  type BatteryMsg,
  type DetectionsGeoJson,
  type DockMsg,
  type GpsMsg,
  type HeartbeatMsg,
  type QaFlagsMsg,
  type Severity,
  type StatusSnapshot,
  type StreamFrame,
} from "./types";

const BASE_LAT = DEMO_MAP_CENTER[0];
const BASE_LON = DEMO_MAP_CENTER[1];

type MockState = {
  started_at_ms: number;
  tick: number;
  battery_pct: number;
  voltage_v: number;
  current_a: number;
  lat: number;
  lon: number;
  alt_m_agl: number;
  alt_m_msl: number;
  fix_type: number;
  satellites: number;
  hdop: number;
  mavlink_ok: boolean;
  gnss_ok: boolean;
  ntrip_ok: boolean;
  pipeline: "running" | "idle" | "fault";
  wind_mps: number;
  qa_flags: string[];
  qa_severity: Severity;
  frame_id: string;
  alerts: AlertMsg[];
  alert_seq: number;
};

function nowIso(): string {
  return new Date().toISOString();
}

function uuidish(seq: number): string {
  return `demo-alert-${seq.toString(16).padStart(4, "0")}-${Date.now().toString(36)}`;
}

function initialState(): MockState {
  return {
    started_at_ms: Date.now(),
    tick: 0,
    battery_pct: 78,
    voltage_v: 22.4,
    current_a: 11.8,
    lat: BASE_LAT + 0.01,
    lon: BASE_LON - 0.02,
    alt_m_agl: 42,
    alt_m_msl: 512.4,
    fix_type: 4,
    satellites: 16,
    hdop: 0.85,
    mavlink_ok: true,
    gnss_ok: true,
    ntrip_ok: false,
    pipeline: "running",
    wind_mps: 3.2,
    qa_flags: [],
    qa_severity: "info",
    frame_id: "F-0840",
    alerts: [
      {
        schema_version: SCHEMA_VERSION,
        topic: "alert",
        ts: nowIso(),
        id: "demo-alert-seed-01",
        type: "qa_critical",
        severity: "warn",
        title: "QA flag · exposure high",
        body: "Frame 0842 · NW quarter · Demo mock — not live aircraft",
        ackable: true,
        acked: false,
      },
    ],
    alert_seq: 1,
  };
}

/** Singleton demo state (per Node process / warm serverless instance). */
let state: MockState = initialState();

/** One simulated tick per this many ms, however many clients are watching. */
export const TICK_MS = 2000;
let lastTickAt = 0;

/**
 * Advance the demo by one tick if a tick is due. Every open stream and every
 * detections poll used to tick the shared state itself, so three open tabs ran
 * the simulated battery down three times as fast. Returns whether it ticked.
 */
export function advanceClock(now: number = Date.now()): boolean {
  // 10% slack so a stream's own setInterval jitter does not skip its tick.
  if (now - lastTickAt < TICK_MS * 0.9) return false;
  lastTickAt = now;
  tickMock();
  return true;
}

const ALERT_CATALOG: {
  type: AlertType;
  severity: Severity;
  title: string;
  body: string;
}[] = [
  {
    type: "gnss_degraded",
    severity: "warn",
    title: "GNSS degraded",
    body: "HDOP / sats below threshold — Demo mock",
  },
  {
    type: "battery_critical",
    severity: "critical",
    title: "Battery critical",
    body: "Remaining low — land soon (Demo mock, not live)",
  },
  {
    type: "link_lost_mavlink",
    severity: "critical",
    title: "MAVLink link lost",
    body: "No healthy FC telemetry for N seconds — Demo mock",
  },
  {
    type: "geofence_warning",
    severity: "warn",
    title: "Geofence warning",
    body: "Telemetry-derived boundary proximity — alert only, no auto-RTL",
  },
  {
    type: "pipeline_fault",
    severity: "critical",
    title: "Pipeline fault",
    body: "Edge process watchdog trip — Demo mock",
  },
  {
    type: "qa_critical",
    severity: "warn",
    title: "QA critical",
    body: "Sustained unusable frames — Demo mock",
  },
  {
    type: "dock_unsafe_power",
    severity: "critical",
    title: "Dock unsafe power",
    body: "Charge path wants cut while Pi not clean — Demo Phase-2 field",
  },
];

function jitter(scale: number): number {
  return (Math.random() - 0.5) * 2 * scale;
}

/** Advance mock physics one step (~2s cadence). */
export function tickMock(): void {
  state.tick += 1;
  const t = state.tick;

  // Battery slowly drops; voltage tracks roughly
  state.battery_pct = Math.max(8, state.battery_pct - 0.08 - Math.random() * 0.04);
  state.voltage_v = Math.max(18.5, 18.2 + (state.battery_pct / 100) * 5.2 + jitter(0.05));
  state.current_a = Math.max(4, 10.5 + jitter(1.2));

  // GPS slight jitter (Saskatchewan-ish demo patch)
  state.lat = BASE_LAT + 0.01 + jitter(0.00018);
  state.lon = BASE_LON - 0.02 + jitter(0.00018);
  state.alt_m_agl = Math.max(8, 42 + jitter(1.5));
  state.alt_m_msl = 470 + state.alt_m_agl + jitter(0.3);
  state.satellites = Math.min(18, Math.max(8, Math.round(16 + jitter(2))));
  state.hdop = Math.max(0.6, Math.min(3.5, 0.85 + jitter(0.25)));
  state.fix_type = state.hdop < 1.2 && state.satellites >= 12 ? 4 : 3;
  state.gnss_ok = state.fix_type >= 3 && state.hdop < 2.5;

  // Wind oscillates → advisory go / no_go
  state.wind_mps = Math.max(0.5, 3.5 + Math.sin(t / 7) * 2.8 + jitter(0.3));

  // Occasional link / pipeline blips
  if (t % 47 === 0) {
    state.mavlink_ok = false;
  } else if (t % 47 === 3) {
    state.mavlink_ok = true;
  }
  if (t % 61 === 0) {
    state.pipeline = "fault";
  } else if (t % 61 === 4) {
    state.pipeline = "running";
  }

  // QA flags rotate
  const qaPool = [
    [],
    ["motion_blur"],
    ["low_gnss"],
    ["motion_blur", "low_gnss"],
    ["uncalibrated_reflectance"],
  ];
  const qi = Math.floor(t / 5) % qaPool.length;
  state.qa_flags = qaPool[qi]!;
  state.qa_severity =
    state.qa_flags.length === 0
      ? "info"
      : state.qa_flags.includes("low_gnss")
        ? "warn"
        : "info";
  state.frame_id = `F-${(840 + (t % 200)).toString().padStart(4, "0")}`;

  // Occasional new alert (~ every 12–18 ticks)
  if (t > 0 && t % 15 === 0) {
    pushRandomAlert();
  }

  // Auto-raise battery_critical when low
  if (state.battery_pct <= 18) {
    ensureAlert("battery_critical", "critical", "Battery critical", [
      `Remaining ${state.battery_pct.toFixed(0)}% — land soon (Demo mock)`,
    ]);
  }
  if (!state.mavlink_ok) {
    ensureAlert(
      "link_lost_mavlink",
      "critical",
      "MAVLink link lost",
      ["No healthy FC telemetry — Demo mock"],
    );
  }
  if (state.pipeline === "fault") {
    ensureAlert(
      "pipeline_fault",
      "critical",
      "Pipeline fault",
      ["Edge process watchdog — Demo mock"],
    );
  }
}

function ensureAlert(
  type: AlertType,
  severity: Severity,
  title: string,
  bodies: string[],
): void {
  const recent = state.alerts.find(
    (a) => a.type === type && !a.acked && Date.now() - Date.parse(a.ts) < 60_000,
  );
  if (recent) return;
  state.alert_seq += 1;
  state.alerts.unshift({
    schema_version: SCHEMA_VERSION,
    topic: "alert",
    ts: nowIso(),
    id: uuidish(state.alert_seq),
    type,
    severity,
    title,
    body: bodies[0] ?? title,
    ackable: true,
    acked: false,
  });
  // Cap list
  if (state.alerts.length > 12) state.alerts.length = 12;
}

function pushRandomAlert(): void {
  const pick = ALERT_CATALOG[Math.floor(Math.random() * ALERT_CATALOG.length)]!;
  // Skip dock alert most of the time (Phase 2 field)
  if (pick.type === "dock_unsafe_power" && Math.random() > 0.15) {
    return;
  }
  state.alert_seq += 1;
  state.alerts.unshift({
    schema_version: SCHEMA_VERSION,
    topic: "alert",
    ts: nowIso(),
    id: uuidish(state.alert_seq),
    type: pick.type,
    severity: pick.severity,
    title: pick.title,
    body: pick.body,
    ackable: true,
    acked: false,
  });
  if (state.alerts.length > 12) state.alerts.length = 12;
}

export function ackAlert(id: string): AlertMsg | null {
  const a = state.alerts.find((x) => x.id === id);
  if (!a) return null;
  a.acked = true;
  return { ...a };
}

export function getHeartbeat(): HeartbeatMsg {
  const uptime_s = Math.floor((Date.now() - state.started_at_ms) / 1000);
  return {
    schema_version: SCHEMA_VERSION,
    topic: "heartbeat",
    ts: nowIso(),
    pi: {
      uptime_s,
      pipeline: state.pipeline,
      model_id: "imageweeds_yolox_s",
    },
    link: {
      mavlink_ok: state.mavlink_ok,
      gnss_ok: state.gnss_ok,
      ntrip_ok: state.ntrip_ok,
    },
  };
}

export function getGps(): GpsMsg {
  return {
    schema_version: SCHEMA_VERSION,
    topic: "gps",
    ts: nowIso(),
    lat: Number(state.lat.toFixed(6)),
    lon: Number(state.lon.toFixed(6)),
    alt_m_msl: Number(state.alt_m_msl.toFixed(1)),
    alt_m_agl: Number(state.alt_m_agl.toFixed(1)),
    fix_type: state.fix_type,
    satellites: state.satellites,
    hdop: Number(state.hdop.toFixed(2)),
    source: "mavlink_readonly",
  };
}

export function getBattery(): BatteryMsg {
  return {
    schema_version: SCHEMA_VERSION,
    topic: "battery",
    ts: nowIso(),
    voltage_v: Number(state.voltage_v.toFixed(2)),
    current_a: Number(state.current_a.toFixed(1)),
    remaining_pct: Number(state.battery_pct.toFixed(1)),
    source: "mavlink_readonly",
  };
}

export function getQaFlags(): QaFlagsMsg {
  return {
    schema_version: SCHEMA_VERSION,
    topic: "qa_flags",
    ts: nowIso(),
    flags: [...state.qa_flags],
    frame_id: state.frame_id,
    severity: state.qa_severity,
  };
}

export function getAdvisory(): AdvisoryMsg {
  const wind = Number(state.wind_mps.toFixed(1));
  // Scout advisory: go under ~5.5 m/s, no_go above (Demo wind gate)
  let decision: AdvisoryMsg["decision"];
  const reasons: string[] = [];
  if (wind == null || Number.isNaN(wind)) {
    decision = "unknown";
    reasons.push("wind missing");
  } else if (wind > 5.5) {
    decision = "no_go";
    reasons.push(`wind ${wind} m/s above 5.5 m/s gate`);
  } else {
    decision = "go";
    reasons.push(`wind ${wind} m/s within scout gate`);
  }
  if (!state.mavlink_ok) {
    decision = "no_go";
    reasons.push("mavlink link not ok");
  }
  return {
    schema_version: SCHEMA_VERSION,
    topic: "advisory",
    ts: nowIso(),
    decision,
    wind_mps: wind,
    reasons,
  };
}

export function getDock(): DockMsg {
  return {
    schema_version: SCHEMA_VERSION,
    topic: "dock",
    ts: nowIso(),
    present: false,
    charging: false,
    charge_pct: null,
    pi_shutdown_armed: false,
    power_cut_safe: false,
  };
}

export function getAlerts(): AlertMsg[] {
  return state.alerts.map((a) => ({ ...a }));
}

export function getDetectionsGeoJson(): DetectionsGeoJson {
  // Slight jitter on demo detections so the list feels live
  const features = DEMO_DETECTIONS.map((d, i) => {
    const jLat = d.lat + jitter(0.00005);
    const jLon = d.lng + jitter(0.00005);
    return {
      type: "Feature" as const,
      id: d.id,
      geometry: {
        type: "Point" as const,
        coordinates: [Number(jLon.toFixed(6)), Number(jLat.toFixed(6))] as [
          number,
          number,
        ],
      },
      properties: {
        label: d.label,
        confidence: Number((0.72 + ((i * 0.07) % 0.22)).toFixed(3)),
        error_m: Number((1.2 + i * 0.3).toFixed(1)),
        frame_id: state.frame_id,
        validated_locally: false,
        in_treatment_zone: null,
        qa_flags: state.qa_flags.slice(0, 1),
        kind: d.kind,
      },
    };
  });
  return {
    type: "FeatureCollection",
    schema_version: SCHEMA_VERSION,
    demo: true,
    features,
  };
}

export function getStatusSnapshot(): StatusSnapshot {
  const detections = getDetectionsGeoJson();
  return {
    schema_version: SCHEMA_VERSION,
    demo: true,
    ts: nowIso(),
    note: "DEMO mock-Pi companion feed — not live aircraft. Read-only; does not arm/fly.",
    heartbeat: getHeartbeat(),
    gps: getGps(),
    battery: getBattery(),
    qa_flags: getQaFlags(),
    advisory: getAdvisory(),
    dock: getDock(),
    alerts: getAlerts(),
    detections_summary: { count: detections.features.length },
  };
}

/** Build one multiplexed set of topic frames after ticking. */
export function nextStreamFrames(now: number = Date.now()): StreamFrame[] {
  advanceClock(now);
  const detections = getDetectionsGeoJson();
  const frames: StreamFrame[] = [
    getHeartbeat(),
    getGps(),
    getBattery(),
    getQaFlags(),
    getAdvisory(),
    getDock(),
    {
      schema_version: SCHEMA_VERSION,
      topic: "detections",
      ts: nowIso(),
      count: detections.features.length,
    },
  ];
  // Emit newest unacked alert if any changed this tick
  const newest = state.alerts[0];
  if (newest && !newest.acked && state.tick % 15 === 0) {
    frames.push({ ...newest });
  }
  return frames;
}

export function resetMockForTests(): void {
  state = initialState();
  lastTickAt = 0;
}
