"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { OpsEmptyState } from "@/components/ops/OpsEmptyState";
import { DemoTag, OpsPageHead } from "@/components/ops/OpsPageHead";
import { OpsMapLazy } from "@/components/ops/OpsMapLazy";
import { OpsScrubber, useScenarioClock } from "@/components/ops/OpsScrubber";
import { useOpsStatus } from "@/components/ops/OpsShell";
import type { Key } from "@/lib/i18n";
import {
  colourFor,
  describe,
  LAYER_IDS,
  mergeLayers,
  stripTimestamps,
  type LayerId,
  type LayerSources,
} from "@/lib/map-layers";
import { isDemo, opsGet } from "@/lib/ops-api";
import { detectionShowAt, pathAt, SCENARIO_TOTAL, surveyPath, type LatLng } from "@/lib/ops-scenario";
import type { FeatureCollection, FieldProfile } from "@/lib/ops-types";

const LAYER_LABEL: Record<LayerId, Key> = {
  farm: "map.fields",
  detections: "map.detections",
  satellite: "map.satellite",
  prescription: "map.prescription",
};

type WithGeo = { geojson?: FeatureCollection; simulation?: boolean };
type Features = { features?: FeatureCollection["features"]; simulation?: boolean; demo?: boolean };

function asCollection(data: Features | undefined): FeatureCollection | null {
  return data?.features ? { type: "FeatureCollection", features: data.features } : null;
}

/** [south, west, north, east] of a polygon boundary, or null. */
function boundaryBox(f: FieldProfile | undefined): [number, number, number, number] | null {
  const ring = f?.boundary?.coordinates?.[0];
  if (!ring || ring.length < 3) return null;
  const lngs = ring.map((p) => p[0]);
  const lats = ring.map((p) => p[1]);
  return [Math.min(...lats), Math.min(...lngs), Math.max(...lats), Math.max(...lngs)];
}

