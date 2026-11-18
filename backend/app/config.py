"""Runtime configuration. Everything is overridable with CHRONOVISION_* env vars."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("CHRONOVISION_DATA", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
EVIDENCE_DIR = DATA_DIR / "evidence"
THUMB_DIR = DATA_DIR / "thumbs"
DB_PATH = DATA_DIR / "chronovision.db"
TRACKER_YAML = Path(__file__).resolve().parent / "bytetrack.yaml"

# --- Detection / tracking -------------------------------------------------
MODEL_NAME = os.getenv("CHRONOVISION_MODEL", "yolo11n.pt")  # yolo11n = fastest on CPU; yolo11s.pt is noticeably better on small objects
DETECT_CONF = float(os.getenv("CHRONOVISION_CONF", "0.25"))  # floor; per-group minimums are in taxonomy.MIN_CONF
IMGSZ = int(os.getenv("CHRONOVISION_IMGSZ", "640"))  # 960 sees small objects (handbags, phones) better but is ~2x slower
DEVICE = os.getenv("CHRONOVISION_DEVICE") or None  # None = auto (cuda if available), or "cpu", "0", "mps"
# Frames are analysed at ~this rate (skipped frames are only grabbed, not decoded) - the main CPU speed knob.
PROCESS_FPS = float(os.getenv("CHRONOVISION_PROCESS_FPS", "10"))
# COCO class ids to detect. Default: every class in taxonomy.COCO (people, animals, vehicles, bags, common objects).
_cls = os.getenv("CHRONOVISION_CLASSES", "").strip()
CLASSES = [int(c) for c in _cls.split(",") if c.strip()] if _cls else None  # None -> taxonomy.COCO keys
SEGMENT_SECONDS = 10.0

# --- API ------------------------------------------------------------------
MAX_UPLOAD_MB = int(os.getenv("CHRONOVISION_MAX_UPLOAD_MB", "2048"))
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"}
# Formats browsers play natively; anything else is transcoded to H.264 MP4 (needs ffmpeg on PATH).
BROWSER_NATIVE = {".mp4", ".webm", ".m4v"}
CORS_ORIGIN_REGEX = os.getenv("CHRONOVISION_CORS_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?")

# --- Natural-language search (optional LLM parsing) -------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
LLM_MODEL = os.getenv("CHRONOVISION_LLM_MODEL", "claude-haiku-5-5")


def ensure_dirs() -> None:
    for d in (DATA_DIR, UPLOAD_DIR, EVIDENCE_DIR, THUMB_DIR):
        d.mkdir(parents=True, exist_ok=True)
