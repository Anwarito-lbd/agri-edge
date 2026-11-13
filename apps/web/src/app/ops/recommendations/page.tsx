"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { OpsEmptyState } from "@/components/ops/OpsEmptyState";
import { useOpsStatus } from "@/components/ops/OpsShell";
import type { Key } from "@/lib/i18n";
import { opsGet } from "@/lib/ops-api";
import type { Recommendation, RecommendationsResponse } from "@/lib/ops-types";

const GROUPS: { priority: 1 | 2 | 3; key: Key; tone: string }[] = [
  { priority: 1, key: "rec.p1", tone: "border-l-red-700" },
  { priority: 2, key: "rec.p2", tone: "border-l-amber-600" },
  { priority: 3, key: "rec.p3", tone: "border-l-slate-400" },
];

function RecCard({ r }: { r: Recommendation }) {
  const { t } = useI18n();
  return (
    <article className="card border border-border bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">
        {r.field_id} · {r.kind}
      </p>
      <h3 className="mt-1 text-base font-semibold text-ink">{r.title}</h3>
      <p className="mt-2 text-sm">{r.action}</p>
      {r.why.length ? (
        <details className="mt-2 text-sm" open={r.priority === 1}>
          <summary className="cursor-pointer font-medium">{t("rec.why")}</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {r.why.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      ) : null}
      {r.missing.length ? (
        <p className="mt-2 text-xs text-muted">
          <span className="font-semibold">{t("rec.notKnown")}:</span> {r.missing.join("; ")}
        </p>
      ) : null}
      <p className="mt-2 text-xs text-muted">
        {t("rec.confidence", { level: r.confidence })} · {t("rec.sources", { sources: r.sources.join(", ") || "—" })}
      </p>
      {r.kind === "scouting" ? (
        <Link className="mt-2 inline-block text-sm font-medium text-primary underline" href={`/ops/map?field=${encodeURIComponent(r.field_id)}`}>
          {t("rec.showOnMap")}
        </Link>
      ) : null}
    </article>
  );
}

export default function RecommendationsPage() {
  const { t } = useI18n();
  const { offline, refreshStatus } = useOpsStatus();
  const [recs, setRecs] = useState<Recommendation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await opsGet<RecommendationsResponse>("recommendations");
    if (res.ok) {
      setRecs(res.data.recommendations ?? []);
      setError(null);
    } else {
      setError(res.error);
    }
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on mount
    void load();
  }, [load]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="section-title text-xl sm:text-2xl">{t("rec.title")}</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted">{t("rec.intro")}</p>
        </div>
        <button type="button" className="btn-secondary text-sm" onClick={() => void load()}>
          {t("common.refresh")}
        </button>
      </div>
      {error && !recs ? <OpsEmptyState title={t("rec.title")} detail={t("common.error", { error })} /> : null}
      {recs === null && !error && !offline ? <p className="text-sm text-muted">{t("common.loading")}</p> : null}
      {recs && recs.length === 0 ? <p className="text-sm text-muted">{t("rec.empty")}</p> : null}
      {recs
        ? GROUPS.map((g) => {
            const items = recs.filter((r) => r.priority === g.priority);
            if (!items.length) return null;
            return (
              <section key={g.priority} aria-labelledby={`p${g.priority}`} className={`border-l-4 pl-3 ${g.tone}`}>
                <h3 id={`p${g.priority}`} className="mb-2 text-sm font-bold uppercase tracking-wide">
                  {t(g.key)} ({items.length})
                </h3>
                <div className="grid gap-3 md:grid-cols-2">
                  {items.map((r, i) => (
                    <RecCard key={`${r.field_id}-${r.kind}-${i}`} r={r} />
                  ))}
                </div>
              </section>
            );
          })
        : null}
    </div>
  );
}
