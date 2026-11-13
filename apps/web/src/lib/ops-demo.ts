/**
 * DEMO / SIMULATED sample data for the Ops Station.
 *
 * Served by /api/ops/* when no live ops API is configured or reachable (see
 * ops-mode.ts). Everything here is synthetic and says so: every payload
 * carries `demo: true, simulation: true, synthetic: true, banner: "SIMULATION"`
 * and every row carries `synthetic: true`.
 *
 * It is deterministic -- fixed timestamps, closed-form numbers, no Math.random
 * and no Date.now -- so a reload shows the same thing and tests can pin it.
 * It is a software prototype's sample data: it is not a farm, not telemetry,
 * not a measurement, and no accuracy or performance should be read into it.
 * Detections deliberately carry no confidence scores for that reason.
 */

import type {
  AlertRow,
  DeviceRow,
  FieldProfile,
  Feature,
  FeatureCollection,
  PrescriptionSummary,
  Recommendation,
  SoilRow,
  WeatherObs,
} from "@/lib/ops-types";

export const DEMO_TS = "2026-09-15T12:00:00Z";

const FLAGS = { demo: true, simulation: true, synthetic: true, banner: "SIMULATION" } as const;

type Ring = number[][];

/** Closed rectangle ring in [lon, lat] order. */
function rect(lat: number, lon: number, dLat: number, dLon: number): Ring {
  return [
    [lon - dLon, lat - dLat],
    [lon + dLon, lat - dLat],
    [lon + dLon, lat + dLat],
    [lon - dLon, lat + dLat],
    [lon - dLon, lat - dLat],
  ];
}

const round = (n: number, d = 1) => Math.round(n * 10 ** d) / 10 ** d;

// --- Fields ---------------------------------------------------------------

const FIELD_SPECS = [
  { id: "demo-field-a", name: "Demo field A (canola)", crop: "canola", seeded: "2026-05-12", soil: "loam", lat: 45.4075, lon: -75.7, irrigated: false },
  { id: "demo-field-b", name: "Demo field B (spring wheat)", crop: "spring_wheat", seeded: "2026-05-06", soil: "silt_loam", lat: 45.4035, lon: -75.689, irrigated: false },
  { id: "demo-field-c", name: "Demo field C (potato)", crop: "potato", seeded: "2026-05-20", soil: "sandy_loam", lat: 45.401, lon: -75.699, irrigated: true },
] as const;

const FIELD_HALF = { dLat: 0.0014, dLon: 0.002 };

export const DEMO_FIELDS: FieldProfile[] = FIELD_SPECS.map((f) => ({
  field_id: f.id,
  name: f.name,
  crop: f.crop,
  seeded: f.seeded,
  soil: f.soil,
  lat: f.lat,
  lon: f.lon,
  irrigated: f.irrigated,
  boundary: { type: "Polygon", coordinates: [rect(f.lat, f.lon, FIELD_HALF.dLat, FIELD_HALF.dLon)] },
}));

// --- Devices --------------------------------------------------------------

export const DEMO_DEVICES: DeviceRow[] = [
  { device_id: "WX-DEMO-01", device_type: "weather_station", name: "Demo weather station", zone_id: "demo-field-a", battery_pct: 87, signal_rssi: -71, last_seen: DEMO_TS, synthetic: true },
  { device_id: "SP-DEMO-01", device_type: "soil_probe", name: "Demo soil probe A", zone_id: "demo-field-a", battery_pct: 74, signal_rssi: -78, last_seen: DEMO_TS, synthetic: true },
  { device_id: "SP-DEMO-02", device_type: "soil_probe", name: "Demo soil probe B", zone_id: "demo-field-b", battery_pct: 91, signal_rssi: -69, last_seen: DEMO_TS, synthetic: true },
  { device_id: "SP-DEMO-03", device_type: "soil_probe", name: "Demo soil probe C", zone_id: "demo-field-c", battery_pct: 18, signal_rssi: -84, last_seen: DEMO_TS, synthetic: true },
];

const PROBE_POINT: Record<string, [number, number]> = {
  "WX-DEMO-01": [-75.7015, 45.4083],
  "SP-DEMO-01": [-75.6992, 45.4071],
  "SP-DEMO-02": [-75.6882, 45.4031],
  "SP-DEMO-03": [-75.6987, 45.4006],
};

function health() {
  return DEMO_DEVICES.map((d) => ({
    device_id: d.device_id,
    status: (d.battery_pct ?? 100) < 25 ? "LOW_BATTERY" : "OK",
    battery_pct: d.battery_pct,
    signal_rssi: d.signal_rssi,
    last_seen: d.last_seen,
    synthetic: true,
  }));
}

