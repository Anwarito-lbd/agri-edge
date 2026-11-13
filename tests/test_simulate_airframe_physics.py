"""Verify that the airframe, spray-flow, optics & 3D trajectory physics suite runs cleanly."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

ROOT = Path(__file__).resolve().parents[1]


def test_simulate_airframe_physics_writes_plots_and_summary(tmp_path):
    out = tmp_path / "physics_proof"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "simulate_airframe_physics.py"),
            "--out",
            str(out),
            "--no-web-copy",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    summary = json.loads((out / "physics_sim_summary.json").read_text(encoding="utf-8"))
    assert summary["mode"] == "SIMULATED"
    assert summary["validated_locally"] is False
    assert summary["airframe"]["airframe_baseline"]["mass_g"] == 3432
    assert summary["spray_and_drift"]["bench_point_20lha_8ms_8m_l_min"] == pytest.approx(7.68, abs=0.01)
    assert summary["spray_and_drift"]["airframe_wind_rejection"]["status"] == "unknown"
    assert summary["georeference_3d"]["shift_at_10deg_roll_30m_agl_m"] == pytest.approx(5.29, abs=0.05)

    for fname in summary["generated_plots"]:
        p = out / fname
        assert p.exists() and p.stat().st_size > 10_000, f"missing or empty plot: {p}"
