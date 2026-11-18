"""Runtime performance: processing speed, latency per frame and peak memory on a video.

  python evaluation/evaluate_runtime.py path/to/video.mp4
"""
import resource
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.detector import YoloByteTrackDetector  # noqa: E402


def main(path: str):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    stride = max(1, round(fps / config.PROCESS_FPS))
    det = YoloByteTrackDetector()
    det.start_video()
    lat, idx = [], 0
    t0 = time.time()
    while cap.grab():
        if idx % stride == 0:
            ok, frame = cap.retrieve()
            if ok:
                s = time.perf_counter()
                det.track(frame)
                lat.append(time.perf_counter() - s)
        idx += 1
    wall = time.time() - t0
    lat.sort()
    peak_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"model={config.MODEL_NAME} device={config.DEVICE or 'auto'} analysed {len(lat)} frames "
          f"(stride {stride} of {fps:.0f} fps source)")
    print(f"video length {idx / fps:.1f}s -> wall {wall:.1f}s  ({(idx / fps) / wall:.2f}x real time)")
    print(f"latency/frame: median {lat[len(lat)//2]*1000:.0f} ms, p95 {lat[int(len(lat)*0.95)]*1000:.0f} ms")
    print(f"peak memory: {peak_mb:.0f} MB")


if __name__ == "__main__":
    main(sys.argv[1])