// --- Alerts ---------------------------------------------------------------

export const DEMO_ALERTS: AlertRow[] = [
  { alert_id: "A-DEMO-001", title: "Soil moisture trending low at 20 cm (sample)", message: "Sample alert from the simulated station.", severity: "WARNING", category: "soil_moisture", state: "OPEN", created_at: "2026-09-15T09:30:00Z", synthetic: true },
  { alert_id: "A-DEMO-002", title: "Wind picked up at the weather station (sample)", message: "Sample alert; already acknowledged.", severity: "INFO", category: "weather", state: "ACKNOWLEDGED", ack_by: "demo user", created_at: "2026-09-15T07:10:00Z", synthetic: true },
  { alert_id: "A-DEMO-003", title: "Probe C battery low (sample)", message: "Sample alert; escalated in the simulation.", severity: "CRITICAL", category: "device", state: "ESCALATED", created_at: "2026-09-14T22:45:00Z", synthetic: true },
];

// --- Weather --------------------------------------------------------------

function weatherObs(): WeatherObs[] {
  const out: WeatherObs[] = [];
  for (let h = 1; h <= 12; h++) {
    const ts = `2026-09-15T${String(h).padStart(2, "0")}:00:00Z`;
    out.push({
      obs_id: `obs-demo-${String(h).padStart(2, "0")}`,
      station_id: "WX-DEMO-01",
      ts,
      air_temp: { value_c: round(11 + 7 * Math.sin(((h - 3) / 12) * Math.PI), 1), kind: "MEASURED", origin: "SYNTHETIC" },
      rh_pct: Math.round(78 - 22 * Math.sin(((h - 3) / 12) * Math.PI)),
      wind_ms: round(2 + 1.5 * Math.abs(Math.sin(h / 3)), 1),
      precip_mm: 0,
      quality: "SAMPLE",
      synthetic: true,
    });
  }
  return out;
}

function derivedWeather() {
  const latest = weatherObs()[11];
  const t = latest.air_temp?.value_c ?? 15;
  const rh = latest.rh_pct ?? 60;
  // Magnus approximation for dewpoint; Tetens for saturation vapour pressure.
  const a = 17.62;
  const b = 243.12;
  const g = Math.log(rh / 100) + (a * t) / (b + t);
  const dew = (b * g) / (a - g);
  const es = 0.6108 * Math.exp((17.27 * t) / (t + 237.3));
  const vpd = es * (1 - rh / 100);
  return {
    ...FLAGS,
    dewpoint: { value_c: round(dew, 1), kind: "DERIVED", origin: "DERIVED" },
    vpd: { vpd_kpa: round(vpd, 3), origin: "DERIVED", algorithm_version: "demo-fixture-1" },
    origin: "DERIVED",
    algorithm_version: "demo-fixture-1",
    gdd_stub: { note: "stub, not computed in the demo", synthetic: true },
  };
}

// --- Soil / sensors -------------------------------------------------------

function soilRows(): SoilRow[] {
  const rows: SoilRow[] = [];
  const base: Record<string, number> = { "SP-DEMO-01": 24, "SP-DEMO-02": 31, "SP-DEMO-03": 19 };
  for (const dev of DEMO_DEVICES.filter((d) => d.device_type === "soil_probe")) {
    for (const [i, depth] of [10, 20, 40].entries()) {
      rows.push({
        reading_id: `soil-${dev.device_id}-${depth}`,
        device_id: dev.device_id,
        zone_id: dev.zone_id ?? undefined,
        depth_cm: depth,
        moisture_pct: base[dev.device_id] + i * 3,
        temp: { value_c: round(13.5 - i * 0.9, 1), kind: "MEASURED" },
        quality: "SAMPLE",
        ts: DEMO_TS,
        synthetic: true,
      });
    }
  }
  return rows;
}

// --- Map ------------------------------------------------------------------

function farmGeo(): FeatureCollection {
  const features: Feature[] = [];
  for (const f of DEMO_FIELDS) {
    features.push({
      type: "Feature",
      id: f.field_id,
      geometry: f.boundary as Feature["geometry"],
      properties: { layer: "field", name: f.name, synthetic: true },
    });
  }
  // One management zone inside field A.
  const a = FIELD_SPECS[0];
  features.push({
    type: "Feature",
    id: "zone-demo-a1",
    geometry: { type: "Polygon", coordinates: [rect(a.lat + 0.0006, a.lon - 0.0008, 0.0006, 0.0009)] },
    properties: { layer: "zone", name: "Demo zone A1", synthetic: true },
  });
  for (const d of DEMO_DEVICES) {
    features.push({
      type: "Feature",
      id: d.device_id,
      geometry: { type: "Point", coordinates: PROBE_POINT[d.device_id] },
      properties: { layer: d.device_type, device_type: d.device_type, name: d.name, synthetic: true },
    });
  }
  return { type: "FeatureCollection", features };
}

