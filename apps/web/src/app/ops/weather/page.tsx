"use client";

import { useCallback, useEffect, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { OpsEmptyState } from "@/components/ops/OpsEmptyState";
import { DemoTag, OpsPageHead } from "@/components/ops/OpsPageHead";
import { useOpsStatus } from "@/components/ops/OpsShell";
import { opsGet } from "@/lib/ops-api";
import type { DerivedWeather, WeatherObs, WeatherResponse } from "@/lib/ops-types";

/** Dew point and VPD from either shape the API has used. */
function derivedValues(derived: DerivedWeather | null): { dew?: number; vpd?: number } {
  if (!derived) return {};
  const dew =
    derived.dewpoint && typeof derived.dewpoint === "object"
      ? (derived.dewpoint as { value_c?: number }).value_c
      : typeof derived.dewpoint_c === "number"
        ? derived.dewpoint_c
        : undefined;
  const vpdObj = derived.vpd && typeof derived.vpd === "object" ? (derived.vpd as { vpd_kpa?: number }) : null;
  const vpd =
    typeof vpdObj?.vpd_kpa === "number" ? vpdObj.vpd_kpa : typeof derived.vpd_kpa === "number" ? derived.vpd_kpa : undefined;
  return { dew, vpd };
}

function latestOf(obs: WeatherObs[]): WeatherObs | undefined {
  return obs.reduce<WeatherObs | undefined>((best, o) => (!best || o.ts > best.ts ? o : best), undefined);
}

/** Demo rows carry fixed sample timestamps; drop them from raw payload dumps so nothing looks live. */
function withoutTime(row: Record<string, unknown>): Record<string, unknown> {
  const { ts: _ts, period: _period, created_at: _created, ...rest } = row;
  void _ts;
  void _period;
  void _created;
  return rest;
}

function Kpi({ label, value, unit, sub }: { label: string; value: string | null; unit?: string; sub?: React.ReactNode }) {
  return (
    <div className="kpi">
      <div className="l">{label}</div>
      <div className={`v${value == null ? " dash" : ""}`}>
        {value ?? "—"}
        {value != null && unit ? <small>{unit}</small> : null}
      </div>
      {sub ? <div className="s">{sub}</div> : null}
    </div>
  );
}

export default function OpsWeatherPage() {
  const { t } = useI18n();
  const { offline, demo: shellDemo, refreshStatus } = useOpsStatus();
  const [data, setData] = useState<WeatherResponse | null>(null);
  const [derived, setDerived] = useState<DerivedWeather | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const [w, d] = await Promise.all([
      opsGet<WeatherResponse>("weather"),
      opsGet<DerivedWeather>("weather/derived"),
    ]);
    if (!w.ok) {
      setError(w.error);
      setData(w.data ?? null);
    } else {
      setError(null);
      setData(w.data);
    }
    if (d.ok) setDerived(d.data);
    else setDerived(null);
    setLoading(false);
    refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    void load();
  }, [load]);

  const demo = shellDemo || data?.demo === true;
  const obs = data?.observations ?? [];
  const aggs = data?.aggregates ?? [];
  const latest = latestOf(obs);
  const { dew, vpd } = derivedValues(derived);
  const tag = t("d.kabe8a16e");
  const num = (n: number | null | undefined, digits = 1) => (typeof n === "number" ? n.toFixed(digits) : null);
  const sub = demo ? <DemoTag label={tag} /> : null;
  const derivedSub = (
    <>
      {demo ? <DemoTag label={tag} /> : null}
      <span>{t("wx.origin", { origin: String(derived?.origin ?? "DERIVED") })}</span>
    </>
  );
  const maxWind = Math.max(0, ...obs.map((o) => o.wind_ms ?? 0));
  const stations = [...new Set(obs.map((o) => o.station_id))].join(", ");
  const gddNote = derived?.gdd_stub && typeof derived.gdd_stub.note === "string" ? derived.gdd_stub.note : null;

  return (
    <>
      <OpsPageHead title={t("nav.weather")} sub={demo ? t("d.k363aa053") : t("wx.title")}>
        <span className="chip">{t("d.k4c6ca02e")}</span>
        <button type="button" className="btn-sm" onClick={() => void load()}>
          {t("common.refresh")}
        </button>
      </OpsPageHead>

      {loading && !data ? <p className="muted cap" style={{ marginBottom: 12 }}>{t("wx.loading")}</p> : null}
      {offline || error ? (
        <div style={{ marginBottom: 16 }}>
          <OpsEmptyState
            title={t("wx.unavailable")}
            detail={error ? t("wx.unavailableDetail", { error }) : t("wx.unreachable")}
          />
        </div>
      ) : null}

      <div className="kpis k6">
        <Kpi label={t("d.k56d1524c")} value={num(latest?.air_temp?.value_c)} unit="°C" sub={latest ? sub : null} />
        <Kpi label={t("wx.humidity")} value={num(latest?.rh_pct, 0)} unit="%" sub={latest ? sub : null} />
        <Kpi label={t("d.k62450ed0")} value={num(latest?.wind_ms)} unit="m/s" sub={latest ? sub : null} />
        <Kpi label={t("d.ka7eede1b")} value={num(latest?.precip_mm)} unit="mm" sub={latest ? sub : null} />
        <Kpi label={t("wx.dewpoint")} value={num(dew)} unit="°C" sub={dew != null ? derivedSub : null} />
        <Kpi label={t("wx.vpd")} value={num(vpd, 3)} unit="kPa" sub={vpd != null ? derivedSub : null} />
      </div>

      <div className="two">
        <div className="panel">
          <header>
            <h2>{t("wx.raw")}</h2>
            {demo ? <DemoTag label={tag} /> : null}
          </header>
          <div className="tw" tabIndex={0} role="region" aria-label={t("d.k4a98ef65")}>
            <table className="dt">
              <thead>
                <tr>
                  <th>{demo ? t("wx.sample") : t("wx.time")}</th>
                  <th>{t("wx.station")}</th>
                  <th className="n">{t("wx.air")}</th>
                  <th className="n">{t("wx.rh")}</th>
                  <th className="n">{t("wx.wind")}</th>
                  <th>{t("wx.synthetic")}</th>
                </tr>
              </thead>
              <tbody>
                {obs.length === 0 ? (
                  <tr>
                    <td colSpan={6}>{t("wx.noObs")}</td>
                  </tr>
                ) : (
                  obs.map((o, i) => (
                    <tr key={o.obs_id}>
                      <td className="id">{demo ? `#${i + 1}` : o.ts}</td>
                      <td className="id">{o.station_id}</td>
                      <td className="n">{o.air_temp?.value_c != null ? o.air_temp.value_c.toFixed(1) : "—"}</td>
                      <td className="n">{o.rh_pct ?? "—"}</td>
                      <td className="n">{o.wind_ms ?? "—"}</td>
                      <td>{o.synthetic ? <DemoTag label={tag} /> : "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div className="stack">
          <div className="panel">
            <header>
              <h2>{t("wx.windByHour")}</h2>
              {demo ? <DemoTag label={tag} /> : null}
            </header>
            <div className="pb">
              {obs.length === 0 ? (
                <div className="empty">{t("wx.noObs")}</div>
              ) : (
                <div className="bars">
                  {obs.map((o, i) => (
                    <div className="bar-row" key={o.obs_id}>
                      <span className="id">
                        {demo ? `#${i + 1}` : new Date(o.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      <div
                        className="tr"
                        role="img"
                        aria-label={`${o.wind_ms ?? "—"} m/s`}
                      >
                        <i style={{ width: `${maxWind > 0 ? ((o.wind_ms ?? 0) / maxWind) * 100 : 0}%` }} />
                      </div>
                      <span className="val">{o.wind_ms ?? "—"}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="panel">
            <header>
              <h2>{t("d.k806ef808")}</h2>
            </header>
            <div className="pb">
              <div className="kv">
                <div>{t("d.kd17c940f")}</div>
                <div>{demo ? t("d.kfb2122cf") : t("map.srcLive")}</div>
                <div>{demo ? t("d.k6eb5b357") : t("wx.station")}</div>
                <div>{demo ? t("d.k4f305c0a") : stations || "—"}</div>
                <div>{t("wx.gdd")}</div>
                <div>{gddNote ?? "—"}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <header>
          <h2>{t("wx.aggregates")}</h2>
          {demo ? <DemoTag label={tag} /> : null}
        </header>
        <div className="tw" tabIndex={0} role="region" aria-label={t("d.k4a98ef65")}>
          <table className="dt">
            <thead>
              <tr>
                <th>{demo ? t("wx.sample") : t("wx.period")}</th>
                <th>{t("wx.station")}</th>
                <th>{t("wx.payload")}</th>
              </tr>
            </thead>
            <tbody>
              {aggs.length === 0 ? (
                <tr>
                  <td colSpan={3}>{t("wx.noAgg")}</td>
                </tr>
              ) : (
                aggs.map((a, i) => {
                  const row = demo ? withoutTime(a) : a;
                  const json = JSON.stringify(row);
                  return (
                    <tr key={String((a as { agg_id?: string }).agg_id ?? i)}>
                      <td className="id">{demo ? `#${i + 1}` : String((a as { period?: string }).period ?? "—")}</td>
                      <td className="id">{String((a as { station_id?: string }).station_id ?? "—")}</td>
                      <td>
                        <code className="cap">
                          {json.slice(0, 160)}
                          {json.length > 160 ? "…" : ""}
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

      {data?.note ? <p className="note cap">{data.note}</p> : null}
    </>
  );
}
