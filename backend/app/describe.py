"""Builds the consecutive 10-second segments: counts, interactions, classification and a plain-English summary.

Every sentence is composed from facts measured on the tracked entities (who is present, how they move, what they
carry, what the behaviour engine concluded). Nothing is looked up from a script, so a quiet empty scene yields a quiet
summary and a busy one yields a busy summary."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import taxonomy
from .behavior import EventRec, Scene, _gap

INTERACTION_KINDS = {"carry", "approach", "handover", "transfer", "pickup", "approach_flee", "following",
                     "vehicle_proximity", "abandoned", "unattended"}
EDGE = 0.04


@dataclass
class SegRec:
    idx: int
    start: float
    end: float
    summary: str
    people: int
    animals: int
    objects: int
    objects_breakdown: dict[str, int]
    entity_ids: list[str]
    event_idx: list[int]
    interactions: list[str]
    classification: str
    confidence: float | None
    frame_t: float
    highlight: list[str] = field(default_factory=list)


def _in_window(e, t0: float, t1: float) -> bool:
    return any(t0 <= o[0] < t1 for o in e.obs)


def build_segments(sc: Scene, events: list[EventRec], duration: float, seg_len: float) -> list[SegRec]:
    out: list[SegRec] = []
    n = max(1, int(-(-duration // seg_len)))  # ceil; a clip shorter than seg_len is one segment, the tail is partial
    for i in range(n):
        t0, t1 = i * seg_len, min(duration, (i + 1) * seg_len)
        if i == n - 1:
            t1 = max(t1, t0 + 0.01)
        ents = [e for e in sc.ents.values() if _in_window(e, t0, t1 + (1e-6 if i == n - 1 else 0))]
        people = [e for e in ents if e.group == taxonomy.PERSON]
        animals = [e for e in ents if e.group == taxonomy.ANIMAL]
        objects = [e for e in ents if e.group == taxonomy.OBJECT]
        # an event belongs to a segment if it overlaps it; touching the boundary does not count
        ev_idx = [j for j, ev in enumerate(events)
                  if ev.start < t1 and ((ev.end > t0) if ev.end is not None else ev.start >= t0)]
        evs = [events[j] for j in ev_idx]
        sev = taxonomy.max_severity(*[ev.severity for ev in evs]) if evs else "normal"

        obs_conf = [o[5] for e in ents for o in e.obs if t0 <= o[0] < t1 + 1e-6]
        conf = round(sum(obs_conf) / len(obs_conf), 2) if obs_conf else None
        important = Counter(e.label for e in objects)

        interactions = [ev.title for ev in sorted(evs, key=lambda x: -taxonomy.SEVERITY_ORDER[x.severity])
                        if ev.kind in INTERACTION_KINDS and ev.kind != "carry"][:6]

        # representative frame: the most serious event, else the moment with the most detections
        top = max(evs, key=lambda x: (taxonomy.SEVERITY_ORDER[x.severity], x.confidence), default=None)
        if top and top.severity != "normal":
            ft = min(max(top.frame_t, t0), max(t0, t1 - 0.05))
            highlight = list(top.entities)
        else:
            counts: Counter = Counter()
            for e in ents:
                for o in e.obs:
                    if t0 <= o[0] < t1:
                        counts[round(o[0], 2)] += 1
            ft = max(counts, key=lambda t: (counts[t], -t)) if counts else (t0 + t1) / 2
            highlight = []

        out.append(SegRec(i, t0, t1, _summary(sc, t0, t1, people, animals, objects, evs), len(people), len(animals),
                          len(objects), dict(important), [e.id for e in ents], ev_idx, interactions, sev, conf, ft, highlight))
    return out


def _summary(sc: Scene, t0, t1, people, animals, objects, evs) -> str:
    if not (people or animals or objects):
        return "No people, animals or tracked objects are visible in this interval."
    sentences: list[str] = []
    flagged = sorted((e for e in evs if e.severity != "normal"), key=lambda e: -taxonomy.SEVERITY_ORDER[e.severity])
    for e in flagged[:2]:
        sentences.append(e.description)
    for e in [e for e in evs if e.severity == "normal" and e.kind in ("approach", "handover", "pickup")][:1]:
        sentences.append(e.description)

    described = {x for e in flagged[:2] for x in e.entities}
    carries = {e.entities[0]: [] for e in evs if e.kind == "carry"}
    for e in evs:
        if e.kind == "carry":
            carries[e.entities[0]].append(sc.ents[e.entities[1]].label)

    if len(people) <= 3:
        for p in people:
            if p.id in described and flagged:
                continue
            sentences.append(_person_line(sc, p, t0, t1, carries.get(p.id, [])))
    else:
        st = Counter(sc.state(p, t0, t1) for p in people)
        bits = [f"{n} {s.replace('is visible', 'visible').replace('stands', 'standing').replace('walks', 'walking').replace('runs', 'running')}"
                for s, n in st.most_common()]
        sentences.append(f"{len(people)} people are visible ({', '.join(bits)}).")
    if animals:
        sentences.append(f"A {animals[0].label} ({animals[0].name}) is visible." if len(animals) == 1 else
                         f"{len(animals)} animals are visible ({', '.join(sorted({a.label for a in animals}))}).")
    if objects:
        c = Counter(o.label for o in objects)
        sentences.append("Objects in view: " + ", ".join(f"{l}" + (f" x{n}" if n > 1 else "") for l, n in c.most_common(5)) + ".")
    text = ""
    for s in sentences:
        if len(text) + len(s) > 360 and text:
            break
        text += (" " if text else "") + s
    return text


def _person_line(sc: Scene, p, t0, t1, carried: list[str]) -> str:
    state = sc.state(p, t0, t1)
    bits = [f"{p.name} {state}"]
    if carried:
        bits.append("while carrying " + " and ".join(f"a {c}" for c in dict.fromkeys(carried)))
    ks = sorted(sc.ks(p, t0, t1))
    if ks:
        mid = ks[len(ks) // 2]
        near = [v for v in sc.ents.values() if v.label in taxonomy.MOTOR_VEHICLES and mid in sc.s[v.id] and mid in sc.s[p.id]
                and _gap(sc, p, v, mid) <= 1.0]
        if near:
            bits.append(f"near a {near[0].label}")
    first, last = p.obs[0], p.obs[-1]
    if t0 <= first[0] < t1 and _at_edge(first):
        bits.append("after entering the scene")
    elif t0 <= last[0] < t1 and _at_edge(last) and last[0] < sc.duration - 0.5:
        bits.append("before leaving the scene")
    return " ".join(bits) + "."


def _at_edge(o) -> bool:
    return o[1] <= EDGE or o[3] >= 1 - EDGE  # side edges only: people are often cut off at the bottom of the frame
