"""End-to-end analysis of one video.

  frames (OpenCV) -> YOLO detection + ByteTrack -> unique entities -> behaviour reasoning -> 10 s segments
  -> evidence frames -> SQLite

Stages are reported to the UI as they really happen (the detection loop reports frame-accurate progress)."""
from __future__ import annotations

import json
import math
import shutil
import time
import uuid
from bisect import bisect_left

import cv2

from . import config, media
from .behavior import EventRec, Scene, analyse
from .camera import CameraMotion
from .db import connect
from .describe import build_segments
from .detector import get_detector
from .entities import Entity, TrackBook, build_entities
from .events import EventEngine, RuleConfig
from .evidence import render_crop, render_evidence, render_scene
from .repo import fmt_clock, get_video_row
from .schemas import AnalysisConfig

STAGES = ["Video uploaded", "Extracting frames", "Detecting objects", "Tracking entities", "Analysing activities",
          "Generating event timeline", "Analysis completed"]


class VideoGone(Exception):
    """The video was deleted while it was being analysed."""


def _set(video_id: str, **cols) -> None:
    sets = ", ".join(f"{k}=?" for k in cols)
    with connect() as c:
        c.execute(f"UPDATE videos SET {sets} WHERE id=?", (*cols.values(), video_id))


def process_video(video_id: str) -> int:
    """Analyse a stored video. Returns the number of events found. Never raises: failures are stored on the row."""
    row = get_video_row(video_id)
    if row is None:
        return 0
    try:
        return _process(video_id, row)
    except VideoGone:
        return 0
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        if get_video_row(video_id):
            _set(video_id, status="Failed", stage="Analysis failed", error=f"{type(exc).__name__}: {exc}"[:500])
        return 0


def _rules(cfg: AnalysisConfig) -> RuleConfig | None:
    if not (cfg.restricted_zone or cfg.line or cfg.presence_zone):
        return None
    return RuleConfig(
        restricted_zone=[tuple(p) for p in cfg.restricted_zone] if cfg.restricted_zone else None,
        line=(tuple(cfg.line[0]), tuple(cfg.line[1])) if cfg.line else None,
        presence_zone=[tuple(p) for p in cfg.presence_zone] if cfg.presence_zone else None,
        dwell_seconds=cfg.dwell_seconds)


