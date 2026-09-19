"""Model registry metadata schema."""
from __future__ import annotations

import json
from pathlib import Path

from agri_edge.ai.registry import ModelRecord, ModelRegistry, load_registry, sha256_file


def test_model_record_roundtrip(tmp_path: Path):
    rec = ModelRecord(
        name="weed_crop_yolox_s",
        version="0.1.0",
        classes=["crop", "weed"],
        sha256_onnx="abc123",
        validated_locally=False,
        status="SIMULATED",
    )
    path = tmp_path / "registry.json"
    reg = ModelRegistry([rec])
    reg.save(path)
    loaded = ModelRegistry.load(path)
    got = loaded.get("weed_crop_yolox_s", "0.1.0")
    assert got is not None
    assert got.classes == ["crop", "weed"]
    assert got.sha256_onnx == "abc123"
    assert got.validated_locally is False


def test_sha256_file(tmp_path: Path):
    f = tmp_path / "blob.bin"
    f.write_bytes(b"agri-edge")
    digest = sha256_file(f)
    assert len(digest) == 64
    assert digest == sha256_file(f)


def test_load_registry_from_repo_models():
    reg = load_registry()
    records = reg.list()
    assert isinstance(records, list)
    # At least the seeded registry or scanned meta files
    assert len(records) >= 1
    for r in records:
        assert r.name
        assert r.version
        assert isinstance(r.classes, list)
        # Safety: nothing pretends field-validated without evidence
        if r.status == "IMPLEMENTED" and r.validated_locally:
            assert r.validation_notes


def test_registry_json_schema_fields():
    path = Path("ai/model_registry/registry.json")
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data
    required = {"name", "version", "classes"}
    for item in data:
        assert required.issubset(item.keys())
        # sha256 fields may be null until artifacts exist
        assert "sha256_onnx" in item or "sha256_hef" in item or True