function detectionsGeo(): FeatureCollection {
  const pts: [string, string, number, number][] = [
    ["det-demo-1", "weed cluster (sample)", -75.7012, 45.4079],
    ["det-demo-2", "weed cluster (sample)", -75.6988, 45.4069],
    ["det-demo-3", "weed candidate (sample)", -75.6891, 45.4039],
  ];
  return {
    type: "FeatureCollection",
    features: pts.map(([id, label, lon, lat]) => ({
      type: "Feature" as const,
      id,
      geometry: { type: "Point" as const, coordinates: [lon, lat] as [number, number] },
      properties: { label, ts: DEMO_TS, synthetic: true },
    })),
  };
}

function satelliteGeo(fieldId: string): FeatureCollection {
  const spec = FIELD_SPECS.find((f) => f.id === fieldId) ?? FIELD_SPECS[0];
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: `${spec.id}-ndvi-1`,
        geometry: { type: "Polygon", coordinates: [rect(spec.lat - 0.0005, spec.lon + 0.0009, 0.0004, 0.0006)] },
        properties: { kind: "ndvi_decline", baseline: 0.72, latest: 0.58, residual: -0.09, synthetic: true },
      },
      {
        type: "Feature",
        id: `${spec.id}-scout-1`,
        geometry: { type: "Polygon", coordinates: [rect(spec.lat - 0.0005, spec.lon + 0.0009, 0.0006, 0.0008)] },
        properties: { kind: "scout_patch", area_ha: 0.4, synthetic: true },
      },
    ],
  };
}

