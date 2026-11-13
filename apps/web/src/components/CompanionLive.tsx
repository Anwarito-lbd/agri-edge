"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AdvisoryMsg,
  AlertMsg,
  BatteryMsg,
  DetectionFeature,
  DetectionsGeoJson,
  DockMsg,
  GpsMsg,
  HeartbeatMsg,
  QaFlagsMsg,
  StatusSnapshot,
} from "@/lib/mock-pi/types";

type LiveState = {
  heartbeat: HeartbeatMsg | null;
  gps: GpsMsg | null;
  battery: BatteryMsg | null;
  qa_flags: QaFlagsMsg | null;
  advisory: AdvisoryMsg | null;
  dock: DockMsg | null;
  alerts: AlertMsg[];
  detections: DetectionFeature[];
  streamConnected: boolean;
  lastEventAt: string | null;
  error: string | null;
};

const INITIAL: LiveState = {
  heartbeat: null,
  gps: null,
  battery: null,
  qa_flags: null,
  advisory: null,
  dock: null,
  alerts: [],
  detections: [],
  streamConnected: false,
  lastEventAt: null,
  error: null,
};

function mergeSnapshot(snap: StatusSnapshot, detections: DetectionFeature[]): LiveState {
  return {
    heartbeat: snap.heartbeat,
    gps: snap.gps,
    battery: snap.battery,
    qa_flags: snap.qa_flags,
    advisory: snap.advisory,
    dock: snap.dock,
    alerts: snap.alerts,
    detections,
    streamConnected: false,
    lastEventAt: snap.ts,
    error: null,
  };
}

function severityDot(sev: string): string {
  if (sev === "critical") return "bg-[var(--ae-status-critical)]";
  if (sev === "warn") return "bg-[var(--ae-status-warn)]";
  if (sev === "ok") return "bg-[var(--ae-status-ok)]";
  return "bg-[var(--ae-status-info)]";
}

function severityText(sev: string): string {
  if (sev === "critical") return "text-[var(--ae-status-critical)]";
  if (sev === "warn") return "text-[var(--ae-status-warn)]";
  if (sev === "ok") return "text-[var(--ae-status-ok)]";
  return "text-[var(--ae-status-info)]";
}

function chipClass(ok: boolean): string {
  return ok
    ? "border-[var(--ae-status-ok)]/50 text-[var(--ae-status-ok)]"
    : "border-[var(--ae-status-critical)]/50 text-[var(--ae-status-critical)]";
}

function fixLabel(fix: number | undefined): string {
  if (fix == null) return "—";
  if (fix >= 4) return "RTK/float+";
  if (fix === 3) return "3D fix";
  if (fix === 2) return "2D";
  return `fix ${fix}`;
}

