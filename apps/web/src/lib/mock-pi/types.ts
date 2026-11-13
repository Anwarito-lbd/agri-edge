/** Phone ↔ Pi companion contract types (read-only). snake_case, schema_version on every message. */

export const SCHEMA_VERSION = 1 as const;

export type Topic =
  | "heartbeat"
  | "gps"
  | "battery"
  | "detections"
  | "qa_flags"
  | "advisory"
  | "dock"
  | "alert";

export type Severity = "info" | "warn" | "critical";

export type AlertType =
  | "link_lost_mavlink"
  | "gnss_degraded"
  | "battery_critical"
  | "qa_critical"
  | "geofence_warning"
  | "pipeline_fault"
  | "dock_unsafe_power";

export const ALERT_TYPES: readonly AlertType[] = [
  "link_lost_mavlink",
  "gnss_degraded",
  "battery_critical",
  "qa_critical",
  "geofence_warning",
  "pipeline_fault",
  "dock_unsafe_power",
] as const;

export type HeartbeatMsg = {
  schema_version: typeof SCHEMA_VERSION;
  topic: "heartbeat";
  ts: string;
  pi: {
    uptime_s: number;
    pipeline: "running" | "idle" | "fault";
    model_id: string;
  };
  link: {
    mavlink_ok: boolean;
    gnss_ok: boolean;
    ntrip_ok: boolean;
  };
};

export type GpsMsg = {
  schema_version: typeof SCHEMA_VERSION;
  topic: "gps";
  ts: string;
  lat: number;
  lon: number;
  alt_m_msl: number;
  alt_m_agl: number;
  fix_type: number;
  satellites: number;
  hdop: number;
  source: "mavlink_readonly";
};

export type BatteryMsg = {
  schema_version: typeof SCHEMA_VERSION;
  topic: "battery";
  ts: string;
  voltage_v: number;
  current_a: number;
  remaining_pct: number;
  source: "mavlink_readonly";
};

export type QaFlagsMsg = {
  schema_version: typeof SCHEMA_VERSION;
  topic: "qa_flags";
  ts: string;
  flags: string[];
  frame_id: string;
  severity: Severity;
};

export type AdvisoryDecision = "go" | "no_go" | "unknown";

export type AdvisoryMsg = {
  schema_version: typeof SCHEMA_VERSION;
  topic: "advisory";
  ts: string;
  decision: AdvisoryDecision;
  wind_mps: number | null;
  reasons: string[];
};

export type DockMsg = {
  schema_version: typeof SCHEMA_VERSION;
  topic: "dock";
  ts: string;
  present: boolean;
  charging: boolean;
  charge_pct: number | null;
  pi_shutdown_armed: boolean;
  power_cut_safe: boolean;
};

export type AlertMsg = {
  schema_version: typeof SCHEMA_VERSION;
  topic: "alert";
  ts: string;
  id: string;
  type: AlertType;
  severity: Severity;
  title: string;
  body: string;
  ackable: boolean;
  acked?: boolean;
};

export type DetectionFeatureProperties = {
  label: string;
  confidence: number;
  error_m: number;
  frame_id: string;
  validated_locally: boolean;
  in_treatment_zone: boolean | null;
  qa_flags: string[];
  kind?: string;
};

export type DetectionFeature = {
  type: "Feature";
  geometry: {
    type: "Point";
    coordinates: [number, number]; // [lon, lat]
  };
  properties: DetectionFeatureProperties;
  id?: string;
};

export type DetectionsGeoJson = {
  type: "FeatureCollection";
  schema_version: typeof SCHEMA_VERSION;
  demo: true;
  features: DetectionFeature[];
};

export type StatusSnapshot = {
  schema_version: typeof SCHEMA_VERSION;
  demo: true;
  ts: string;
  note: string;
  heartbeat: HeartbeatMsg;
  gps: GpsMsg;
  battery: BatteryMsg;
  qa_flags: QaFlagsMsg;
  advisory: AdvisoryMsg;
  dock: DockMsg;
  alerts: AlertMsg[];
  detections_summary: { count: number };
};

/** Envelope for SSE frames (topic already on payload). */
export type StreamFrame =
  | HeartbeatMsg
  | GpsMsg
  | BatteryMsg
  | QaFlagsMsg
  | AdvisoryMsg
  | DockMsg
  | AlertMsg
  | {
      schema_version: typeof SCHEMA_VERSION;
      topic: "detections";
      ts: string;
      count: number;
    };

/** Forbidden companion ops — must never be implemented as write paths. */
export const FORBIDDEN_OPS = [
  "arm",
  "disarm",
  "set_mode",
  "upload_mission",
  "mission_upload",
  "rc_override",
  "fly",
  "rtl",
  "land",
  "takeoff",
  "command",
  "mavlink_write",
  "publish",
] as const;

export const ALLOWED_OPS = ["subscribe", "unsubscribe", "ping", "ack_alert"] as const;
