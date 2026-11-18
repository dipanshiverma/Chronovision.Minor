"""YOLO detection + ByteTrack tracking via Ultralytics, for people, animals and objects."""
from __future__ import annotations

import threading
from typing import Protocol

from . import config, taxonomy
from .events import TrackObs


class Detector(Protocol):
    def start_video(self) -> None: ...
    def track(self, frame) -> list[TrackObs]: ...


class YoloByteTrackDetector:
    def __init__(self) -> None:
        from ultralytics import YOLO  # heavy import, so only when actually analysing

        self.model = YOLO(config.MODEL_NAME)  # auto-downloads weights on first use
        self.classes = config.CLASSES or sorted(taxonomy.COCO)

    def start_video(self) -> None:
        # Dropping the predictor discards the tracker, so IDs/state never leak between videos.
        self.model.predictor = None

    def track(self, frame) -> list[TrackObs]:
        res = self.model.track(
            frame, persist=True, tracker=str(config.TRACKER_YAML), classes=self.classes, conf=config.DETECT_CONF,
            imgsz=config.IMGSZ, device=config.DEVICE, verbose=False,
        )[0]
        boxes = res.boxes
        if boxes is None or boxes.id is None:
            return []
        out = []
        for xyxy, tid, conf, cls in zip(boxes.xyxy.tolist(), boxes.id.int().tolist(),
                                        boxes.conf.tolist(), boxes.cls.int().tolist()):
            if cls not in taxonomy.COCO:
                continue
            group, label = taxonomy.COCO[cls]
            if conf < taxonomy.MIN_CONF[group]:
                continue
            out.append(TrackObs(track_id=tid, bbox=tuple(xyxy), conf=float(conf), label=label, group=group))
        return out


_detector: Detector | None = None
_lock = threading.Lock()


def get_detector() -> Detector:
    global _detector
    with _lock:
        if _detector is None:
            _detector = YoloByteTrackDetector()
        return _detector


def set_detector(d: Detector | None) -> None:
    """Swap the detector (used by tests)."""
    global _detector
    _detector = d
