"""The field training loop: pole GNSS, frame selection, Label Studio round trip,
metrics, local validation, and the engine trusting a model only through a
report that matches its file."""

from __future__ import annotations

import json
import struct
import zlib
from datetime import datetime, timezone

import numpy as np
import pytest

from agri_edge.capture.camera import SimulatedCamera
from agri_edge.config import Config
from agri_edge.inference.engine import Detection, InferenceEngine, ModelMetadata
from agri_edge.learning import png
from agri_edge.learning.labelstudio import export_tasks, import_coco, label_config, split_by_day
from agri_edge.learning.metrics import evaluate
from agri_edge.learning.selection import score, select
from agri_edge.learning.validate import Criteria, run_validation, sha256_file, trust_for, write_report
from agri_edge.pipeline.runner import Pipeline
from agri_edge.store.spool import Spool
from agri_edge.telemetry.nmea import NmeaTelemetry, checksum_ok, parse

GGA = "$GPGGA,172814.0,5026.712,N,10436.134,W,4,12,0.6,577.3,M,-16.0,M,1.0,0000*"
RMC = "$GPRMC,172814.0,A,5026.712,N,10436.134,W,1.2,87.5,240926,,,A*"


def _nmea(body: str) -> str:
    cs = 0
    for ch in body[1:-1]:
        cs ^= ord(ch)
    return f"{body}{cs:02X}"


# -- pole capture ----------------------------------------------------------------


def test_nmea_checksums_and_parsing():
    gga = _nmea(GGA)
    assert checksum_ok(gga) and not checksum_ok(gga[:-2] + "00")
    d = parse(gga)
    assert d["lat"] == pytest.approx(50 + 26.712 / 60) and d["lon"] == pytest.approx(-(104 + 36.134 / 60))
    assert d["fix_type"] == 6 and d["satellites"] == 12 and d["hdop"] == 0.6
    r = parse(_nmea(RMC))
    assert r["valid"] and r["speed_ms"] == pytest.approx(1.2 * 0.514444) and r["course_deg"] == 87.5
    assert parse("$GPGSV,garbage*00") is None


def test_pole_telemetry_is_nadir_at_pole_height_and_honest_about_heading():
    t = NmeaTelemetry("/dev/null", pole_height_m=2.5)
    t.feed(_nmea(GGA), now=1000.0)
    s = t.snapshot()
    assert s.alt_rel_m == 2.5 and s.roll_deg == 0.0 and s.pitch_deg == 0.0
    assert s.yaw_deg is None, "standing still: no heading, so no georeference"
    assert s.age_s(now=1000.0) == 0.0
    t.feed(_nmea(RMC), now=1000.5)
    assert t.snapshot().yaw_deg == 87.5
    slow = RMC.replace(",1.2,", ",0.3,")
    t.feed(_nmea(slow), now=1001.0)
    assert t.snapshot().yaw_deg is None


# -- selection -----------------------------------------------------------------


def _meta(dets, lat=50.0, lon=-104.0, green=None, qa=True):
    m = {"qa": {"passed": qa}, "telemetry": {"lat": lat, "lon": lon},
         "detections": [{"label": "kochia", "confidence": c, "bbox": [0.1, 0.1, 0.2, 0.2]} for c in dets]}
    if green is not None:
        m["indices"] = {"excess_green": {"p95": green}}
    return m


def test_uncertain_and_possibly_missed_frames_score_first():
    assert score("a", _meta([0.95, 0.9])).score == 0           # confident: little to learn
    assert score("b", _meta([0.45])).score > 1                  # the model is guessing
    miss = score("c", _meta([], green=0.3))
    assert miss.score > 1 and "possible miss" in miss.reasons[0]
    assert score("d", _meta([0.45], qa=False)) is None          # blurred frames teach blur


def test_selection_spreads_out_and_keeps_random_controls():
    frames = [(f"u{i}", _meta([0.45], lat=50 + i * 1e-6)) for i in range(10)]     # one patch
    frames += [(f"far{i}", _meta([0.5], lat=50 + (i + 1) * 0.001)) for i in range(5)]
    frames += [(f"easy{i}", _meta([0.95], lat=51 + i * 0.001)) for i in range(20)]
    chosen = select(frames, n=10, seed=1)
    assert len(chosen) == 10
    scored = [c.entry_id for c in chosen if not c.random_pick]
    assert sum(1 for i in scored if i.startswith("u")) == 1, "one scored frame per patch"
    assert all(i.startswith(("u", "far")) for i in scored), "confident frames are not scored picks"
    assert sum(1 for c in chosen if c.random_pick) >= 1
    assert select(frames, n=10, seed=1)[0].entry_id == chosen[0].entry_id     # deterministic


