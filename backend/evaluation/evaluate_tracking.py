"""Tracking accuracy (IDF1, MOTA, ID switches) on a MOTChallenge-format sequence such as MOT17.

  python evaluation/evaluate_tracking.py /data/MOT17/train/MOT17-02-FRCNN
needs  <seq>/img1/*.jpg  and  <seq>/gt/gt.txt, plus `pip install motmetrics`.
Runs the SAME detector+ByteTrack configuration as the app (config.py / bytetrack.yaml), people only.
HOTA is not computed here; use the official TrackEval toolkit on the MOT-format file this script also writes (--out).
"""
import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.detector import YoloByteTrackDetector  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sequence")
    ap.add_argument("--out", default="tracker_output.txt")
    a = ap.parse_args()
    import motmetrics as mm  # imported late so the other scripts do not require it

    seq = Path(a.sequence)
    frames = sorted((seq / "img1").glob("*.jpg"))
    det = YoloByteTrackDetector()
    det.start_video()
    rows, t0 = [], time.time()
    for i, f in enumerate(frames, 1):
        for t in det.track(cv2.imread(str(f))):
            x1, y1, x2, y2 = t.bbox
            rows.append((i, t.track_id, x1, y1, x2 - x1, y2 - y1, t.conf))
    fps = len(frames) / (time.time() - t0)
    Path(a.out).write_text("\n".join(f"{f},{i},{x:.1f},{y:.1f},{w:.1f},{h:.1f},{c:.3f},-1,-1,-1" for f, i, x, y, w, h, c in rows))

    gt = mm.io.loadtxt(seq / "gt" / "gt.txt", fmt="mot15-2D", min_confidence=1)  # considered pedestrians only
    ts = mm.io.loadtxt(a.out, fmt="mot15-2D")
    acc = mm.utils.compare_to_groundtruth(gt, ts, "iou", distth=0.5)
    summ = mm.metrics.create().compute(acc, metrics=["idf1", "idp", "idr", "recall", "precision", "mota", "num_switches"], name=seq.name)
    print(mm.io.render_summary(summ, namemap=mm.io.motchallenge_metric_names))
    print(f"speed: {fps:.1f} frames/s")


if __name__ == "__main__":
    main()
