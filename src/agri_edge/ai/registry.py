"""Model registry — metadata schema with name, version, sha256, classes.

Status: IMPLEMENTED (software). Hardware HEF entries may exist as records but
validated_locally stays False until field evidence is recorded.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass
class ModelRecord:
    """Registry entry for a deployable model artifact."""

    name: str
    version: str
    classes: list[str] = field(default_factory=list)
    sha256_onnx: str | None = None
    sha256_hef: str | None = None
    sha256_weights: str | None = None
    architecture: str = "YOLOX-s"
    input_size: list[int] = field(default_factory=lambda: [640, 640])
    validated_locally: bool = False
    validation_notes: str = ""
    trained_on: list[str] = field(default_factory=list)
    paths: dict[str, str] = field(default_factory=dict)
    status: str = "SIMULATED"  # IMPLEMENTED | SIMULATED | BLOCKED-HARDWARE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def from_meta_json(cls, path: Path, *, compute_sha256: bool = False) -> "ModelRecord":
        raw = json.loads(path.read_text(encoding="utf-8"))
        # e.g. weed_crop_yolox_s.onnx.meta.json
        artifact = path.parent / path.name.replace(".meta.json", "").replace(".onnx.meta.json", ".onnx")
        if not artifact.exists():
            # try sibling without double suffix confusion
            candidate = Path(str(path).replace(".meta.json", ""))
            if candidate.exists():
                artifact = candidate
        sha_onnx = raw.get("sha256_onnx")
        if compute_sha256 and artifact.exists() and artifact.suffix == ".onnx":
            sha_onnx = sha256_file(artifact)
        return cls(
            name=str(raw.get("name") or path.stem.split(".")[0]),
            version=str(raw.get("version") or "0.0.0"),
            classes=list(raw.get("class_names") or raw.get("classes") or []),
            sha256_onnx=sha_onnx,
            sha256_hef=raw.get("sha256_hef"),
            sha256_weights=raw.get("sha256_weights"),
            architecture=str(raw.get("architecture") or "YOLOX-s"),
            input_size=list(raw.get("input_size") or [640, 640]),
            validated_locally=bool(raw.get("validated_locally", False)),
            validation_notes=str(raw.get("validation_notes") or ""),
            trained_on=list(raw.get("trained_on") or []),
            paths={"meta": str(path), "artifact": str(artifact) if artifact.exists() else ""},
            status="SIMULATED" if not raw.get("validated_locally") else "IMPLEMENTED",
        )


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


class ModelRegistry:
    """In-memory / JSON-backed model registry."""

    def __init__(self, records: Iterable[ModelRecord] | None = None) -> None:
        self._by_key: dict[str, ModelRecord] = {}
        for r in records or []:
            self.add(r)

    @staticmethod
    def key(name: str, version: str) -> str:
        return f"{name}@{version}"

    def add(self, record: ModelRecord) -> None:
        self._by_key[self.key(record.name, record.version)] = record

    def get(self, name: str, version: str | None = None) -> ModelRecord | None:
        if version is not None:
            return self._by_key.get(self.key(name, version))
        matches = [r for r in self._by_key.values() if r.name == name]
        if not matches:
            return None
        return sorted(matches, key=lambda r: r.version, reverse=True)[0]

    def list(self) -> list[ModelRecord]:
        return sorted(self._by_key.values(), key=lambda r: (r.name, r.version))

    def to_list(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.list()]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_list(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ModelRegistry":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(ModelRecord.from_dict(item) for item in data)


def load_registry(
    models_dir: Path | str | None = None,
    registry_json: Path | str | None = None,
) -> ModelRegistry:
    """Load from ai/model_registry/registry.json and/or scan models/*.meta.json."""
    root = Path(__file__).resolve().parents[3]
    reg_path = Path(registry_json) if registry_json else root / "ai" / "model_registry" / "registry.json"
    registry = ModelRegistry.load(reg_path) if reg_path.exists() else ModelRegistry()
    mdir = Path(models_dir) if models_dir else root / "models"
    if mdir.is_dir():
        for meta in sorted(mdir.glob("*.meta.json")):
            rec = ModelRecord.from_meta_json(meta)
            # do not overwrite explicit registry entries
            if registry.get(rec.name, rec.version) is None:
                registry.add(rec)
    return registry
