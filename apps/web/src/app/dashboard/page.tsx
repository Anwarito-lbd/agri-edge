import type { Metadata } from "next";
import Link from "next/link";
import { DemoMapLazy } from "@/components/DemoMapLazy";
import { DEMO_DETECTIONS } from "@/lib/demo-geo";

export const metadata: Metadata = {
  title: "Dashboard demo",
  description:
    "Mock field dashboard for agri-edge — labeled Demo, not live telemetry.",
};

const FLIGHTS = [
  {
    id: "F-2026-09-14-A",
    field: "NW quarter — canola",
    frames: 842,
    qaPass: "91%",
    detections: 126,
    status: "Spooled",
  },
  {
    id: "F-2026-09-12-B",
    field: "South pasture — sheep",
    frames: 310,
    qaPass: "96%",
    detections: 204,
    status: "Exported",
  },
  {
    id: "F-2026-09-10-C",
    field: "East strip — weed scout",
    frames: 1204,
    qaPass: "88%",
    detections: 67,
    status: "QA review",
  },
];

const KPIS = [
  { label: "Flights", value: "3" },
  { label: "Frames", value: "2,356" },
  { label: "QA pass", value: "91%" },
  { label: "Treatment ready", value: "0" },
];

export default function DashboardPage() {
  return (
    <div className="bg-ops-slate">
      {/* Full-bleed ops map — CFPS density, no marketing lede */}
      <div className="dash-map-shell">
        <DemoMapLazy className="absolute inset-0 h-full w-full" />

        <div className="dash-float dash-kpi-strip" aria-label="Demo KPIs">
          <div className="dash-kpi-card flex items-center justify-between gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-white/55">
              Field dashboard
            </span>
            <span className="rounded border border-white/25 px-1.5 py-px text-[9px] font-bold uppercase tracking-wide text-cyan">
              Demo
            </span>
          </div>
          {KPIS.map((kpi) => (
            <div key={kpi.label} className="dash-kpi-card">
              <p className="text-[9px] font-semibold uppercase tracking-wide text-white/45">
                {kpi.label}
              </p>
              <p className="mt-0.5 text-lg font-bold leading-none text-white">
                {kpi.value}
              </p>
            </div>
          ))}
          <p className="dash-kpi-card text-[10px] leading-snug text-white/55">
            Treatment ready is 0:{" "}
            <code className="font-mono text-[10px] text-white/75">
              validated_locally
            </code>{" "}
            false until local annotation + geofence.
          </p>
        </div>

        <aside className="dash-float dash-det-panel" aria-label="Detection list">
          <div className="border-b border-white/10 px-3 py-2.5">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-white/45">
              Detection list
            </p>
            <p className="mt-0.5 text-[13px] font-medium text-white/90">
              {DEMO_DETECTIONS.length} mock markers
            </p>
          </div>
          <ul className="divide-y divide-white/8 flex-1 overflow-y-auto">
            {DEMO_DETECTIONS.map((d) => (
              <li key={d.id} className="px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[11px] text-cyan">{d.id}</span>
                  <span className="rounded border border-white/15 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-white/60">
                    {d.kind}
                  </span>
                </div>
                <p className="mt-0.5 text-[13px] font-medium text-white/90">
                  {d.label}
                </p>
                <p className="text-[10px] text-white/45">{d.note}</p>
              </li>
            ))}
          </ul>
          <div className="border-t border-white/10 px-3 py-2">
            <Link
              href="/proof"
              className="text-[11px] font-medium text-cyan hover:underline"
            >
              Real pipeline images →
            </Link>
          </div>
        </aside>

        <p className="dash-honesty">
          Demo only — no live aircraft, no production farmOS. Markers and
          polygons are illustrative placeholders for layout review.
        </p>
      </div>

      {/* Compact ops tables below map fold */}
      <div className="border-t border-white/10 bg-surface">
        <div className="container-page py-6 sm:py-8">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <h2 className="text-base font-bold text-ink">
              Recent flights (mock)
            </h2>
            <p className="text-[11px] text-muted">
              Leaflet · dark basemap · Saskatchewan-ish
            </p>
          </div>
          <div className="mt-3 overflow-x-auto border border-border bg-white">
            <table className="table-inst w-full min-w-[40rem]">
              <thead>
                <tr>
                  <th>Flight</th>
                  <th>Field</th>
                  <th>Frames</th>
                  <th>QA</th>
                  <th>Detections</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {FLIGHTS.map((f) => (
                  <tr key={f.id}>
                    <td className="emph font-mono text-xs">{f.id}</td>
                    <td>{f.field}</td>
                    <td>{f.frames}</td>
                    <td>{f.qaPass}</td>
                    <td>{f.detections}</td>
                    <td>
                      <span className="rounded border border-border bg-surface px-2 py-0.5 text-xs font-medium text-ink">
                        {f.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-start justify-between gap-3 border border-border bg-white px-4 py-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-bold text-ink">
                  Thermal stress layer
                </h3>
                <span className="rounded border border-warning/40 bg-warning/10 px-1.5 py-px text-[9px] font-bold uppercase tracking-wide text-warning">
                  Next
                </span>
                <span className="rounded border border-cyan/40 bg-cyan/10 px-1.5 py-px text-[9px] font-bold uppercase tracking-wide text-cyan">
                  Demo note
                </span>
              </div>
              <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-muted">
                CWSI-style canopy temperature / water-stress maps are on the
                roadmap. This dashboard does not show live °C imagery — no
                thermal payload on the Demo map. See Vision for the capability
                map.
              </p>
            </div>
            <Link
              href="/vision"
              className="shrink-0 text-[11px] font-medium text-primary hover:underline"
            >
              Vision roadmap →
            </Link>
          </div>

          <div className="mt-6 grid gap-3 lg:grid-cols-2">
            <div className="card p-4">
              <h3 className="text-sm font-bold text-ink">
                Pipeline stages (demo)
              </h3>
              <ul className="mt-2 space-y-1.5 text-[13px] text-muted">
                {[
                  "Capture geotagged frames",
                  "QA gate (flag, do not delete)",
                  "Inference (YOLOX / green-on-brown)",
                  "Indices + management zones",
                  "Spool → farmOS / WebODM",
                ].map((step, i) => (
                  <li key={step} className="flex gap-2">
                    <span className="font-mono text-primary">{i + 1}.</span>
                    {step}
                  </li>
                ))}
              </ul>
            </div>
            <div className="notice-safety !py-3 !px-4">
              <h3 className="text-sm font-semibold text-ink">Safety reminder</h3>
              <p className="mt-1.5 text-[13px] leading-relaxed font-normal text-muted">
                This dashboard does not send MAVLink commands. Models are
                sensors. A false positive used for scouting costs a walk; the
                same false positive wired to a sprayer costs chemical, crop, or
                an environmental incident.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
