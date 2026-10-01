"""Which spooled frames deserve a person's labelling time.

Labelling is the expensive step, and labelling the frames a model already
gets right teaches it nothing. Scores, highest first:

* **uncertain detections** -- confidence between 0.25 and 0.6: the model is
  guessing, and the label settles it;
* **possible misses** -- clearly green frames (ExG p95 or NDVI p95 high) with
  no detection at all: either bare crop or a weed the model cannot see;
* **new ground** -- frames far from anything already chosen, so one patch
  does not fill the whole batch.

A fixed share of frames (default 15 %) is drawn at random regardless of score.
Active learning alone biases the labelled set toward hard cases, and a
validation set built only from hard cases misstates field performance.
Selection is deterministic for a given seed.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

UNCERTAIN = (0.25, 0.6)


@dataclass
class Candidate:
    entry_id: str
    score: float
    reasons: list[str] = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    random_pick: bool = False

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _green(meta: dict) -> float | None:
    idx = meta.get("indices") or {}
    for key, thr in (("ndvi", 0.4), ("excess_green", 0.1)):
        s = idx.get(key) or {}
        if s.get("p95") is not None:
            return float(s["p95"]) - thr
    return None


def score(entry_id: str, meta: dict) -> Candidate | None:
    qa = meta.get("qa") or {}
    if qa.get("passed") is False:
        return None                         # a blurred frame teaches blur
    dets = meta.get("detections") or []
    t = meta.get("telemetry") or {}
    c = Candidate(entry_id, 0.0, lat=t.get("lat"), lon=t.get("lon"))
    unsure = [d for d in dets if UNCERTAIN[0] <= float(d.get("confidence", 0)) <= UNCERTAIN[1]]
    if unsure:
        c.score += len(unsure) + sum(1 - abs(float(d["confidence"]) - 0.425) / 0.175 for d in unsure) / 2
        c.reasons.append(f"{len(unsure)} uncertain detection(s)")
    g = _green(meta)
    if not dets and g is not None and g > 0:
        c.score += 1.5 + min(g * 5, 1.5)
        c.reasons.append("green frame with no detection (possible miss)")
    if meta.get("inference_error"):
        c.reasons.append("inference failed on this frame")
    return c


def _dist_m(a: Candidate, b: Candidate) -> float:
    if None in (a.lat, a.lon, b.lat, b.lon):
        return math.inf
    dlat = math.radians(b.lat - a.lat)      # type: ignore[operator]
    dlon = math.radians(b.lon - a.lon) * math.cos(math.radians(a.lat))  # type: ignore[operator, arg-type]
    return 6_371_000 * math.hypot(dlat, dlon)


def select(frames: list[tuple[str, dict]], n: int, *, min_spacing_m: float = 15.0,
           random_share: float = 0.15, seed: int = 0) -> list[Candidate]:
    """frames: (entry_id, sidecar metadata). Returns up to n candidates."""
    cands = [c for c in (score(e, m) for e, m in frames) if c is not None]
    rng = random.Random(seed)
    n_random = min(len(cands), int(round(n * random_share)))
    chosen: list[Candidate] = []
    for c in sorted(cands, key=lambda c: (-c.score, c.entry_id)):
        if len(chosen) >= n - n_random or c.score <= 0:
            break
        if all(_dist_m(c, o) >= min_spacing_m for o in chosen):
            chosen.append(c)
    picked = {c.entry_id for c in chosen}
    pool = [c for c in cands if c.entry_id not in picked]
    for c in rng.sample(pool, min(len(pool), n - len(chosen))):
        c.random_pick = True
        c.reasons.append("random control sample")
        chosen.append(c)
    return chosen
