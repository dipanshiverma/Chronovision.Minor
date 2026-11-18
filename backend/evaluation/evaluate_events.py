"""Event-detection accuracy: precision / recall / F1 / detection delay against hand-labelled ground truth.

Ground-truth file (JSON list), times in seconds:
  [{"video": "lobby.mp4", "category": "transfer", "start": 12.4},
   {"video": "lobby.mp4", "category": "running", "start": 30.0, "end": 41.0}]
  ("category" = event kind: transfer, handover, pickup, carry, approach, approach_flee, following, running, loitering,
   unattended, abandoned, vehicle_proximity, restricted_entry, line_crossing, prolonged_presence)
Analyse the same videos in ChronoVision first, then:
  python evaluation/evaluate_events.py gt.json --tolerance 2.0
"""
import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import config  # noqa: E402
from metrics import match_events, prf  # noqa: E402


def load_predictions(db_path) -> list[dict]:
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    rows = c.execute("SELECT v.filename, e.kind AS category, e.start_sec, e.end_sec, e.details_json FROM events e "
                     "JOIN videos v ON v.id=e.video_id WHERE v.status='Completed'").fetchall()
    out = []
    for r in rows:
        d = json.loads(r["details_json"] or "{}")
        out.append({"video": r["filename"], "category": r["category"], "start": r["start_sec"], "end": r["end_sec"],
                    "detected_at": d.get("detectedAt", r["start_sec"])})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ground_truth")
    ap.add_argument("--tolerance", type=float, default=2.0, help="seconds allowed between predicted and true start")
    ap.add_argument("--db", default=str(config.DB_PATH))
    a = ap.parse_args()

    gt = json.load(open(a.ground_truth))
    videos = {g["video"] for g in gt}
    pred = [p for p in load_predictions(a.db) if p["video"] in videos]  # only score videos that have labels
    matches, fps_, fns = match_events(pred, gt, a.tolerance)

    per = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "delays": []})
    for p, g in matches:
        per[p["category"]]["tp"] += 1
        per[p["category"]]["delays"].append(p["detected_at"] - g["start"])
    for p in fps_: per[p["category"]]["fp"] += 1
    for g in fns: per[g["category"]]["fn"] += 1

    report = {}
    for cat, v in sorted(per.items()):
        r = prf(v["tp"], v["fp"], v["fn"])
        r["mean_detection_delay_s"] = round(sum(v["delays"]) / len(v["delays"]), 2) if v["delays"] else None
        report[cat] = r
    tot = prf(sum(v["tp"] for v in per.values()), sum(v["fp"] for v in per.values()), sum(v["fn"] for v in per.values()))
    report["overall"] = tot
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
