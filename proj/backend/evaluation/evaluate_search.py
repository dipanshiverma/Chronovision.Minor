"""Natural-language search quality: Recall@k and timestamp accuracy.

Query file (JSON list). `relevant` are ground-truth events the question should return:
  [{"q": "when did someone steal the bag", "relevant": [{"video": "lobby.mp4", "category": "transfer", "start": 12.4}]}]
  python evaluation/evaluate_search.py queries.json --k 1 3 5
Runs the real parser + retrieval (LLM parsing is used if ANTHROPIC_API_KEY is set; compare both by toggling it).
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import config, nlq  # noqa: E402
from app.db import connect  # noqa: E402
from metrics import recall_at_k  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queries")
    ap.add_argument("--k", type=int, nargs="+", default=[1, 3, 5])
    ap.add_argument("--tolerance", type=float, default=2.0)
    a = ap.parse_args()

    with connect() as c:
        names = [r["filename"] for r in c.execute("SELECT filename FROM videos")]
        vid_name = {r["id"]: r["filename"] for r in c.execute("SELECT id, filename FROM videos")}
    queries = json.load(open(a.queries))
    recalls = {k: [] for k in a.k}
    errors = []
    for item in queries:
        results = [r for r in nlq.run_search(nlq.parse_query(item["q"], names))["results"] if r.get("type") == "event"]
        rel = item["relevant"]
        hit_flags, used = [], set()
        for r in results:
            hit = False
            for i, g in enumerate(rel):
                if i in used:
                    continue
                if r["filename"] == g["video"] and r["kind"] == g["category"] and abs(r["startSec"] - g["start"]) <= a.tolerance:
                    used.add(i); hit = True; errors.append(abs(r["startSec"] - g["start"])); break
            hit_flags.append(hit)
        for k in a.k:
            recalls[k].append(recall_at_k(hit_flags, len(rel), k))
    out = {f"Recall@{k}": round(sum(v) / len(v), 3) for k, v in recalls.items()}
    out["timestamp_mae_s"] = round(sum(errors) / len(errors), 2) if errors else None
    out["queries"] = len(queries)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
