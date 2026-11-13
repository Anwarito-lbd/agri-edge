"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { OpsEmptyState } from "@/components/ops/OpsEmptyState";
import { DemoTag, OpsPageHead } from "@/components/ops/OpsPageHead";
import { useOpsStatus } from "@/components/ops/OpsShell";
import type { Key } from "@/lib/i18n";
import { opsGet } from "@/lib/ops-api";
import { deviceState, type SensorState } from "@/lib/ops-sensors";
import type { DeviceRow, SensorsResponse, SoilRow } from "@/lib/ops-types";

type Filter = "all" | SensorState;

const STATE_LABEL: Record<SensorState, Key> = {
  ok: "d.k5f4e763d",
  warn: "sn.lowBattery",
  critical: "d.k782389b8",
};

const FILTERS: { id: Filter; label: Key }[] = [
  { id: "all", label: "d.k2cc731a3" },
  { id: "ok", label: "d.kd8a985e8" },
  { id: "warn", label: "sn.lowBattery" },
  { id: "critical", label: "d.k8a03ce9f" },
];

function prettyType(s: string) {
  return s.replace(/_/g, " ");
}

/** Demo rows carry fixed sample timestamps; drop them from raw payload dumps so nothing looks live. */
function withoutTime(row: Record<string, unknown>): Record<string, unknown> {
  const { ts: _ts, created_at: _created, ...rest } = row;
  void _ts;
  void _created;
  return rest;
}