def _process(video_id: str, row) -> int:
    _set(video_id, status="Processing", stage="Extracting frames", progress=0.02, error=None)

    path = config.UPLOAD_DIR / row["stored_name"]
    playable = media.ensure_browser_playable(path)  # MOV/AVI/MKV/HEVC -> H.264 MP4 so the player works
    if playable != path:
        _set(video_id, stored_name=playable.name)
        path = playable

    cfg = AnalysisConfig.model_validate(json.loads(row["config_json"]))
    rules = _rules(cfg)
    engine = EventEngine(rules, renderer=render_evidence) if rules else None
    legacy: list = []

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError("could not open video")
    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = fps if 1 <= fps <= 240 else 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    stride = max(1, round(fps / config.PROCESS_FPS))

    detector = get_detector()
    detector.start_video()
    book, cam = TrackBook(), CameraMotion()
    _set(video_id, stage="Detecting objects", progress=0.05)

    idx, last_report, W, H, last_t = 0, time.monotonic(), 0, 0, 0.0
    while True:
        if not cap.grab():
            break
        if idx % stride == 0:
            ok, frame = cap.retrieve()
            if ok:
                H, W = frame.shape[:2]
                t = idx / fps
                last_t = t
                shift = cam.update(frame)
                tracks = detector.track(frame)
                book.add(t, tracks, W, H, shift)
                if engine:
                    legacy += engine.update(t, W, H, [x for x in tracks if x.group == "person"], frame)
                if time.monotonic() - last_report > 0.8:
                    last_report = time.monotonic()
                    if get_video_row(video_id) is None:
                        raise VideoGone()
                    if total:
                        _set(video_id, progress=round(0.05 + 0.70 * min(1.0, idx / total), 3))
        idx += 1
    cap.release()
    if engine:
        legacy += engine.finish()
    if not W:
        raise RuntimeError("no frames could be decoded")
    duration = max(row["duration_sec"] or 0.0, last_t)

    _set(video_id, stage="Tracking entities", progress=0.78)
    entities = build_entities(book, W, H)

    _set(video_id, stage="Analysing activities", progress=0.84)
    scene = Scene(entities, W, H, duration)
    events: list[EventRec] = analyse(entities, W, H, duration, scene)
    legacy_recs = _legacy_events(legacy, entities)
    events = sorted(events + [r for r, _ in legacy_recs], key=lambda e: (e.start, -e.confidence))

    _set(video_id, stage="Generating event timeline", progress=0.90)
    segments = build_segments(scene, events, duration, config.SEGMENT_SECONDS)

    new_dir = config.EVIDENCE_DIR / f"{video_id}__new"
    shutil.rmtree(new_dir, ignore_errors=True)
    new_dir.mkdir(parents=True, exist_ok=True)
    ids = {"seg": [f"s-{uuid.uuid4().hex[:8]}" for _ in segments], "evt": [f"e-{uuid.uuid4().hex[:8]}" for _ in events]}
    files = _evidence(path, fps, entities, events, segments, ids, legacy_recs, new_dir)

    # ---- persist atomically: re-analysis replaces everything, so nothing can be double counted ----------------------
    if get_video_row(video_id) is None:
        shutil.rmtree(new_dir, ignore_errors=True)
        raise VideoGone()
    ev_seg = {}
    for s in segments:
        for j in s.event_idx:
            ev_seg.setdefault(j, s.idx)
    with connect() as c:
        for tbl in ("entities", "segments", "events"):
            c.execute(f"DELETE FROM {tbl} WHERE video_id=?", (video_id,))
        for e in entities:
            traj, dist = _trajectory(e, W, H)
            c.execute(
                "INSERT INTO entities(id,video_id,grp,label,seq,track_ids_json,first_sec,last_sec,duration_sec,confidence,"
                "obs_count,thumb_path,trajectory_json,distance,obs_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (e.id, video_id, e.group, e.label, e.seq, json.dumps(e.track_ids), e.first, e.last, e.duration, e.conf,
                 len(e.obs), files["ent"].get(e.id), json.dumps(traj), dist,
                 json.dumps([[round(o[0], 2), round(o[1], 4), round(o[2], 4), round(o[3], 4), round(o[4], 4), round(o[5], 2)]
                             for o in e.obs])))
        for j, ev in enumerate(events):
            c.execute(
                "INSERT INTO events(id,video_id,kind,severity,title,description,start_sec,end_sec,confidence,frame_path,"
                "entity_ids_json,segment_idx,details_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ids["evt"][j], video_id, ev.kind, ev.severity, ev.title, ev.description, ev.start, ev.end, ev.confidence,
                 files["evt"].get(j), json.dumps(ev.entities), ev_seg.get(j), json.dumps(ev.details)))
        for i, s in enumerate(segments):
            c.execute(
                "INSERT INTO segments(id,video_id,idx,start_sec,end_sec,summary,people,animals,objects,objects_json,"
                "entity_ids_json,event_ids_json,interactions_json,classification,confidence,frame_path) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ids["seg"][i], video_id, s.idx, s.start, s.end, s.summary, s.people, s.animals, s.objects,
                 json.dumps(s.objects_breakdown), json.dumps(s.entity_ids), json.dumps([ids["evt"][j] for j in s.event_idx]),
                 json.dumps(s.interactions), s.classification, s.confidence, files["seg"].get(i)))
        c.execute("UPDATE videos SET status='Completed', stage='Analysis completed', progress=1, error=NULL, "
                  "duration_sec=?, width=?, height=? WHERE id=?", (duration, W, H, video_id))
    old = config.EVIDENCE_DIR / video_id
    shutil.rmtree(old, ignore_errors=True)
    new_dir.rename(old)
    return len(events)


