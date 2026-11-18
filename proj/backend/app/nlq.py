"""Natural-language search over the stored analysis.

A question is parsed into a *structured query* (intent, entity types, event kinds, time window, ...) and then run as
SQL over stored entities / events / segments. The parser only decides WHAT to look up. Every answer and every result
comes from stored analysis rows, so nothing is generated or guessed - and when the data does not support a claim, the
answer says so instead of inventing one.

Two parsers share one output schema: rule-based (default, offline) and optional LLM-assisted (ANTHROPIC_API_KEY),
which falls back to the rules on any failure."""
from __future__ import annotations

import json
import re
from typing import Literal, Optional

import httpx
from pydantic import BaseModel, Field

from . import config, taxonomy
from .db import connect
from .repo import ent_name, fmt_clock, intervals, query_events, list_videos

KINDS = ["transfer", "handover", "pickup", "carry", "approach", "approach_flee", "following", "running", "loitering",
         "unattended", "abandoned", "vehicle_proximity", "restricted_entry", "line_crossing", "prolonged_presence"]

LABEL_TERMS: list[tuple[str, list[str]]] = [  # regex -> COCO labels
    (r"\b(dogs?|puppy|puppies)\b", ["dog"]), (r"\bcats?\b", ["cat"]), (r"\bbirds?\b", ["bird"]), (r"\bcows?\b", ["cow"]),
    (r"\bhorses?\b", ["horse"]), (r"\bsheep\b", ["sheep"]),
    (r"\bvehicles?\b", ["bicycle", "car", "motorcycle", "bus", "truck"]), (r"\bcars?\b", ["car"]),
    (r"\btrucks?\b", ["truck"]), (r"\bbus(es)?\b", ["bus"]), (r"\b(motorcycles?|motorbikes?)\b", ["motorcycle"]),
    (r"\b(bicycles?|bikes?)\b", ["bicycle"]),
    (r"\b(handbags?|purses?)\b", ["handbag"]), (r"\b(backpacks?|rucksacks?)\b", ["backpack"]),
    (r"\b(suitcases?|luggage)\b", ["suitcase"]), (r"\bbags?\b", ["handbag", "backpack", "suitcase"]),
    (r"\b(phones?|mobiles?|smartphones?)\b", ["cell phone"]), (r"\blaptops?\b", ["laptop"]), (r"\bbottles?\b", ["bottle"]),
    (r"\bchairs?\b", ["chair"]), (r"\btables?\b", ["dining table"]), (r"\bumbrellas?\b", ["umbrella"]),
]
PERSON_RE = r"\b(people|persons?|men|man|women|woman|someone|somebody|anyone|anybody|pedestrians?|individuals?|humans?)\b"
EVENT_TERMS: list[tuple[str, list[str]]] = [
    (r"\b(steal|steals|stole|stolen|stealing|theft|thief|thieves|snatch\w*|rob\w*|grab\w*|took|taken|take|takes)\b", ["transfer"]),
    (r"\b(hand(ed)? over|handover|hand-over|exchang\w*|pass(ed)? )\b", ["handover"]),
    (r"\b(picked up|pick up|picks up|pickup|pick-up|pick)\b", ["pickup"]),
    (r"\b(unattended|abandon\w*|left behind|left alone|leave\w* (an |a |the )?(object|bag|item|luggage|backpack)\w*)\b",
     ["unattended", "abandoned"]),
    (r"\b(loiter\w*|linger\w*|prolonged|dwell\w*)\b", ["loitering", "prolonged_presence"]),
    (r"\b(run|runs|ran|running|fled|flee|fleeing|sprint\w*)\b", ["running", "approach_flee"]),
    (r"\b(follow\w*)\b", ["following"]),
    (r"\b(carry|carried|carrying|carries|holding|held|holds)\b", ["carry"]),
    (r"\b(approach\w*)\b", ["approach"]),
    (r"\b(restricted|forbidden|prohibited|unauthori[sz]ed|trespass\w*|intru\w*)\b", ["restricted_entry"]),
    (r"\b(cross\w* (the )?line|boundary|tripwire)\b", ["line_crossing"]),
    (r"\b(around|near|beside) (a |the )?(car|vehicle|truck|motorcycle)", ["vehicle_proximity"]),
]


class ParsedQuery(BaseModel):
    intent: Literal["list", "count", "exists", "longest", "segments"] = "list"
    groups: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    min_severity: Optional[str] = None
    time_from: Optional[float] = None
    time_to: Optional[float] = None
    video_hint: Optional[str] = None
    keywords: list[str] = Field(default_factory=list)
    note: Optional[str] = None
    source: Literal["rules", "llm"] = "rules"


