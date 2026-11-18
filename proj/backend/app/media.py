"""Video helpers: probing, thumbnails, browser-friendly transcoding (methodology Step 1)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cv2

from . import config


def probe(path: Path) -> dict | None:
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        ok, _ = cap.read()
        if not ok or w <= 0 or h <= 0:
            return None
        fps = fps if 1 <= fps <= 240 else 25.0
        return {"fps": fps, "width": w, "height": h, "duration": (n / fps) if n > 0 else None}
    finally:
        cap.release()


def make_thumbnail(path: Path, dest: Path, at_sec: float = 1.0, width: int = 480) -> bool:
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(at_sec * fps))
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok:
            return False
        h, w = frame.shape[:2]
        frame = cv2.resize(frame, (width, max(1, int(h * width / w))), interpolation=cv2.INTER_AREA)
        return bool(cv2.imwrite(str(dest), frame, [cv2.IMWRITE_JPEG_QUALITY, 85]))
    finally:
        cap.release()


BROWSER_CODECS = {"h264", "vp8", "vp9", "av1"}


def _video_codec(path: Path) -> str | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=30)
        return r.stdout.strip().lower() or None
    except Exception:
        return None


def ensure_browser_playable(path: Path) -> Path:
    """Transcode to H.264 MP4 when the container or codec would not play in a browser (MOV/AVI/MKV, HEVC, MPEG-4 part 2...).
    Needs ffmpeg on PATH; without it the original file is kept. Returns the (possibly new) path."""
    if not shutil.which("ffmpeg"):
        return path
    codec = _video_codec(path)
    if path.suffix.lower() in config.BROWSER_NATIVE and (codec is None or codec in BROWSER_CODECS):
        return path
    out = path.with_name(path.stem + "_web.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(out)]
    try:
        subprocess.run(cmd, check=True, timeout=3600)
    except Exception:
        out.unlink(missing_ok=True)
        return path
    path.unlink(missing_ok=True)
    return out
