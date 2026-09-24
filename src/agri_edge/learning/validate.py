"""Local validation: the only way a model becomes `validated_locally`.

A report is written only by `run_validation`, only after the model has been
scored on this farm's own labelled imagery against criteria stated in the
report itself, and it is tied to the model FILE by sha256. The inference
engine trusts a model as locally validated only when a passing report
matches the exact file it loaded (`ModelMetadata.load_beside`), and the
prescription gate only when a passing report names the model.

Default criteria are deliberately demanding and printed in every report so a
reader can disagree with them explicitly:

* at least 200 labelled images, from at least 2 capture days and all from
  this farm's fields (sidecar site/field present);
* per required class: AP50 >= 0.5 and recall >= 0.7 at the operating
  threshold the aircraft uses;
* a named reviewer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .metrics import evaluate


@dataclass
class Criteria:
    required_classes: list[str]
    min_images: int = 200
    min_days: int = 2
    min_ap50: float = 0.5
    min_recall: float = 0.7
    op_threshold: float = 0.3


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dataset_hash(coco: dict) -> str:
    return hashlib.sha256(json.dumps({"images": coco["images"], "annotations": coco["annotations"]},
                                     sort_keys=True).encode()).hexdigest()


def predict_from_spool(engine, spool_dir: Path, coco: dict) -> dict[int, list]:  # pragma: no cover - needs a model
    preds: dict[int, list] = {}
    for img in coco["images"]:
        arr = np.load(Path(spool_dir) / f"{img['entry_id']}.npy")
        h, w = arr.shape[:2]
        preds[img["id"]] = [((d.source_label or d.label), d.confidence,
                             (d.bbox[0] * w, d.bbox[1] * h, d.bbox[2] * w, d.bbox[3] * h))
                            for d in engine.infer(arr)]
    return preds


def run_validation(model_path: Path, model_name: str, model_version: str, coco: dict,
                   preds: dict[int, list], criteria: Criteria, reviewer: str, notes: str = "") -> dict:
    names = {c["id"]: c["name"] for c in coco["categories"]}
    gt: dict[int, list] = {i["id"]: [] for i in coco["images"]}
    for a in coco["annotations"]:
        x, y, w, h = a["bbox"]
        gt[a["image_id"]].append((names[a["category_id"]], (x, y, x + w, y + h)))
    metrics = evaluate(gt, {i: preds.get(i, []) for i in gt}, criteria.required_classes,
                       criteria.op_threshold)
    days = sorted({i.get("capture_day") for i in coco["images"] if i.get("capture_day")})
    local = all(i.get("site") and i.get("field_id") for i in coco["images"])
    checks = [
        {"check": "images", "passed": len(gt) >= criteria.min_images,
         "detail": f"{len(gt)} labelled images (need {criteria.min_images})"},
        {"check": "capture days", "passed": len(days) >= criteria.min_days,
         "detail": f"{len(days)} day(s): {', '.join(days) or 'none'} (need {criteria.min_days})"},
        {"check": "local imagery", "passed": local,
         "detail": "every image carries this farm's site and field" if local
         else "some images have no site/field: not provably from this farm"},
        {"check": "reviewer", "passed": bool(reviewer and reviewer.strip()),
         "detail": reviewer or "no reviewer named"},
    ]
    for m in metrics:
        checks.append({"check": f"{m.label} AP50", "passed": m.ap50 >= criteria.min_ap50,
                       "detail": f"{m.ap50:.3f} on {m.n_gt} boxes (need {criteria.min_ap50})"})
        checks.append({"check": f"{m.label} recall@{criteria.op_threshold}",
                       "passed": m.recall_at_op >= criteria.min_recall,
                       "detail": f"{m.recall_at_op:.3f} (need {criteria.min_recall})"})
    return {
        "schema": "agri-edge/validation/1",
        "model_name": model_name, "model_version": model_version,
        "model_file": Path(model_path).name, "model_sha256": sha256_file(Path(model_path)),
        "dataset_sha256": _dataset_hash(coco), "n_images": len(gt), "capture_days": days,
        "fields": sorted({str(i.get("field_id")) for i in coco["images"]}),
        "metrics": [m.to_dict() for m in metrics], "criteria": asdict(criteria),
        "checks": checks, "passed": all(c["passed"] for c in checks),
        "reviewer": reviewer, "notes": notes,
        "created": datetime.now(timezone.utc).isoformat(),
    }


def write_report(report: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report["created"][:19].replace(":", "").replace("-", "")
    path = directory / f"{report['model_name']}-{report['model_version']}-{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


@dataclass
class Trust:
    validated_locally: bool
    reason: str
    report: str | None = None
    notes: list[str] = field(default_factory=list)


def trust_for(model_path: Path, claimed: bool, reports: list[dict]) -> Trust:
    """What the engine may believe about a model file."""
    sha = sha256_file(model_path)
    match = [r for r in reports if r.get("passed") is True and r.get("model_sha256") == sha]
    if match:
        return Trust(True, "passing local validation report for this exact file",
                     report=str(match[-1].get("created")))
    if claimed:
        return Trust(False, "meta claims validated_locally but no passing report matches "
                            "this file's sha256; treated as NOT validated")
    return Trust(False, "no passing local validation report for this file")
