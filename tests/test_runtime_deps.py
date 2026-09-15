"""Guard the Pi runtime's dependency boundary.

`src/agri_edge/` must import with **numpy and PyYAML only**. Everything heavy --
torch, onnxruntime, OpenCV, picamera2, rasterio, HailoRT, pymavlink -- has to be
imported lazily, inside the function that needs it.

This is an architectural guarantee, and it is exactly the kind that regresses
silently: someone adds `import cv2` at the top of a module for one convenience
function, everything still passes on the laptop, and the next `pip install` on
the Pi drags in a 200 MB dependency tree, or fails outright on an aircraft.

Torch alone is ~3 GB. It has no business on a drone.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "agri_edge"

# Allowed as hard, module-level imports: the declared core dependencies.
ALLOWED_THIRD_PARTY = {"numpy", "yaml"}

# Must never appear at module level anywhere in the runtime package.
FORBIDDEN_AT_MODULE_LEVEL = {
    "torch", "torchvision", "onnx", "onnxruntime", "cv2", "picamera2",
    "rasterio", "hailo_platform", "pymavlink", "PIL", "pycocotools",
    "yolox", "matplotlib", "scipy", "pandas",
}


def module_level_imports(path: Path) -> set[str]:
    """Top-level import names only -- imports nested in functions are fine."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:                       # top level only, not ast.walk
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # absolute import
                names.add(node.module.split(".")[0])
    return names


ALL_MODULES = sorted(SRC.rglob("*.py"))


@pytest.mark.parametrize("path", ALL_MODULES, ids=lambda p: p.name)
def test_no_heavy_imports_at_module_level(path):
    offenders = module_level_imports(path) & FORBIDDEN_AT_MODULE_LEVEL
    assert not offenders, (
        f"{path.relative_to(SRC)} imports {sorted(offenders)} at module level. "
        "Move it inside the function that needs it -- the Pi runtime must install "
        "with numpy and PyYAML alone."
    )


@pytest.mark.parametrize("path", ALL_MODULES, ids=lambda p: p.name)
def test_only_declared_core_dependencies(path):
    """Catch any new third-party dependency, not just the known-heavy list."""
    stdlib = set(sys.stdlib_module_names)
    third_party = {
        n for n in module_level_imports(path)
        if n not in stdlib and n != "agri_edge"
    }
    unexpected = third_party - ALLOWED_THIRD_PARTY
    assert not unexpected, (
        f"{path.relative_to(SRC)} adds module-level dependency {sorted(unexpected)}. "
        f"The runtime core is {sorted(ALLOWED_THIRD_PARTY)}; anything else must be "
        "an optional extra imported lazily."
    )


def test_package_imports_with_optional_extras_absent():
    """Import the whole package in a subprocess with the extras blocked.

    The static checks above catch declarations; this catches an import that
    happens as a side effect of something else.
    """
    code = """
import sys
for mod in ['torch','torchvision','onnxruntime','cv2','picamera2',
            'rasterio','hailo_platform','pymavlink','PIL','pycocotools','yolox']:
    sys.modules[mod] = None

import agri_edge
from agri_edge.config import Config
from agri_edge.pipeline.runner import Pipeline
from agri_edge.inference.engine import build_engine, SimulatedEngine
from agri_edge.inference.tiling import TiledEngine
from agri_edge.inference import yolox
from agri_edge.qa.checks import run_qa
from agri_edge.geo.indices import BandStack
from agri_edge.store.spool import Spool
from agri_edge.capture.camera import build_camera
from agri_edge.telemetry.mavlink_link import build_telemetry_source
from agri_edge.cli import main
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, (
        "The runtime failed to import with optional extras absent:\n"
        f"{result.stderr}"
    )
    assert "OK" in result.stdout


def test_pipeline_runs_without_optional_extras():
    """Not just importable -- actually usable end to end on a bare install."""
    code = """
import sys, tempfile, pathlib
for mod in ['torch','onnxruntime','cv2','picamera2','rasterio','hailo_platform','pymavlink','PIL']:
    sys.modules[mod] = None

from agri_edge.config import Config, QAConfig
from agri_edge.capture.camera import SimulatedCamera
from agri_edge.telemetry.mavlink_link import SimulatedTelemetry
from agri_edge.store.spool import Spool
from agri_edge.pipeline.runner import Pipeline
from agri_edge.inference.engine import SimulatedEngine

tmp = pathlib.Path(tempfile.mkdtemp())
cfg = Config()
cfg.spool.spool_dir = tmp / "spool"
cfg.capture.interval_s = 0.0
cfg.qa = QAConfig(blur_threshold=1.0)

p = Pipeline(cfg, SimulatedCamera(resolution=(64, 48)), SimulatedTelemetry(),
             Spool(cfg.spool.spool_dir), SimulatedEngine())
stats = p.run(max_frames=3)
assert stats.spooled == 3, stats
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, f"Bare-install pipeline run failed:\n{result.stderr}"
    assert "OK" in result.stdout


def test_pyproject_core_dependencies_match():
    """The declared core deps must match what the code actually requires."""
    pyproject = (SRC.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    core = pyproject.split("dependencies = [", 1)[1].split("]", 1)[0]
    assert "numpy" in core
    assert "pyyaml" in core.lower()
    for heavy in ("torch", "onnxruntime", "opencv", "picamera2", "rasterio"):
        assert heavy not in core, (
            f"'{heavy}' appears in the core dependencies. It belongs in "
            "[project.optional-dependencies]."
        )
