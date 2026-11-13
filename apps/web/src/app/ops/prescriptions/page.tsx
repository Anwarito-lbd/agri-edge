"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useI18n } from "@/components/I18nProvider";
import { useOpsStatus } from "@/components/ops/OpsShell";
import { opsGet, opsPost } from "@/lib/ops-api";
import type { FieldProfile, PrescriptionSummary } from "@/lib/ops-types";

export default function PrescriptionsPage() {
  const { t } = useI18n();
  const { refreshStatus } = useOpsStatus();
  const [rxs, setRxs] = useState<PrescriptionSummary[]>([]);
  const [fields, setFields] = useState<FieldProfile[]>([]);
  const [source, setSource] = useState<"detections" | "satellite">("detections");
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [r, f] = await Promise.all([
      opsGet<{ prescriptions?: PrescriptionSummary[]; simulation?: boolean }>("prescriptions"),
      opsGet<{ fields?: FieldProfile[]; simulation?: boolean }>("fields"),
    ]);
    if (r.ok) setRxs(r.data.prescriptions ?? []);
    if (f.ok) setFields((f.data.fields ?? []).filter((x) => x.boundary));
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on mount
    void load();
  }, [load]);

  function explain(res: { error: string; forbidden?: boolean }) {
    return res.forbidden ? t("common.forbidden", { error: res.error }) : t("common.error", { error: res.error });
  }

  async function build(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const body: Record<string, unknown> = {
      field_id: f.get("field_id"),
      source,
      product: f.get("product"),
      unit: f.get("unit"),
    };
    if (source === "detections") body.rate = Number(f.get("rate"));
    else body.rates_by_zone = String(f.get("rates")).split(",").map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x));
    const res = await opsPost<PrescriptionSummary & { simulation?: boolean }>("prescriptions", body);
    setMsg(res.ok ? `${res.data.prescription_id}` : explain(res));
    await load();
  }

  async function approve(id: string, wind: string) {
    const res = await opsPost<{ approved: boolean; issues: string[]; simulation?: boolean }>(`prescriptions/${encodeURIComponent(id)}/approve`, {
      wind_ms: wind === "" ? null : Number(wind),
    });
    if (!res.ok) setMsg(explain(res));
    else setMsg(res.data.approved ? t("rx.approved", { name: "✓" }) : res.data.issues.join(" · "));
    await load();
  }

  const input = "mt-1 w-full rounded border border-border px-2 py-1.5";
  return (
    <div className="space-y-5">
      <div>
        <h1 className="section-title text-xl sm:text-2xl">{t("rx.title")}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">{t("rx.intro")}</p>
      </div>
      {msg ? <p role="status" className="text-sm font-medium text-primary">{msg}</p> : null}

      <form onSubmit={(e) => void build(e)} className="card grid gap-3 border border-border bg-white p-4 sm:grid-cols-3">
        <h3 className="font-semibold sm:col-span-3">{t("rx.build")}</h3>
        <label className="text-sm">{t("rx.field")}
          <select name="field_id" required className={input}>
            {fields.map((f) => <option key={f.field_id} value={f.field_id}>{f.name}</option>)}
          </select>
        </label>
        <label className="text-sm">{t("rx.source")}
          <select className={input} value={source} onChange={(e) => setSource(e.target.value as "detections" | "satellite")}>
            <option value="detections">{t("rx.sourceDetections")}</option>
            <option value="satellite">{t("rx.sourceSatellite")}</option>
          </select>
        </label>
        {source === "detections" ? (
          <label className="text-sm">{t("rx.rate")}<input name="rate" type="number" step="any" min="0" required className={input} /></label>
        ) : (
          <label className="text-sm">{t("rx.rates")}<input name="rates" required placeholder="120, 80, 40" className={input} /></label>
        )}
        <label className="text-sm">{t("rx.product")}<input name="product" defaultValue={source === "detections" ? "herbicide" : "nitrogen"} className={input} /></label>
        <label className="text-sm">{t("rx.unit")}
          <select name="unit" className={input} defaultValue={source === "detections" ? "L/ha" : "kg/ha"}>
            <option>L/ha</option><option>kg/ha</option>
          </select>
        </label>
        <button type="submit" className="btn-primary self-end" disabled={!fields.length}>{t("rx.build")}</button>
      </form>

      <section className="space-y-3">
        {rxs.length === 0 ? <p className="text-sm text-muted">{t("rx.empty")}</p> : null}
        {rxs.map((r) => (
          <RxRow key={r.prescription_id} r={r} onApprove={approve} />
        ))}
      </section>
    </div>
  );
}

function RxRow({ r, onApprove }: { r: PrescriptionSummary; onApprove: (id: string, wind: string) => void }) {
  const { t } = useI18n();
  const [wind, setWind] = useState("");
  const base = `/api/ops/prescriptions/${encodeURIComponent(r.prescription_id)}/export?format=`;
  return (
    <article className="card border border-border bg-white p-4 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">{r.prescription_id} · {r.field_id} · {r.product} ({r.unit})</h3>
        <span className="text-xs font-semibold uppercase">
          {r.approved ? t("rx.approved", { name: r.approved_by ?? "?" }) : r.validated ? t("rx.validated") : t("rx.notValidated")}
        </span>
      </div>
      <p className="mt-1 text-muted">
        {t("rx.cellsOn")}: {r.cells_on} · {t("rx.treated")}: {r.treated_ha} · {t("rx.total")}: {r.total_product}
      </p>
      {r.issues.length ? (
        <div className="mt-2">
          <p className="font-medium">{t("rx.issues")}</p>
          <ul className="list-disc pl-5">{r.issues.map((i, k) => <li key={k}>{i}</li>)}</ul>
        </div>
      ) : null}
      {r.notes.length ? <p className="mt-1 text-xs text-muted">{r.notes.join(" · ")}</p> : null}
      <div className="mt-3 flex flex-wrap items-end gap-2">
        {!r.approved && r.validated ? (
          <>
            <label className="text-xs">{t("rx.wind")}
              <input type="number" step="0.1" min="0" value={wind} onChange={(e) => setWind(e.target.value)}
                     className="ml-1 w-20 rounded border border-border px-2 py-1" />
            </label>
            <button type="button" className="btn-primary text-sm" disabled={wind === ""} onClick={() => onApprove(r.prescription_id, wind)}>
              {t("rx.approve")}
            </button>
          </>
        ) : null}
        {r.approved ? (
          <>
            <a className="btn-secondary text-sm" href={`${base}isoxml`}>{t("rx.download")} ISOXML</a>
            <a className="btn-secondary text-sm" href={`${base}shapefile`}>{t("rx.download")} Shapefile</a>
          </>
        ) : null}
      </div>
    </article>
  );
}
