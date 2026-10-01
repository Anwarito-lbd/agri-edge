"""Store-and-forward spool.

Rural Canadian connectivity cannot be assumed, so the pipeline is built to run
entirely offline and upload opportunistically. Nothing in the capture path ever
blocks on the network.

Priority ordering matters: when the link comes up over a field edge for ninety
seconds, the frames that go first should be the ones carrying information
(detections, anomalies), not frame 1 of 4,000. Frames that failed QA go last --
but they do go, because the decision to discard data belongs to an agronomist on
the ground, not to a threshold on a Pi.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, asdict
from enum import IntEnum
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

class Priority(IntEnum):
    """Lower value uploads first."""

    ANOMALY = 0      # A detection worth acting on.
    NORMAL = 1       # Passed QA, nothing notable.
    DEGRADED = 2     # Failed QA. Kept, but last in the queue.


@dataclass
class SpoolEntry:
    entry_id: str
    priority: int
    created_at: float
    site: str
    field_id: str
    sequence: int
    image_path: str
    meta_path: str
    size_bytes: int
    uploaded: bool = False
    # Payload and sidecar deleted by the quota. Kept in the index as a record
    # that the frame existed, but never offered for upload again.
    evicted: bool = False
    # Image deleted by the quota, sidecar kept: still uploads as metadata.
    image_evicted: bool = False
    # An observation log for this frame exists in farmOS.
    farmos_pushed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class Spool:
    """A durable, priority-ordered on-disk queue.

    Each entry is an image plus a JSON sidecar holding telemetry, QA results and
    detections. The sidecar is the provenance record the report's data hierarchy
    depends on -- every derived product must be able to point back at the raw
    frame, the flight, the calibration and the model version that produced it.
    """

    INDEX_NAME = "index.jsonl"

    def __init__(self, spool_dir: Path, max_bytes: int = 64 * 1024 * 1024 * 1024):
        self.dir = Path(spool_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self._index_path = self.dir / self.INDEX_NAME

    # -- writing ---------------------------------------------------------------

    def add(
        self,
        image: np.ndarray,
        metadata: dict,
        priority: Priority,
        site: str,
        field_id: str,
        sequence: int,
    ) -> SpoolEntry:
        entry_id = f"{int(time.time() * 1000):013d}-{sequence:06d}"
        img_path = self.dir / f"{entry_id}.npy"
        meta_path = self.dir / f"{entry_id}.json"

        # .npy rather than a compressed image format: lossless, no encoder
        # dependency, and it preserves >8-bit multispectral data. Convert to
        # GeoTIFF on the workstation where rasterio is available.
        np.save(img_path, image)
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        entry = SpoolEntry(
            entry_id=entry_id,
            priority=int(priority),
            created_at=time.time(),
            site=site,
            field_id=field_id,
            sequence=sequence,
            image_path=str(img_path.name),
            meta_path=str(meta_path.name),
            size_bytes=img_path.stat().st_size + meta_path.stat().st_size,
        )
        with self._index_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict()) + "\n")

        self._enforce_quota()
        return entry

    # -- reading ---------------------------------------------------------------

    def entries(self, include_uploaded: bool = False, include_evicted: bool = False) -> list[SpoolEntry]:
        if not self._index_path.exists():
            return []
        out: list[SpoolEntry] = []
        for line in self._index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                # A truncated final line means power was lost mid-write. Skip it
                # rather than failing the whole spool; the frame is lost, the
                # queue is not.
                continue
            entry = SpoolEntry(**d)
            if entry.uploaded and not include_uploaded:
                continue
            if entry.evicted and not include_evicted:
                continue
            out.append(entry)
        return out

    def pending(self) -> list[SpoolEntry]:
        """Entries awaiting upload, in the order they should go."""
        return sorted(self.entries(), key=lambda e: (e.priority, e.created_at))

    def total_bytes(self) -> int:
        return sum(
            p.stat().st_size for p in self.dir.iterdir() if p.is_file() and p.name != self.INDEX_NAME
        )

    def stats(self) -> dict:
        pend = self.pending()
        by_priority: dict[str, int] = {}
        for e in pend:
            by_priority[Priority(e.priority).name] = by_priority.get(Priority(e.priority).name, 0) + 1
        return {
            "pending": len(pend),
            "by_priority": by_priority,
            "total_bytes": self.total_bytes(),
            "max_bytes": self.max_bytes,
            "utilisation": (self.total_bytes() / self.max_bytes) if self.max_bytes else 0.0,
        }

    # -- completion ------------------------------------------------------------

    def mark_uploaded(self, entry_ids: list[str]) -> int:
        """Rewrite the index marking the given entries uploaded."""
        return self._mark(entry_ids, "uploaded")

    def mark_evicted(self, entry_ids: list[str]) -> int:
        """Record that these entries' files are gone and must not be uploaded."""
        return self._mark(entry_ids, "evicted")

    def mark_farmos_pushed(self, entry_ids: list[str]) -> int:
        """Record that farmOS holds a log for these entries."""
        return self._mark(entry_ids, "farmos_pushed")

    def _mark(self, entry_ids: list[str], flag: str) -> int:
        """Set a boolean flag on index rows.

        Written to a temp file and moved into place so an interruption leaves the
        previous index intact rather than a half-written one.
        """
        if not self._index_path.exists() or not entry_ids:
            return 0
        ids = set(entry_ids)
        tmp = self._index_path.with_suffix(".jsonl.tmp")
        count = 0
        with tmp.open("w", encoding="utf-8") as out:
            for line in self._index_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("entry_id") in ids and not d.get(flag):
                    d[flag] = True
                    count += 1
                out.write(json.dumps(d) + "\n")
        tmp.replace(self._index_path)
        return count

    def purge_uploaded(self) -> int:
        """Delete the payload files of uploaded entries, keeping the index record.

        The index row stays so there is a permanent record that the frame existed
        and where it went, even after the bytes are gone from the aircraft.
        """
        removed = 0
        for entry in self.entries(include_uploaded=True):
            if not entry.uploaded:
                continue
            for name in (entry.image_path, entry.meta_path):
                p = self.dir / name
                if p.exists():
                    p.unlink()
                    removed += 1
        return removed

    def _enforce_quota(self) -> None:
        """Drop the lowest-value data first when the disk fills.

        Order of sacrifice:

        1. payloads of frames already uploaded;
        2. QA-failed frames, oldest first -- image and sidecar;
        3. the IMAGES of ordinary frames, oldest first. Their sidecars stay:
           a few kB each, and they carry the flight record and the decision.

        Anomaly frames are never dropped by the quota -- if the spool is full of
        anomalies, that is a situation for a human, not for an eviction policy.

        Until 24 Sept 2026 only steps 1-2 existed, and evicted entries stayed
        "pending" in the index. So a spool of ordinary frames filled the disk and
        every later save failed, and the uploader tripped over the missing files
        of evicted entries on every pass and stopped, forever.
        """
        if self.max_bytes <= 0 or self.total_bytes() <= self.max_bytes:
            return

        self.purge_uploaded()
        if self.total_bytes() <= self.max_bytes:
            return

        by_age = sorted(self.pending(), key=lambda e: e.created_at)

        evicted: list[str] = []
        try:
            for entry in (e for e in by_age if e.priority == Priority.DEGRADED):
                for name in (entry.image_path, entry.meta_path):
                    (self.dir / name).unlink(missing_ok=True)
                evicted.append(entry.entry_id)
                if self.total_bytes() <= self.max_bytes:
                    return
        finally:
            self.mark_evicted(evicted)

        images_dropped: list[str] = []
        try:
            for entry in (e for e in by_age if e.priority == Priority.NORMAL and not e.image_evicted):
                (self.dir / entry.image_path).unlink(missing_ok=True)
                images_dropped.append(entry.entry_id)
                if self.total_bytes() <= self.max_bytes:
                    return
        finally:
            self._mark(images_dropped, "image_evicted")

        log.warning(
            "Spool over quota (%d of %d bytes) with only anomaly frames left. "
            "Offload the spool; nothing more will be evicted automatically.",
            self.total_bytes(), self.max_bytes,
        )

    def export(self, dest: Path) -> int:
        """Copy the spool to removable media, for the drive back to the office.

        The realistic transfer mechanism for a rural operation is an SSD in a
        vehicle, not a cellular link.
        """
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        copied = 0
        for entry in self.pending():
            for name in (entry.image_path, entry.meta_path):
                src = self.dir / name
                if src.exists():
                    shutil.copy2(src, dest / name)
                    copied += 1
        if self._index_path.exists():
            shutil.copy2(self._index_path, dest / self.INDEX_NAME)
        return copied
