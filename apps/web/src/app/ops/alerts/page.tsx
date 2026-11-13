"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { OpsEmptyState } from "@/components/ops/OpsEmptyState";
import { DemoTag, OpsPageHead, ReadOnlyTag } from "@/components/ops/OpsPageHead";
import { useOpsStatus } from "@/components/ops/OpsShell";
import type { Key } from "@/lib/i18n";
import { SEVERITY_LABEL, severityClass, type SeverityClass } from "@/lib/ops-severity";
import { opsGet, opsPost } from "@/lib/ops-api";
import type { AlertRow, AlertsResponse } from "@/lib/ops-types";

type Action = "ack" | "resolve" | "escalate";

// Which actions each state allows -- the same table the ops API enforces
// (agri_edge/ops/alerts.py _ALLOWED). RESOLVED is terminal.
const ALLOWED: Record<string, Action[]> = {
  OPEN: ["ack", "escalate", "resolve"],
  ACKNOWLEDGED: ["escalate", "resolve"],
  ESCALATED: ["ack", "resolve"],
};

const STATE_LABEL: Record<string, Key> = {
  OPEN: "d.kb11fe66a",
  ACKNOWLEDGED: "d.k5e0f5b04",
  RESOLVED: "d.k3a01fc2b",
  ESCALATED: "alerts.stateEscalated",
};

type Filter = "all" | "critical" | "warn" | "ok";

const FILTERS: { id: Filter; label: Key }[] = [
  { id: "all", label: "d.k104897d8" },
  { id: "critical", label: "d.k3fa080c5" },
  { id: "warn", label: "d.k67574d22" },
  { id: "ok", label: "d.k6d9dc464" },
];

export default function OpsAlertsPage() {
  const { t } = useI18n();
  const { offline, demo: shellDemo, refreshStatus } = useOpsStatus();
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [dataDemo, setDataDemo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  const load = useCallback(async () => {
    setLoading(true);
    const result = await opsGet<AlertsResponse>("alerts");
    if (!result.ok) {
      setError(result.error);
      setAlerts(result.data?.alerts ?? []);
      setDataDemo(result.data?.demo === true);
    } else {
      setError(null);
      setAlerts(result.data.alerts ?? []);
      setDataDemo(result.data.demo === true);
    }
    setLoading(false);
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on mount
    void load();
  }, [load]);

  async function act(alertId: string, action: Action) {
    setBusy(alertId);
    setMsg(null);
    // No `by`: the ops API records the logged-in person from the session.
    const result = await opsPost<AlertRow>(`alerts/${action}`, { alert_id: alertId });
    const label = t(`alerts.${action}`);
    if (!result.ok) {
      setMsg(result.forbidden ? t("common.forbidden", { error: result.error }) : t("common.error", { error: result.error }));
    } else {
      setMsg(t("alerts.done", { action: label, id: alertId }));
      await load();
    }
    setBusy(null);
  }

  const demo = shellDemo || dataDemo;
  // Demo mode is read-only: the sample API refuses writes, so no write buttons are shown at all.
  const canAct = !demo && !offline;

  const counts = useMemo(() => {
    const c: Record<Filter, number> = { all: alerts.length, critical: 0, warn: 0, ok: 0 };
    for (const a of alerts) {
      const cls: SeverityClass = severityClass(a.severity);
      if (cls !== "neutral") c[cls] += 1;
    }
    return c;
  }, [alerts]);
  const rows = alerts.filter((a) => filter === "all" || severityClass(a.severity) === filter);

  return (
    <>
      <OpsPageHead title={t("nav.alerts")} sub={demo ? t("d.kaf3f71ea") : t("alerts.sub")}>
        {demo ? <ReadOnlyTag label={t("d.kc28f7f1e")} /> : null}
        <button type="button" className="btn-sm" onClick={() => void load()}>
          {t("common.refresh")}
        </button>
      </OpsPageHead>

      {loading && alerts.length === 0 ? <p className="muted cap" style={{ marginBottom: 12 }}>{t("common.loading")}</p> : null}
      {offline || error ? (
        <div style={{ marginBottom: 16 }}>
          <OpsEmptyState title={t("alerts.title")} detail={error ? t("common.error", { error }) : t("shell.unreachable")} />
        </div>
      ) : null}
      {msg ? (
        <p className="msg" role="status">
          {msg}
        </p>
      ) : null}

      <div className="filters" role="group" aria-label={t("d.k22675d7d")}>
        {FILTERS.map((f) => (
          <button key={f.id} type="button" className="fchip" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
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
                <th>{t("d.k182ece25")}</th>
                <th>{t("d.k806ef808")}</th>
                <th>{t("d.k70a32534")}</th>
                <th>{t("d.ke4d85eec")}</th>
                <th>{t("d.ke0c8cdf1")}</th>
                {canAct ? <th>{t("alerts.action")}</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => {
                const actions = ALLOWED[a.state ?? ""] ?? [];
                const by = (a.ack_by as string | undefined) || (a.resolved_by as string | undefined);
                const cls = severityClass(a.severity);
                const stateKey = STATE_LABEL[(a.state ?? "").toUpperCase()];
                const when = a.created_at ?? a.ts;
                return (
                  <tr key={a.alert_id}>
                    <td className="id">{a.alert_id}</td>
                    <td>
                      {a.title || a.alert_id}
                      {a.message ? <span className="sub">{a.message}</span> : null}
                    </td>
                    <td>{a.category ?? "—"}</td>
                    {/* Severity as a word and a dot, never colour alone. */}
                    <td>
                      <span className={`badge ${cls}`}>{cls === "neutral" ? (a.severity ?? "—") : t(SEVERITY_LABEL[cls])}</span>
                    </td>
                    <td>
                      {stateKey ? t(stateKey) : (a.state ?? "—")}
                      {by ? <span className="sub">{t("alerts.by", { name: by })}</span> : null}
                    </td>
                    <td className="id">
                      {demo ? <DemoTag label={t("live.demoData")} /> : when ? when : "—"}
                    </td>
                    {canAct ? (
                      <td>
                        <div className="acts-cell">
                          {actions.length
                            ? actions.map((action) => (
                                <button
                                  key={action}
                                  type="button"
                                  className="btn-sm"
                                  disabled={busy === a.alert_id}
                                  onClick={() => void act(a.alert_id, action)}
                                >
                                  {t(`alerts.${action}`)}
                                </button>
                              ))
                            : "—"}
                        </div>
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {alerts.length === 0 && !loading ? <div className="empty">{t("alerts.empty")}</div> : null}
          {alerts.length > 0 && rows.length === 0 ? <div className="empty">{t("d.k82296f97")}</div> : null}
        </div>
      </div>

      <p className="note">{demo ? `${t("d.kf21f3d1b")} ${t("alerts.demoReadOnly")}` : t("alerts.liveNote")}</p>
    </>
  );
}
