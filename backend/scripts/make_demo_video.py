"""Builds a short demo clip from the sample photo bundled with Ultralytics (people on a street).

A virtual camera pans across the photo, so the people drift through the frame - enough to exercise detection,
tracking, zone entry, line crossing and dwell. For realistic testing, upload your own CCTV/phone footage.

    python scripts/make_demo_video.py demo_pan.mp4
"""
import sys
from pathlib import Path

import cv2
import numpy as np
import ultralytics

out = sys.argv[1] if len(sys.argv) > 1 else "demo_pan.mp4"
img = cv2.imread(str(Path(ultralytics.__file__).parent / "assets" / "bus.jpg"))
H0, W0 = img.shape[:2]
crop_w, crop_h, fps, secs = 480, 480, 25, 14
canvas = cv2.copyMakeBorder(img, 0, 0, crop_w, crop_w, cv2.BORDER_REPLICATE)  # pad so the pan starts/ends empty-ish
vw = cv2.VideoWriter(out, cv2.VideoWriter_fourcc(*"mp4v"), fps, (crop_w, crop_h))
n = fps * secs
for i in range(n):
    x = int(np.interp(i, [0, n - 1], [0, canvas.shape[1] - crop_w]))
    y = int(np.interp(i, [0, n - 1], [H0 * 0.35, H0 * 0.35]))
    frame = canvas[y:y + crop_h, x:x + crop_w]
    vw.write(frame)
vw.release()
print("wrote", out, f"({secs}s @ {fps}fps)")