export function CompanionLive() {
  const [live, setLive] = useState<LiveState>(INITIAL);
  const esRef = useRef<EventSource | null>(null);
  const detectionsRef = useRef<DetectionFeature[]>([]);

  const applyFrame = useCallback((raw: unknown) => {
    if (!raw || typeof raw !== "object") return;
    const msg = raw as { topic?: string };
    const ts =
      typeof (raw as { ts?: string }).ts === "string"
        ? (raw as { ts: string }).ts
        : new Date().toISOString();

    setLive((prev) => {
      const next: LiveState = { ...prev, lastEventAt: ts, streamConnected: true, error: null };
      switch (msg.topic) {
        case "heartbeat":
          next.heartbeat = raw as HeartbeatMsg;
          break;
        case "gps":
          next.gps = raw as GpsMsg;
          break;
        case "battery":
          next.battery = raw as BatteryMsg;
          break;
        case "qa_flags":
          next.qa_flags = raw as QaFlagsMsg;
          break;
        case "advisory":
          next.advisory = raw as AdvisoryMsg;
          break;
        case "dock":
          next.dock = raw as DockMsg;
          break;
        case "alert": {
          const alert = raw as AlertMsg;
          const rest = prev.alerts.filter((a) => a.id !== alert.id);
          next.alerts = [alert, ...rest].slice(0, 12);
          break;
        }
        case "detections":
          // count-only frame; full features refreshed separately on snapshot / geojson
          break;
        default:
          break;
      }
      return next;
    });
  }, []);

  const ackAlert = useCallback(async (id: string) => {
    try {
      const res = await fetch(`/api/v1/alerts/${encodeURIComponent(id)}/ack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ op: "ack_alert" }),
      });
      if (!res.ok) return;
      setLive((prev) => ({
        ...prev,
        alerts: prev.alerts.map((a) =>
          a.id === id ? { ...a, acked: true } : a,
        ),
      }));
    } catch {
      /* ignore demo ack errors */
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        const [statusRes, geoRes] = await Promise.all([
          fetch("/api/v1/status", { cache: "no-store" }),
          fetch("/api/v1/detections.geojson", { cache: "no-store" }),
        ]);
        if (!statusRes.ok) throw new Error(`status ${statusRes.status}`);
        const snap = (await statusRes.json()) as StatusSnapshot;
        let features: DetectionFeature[] = [];
        if (geoRes.ok) {
          const fc = (await geoRes.json()) as DetectionsGeoJson;
          features = fc.features ?? [];
        }
        if (cancelled) return;
        detectionsRef.current = features;
        setLive(mergeSnapshot(snap, features));
      } catch (e) {
        if (!cancelled) {
          setLive((prev) => ({
            ...prev,
            error: e instanceof Error ? e.message : "bootstrap failed",
          }));
        }
      }
    }

    function connectStream() {
      if (cancelled) return;
      esRef.current?.close();
      const es = new EventSource("/api/v1/stream");
      esRef.current = es;

      const onPayload = (ev: MessageEvent) => {
        try {
          const data = JSON.parse(ev.data as string);
          if (data && data.demo === true && data.heartbeat) {
            // snapshot event
            const snap = data as StatusSnapshot;
            setLive((prev) => ({
              ...mergeSnapshot(snap, prev.detections.length ? prev.detections : detectionsRef.current),
              streamConnected: true,
            }));
            // refresh geojson occasionally with snapshot
            void fetch("/api/v1/detections.geojson", { cache: "no-store" })
              .then((r) => (r.ok ? r.json() : null))
              .then((fc: DetectionsGeoJson | null) => {
                if (!fc || cancelled) return;
                detectionsRef.current = fc.features;
                setLive((prev) => ({ ...prev, detections: fc.features }));
              })
              .catch(() => undefined);
            return;
          }
          applyFrame(data);
        } catch {
          /* ignore malformed */
        }
      };

      es.addEventListener("snapshot", onPayload);
      for (const t of [
        "heartbeat",
        "gps",
        "battery",
        "qa_flags",
        "advisory",
        "dock",
        "alert",
        "detections",
      ]) {
        es.addEventListener(t, onPayload);
      }
      es.onmessage = onPayload;
      es.onopen = () => {
        setLive((prev) => ({ ...prev, streamConnected: true, error: null }));
      };
      es.onerror = () => {
        setLive((prev) => ({ ...prev, streamConnected: false }));
        // EventSource reconnects automatically
      };
    }

    void bootstrap().then(connectStream);

    // Periodic geojson refresh so detection list jitters with mock
    const geoTimer = setInterval(() => {
      void fetch("/api/v1/detections.geojson", { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((fc: DetectionsGeoJson | null) => {
          if (!fc || cancelled) return;
          detectionsRef.current = fc.features;
          setLive((prev) => ({ ...prev, detections: fc.features }));
        })
        .catch(() => undefined);
    }, 8000);

    return () => {
      cancelled = true;
      clearInterval(geoTimer);
      esRef.current?.close();
      esRef.current = null;
    };
  }, [applyFrame]);

  const advisoryTone = useMemo(() => {
    const d = live.advisory?.decision;
    if (d === "go") return { label: "GO", sev: "ok" as const };
    if (d === "no_go") return { label: "NO-GO", sev: "critical" as const };
    return { label: "UNKNOWN", sev: "warn" as const };
  }, [live.advisory]);

  const battPct = live.battery?.remaining_pct;
  const battSev =
    battPct == null
      ? "info"
      : battPct <= 18
        ? "critical"
        : battPct <= 30
          ? "warn"
          : "ok";

  return (
    <div className="bg-surface min-h-full">
      <div className="container-page app-dense">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="max-w-md">
            <p className="eyebrow text-[11px]">Product UI · DEMO</p>
            <h1 className="mt-1 text-[1.5rem] font-bold tracking-tight text-ink sm:text-[1.75rem]">
              Companion app · mock-Pi feed
            </h1>
            <p className="mt-1 text-[13px] text-muted">
              Live SSE status/alerts — never flight control. Not live aircraft.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-[12px]">
            <span
              className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
                live.streamConnected
                  ? "border-[var(--ae-status-ok)]/40 text-[var(--ae-status-ok)]"
                  : "border-[var(--ae-status-warn)]/40 text-[var(--ae-status-warn)]"
              }`}
            >
              {live.streamConnected ? "Demo feed" : "Demo feed reconnecting"}
            </span>
            <Link href="/proof" className="link-arrow text-[13px]">
              /proof
            </Link>
            <Link href="/dashboard" className="link-arrow text-[13px]">
              /dashboard
            </Link>
          </div>
        </div>

        <div
          role="alert"
          className="notice-safety mt-4 max-w-xl !px-3 !py-2.5 text-[12px]"
        >
          This app does not arm, disarm, or fly the aircraft. Companion computer
          is read-only toward the aircraft. Treatment stays locked until local
          validation and a geofence.{" "}
          <strong>DEMO mock-Pi</strong> — never implies a live aircraft.
        </div>

        {live.error ? (
          <p className="mt-3 text-[12px] text-[var(--ae-status-critical)]">
            Feed error: {live.error}
          </p>
        ) : null}

        <div className="mt-6 flex flex-col items-center gap-8 lg:flex-row lg:items-start lg:justify-center lg:gap-10">
          <div className="phone-frame phone-frame-dense w-full overflow-hidden rounded-sm">
            <div className="border-b border-white/10 px-3 py-2.5">
              <div className="flex items-center justify-between">
                <p className="text-[9px] font-semibold uppercase tracking-wide text-white/45">
                  agri-edge companion
                </p>
                <div className="flex items-center gap-1.5">
                  <span className="rounded border border-white/20 px-1.5 py-px text-[8px] font-bold uppercase tracking-wide text-cyan">
                    RO
                  </span>
                  <span className="rounded border border-[var(--ae-status-warn)]/50 px-1.5 py-px text-[8px] font-bold uppercase tracking-wide text-[var(--ae-status-warn)]">
                    DEMO
                  </span>
                </div>
              </div>
              <h2 className="mt-0.5 text-[13px] font-bold text-white">
                Ops · Edge status
              </h2>
              <p className="text-[10px] text-white/45">
                Mock-Pi SSE · does not arm/fly
                {live.lastEventAt
                  ? ` · ${new Date(live.lastEventAt).toLocaleTimeString()}`
                  : ""}
              </p>
            </div>

            <div className="space-y-1.5 p-2">
              {/* Link chips */}
              <div className="flex flex-wrap gap-1">
                {[
                  {
                    k: "MAVLink",
                    ok: live.heartbeat?.link.mavlink_ok ?? false,
                  },
                  { k: "GNSS", ok: live.heartbeat?.link.gnss_ok ?? false },
                  {
                    k: "NTRIP",
                    ok: live.heartbeat?.link.ntrip_ok ?? false,
                  },
                  {
                    k: "Pipe",
                    ok: live.heartbeat?.pi.pipeline === "running",
                  },
                ].map((c) => (
                  <span
                    key={c.k}
                    className={`rounded border px-1.5 py-0.5 text-[8px] font-semibold uppercase tracking-wide ${chipClass(c.ok)}`}
                  >
                    {c.k} {c.ok ? "ok" : "fail"}
                  </span>
                ))}
              </div>

              <div className="grid grid-cols-2 gap-1.5">
                <div className="phone-panel px-2 py-1.5">
                  <p className="text-[8px] font-semibold uppercase tracking-wide text-white/40">
                    Battery (FC)
                  </p>
                  <p
                    className={`mt-0.5 text-[12px] font-semibold ${severityText(battSev)}`}
                  >
                    {battPct != null ? `${battPct.toFixed(0)}%` : "—"}
                  </p>
                  <p className="text-[9px] text-white/40">
                    {live.battery
                      ? `${live.battery.voltage_v.toFixed(1)} V · ${live.battery.current_a.toFixed(1)} A`
                      : "telemetry mock"}
                  </p>
                </div>
                <div className="phone-panel px-2 py-1.5">
                  <p className="text-[8px] font-semibold uppercase tracking-wide text-white/40">
                    GNSS
                  </p>
                  <p className="mt-0.5 text-[12px] font-semibold text-white">
                    {fixLabel(live.gps?.fix_type)}
                  </p>
                  <p className="text-[9px] text-white/40">
                    {live.gps
                      ? `${live.gps.satellites} sats · HDOP ${live.gps.hdop}`
                      : "read-only"}
                  </p>
                </div>
                <div className="phone-panel px-2 py-1.5">
                  <p className="text-[8px] font-semibold uppercase tracking-wide text-white/40">
                    Advisory
                  </p>
                  <p
                    className={`mt-0.5 text-[12px] font-semibold ${severityText(advisoryTone.sev)}`}
                  >
                    {advisoryTone.label}
                  </p>
                  <p className="text-[9px] text-white/40">
                    {live.advisory?.wind_mps != null
                      ? `wind ${live.advisory.wind_mps} m/s · Demo`
                      : "wind gate · Demo"}
                  </p>
                </div>
                <div className="phone-panel px-2 py-1.5">
                  <p className="text-[8px] font-semibold uppercase tracking-wide text-white/40">
                    Model
                  </p>
                  <p className="mt-0.5 text-[11px] font-semibold text-white">
                    {live.heartbeat?.pi.model_id ?? "—"}
                  </p>
                  <p className="text-[9px] text-white/40">
                    up {live.heartbeat?.pi.uptime_s ?? "—"}s · mock
                  </p>
                </div>
              </div>

              {/* GPS / map thumbnail */}
              <div className="phone-panel overflow-hidden">
                <div className="flex items-center justify-between border-b border-white/10 px-2 py-1.5">
                  <p className="text-[9px] font-semibold uppercase tracking-wide text-white/40">
                    Field map · GPS
                  </p>
                  <span className="text-[8px] font-medium uppercase text-[var(--ae-status-warn)]">
                    Demo
                  </span>
                </div>
                <div
                  className="relative h-24"
                  style={{
                    background:
                      "linear-gradient(145deg, #1a2330 0%, #232d3b 40%, #1b2430 100%)",
                  }}
                >
                  <div
                    className="absolute inset-0 opacity-40"
                    style={{
                      backgroundImage:
                        "linear-gradient(rgba(0,166,220,0.12) 1px, transparent 1px), linear-gradient(90deg, rgba(0,166,220,0.12) 1px, transparent 1px)",
                      backgroundSize: "14px 14px",
                    }}
                  />
                  <div className="absolute left-[28%] top-[35%] h-7 w-10 border border-[#3879C1]/70 bg-[#225FA3]/25" />
                  {live.detections.slice(0, 5).map((f, i) => (
                    <div
                      key={String(f.id ?? i)}
                      className="absolute h-1.5 w-1.5 rounded-full bg-[#00A6DC]"
                      style={{
                        left: `${30 + (i * 12) % 40}%`,
                        top: `${28 + (i * 9) % 45}%`,
                      }}
                    />
                  ))}
                  <p className="absolute bottom-1.5 left-2 font-mono text-[8px] text-white/50">
                    {live.gps
                      ? `${live.gps.lat.toFixed(5)}, ${live.gps.lon.toFixed(5)} · AGL ${live.gps.alt_m_agl.toFixed(0)} m`
                      : "NW quarter · mock geo"}
                  </p>
                </div>
              </div>

              {/* Alerts */}
              <div className="phone-panel">
                <div className="border-b border-white/10 px-2 py-1.5">
                  <p className="text-[9px] font-semibold uppercase tracking-wide text-white/40">
                    Alerts
                  </p>
                </div>
                <ul className="max-h-36 divide-y divide-white/8 overflow-y-auto">
                  {live.alerts.length === 0 ? (
                    <li className="px-2 py-1.5 text-[10px] text-white/40">
                      No alerts · Demo
                    </li>
                  ) : (
                    live.alerts.map((a) => (
                      <li key={a.id} className="flex gap-2 px-2 py-1.5">
                        <span
                          className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${severityDot(a.severity)}`}
                        />
                        <span className="min-w-0 flex-1">
                          <span
                            className={`block text-[11px] font-medium ${a.acked ? "text-white/45 line-through" : "text-white/90"}`}
                          >
                            {a.title}
                          </span>
                          <span className="block text-[9px] text-white/40">
                            {a.type} · {a.body}
                          </span>
                          {a.ackable && !a.acked ? (
                            <button
                              type="button"
                              onClick={() => void ackAlert(a.id)}
                              className="mt-0.5 text-[8px] font-semibold uppercase tracking-wide text-cyan"
                            >
                              Ack
                            </button>
                          ) : null}
                        </span>
                      </li>
                    ))
                  )}
                </ul>
              </div>

              {/* Detections list */}
              <div className="phone-panel">
                <div className="flex items-center justify-between border-b border-white/10 px-2 py-1.5">
                  <p className="text-[9px] font-semibold uppercase tracking-wide text-white/40">
                    Detections
                  </p>
                  <span className="text-[8px] text-white/35">
                    {live.detections.length} · geojson
                  </span>
                </div>
                <ul className="max-h-28 divide-y divide-white/8 overflow-y-auto">
                  {live.detections.map((f) => {
                    const p = f.properties;
                    const treatLocked =
                      !(p.validated_locally && p.in_treatment_zone === true);
                    return (
                      <li key={String(f.id)} className="px-2 py-1.5">
                        <span className="block text-[11px] font-medium text-white/90">
                          {p.label}{" "}
                          <span className="font-mono text-[9px] text-white/40">
                            {(p.confidence * 100).toFixed(0)}%
                          </span>
                        </span>
                        <span className="block text-[9px] text-white/40">
                          {f.geometry.coordinates[1].toFixed(4)},{" "}
                          {f.geometry.coordinates[0].toFixed(4)}
                          {treatLocked ? " · treat locked" : ""}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>

              {/* Telemetry strip */}
              <div className="phone-panel px-2 py-1.5">
                <p className="text-[9px] font-semibold uppercase tracking-wide text-white/40">
                  Demo telemetry (mock-Pi)
                </p>
                <div className="mt-1.5 grid grid-cols-3 gap-1 text-center">
                  {[
                    {
                      k: "Alt",
                      v: live.gps ? `${live.gps.alt_m_agl.toFixed(0)} m` : "—",
                    },
                    {
                      k: "QA",
                      v:
                        live.qa_flags && live.qa_flags.flags.length
                          ? live.qa_flags.flags[0]
                          : "clear",
                    },
                    {
                      k: "Dock",
                      v: live.dock?.present ? "present" : "n/a",
                    },
                  ].map((t) => (
                    <div key={t.k} className="ops-hairline rounded-sm py-1">
                      <p className="text-[8px] uppercase text-white/35">{t.k}</p>
                      <p className="truncate px-0.5 font-mono text-[10px] font-semibold text-white">
                        {t.v}
                      </p>
                    </div>
                  ))}
                </div>
                <p className="mt-1.5 text-[9px] leading-snug text-white/40">
                  MAVLink listen-only. No arm, disarm, mode, or mission write
                  paths exist in this shell.
                </p>
              </div>

              <div className="space-y-1">
                {[
                  {
                    label: "Run edge preflight",
                    hint: "config · storage · provenance",
                    primary: true,
                  },
                  {
                    label: "Start capture session",
                    hint: "simulate",
                    primary: false,
                  },
                  {
                    label: "List spool · export",
                    hint: "workstation handoff",
                    primary: false,
                  },
                ].map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    disabled
                    className={`flex w-full items-center justify-between px-2.5 py-2 text-left disabled:opacity-95 ${
                      action.primary
                        ? "bg-primary text-white"
                        : "phone-panel text-white/90"
                    }`}
                  >
                    <span>
                      <span className="block text-[12px] font-medium">
                        {action.label}
                      </span>
                      <span
                        className={`mt-0.5 block text-[9px] ${
                          action.primary ? "text-white/70" : "text-white/40"
                        }`}
                      >
                        {action.hint}
                      </span>
                    </span>
                    <span className="text-base opacity-40" aria-hidden>
                      ›
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex border-t border-white/10 pb-2 pt-1 text-center">
              {[
                { label: "Status", active: true },
                { label: "Map", active: false },
                { label: "Alerts", active: false },
                { label: "About", active: false },
              ].map((tab) => (
                <span
                  key={tab.label}
                  className={`flex flex-1 flex-col items-center gap-0.5 py-1 text-[9px] font-semibold ${
                    tab.active ? "text-cyan" : "text-white/35"
                  }`}
                >
                  <span
                    className={`h-0.5 w-3.5 ${
                      tab.active ? "bg-cyan" : "bg-transparent"
                    }`}
                  />
                  {tab.label}
                </span>
              ))}
            </div>
          </div>

          <div className="max-w-xs space-y-4 text-center lg:pt-1 lg:text-left">
            <div>
              <h3 className="text-base font-bold text-ink">
                Demo mock-Pi companion feed
              </h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
                Snapshot + SSE every ~2s: heartbeat, GPS jitter, battery drain,
                wind-gated advisory, alerts, and GeoJSON detections. Dense NAV
                CANADA ops chrome — still a demo shell, not a flight controller.
              </p>
            </div>
            <ul className="space-y-2 text-[13px] text-muted">
              {[
                "Read-only MAVLink by construction",
                "DEMO labeling — never implies live aircraft",
                "Unknown ops rejected; ack-alert only write",
                "Treatment fails closed without local validation",
              ].map((t) => (
                <li
                  key={t}
                  className="flex justify-center gap-2 lg:justify-start"
                >
                  <span className="mt-1.5 h-1 w-1 shrink-0 bg-primary" />
                  <span>{t}</span>
                </li>
              ))}
            </ul>
            <p className="font-mono text-[10px] text-muted">
              GET /api/v1/status · /detections.geojson · SSE /stream
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
