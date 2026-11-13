"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useI18n } from "@/components/I18nProvider";
import { clampT, fmtT, parseT, SCENARIO_STEP, SCENARIO_TOTAL } from "@/lib/ops-scenario";

/** Synthetic-time state for the demo scrubber: position, play/pause, `?t=` preset. Never autoplays. */
export function useScenarioClock(initialRaw?: string | null) {
  const [t, setT] = useState(() => parseT(initialRaw));
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setPlaying(false);
  }, []);

  const play = useCallback(() => {
    setT((cur) => (cur >= SCENARIO_TOTAL ? 0 : cur));
    setPlaying(true);
  }, []);

  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => {
      setT((cur) => Math.min(SCENARIO_TOTAL, cur + SCENARIO_STEP));
    }, 100);
    return () => {
      if (timer.current) clearInterval(timer.current);
      timer.current = null;
    };
  }, [playing]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- stop playing once the end is reached
    if (playing && t >= SCENARIO_TOTAL) stop();
  }, [playing, t, stop]);

  const toggle = useCallback(() => (playing ? stop() : play()), [playing, play, stop]);
  const seek = useCallback((next: number) => setT(clampT(next)), []);
  return { t, playing, toggle, seek, stop };
}

/** The design's synthetic timeline: play/pause, range and a "t+mm:ss" read-out. Everything on it is simulated. */
export function OpsScrubber({
  t,
  playing,
  onToggle,
  onSeek,
}: {
  t: number;
  playing: boolean;
  onToggle: () => void;
  onSeek: (t: number) => void;
}) {
  const { t: tr } = useI18n();
  return (
    <div className="scrub" role="group" aria-label={tr("d.k10dbf975")}>
      <button type="button" className="pp" aria-pressed={playing} aria-label={tr("d.kc67da1bb")} onClick={onToggle}>
        <svg className="i-play" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M7 4l13 8-13 8z" />
        </svg>
        <svg className="i-pause" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M8 5v14M16 5v14" />
        </svg>
      </button>
      <div className="tl">
        <input
          type="range"
          min={0}
          max={SCENARIO_TOTAL}
          step={1}
          value={t}
          aria-label={tr("d.kf41de9ab")}
          aria-valuetext={`${fmtT(t)} ${tr("d.k4445a7cd").toLowerCase()}`}
          onChange={(e) => onSeek(Number(e.target.value))}
          onKeyDown={(e) => {
            if (e.key === "Home") {
              e.preventDefault();
              onSeek(0);
            } else if (e.key === "End") {
              e.preventDefault();
              onSeek(SCENARIO_TOTAL);
            }
          }}
        />
        <div className="ticks" aria-hidden="true">
          <span>t+00:00</span>
          <span>t+05:00</span>
          <span>t+10:00</span>
          <span>t+15:00</span>
        </div>
      </div>
      <div className="ro-t">
        <small>{tr("d.k498526a1")}</small>
        <span>{fmtT(t)}</span>
      </div>
    </div>
  );
}
