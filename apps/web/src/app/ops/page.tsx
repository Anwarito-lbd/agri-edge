"use client";

import { useCallback, useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { opsGet } from "@/lib/ops-api";
import type { OverviewResponse } from "@/lib/ops-types";
import { OpsEmptyState } from "@/components/ops/OpsEmptyState";
import { useOpsStatus } from "@/components/ops/OpsShell";

export default function OpsOverviewPage() {
  const { t } = useI18n();
  const { offline, demo, refreshStatus } = useOpsStatus();
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const result = await opsGet<OverviewResponse>("overview");
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
  }, [load]);

  const cards = [
    { label: t("ov.devices"), value: data?.device_count },
    { label: t("ov.weatherObs"), value: data?.weather_count },
    { label: t("ov.soil"), value: data?.soil_count },
    { label: t("ov.openAlerts"), value: data?.open_alerts },
    { label: t("ov.layersOn"), value: data?.map_layers_enabled },
    { label: t("ov.tasks"), value: data?.tasks_open },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">{t("ov.eyebrow")}</p>
          <h1 className="section-title mt-1 text-xl sm:text-2xl">
            {t("ov.title")}
          </h1>
        </div>
        <button type="button" className="btn-secondary text-sm" onClick={() => void load()}>
          {t("common.refresh")}
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-muted">{t("ov.loading")}</p>
      ) : offline || error ? (
        <OpsEmptyState
          title={t("ov.unreachable")}
          detail={error ? t("ov.blank", { error }) : undefined}
        />
      ) : null}

      <div className="kpis k6">
        {cards.map((c) => (
          <div key={c.label} className="kpi">
            <div className="l">{c.label}</div>
            <div className={`v${typeof c.value === "number" ? "" : " dash"}`}>
              {typeof c.value === "number" ? c.value : "—"}
            </div>
            {demo && typeof c.value === "number" ? (
              <div className="s">
                <span className="tag-demo">{t("common.demo")}</span>
              </div>
            ) : null}
          </div>
        ))}
      </div>

      {data?.ts && !demo ? (
        <p className="text-xs text-muted">
          {t("ov.last")} · <time dateTime={data.ts}>{data.ts}</time>
        </p>
      ) : null}

      <div className="notice">{t("ov.notice")}</div>
    </div>
  );
}
