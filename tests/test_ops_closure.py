
"""Closure tests for PARTIAL/STUB → DONE items (§108–159 extras + db)."""
from __future__ import annotations

import os
from pathlib import Path

from agri_edge.ops.store import reset_store
from agri_edge.ops.simulate import seed_demo
from agri_edge.ops.geo import build_microclimate_grid, default_map_assets
from agri_edge.ops.vra import make_demo_prescription, validate_prescription, approve_prescription, list_cells, feedback_maps
from agri_edge.ops.odm import ODMPipelineStub
from agri_edge.ops.map3d import scene, vr_status
from agri_edge.ops.analytics import battery_analytics, energy_analytics, water_analytics, application_analytics
from agri_edge.ops.irrigation import irrigation_dashboard
from agri_edge.ops.db import get_sensor_db, reset_sensor_db, parse_sqlite_path
from agri_edge.ops.schema import SensorReading
from agri_edge.ops.types import new_id, utcnow


def test_microclimate_interpolated_grid():
    g = build_microclimate_grid()
    assert g["stub"] is False
    kinds = {f["properties"]["kind"] for f in g["features"]}
    assert "measured" in kinds and "interpolated" in kinds
    assets = default_map_assets()
    mc = next(a for a in assets if a.layer_kind == "microclimate")
    assert mc.meta.get("stub") is False
    ch = next(a for a in assets if "health" in a.layer_kind or a.asset_id.endswith("crop_health"))
    assert ch.geotiff_path
    assert ch.meta.get("stub") is False


def test_vra_feedback_and_approve():
    rx = make_demo_prescription()
    fb = feedback_maps(rx.prescription_id, rx.cells)
    assert fb["stub"] is False
    assert len(fb["error"]["features"]) >= 1
    cells = list_cells(rx)
    assert cells["count"] >= 1
    # force validate then approve
    rx.validated = True
    result = approve_prescription(rx, actor="tester", wind_ms=1.0)
    assert result["approved"] is True
    assert result["auto_apply"] is False


def test_mapfield_odm_async_completes():
    import time
    store = reset_store()
    seed_demo(store)
    pipe = ODMPipelineStub()
    wf = pipe.create_workflow("field_north")
    assert pipe.validate_workflow(wf.workflow_id)["ok"]
    assert pipe.approve_workflow(wf.workflow_id)["ok"]
    out = pipe.execute_workflow(wf.workflow_id, store=store)
    assert out["blocking"] is False
    job = pipe.get(out["odm_job"]["job_id"]) if "odm_job" in out else pipe.jobs[wf.odm_job_id]
    # wait briefly for async done
    for _ in range(50):
        j = pipe.get(job.job_id) if hasattr(job, "job_id") else job
        status = j.status if hasattr(j, "status") else j["status"]
        if status == "done":
            break
        time.sleep(0.02)
    j = pipe.get(job.job_id) if hasattr(job, "job_id") else job
    status = j.status if hasattr(j, "status") else j["status"]
    assert status == "done"
    # RGB_ORTHO map asset attached
    assert any(
        (getattr(a, "meta", {}) or {}).get("product") == "RGB_ORTHO" or "ORTHO" in a.name.upper()
        for a in store.map_assets.values()
    )


def test_scene_and_vr_status():
    sc = scene()
    assert sc["stub"] is False
    assert "terrain" in sc and "fields" in sc and "vehicles" in sc and "stations" in sc
    vr = vr_status()
    assert vr["supported"] is False
    assert vr.get("safety_critical") is False


def test_battery_energy_water_application_seeded():
    store = reset_store()
    seed_demo(store)
    b = battery_analytics(store)
    assert b["stub"] is False
    assert any(i.get("pack_id") for i in b["items"])
    e = energy_analytics(store)
    assert e["stub"] is False and e["mission_count"] >= 1
    w = water_analytics(store)
    assert w["stub"] is False and w["mismatches"]
    a = application_analytics(store)
    assert a["stub"] is False and a["weeds_detected"] >= 1


def test_observation_seeds_and_irrigation_zones():
    store = reset_store()
    seed_demo(store)
    assert store.cameras and store.scouts and store.manual and store.notes
    dash = irrigation_dashboard(store)
    assert dash["zones"]
    assert dash["safety"]["auto_execute"] is False


def test_sqlite_sensor_store(tmp_path):
    reset_sensor_db()
    path = tmp_path / "sensors.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{path}"
    try:
        db = get_sensor_db()
        assert db is not None
        reading = SensorReading(
            reading_id=new_id("sr_"),
            sensor_id="soil1",
            ts=utcnow().isoformat(),
            metric="moisture_pct",
            value=22.5,
            unit="%",
            synthetic=True,
        )
        db.upsert(reading)
        rows = db.list(sensor_id="soil1")
        assert len(rows) >= 1
        assert parse_sqlite_path(os.environ["DATABASE_URL"]).endswith("sensors.db")
    finally:
        os.environ.pop("DATABASE_URL", None)
        reset_sensor_db()


def test_ui_map3d_and_postgis_schema_exist():
    assert Path("src/agri_edge/ops/ui/map3d.html").exists()
    html = Path("src/agri_edge/ops/ui/map3d.html").read_text()
    assert "SIMULATION" in html
    assert Path("docs/operations/schema_postgis.sql").exists()
    sql = Path("docs/operations/schema_postgis.sql").read_text()
    assert "postgis" in sql.lower() and "sensor_readings" in sql