# ------------------------------------------------------------------------------------------- rule-based parser
_TIME = r"(?:\d{1,2}:\d{2}(?::\d{2})?|\d+(?:\.\d+)?\s*(?:seconds?|secs?|s|minutes?|mins?|m)\b)"


def _to_seconds(s: str) -> float:
    s = s.strip().lower()
    if ":" in s:
        parts = [int(p) for p in s.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    m = re.match(r"(\d+(?:\.\d+)?)\s*([a-z]+)", s)
    return float(m.group(1)) * (60 if m.group(2).startswith("m") else 1)


def parse_rules(q: str, video_names: list[str] | None = None) -> ParsedQuery:
    text = " " + q.lower().strip().rstrip("?.!") + " "
    pq = ParsedQuery(source="rules")

    def eat(pattern: str):
        nonlocal text
        m = re.search(pattern, text)
        if m:
            text = text[: m.start()] + " " + text[m.end():]
        return m

    # time window
    if m := eat(rf"between\s+({_TIME})\s+(?:and|to)\s+({_TIME})"):
        pq.time_from, pq.time_to = _to_seconds(m.group(1)), _to_seconds(m.group(2))
    elif m := eat(rf"in the first\s+({_TIME})"):
        pq.time_from, pq.time_to = 0.0, _to_seconds(m.group(1))
    else:
        if m := eat(rf"(?:after|from|since)\s+({_TIME})"):
            pq.time_from = _to_seconds(m.group(1))
        if m := eat(rf"(?:before|until|till)\s+({_TIME})"):
            pq.time_to = _to_seconds(m.group(1))
        if pq.time_from is None and pq.time_to is None and (m := eat(rf"(?:\bat\b|around)?\s*({_TIME})")):
            t = _to_seconds(m.group(1))
            pq.time_from, pq.time_to = max(0.0, t - 2), t + 2

    # intent
    if re.search(r"\bwhat happened\b|\bwhat was happening\b|\bsummar(y|ise|ize)\b|\bdescribe\b", text):
        pq.intent = "segments"
    elif re.search(r"\bhow many\b|\bnumber of\b|\bcount\b", text):
        pq.intent = "count"
    elif re.search(r"\b(longest|most time|the longest)\b", text):
        pq.intent = "longest"
    elif re.search(r"^\s*(were|was|are|is|did|does|do|has|have|can you see)\s+(there\s+)?(any|anyone|anybody|someone|somebody|an?|the)\b", text):
        pq.intent = "exists"

    # event kinds
    for pattern, kinds in EVENT_TERMS:
        if re.search(pattern, text):
            pq.kinds += [k for k in kinds if k not in pq.kinds]
    if re.search(r"\b(suspicious|crime|criminal|incidents?|dangerous|threat\w*|high[- ]priority)\b", text):
        pq.min_severity = "suspicious"
    elif re.search(r"\bunusual|abnormal|strange|odd\b", text):
        pq.min_severity = "unusual"
    if re.search(r"\benter(ed|s|ing)?\b|\bentry\b|\bentrance\b", text):
        if "restricted_entry" not in pq.kinds and re.search(r"\b(building|room|store|shop|gate|door|premises|area|checkpoint|site)\b", text):
            pq.note = ("ChronoVision cannot tell where a building or doorway is without a marked zone, so this counts the "
                       "unique people who appear in the footage.")
            pq.groups.append("person")
            pq.intent = "count" if pq.intent == "list" else pq.intent

    # entity types
    for pattern, labels in LABEL_TERMS:
        if re.search(pattern, text):
            pq.labels += [l for l in labels if l not in pq.labels]
    if re.search(r"\banimals?\b", text) and "animal" not in pq.groups:
        pq.groups.append("animal")
    if re.search(PERSON_RE, text) and "person" not in pq.groups:
        pq.groups.append("person")
    if re.search(r"\bobjects?\b|\bitems?\b|\bbelongings\b", text) and "object" not in pq.groups and not pq.labels:
        pq.groups.append("object")
    # labels imply their group
    for lab in pq.labels:
        grp = next((g for g, l in taxonomy.COCO.values() if l == lab), None)
        if grp and grp not in pq.groups and not pq.kinds:
            pq.groups.append(grp)

    # video mention by filename
    for name in video_names or []:
        stem = re.sub(r"\.[a-z0-9]+$", "", name.lower())
        if len(stem) >= 3 and stem in text:
            pq.video_hint = stem
            text = text.replace(stem, " ")
            break

    if not (pq.kinds or pq.groups or pq.labels or pq.min_severity or pq.intent == "segments"
            or pq.time_from is not None or pq.time_to is not None or pq.video_hint):
        stop = {"when", "did", "does", "do", "show", "find", "me", "the", "a", "an", "of", "in", "on", "to", "is", "was",
                "were", "any", "all", "events", "event", "video", "videos", "who", "what", "where", "which"}
        pq.keywords = [w for w in re.findall(r"[a-z0-9_\-]+", text) if w not in stop and len(w) > 2]
    if pq.intent == "longest" and not pq.groups and not pq.labels:
        pq.groups.append("person")
    return pq


# ---------------------------------------------------------------------------------------- LLM-assisted parser
_SYSTEM = f"""You convert a user's question about analysed surveillance videos into a JSON search filter.
Output ONLY one JSON object (no prose, no code fences) with these optional keys:
  intent: "list" | "count" | "exists" | "longest" | "segments" (segments = "what happened between X and Y")
  groups: array of "person" | "animal" | "object"
  labels: array of COCO labels, e.g. dog, cat, car, truck, handbag, backpack, suitcase, cell phone, bottle, laptop
  kinds: array chosen from {KINDS}   (theft/taking something from someone = "transfer")
  min_severity: "unusual" | "suspicious"   (use "suspicious" for suspicious/crime/incident questions)
  time_from, time_to: seconds from the video start
  video_hint: part of a filename
Never answer the question and never invent events; only describe the filter."""


def parse_llm(q: str, video_names: list[str] | None = None) -> Optional[ParsedQuery]:
    if not config.ANTHROPIC_API_KEY:
        return None
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": config.LLM_MODEL, "max_tokens": 300, "system": _SYSTEM,
                  "messages": [{"role": "user", "content": f"Known videos: {video_names or []}\nQuestion: {q}"}]},
            timeout=8.0)
        resp.raise_for_status()
        text = "".join(b.get("text", "") for b in resp.json().get("content", []))
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        data = {k: v for k, v in json.loads(text).items() if v is not None}
        data["kinds"] = [k for k in data.get("kinds", []) if k in KINDS]
        data["source"] = "llm"
        return ParsedQuery.model_validate(data)
    except Exception:  # noqa: BLE001
        return None


