"""MapField workflow + ODM pipeline stub — async, non-blocking (§112–113)."""
from __future__ import annotations

import threading
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

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


class ODMPipelineStub:
    def __init__(self) -> None:
        self.jobs: dict[str, ODMJob] = {}

    def submit(self, field_id: str) -> ODMJob:
        job = ODMJob(
            job_id=new_id("odm_"),
            field_id=field_id,
            status="queued",
            created_at=utcnow().isoformat(),
            synthetic=True,
        )
        self.jobs[job.job_id] = job

        def _run() -> None:
            job.status = "running"
            # Immediate stub completion — non-blocking submit already returned
            job.status = "done"
            job.finished_at = utcnow().isoformat()
            job.result_asset_id = f"odm_asset_{job.job_id}"

        threading.Thread(target=_run, daemon=True).start()
        return job

    def get(self, job_id: str) -> Optional[ODMJob]:
        return self.jobs.get(job_id)
