"""Data-access helpers and row -> API model conversion."""
from __future__ import annotations

import json
import shutil
import sqlite3
from typing import Optional

from . import config, taxonomy
from .db import connect
from .schemas import EntityOut, EventOut, SegmentOut, VideoOut, VideoStats


def fmt_hms(sec: float) -> str:
    s = max(0, round(sec))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def fmt_clock(sec: float) -> str:
    """mm:ss (hh:mm:ss past an hour)."""
    s = max(0, int(sec))
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def ent_name(grp: str, seq: int) -> str:
    return f"{grp.capitalize()} {seq}"


# ------------------------------------------------------------------------------------------------- videos
def _stats(c: sqlite3.Connection, video_id: str) -> VideoStats:
    g = {r["grp"]: r["n"] for r in c.execute("SELECT grp, COUNT(*) n FROM entities WHERE video_id=? GROUP BY grp", (video_id,))}
    br = {r["label"]: r["n"] for r in c.execute(
        "SELECT label, COUNT(*) n FROM entities WHERE video_id=? AND grp='object' GROUP BY label ORDER BY n DESC", (video_id,))}
    ev = c.execute("SELECT COUNT(*) n, SUM(severity IN ('suspicious','high')) bad FROM events WHERE video_id=?",
                   (video_id,)).fetchone()
    return VideoStats(people=g.get("person", 0), animals=g.get("animal", 0), objects=g.get("object", 0),
                      events=ev["n"] or 0, incidents=ev["bad"] or 0, object_breakdown=br)


def video_out(c: sqlite3.Connection, r: sqlite3.Row) -> VideoOut:
    done = r["status"] == "Completed"
    return VideoOut(
        id=r["id"], filename=r["filename"], uploaded_at=r["uploaded_at"],
        duration=fmt_hms(r["duration_sec"]) if r["duration_sec"] is not None else None, duration_sec=r["duration_sec"],
        width=r["width"], height=r["height"], fps=r["fps"], status=r["status"], stage=r["stage"],
        progress=round(r["progress"], 3), error=r["error"],
        thumbnail=f"/api/videos/{r['id']}/thumbnail" if r["thumb_path"] else None,
        src=f"/api/videos/{r['id']}/file", stats=_stats(c, r["id"]) if done else None)


def get_video_row(video_id: str) -> Optional[sqlite3.Row]:
    with connect() as c:
        return c.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()


def list_videos() -> list[VideoOut]:
    with connect() as c:
        return [video_out(c, r) for r in c.execute("SELECT * FROM videos ORDER BY created_ts DESC")]


def get_video(video_id: str) -> Optional[VideoOut]:
    with connect() as c:
        r = c.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        return video_out(c, r) if r else None


def delete_video(video_id: str) -> bool:
    row = get_video_row(video_id)
    if not row:
        return False
    with connect() as c:
        c.execute("DELETE FROM videos WHERE id=?", (video_id,))
    (config.UPLOAD_DIR / row["stored_name"]).unlink(missing_ok=True)
    if row["thumb_path"]:
        (config.THUMB_DIR / row["thumb_path"]).unlink(missing_ok=True)
    shutil.rmtree(config.EVIDENCE_DIR / video_id, ignore_errors=True)
    return True


# ------------------------------------------------------------------------------------------------- entities
def _entity_refs(c: sqlite3.Connection, video_id: Optional[str] = None) -> dict[str, dict]:
    q, a = "SELECT id, grp, label, seq FROM entities", ()
    if video_id:
        q, a = q + " WHERE video_id=?", (video_id,)
    return {r["id"]: {"id": r["id"], "name": ent_name(r["grp"], r["seq"]), "label": r["label"], "group": r["grp"]}
            for r in c.execute(q, a)}


def intervals(obs: list[list[float]], gap: float = 1.0) -> list[list[float]]:
    out: list[list[float]] = []
    for o in obs:
        if out and o[0] - out[-1][1] <= gap:
            out[-1][1] = o[0]
        else:
            out.append([o[0], o[0]])
    return [[round(a, 2), round(b, 2)] for a, b in out]


def entity_out(r: sqlite3.Row) -> EntityOut:
    obs = json.loads(r["obs_json"])
    return EntityOut(
        id=r["id"], video_id=r["video_id"], group=r["grp"], label=r["label"], name=ent_name(r["grp"], r["seq"]),
        track_ids=json.loads(r["track_ids_json"]), first_sec=round(r["first_sec"], 2), last_sec=round(r["last_sec"], 2),
        duration_sec=round(r["duration_sec"], 2), confidence=round(r["confidence"], 2) if r["confidence"] is not None else None,
        thumbnail=f"/api/entities/{r['id']}/thumb" if r["thumb_path"] else None,
        trajectory=json.loads(r["trajectory_json"]), distance=r["distance"], appearances=intervals(obs))


def list_entities(video_id: str) -> list[EntityOut]:
    with connect() as c:
        return [entity_out(r) for r in c.execute("SELECT * FROM entities WHERE video_id=? ORDER BY grp, seq", (video_id,))]


def tracks(video_id: str) -> list[dict]:
    """Compact per-entity boxes for the synchronised overlay."""
    with connect() as c:
        return [{"id": r["id"], "group": r["grp"], "label": r["label"], "name": ent_name(r["grp"], r["seq"]),
                 "obs": json.loads(r["obs_json"])}
                for r in c.execute("SELECT * FROM entities WHERE video_id=? ORDER BY grp, seq", (video_id,))]


