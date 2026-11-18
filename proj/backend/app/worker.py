"""Single background worker: analyses queued videos one at a time (avoids CPU/GPU contention)."""
from __future__ import annotations

import queue
import threading

from .db import connect
from .pipeline import process_video

_q: "queue.Queue[str]" = queue.Queue()
_thread: threading.Thread | None = None


def enqueue(video_id: str) -> None:
    with connect() as c:
        c.execute("UPDATE videos SET status='Queued', progress=0, error=NULL WHERE id=?", (video_id,))
    _q.put(video_id)


def _loop() -> None:
    while True:
        vid = _q.get()
        try:
            process_video(vid)
        finally:
            _q.task_done()


def start() -> None:
    """Start the worker thread and resume anything interrupted by a restart."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_loop, name="analysis-worker", daemon=True)
    _thread.start()
    with connect() as c:
        pending = [r["id"] for r in c.execute(
            "SELECT id FROM videos WHERE status IN ('Queued','Processing') ORDER BY created_ts")]
    for vid in pending:
        enqueue(vid)
