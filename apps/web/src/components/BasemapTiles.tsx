"use client";

import { useRef, useState } from "react";
import { TileLayer } from "react-leaflet";

import { useI18n } from "@/components/I18nProvider";
import {
  BASEMAP_ATTRIBUTION,
  BASEMAP_MAX_ZOOM,
  BASEMAP_URL,
  TILE_FAILURE_THRESHOLD,
} from "@/lib/basemap";

/**
 * The basemap, and what the map does when it cannot load.
 *
 * If several tiles fail and none has loaded, the map keeps its neutral
 * background and the drawn features, and says so in a note. It does not stay
 * silently blank. Render inside a <MapContainer>.
 */
export function BasemapTiles() {
  const { t } = useI18n();
  const failed = useRef(0);
  const loaded = useRef(0);
  const [down, setDown] = useState(false);

  return (
    <>
      <TileLayer
        url={BASEMAP_URL}
        attribution={BASEMAP_ATTRIBUTION}
        maxZoom={BASEMAP_MAX_ZOOM}
        eventHandlers={{
          tileload: () => {
            loaded.current += 1;
            failed.current = 0;
            setDown(false);
          },
          tileerror: () => {
            failed.current += 1;
            if (loaded.current === 0 && failed.current >= TILE_FAILURE_THRESHOLD) setDown(true);
          },
        }}
      />
      {down ? (
        <div
          role="status"
          className="absolute bottom-6 left-3 z-[1000] max-w-[16rem] border border-border bg-white/95 px-3 py-2 text-xs text-ink shadow-sm"
        >
          {t("map.tilesDown")}
        </div>
      ) : null}
    </>
  );
}
