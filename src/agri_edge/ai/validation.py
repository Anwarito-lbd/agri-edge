"""Which models have been validated on this farm's own imagery.

A model counts as locally validated only through a passing validation report
in the reports directory (default `ai/model_registry/validations/`, override
with AGRIEDGE_VALIDATIONS_DIR). Reports are written by
`training/validate_local.py`, which ties each one to the model file's sha256.
There is no flag to set by hand: `validated_locally: true` in a meta file is
not enough on its own anywhere this module is consulted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "ai" / "model_registry" / "validations"


def reports_dir() -> Path:
    return Path(os.environ.get("AGRIEDGE_VALIDATIONS_DIR") or DEFAULT_DIR)


def load_reports(directory: Path | None = None) -> list[dict]:
    d = directory or reports_dir()
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def validated_models(directory: Path | None = None) -> set[tuple[str, str]]:
    """(name, version) of every model with a passing report."""
    return {(str(r.get("model_name")), str(r.get("model_version")))
            for r in load_reports(directory) if r.get("passed") is True}
