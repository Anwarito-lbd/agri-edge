/**
 * Map layers from the ops API, merged into one collection the map draws.
 *
 * Each source tags its features with `properties.layer`, so the map can colour
 * them and the page can toggle them. Pure functions; tested without Leaflet.
 */

import type { Feature, FeatureCollection, Geometry } from "@/lib/ops-types";

export type LayerId = "farm" | "detections" | "satellite" | "prescription";
export const LAYER_IDS: LayerId[] = ["farm", "detections", "satellite", "prescription"];

export type LayerSources = Partial<Record<LayerId, FeatureCollection | null | undefined>>;

export function tag(fc: FeatureCollection | null | undefined, layer: LayerId): Feature[] {
  return (fc?.features ?? []).map((f, i) => ({
    ...f,
    id: `${layer}:${f.id ?? i}`,
    properties: { ...(f.properties ?? {}), source_layer: layer },
  }));
}

export function mergeLayers(sources: LayerSources, visible: Set<LayerId>): FeatureCollection {
  const features: Feature[] = [];
  for (const id of LAYER_IDS) {
    if (visible.has(id)) features.push(...tag(sources[id], id));
  }
  return { type: "FeatureCollection", features };
}

/** Every polygon ring set in a geometry, MultiPolygons flattened (W4: they were counted but never drawn). */
export function polygonsOf(g: Geometry | null): [number, number][][][] {
  if (!g) return [];
  if (g.type === "Polygon" && Array.isArray(g.coordinates)) {
    return [g.coordinates as [number, number][][]];
  }
  if (g.type === "MultiPolygon" && Array.isArray(g.coordinates)) {
    return g.coordinates as [number, number][][][];
  }
  return [];
}

/** Colour by what the feature is. Shape and a text label accompany it everywhere. */
export function colourFor(props: Record<string, unknown>): string {
  const kind = String(props.kind ?? "");
  const layer = String(props.source_layer ?? props.layer ?? "");
  if (layer === "detections") return "#d7263d";
  if (kind === "ndvi_decline") return "#f28f3b";
  if (kind === "scout_patch") return "#ffd166";
  if (layer === "prescription") {
    const rate = Number(props.rate ?? 0);
    return rate > 0 ? "#2a9d8f" : "#6c757d";
  }
  switch (props.layer) {
    case "field":
      return "#3879C1";
    case "zone":
      return "#00A6DC";
    case "weather_station":
      return "#1FAA92";
    case "soil_probe":
      return "#F4793B";
    default:
      return "#006EB0";
  }
}

/** A one-line description of a feature, for popups and the list view. */
export function describe(f: Feature): string {
  const p = (f.properties ?? {}) as Record<string, unknown>;
  const layer = String(p.source_layer ?? "");
  if (layer === "detections") {
    const conf = typeof p.confidence === "number" ? ` ${Math.round(p.confidence * 100)}%` : "";
    return `${p.label ?? "detection"}${conf}${p.ts ? ` · ${String(p.ts).slice(0, 16)}` : ""}`;
  }
  if (p.kind === "ndvi_decline") return `NDVI ${p.baseline} → ${p.latest} (${p.residual} vs field)`;
  if (p.kind === "scout_patch") return `Scout patch · ${p.area_ha} ha`;
  if (layer === "prescription") return `${p.rate} ${p.unit ?? ""}`.trim();
  return String(p.name ?? p.layer ?? f.id ?? "feature");
}

/**
 * Demo data carries fixed sample timestamps that would read as "just now". Drop `ts` and `created_at`
 * style fields from every feature so the demo map and its list never show a wall-clock time.
 */
export function stripTimestamps(fc: FeatureCollection | null | undefined): FeatureCollection | null {
  if (!fc) return null;
  return {
    ...fc,
    features: fc.features.map((f) => {
      const { ts: _ts, created_at: _createdAt, ...rest } = (f.properties ?? {}) as Record<string, unknown>;
      void _ts;
      void _createdAt;
      return { ...f, properties: rest };
    }),
  };
}
