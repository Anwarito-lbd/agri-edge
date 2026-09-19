"""YOLOX export stub documents the real command path."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_export_stub_dry_run():
    script = Path("scripts/export_yolox_onnx.py")
    assert script.exists()
    proc = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "YOLOX" in proc.stdout or "export" in proc.stdout.lower()
    assert "training/export_onnx.py" in proc.stdout


def test_hailo_compile_scripts_exist():
    assert Path("scripts/hailo_compile.sh").exists()
    assert Path("scripts/hailo_compile.ps1").exists()
    assert Path("docs/architecture/hailo-compile.md").exists()
    text = Path("scripts/hailo_compile.sh").read_text(encoding="utf-8")
    assert "hailomz" in text or "hailo" in text.lower()
    # Must not claim hardware validation in the script header
    ps1 = Path("scripts/hailo_compile.ps1").read_text(encoding="utf-8")
    assert "HARDWARE" in ps1.upper() or "SIMULATED" in ps1.upper()
