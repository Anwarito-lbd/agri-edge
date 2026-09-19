"""MapField workflow + ODM pipeline — async, non-blocking (§112–113)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

from .schema import MapAsset
from .types import new_id, utcnow


@dataclass
class ODMJob:
    job_id: str
    field_id: str
    status: str = "queued"  # queued|running|done|failed
    created_at: str = ""
    finished_at: Optional[str] = None
    result_asset_id: Optional[str] = None
    synthetic: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MapFieldWorkflow:
    """§112 select field → sensor → GSD → route → validate → approve → execute → publish."""
    workflow_id: str
    field_id: str
    sensor: str = "rgb"
    gsd_cm: float = 2.5
    route_stub: list[dict[str, float]] = field(default_factory=list)
    validated: bool = False
    approved: bool = False
    status: str = "draft"  # draft|validated|approved|executing|done|failed
    odm_job_id: Optional[str] = None
    map_asset_id: Optional[str] = None
    synthetic: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ODMPipeline:
    def __init__(self) -> None:
        self.jobs: dict[str, ODMJob] = {}
        self.workflows: dict[str, MapFieldWorkflow] = {}
        self._lock = threading.Lock()

    def submit(self, field_id: str, store: Any = None, *, delay_s: float = 0.05) -> ODMJob:
        """Non-blocking submit — returns immediately; finishes async to done + MapAsset."""
        job = ODMJob(
            job_id=new_id("odm_"),
            field_id=field_id,
            status="queued",
            created_at=utcnow().isoformat(),
            synthetic=True,
        )
        with self._lock:
            self.jobs[job.job_id] = job

        def _run() -> None:
            job.status = "running"
            time.sleep(delay_s)
            asset_id = f"odm_rgb_ortho_{job.job_id}"
            job.result_asset_id = asset_id
            job.status = "done"
            job.finished_at = utcnow().isoformat()
            if store is not None:
                store.map_assets[asset_id] = MapAsset(
                    asset_id=asset_id,
                    name=f"RGB_ORTHO {field_id}",
                    layer_kind="odm",
                    geotiff_path=f"sim://odm/{field_id}/{job.job_id}/rgb_ortho.tif",
                    enabled=True,
                    farm_id="demo_farm",
                    time_range="now",
                    synthetic=True,
                    meta={
                        "product": "RGB_ORTHO",
                        "odm_job_id": job.job_id,
                        "field_id": field_id,
                        "origin": "DERIVED",
                        "algorithm_version": "odm_sim_v1",
                    },
                )

        threading.Thread(target=_run, daemon=True).start()
        return job

    def get(self, job_id: str) -> Optional[ODMJob]:
        return self.jobs.get(job_id)

    def create_workflow(
        self,
        field_id: str = "field_north",
        *,
        sensor: str = "rgb",
        gsd_cm: float = 2.5,
    ) -> MapFieldWorkflow:
        wf = MapFieldWorkflow(
            workflow_id=new_id("mf_"),
            field_id=field_id,
            sensor=sensor,
            gsd_cm=gsd_cm,
            route_stub=[
                {"lat": 45.4005, "lon": -75.6995},
                {"lat": 45.4005, "lon": -75.6905},
                {"lat": 45.4095, "lon": -75.6905},
                {"lat": 45.4095, "lon": -75.6995},
            ],
            created_at=utcnow().isoformat(),
            synthetic=True,
        )
        self.workflows[wf.workflow_id] = wf
        return wf

    def validate_workflow(self, workflow_id: str) -> dict[str, Any]:
        wf = self.workflows[workflow_id]
        issues = []
        if not wf.field_id:
            issues.append("field required")
        if wf.gsd_cm <= 0 or wf.gsd_cm > 20:
            issues.append("GSD out of range")
        if not wf.route_stub:
            issues.append("route stub empty")
        if not issues:
            wf.validated = True
            wf.status = "validated"
        return {"ok": not issues, "issues": issues, "workflow": wf.to_dict()}

    def approve_workflow(self, workflow_id: str, actor: str = "operator") -> dict[str, Any]:
        wf = self.workflows[workflow_id]
        if not wf.validated:
            return {"ok": False, "issues": ["must validate first"], "workflow": wf.to_dict()}
        wf.approved = True
        wf.status = "approved"
        return {"ok": True, "actor": actor, "workflow": wf.to_dict(), "auto_execute": False}

    def execute_workflow(self, workflow_id: str, store: Any = None) -> dict[str, Any]:
        """Execute sim — submits ODM without blocking caller; mission API stays free."""
        wf = self.workflows[workflow_id]
        if not wf.approved:
            return {"ok": False, "issues": ["must approve first"], "workflow": wf.to_dict()}
        wf.status = "executing"
        job = self.submit(wf.field_id, store=store)
        wf.odm_job_id = job.job_id

        def _watch() -> None:
            for _ in range(100):
                if job.status == "done":
                    wf.status = "done"
                    wf.map_asset_id = job.result_asset_id
                    return
                if job.status == "failed":
                    wf.status = "failed"
                    return
                time.sleep(0.02)

        threading.Thread(target=_watch, daemon=True).start()
        return {
            "ok": True,
            "workflow": wf.to_dict(),
            "odm_job": job.to_dict(),
            "blocking": False,
            "note": "ODM runs async; mission API never blocked",
        }


# Back-compat alias
ODMPipelineStub = ODMPipeline
