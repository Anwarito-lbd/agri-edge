"""Detection metrics, pure numpy: per-class AP at IoU 0.5, and precision /
recall at the operating threshold the aircraft actually uses.

AP uses all-point interpolation of the precision envelope (as in PASCAL VOC
2010+ and COCO's per-threshold AP). Matching is greedy by descending score,
one prediction per ground-truth box.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Box = tuple[float, float, float, float]   # x0, y0, x1, y1


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


@dataclass
class ClassMetrics:
    label: str
    n_gt: int
    ap50: float
    precision_at_op: float
    recall_at_op: float
    tp_at_op: int
    fp_at_op: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def evaluate(gt: dict[int, list[tuple[str, Box]]], preds: dict[int, list[tuple[str, float, Box]]],
             labels: list[str], op_threshold: float = 0.3, iou_thr: float = 0.5) -> list[ClassMetrics]:
    out = []
    for label in labels:
        gts = {i: [b for c, b in boxes if c == label] for i, boxes in gt.items()}
        n_gt = sum(len(v) for v in gts.values())
        cand = sorted(((s, i, b) for i, ps in preds.items() for c, s, b in ps if c == label),
                      key=lambda x: -x[0])
        used = {i: np.zeros(len(v), dtype=bool) for i, v in gts.items()}
        tp = np.zeros(len(cand))
        for k, (_, i, b) in enumerate(cand):
            best, best_j = 0.0, -1
            for j, g in enumerate(gts.get(i, [])):
                if not used[i][j]:
                    o = iou(b, g)
                    if o > best:
                        best, best_j = o, j
            if best >= iou_thr:
                used[i][best_j] = True
                tp[k] = 1
        scores = np.array([c[0] for c in cand])
        ctp, cfp = np.cumsum(tp), np.cumsum(1 - tp)
        recall = ctp / n_gt if n_gt else np.zeros_like(ctp)
        precision = ctp / np.maximum(ctp + cfp, 1e-12)
        if n_gt and len(cand):
            mrec = np.concatenate([[0.0], recall, [1.0]])
            mpre = np.concatenate([[1.0], precision, [0.0]])
            mpre = np.maximum.accumulate(mpre[::-1])[::-1]
            idx = np.where(mrec[1:] != mrec[:-1])[0]
            ap = float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))
        else:
            ap = 0.0
        at = scores >= op_threshold
        tp_op, fp_op = int(tp[at].sum()), int((1 - tp[at]).sum())
        out.append(ClassMetrics(label, n_gt, round(ap, 4),
                                round(tp_op / (tp_op + fp_op), 4) if tp_op + fp_op else 0.0,
                                round(tp_op / n_gt, 4) if n_gt else 0.0, tp_op, fp_op))
    return out