def parse_query(q: str, video_names: list[str] | None = None) -> ParsedQuery:
    return parse_llm(q, video_names) or parse_rules(q, video_names)


# -------------------------------------------------------------------------------------------------- execution
def interpretation(pq: ParsedQuery) -> list[str]:
    chips = []
    if pq.intent != "list":
        chips.append({"count": "count", "exists": "yes / no", "longest": "longest", "segments": "what happened"}[pq.intent])
    chips += [g for g in pq.groups if not pq.labels]
    chips += pq.labels
    chips += [k.replace("_", " ") for k in pq.kinds]
    if pq.min_severity:
        chips.append("suspicious or worse" if pq.min_severity == "suspicious" else "unusual or worse")
    if pq.time_from is not None and pq.time_to is not None:
        chips.append(f"{fmt_clock(pq.time_from)} - {fmt_clock(pq.time_to)}")
    elif pq.time_from is not None:
        chips.append(f"after {fmt_clock(pq.time_from)}")
    elif pq.time_to is not None:
        chips.append(f"before {fmt_clock(pq.time_to)}")
    if pq.video_hint:
        chips.append(f"video {pq.video_hint}")
    chips += pq.keywords
    return chips


def _event_item(e) -> dict:
    return {"type": "event", "kind": e.kind, "videoId": e.video_id, "filename": e.filename, "startSec": e.start_sec, "endSec": e.end_sec,
            "title": e.title, "text": e.description, "thumbnail": e.frame, "confidence": e.confidence,
            "severity": e.severity, "severityLabel": e.severity_label,
            "entities": [{"name": x["name"], "label": x["label"]} for x in e.entities]}


def _overlaps(a0, a1, t0, t1) -> bool:
    return (t1 is None or a0 <= t1) and (t0 is None or a1 >= t0)


