"""The portfolio demo must actually run and write the files the README cites."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_portfolio_demo_writes_observed_artifacts(tmp_path):
    out = tmp_path / "proof"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "portfolio_demo.py"),
            "--out",
            str(out),
            "--frames",
            "3",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["simulated"] is True
    assert summary["hardware"] is False
    assert summary["sitl_ran"] is False
    assert summary["pipeline"]["captured"] == 3
    assert summary["pipeline"]["qa_ok"] == 3
    assert summary["pipeline"]["decision_support_only"] is True
    assert summary["pipeline"]["may_drive_treatment"] is False
    assert summary["pipeline"]["validated_locally"] is False
    assert summary["et0_brussels_mm_day"] == pytest.approx(3.9, abs=0.05)
    assert summary["decisions_allowed"] == 1
    assert summary["decisions_refused"] == 7
    assert summary["coverage"]["lines"] >= 1
    assert 0.0 <= summary["coverage"]["gap_fraction"] < 0.05

    allowed = [row for row in summary["decisions"] if row["allowed"]]
    assert len(allowed) == 1
    assert allowed[0]["simulated_actuator_commands"] == 1
    assert all(row["simulated_actuator_commands"] == 0 for row in summary["decisions"] if not row["allowed"])

    assert (out / "flight_track.svg").stat().st_size > 1000
    assert (out / "ndvi.png").stat().st_size > 1000
    assert (out / "scene_rgb.png").stat().st_size > 1000
    assert (out / "gsd.svg").stat().st_size > 500
    telemetry = (out / "telemetry.csv").read_text(encoding="utf-8").splitlines()
    assert telemetry[0].startswith("t_s,east_m,north_m")
    assert len(telemetry) > 20
