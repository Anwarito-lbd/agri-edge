"""Simulated flight, optics, spray-flow, drift-advisory, and ML envelope suite.

Exercises the real repository modules -- NO invented numbers:
  * mechanical.airframe_spec     : 650 mm X-quad AUW, thrust margin, endurance,
                                   blade-pass vs 35 Hz isolator transmissibility,
                                   and leg-clearance view pyramid
  * training.gsd_calculator      : IMX708 / IMX477 / IMX296 / M3M pinhole GSD &
                                   whole-frame vs tiled altitude ceilings
  * training.motion_budget       : motion-smear shutter limits & rolling skew
  * agri_edge.geo.geofence       : outer + hole polygons, spray_flow_l_min, coverage_rate_ha_h
  * agri_edge.geo.coverage       : boustrophedon flight lines & heading sweep
  * agri_edge.geo.georeference   : ZYX body-to-NED ray-plane projection (3D frustums)
  * agri_edge.sensors.environment: Magnus dew point, Tetens VPD, wind-first spray_advisory

All outputs are SIMULATED physics-model computations grounded in the codebase;
no physical aircraft flight or pump hardware test is claimed.

Usage:
    python scripts/simulate_airframe_physics.py
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "training"))

from gsd_calculator import CAMERAS, native_gsd_cm  # noqa: E402
from mechanical.airframe_spec import (  # noqa: E402
    Airframe,
    Battery,
    MassBudget,
    blade_pass_hz,
    clearance_radius_m,
    endurance_min,
    hectares_per_battery,
    max_exposure_s,
    summary as airframe_summary,
)
from motion_budget import READOUT_S  # noqa: E402

from agri_edge.geo.coverage import best_heading, coverage_gaps, plan_coverage  # noqa: E402
from agri_edge.geo.geofence import (  # noqa: E402
    TreatmentGeofence,
    coverage_rate_ha_h,
    spray_flow_l_min,
)
from agri_edge.geo.georeference import IMX708, pixel_ray_ned  # noqa: E402
from agri_edge.sensors.environment import EnvironmentReading  # noqa: E402

PROOF_DIR = ROOT / "docs" / "proof"
WEB_PROOF_DIR = ROOT / "apps" / "web" / "public" / "proof"

# Style palette aligned with apps/web industrial cobalt + agronomic slate
NAVY = "#173D68"
BLUE = "#2B6CB0"
TEAL = "#1F7A6E"
AMBER = "#D97706"
RED = "#C53030"
SLATE = "#4A5568"
BG = "#F8FAFC"


def _save_fig(fig: plt.Figure, filename: str, proof_dir: Path, mirror_web: bool) -> Path:
    proof_dir.mkdir(parents=True, exist_ok=True)
    out_doc = proof_dir / filename
    fig.savefig(out_doc, dpi=180, bbox_inches="tight", facecolor="white")
    if mirror_web:
        WEB_PROOF_DIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(WEB_PROOF_DIR / filename, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_doc


def simulate_airframe_and_vibration(af: Airframe, proof_dir: Path, mirror_web: bool) -> dict:
    """Compute payload, endurance, battery, vibration, and gear-clearance curves."""
    base_mass = MassBudget()
    base_g = base_mass.total_g

    payload_adds = np.linspace(0, 1400, 57)
    auws_kg = (base_g + payload_adds) / 1000.0
    twr = [af.propulsion.thrust_to_weight(base_g + dp) for dp in payload_adds]
    hover_frac = [af.propulsion.hover_throttle_fraction(base_g + dp) for dp in payload_adds]

    bat_10 = Battery(cells=6, capacity_ah=10.0)
    bat_16 = Battery(cells=6, capacity_ah=16.0)
    end_10 = [endurance_min(bat_10.usable_wh, af.propulsion.hover_power_w(base_g + dp)) for dp in payload_adds]
    end_16 = [endurance_min(bat_16.usable_wh, af.propulsion.hover_power_w(base_g + dp)) for dp in payload_adds]
    ha_10 = [
        hectares_per_battery(af.survey_agl_m, af.survey_speed_ms, max(0.0, e - 3.0), af.survey_overlap)
        for e in end_10
    ]
    ha_16 = [
        hectares_per_battery(af.survey_agl_m, af.survey_speed_ms, max(0.0, e - 3.0), af.survey_overlap)
        for e in end_16
    ]

    # Vibration isolator transmissibility curve T(r) with zeta = 0.10 nominal elastomer
    fn = af.isolator_target_hz
    freqs = np.linspace(5.0, 260.0, 400)
    r = freqs / fn
    zeta = 0.10
    trans = np.sqrt((1.0 + (2.0 * zeta * r) ** 2) / ((1.0 - r**2) ** 2 + (2.0 * zeta * r) ** 2))
    bpf_hover = blade_pass_hz(af.hover_rpm, af.rotors.blades)
    bpf_full = blade_pass_hz(af.full_throttle_rpm, af.rotors.blades)

    # View pyramid clearance cross-section at foot depth below lens
    drop = af.lens_drop_below_legs_m
    az_deg = np.linspace(0.0, 360.0, 361)
    req_r_mm = np.array([clearance_radius_m(drop, float(a)) * 1000.0 for a in az_deg])
    leg_angles_rad = np.radians([af.leg_azimuth_deg + j * 90.0 for j in range(4)])
    leg_r_mm = af.leg_span_radius_m * 1000.0

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 9.2), dpi=180)
    fig.suptitle(
        "650 mm Scouting Airframe Physics & Mechanical Margins (SIMULATED — mechanical/airframe_spec.py)",
        fontsize=13,
        fontweight="bold",
        color=NAVY,
        y=0.98,
    )

    # Panel A: Thrust-to-Weight & Hover Throttle vs Added Payload
    ax = axes[0, 0]
    ax2 = ax.twinx()
    l1 = ax.plot(payload_adds, twr, color=NAVY, lw=2.2, label="Thrust-to-Weight (TWR)")
    ax.axhline(2.0, color=RED, ls="--", lw=1.2, label="Min TWR gate (>= 2.0:1)")
    l2 = ax2.plot(payload_adds, np.array(hover_frac) * 100.0, color=TEAL, lw=2.0, label="Hover throttle (%)")
    ax2.axhline(60.0, color=AMBER, ls=":", lw=1.2, label="Max hover gate (<= 60%)")
    ax.scatter([0], [af.propulsion.thrust_to_weight(base_g)], color=NAVY, s=45, zorder=5)
    ax.annotate(
        f"Baseline 3.43 kg\nTWR {af.propulsion.thrust_to_weight(base_g):.2f}:1",
        xy=(0, af.propulsion.thrust_to_weight(base_g)),
        xytext=(210, 2.34),
        fontsize=8.5,
        arrowprops={"arrowstyle": "->", "color": NAVY, "lw": 0.9},
    )
    ax.set_title("A. Added Payload vs Control Authority", fontweight="bold", color=NAVY)
    ax.set_xlabel("Added payload above baseline 3,432 g (g)")
    ax.set_ylabel("Thrust-to-Weight Ratio", color=NAVY)
    ax2.set_ylabel("Hover Throttle (%)", color=TEAL)
    ax.grid(True, alpha=0.25)
    lines = l1 + l2
    ax.legend(lines, [ln.get_label() for ln in lines], loc="upper right", fontsize=8)

    # Panel B: Endurance & Hectares per Battery
    ax = axes[0, 1]
    ax.plot(payload_adds, end_10, color=NAVY, lw=2.2, label="Endurance 6S 10 Ah (min)")
    ax.plot(payload_adds, end_16, color=BLUE, lw=2.0, ls="--", label="Endurance 6S 16 Ah (min)")
    axb = ax.twinx()
    axb.plot(payload_adds, ha_10, color=TEAL, lw=1.8, label="Area/bat 6S 10 Ah (ha)")
    axb.plot(payload_adds, ha_16, color=AMBER, lw=1.8, ls="-.", label="Area/bat 6S 16 Ah (ha)")
    ax.set_title("B. Endurance & Survey Area per Battery (30 m AGL, 5 m/s)", fontweight="bold", color=NAVY)
    ax.set_xlabel("Added payload (g)")
    ax.set_ylabel("Total Hover Endurance (min)", color=NAVY)
    axb.set_ylabel("Survey Area / Battery (ha)", color=TEAL)
    ax.grid(True, alpha=0.25)
    h1, lbl1 = ax.get_legend_handles_labels()
    h2, lbl2 = axb.get_legend_handles_labels()
    ax.legend(h1 + h2, lbl1 + lbl2, loc="upper right", fontsize=7.5)

    # Panel C: Vibration Isolation Transmissibility
    ax = axes[1, 0]
    ax.semilogy(freqs, trans, color=NAVY, lw=2.2, label="Mount transmissibility (zeta=0.10)")
    ax.axhline(1.0, color=SLATE, ls="--", lw=1.0, label="Unity gain (0 dB)")
    ax.axvline(fn, color=AMBER, ls="--", lw=1.3, label=f"Isolator fn = {fn:.0f} Hz (k={af.vibration()['isolator_k_n_per_mm_each']:.2f} N/mm)")
    ax.axvline(bpf_hover, color=TEAL, ls="-.", lw=1.5, label=f"Hover blade-pass = {bpf_hover:.0f} Hz ({bpf_hover/fn:.1f}x fn)")
    ax.axvline(bpf_full, color=RED, ls=":", lw=1.4, label=f"Full-throttle blade-pass = {bpf_full:.0f} Hz")
    ax.set_ylim(0.02, 8.0)
    ax.set_title("C. Blade-Pass Excitation vs 35 Hz Payload Isolator", fontweight="bold", color=NAVY)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Transmissibility |X_payload / X_frame| (log)")
    ax.grid(True, which="both", alpha=0.22)
    ax.legend(loc="upper right", fontsize=7.8)

    # Panel D: Bottom Clearance & IMX708 View Pyramid Polar Cross-Section
    ax = axes[1, 1]
    ax.remove()
    ax_pol = fig.add_subplot(2, 2, 4, projection="polar")
    ax_pol.plot(np.radians(az_deg), req_r_mm, color=RED, lw=2.0, label=f"IMX708 FOV pyramid @ drop={drop*1000:.0f} mm")
    ax_pol.fill(np.radians(az_deg), req_r_mm, color=RED, alpha=0.12)
    ax_pol.plot(np.radians(az_deg), np.full_like(az_deg, leg_r_mm), color=SLATE, ls="--", lw=1.1, label=f"Gear circle R={leg_r_mm:.0f} mm")
    ax_pol.scatter(leg_angles_rad, [leg_r_mm] * 4, color=TEAL, s=85, zorder=5, label="4 Landing gear feet (outside FOV)")
    ax_pol.set_title(
        f"D. Camera View-Pyramid Clearance ({af.leg_clearance()['margin_m']*1000:.0f} mm margin)",
        fontweight="bold",
        color=NAVY,
        pad=14,
    )
    ax_pol.set_ylim(0, 310)
    ax_pol.legend(loc="upper left", bbox_to_anchor=(0.82, 1.04), fontsize=7.6)

    fig.tight_layout(rect=[0, 0.03, 1, 0.94])
    _save_fig(fig, "airframe_endurance_physics.png", proof_dir, mirror_web)

    return {
        "airframe_baseline": airframe_summary(af),
        "auws_kg_range": [round(float(auws_kg[0]), 3), round(float(auws_kg[-1]), 3)],
        "max_payload_for_twr_2_0_g": int(
            payload_adds[np.max(np.where(np.array(twr) >= 2.0))]
        ),
        "endurance_10ah_min_at_baseline": round(float(end_10[0]), 2),
        "endurance_16ah_min_at_baseline": round(float(end_16[0]), 2),
    }


def simulate_georeference_and_3d_flight(af: Airframe, proof_dir: Path, mirror_web: bool) -> dict:
    """Plan boustrophedon coverage on a notched field with an exclusion hole & project 3D rays."""
    outer = np.array([
        [0.0, 0.0],
        [420.0, 0.0],
        [420.0, 140.0],
        [270.0, 140.0],
        [270.0, 260.0],
        [0.0, 260.0],
    ])
    slough_hole = np.array([
        [110.0, 90.0],
        [175.0, 90.0],
        [175.0, 155.0],
        [110.0, 155.0],
    ])
    origin = (50.4452, -104.6189)  # Regina / Saskatchewan reference lat/lon
    fence = TreatmentGeofence(
        outer,
        treatment_buffer_m=10.0,
        holes_m=[slough_hole],
    )

    swath_m = af.performance()["swath_m"]
    heading = best_heading(outer, swath_m=swath_m, overlap=af.survey_overlap, step_deg=5.0)
    plan = plan_coverage(outer, swath_m=swath_m, overlap=af.survey_overlap, heading_deg=heading, inset_m=10.0)
    gaps = coverage_gaps(plan, outer, samples=60)

    # Create a 2-subplot figure: Left 3D flight trajectory + camera ray frustums, Right attitude projection drift
    fig = plt.figure(figsize=(13.2, 6.2), dpi=180)
    fig.suptitle(
        "3D Boustrophedon Survey Geometry, Treatment Geofence & Ray-Plane Georeferencing (SIMULATED)",
        fontsize=12.8,
        fontweight="bold",
        color=NAVY,
        y=0.98,
    )

    ax3d = fig.add_subplot(1, 2, 1, projection="3d")
    # Plot outer field & slough exclusion hole at z=0
    closed_outer = np.vstack([outer, outer[0]])
    closed_hole = np.vstack([slough_hole, slough_hole[0]])
    ax3d.plot(closed_outer[:, 0], closed_outer[:, 1], np.zeros(len(closed_outer)), color=NAVY, lw=2.0, label="Flight boundary")
    ax3d.plot(closed_hole[:, 0], closed_hole[:, 1], np.zeros(len(closed_hole)), color=RED, lw=1.8, ls="--", label="Exclusion hole + 10 m buffer")

    agl = af.survey_agl_m
    waypoints_x, waypoints_y, waypoints_z = [], [], []
    for i, ln in enumerate(plan.lines):
        waypoints_x.extend([ln.start[0], ln.end[0]])
        waypoints_y.extend([ln.start[1], ln.end[1]])
        waypoints_z.extend([agl, agl])
        ax3d.plot([ln.start[0], ln.end[0]], [ln.start[1], ln.end[1]], [agl, agl], color=TEAL, lw=2.0)
        if i + 1 < len(plan.lines):
            nxt = plan.lines[i + 1]
            ax3d.plot([ln.end[0], nxt.start[0]], [ln.end[1], nxt.start[1]], [agl, agl], color=AMBER, lw=1.1, ls=":")

    # Project 3D IMX708 FOV frustums from two sample points (level vs 10 deg roll)
    sample_poses = [
        (plan.lines[1].start[0] * 0.4 + plan.lines[1].end[0] * 0.6,
         plan.lines[1].start[1] * 0.4 + plan.lines[1].end[1] * 0.6,
         0.0, 0.0, heading, BLUE, "Nadir FOV frustum (0 deg)"),
        (plan.lines[2].start[0] * 0.65 + plan.lines[2].end[0] * 0.35,
         plan.lines[2].start[1] * 0.65 + plan.lines[2].end[1] * 0.35,
         10.0, 2.0, heading, AMBER, "Tilted frustum (10 deg roll)"),
    ]
    corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    for sx, sy, r_deg, p_deg, y_deg, col, lbl in sample_poses:
        gpts = []
        for u, v in corners:
            ray = pixel_ray_ned(u, v, IMX708, roll_deg=r_deg, pitch_deg=p_deg, yaw_deg=y_deg)
            t = agl / ray[2]
            # NED -> ENU: x=East(ray[1]), y=North(ray[0])
            gx = sx + ray[1] * t
            gy = sy + ray[0] * t
            gpts.append((gx, gy))
            ax3d.plot([sx, gx], [sy, gy], [agl, 0.0], color=col, lw=0.8, alpha=0.65)
        garr = np.array(gpts + [gpts[0]])
        ax3d.plot(garr[:, 0], garr[:, 1], np.zeros(5), color=col, lw=1.8, label=lbl)
        ax3d.scatter([sx], [sy], [agl], color=col, s=38)

    # Check simulated weed detections against dual geofence
    det_points = [(65.0, 55.0), (142.0, 122.0), (416.0, 80.0), (220.0, 210.0)]
    in_pts = [pt for pt in det_points if fence.may_treat(pt)]
    out_pts = [pt for pt in det_points if not fence.may_treat(pt)]
    if in_pts:
        ax3d.scatter([p[0] for p in in_pts], [p[1] for p in in_pts], [0] * len(in_pts), color=TEAL, marker="^", s=55, label="Geofence OK (may_treat)")
    if out_pts:
        ax3d.scatter([p[0] for p in out_pts], [p[1] for p in out_pts], [0] * len(out_pts), color=RED, marker="x", s=65, label="Geofence blocked (hole/edge)")

    ax3d.set_xlabel("East (m)")
    ax3d.set_ylabel("North (m)")
    ax3d.set_zlabel("AGL (m)")
    ax3d.set_zlim(0, 42)
    ax3d.view_init(elev=26, azim=-58)
    ax3d.set_title(
        f"3D Flight Lines ({len(plan.lines)} passes, {plan.area_ha:.2f} ha, {gaps*100:.2f}% edge gap)",
        fontweight="bold",
        color=NAVY,
        fontsize=10.5,
    )
    ax3d.legend(loc="upper left", fontsize=7.2)

    # Right subplot: Flat-ground shortcut error vs Ray-Plane georeference over Roll angle
    ax2 = fig.add_subplot(1, 2, 2)
    rolls = np.linspace(0.0, 18.0, 37)
    shift_30m = []
    shift_45m = []
    for rd in rolls:
        ray30 = pixel_ray_ned(0.5, 0.5, IMX708, roll_deg=float(rd), pitch_deg=0.0, yaw_deg=0.0)
        shift_30m.append(math.hypot(ray30[0], ray30[1]) * (30.0 / ray30[2]))
        shift_45m.append(math.hypot(ray30[0], ray30[1]) * (45.0 / ray30[2]))

    ax2.plot(rolls, shift_30m, color=NAVY, lw=2.3, label="30 m AGL centre shift (m)")
    ax2.plot(rolls, shift_45m, color=BLUE, lw=2.0, ls="--", label="45 m AGL centre shift (m)")
    ax2.axvline(10.0, color=RED, ls=":", lw=1.4, label="QA max tilt threshold (10 deg -> 5.3 m @ 30 m)")
    ax2.axhline(5.29, color=SLATE, ls="--", lw=1.0, alpha=0.7)
    ax2.set_title("ZYX Ray-Plane Centre Displacement vs Aircraft Roll", fontweight="bold", color=NAVY, fontsize=10.5)
    ax2.set_xlabel("Aircraft Roll Angle (deg)")
    ax2.set_ylabel("Principal-Point Ground Displacement (m)")
    ax2.grid(True, alpha=0.25)
    ax2.legend(loc="upper left", fontsize=8.3)

    fig.tight_layout(rect=[0, 0.02, 1, 0.94])
    _save_fig(fig, "georef_3d_trajectory.png", proof_dir, mirror_web)

    return {
        "origin_lat_lon": list(origin),
        "plan": plan.as_dict(),
        "coverage_gaps_fraction": round(float(gaps), 4),
        "shift_at_10deg_roll_30m_agl_m": round(float(shift_30m[int(np.argmin(np.abs(rolls - 10.0)))]), 3),
        "geofence_allowed_points": len(in_pts),
        "geofence_blocked_points": len(out_pts),
    }


def simulate_spray_drift_and_flow(proof_dir: Path, mirror_web: bool) -> dict:
    """Map spray_advisory wind/VPD physics and Q = R * v * W * 0.006 hydraulic curves."""
    winds = np.linspace(0.0, 7.5, 90)
    temps = np.linspace(2.0, 36.0, 70)
    rh_fixed = 55.0

    # Grid values: 0 = ok, 1 = caution, 2 = poor
    regime = np.zeros((len(temps), len(winds)), dtype=int)
    code_map = {"ok": 0, "caution": 1, "poor": 2, "unknown": 3}
    now_ts = 1_700_000_000.0
    for i, t_c in enumerate(temps):
        for j, w_ms in enumerate(winds):
            r = EnvironmentReading(
                timestamp=now_ts,
                sensor="sim_bme280_mast",
                temperature_c=float(t_c),
                humidity_pct=rh_fixed,
                wind_speed_ms=float(w_ms),
                wind_direction_deg=270.0,
                wind_source="ground_mast",
                wind_measured_at=now_ts - 15.0,
            )
            adv, _ = r.spray_advisory(now=now_ts)
            regime[i, j] = code_map[adv]

    # Verify airframe wind rejection explicitly
    airframe_test = EnvironmentReading(
        timestamp=now_ts,
        sensor="onboard",
        temperature_c=20.0,
        humidity_pct=60.0,
        wind_speed_ms=2.5,
        wind_direction_deg=180.0,
        wind_source="airframe",
        wind_measured_at=now_ts,
    ).spray_advisory(now=now_ts)

    speeds = np.linspace(1.0, 12.0, 50)
    swath_w = 8.0
    rates = [10.0, 20.0, 40.0, 60.0]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 5.4), dpi=180)
    fig.suptitle(
        "Meteorological Spray-Window Gates & Feed-Forward Pump Flow Physics (SIMULATED)",
        fontsize=12.8,
        fontweight="bold",
        color=NAVY,
        y=0.98,
    )

    from matplotlib.colors import ListedColormap

    cmap = ListedColormap(["#D1FAE5", "#FEF3C7", "#FEE2E2"])
    ax1.imshow(
        regime,
        origin="lower",
        aspect="auto",
        extent=[winds[0], winds[-1], temps[0], temps[-1]],
        cmap=cmap,
        vmin=0,
        vmax=2,
    )
    ax1.axvline(0.83, color=RED, ls="--", lw=1.2)
    ax1.axvline(4.17, color=AMBER, ls="--", lw=1.2)
    ax1.axvline(5.56, color=RED, ls="-", lw=1.2)
    ax1.axhline(30.0, color=RED, ls=":", lw=1.2)
    ax1.axhline(5.0, color=AMBER, ls=":", lw=1.2)
    ax1.text(0.15, 17.0, "Inversion\n<0.83 m/s\n(POOR)", fontsize=8, color=RED, fontweight="bold")
    ax1.text(1.75, 17.5, "OK\nWindow", fontsize=9.5, color=TEAL, fontweight="bold")
    ax1.text(4.35, 17.5, "Caution\n>15 km/h", fontsize=8, color=AMBER, fontweight="bold")
    ax1.text(5.8, 17.5, "Too Windy\n>20 km/h", fontsize=8, color=RED, fontweight="bold")
    ax1.set_title("A. spray_advisory(T, wind) @ 55% RH", fontweight="bold", color=NAVY, fontsize=10.5)
    ax1.set_xlabel("Mast Wind Speed (m/s)")
    ax1.set_ylabel("Ambient Air Temperature (C)")
    ax1.legend(
        handles=[
            Patch(facecolor="#D1FAE5", edgecolor=TEAL, label="OK (spray allowed by met gate)"),
            Patch(facecolor="#FEF3C7", edgecolor=AMBER, label="CAUTION (low T / upper wind)"),
            Patch(facecolor="#FEE2E2", edgecolor=RED, label="POOR (inversion calm, >5.56 m/s, T>30 C)"),
        ],
        loc="upper right",
        fontsize=7.6,
    )

    colors = [SLATE, NAVY, BLUE, TEAL]
    for idx, rate in enumerate(rates):
        q = [spray_flow_l_min(rate, float(v), swath_w) for v in speeds]
        ax2.plot(speeds, q, color=colors[idx], lw=2.2, label=f"R = {rate:.0f} L/ha @ W = {swath_w:.0f} m")
    q_ref = spray_flow_l_min(20.0, 8.0, 8.0)
    ax2.scatter([8.0], [q_ref], color=RED, s=55, zorder=6)
    ax2.annotate(
        f"Report bench pt:\n20 L/ha @ 8 m/s, 8 m = {q_ref:.2f} L/min\n({coverage_rate_ha_h(8.0, 8.0):.2f} ha/h raw)",
        xy=(8.0, q_ref),
        xytext=(3.2, q_ref + 9.0),
        fontsize=8.2,
        arrowprops={"arrowstyle": "->", "color": RED, "lw": 1.0},
    )
    ax2.set_title("B. Nozzle Flow Q = R * v * W * 0.006 (Water Bench Spec)", fontweight="bold", color=NAVY, fontsize=10.5)
    ax2.set_xlabel("Ground Speed v (m/s)")
    ax2.set_ylabel("Required Pump Flow Q (L/min)")
    ax2.grid(True, alpha=0.25)
    ax2.legend(loc="upper left", fontsize=8.3)

    fig.tight_layout(rect=[0, 0.02, 1, 0.93], w_pad=2.5)
    _save_fig(fig, "spray_drift_envelope.png", proof_dir, mirror_web)

    return {
        "airframe_wind_rejection": {"status": airframe_test[0], "reason": airframe_test[1]},
        "bench_point_20lha_8ms_8m_l_min": round(float(q_ref), 3),
        "raw_coverage_rate_8ms_8m_ha_h": round(float(coverage_rate_ha_h(8.0, 8.0)), 2),
    }


def simulate_ml_and_optics_envelope(proof_dir: Path, mirror_web: bool) -> dict:
    """Plot exact verified Model Card test APs & pinhole/motion optical envelopes."""
    # Grounded strictly in models/*_CARD.md (zero fabricated metrics)
    model_labels = [
        "Sheep\n(YOLOX-s)\n5,603 GT",
        "ImageWeeds\n(binary)\n306 GT",
        "ImageWeeds\n(5 species)\n306 GT",
        "Weed/Crop*\n(tray crop)\n781 GT",
    ]
    ap50 = [0.9049, 0.6730, 0.4570, 0.6893]
    ap50_95 = [0.4664, 0.3750, 0.2590, 0.3924]

    alts = np.linspace(2.0, 50.0, 97)
    cam = CAMERAS["imx708"]
    downscale = cam["width_px"] / 640.0
    gsd_native = np.array([native_gsd_cm(cam, float(h)) for h in alts])
    px_30cm_tiled = 30.0 / gsd_native
    px_30cm_whole = 30.0 / (gsd_native * downscale)
    px_120cm_whole = 120.0 / (gsd_native * downscale)

    speeds = np.linspace(1.0, 15.0, 40)
    exp_1px_30m_ms = [(1.0 * (native_gsd_cm(cam, 30.0) / 100.0) / float(v)) * 1000.0 for v in speeds]
    skew_imx708 = [(float(v) * READOUT_S["imx708"]) / (native_gsd_cm(cam, 30.0) / 100.0) for v in speeds]

    fig, axes = plt.subplots(1, 3, figsize=(15.2, 5.1), dpi=180)
    fig.suptitle(
        "Observed YOLOX-s Model Card APs & IMX708 Optical/Motion-Budget Envelopes",
        fontsize=12.8,
        fontweight="bold",
        color=NAVY,
        y=0.98,
    )

    # Panel A: Real Model Card COCO APs
    ax = axes[0]
    x = np.arange(len(model_labels))
    w = 0.36
    b1 = ax.bar(x - w / 2, ap50, width=w, color=NAVY, label="Test AP@0.50")
    b2 = ax.bar(x + w / 2, ap50_95, width=w, color=TEAL, label="Test AP@0.50:0.95")
    for bar in list(b1) + list(b2):
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.015, f"{h:.3f}", ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(x)
    ax.set_xticklabels(model_labels, fontsize=8.0)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("COCO Average Precision (ONNX test eval)")
    ax.set_title("A. Real Model Card Evaluation Metrics", fontweight="bold", color=NAVY, fontsize=10.3)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="upper right", fontsize=8)

    # Panel B: Pixels on Target vs AGL Altitude (Whole-Frame 7.2x downscale vs Tiled Native)
    ax = axes[1]
    ax.plot(alts, px_30cm_tiled, color=TEAL, lw=2.3, label="30 cm weed (tiled native 4608 px)")
    ax.plot(alts, px_120cm_whole, color=NAVY, lw=2.1, ls="--", label="120 cm sheep (whole-frame 640 px)")
    ax.plot(alts, px_30cm_whole, color=RED, lw=2.0, ls=":", label="30 cm weed (whole-frame 7.2x loss)")
    ax.axhline(20.0, color=AMBER, ls="--", lw=1.3, label="Detection floor (20 px across target)")
    ax.set_ylim(0, 110)
    ax.set_title("B. Pinhole Detectability: Whole-Frame vs Tiled", fontweight="bold", color=NAVY, fontsize=10.3)
    ax.set_xlabel("Altitude AGL (m)")
    ax.set_ylabel("Pixels Across Target (IMX708)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", fontsize=7.6)

    # Panel C: Motion Blur Exposure Budget & Rolling-Shutter Skew at 30 m AGL
    ax = axes[2]
    ax3 = ax.twinx()
    l1 = ax.plot(speeds, exp_1px_30m_ms, color=NAVY, lw=2.2, label="Max exposure <= 1 px smear (ms)")
    l2 = ax3.plot(speeds, skew_imx708, color=RED, lw=2.0, ls="--", label="Full-frame skew @ 33 ms (px)")
    l3 = ax3.axhline(5.0, color=AMBER, ls=":", lw=1.3, label="Skew threshold (5 px)")
    ax.set_title("C. Speed vs Shutter & Rolling Skew (30 m)", fontweight="bold", color=NAVY, fontsize=10.3)
    ax.set_xlabel("Ground Speed (m/s)")
    ax.set_ylabel("Max Shutter Time (ms)", color=NAVY)
    ax3.set_ylabel("Top-to-Bottom Skew (px)", color=RED)
    ax.grid(True, alpha=0.25)
    ax.legend(l1 + l2 + [l3], [ln.get_label() for ln in (l1 + l2 + [l3])], loc="upper center", fontsize=7.4)

    fig.tight_layout(rect=[0, 0.02, 1, 0.93], w_pad=2.8)
    _save_fig(fig, "ml_models_optics_envelope.png", proof_dir, mirror_web)

    return {
        "model_cards": {
            "aerial_sheep_yolox_s": {"ap50": 0.9049, "ap50_95": 0.4664, "test_gt_boxes": 5603},
            "imageweeds_yolox_s_species": {"ap50": 0.4570, "ap50_95": 0.2590, "test_gt_boxes": 306},
            "imageweeds_yolox_s_binary": {"ap50": 0.6730, "ap50_95": 0.3750, "test_gt_boxes": 306},
            "weed_crop_yolox_s": {"ap50": 0.6893, "ap50_95": 0.3924, "test_gt_boxes": 781, "caveat": "98.3% crop in indoor trays"},
        },
        "imx708_downscale_factor": round(downscale, 2),
        "imx708_native_gsd_30m_cm": round(float(native_gsd_cm(cam, 30.0)), 3),
        "max_exposure_5ms_30m_ms": round(float(max_exposure_s(30.0, 5.0) * 1000.0), 3),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=PROOF_DIR)
    ap.add_argument("--no-web-copy", action="store_true")
    args = ap.parse_args(argv)
    proof_dir: Path = args.out
    mirror_web = not args.no_web_copy

    af = Airframe()
    airframe_res = simulate_airframe_and_vibration(af, proof_dir, mirror_web)
    georef_res = simulate_georeference_and_3d_flight(af, proof_dir, mirror_web)
    spray_res = simulate_spray_drift_and_flow(proof_dir, mirror_web)
    ml_optics_res = simulate_ml_and_optics_envelope(proof_dir, mirror_web)

    summary_out = {
        "mode": "SIMULATED",
        "validated_locally": False,
        "airframe": airframe_res,
        "georeference_3d": georef_res,
        "spray_and_drift": spray_res,
        "ml_and_optics": ml_optics_res,
        "generated_plots": [
            "airframe_endurance_physics.png",
            "georef_3d_trajectory.png",
            "spray_drift_envelope.png",
            "ml_models_optics_envelope.png",
        ],
    }
    proof_dir.mkdir(parents=True, exist_ok=True)
    (proof_dir / "physics_sim_summary.json").write_text(
        json.dumps(summary_out, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary_out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