export default function OpsSensorsPage() {
  const { t } = useI18n();
  const { offline, demo: shellDemo, refreshStatus } = useOpsStatus();
  const [data, setData] = useState<SensorsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");

  const load = useCallback(async () => {
    setLoading(true);
    const result = await opsGet<SensorsResponse>("sensors");
    if (!result.ok) {
      setError(result.error);
      setData(result.data ?? null);
    } else {
      setError(null);
      setData(result.data);
    }
    setLoading(false);
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on mount
    void load();
  }, [load]);

  const demo = shellDemo || data?.demo === true;
  const soil = useMemo<SoilRow[]>(() => data?.soil ?? [], [data]);
  const readings = data?.readings ?? [];
  const devices = useMemo<DeviceRow[]>(() => data?.devices ?? [], [data]);
  const tag = t("d.kabe8a16e");

  const counts = useMemo(() => {
    const c = { all: devices.length, ok: 0, warn: 0, critical: 0 };
    for (const d of devices) c[deviceState(d)] += 1;
    return c;
  }, [devices]);

  const rows = devices.filter((d) => filter === "all" || deviceState(d) === filter);

  // Latest reading per device: the shallowest depth we have.
  const readingFor = (id: string): SoilRow | undefined =>
    soil
      .filter((s) => s.device_id === id && typeof s.moisture_pct === "number")
      .sort((a, b) => (a.depth_cm ?? 0) - (b.depth_cm ?? 0))[0];

  const lastSeen = devices.map((d) => d.last_seen).filter((s): s is string => !!s).sort().pop();

  return (
    <>
      <OpsPageHead title={t("nav.sensors")} sub={demo ? t("d.k817526c4") : t("sn.title")}>
        <button type="button" className="btn-sm" onClick={() => void load()}>
          {t("common.refresh")}
        </button>
      </OpsPageHead>

      {loading && !data ? <p className="muted cap" style={{ marginBottom: 12 }}>{t("sn.loading")}</p> : null}
      {offline || error ? (
        <div style={{ marginBottom: 16 }}>
          <OpsEmptyState
            title={t("sn.unavailable")}
            detail={error ? t("sn.unavailableDetail", { error }) : t("shell.unreachable")}
          />
        </div>
      ) : null}

      <div className="kpis">
        <div className="kpi">
          <div className="l">{demo ? t("d.kd65e09b9") : t("sn.devices")}</div>
          <div className="v">{counts.all}</div>
          {demo ? (
            <div className="s">
              <DemoTag label={tag} />
              <span>{t("d.k4445a7cd")}</span>
            </div>
          ) : null}
        </div>
        {(
          [
            ["d.kd8a985e8", counts.ok],
            ["sn.lowBattery", counts.warn],
            ["d.k8a03ce9f", counts.critical],
          ] as [Key, number][]
        ).map(([label, n]) => (
          <div className="kpi" key={label}>
            <div className="l">{t(label)}</div>
            <div className="v">{n}</div>
            {demo ? (
              <div className="s">
                <DemoTag label={tag} />
              </div>
            ) : null}
          </div>
        ))}
        <div className="kpi">
          <div className="l">{t("d.k5937b6a6")}</div>
          {demo || !lastSeen ? (
            <>
              <div className="v dash">—</div>
              <div className="s">
                <span>{t("d.ke89eded2")}</span>
              </div>
            </>
          ) : (
            <div className="v" style={{ fontSize: 16, lineHeight: "24px" }}>{lastSeen}</div>
          )}
        </div>
      </div>

      <div className="filters" role="group" aria-label={t("d.k40f78093")}>
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className="fchip"
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
          >
            <span>{t(f.label)}</span>
            <span className="n">{counts[f.id]}</span>
          </button>
        ))}
      </div>

      <div className="panel">
        <div className="tw" tabIndex={0} role="region" aria-label={t("d.k4a98ef65")}>
          <table className="dt">
            <thead>
              <tr>
                <th>ID</th>
                <th>{t("d.k4bf77bbc")}</th>
                <th>{t("d.k5ccdaa50")}</th>
                <th>{t("d.k06a472cd")}</th>
                <th>{t("d.k73c6f7f2")}</th>
                <th className="n">{t("d.kcb16ec70")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => {
                const st = deviceState(d);
                const r = readingFor(d.device_id);
                return (
                  <tr key={d.device_id}>
                    <td>
                      <span className="id">{d.device_id}</span>
                      <span className="sub">{d.name}</span>
                    </td>
                    <td>{prettyType(d.device_type)}</td>
                    <td>{d.zone_id ?? "—"}</td>
                    <td>
                      <span className={`badge ${st}`}>{t(STATE_LABEL[st])}</span>
                    </td>
                    <td>{d.synthetic || demo ? <DemoTag label={tag} /> : "—"}</td>
                    <td className="n">
                      {r ? (
                        <>
                          {r.moisture_pct}
                          <span className="muted"> % · {r.depth_cm} cm</span>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {devices.length === 0 && !loading ? <div className="empty">{t("sn.noDevices")}</div> : null}
          {devices.length > 0 && rows.length === 0 ? <div className="empty">{t("d.k78d3563d")}</div> : null}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <header>
          <h2>{t("sn.soil")}</h2>
          {demo ? <DemoTag label={tag} /> : null}
        </header>
        <div className="tw" tabIndex={0} role="region" aria-label={t("d.k4a98ef65")}>
          <table className="dt">
            <thead>
              <tr>
                <th>{t("sn.deviceZone")}</th>
                <th className="n">{t("sn.depth")}</th>
                <th className="n">{t("sn.moisture")}</th>
                <th className="n">{t("sn.soilTemp")}</th>
                <th>{t("sn.quality")}</th>
                <th>{t("sn.synthetic")}</th>
              </tr>
            </thead>
            <tbody>
              {soil.length === 0 ? (
                <tr>
                  <td colSpan={6}>{t("sn.noSoil")}</td>
                </tr>
              ) : (
                soil.map((s, i) => (
                  <tr key={String(s.reading_id ?? i)}>
                    <td className="id">
                      {s.device_id ?? "—"}
                      {s.zone_id ? ` · ${s.zone_id}` : ""}
                    </td>
                    <td className="n">{s.depth_cm ?? "—"}</td>
                    <td className="n">{s.moisture_pct ?? "—"}</td>
                    <td className="n">{s.temp?.value_c != null ? s.temp.value_c.toFixed(1) : "—"}</td>
                    <td>{s.quality ?? "—"}</td>
                    <td>{s.synthetic ? <DemoTag label={tag} /> : "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <header>
          <h2>{t("sn.readings")}</h2>
          {demo ? <DemoTag label={tag} /> : null}
        </header>
        <div className="tw" tabIndex={0} role="region" aria-label={t("d.k4a98ef65")}>
          <table className="dt">
            <thead>
              <tr>
                <th>#</th>
                <th>{t("sn.payload")}</th>
              </tr>
            </thead>
            <tbody>
              {readings.length === 0 ? (
                <tr>
                  <td colSpan={2}>{t("sn.noReadings")}</td>
                </tr>
              ) : (
                readings.slice(0, 40).map((r, i) => {
                  const json = JSON.stringify(demo ? withoutTime(r) : r);
                  return (
                    <tr key={i}>
                      <td className="id">{i + 1}</td>
                      <td>
                        <code className="cap">
                          {json.slice(0, 200)}
                          {json.length > 200 ? "…" : ""}
                        </code>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {demo ? <p className="note">{t("sn.demoNote")}</p> : null}
    </>
  );
}
