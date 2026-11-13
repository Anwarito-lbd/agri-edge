"use client";

import dynamic from "next/dynamic";
import { useI18n } from "@/components/I18nProvider";
import type { FeatureCollection } from "@/lib/ops-types";

function MapLoading() {
  const { t } = useI18n();
  return (
    <div className="flex h-full min-h-[22rem] w-full items-center justify-center bg-ops-slate text-sm text-white/50">
      {t("map.loading")}
    </div>
  );
}

const OpsMapInner = dynamic(
  () => import("./OpsMap").then((m) => m.OpsMap),
  {
    ssr: false,
    loading: () => <MapLoading />,
  },
);

type LatLngTuple = [number, number];

export function OpsMapLazy({
  geojson,
  className = "",
  flightLine = null,
  flightProgress = null,
  aircraft = null,
}: {
  geojson: FeatureCollection | null;
  className?: string;
  flightLine?: LatLngTuple[] | null;
  flightProgress?: LatLngTuple[] | null;
  aircraft?: LatLngTuple | null;
}) {
  return (
    <OpsMapInner
      geojson={geojson}
      className={className}
      flightLine={flightLine}
      flightProgress={flightProgress}
      aircraft={aircraft}
    />
  );
}
