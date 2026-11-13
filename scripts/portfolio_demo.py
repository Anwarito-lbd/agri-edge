#!/usr/bin/env python3
"""Run the laptop simulations and write the files under docs/proof/.

What this runs, and what it refuses to pretend:

* Coverage planning (`geo/coverage.py`) on a synthetic concave polygon, then a
  constant-speed playback of those lines. No wind, no attitude dynamics, no
  autopilot. The 4 s turn penalty is the planner's own placeholder.
* `agri-edge preflight` and `agri-edge fly --simulate` against config/demo.yaml.
  Telemetry is SimulatedTelemetry (straight east, near the Saskatoon default in
  that class). Imagery is SimulatedCamera. The detector is SimulatedEngine.
* The treatment decision engine, simulation only, on the same local frame the
  unit tests use.
* FAO-56 Example 18 through `et0_penman_monteith`, plus a scripted 21-day
  canola water balance whose temperatures are written in this file.
* `training/gsd_calculator.py` and `training/motion_budget.py`, captured as
  their own stdout.

ArduPilot SITL is not started. This script records whether the SITL binary is
present and stops there.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import struct
import subprocess
import sys
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agri_edge.agronomy.crops import get_crop  # noqa: E402
from agri_edge.agronomy.et0 import DayInputs, et0_penman_monteith, wind_at_2m  # noqa: E402
from agri_edge.agronomy.soils import get_soil  # noqa: E402
from agri_edge.agronomy.water_balance import run_balance  # noqa: E402
from agri_edge.agronomy.weather import Day  # noqa: E402
from agri_edge.decision.engine import (  # noqa: E402
    ArmingState,
    MissionState,
    SimulatedActuator,
    TreatmentCommand,
    TreatmentDecisionEngine,
)
from agri_edge.geo.coverage import best_heading, coverage_gaps, plan_coverage  # noqa: E402
from agri_edge.geo.geofence import TreatmentGeofence  # noqa: E402
from agri_edge.geo.georef import VehiclePose  # noqa: E402
from agri_edge.geo.indices import BandStack, compute  # noqa: E402
from agri_edge.inference.engine import Detection  # noqa: E402

# Synthetic boundary in local east/north metres. A notch, so a flight line has
# to break in two instead of crossing the gap. Not a surveyed field.
FIELD_M = np.array(
    [
        [0.0, 0.0],
        [420.0, 0.0],
        [420.0, 260.0],
        [270.0, 260.0],
        [270.0, 110.0],
        [150.0, 110.0],
        [150.0, 260.0],
        [0.0, 260.0],
    ],
    dtype=np.float64,
)

# Same origin and square the decision-engine tests use. A coordinate frame for
# the gate, not a place this process flew.
DECISION_ORIGIN = (49.8951, -97.1384)
DECISION_FIELD = np.array(
    [[-100.0, -100.0], [100.0, -100.0], [100.0, 100.0], [-100.0, 100.0]]
)
M_PER_DEG_LAT = 111_320.0
DECISION_NOW = 2_000_000.0

BANDS = "red,green,blue,nir,red-edge"


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _run(cmd: list[str], log_path: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    log_path.write_text(
        "$ " + " ".join(cmd) + "\n\n" + proc.stdout + (
            "\n--- stderr ---\n" + proc.stderr if proc.stderr else ""
        ),
        encoding="utf-8",
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}"
        )
    return proc


def _latlon(east_m: float, north_m: float) -> tuple[float, float]:
    lat = DECISION_ORIGIN[0] + north_m / M_PER_DEG_LAT
    lon = DECISION_ORIGIN[1] + east_m / (
        M_PER_DEG_LAT * math.cos(math.radians(DECISION_ORIGIN[0]))
    )
    return lat, lon


def _png(path: Path, rgb: np.ndarray) -> None:
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    height, width, channels = rgb.shape
    if channels != 3:
        raise ValueError("png writer expects RGB")
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    blob = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(blob)


def _nearest(rgb: np.ndarray, factor: int) -> np.ndarray:
    return np.repeat(np.repeat(rgb, factor, axis=0), factor, axis=1)


def _ndvi_rgb(ndvi: np.ndarray) -> np.ndarray:
    """Map NDVI to brown / yellow / green. Stretch is fixed, not per-image."""
    stops = (
        (-0.4, (140, 82, 45)),
        (0.05, (214, 196, 92)),
        (0.55, (27, 110, 48)),
    )
    out = np.zeros(ndvi.shape + (3,), dtype=np.float64)
    for i in range(len(stops) - 1):
        a_v, a_c = stops[i]
        b_v, b_c = stops[i + 1]
        span = b_v - a_v
        t = np.clip((ndvi - a_v) / span, 0.0, 1.0)
        for c in range(3):
            band = a_c[c] + (b_c[c] - a_c[c]) * t
            if i == 0:
                out[..., c] = np.where(ndvi < a_v, a_c[c], band)
            else:
                out[..., c] = np.where(ndvi >= a_v, band, out[..., c])
    return np.clip(out, 0, 255).astype(np.uint8)


def _svg_header(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">',
        "<title>" + title.replace("&", "&amp;").replace("<", "&lt;") + "</title>",
        '<rect width="100%" height="100%" fill="#f7f5f0"/>',
        '<style>text{font-family:Georgia,serif;fill:#1c1915} .small{font-size:12px;fill:#4a453d} '
        ".axis{font-size:11px;fill:#4a453d}</style>",
    ]


def write_flight_svg(path: Path, plan, samples: list[dict]) -> None:
    width, height, pad = 820, 460, 48
    pts = np.vstack([FIELD_M, np.array([[s["east_m"], s["north_m"]] for s in samples])])
    minx, miny = pts.min(axis=0)
    maxx, maxy = pts.max(axis=0)
    scale = min((width - 2 * pad) / (maxx - minx), (height - 2 * pad - 28) / (maxy - miny))

    def xy(x: float, y: float) -> tuple[float, float]:
        return pad + (x - minx) * scale, height - pad - (y - miny) * scale

    poly = " ".join(f"{xy(x, y)[0]:.1f},{xy(x, y)[1]:.1f}" for x, y in FIELD_M)
    parts = _svg_header(width, height, "Synthetic field coverage playback")
    parts.append(
        '<text x="48" y="28" font-size="16">Coverage plan, kinematic playback '
        "(constant 5 m/s, no wind)</text>"
    )
    parts.append(f'<polygon points="{poly}" fill="#e4efe4" stroke="#1f4d32" stroke-width="1.5"/>')
    for i, line in enumerate(plan.lines):
        x1, y1 = xy(*line.start)
        x2, y2 = xy(*line.end)
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#1f6b3a" stroke-width="2"/>'
        )
        if i + 1 < len(plan.lines):
            a, b = xy(*line.end), xy(*plan.lines[i + 1].start)
            parts.append(
                f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                f'stroke="#8a8175" stroke-width="1" stroke-dasharray="4 3"/>'
            )
    step = max(1, len(samples) // 80)
    for s in samples[::step]:
        x, y = xy(s["east_m"], s["north_m"])
        color = "#1f6b3a" if s["on_line"] else "#8a8175"
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="{color}"/>')
    parts.append(
        '<text class="small" x="48" y="448">Green lines are photo passes. '
        "Dashed segments are turns, which collect nothing. Dots are 0.5 s samples.</text>"
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_line_svg(
    path: Path,
    title: str,
    xlabel: str,
    ylabel: str,
    series: list[tuple[str, list[float], list[float], str]],
    hline: tuple[float, str] | None = None,
) -> None:
    width, height = 760, 420
    left, right, top, bottom = 64, 24, 46, 48
    xs = [x for _, sx, _, _ in series for x in sx]
    ys = [y for _, _, sy, _ in series for y in sy]
    if hline is not None:
        ys.append(hline[0])
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmax == xmin:
        xmax = xmin + 1
    if ymax == ymin:
        ymax = ymin + 1
    pad_y = (ymax - ymin) * 0.08
    ymin -= pad_y
    ymax += pad_y

    def px(x: float, y: float) -> tuple[float, float]:
        X = left + (x - xmin) / (xmax - xmin) * (width - left - right)
        Y = top + (ymax - y) / (ymax - ymin) * (height - top - bottom)
        return X, Y

    parts = _svg_header(width, height, title)
    parts.append(f'<text x="{left}" y="26" font-size="16">{title}</text>')
    x0, y0 = px(xmin, ymin)
    x1, y1 = px(xmax, ymax)
    parts.append(
        f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y0:.1f}" stroke="#1c1915"/>'
    )
    parts.append(
        f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x0:.1f}" y2="{y1:.1f}" stroke="#1c1915"/>'
    )
    if hline is not None:
        hx0, hy = px(xmin, hline[0])
        hx1, _ = px(xmax, hline[0])
        parts.append(
            f'<line x1="{hx0:.1f}" y1="{hy:.1f}" x2="{hx1:.1f}" y2="{hy:.1f}" '
            f'stroke="#a33b24" stroke-dasharray="5 4"/>'
        )
        parts.append(
            f'<text class="small" x="{hx1 - 120:.1f}" y="{hy - 6:.1f}">{hline[1]}</text>'
        )
    legend_x = width - 210
    for i, (name, sx, sy, color) in enumerate(series):
        coords = " ".join(f"{px(x, y)[0]:.1f},{px(x, y)[1]:.1f}" for x, y in zip(sx, sy))
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{coords}"/>')
        ly = 48 + i * 16
        parts.append(f'<line x1="{legend_x}" y1="{ly}" x2="{legend_x + 18}" y2="{ly}" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<text class="small" x="{legend_x + 24}" y="{ly + 4}">{name}</text>')
    parts.append(f'<text class="axis" x="{(left + width - right) / 2:.0f}" y="{height - 12}">{xlabel}</text>')
    parts.append(
        f'<text class="axis" x="16" y="{(top + height - bottom) / 2:.0f}" '
        f'transform="rotate(-90 16 {(top + height - bottom) / 2:.0f})">{ylabel}</text>'
    )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def coverage_section() -> dict:
    swath_m, overlap, speed = 30.0, 0.2, 5.0
    sweep = []
    for deg in np.arange(0.0, 180.0, 5.0):
        plan = plan_coverage(FIELD_M, swath_m, overlap, float(deg))
        sweep.append(
            {
                "heading_deg": float(deg),
                "total_distance_m": plan.total_distance_m,
                "turn_distance_m": plan.turn_distance_m,
                "lines": len(plan.lines),
            }
        )
    heading = best_heading(FIELD_M, swath_m, overlap, step_deg=5.0)
    plan = plan_coverage(FIELD_M, swath_m, overlap, heading)
    gaps = float(coverage_gaps(plan, FIELD_M, samples=80))
    samples = _playback(plan, speed_ms=speed, dt_s=0.5)
    return {
        "swath_m": swath_m,
        "overlap": overlap,
        "spacing_m": swath_m * (1.0 - overlap),
        "best_heading_deg": heading,
        "area_ha": plan.area_ha,
        "lines": len(plan.lines),
        "line_distance_m": plan.line_distance_m,
        "turn_distance_m": plan.turn_distance_m,
        "total_distance_m": plan.total_distance_m,
        "duration_s_at_5ms_plus_4s_turns": plan.estimate_duration_s(speed, turn_penalty_s=4.0),
        "turn_penalty_s": 4.0,
        "turn_penalty_note": "placeholder in CoveragePlan.estimate_duration_s; not measured on an aircraft",
        "gap_fraction": gaps,
        "speed_ms": speed,
        "worst_heading": max(sweep, key=lambda row: row["total_distance_m"]),
        "sweep": sweep,
        "plan": plan,
        "samples": samples,
    }


def _playback(plan, speed_ms: float, dt_s: float) -> list[dict]:
    segments: list[tuple[tuple[float, float], tuple[float, float], bool]] = []
    for i, line in enumerate(plan.lines):
        segments.append((line.start, line.end, True))
        if i + 1 < len(plan.lines):
            segments.append((line.end, plan.lines[i + 1].start, False))
    samples: list[dict] = []
    t = 0.0
    cum = 0.0
    for start, end, on_line in segments:
        length = math.dist(start, end)
        if length == 0:
            continue
        n = max(1, int(math.floor(length / (speed_ms * dt_s))))
        for k in range(n):
            u = (k * speed_ms * dt_s) / length
            east = start[0] + (end[0] - start[0]) * u
            north = start[1] + (end[1] - start[1]) * u
            course = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
            samples.append(
                {
                    "t_s": round(t + k * dt_s, 3),
                    "east_m": east,
                    "north_m": north,
                    "on_line": on_line,
                    "course_deg_ccw_from_east": course,
                    "cum_dist_m": cum + k * speed_ms * dt_s,
                }
            )
        t += length / speed_ms
        cum += length
    if segments:
        end = segments[-1][1]
        samples.append(
            {
                "t_s": round(t, 3),
                "east_m": end[0],
                "north_m": end[1],
                "on_line": True,
                "course_deg_ccw_from_east": samples[-1]["course_deg_ccw_from_east"] if samples else 0.0,
                "cum_dist_m": cum,
            }
        )
    return samples


def decision_section() -> list[dict]:
    fence = TreatmentGeofence(DECISION_FIELD, treatment_buffer_m=10.0)
    lat, lon = _latlon(0.0, 0.0)

    def detection(**kw) -> Detection:
        det = Detection(
            label="weed",
            confidence=0.95,
            bbox=(0.4, 0.4, 0.6, 0.6),
            validated_locally=True,
        )
        det.world_lat = det.lat = lat
        det.world_lon = det.lon = lon
        det.position_uncertainty_m = 0.3
        det.georef_status = "OK"
        for key, value in kw.items():
            setattr(det, key, value)
        return det

    arming = ArmingState(
        operator_armed=True,
        payload_armed=True,
        armed_by="demo",
        armed_at=DECISION_NOW - 5,
        expires_at=DECISION_NOW + 60,
    )
    command = TreatmentCommand(
        command_id="cmd-demo",
        issued_at=DECISION_NOW - 1,
        expires_at=DECISION_NOW + 10,
        issued_by="demo",
        mission_id="demo",
    )
    pose = VehiclePose(
        lat=DECISION_ORIGIN[0],
        lon=DECISION_ORIGIN[1],
        alt_agl_m=30.0,
        heading_deg=0.0,
        timestamp=DECISION_NOW,
        h_acc_m=0.02,
    )
    outside_lat, outside_lon = _latlon(180.0, 0.0)
    cases = [
        ("all_gates_pass", detection(), arming, command, pose, MissionState.TREATMENT_ACTIVE),
        ("operator_not_armed", detection(), ArmingState(operator_armed=False, payload_armed=True, expires_at=DECISION_NOW + 60), command, pose, MissionState.TREATMENT_ACTIVE),
        ("model_not_validated", detection(validated_locally=False), arming, command, pose, MissionState.TREATMENT_ACTIVE),
        ("low_confidence", detection(confidence=0.4), arming, command, pose, MissionState.TREATMENT_ACTIVE),
        ("outside_geofence", detection(lat=outside_lat, lon=outside_lon, world_lat=outside_lat, world_lon=outside_lon), arming, command, pose, MissionState.TREATMENT_ACTIVE),
        ("mission_paused", detection(), arming, command, pose, MissionState.PAUSED),
        # TTL is 10 s, inside the 30 s cap, and expires_at is already past.
        ("command_expired", detection(), arming, TreatmentCommand(
            "cmd-old", DECISION_NOW - 20, DECISION_NOW - 10, "demo", "demo"
        ), pose, MissionState.TREATMENT_ACTIVE),
        ("nan_position", detection(lat=float("nan"), lon=lon, world_lat=float("nan"), world_lon=lon), arming, command, pose, MissionState.TREATMENT_ACTIVE),
    ]
    rows = []

    def clock() -> float:
        return DECISION_NOW

    for name, det, arm, cmd, pz, state in cases:
        # Fresh actuator and engine per case. Both share the frozen clock: the
        # actuator's heartbeat defaults to wall time, and a wall-time heartbeat
        # is in the future relative to DECISION_NOW, which the gate rejects.
        actuator = SimulatedActuator(now_fn=clock)
        eng = TreatmentDecisionEngine(
            actuator, fence, DECISION_ORIGIN, now_fn=clock
        )
        result = eng.process(
            det, arming=arm, command=cmd, pose=pz, mission_state=state
        )
        rows.append(
            {
                "case": name,
                "allowed": result.allowed,
                "reasons": result.reasons,
                "gates": result.gates,
                "simulated_actuator_commands": len(actuator.commands),
                "event_counts": eng.log.counts(),
                "simulated": True,
            }
        )
    return rows


def optics_rows() -> list[dict]:
    sys.path.insert(0, str(ROOT / "training"))
    from gsd_calculator import CAMERAS, native_gsd_cm

    cam = CAMERAS["imx708"]
    downscale = cam["width_px"] / 640
    rows = []
    for alt in (1, 2, 3, 5, 10, 15, 20, 30, 50, 80, 120):
        native = native_gsd_cm(cam, alt)
        rows.append(
            {
                "altitude_m": alt,
                "native_gsd_cm": native,
                "px_3cm_whole": 3.0 / (native * downscale),
                "px_3cm_tiled": 3.0 / native,
                "px_30cm_whole": 30.0 / (native * downscale),
                "px_30cm_tiled": 30.0 / native,
            }
        )
    return rows


def et0_and_balance() -> dict:
    brussels = DayInputs(
        doy=187,
        lat_deg=50 + 48 / 60,
        elevation_m=100,
        t_max=21.5,
        t_min=12.3,
        rh_max=84,
        rh_min=63,
        u2=wind_at_2m(10 / 3.6, 10.0),
        sunshine_h=9.25,
    )
    brussels_mm = et0_penman_monteith(brussels)

    # Scripted. A dry fortnight, then 18 mm on day 15. Not a forecast and not
    # a station record. Latitude is the FAO-style input the function requires.
    crop = get_crop("canola")
    soil = get_soil("loam")
    seeded = date(2026, 5, 20)
    start = date(2026, 6, 1)
    days = []
    for i in range(21):
        day = start + timedelta(days=i)
        days.append(
            Day(
                date=day,
                t_max=18.0 + (i % 6),
                t_min=6.0 + (i % 4),
                precip_mm=18.0 if i == 14 else 0.0,
                rh_max=80,
                rh_min=45,
                u2=2.0,
                source="scripted-demo",
            ).with_et0(lat=52.13, elevation_m=500)
        )
    balance = run_balance(crop, soil, seeded, days)
    return {
        "brussels_example_18_mm_day": brussels_mm,
        "brussels_published_mm_day": 3.9,
        "brussels_u2_m_s": brussels.u2,
        "balance_note": (
            "21 scripted days, canola on loam, seeded 2026-05-20, "
            "temperatures written in scripts/portfolio_demo.py. Not weather."
        ),
        "balance": [row.to_dict() if hasattr(row, "to_dict") else row.__dict__ for row in balance],
    }


def _frame_images(spool: Path, out: Path) -> dict:
    sidecars = sorted(spool.glob("*.json"))
    if not sidecars:
        raise SystemExit(f"fly produced no sidecars in {spool}")
    frames = []
    first_image = None
    first_meta = None
    for sidecar in sidecars:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        npy = sidecar.with_suffix(".npy")
        if first_image is None and npy.exists():
            first_image = np.load(npy)
            first_meta = meta
        telem = meta["telemetry"]
        ndvi = (meta.get("indices") or {}).get("ndvi") or {}
        frames.append(
            {
                "sequence": meta["sequence"],
                "lat": telem["lat"],
                "lon": telem["lon"],
                "alt_rel_m": telem["alt_rel_m"],
                "groundspeed_ms": telem["groundspeed_ms"],
                "fix_name": telem["fix_name"],
                "battery_pct": telem["battery_pct"],
                "qa_severity": meta["qa"]["severity"],
                "blur": next(c["value"] for c in meta["qa"]["checks"] if c["name"] == "blur"),
                "ndvi_mean": ndvi.get("mean"),
                "ndvi_min": ndvi.get("min"),
                "ndvi_max": ndvi.get("max"),
                "ndvi_calibrated": ndvi.get("calibrated"),
                "detections": [
                    {
                        "label": d["label"],
                        "confidence": d["confidence"],
                        "validated_locally": d["validated_locally"],
                        "may_drive_treatment": d["may_drive_treatment"],
                    }
                    for d in meta["detections"]
                ],
                "decision_support_only": meta["decision_support_only"],
                "environment_c": (meta.get("environment") or {}).get("temperature_c"),
            }
        )
        npy.unlink(missing_ok=True)
    if first_image is None or first_meta is None:
        raise SystemExit("spool had sidecars but no image array")

    bands = first_meta["bands"]
    stack = BandStack(first_image, bands)
    ndvi = compute(stack, "ndvi", calibrated=False)
    rgb = np.stack(
        [first_image[:, :, bands.index(name)] for name in ("red", "green", "blue")],
        axis=-1,
    )
    _png(out / "scene_rgb.png", _nearest(rgb, 2))
    _png(out / "ndvi.png", _nearest(_ndvi_rgb(ndvi.array), 2))
    summary = ndvi.summary()
    summary["source"] = "first spooled frame of agri-edge fly --simulate"
    summary["display_scale"] = "nearest-neighbour 2x of the 320x240 frame"
    summary["calibrated"] = False
    return {"frames": frames, "ndvi_frame": summary}


def write_outputs(out: Path, summary: dict, coverage: dict, optics: list[dict], agronomy: dict) -> None:
    samples = coverage.pop("samples")
    plan = coverage.pop("plan")
    write_flight_svg(out / "flight_track.svg", plan, samples)
    with (out / "telemetry.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "t_s",
                "east_m",
                "north_m",
                "on_line",
                "course_deg_ccw_from_east",
                "cum_dist_m",
            ],
        )
        writer.writeheader()
        for row in samples:
            writer.writerow(
                {
                    **row,
                    "on_line": int(row["on_line"]),
                    "east_m": f"{row['east_m']:.3f}",
                    "north_m": f"{row['north_m']:.3f}",
                    "course_deg_ccw_from_east": f"{row['course_deg_ccw_from_east']:.2f}",
                    "cum_dist_m": f"{row['cum_dist_m']:.3f}",
                }
            )

    sweep = coverage["sweep"]
    write_line_svg(
        out / "heading_sweep.svg",
        "Total distance vs flight-line heading",
        "heading, degrees counter-clockwise from east",
        "total distance, m",
        [("total distance", [r["heading_deg"] for r in sweep], [r["total_distance_m"] for r in sweep], "#1f6b3a")],
    )
    write_line_svg(
        out / "gsd.svg",
        "Pixels across the target, Pi Camera Module 3",
        "altitude AGL, m",
        "pixels across the target",
        [
            ("3 cm, whole frame", [r["altitude_m"] for r in optics], [r["px_3cm_whole"] for r in optics], "#a33b24"),
            ("3 cm, tiled", [r["altitude_m"] for r in optics], [r["px_3cm_tiled"] for r in optics], "#c47b2b"),
            ("30 cm, whole frame", [r["altitude_m"] for r in optics], [r["px_30cm_whole"] for r in optics], "#8a8175"),
            ("30 cm, tiled", [r["altitude_m"] for r in optics], [r["px_30cm_tiled"] for r in optics], "#1f6b3a"),
        ],
        hline=(20.0, "20 px floor"),
    )
    balance = agronomy["balance"]
    write_line_svg(
        out / "water_balance.svg",
        "Scripted canola water balance (not weather)",
        "day index",
        "millimetres",
        [
            ("root-zone depletion", list(range(len(balance))), [r["depletion_mm"] for r in balance], "#1f6b3a"),
            ("readily available water", list(range(len(balance))), [r["raw_mm"] for r in balance], "#a33b24"),
            ("rain", list(range(len(balance))), [r["rain"] for r in balance], "#3d6f9c"),
        ],
    )

    (out / "coverage.json").write_text(json.dumps({k: v for k, v in coverage.items()}, indent=2), encoding="utf-8")
    (out / "optics.csv").write_text(
        "altitude_m,native_gsd_cm,px_3cm_whole,px_3cm_tiled,px_30cm_whole,px_30cm_tiled\n"
        + "\n".join(
            f"{r['altitude_m']},{r['native_gsd_cm']:.6f},{r['px_3cm_whole']:.4f},"
            f"{r['px_3cm_tiled']:.4f},{r['px_30cm_whole']:.4f},{r['px_30cm_tiled']:.4f}"
            for r in optics
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "decisions.json").write_text(json.dumps(summary["decisions"], indent=2), encoding="utf-8")
    (out / "agronomy.json").write_text(json.dumps(agronomy, indent=2), encoding="utf-8")
    (out / "frames.json").write_text(json.dumps(summary["pipeline"]["frames"], indent=2), encoding="utf-8")
    public = {
        k: v
        for k, v in summary.items()
        if k != "pipeline" or True
    }
    # Drop the bulky per-frame list from the top-level summary; frames.json has it.
    pipeline = dict(public["pipeline"])
    pipeline.pop("frames", None)
    public["pipeline"] = pipeline
    public["coverage"] = {k: v for k, v in coverage.items() if k != "sweep"}
    (out / "summary.json").write_text(json.dumps(public, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "proof")
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--config", type=Path, default=ROOT / "config" / "demo.yaml")
    args = ap.parse_args()
    if args.frames < 1:
        raise SystemExit("--frames must be >= 1")

    out = args.out
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    spool = out / "_spool"
    if spool.exists():
        shutil.rmtree(spool)
    spool.mkdir()

    raw = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    try:
        spool_cfg = spool.relative_to(ROOT)
    except ValueError:
        spool_cfg = spool
    raw.setdefault("spool", {})["spool_dir"] = str(spool_cfg)
    resolved = out / "demo.resolved.yaml"
    resolved.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    py = sys.executable
    _run([py, "-m", "agri_edge.cli", "-c", str(resolved), "preflight", "--simulate"], out / "cli_preflight.log")
    fly = _run(
        [
            py, "-m", "agri_edge.cli", "-c", str(resolved), "fly", "--simulate",
            "--frames", str(args.frames), "--bands", BANDS,
        ],
        out / "cli_fly.log",
    )
    _run([py, "-m", "agri_edge.cli", "indices", "red,green,nir,red-edge"], out / "cli_indices.log")
    _run(
        [py, "-m", "agri_edge.cli", "indices", BANDS],
        out / "cli_indices_with_blue.log",
    )
    _run([py, str(ROOT / "training" / "gsd_calculator.py"), "--camera", "imx708", "--target-size", "3"], out / "gsd_3cm.log")
    _run([py, str(ROOT / "training" / "gsd_calculator.py"), "--camera", "imx708", "--target-size", "30"], out / "gsd_30cm.log")
    _run(
        [py, str(ROOT / "training" / "motion_budget.py"), "--camera", "imx708", "--altitude", "30", "--target-size", "30"],
        out / "motion_budget.log",
    )

    images = _frame_images(spool, out)
    # The index is small and useful; the arrays are not.
    index = spool / "index.jsonl"
    if index.exists():
        shutil.copy(index, out / "spool_index.jsonl")
    shutil.rmtree(spool)

    coverage = coverage_section()
    decisions = decision_section()
    optics = optics_rows()
    agronomy = et0_and_balance()
    sitl_bin = ROOT / "vendor" / "ardupilot" / "build" / "sitl" / "bin" / "arducopter"

    frames = images["frames"]
    lats = [f["lat"] for f in frames]
    lons = [f["lon"] for f in frames]
    # East displacement of the straight-line simulator, from the first and last fix.
    mean_lat = sum(lats) / len(lats)
    east_m = (lons[-1] - lons[0]) * M_PER_DEG_LAT * math.cos(math.radians(mean_lat))

    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_commit": _git_sha(),
        "simulated": True,
        "hardware": False,
        "sitl_ran": False,
        "sitl_binary_present": sitl_bin.exists(),
        "commands": [
            "python -m agri_edge.cli -c config/demo.yaml preflight --simulate",
            f"python -m agri_edge.cli -c config/demo.yaml fly --simulate --frames {args.frames} --bands {BANDS}",
            "python -m agri_edge.cli indices red,green,nir,red-edge",
            f"python -m agri_edge.cli indices {BANDS}",
            "python training/gsd_calculator.py --camera imx708 --target-size 3",
            "python training/gsd_calculator.py --camera imx708 --target-size 30",
            "python training/motion_budget.py --camera imx708 --altitude 30 --target-size 30",
        ],
        "fly_stdout_tail": "\n".join(fly.stdout.strip().splitlines()[-25:]),
        "pipeline": {
            "frames_requested": args.frames,
            "captured": len(frames),
            "qa_ok": sum(1 for f in frames if f["qa_severity"] == "ok"),
            "decision_support_only": all(f["decision_support_only"] for f in frames),
            "validated_locally": any(
                d["validated_locally"] for f in frames for d in f["detections"]
            ),
            "may_drive_treatment": any(
                d["may_drive_treatment"] for f in frames for d in f["detections"]
            ),
            "detection_count": sum(len(f["detections"]) for f in frames),
            "straight_line_east_m": east_m,
            "ndvi_means": [f["ndvi_mean"] for f in frames],
            "blur_values": [f["blur"] for f in frames],
            "frames": frames,
            "ndvi_frame": images["ndvi_frame"],
        },
        "decisions": decisions,
        "decisions_allowed": sum(1 for d in decisions if d["allowed"]),
        "decisions_refused": sum(1 for d in decisions if not d["allowed"]),
        "et0_brussels_mm_day": agronomy["brussels_example_18_mm_day"],
        "coverage_preview": {
            "lines": coverage["lines"],
            "gap_fraction": coverage["gap_fraction"],
            "best_heading_deg": coverage["best_heading_deg"],
            "total_distance_m": coverage["total_distance_m"],
        },
    }
    write_outputs(out, summary, coverage, optics, agronomy)
    print(json.dumps({k: summary[k] for k in ("pipeline", "decisions_allowed", "decisions_refused", "et0_brussels_mm_day", "coverage_preview", "sitl_ran")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