# -- PNG --------------------------------------------------------------------------


def test_png_is_valid():
    img = (np.arange(4 * 5 * 3) % 256).astype(np.uint8).reshape(4, 5, 3)
    data = png.encode(img)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    assert (w, h) == (5, 4)
    idat = data[data.index(b"IDAT") + 4:data.index(b"IEND") - 8]
    raw = zlib.decompress(idat)
    assert raw[1:16] == img[0].tobytes()
    try:
        from PIL import Image
    except ImportError:
        return
    import io
    assert np.array_equal(np.asarray(Image.open(io.BytesIO(data))), img)


# -- Label Studio round trip --------------------------------------------------------


class _Guessing(InferenceEngine):
    def __init__(self):
        super().__init__(ModelMetadata(name="m", version="1", class_names=["kochia"]))

    def infer(self, image):
        return [Detection("kochia", 0.45, (0.25, 0.25, 0.5, 0.5))]


def test_export_then_import_as_coco_split_by_day(tmp_path):
    spool = Spool(tmp_path / "spool")
    from agri_edge.telemetry.mavlink_link import SimulatedTelemetry
    from agri_edge.config import QAConfig
    cfg = Config()
    cfg.qa = QAConfig(blur_threshold=1.0, required_bands=[])
    cfg.inference.confidence_threshold = 0.25
    pipe = Pipeline(cfg, SimulatedCamera(resolution=(40, 30), bands=["red", "green", "blue"]),
                    SimulatedTelemetry(), spool, _Guessing(), capture_mode="walk")
    for _ in range(3):
        meta = pipe.process_once()
    assert meta["capture_mode"] == "walk"
    entries = [e.to_dict() for e in spool.entries()]
    tasks_path = export_tasks(spool.dir, entries, tmp_path / "labeling")
    tasks = json.loads(tasks_path.read_text())
    assert len(tasks) == 3 and (tmp_path / "labeling" / "images" / f"{entries[0]['entry_id']}.png").exists()
    pred = tasks[0]["predictions"][0]["result"][0]
    assert pred["value"]["x"] == pytest.approx(25) and pred["value"]["rectanglelabels"] == ["kochia"]
    assert "<Label value=\"kochia\"/>" in label_config(["kochia"])

    # A labeller corrects the box on two tasks and skips the third.
    days = [datetime(2026, 7, 1, tzinfo=timezone.utc), datetime(2026, 7, 8, tzinfo=timezone.utc)]
    for t, day in zip(tasks[:2], days):
        t["data"]["captured_at"] = day.timestamp()
        t["annotations"] = [{"completed_by": {"email": "anwar@farm"}, "result": [
            {"type": "rectanglelabels", "value": {"x": 20, "y": 20, "width": 30, "height": 30,
                                                  "rectanglelabels": ["kochia"]}}]}]
    coco = import_coco(tasks, ["kochia"])
    assert len(coco["images"]) == 2 and len(coco["annotations"]) == 2
    assert coco["info"]["skipped_unlabelled"] == [tasks[2]["data"]["entry_id"]]
    assert coco["annotations"][0]["bbox"] == pytest.approx([8.0, 6.0, 12.0, 9.0])
    assert coco["images"][0]["labelled_by"] == "anwar@farm"
    train, val = split_by_day(coco)
    assert [i["capture_day"] for i in val["images"]] == ["2026-07-08"]
    assert len(train["images"]) == 1


def test_predictions_are_never_imported_as_labels():
    task = {"data": {"image": "x.png", "width": 10, "height": 10},
            "predictions": [{"result": [{"type": "rectanglelabels", "value": {
                "x": 0, "y": 0, "width": 50, "height": 50, "rectanglelabels": ["kochia"]}}]}]}
    assert import_coco([task], ["kochia"])["images"] == []


# -- metrics ----------------------------------------------------------------------


def test_ap_and_operating_point_by_hand():
    gt = {1: [("kochia", (0, 0, 10, 10))], 2: [("kochia", (0, 0, 10, 10))]}
    preds = {1: [("kochia", 0.9, (0, 0, 10, 10)), ("kochia", 0.8, (50, 50, 60, 60))],
             2: [("kochia", 0.2, (1, 1, 10, 10))]}
    (m,) = evaluate(gt, preds, ["kochia"], op_threshold=0.3)
    # Ranked: TP (P=1, R=.5), FP (P=.5), TP (P=.67, R=1). Envelope: 1.0 to R=.5, .67 to R=1.
    assert m.ap50 == pytest.approx(0.5 * 1.0 + 0.5 * 2 / 3, abs=1e-4)
    assert (m.tp_at_op, m.fp_at_op, m.recall_at_op) == (1, 1, 0.5)


