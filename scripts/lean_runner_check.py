"""Reproduce CI's lean runner: a venv with the runtime core and nothing else.

    make test-lean


An earlier version of this check faked absence with a meta_path hook that
raised from find_spec. That breaks find_spec's contract -- a genuinely missing
module makes it return None, not raise -- so a test guarded with
`importlib.util.find_spec("PIL") is not None` blew up under the fake and would
have passed on a real runner.

And the version before that only ran --collect-only, which misses an import
inside a fixture. That is precisely what slipped through and left CI red.

So: a real venv, `pip install -e .` and pytest, nothing else. Exactly what the
workflow's lean job does.
"""
import shutil
import subprocess
import sys
from pathlib import Path

VENV = Path(".lean-venv")

if VENV.exists():
    shutil.rmtree(VENV, ignore_errors=True)

print("creating venv ...")
subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)

py = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

print("installing the runtime core only ...")
subprocess.run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
subprocess.run([str(py), "-m", "pip", "install", "-q", "-e", "."], check=True)
subprocess.run([str(py), "-m", "pip", "install", "-q", "pytest"], check=True)

installed = subprocess.run(
    [str(py), "-m", "pip", "list", "--format=freeze"],
    capture_output=True, text=True, check=True,
).stdout
heavy = [ln for ln in installed.splitlines()
         if ln.split("==")[0].lower() in
         {"torch", "pillow", "opencv-python", "opencv-python-headless",
          "onnxruntime", "pymavlink"}]
print("heavy packages present:", heavy or "none (good)")

print("\nrunning the suite ...")
r = subprocess.run([str(py), "-m", "pytest", "-q"], capture_output=True, text=True)
print("\n".join((r.stdout + r.stderr).strip().splitlines()[-15:]))
print("exit:", r.returncode)

shutil.rmtree(VENV, ignore_errors=True)
sys.exit(r.returncode)
