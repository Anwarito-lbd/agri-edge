"use client";

import { useEffect, useMemo } from "react";
import {
  MapContainer,
  Popup,
  Polygon,
  CircleMarker,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import { BasemapTiles } from "@/components/BasemapTiles";
import {
  DEMO_DETECTIONS,
  DEMO_FIELD_POLYGON,
  DEMO_MAP_CENTER,
  DEMO_WEED_POLYGON,
  type DemoDetection,
} from "@/lib/demo-geo";

function kindColor(kind: DemoDetection["kind"]) {
  switch (kind) {
    case "weed":
      return "#F4793B";
    case "livestock":
      return "#006EB0";
    case "vigour":
      return "#00A6DC";
  }
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    const bounds = L.latLngBounds(points.map(([lat, lng]) => [lat, lng]));
    map.fitBounds(bounds.pad(0.18), { animate: false });
  }, [map, points]);
  return null;
}

export function DemoMap({ className = "" }: { className?: string }) {
  const fitPoints = useMemo(() => {
    const pts: [number, number][] = DEMO_DETECTIONS.map((d) => [d.lat, d.lng]);
    DEMO_FIELD_POLYGON.forEach((p) => pts.push(p));
    return pts;
  }, []);

  return (
    <div className={`relative h-full w-full ${className}`}>
      <MapContainer
        center={DEMO_MAP_CENTER}
        zoom={12}
        scrollWheelZoom={false}
        className="demo-map h-full min-h-[22rem] w-full"
        attributionControl
        style={{ height: "100%", width: "100%" }}
      >
        <BasemapTiles />
        <FitBounds points={fitPoints} />
        <Polygon
          positions={DEMO_FIELD_POLYGON}
          pathOptions={{
            color: "#3879C1",
            weight: 1.5,
            fillColor: "#225FA3",
            fillOpacity: 0.18,
          }}
        >
          <Popup>
            <strong>NW quarter — canola</strong>
            <br />
            Field boundary · Demo
          </Popup>
        </Polygon>
        <Polygon
          positions={DEMO_WEED_POLYGON}
          pathOptions={{
            color: "#F4793B",
            weight: 1.5,
            fillColor: "#F4793B",
            fillOpacity: 0.22,
            dashArray: "4 3",
          }}
        >
          <Popup>
            <strong>Weed patch polygon</strong>
            <br />
            Geo detection · Demo
          </Popup>
        </Polygon>
        {DEMO_DETECTIONS.map((d) => (
          <CircleMarker
            key={d.id}
            center={[d.lat, d.lng]}
            radius={8}
            pathOptions={{
              color: "#0B101C",
              weight: 1,
              fillColor: kindColor(d.kind),
              fillOpacity: 0.95,
            }}
          >
            <Popup>
              <strong>
                {d.id} · {d.label}
              </strong>
              <br />
              {d.note}
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}
