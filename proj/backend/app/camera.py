"""Global camera-motion estimate (panning / handheld footage).

Without this, every stationary object in a panning shot would look like it is moving, which would trigger false
"running" or "following" events. We estimate the whole-image shift between consecutive analysed frames with phase
correlation and accumulate it, so entity motion can be measured in a world frame (image position minus camera shift).
For a fixed camera the shift is ~0 and is ignored (dead-zone), so nothing changes."""
from __future__ import annotations

import cv2
import numpy as np

_W = 160


class CameraMotion:
    def __init__(self) -> None:
        self.prev: np.ndarray | None = None
        self.win: np.ndarray | None = None
        self.cum = np.zeros(2)  # accumulated content shift as a fraction of frame width / height

    def update(self, frame) -> tuple[float, float]:
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h = max(8, int(_W * g.shape[0] / g.shape[1]))
        small = cv2.resize(g, (_W, h), interpolation=cv2.INTER_AREA).astype(np.float32)
        if self.prev is not None and self.prev.shape == small.shape:
            if self.win is None or self.win.shape != small.shape:
                self.win = cv2.createHanningWindow((small.shape[1], small.shape[0]), cv2.CV_32F)
            (dx, dy), resp = cv2.phaseCorrelate(self.prev, small, self.win)
            # Ignore unreliable matches and sub-pixel jitter; accept real shifts only.
            if resp >= 0.1 and (abs(dx) >= 0.4 or abs(dy) >= 0.4) and abs(dx) < _W / 3 and abs(dy) < h / 3:
                self.cum += (dx / _W, dy / h)
        self.prev = small
        return float(self.cum[0]), float(self.cum[1])