function prescriptionGeo(): FeatureCollection {
  const a = FIELD_SPECS[0];
  const features: Feature[] = [];
  const cols = 4;
  const rows = 3;
  const w = (FIELD_HALF.dLon * 2) / cols;
  const h = (FIELD_HALF.dLat * 2) / rows;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const lon0 = a.lon - FIELD_HALF.dLon + c * w;
      const lat0 = a.lat - FIELD_HALF.dLat + r * h;
      const on = (r + c) % 3 === 0;
      features.push({
        type: "Feature",
        id: `cell-${r}-${c}`,
        geometry: { type: "Polygon", coordinates: [[[lon0, lat0], [lon0 + w, lat0], [lon0 + w, lat0 + h], [lon0, lat0 + h], [lon0, lat0]]] },
        properties: { rate: on ? 1.5 : 0, unit: "L/ha", synthetic: true },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

// --- Prescriptions / recommendations --------------------------------------

const PRESCRIPTIONS: PrescriptionSummary[] = [
  {
    prescription_id: "rx-demo-001",
    field_id: "demo-field-a",
    product: "herbicide (sample)",
    unit: "L/ha",
    source: "detections",
    cells_on: 4,
    treated_ha: 0.5,
    total_product: 0.8,
    validated: true,
    issues: [],
    approved: false,
    approved_by: null,
    approved_at: null,
    notes: ["Sample prescription. Nothing is sent to any machine."],
  },
  {
    prescription_id: "rx-demo-002",
    field_id: "demo-field-b",
    product: "nitrogen (sample)",
    unit: "kg/ha",
    source: "satellite",
    cells_on: 0,
    treated_ha: 0,
    total_product: 0,
    validated: false,
    issues: ["No treatment zone has been validated locally (sample)."],
    approved: false,
    approved_by: null,
    approved_at: null,
    notes: ["Sample prescription that fails closed."],
  },
];

const RECOMMENDATIONS: Recommendation[] = [
  {
    field_id: "demo-field-c",
    kind: "irrigation",
    priority: 2,
    title: "Soil moisture is trending low (sample)",
    action: "Check the probe and the soil before the next irrigation window.",
    why: ["The simulated probe shows lower moisture at 20 cm than the other fields."],
    missing: ["No rainfall forecast in the demo", "No irrigation records"],
    confidence: "low",
    sources: ["synthetic demo fixture"],
    data: { synthetic: true },
  },
  {
    field_id: "demo-field-b",
    kind: "scouting",
    priority: 2,
    title: "Walk the flagged patch (sample)",
    action: "Scout the highlighted patch on the map and record what you see.",
    why: ["A simulated satellite layer flags a declining patch."],
    missing: ["No ground truth", "No imagery of the patch from the aircraft"],
    confidence: "low",
    sources: ["synthetic demo fixture"],
    data: { synthetic: true },
  },
  {
    field_id: "demo-field-a",
    kind: "data",
    priority: 3,
    title: "Add a boundary for more layers (sample)",
    action: "Draw or paste a field boundary to unlock satellite and prescription layers.",
    why: ["Layers that need a boundary are limited without one."],
    missing: [],
    confidence: "medium",
    sources: ["synthetic demo fixture"],
    data: { synthetic: true },
  },
];

// --- Router ---------------------------------------------------------------

export type DemoReply = { status: number; body: unknown };

export function demoGet(segments: string[], search: URLSearchParams): DemoReply {
  const path = segments.join("/");
  const ok = (body: Record<string, unknown>): DemoReply => ({ status: 200, body: { ...FLAGS, ...body } });

  switch (path) {
    case "overview": {
      const soil = soilRows();
      return ok({
        device_count: DEMO_DEVICES.length,
        weather_count: weatherObs().length,
        soil_count: soil.length,
        open_alerts: DEMO_ALERTS.filter((a) => a.state !== "RESOLVED").length,
        map_layers_enabled: 3,
        tasks_open: 2,
        ts: DEMO_TS,
        retention: {},
      });
    }
    case "live":
      return ok({
        devices: DEMO_DEVICES,
        health: health(),
        open_alerts: DEMO_ALERTS.filter((a) => a.state !== "RESOLVED"),
        latest_weather: weatherObs()[11],
        ts: DEMO_TS,
      });
    case "weather":
      return ok({
        observations: weatherObs(),
        aggregates: [
          { agg_id: "agg-demo-1", period: "2026-09-14", station_id: "WX-DEMO-01", temp_min_c: 8.2, temp_max_c: 17.9, precip_mm: 0, synthetic: true },
          { agg_id: "agg-demo-2", period: "2026-09-13", station_id: "WX-DEMO-01", temp_min_c: 9.1, temp_max_c: 16.4, precip_mm: 1.2, synthetic: true },
        ],
        note: "Synthetic sample observations. Not a real station.",
      });
    case "weather/derived":
      return { status: 200, body: derivedWeather() };
    case "sensors": {
      const soil = soilRows();
      return ok({
        soil,
        readings: soil.map((s) => ({ device_id: s.device_id, depth_cm: s.depth_cm, moisture_pct: s.moisture_pct, ts: s.ts, synthetic: true })),
        devices: DEMO_DEVICES,
      });
    }
    case "alerts":
      return ok({ alerts: DEMO_ALERTS });
    case "map/geojson":
      return { status: 200, body: { ...FLAGS, ...farmGeo() } };
    case "map/detections":
      return { status: 200, body: { ...FLAGS, ...detectionsGeo() } };
    case "map/layers":
      return ok({
        layers: [
          { asset_id: "layer-fields", name: "Fields", layer_kind: "field", enabled: true, synthetic: true },
          { asset_id: "layer-detections", name: "Detections", layer_kind: "detections", enabled: true, synthetic: true },
          { asset_id: "layer-satellite", name: "Satellite: declining patches", layer_kind: "satellite", enabled: true, synthetic: true },
        ],
        time_ranges: ["24h", "7d"],
      });
    case "fields":
      return ok({ fields: DEMO_FIELDS });
    case "satellite":
      return ok({ geojson: satelliteGeo(search.get("field") ?? "") });
    case "prescriptions":
      return ok({ prescriptions: PRESCRIPTIONS });
    case "recommendations":
      return ok({ recommendations: RECOMMENDATIONS });
    case "auth/me":
      return ok({ name: "demo", role: "viewer", kind: "demo", auth_enabled: false });
  }

  const rx = /^prescriptions\/([^/]+)$/.exec(path);
  if (rx) {
    const found = PRESCRIPTIONS.find((p) => p.prescription_id === rx[1]);
    if (found) return ok({ ...found, geojson: prescriptionGeo() });
  }
  if (/^prescriptions\/[^/]+\/export$/.test(path)) {
    return {
      status: 404,
      body: { ...FLAGS, error: "demo_no_export", message: "Demo mode has no downloadable prescription files." },
    };
  }
  return {
    status: 404,
    body: { ...FLAGS, error: "demo_no_such_route", message: `No sample data for /api/ops/${path} in demo mode.` },
  };
}

/** What a write gets in demo mode: refused, nothing is stored or sent anywhere. */
export function demoWriteRefusal(path: string): DemoReply {
  return {
    status: 405,
    body: {
      ...FLAGS,
      error: "demo_read_only",
      message: `Demo mode is read-only: POST /api/ops/${path} was not applied. Nothing is saved or sent.`,
    },
  };
}
