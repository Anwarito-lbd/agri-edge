"""Label Studio round trip: tasks out (with the model's boxes as pre-annotations),
labels back in as COCO for YOLOX training.

Label Studio (Apache-2.0) runs unmodified beside this, e.g.
`docker run -p 8080:8080 -v $PWD/labeling:/label-studio/data heartexlabs/label-studio`
with local file serving enabled (LOCAL_FILES_SERVING_ENABLED=true,
LOCAL_FILES_DOCUMENT_ROOT=/label-studio/data). Pre-annotations only save
clicks: the labeller must see and correct every box, and the imported set
records who labelled what.

Each COCO image keeps where and when it was taken, so the training split can
be done by capture DAY -- frames seconds apart are near-duplicates, and a
random frame split leaks them across train and validation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import png


def label_config(classes: list[str]) -> str:
    labels = "\n".join(f'    <Label value="{c}"/>' for c in classes)
    return ('<View>\n  <Image name="image" value="$image" zoom="true"/>\n'
            f'  <RectangleLabels name="label" toName="image">\n{labels}\n  </RectangleLabels>\n</View>\n')


def export_tasks(spool_dir: Path, entries: list[dict], out_dir: Path, *,
                 url_prefix: str = "/data/local-files/?d=images/") -> Path:
    """entries: spool index rows (dicts) for the selected frames. Writes
    out_dir/images/*.png and out_dir/tasks.json; returns the tasks path."""
    img_dir = out_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    tasks = []
    for e in entries:
        meta = json.loads((spool_dir / e["meta_path"]).read_text(encoding="utf-8"))
        img_path = spool_dir / e["image_path"]
        if not img_path.exists():
            continue                     # image evicted by the spool quota
        arr = np.load(img_path)
        name = f"{e['entry_id']}.png"
        (img_dir / name).write_bytes(png.encode(arr[..., :3] if arr.ndim == 3 else arr))
        t = meta.get("telemetry") or {}
        model = meta.get("model") or {}
        result = []
        for i, d in enumerate(meta.get("detections") or []):
            x0, y0, x1, y1 = d["bbox"]
            result.append({"id": f"p{i}", "from_name": "label", "to_name": "image",
                           "type": "rectanglelabels", "score": d.get("confidence"),
                           "value": {"x": x0 * 100, "y": y0 * 100, "width": (x1 - x0) * 100,
                                     "height": (y1 - y0) * 100,
                                     "rectanglelabels": [d.get("source_label") or d["label"]]}})
        tasks.append({
            "data": {"image": url_prefix + name, "entry_id": e["entry_id"],
                     "site": meta.get("site"), "field_id": meta.get("field_id"),
                     "captured_at": meta.get("captured_at"), "lat": t.get("lat"), "lon": t.get("lon"),
                     "width": int(arr.shape[1]), "height": int(arr.shape[0])},
            "predictions": [{"model_version": f"{model.get('name')} v{model.get('version')}",
                             "result": result}] if result else [],
        })
    path = out_dir / "tasks.json"
    path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    return path


def import_coco(ls_export: list[dict], classes: list[str]) -> dict:
    """Label Studio JSON export -> COCO. Only tasks with a completed, non-cancelled
    human annotation are included; predictions are never taken as labels."""
    cat_id = {c: i + 1 for i, c in enumerate(classes)}
    images: list[dict] = []
    anns: list[dict] = []
    skipped: list = []
    for task in ls_export:
        data = task.get("data") or {}
        done = [a for a in task.get("annotations") or [] if not a.get("was_cancelled")]
        if not done:
            skipped.append(data.get("entry_id"))
            continue
        ann = done[-1]
        w, h = int(data.get("width") or 0), int(data.get("height") or 0)
        if not (w and h):
            raise ValueError(f"task {data.get('entry_id')} has no image size")
        img_id = len(images) + 1
        captured = data.get("captured_at")
        day = (datetime.fromtimestamp(captured, tz=timezone.utc).date().isoformat()
               if isinstance(captured, (int, float)) else None)
        images.append({"id": img_id, "file_name": Path(str(data["image"]).split("=")[-1]).name,
                       "width": w, "height": h, "entry_id": data.get("entry_id"),
                       "site": data.get("site"), "field_id": data.get("field_id"),
                       "capture_day": day, "lat": data.get("lat"), "lon": data.get("lon"),
                       "labelled_by": (ann.get("completed_by") or {}).get("email")
                       if isinstance(ann.get("completed_by"), dict) else ann.get("completed_by")})
        for r in ann.get("result") or []:
            if r.get("type") != "rectanglelabels":
                continue
            v = r["value"]
            label = v["rectanglelabels"][0]
            if label not in cat_id:
                raise ValueError(f"label {label!r} is not in the class list {classes}")
            bw, bh = v["width"] / 100 * w, v["height"] / 100 * h
            anns.append({"id": len(anns) + 1, "image_id": img_id, "category_id": cat_id[label],
                         "bbox": [v["x"] / 100 * w, v["y"] / 100 * h, bw, bh],
                         "area": bw * bh, "iscrowd": 0})
    return {"images": images, "annotations": anns,
            "categories": [{"id": i, "name": c} for c, i in cat_id.items()],
            "info": {"source": "label-studio", "skipped_unlabelled": skipped}}


def split_by_day(coco: dict, val_days: int = 1) -> tuple[dict, dict]:
    """Hold out the LAST `val_days` capture days as validation: frames from one
    day never appear on both sides."""
    days = sorted({i["capture_day"] for i in coco["images"] if i.get("capture_day")})
    if len(days) <= val_days:
        raise ValueError(f"need more than {val_days} capture day(s) to split by day; have {days}")
    val = set(days[-val_days:])

    def part(keep) -> dict:
        imgs = [i for i in coco["images"] if keep(i.get("capture_day"))]
        ids = {i["id"] for i in imgs}
        return {**coco, "images": imgs, "annotations": [a for a in coco["annotations"] if a["image_id"] in ids]}

    return part(lambda d: d not in val), part(lambda d: d in val)