# -- validation and trust ----------------------------------------------------------


def _coco(n_images, days):
    imgs = [{"id": i + 1, "entry_id": f"e{i}", "site": "farm", "field_id": "north",
             "capture_day": days[i % len(days)], "width": 100, "height": 100} for i in range(n_images)]
    anns = [{"id": i + 1, "image_id": i + 1, "category_id": 1, "bbox": [10, 10, 20, 20]}
            for i in range(n_images)]
    return {"images": imgs, "annotations": anns, "categories": [{"id": 1, "name": "kochia"}]}


def _model(tmp_path, claim=True):
    model = tmp_path / "m.onnx"
    model.write_bytes(b"weights-v1")
    (tmp_path / "m.onnx.meta.json").write_text(json.dumps(
        {"name": "m", "version": "1", "class_names": ["kochia"], "validated_locally": claim}))
    return model


def test_a_good_model_on_enough_local_data_passes(tmp_path):
    coco = _coco(200, ["2026-07-01", "2026-07-08"])
    preds = {i["id"]: [("kochia", 0.9, (10, 10, 30, 30))] for i in coco["images"]}
    r = run_validation(_model(tmp_path), "m", "1", coco, preds, Criteria(["kochia"]), "anwar")
    assert r["passed"], [c for c in r["checks"] if not c["passed"]]
    assert r["model_sha256"] == sha256_file(tmp_path / "m.onnx")
    assert write_report(r, tmp_path / "v").exists()


@pytest.mark.parametrize("n,days,reviewer,hit,failing", [
    (50, ["2026-07-01", "2026-07-08"], "anwar", True, "images"),
    (200, ["2026-07-01"], "anwar", True, "capture days"),
    (200, ["2026-07-01", "2026-07-08"], "", True, "reviewer"),
    (200, ["2026-07-01", "2026-07-08"], "anwar", False, "kochia AP50"),
])
def test_each_criterion_can_fail_the_validation(tmp_path, n, days, reviewer, hit, failing):
    coco = _coco(n, days)
    box = (10, 10, 30, 30) if hit else (60, 60, 90, 90)
    preds = {i["id"]: [("kochia", 0.9, box)] for i in coco["images"]}
    r = run_validation(_model(tmp_path), "m", "1", coco, preds, Criteria(["kochia"]), reviewer)
    assert not r["passed"]
    assert failing in [c["check"] for c in r["checks"] if not c["passed"]]


def test_a_meta_flag_alone_is_not_trusted(tmp_path, monkeypatch):
    monkeypatch.setenv("AGRIEDGE_VALIDATIONS_DIR", str(tmp_path / "v"))
    meta = ModelMetadata.load_beside(_model(tmp_path, claim=True))
    assert meta.validated_locally is False
    assert "no passing report" in meta.validation_notes


def test_a_matching_passing_report_is_trusted_and_a_changed_file_is_not(tmp_path, monkeypatch):
    monkeypatch.setenv("AGRIEDGE_VALIDATIONS_DIR", str(tmp_path / "v"))
    model = _model(tmp_path, claim=False)
    coco = _coco(200, ["2026-07-01", "2026-07-08"])
    preds = {i["id"]: [("kochia", 0.9, (10, 10, 30, 30))] for i in coco["images"]}
    write_report(run_validation(model, "m", "1", coco, preds, Criteria(["kochia"]), "anwar"), tmp_path / "v")
    assert ModelMetadata.load_beside(model).validated_locally is True
    model.write_bytes(b"weights-v2 retrained")          # same name, different file
    assert ModelMetadata.load_beside(model).validated_locally is False


def test_a_file_that_does_not_match_its_meta_hash_is_refused(tmp_path):
    model = _model(tmp_path)
    meta = json.loads((tmp_path / "m.onnx.meta.json").read_text())
    meta["sha256"] = "0" * 64
    (tmp_path / "m.onnx.meta.json").write_text(json.dumps(meta))
    with pytest.raises(RuntimeError):
        ModelMetadata.load_beside(model)


def test_trust_reasons_are_explicit(tmp_path):
    model = _model(tmp_path)
    assert "treated as NOT validated" in trust_for(model, True, []).reason
