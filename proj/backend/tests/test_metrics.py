import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))
from metrics import match_events, prf, recall_at_k  # noqa: E402


def ev(video, cat, start): return {"video": video, "category": cat, "start": start}


def test_matching_and_prf():
    gt = [ev("a", "line", 10), ev("a", "line", 30), ev("a", "restricted", 50)]
    pred = [ev("a", "line", 11), ev("a", "line", 80), ev("a", "restricted", 49), ev("b", "line", 10)]
    m, fp, fn = match_events(pred, gt, tol=2)
    assert len(m) == 2 and len(fp) == 2 and len(fn) == 1  # 80s and other-video are FPs; 30s is a miss
    assert prf(2, 2, 1) == {"tp": 2, "fp": 2, "fn": 1, "precision": 0.5, "recall": 0.667, "f1": 0.571}


def test_each_ground_truth_matches_once():
    m, fp, _ = match_events([ev("a", "line", 10), ev("a", "line", 10.5)], [ev("a", "line", 10)], tol=2)
    assert len(m) == 1 and len(fp) == 1


def test_recall_at_k():
    assert recall_at_k([False, True, True], 2, 1) == 0.0
    assert recall_at_k([False, True, True], 2, 3) == 1.0
