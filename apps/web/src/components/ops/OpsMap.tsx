"use client";

import { useEffect, useMemo } from "react";
import {
  MapContainer,
  Popup,
  Polygon,
  Polyline,
  CircleMarker,
  useMap,
} from "react-leaflet";
import L, { type LatLngExpression } from "leaflet";
import { BasemapTiles } from "@/components/BasemapTiles";
import { useI18n } from "@/components/I18nProvider";
import { colourFor, describe, polygonsOf } from "@/lib/map-layers";
import type { Feature, FeatureCollection, Geometry } from "@/lib/ops-types";

type OpsFeatureProps = {
  name?: string;
  layer?: string;
  device_type?: string;
  synthetic?: boolean;
  [key: string]: unknown;
};

function FitGeo({ features }: { features: Feature[] }) {
  const map = useMap();
  useEffect(() => {
    const pts: [number, number][] = [];
    for (const f of features) {
      const g = f.geometry;
      if (!g) continue;
      if (g.type === "Point" && Array.isArray(g.coordinates)) {
        const [lng, lat] = g.coordinates as [number, number];
        pts.push([lat, lng]);
      } else if (g.type === "Polygon" && Array.isArray(g.coordinates)) {
        for (const ring of g.coordinates as [number, number][][]) {
          for (const [lng, lat] of ring) pts.push([lat, lng]);
        }
      } else if (g.type === "MultiPolygon" && Array.isArray(g.coordinates)) {
        for (const poly of g.coordinates as [number, number][][][]) {
          for (const ring of poly) {
            for (const [lng, lat] of ring) pts.push([lat, lng]);
          }
        }
      }
    }
    if (!pts.length) {
      map.setView([45.405, -75.695], 14, { animate: false });
      return;
    }
    const bounds = L.latLngBounds(pts.map(([lat, lng]) => [lat, lng]));
    map.fitBounds(bounds.pad(0.2), { animate: false });
  }, [map, features]);
  return null;
}

export type LatLngTuple = [number, number];

export function OpsMap({
  geojson,
  className = "",
  flightLine = null,
  flightProgress = null,
  aircraft = null,
}: {
  geojson: FeatureCollection | null;
  className?: string;
  /** Demo only: the simulated survey path, its flown part, and the simulated aircraft position (lat, lng). */
  flightLine?: LatLngTuple[] | null;
  flightProgress?: LatLngTuple[] | null;
  aircraft?: LatLngTuple | null;
}) {
  const { t } = useI18n();
  const features = useMemo(() => geojson?.features ?? [], [geojson]);

  const polygons = useMemo(
    () =>
      features.filter(
        (f) =>
          f.geometry?.type === "Polygon" || f.geometry?.type === "MultiPolygon",
      ),
    [features],
  );
  const points = useMemo(
    () => features.filter((f) => f.geometry?.type === "Point"),
    [features],
  );

  return (
    <div className={`relative h-full w-full ${className}`}>
      <MapContainer
        center={[45.405, -75.695]}
        zoom={14}
        scrollWheelZoom
        className="demo-map h-full min-h-[22rem] w-full"
        attributionControl
        style={{ height: "100%", width: "100%" }}
      >
        <BasemapTiles />
        <FitGeo features={features} />

        {polygons.flatMap((f, i) => {
          const props = (f.properties || {}) as OpsFeatureProps;
          const color = colourFor(props);
          const scout = props.kind === "scout_patch";
          return polygonsOf(f.geometry as Geometry).map((rings, j) => {
            const positions = rings.map((ring) =>
              ring.map(([lng, lat]) => [lat, lng] as [number, number]),
            ) as LatLngExpression[][];
            return (
              <Polygon
                key={`${String(f.id ?? `poly-${i}`)}-${j}`}
                positions={positions}
                pathOptions={{
                  color,
                  weight: scout ? 3 : 1.5,
                  dashArray: scout ? "6 4" : undefined,
                  fillColor: color,
                  fillOpacity: scout ? 0.05 : 0.25,
                }}
              >
                <Popup>
                  <strong>{describe(f)}</strong>
                  {props.synthetic ? ` · ${t("map.synthetic")}` : ""}
                </Popup>
              </Polygon>
            );
          });
        })}

        {points.map((f, i) => {
          const props = (f.properties || {}) as OpsFeatureProps;
          const geom = f.geometry as Geometry;
          if (geom.type !== "Point" || !Array.isArray(geom.coordinates)) {
            return null;
          }
          const [lng, lat] = geom.coordinates as [number, number];
          const color = colourFor({ ...props, layer: props.layer || props.device_type });
          return (
            <CircleMarker
              key={String(f.id ?? `pt-${i}`)}
              center={[lat, lng]}
              radius={8}
              pathOptions={{
                color: "#0B101C",
                weight: 1,
                fillColor: color,
                fillOpacity: 0.95,
              }}
            >
              <Popup>
                <strong>{describe(f)}</strong>
                {props.synthetic ? ` · ${t("map.synthetic")}` : ""}
              </Popup>
            </CircleMarker>
          );
        })}
        {flightLine && flightLine.length > 1 ? (
          <Polyline positions={flightLine} pathOptions={{ color: "#B9C9DA", weight: 2 }} />
        ) : null}
        {flightProgress && flightProgress.length > 1 ? (
          <Polyline positions={flightProgress} pathOptions={{ color: "#225FA3", weight: 3 }} />
        ) : null}
        {aircraft ? (
          <CircleMarker
            center={aircraft}
            radius={8}
            pathOptions={{ color: "#fff", weight: 2.5, fillColor: "#006EB0", fillOpacity: 1 }}
          >
            <Popup>
              <strong>{t("d.k4dacb97d")}</strong> · {t("map.synthetic")}
            </Popup>
          </CircleMarker>
        ) : null}
      </MapContainer>
    </div>
  );
}