function OpsMapInner() {
  const { t } = useI18n();
  const params = useSearchParams();
  const rx = params.get("rx");
  const { offline, demo: shellDemo, refreshStatus } = useOpsStatus();
  const clock = useScenarioClock(params.get("t"));

  const [fields, setFields] = useState<FieldProfile[]>([]);
  const [chosenField, setChosenField] = useState<string>(params.get("field") ?? "");
  const [sources, setSources] = useState<LayerSources>({});
  const [visible, setVisible] = useState<Set<LayerId>>(
    () => new Set<LayerId>(rx ? ["farm", "prescription"] : ["farm", "detections", "satellite"]),
  );
  const [showFlight, setShowFlight] = useState(true);
  const [dataDemo, setDataDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // The satellite layer needs a field with a boundary: the one asked for, else the first.
  const fieldId = chosenField || fields[0]?.field_id || "";

  const loadBase = useCallback(async () => {
    setLoading(true);
    const [farm, det, fl, presc] = await Promise.all([
      opsGet<Features>("map/geojson"),
      opsGet<Features>("map/detections"),
      opsGet<{ fields: FieldProfile[]; simulation?: boolean }>("fields"),
      rx ? opsGet<WithGeo>(`prescriptions/${encodeURIComponent(rx)}`) : Promise.resolve(null),
    ]);
    setError(farm.ok ? null : farm.error);
    setDataDemo(farm.ok && isDemo(farm.data));
    setFields(fl.ok ? (fl.data.fields ?? []).filter((f) => f.boundary) : []);
    setSources((prev) => ({
      ...prev,
      farm: farm.ok ? asCollection(farm.data) : null,
      detections: det.ok ? asCollection(det.data) : null,
      prescription: presc?.ok ? (presc.data.geojson ?? null) : null,
    }));
    setLoading(false);
    refreshStatus();
  }, [rx, refreshStatus]);

  const loadSatellite = useCallback(async () => {
    if (!fieldId) {
      setSources((prev) => ({ ...prev, satellite: null }));
      return;
    }
    const sat = await opsGet<WithGeo>(`satellite?field=${encodeURIComponent(fieldId)}`);
    setSources((prev) => ({ ...prev, satellite: sat.ok ? (sat.data.geojson ?? null) : null }));
  }, [fieldId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on mount
    void loadBase();
  }, [loadBase]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch when the field changes
    void loadSatellite();
  }, [loadSatellite]);

  // Demo only: the design's synthetic replay. Detections appear over synthetic time; a simulated aircraft
  // flies a drawn survey path inside the first field. With a live Ops API none of this is shown.
  const replayOn = shellDemo || dataDemo;
  const t0 = replayOn ? clock.t : SCENARIO_TOTAL;
  const shownSources = useMemo<LayerSources>(() => {
    if (!replayOn) return sources;
    const det = stripTimestamps(sources.detections);
    const n = det?.features.length ?? 0;
    return {
      ...sources,
      farm: stripTimestamps(sources.farm),
      satellite: stripTimestamps(sources.satellite),
      prescription: stripTimestamps(sources.prescription),
      detections: det
        ? { ...det, features: det.features.filter((_, i) => detectionShowAt(i, n) <= t0) }
        : det,
    };
  }, [sources, replayOn, t0]);

  const merged = useMemo(() => mergeLayers(shownSources, visible), [shownSources, visible]);
  const hasAny = merged.features.length > 0;
  const detCount = visible.has("detections") ? (shownSources.detections?.features.length ?? 0) : 0;

  const flightPath = useMemo<LatLng[] | null>(() => {
    if (!replayOn) return null;
    const box = boundaryBox(fields.find((f) => f.field_id === fieldId) ?? fields[0]);
    return box ? surveyPath(box) : null;
  }, [replayOn, fields, fieldId]);
  const flown = useMemo(
    () => (flightPath ? pathAt(flightPath, t0 / SCENARIO_TOTAL) : { point: null, upTo: [] as LatLng[] }),
    [flightPath, t0],
  );

  function toggle(id: LayerId) {
    setVisible((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const label = (id: LayerId) => (id === "detections" && replayOn ? t("d.kc6493b46") : t(LAYER_LABEL[id]));
  const swatch = (id: LayerId) =>
    colourFor({ source_layer: id, layer: id === "farm" ? "field" : id, kind: id === "satellite" ? "ndvi_decline" : undefined, rate: 1 });

  return (
    <>
      <OpsPageHead title={t("nav.map")} sub={replayOn ? t("d.k244a57c1") : t("map.sub")}>
        <button
          type="button"
          className="btn-sm"
          onClick={() => {
            void loadBase();
            void loadSatellite();
          }}
        >
          {t("common.refresh")}
        </button>
      </OpsPageHead>

      {loading ? <p className="muted cap" style={{ marginBottom: 12 }}>{t("common.loading")}</p> : null}
      {(offline || error) && !hasAny ? (
        <div style={{ marginBottom: 16 }}>
          <OpsEmptyState title={t("map.title")} detail={error ? t("common.error", { error }) : t("shell.unreachable")} />
        </div>
      ) : null}

      {replayOn ? (
        <OpsScrubber t={clock.t} playing={clock.playing} onToggle={clock.toggle} onSeek={clock.seek} />
      ) : null}

      <div className="maplayout">
        <div>
          <div className="mapwrap">
            <div className="leaflet-wrap">
              <OpsMapLazy
                geojson={merged}
                className="h-full w-full"
                flightLine={replayOn && showFlight ? flightPath : null}
                flightProgress={replayOn && showFlight ? flown.upTo : null}
                aircraft={replayOn && showFlight ? flown.point : null}
              />
            </div>
            {replayOn ? <div className="mapnote">{t("map.noteDemo")}</div> : null}
          </div>
          <div className="legend">
            {LAYER_IDS.filter((id) => visible.has(id)).map((id) => (
              <span key={id}>
                <span className="sw" aria-hidden="true" style={{ background: swatch(id) }} />
                <span>{label(id)}</span>
              </span>
            ))}
            {replayOn && showFlight ? (
              <>
                <span>
                  <i style={{ borderColor: "var(--ae-blue-mid)" }} aria-hidden="true" />
                  <span>{t("d.k0fc842f8")}</span>
                </span>
                <span>
                  <svg width="14" height="14" aria-hidden="true">
                    <circle cx="7" cy="7" r="5" fill="#006EB0" />
                  </svg>
                  <span>{t("d.k4dacb97d")}</span>
                </span>
              </>
            ) : null}
          </div>
        </div>

        <div className="stack">
          <div className="lp">
            <h2>{t("d.k32806db2")}</h2>
            {LAYER_IDS.map((id) => {
              const count = shownSources[id]?.features?.length ?? 0;
              return (
                <label key={id}>
                  <input type="checkbox" checked={visible.has(id)} onChange={() => toggle(id)} />
                  <span>
                    {label(id)} ({count})
                  </span>
                </label>
              );
            })}
            {replayOn ? (
              <label>
                <input type="checkbox" checked={showFlight} onChange={() => setShowFlight((v) => !v)} />
                <span>{t("d.k0fc842f8")}</span>
              </label>
            ) : null}
            {fields.length ? (
              <>
                <span className="fl">{t("map.selectField")}</span>
                <select
                  aria-label={t("map.selectField")}
                  value={fieldId}
                  onChange={(e) => setChosenField(e.target.value)}
                >
                  {fields.map((f) => (
                    <option key={f.field_id} value={f.field_id}>
                      {f.name || f.field_id}
                    </option>
                  ))}
                </select>
              </>
            ) : null}
          </div>

          <div className="panel">
            <header>
              <h2>{t("d.kf7af5cf1")}</h2>
              {replayOn ? <DemoTag label={t("d.kabe8a16e")} /> : null}
            </header>
            <div className="pb">
              <div className="kv">
                <div>{t("d.k07208aa3")}</div>
                <div className="mono">{detCount}</div>
                <div>{t("d.k806ef808")}</div>
                <div>{replayOn ? t("d.k4445a7cd") : t("map.srcLive")}</div>
                {replayOn ? (
                  <>
                    <div>{t("d.k2578b0c4")}</div>
                    <div>{t("d.kdadc3988")}</div>
                  </>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* The same features as text: for keyboard and screen-reader users, and small screens. */}
      <details className="panel" style={{ marginTop: 16 }}>
        <summary style={{ cursor: "pointer", padding: "12px 16px", font: "600 14px/20px var(--ae-font)", color: "var(--ae-navy)" }}>
          {t("map.list")} ({merged.features.length})
        </summary>
        <ul style={{ maxHeight: 320, overflowY: "auto", padding: "0 16px 12px", fontSize: 14 }}>
          {merged.features.length === 0 ? <li className="muted">{t("common.none")}</li> : null}
          {merged.features.slice(0, 500).map((f) => {
            const layer = (f.properties?.source_layer as LayerId | undefined) ?? "farm";
            return (
              <li key={String(f.id)} style={{ borderBottom: "1px solid var(--ae-border)", padding: "4px 0" }}>
                <span className="muted">{label(layer)}:</span> {describe(f)}
                {replayOn ? (
                  <>
                    {" "}
                    <DemoTag label={t("d.kabe8a16e")} />
                  </>
                ) : null}
              </li>
            );
          })}
        </ul>
      </details>
    </>
  );
}

export default function OpsMapPage() {
  return (
    <Suspense fallback={null}>
      <OpsMapInner />
    </Suspense>
  );
}
