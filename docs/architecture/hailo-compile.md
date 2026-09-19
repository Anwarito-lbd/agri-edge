# Hailo compile path (ONNX → HEF)

**Status:** SIMULATED / docs — **not** HARDWARE-validated on a Pi AI HAT.

## Preconditions
- x86_64 Linux or **WSL2 Ubuntu 22.04** (not Windows-native, not Pi ARM)
- Hailo Dataflow Compiler wheel from [Hailo Developer Zone](https://hailo.ai/developer-zone/) (not on PyPI)
- `hailo_model_zoo` / `hailomz` installed into a Python 3.10 venv
- Exported ONNX from `training/export_onnx.py` / `scripts/export_yolox_onnx.py`
- ≥64 calibration images from the **same** training distribution

## Commands
```bash
# Linux / WSL2
bash scripts/hailo_compile.sh --arch hailo8l \
  --model models/weed_crop_yolox_s.onnx \
  --calib data/weed-crop-aerial/train/images

# Windows → WSL2 helper
pwsh scripts/hailo_compile.ps1 -Arch hailo8l -DryRun
```

## Safety / honesty
- Real HEF inference on AI HAT = **BLOCKED-HARDWARE** until device present
- Live camera on Pi = **BLOCKED-HARDWARE**
- Do not mark Hardware/Field green without evidence
