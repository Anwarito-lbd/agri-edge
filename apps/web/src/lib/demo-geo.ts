/** Mock Saskatchewan-ish detections — Demo only, not live telemetry. */

export type DemoDetection = {
  id: string;
  kind: "weed" | "livestock" | "vigour";
  label: string;
  lat: number;
  lng: number;
  note: string;
};

/** Roughly near Saskatoon / prairie belt */
export const DEMO_MAP_CENTER: [number, number] = [52.1579, -106.6702];

export const DEMO_DETECTIONS: DemoDetection[] = [
  {
    id: "D-01",
    kind: "weed",
    label: "Weed cluster",
    lat: 52.1682,
    lng: -106.7014,
    note: "imageweeds binary · Demo",
  },
  {
    id: "D-02",
    kind: "weed",
    label: "Kochia candidate",
    lat: 52.1511,
    lng: -106.6528,
    note: "species label weak · Demo",
  },
  {
    id: "D-03",
    kind: "livestock",
    label: "Sheep group",
    lat: 52.1425,
    lng: -106.689,
    note: "aerial_sheep · Demo",
  },
  {
    id: "D-04",
    kind: "livestock",
    label: "Sheep outlier",
    lat: 52.1398,
    lng: -106.6755,
    note: "AP path only · Demo",
  },
  {
    id: "D-05",
    kind: "vigour",
    label: "Low vigour zone",
    lat: 52.1744,
    lng: -106.6402,
    note: "ExG index · Demo",
  },
];

/** Simple polygon around a demo field patch (NW quarter mock) */
export const DEMO_FIELD_POLYGON: [number, number][] = [
  [52.1755, -106.712],
  [52.1755, -106.688],
  [52.162, -106.688],
  [52.162, -106.712],
];

export const DEMO_WEED_POLYGON: [number, number][] = [
  [52.1705, -106.705],
  [52.1705, -106.697],
  [52.166, -106.697],
  [52.166, -106.705],
];
