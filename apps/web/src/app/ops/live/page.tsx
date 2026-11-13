"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { OpsEmptyState } from "@/components/ops/OpsEmptyState";
import { DemoTag, OpsPageHead, ReadOnlyTag } from "@/components/ops/OpsPageHead";
import { OpsScrubber, useScenarioClock } from "@/components/ops/OpsScrubber";
import { useOpsStatus } from "@/components/ops/OpsShell";
import { opsGet } from "@/lib/ops-api";
import {
  fmtT,
  SCENARIO_EVENTS,
  SCENARIO_TOTAL,
  seriesText,
  tracePoints,
  type SeriesKey,
} from "@/lib/ops-scenario";
import { SEVERITY_LABEL, severityClass } from "@/lib/ops-severity";
import type { LiveResponse } from "@/lib/ops-types";

const TELEMETRY: { key: SeriesKey; label: string; unit: string }[] = [
  { key: "alt", label: "d.kdaf4a9e5", unit: "m" },
  { key: "spd", label: "d.k6e5910ee", unit: "m/s" },
  { key: "hdg", label: "d.kedf2fd4f", unit: "deg" },
  { key: "bat", label: "d.k290140d2", unit: "%" },
  { key: "sat", label: "d.ke59d9119", unit: "" },
];

function OpsLiveInner() {
  const { t } = useI18n();
  const params = useSearchParams();
  const { offline, demo: shellDemo, refreshStatus } = useOpsStatus();
  const clock = useScenarioClock(params.get("t"));
  const [data, setData] = useState<LiveResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const result = await opsGet<LiveResponse>("live");
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
    void load();
    const id = setInterval(() => void load(), 15_000);
    return () => clearInterval(id);
  }, [load]);

  const demo = shellDemo || data?.demo === true;
  const devices = data?.devices ?? [];
  const health = data?.health ?? [];
  const alerts = data?.open_alerts ?? [];
  const tag = t("d.kabe8a16e");
  const cursorX = (640 * clock.t) / SCENARIO_TOTAL;

  return (
    <>
      <OpsPageHead title={t("nav.live")} sub={demo ? t("d.kf6af3236") : t("live.title")}>
        <ReadOnlyTag label={t("d.kc28f7f1e")} />
        <button type="button" className="btn-sm" onClick={() => void load()}>
          {t("common.refresh")}
        </button>
      </OpsPageHead>

      {loading && !data ? <p className="muted cap" style={{ marginBottom: 12 }}>{t("live.loading")}</p> : null}
      {offline || error ? (
        <div style={{ marginBottom: 16 }}>
          <OpsEmptyState
            title={t("live.offline")}
            detail={error ? t("live.offlineDetail", { error }) : undefined}
          />
        </div>
      ) : null}

      {demo ? (
        <>
          <OpsScrubber t={clock.t} playing={clock.playing} onToggle={clock.toggle} onSeek={clock.seek} />

          <div className="tele">
            {TELEMETRY.map((m) => (
              <div className="tcell" key={m.key}>
                <div className="l">
                  {t(m.label as "d.kdaf4a9e5")} · {tag}
                </div>
                <div className="v">
                  <span>{seriesText(m.key, clock.t)}</span>
                  <small>{m.unit}</small>
                </div>
              </div>
            ))}
            <div className="tcell">
              <div className="l">
                {t("d.k18f09380")} · {tag}
              </div>
              <div className="v">
                <span>AUTO</span>
              </div>
            </div>
          </div>

          <div className="two" style={{ marginBottom: 16 }}>
            <div className="panel">
              <header>
                <h2>{t("d.k860f6741")}</h2>
                <DemoTag label={t("d.k4445a7cd")} />
              </header>
              <div className="pb">
                <svg
                  viewBox="0 0 680 220"
                  style={{ width: "100%", height: "auto" }}
                  role="img"
                  aria-label={t("d.ke0836ea6")}
                >
                  <g stroke="#D5DDE5">
                    {[30, 70, 110, 150, 190].map((y) => (
                      <path key={y} d={`M20 ${y} H660`} />
                    ))}
                  </g>
                  <polyline points={tracePoints("alt")} fill="none" stroke="#006EB0" strokeWidth="2" />
                  <polyline points={tracePoints("spd")} fill="none" stroke="#173D68" strokeWidth="2" strokeDasharray="6 4" />
                  <g transform={`translate(${(20 + cursorX).toFixed(1)},0)`}>
                    <path d="M0 24V196" stroke="#1A2A38" strokeWidth="1.5" />
                    <rect x="-4" y="20" width="8" height="8" fill="#1A2A38" />
                  </g>
                  <g fontFamily="Inter,sans-serif" fontSize="12" fill="#5B6B7A">
                    <text x="20" y="214">t+00:00</text>
                    <text x="620" y="214">t+15:00</text>
                  </g>
                  <g fontFamily="Inter,sans-serif" fontSize="12" fontWeight="600">
                    <text x="30" y="16" fill="#006EB0">{t("d.kdaf4a9e5")} ({tag})</text>
                    <text x="190" y="16" fill="#173D68">{t("d.k6e5910ee")} ({tag})</text>
                  </g>
                </svg>
              </div>
            </div>

            <div className="panel">
              <header>
                <h2>{t("d.k8e1b92c0")}</h2>
                <ReadOnlyTag label={t("d.kc28f7f1e")} />
              </header>
              <div className="tw" tabIndex={0} role="region" aria-label={t("d.k4a98ef65")}>
                <table className="dt">
                  <tbody>
                    {SCENARIO_EVENTS.map((e) => {
                      const dim = e.at > clock.t;
                      const now = !dim && clock.t - e.at < 45;
                      return (
                        <tr key={e.at} className={dim ? "dim" : now ? "now" : undefined}>
                          <td className="id" style={{ width: 72 }}>{fmtT(e.at)}</td>
                          <td>{t(e.key as "d.k7e3c3499")}</td>
                          <td style={{ textAlign: "right" }}>
                            <span className={`badge ${e.level}`}>
                              {t(SEVERITY_LABEL[e.level])}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      ) : null}

      <div className="two" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,420px),1fr))" }}>
        <div className="panel">
          <header>
            <h2>{t("live.devices")}</h2>
            {demo ? <DemoTag label={tag} /> : null}
          </header>
          <div className="tw" tabIndex={0} role="region" aria-label={t("d.k4a98ef65")}>
            <table className="dt">
              <thead>
                <tr>
                  <th>{t("live.name")}</th>
                  <th>{t("live.type")}</th>
                  <th className="n">{t("live.battery")}</th>
                  <th>{t("live.lastSeen")}</th>
                </tr>
              </thead>
              <tbody>
                {devices.length === 0 ? (
                  <tr>
                    <td colSpan={4}>{t("live.noDevices")}</td>
                  </tr>
                ) : (
                  devices.map((d) => (
                    <tr key={d.device_id}>
                      <td>
                        {d.name}
                        <span className="sub id">{d.device_id}</span>
                      </td>
                      <td>{d.device_type}</td>
                      <td className="n">{typeof d.battery_pct === "number" ? `${d.battery_pct}%` : "—"}</td>
                      <td>
                        {demo ? <DemoTag label={t("live.demoData")} /> : (d.last_seen ?? "—")}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="panel">
          <header>
            <h2>{t("live.health")}</h2>
            {demo ? <DemoTag label={tag} /> : null}
          </header>
          <div className="tw" tabIndex={0} role="region" aria-label={t("d.k4a98ef65")}>
            <table className="dt">
              <thead>
                <tr>
                  <th>{t("live.device")}</th>
                  <th>{t("live.status")}</th>
                  <th className="n">{t("live.battery")}</th>
                  <th className="n">{t("live.signal")}</th>
                </tr>
              </thead>
              <tbody>
                {health.length === 0 ? (
                  <tr>
                    <td colSpan={4}>{t("live.noHealth")}</td>
                  </tr>
                ) : (
                  health.map((h, i) => {
                    const status = String(h.status ?? "—");
                    return (
                      <tr key={`${h.device_id}-${i}`}>
                        <td className="id">{h.device_id}</td>
                        <td>
                          <span className={`badge ${status === "OK" ? "ok" : status === "—" ? "neutral" : "warn"}`}>
                            {status}
                          </span>
                        </td>
                        <td className="n">{typeof h.battery_pct === "number" ? `${h.battery_pct}%` : "—"}</td>
                        <td className="n">{typeof h.signal_rssi === "number" ? h.signal_rssi : "—"}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <header>
          <h2>{t("live.openAlerts")}</h2>
          {demo ? <DemoTag label={tag} /> : null}
        </header>
        <div className="tw" tabIndex={0} role="region" aria-label={t("d.k4a98ef65")}>
          <table className="dt">
            <thead>
              <tr>
                <th>{t("live.severity")}</th>
                <th>{t("live.alertTitle")}</th>
                <th>{t("live.state")}</th>
                <th>{t("live.category")}</th>
              </tr>
            </thead>
            <tbody>
              {alerts.length === 0 ? (
                <tr>
                  <td colSpan={4}>{t("live.noAlerts")}</td>
                </tr>
              ) : (
                alerts.map((a) => {
                  const cls = severityClass(a.severity);
                  return (
                    <tr key={a.alert_id}>
                      <td>
                        <span className={`badge ${cls}`}>
                          {cls === "neutral" ? (a.severity ?? "—") : t(SEVERITY_LABEL[cls])}
                        </span>
                      </td>
                      <td>{a.title || a.message || a.alert_id}</td>
                      <td>{a.state ?? "—"}</td>
                      <td>{a.category ?? "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {data?.ts && !demo ? <p className="note cap">{t("live.snapshot", { ts: data.ts })}</p> : null}
      <p className="note">{t("d.k4ada8edb")}</p>
    </>
  );
}

export default function OpsLivePage() {
  return (
    <Suspense fallback={null}>
      <OpsLiveInner />
    </Suspense>
  );
}