# --------------------------------------------------------------------------------------------------- events
def _event_out(r: sqlite3.Row, refs: dict[str, dict], filename: Optional[str] = None) -> EventOut:
    ids = json.loads(r["entity_ids_json"])
    return EventOut(
        id=r["id"], video_id=r["video_id"], filename=filename, kind=r["kind"], severity=r["severity"],
        severity_label=taxonomy.SEVERITY_LABEL[r["severity"]], title=r["title"], description=r["description"],
        start_sec=round(r["start_sec"], 2), end_sec=round(r["end_sec"], 2) if r["end_sec"] is not None else None,
        confidence=r["confidence"], frame=f"/api/events/{r['id']}/frame" if r["frame_path"] else None,
        entities=[refs[i] for i in ids if i in refs], segment_index=r["segment_idx"])


def query_events(video_id: Optional[str] = None, kinds: Optional[list[str]] = None, severities: Optional[list[str]] = None,
                 min_severity: Optional[str] = None, order: str = "time", limit: Optional[int] = None) -> list[EventOut]:
    sql = ("SELECT e.*, v.filename fn FROM events e JOIN videos v ON v.id=e.video_id "
           "WHERE v.status='Completed'")
    args: list = []
    if video_id:
        sql += " AND e.video_id=?"; args.append(video_id)
    if kinds:
        sql += f" AND e.kind IN ({','.join('?' * len(kinds))})"; args += kinds
    if severities:
        sql += f" AND e.severity IN ({','.join('?' * len(severities))})"; args += severities
    if min_severity:
        ok = [s for s, o in taxonomy.SEVERITY_ORDER.items() if o >= taxonomy.SEVERITY_ORDER[min_severity]]
        sql += f" AND e.severity IN ({','.join('?' * len(ok))})"; args += ok
    sql += {"time": " ORDER BY v.created_ts DESC, e.start_sec ASC", "recent": " ORDER BY v.created_ts DESC, e.start_sec DESC",
            "severity": " ORDER BY CASE e.severity WHEN 'high' THEN 0 WHEN 'suspicious' THEN 1 WHEN 'unusual' THEN 2 ELSE 3 END,"
                        " v.created_ts DESC, e.start_sec"}[order]
    if limit:
        sql += " LIMIT ?"; args.append(limit)
    with connect() as c:
        refs = _entity_refs(c)
        return [_event_out(r, refs, r["fn"]) for r in c.execute(sql, args)]


# ------------------------------------------------------------------------------------------ full analysis
def analysis(video_id: str) -> Optional[dict]:
    with connect() as c:
        vr = c.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
        if not vr:
            return None
        refs = _entity_refs(c, video_id)
        ev_rows = c.execute("SELECT * FROM events WHERE video_id=? ORDER BY start_sec", (video_id,)).fetchall()
        events = {r["id"]: _event_out(r, refs, vr["filename"]) for r in ev_rows}
        segs = []
        for r in c.execute("SELECT * FROM segments WHERE video_id=? ORDER BY idx", (video_id,)):
            ids = json.loads(r["entity_ids_json"])
            segs.append(SegmentOut(
                id=r["id"], video_id=video_id, index=r["idx"], start_sec=round(r["start_sec"], 2), end_sec=round(r["end_sec"], 2),
                summary=r["summary"], people=r["people"], animals=r["animals"], objects=r["objects"],
                objects_breakdown=json.loads(r["objects_json"]), entities=[refs[i] for i in ids if i in refs],
                interactions=json.loads(r["interactions_json"]), classification=r["classification"],
                classification_label=taxonomy.SEVERITY_LABEL[r["classification"]], confidence=r["confidence"],
                frame=f"/api/segments/{r['id']}/frame" if r["frame_path"] else None,
                events=[events[i] for i in json.loads(r["event_ids_json"]) if i in events]))
        ents = [entity_out(r) for r in c.execute("SELECT * FROM entities WHERE video_id=? ORDER BY grp, seq", (video_id,))]
        return {"video": video_out(c, vr), "segments": segs, "events": list(events.values()), "entities": ents}


# ----------------------------------------------------------------------------------------------- overview
def overview() -> dict:
    with connect() as c:
        videos = c.execute("SELECT COUNT(*) n, SUM(status='Completed') done FROM videos").fetchone()
        g = {r["grp"]: r["n"] for r in c.execute(
            "SELECT e.grp, COUNT(*) n FROM entities e JOIN videos v ON v.id=e.video_id WHERE v.status='Completed' GROUP BY e.grp")}
        sev = {r["severity"]: r["n"] for r in c.execute(
            "SELECT e.severity, COUNT(*) n FROM events e JOIN videos v ON v.id=e.video_id WHERE v.status='Completed' GROUP BY e.severity")}
        seg = {r["classification"]: r["n"] for r in c.execute(
            "SELECT s.classification, COUNT(*) n FROM segments s JOIN videos v ON v.id=s.video_id WHERE v.status='Completed' "
            "GROUP BY s.classification")}
    return {
        "videos": videos["n"] or 0, "analysed": videos["done"] or 0,
        "people": g.get("person", 0), "animals": g.get("animal", 0), "objects": g.get("object", 0),
        "events": sum(sev.values()), "incidents": sev.get("suspicious", 0) + sev.get("high", 0),
        # Distribution is over 10-second segments (time spent), alongside the number of events of each class.
        "distribution": [{"severity": s, "label": taxonomy.SEVERITY_LABEL[s], "segments": seg.get(s, 0), "events": sev.get(s, 0)}
                         for s in ("normal", "unusual", "suspicious", "high")],
    }
