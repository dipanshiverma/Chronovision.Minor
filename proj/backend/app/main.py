"""ChronoVision API.  Run:  uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from . import config, media, nlq, repo, report, worker
from .db import connect, init_db
from .schemas import AnalysisConfig, EntityOut, EventOut, VideoOut


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    worker.start()
    yield


app = FastAPI(title="ChronoVision API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origin_regex=config.CORS_ORIGIN_REGEX, allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "model": config.MODEL_NAME, "llmSearch": bool(config.ANTHROPIC_API_KEY)}


# ------------------------------------------------------------------ videos
def _parse_config(raw: str) -> AnalysisConfig:
    try:
        return AnalysisConfig.model_validate(json.loads(raw or "{}"))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(422, f"Invalid analysis config: {exc}") from exc


@app.post("/api/videos", response_model=VideoOut, response_model_by_alias=True, status_code=201)
async def upload_video(file: UploadFile = File(...), config_json: str = Form("{}", alias="config")):
    """Upload a video. Analysis starts automatically; `config` is optional (advanced restricted-area / line rules)."""
    cfg = _parse_config(config_json)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Use: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}")

    video_id = f"v-{uuid.uuid4().hex[:8]}"
    stored = f"{video_id}{ext}"
    dest = config.UPLOAD_DIR / stored
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                out.close(); dest.unlink(missing_ok=True)
                raise HTTPException(413, f"File exceeds {config.MAX_UPLOAD_MB} MB limit")
            out.write(chunk)

    info = media.probe(dest)  # validates the file and reads duration / resolution / frame rate
    if info is None:
        dest.unlink(missing_ok=True)
        raise HTTPException(422, "Could not read this file as a video.")
    thumb_name = f"{video_id}.jpg"
    has_thumb = media.make_thumbnail(dest, config.THUMB_DIR / thumb_name)

    with connect() as c:
        c.execute(
            "INSERT INTO videos(id,filename,stored_name,thumb_path,uploaded_at,duration_sec,fps,width,height,status,stage,"
            "progress,config_json,created_ts) VALUES(?,?,?,?,?,?,?,?,?,'Queued','Video uploaded',0,?,?)",
            (video_id, file.filename, stored, thumb_name if has_thumb else None, date.today().isoformat(),
             info["duration"], info["fps"], info["width"], info["height"], cfg.model_dump_json(by_alias=True), time.time()))
    worker.enqueue(video_id)
    return repo.get_video(video_id)


@app.get("/api/videos", response_model=list[VideoOut], response_model_by_alias=True)
def list_videos():
    return repo.list_videos()


@app.get("/api/videos/{video_id}", response_model=VideoOut, response_model_by_alias=True)
def get_video(video_id: str):
    v = repo.get_video(video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


@app.get("/api/videos/{video_id}/analysis")
def video_analysis(video_id: str):
    """Everything about one analysed video: stats, 10-second segments, events and tracked entities."""
    a = repo.analysis(video_id)
    if not a:
        raise HTTPException(404, "Video not found")
    return {k: ([x.model_dump(by_alias=True) for x in v] if isinstance(v, list) else v.model_dump(by_alias=True))
            for k, v in a.items()}


@app.get("/api/videos/{video_id}/tracks")
def video_tracks(video_id: str):
    """Per-entity tracked boxes [t,x1,y1,x2,y2,conf] (normalised) for the synchronised detection overlay."""
    if not repo.get_video_row(video_id):
        raise HTTPException(404, "Video not found")
    return repo.tracks(video_id)


@app.get("/api/videos/{video_id}/report.pdf")
def video_report(video_id: str):
    pdf = report.build_report(video_id)
    if pdf is None:
        raise HTTPException(404, "Video not found")
    row = repo.get_video_row(video_id)
    name = Path(row["filename"]).stem
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="chronovision-report-{name}.pdf"'})


@app.post("/api/videos/{video_id}/analyse", response_model=VideoOut, response_model_by_alias=True)
def reanalyse(video_id: str, cfg: Optional[AnalysisConfig] = None):
    """Re-run analysis. Replaces the previous results, so nothing is double counted."""
    if not repo.get_video_row(video_id):
        raise HTTPException(404, "Video not found")
    if cfg is not None:
        with connect() as c:
            c.execute("UPDATE videos SET config_json=? WHERE id=?", (cfg.model_dump_json(by_alias=True), video_id))
    worker.enqueue(video_id)
    return repo.get_video(video_id)


@app.delete("/api/videos/{video_id}", status_code=204)
def delete_video(video_id: str):
    if not repo.delete_video(video_id):
        raise HTTPException(404, "Video not found")


@app.get("/api/videos/{video_id}/file")
def video_file(video_id: str):
    row = repo.get_video_row(video_id)
    path = config.UPLOAD_DIR / row["stored_name"] if row else None
    if not path or not path.exists():
        raise HTTPException(404, "Video not found")
    return FileResponse(path)  # Starlette serves HTTP Range requests, so seeking works in <video>


@app.get("/api/videos/{video_id}/thumbnail")
def video_thumb(video_id: str):
    row = repo.get_video_row(video_id)
    path = config.THUMB_DIR / row["thumb_path"] if row and row["thumb_path"] else None
    if not path or not path.exists():
        raise HTTPException(404, "No thumbnail")
    return FileResponse(path, media_type="image/jpeg")


# ------------------------------------------------------------------ events, segments, entities
@app.get("/api/events", response_model=list[EventOut], response_model_by_alias=True)
def list_events(video_id: Optional[str] = Query(None, alias="videoId"), kind: Optional[str] = None,
                severity: Optional[str] = None, min_severity: Optional[str] = Query(None, alias="minSeverity"),
                limit: Optional[int] = Query(None, ge=1, le=500), order: str = "time"):
    if order not in ("time", "recent", "severity"):
        raise HTTPException(422, "order must be time, recent or severity")
    return repo.query_events(video_id, [kind] if kind else None, [severity] if severity else None, min_severity, order, limit)


def _evidence_file(table: str, col: str, row_id: str, id_col: str = "id") -> Path:
    with connect() as c:
        r = c.execute(f"SELECT video_id, {col} f FROM {table} WHERE {id_col}=?", (row_id,)).fetchone()
    path = config.EVIDENCE_DIR / r["video_id"] / r["f"] if r and r["f"] else None
    if not path or not path.exists():
        raise HTTPException(404, "No evidence image")
    return path


@app.get("/api/events/{event_id}/frame")
def event_frame(event_id: str):
    return FileResponse(_evidence_file("events", "frame_path", event_id), media_type="image/jpeg")


@app.get("/api/segments/{segment_id}/frame")
def segment_frame(segment_id: str):
    return FileResponse(_evidence_file("segments", "frame_path", segment_id), media_type="image/jpeg")


@app.get("/api/entities/{entity_id}/thumb")
def entity_thumb(entity_id: str):
    return FileResponse(_evidence_file("entities", "thumb_path", entity_id), media_type="image/jpeg")


# ------------------------------------------------------------------ overview + search
@app.get("/api/overview")
def overview():
    return repo.overview()


@app.get("/api/search")
def search(q: str = Query("", max_length=300)):
    """Natural-language search. Parses the question into a structured query, then answers from stored analysis only."""
    names = [v.filename for v in repo.list_videos()]
    if not q.strip():
        evs = repo.query_events(min_severity="unusual", order="severity", limit=20)
        return {"query": q, "source": None, "interpretation": [],
                "answer": "Ask a question about your analysed videos." if not evs else f"{len(evs)} notable events (most serious first).",
                "results": [nlq._event_item(e) for e in evs]}
    pq = nlq.parse_query(q, names)
    out = nlq.run_search(pq)
    return {"query": q, "source": pq.source, "interpretation": nlq.interpretation(pq), **out}