# ------------------------------------------------------------------------------------------------ helpers
def _trajectory(e: Entity, W: int, H: int) -> tuple[list[list[float]], float]:
    """[[t, x, y], ...] ~20 samples of the box centre-bottom in image space; distance = world path / frame diagonal."""
    step = max(1, len(e.obs) // 20)
    traj = [[round(o[0], 2), round((o[1] + o[3]) / 2, 3), round(o[4], 3)] for o in e.obs[::step]]
    d = 0.0
    for a, b in zip(e.obs, e.obs[1:]):
        ax, ay = ((a[1] + a[3]) / 2 - a[6]) * W, (a[4] - a[7]) * H
        bx, by = ((b[1] + b[3]) / 2 - b[6]) * W, (b[4] - b[7]) * H
        d += math.hypot(bx - ax, by - ay)
    return traj, round(d / math.hypot(W, H), 3)


def _legacy_events(raw, entities: list[Entity]) -> list[tuple[EventRec, object]]:
    """Optional geometry rules (only when a zone/line was supplied) -> same event model."""
    by_tid = {tid: e for e in entities for tid in e.track_ids}
    out, crossings = [], {}
    for r in raw:
        ent = by_tid.get(r.track_id)
        if not ent:
            continue
        name = ent.name
        if r.category == "restricted":
            rec = EventRec("restricted_entry", "suspicious", f"{name} enters a restricted area",
                           f"{name} enters the restricted area marked for this video.", r.start, r.end, round(r.confidence, 2),
                           [ent.id], r.start, {})
        elif r.category == "line":
            crossings[ent.id] = crossings.get(ent.id, 0) + 1
            rec = EventRec("line_crossing", "unusual", f"{name} crosses the boundary line",
                           f"{name} crosses the marked boundary line.", r.start, None, round(r.confidence, 2), [ent.id], r.start,
                           {"direction": r.details.get("direction")})
        else:
            rec = EventRec("prolonged_presence", "unusual", f"{name} stays in the marked area",
                           f"{name} stays in the marked area for an extended period.", r.start, r.end, round(r.confidence, 2),
                           [ent.id], r.start, {})
        out.append((rec, r.evidence))
    for rec, _ in out:  # repeated boundary crossing by the same entity escalates
        if rec.kind == "line_crossing" and crossings.get(rec.entities[0], 0) >= 3:
            rec.severity = "suspicious"
            rec.description += " It crosses the line repeatedly."
    return out


def _boxes_at(entities: list[Entity], t: float, tol: float = 0.2):
    out = []
    for e in entities:
        times = [o[0] for o in e.obs]
        i = bisect_left(times, t)
        c = [j for j in (i - 1, i) if 0 <= j < len(times)]
        if not c:
            continue
        j = min(c, key=lambda j: abs(times[j] - t))
        if abs(times[j] - t) <= tol:
            o = e.obs[j]
            out.append((e.id, e.group, e.name, e.label, o[5], (o[1], o[2], o[3], o[4])))
    return out


def _evidence(path, fps, entities, events, segments, ids, legacy_recs, out_dir) -> dict:
    """One sequential pass over the video grabs every evidence frame (segments, events, entity thumbnails)."""
    files: dict = {"seg": {}, "evt": {}, "ent": {}}
    targets = []  # (time, kind, key, highlight)
    for i, s in enumerate(segments):
        targets.append((s.frame_t, "seg", i, set(s.highlight)))
    legacy_img = {id(r): img for r, img in legacy_recs}
    for j, ev in enumerate(events):
        img = legacy_img.get(id(ev))
        if img is not None:  # geometry rule: the engine already rendered its own annotated frame
            name = f"evt-{ids['evt'][j]}.jpg"
            cv2.imwrite(str(out_dir / name), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
            files["evt"][j] = name
        else:
            targets.append((ev.frame_t, "evt", j, set(ev.entities)))
    for e in entities:
        best = max(e.obs, key=lambda o: o[5] * max(1e-6, (o[3] - o[1]) * (o[4] - o[2])))
        targets.append((best[0], "ent", e, {e.id}))
    targets.sort(key=lambda x: x[0])

    cap = cv2.VideoCapture(str(path))
    k, frame, idx = 0, None, 0
    half = 0.5 / fps
    while k < len(targets):
        ok, f = cap.read()
        if not ok:
            break
        frame, t_idx = f, idx / fps
        idx += 1
        while k < len(targets) and t_idx + half >= targets[k][0]:
            _write(frame, targets[k], t_idx, entities, ids, files, out_dir)
            k += 1
    while k < len(targets) and frame is not None:  # targets past the last decodable frame
        _write(frame, targets[k], targets[k][0], entities, ids, files, out_dir)
        k += 1
    cap.release()
    return files


def _write(frame, target, t, entities, ids, files, out_dir) -> None:
    ft, kind, key, hot = target
    if kind == "ent":
        o = max(key.obs, key=lambda o: o[5] * max(1e-6, (o[3] - o[1]) * (o[4] - o[2])))
        name = f"ent-{key.id}.jpg"
        cv2.imwrite(str(out_dir / name), render_crop(frame, o[1:5]), [cv2.IMWRITE_JPEG_QUALITY, 88])
        files["ent"][key.id] = name
        return
    img = render_scene(frame, _boxes_at(entities, ft), hot, stamp=fmt_clock(ft))
    name = f"{kind}-{ids[kind][key]}.jpg"
    cv2.imwrite(str(out_dir / name), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    files[kind][key] = name