def run_search(pq: ParsedQuery) -> dict:
    videos = {v.id: v for v in list_videos() if v.status == "Completed"}
    if not videos:
        return {"answer": "No videos have been analysed yet. Upload a video on the Analyse Video page first.", "results": []}
    if pq.video_hint:
        videos = {i: v for i, v in videos.items() if pq.video_hint in v.filename.lower()}
        if not videos:
            return {"answer": f"No analysed video matches “{pq.video_hint}”.", "results": []}
    t0, t1 = pq.time_from, pq.time_to

    # ---- what happened between X and Y -> segments ------------------------------------------------------------
    if pq.intent == "segments":
        return _segments(pq, videos)

    # ---- event questions (theft, pickup, running, suspicious ...) ----------------------------------------------
    if pq.kinds or pq.min_severity:
        evs = query_events(kinds=pq.kinds or None, min_severity=pq.min_severity, order="time")
        evs = [e for e in evs if e.video_id in videos and _overlaps(e.start_sec, e.end_sec or e.start_sec, t0, t1)]
        if pq.labels:  # e.g. "handbag": the event must involve an entity with that label
            evs = [e for e in evs if any(x["label"] in pq.labels for x in e.entities)]
        items = [_event_item(e) for e in evs]
        if pq.intent == "count":
            answer = f"{len(items)} matching event{'s' if len(items) != 1 else ''} in {len({e.video_id for e in evs})} video(s)."
        elif items:
            answer = (f"{'Yes - ' if pq.intent == 'exists' else ''}{len(items)} matching event{'s' if len(items) != 1 else ''}. "
                      f"Earliest: {items[0]['title']} at {fmt_clock(items[0]['startSec'])} in {items[0]['filename']}.")
        else:
            answer = _no_event_answer(pq)
        return {"answer": answer + (f" {pq.note}" if pq.note and items else ""), "results": items}

    # ---- entity questions (people / animals / objects) ---------------------------------------------------------
    if pq.groups or pq.labels:
        return _entities(pq, videos)

    # ---- fallback: free-text over event descriptions and segment summaries -------------------------------------
    if pq.keywords:
        like = [f"%{k}%" for k in pq.keywords]
        items = []
        with connect() as c:
            for r in c.execute("SELECT s.*, v.filename fn FROM segments s JOIN videos v ON v.id=s.video_id WHERE v.status='Completed' "
                               "ORDER BY v.created_ts DESC, s.idx"):
                if r["video_id"] in videos and all(k.lower() in (r["summary"] + " " + r["interactions_json"]).lower() for k in pq.keywords):
                    items.append(_seg_item(r))
        return {"answer": (f"{len(items)} segment{'s' if len(items) != 1 else ''} mention that." if items else
                           "Nothing in the stored analysis matches those words."), "results": items}
    return {"answer": "I could not tell what to look for. Try asking about people, animals, objects, or events such as "
                      "“show all suspicious activities”.", "results": []}


def _no_event_answer(pq: ParsedQuery) -> str:
    if "transfer" in pq.kinds:
        return ("No stored analysis shows an object being taken from a person. ChronoVision reports only what its detectors "
                "observed, so this does not prove nothing happened - small or heavily occluded items can be missed.")
    if "restricted_entry" in pq.kinds:
        return ("No restricted-area entries were recorded. Restricted areas must be marked on a video before analysis; "
                "ChronoVision does not guess them.")
    if pq.min_severity == "suspicious":
        return "No potentially suspicious or high-priority activity was detected in the analysed videos."
    if pq.kinds:
        names = {"unattended": "unattended objects", "abandoned": "abandoned objects", "pickup": "object pick-ups",
                 "handover": "hand-overs", "loitering": "loitering", "prolonged_presence": "loitering",
                 "running": "running", "approach_flee": "running", "following": "one person following another",
                 "carry": "people carrying objects", "approach": "people approaching one another",
                 "vehicle_proximity": "movement around vehicles", "line_crossing": "boundary crossings"}
        what = sorted({names.get(k, k.replace("_", " ")) for k in pq.kinds})
        return (f"No stored analysis shows {' or '.join(what)}. ChronoVision reports only what its detectors observed, "
                "so this does not prove nothing happened - small or heavily occluded items can be missed.")
    return "No stored analysis matches this question."


