/** Minimal GeoJSON + Ops API response shapes (no invented telemetry). */

export type OpsBanner = {
  demo?: boolean;
  simulation?: boolean;
  banner?: string | null;
  offline?: boolean;
  error?: string;
  message?: string;
};

export type Position = [number, number] | [number, number, number];

export type Geometry =
  | { type: "Point"; coordinates: Position }
  | { type: "Polygon"; coordinates: Position[][] }
  | { type: "MultiPolygon"; coordinates: Position[][][] }
  | { type: string; coordinates?: unknown };

export type Feature = {
  type: "Feature";
  id?: string | number;
  geometry: Geometry | null;
  properties?: Record<string, unknown> | null;
};

export type FeatureCollection = {
  type: "FeatureCollection";
  features: Feature[];
};

export type OverviewResponse = OpsBanner & {
  device_count?: number;
  weather_count?: number;
  soil_count?: number;
  open_alerts?: number;
  map_layers_enabled?: number;
  tasks_open?: number;
  ts?: string;
  retention?: Record<string, unknown>;
};

export type DeviceRow = {
  device_id: string;
  device_type: string;
  name: string;
  zone_id?: string | null;
  battery_pct?: number | null;
  signal_rssi?: number | null;
  last_seen?: string | null;
  synthetic?: boolean;
};

export type HealthRow = {
  device_id: string;
  status?: string;
  battery_pct?: number | null;
  signal_rssi?: number | null;
  last_seen?: string | null;
  [key: string]: unknown;
};

export type AlertRow = {
  alert_id: string;
  title?: string;
  message?: string;
  severity?: string;
  category?: string;
  state?: string;
  created_at?: string;
  ts?: string;
  synthetic?: boolean;
  [key: string]: unknown;
};

export type LiveResponse = OpsBanner & {
  devices?: DeviceRow[];
  health?: HealthRow[];
  open_alerts?: AlertRow[];
  latest_weather?: Record<string, unknown> | null;
  ts?: string;
};

export type WeatherObs = {
  obs_id: string;
  station_id: string;
  ts: string;
  air_temp?: { value_c: number; kind: string; origin?: string } | null;
  rh_pct?: number | null;
  wind_ms?: number | null;
  precip_mm?: number | null;
  quality?: string;
  synthetic?: boolean;
};

export type WeatherResponse = OpsBanner & {
  observations?: WeatherObs[];
  aggregates?: Record<string, unknown>[];
  note?: string;
};

export type DerivedWeather = OpsBanner & {
  dewpoint?: { value_c?: number; kind?: string; origin?: string };
  dewpoint_c?: number;
  vpd?: { vpd_kpa?: number; origin?: string; algorithm_version?: string };
  vpd_kpa?: number;
  origin?: string;
  algorithm_version?: string;
  gdd_stub?: Record<string, unknown>;
  [key: string]: unknown;
};

export type SoilRow = {
  reading_id?: string;
  device_id?: string;
  zone_id?: string;
  depth_cm?: number;
  moisture_pct?: number;
  temp?: { value_c: number; kind: string } | null;
  quality?: string;
  ts?: string;
  synthetic?: boolean;
  [key: string]: unknown;
};

export type SensorsResponse = OpsBanner & {
  soil?: SoilRow[];
  readings?: Record<string, unknown>[];
  devices?: DeviceRow[];
};

export type AlertsResponse = OpsBanner & {
  alerts?: AlertRow[];
};

export type MapGeoResponse = OpsBanner & FeatureCollection & {
  type: "FeatureCollection";
  features: Feature[];
};

export type MapLayersResponse = OpsBanner & {
  layers?: {
    asset_id: string;
    name: string;
    layer_kind: string;
    enabled: boolean;
    synthetic?: boolean;
  }[];
  time_ranges?: string[];
};

/** agri_edge/agronomy/engine.py Recommendation, plus satellite scouting ones. */
export type Recommendation = {
  field_id: string;
  kind: "irrigation" | "disease" | "frost" | "stage" | "scouting" | "data" | string;
  priority: 1 | 2 | 3;
  title: string;
  action: string;
  why: string[];
  missing: string[];
  confidence: "low" | "medium" | "high" | string;
  sources: string[];
  data: Record<string, unknown>;
};

export type RecommendationsResponse = {
  recommendations?: Recommendation[];
  simulation?: boolean;
  banner?: string | null;
};

export type FieldProfile = {
  field_id: string;
  name: string;
  crop: string;
  seeded: string;
  soil: string;
  lat: number;
  lon: number;
  elevation_m?: number;
  irrigated?: boolean;
  boundary?: { type: "Polygon"; coordinates: number[][][] } | null;
};

export type PrescriptionSummary = {
  prescription_id: string;
  field_id: string;
  product: string;
  unit: string;
  source: string;
  cells_on: number;
  treated_ha: number;
  total_product: number;
  validated: boolean;
  issues: string[];
  approved: boolean;
  approved_by: string | null;
  approved_at: string | null;
  notes: string[];
};
