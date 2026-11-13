"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useI18n } from "@/components/I18nProvider";
import { useOpsStatus } from "@/components/ops/OpsShell";
import { opsGet, opsPost } from "@/lib/ops-api";
import type { FieldProfile } from "@/lib/ops-types";

const CROPS = ["canola", "spring_wheat", "potato"];
const SOILS = ["sand", "loamy_sand", "sandy_loam", "loam", "silt_loam", "silt", "silty_clay_loam", "silty_clay", "clay"];

export default function FieldsPage() {
  const { t } = useI18n();
  const { refreshStatus } = useOpsStatus();
  const [fields, setFields] = useState<FieldProfile[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await opsGet<{ fields?: FieldProfile[]; simulation?: boolean }>("fields");
    if (res.ok) setFields(res.data.fields ?? []);
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on mount
    void load();
  }, [load]);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    let boundary: FieldProfile["boundary"] = null;
    const raw = String(f.get("boundary") || "").trim();
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        boundary = parsed.type === "Feature" ? parsed.geometry : parsed;
      } catch {
        setMsg(t("common.error", { error: "boundary is not valid JSON" }));
        return;
      }
    }
    const body: FieldProfile = {
      field_id: String(f.get("field_id")),
      name: String(f.get("name")),
      crop: String(f.get("crop")),
      seeded: String(f.get("seeded")),
      soil: String(f.get("soil")),
      lat: Number(f.get("lat")),
      lon: Number(f.get("lon")),
      irrigated: f.get("irrigated") === "on",
      ...(boundary ? { boundary } : {}),
    };
    const res = await opsPost<{ field?: FieldProfile; simulation?: boolean }>("fields", body);
    if (res.ok) {
      setMsg(t("fields.saved", { id: body.field_id }));
      await load();
    } else {
      setMsg(res.forbidden ? t("common.forbidden", { error: res.error }) : t("common.error", { error: res.error }));
    }
  }

  async function refreshSatellite(id: string) {
    const res = await opsPost("satellite/refresh", { field_id: id });
    setMsg(res.ok ? t("fields.refreshStarted", { id }) : t("common.error", { error: res.error }));
  }

  const input = "mt-1 w-full rounded border border-border px-2 py-1.5";
  return (
    <div className="space-y-5">
      <div>
        <h1 className="section-title text-xl sm:text-2xl">{t("fields.title")}</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">{t("fields.intro")}</p>
      </div>
      {msg ? <p role="status" className="text-sm font-medium text-primary">{msg}</p> : null}
      <section className="card overflow-x-auto border border-border bg-white">
        <table className="table-inst w-full">
          <thead>
            <tr>
              <th>{t("fields.id")}</th><th>{t("fields.name")}</th><th>{t("fields.crop")}</th>
              <th>{t("fields.seeded")}</th><th>{t("fields.soil")}</th><th>{t("fields.irrigated")}</th>
              <th>{t("fields.satellite")}</th>
            </tr>
          </thead>
          <tbody>
            {fields.length === 0 ? (
              <tr><td colSpan={7}>{t("fields.empty")}</td></tr>
            ) : fields.map((f) => (
              <tr key={f.field_id}>
                <td className="emph">{f.field_id}</td><td>{f.name}</td><td>{f.crop}</td>
                <td>{f.seeded}</td><td>{f.soil}</td><td>{f.irrigated ? "✓" : "—"}</td>
                <td>
                  {f.boundary ? (
                    <button type="button" className="btn-secondary text-xs" onClick={() => void refreshSatellite(f.field_id)}>
                      {t("fields.refresh")}
                    </button>
                  ) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <form onSubmit={(e) => void save(e)} className="card grid gap-3 border border-border bg-white p-4 sm:grid-cols-2">
        <h3 className="font-semibold sm:col-span-2">{t("fields.add")}</h3>
        <label className="text-sm">{t("fields.id")}<input name="field_id" required pattern="[^/]{1,64}" className={input} /></label>
        <label className="text-sm">{t("fields.name")}<input name="name" required className={input} /></label>
        <label className="text-sm">{t("fields.crop")}
          <select name="crop" className={input}>{CROPS.map((c) => <option key={c}>{c}</option>)}</select>
        </label>
        <label className="text-sm">{t("fields.soil")}
          <select name="soil" className={input}>{SOILS.map((c) => <option key={c}>{c}</option>)}</select>
        </label>
        <label className="text-sm">{t("fields.seeded")}<input name="seeded" type="date" required className={input} /></label>
        <label className="flex items-center gap-2 text-sm"><input name="irrigated" type="checkbox" /> {t("fields.irrigated")}</label>
        <label className="text-sm">{t("fields.lat")}<input name="lat" type="number" step="any" required className={input} /></label>
        <label className="text-sm">{t("fields.lon")}<input name="lon" type="number" step="any" required className={input} /></label>
        <label className="text-sm sm:col-span-2">{t("fields.boundary")}
          <textarea name="boundary" rows={3} className={`${input} font-mono text-xs`} />
        </label>
        <button type="submit" className="btn-primary sm:col-span-2">{t("common.save")}</button>
      </form>
    </div>
  );
}
