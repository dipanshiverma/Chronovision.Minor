"""Pure metric helpers (tested in tests/test_metrics.py)."""
from __future__ import annotations


def match_events(pred: list[dict], gt: list[dict], tol: float = 2.0):
    """Greedy one-to-one matching of predicted to ground-truth events of the same (video, category).
    A prediction is a true positive when |pred.start - gt.start| <= tol seconds.
    Returns (matches[(pred, gt)], unmatched_pred, unmatched_gt)."""
    used, matches = set(), []
    for p in sorted(pred, key=lambda e: e["start"]):
        best, best_d = None, tol + 1e-9
        for i, g in enumerate(gt):
            if i in used or g["video"] != p["video"] or g["category"] != p["category"]:
                continue
            d = abs(p["start"] - g["start"])
            if d <= best_d:
                best, best_d = i, d
        if best is not None:
            used.add(best)
            matches.append((p, gt[best]))
    matched_pred = {id(p) for p, _ in matches}
    return (matches, [p for p in pred if id(p) not in matched_pred], [g for i, g in enumerate(gt) if i not in used])


def prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def recall_at_k(ranked: list[bool], n_relevant: int, k: int) -> float:
    """Fraction of the relevant items found in the top-k results."""
    return sum(ranked[:k]) / n_relevant if n_relevant else 0.0