def _entities(pq: ParsedQuery, videos: dict) -> dict:
    sql = ("SELECT e.* FROM entities e JOIN videos v ON v.id=e.video_id WHERE v.status='Completed'")
    args: list = []
    if pq.labels:
        sql += f" AND e.label IN ({','.join('?' * len(pq.labels))})"; args += pq.labels
    elif pq.groups:
        sql += f" AND e.grp IN ({','.join('?' * len(pq.groups))})"; args += pq.groups
    sql += " ORDER BY v.created_ts DESC, e.first_sec"
    with connect() as c:
        rows = [r for r in c.execute(sql, args) if r["video_id"] in videos
                and _overlaps(r["first_sec"], r["last_sec"], pq.time_from, pq.time_to)]
    noun = _noun(pq)
    if pq.intent == "longest":
        rows.sort(key=lambda r: -r["duration_sec"])
        rows = rows[:1]
        if not rows:
            return {"answer": f"No {noun} were detected.", "results": []}
        r = rows[0]
        return {"answer": f"{ent_name(r['grp'], r['seq'])} was visible the longest: {fmt_clock(r['first_sec'])} to "
                          f"{fmt_clock(r['last_sec'])} ({r['duration_sec']:.0f}s) in {videos[r['video_id']].filename}.",
                "results": [_entity_item(r, videos)]}
    items = [_entity_item(r, videos) for r in rows]
    per_video: dict[str, int] = {}
    for r in rows:
        per_video[r["video_id"]] = per_video.get(r["video_id"], 0) + 1
    if not rows:
        return {"answer": (f"No {noun} were detected in the analysed videos." if pq.intent in ("exists", "count", "list")
                           else "Nothing found."), "results": []}
    breakdown = "; ".join(f"{videos[v].filename}: {n}" for v, n in per_video.items())
    lead = "Yes - " if pq.intent == "exists" else ""
    answer = f"{lead}{len(rows)} unique {_plural(noun, len(rows))} detected" + (
        f" ({breakdown})." if len(per_video) > 1 else f" in {videos[next(iter(per_video))].filename}.")
    if pq.note:
        answer += " " + pq.note
    return {"answer": answer, "results": items}


_VEHICLES = {"bicycle", "car", "motorcycle", "bus", "truck"}
_BAGS = {"handbag", "backpack", "suitcase"}
_SINGULAR = {"people": "person", "animals": "animal", "objects": "object", "vehicles": "vehicle", "bags": "bag"}


def _noun(pq: ParsedQuery) -> str:
    if pq.labels:
        ls = set(pq.labels)
        return "vehicles" if ls == _VEHICLES else "bags" if ls == _BAGS else " / ".join(pq.labels)
    if len(pq.groups) == 1:
        return {"person": "people", "animal": "animals", "object": "objects"}[pq.groups[0]]
    return "people, animals and objects"


def _plural(noun: str, n: int) -> str:
    if noun in _SINGULAR:
        return noun if n != 1 else _SINGULAR[noun]
    if " / " in noun or n == 1 or noun.endswith("s") and noun != "bus":
        return noun
    return noun + ("es" if noun.endswith(("s", "x", "ch", "sh")) else "s")


def _entity_item(r, videos) -> dict:
    return {"type": "entity", "videoId": r["video_id"], "filename": videos[r["video_id"]].filename,
            "startSec": r["first_sec"], "endSec": r["last_sec"], "title": f"{ent_name(r['grp'], r['seq'])} ({r['label']})",
            "text": f"Visible from {fmt_clock(r['first_sec'])} to {fmt_clock(r['last_sec'])} ({r['duration_sec']:.0f}s observed).",
            "thumbnail": f"/api/entities/{r['id']}/thumb" if r["thumb_path"] else None, "confidence": round(r["confidence"], 2),
            "severity": None, "severityLabel": None, "entities": [{"name": ent_name(r["grp"], r["seq"]), "label": r["label"]}]}


def _seg_item(r) -> dict:
    return {"type": "segment", "videoId": r["video_id"], "filename": r["fn"], "startSec": r["start_sec"], "endSec": r["end_sec"],
            "title": f"{fmt_clock(r['start_sec'])} - {fmt_clock(r['end_sec'])}", "text": r["summary"],
            "thumbnail": f"/api/segments/{r['id']}/frame" if r["frame_path"] else None, "confidence": r["confidence"],
            "severity": r["classification"], "severityLabel": taxonomy.SEVERITY_LABEL[r["classification"]], "entities": []}


def _segments(pq: ParsedQuery, videos: dict) -> dict:
    with connect() as c:
        rows = [r for r in c.execute("SELECT s.*, v.filename fn FROM segments s JOIN videos v ON v.id=s.video_id "
                                     "WHERE v.status='Completed' ORDER BY v.created_ts DESC, s.idx")
                if r["video_id"] in videos and _overlaps(r["start_sec"], r["end_sec"], pq.time_from, pq.time_to)]
    if not rows:
        return {"answer": "No analysed footage covers that time range.", "results": []}
    return {"answer": f"{len(rows)} segment{'s' if len(rows) != 1 else ''} overlap that time range.",
            "results": [_seg_item(r) for r in rows]}
