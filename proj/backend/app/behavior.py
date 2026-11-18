"""Temporal reasoning over tracked entities: who carries what, who approaches whom, what changes hands.

Object detection says *what is visible*; tracking says *which thing is which over time*; this module reasons about
*what changes and interacts over time*. Everything here is derived from geometry of the tracked boxes - nothing is
hard-coded per video. Distances are measured in "person heights" so the rules work at any camera distance, and
motion is measured in a world frame (camera panning compensated).

The rules are heuristics, so every event carries a confidence built from the detection confidences of the entities
involved and how many independent cues agree (see _score). Wording is deliberately hedged ("appears to ...").
"""
from __future__ import annotations

import math
import statistics
from bisect import bisect_left
from dataclasses import dataclass, field

from . import taxonomy
from .entities import Entity

STEP = 0.5            # analysis grid, seconds
STILL = 0.12          # person heights/second below which someone is standing still
RUN = 1.8             # person heights/second above which someone is running
HOLD_OVERLAP = 0.45   # fraction of an object's box inside a person's box to count as "with that person"
UNATTENDED_AFTER = 8.0
UNATTENDED_STRONG = 15.0
LOITER_SECONDS = 20.0


@dataclass
class EventRec:
    kind: str
    severity: str
    title: str
    description: str
    start: float
    end: float | None
    confidence: float
    entities: list[str]
    frame_t: float
    details: dict = field(default_factory=dict)


class Sample:
    """One entity at one grid time, in pixels. fx/fy = foot point (bottom centre); wx/wy = camera-compensated foot."""
    __slots__ = ("x1", "y1", "x2", "y2", "cx", "cy", "fx", "fy", "wx", "wy", "conf")

    def __init__(self, x1, y1, x2, y2, wx, wy, conf):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.cx, self.cy = (x1 + x2) / 2, (y1 + y2) / 2
        self.fx, self.fy = self.cx, y2
        self.wx, self.wy = wx, wy
        self.conf = conf

    @property
    def h(self) -> float:
        return max(1.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return max(1.0, (self.x2 - self.x1) * (self.y2 - self.y1))


class Scene:
    """All entities resampled on a common time grid."""

    def __init__(self, entities: list[Entity], w: int, h: int, duration: float):
        self.w, self.h, self.duration = w, h, duration
        self.ents = {e.id: e for e in entities}
        self.persons = [e for e in entities if e.group == taxonomy.PERSON]
        self.s: dict[str, dict[int, Sample]] = {e.id: self._resample(e) for e in entities}
        heights = [s.h for e in self.persons for s in self.s[e.id].values()]
        self.ref_h = statistics.median(heights) if heights else h * 0.3

    def _resample(self, e: Entity) -> dict[int, Sample]:
        times = [o[0] for o in e.obs]
        out: dict[int, Sample] = {}
        k = math.ceil(e.first / STEP - 1e-9)
        while k * STEP <= e.last + 1e-9:
            t = k * STEP
            i = bisect_left(times, t)
            cand = [j for j in (i - 1, i) if 0 <= j < len(times)]
            j = min(cand, key=lambda j: abs(times[j] - t))
            if abs(times[j] - t) <= 0.35:
                o = e.obs[j]
                box = o[1:5]
                conf, sx, sy = o[5], o[6], o[7]
            elif 0 < i < len(times) and times[i] - times[i - 1] <= 1.0:  # short gap: interpolate
                a, b = e.obs[i - 1], e.obs[i]
                f = (t - a[0]) / (b[0] - a[0])
                box = tuple(a[n] + f * (b[n] - a[n]) for n in range(1, 5))
                conf = min(a[5], b[5])
                sx, sy = a[6] + f * (b[6] - a[6]), a[7] + f * (b[7] - a[7])
            else:
                k += 1
                continue
            x1, y1, x2, y2 = box[0] * self.w, box[1] * self.h, box[2] * self.w, box[3] * self.h
            out[k] = Sample(x1, y1, x2, y2, (x1 + x2) / 2 - sx * self.w, y2 - sy * self.h, conf)
            k += 1
        return out

    # ------------------------------------------------------------------ measurements
    def dist(self, a: Entity, b: Entity, k: int, scale: float | None = None) -> float | None:
        sa, sb = self.s[a.id].get(k), self.s[b.id].get(k)
        if not sa or not sb:
            return None
        sc = scale or max(sa.h if a.group == taxonomy.PERSON else 0, sb.h if b.group == taxonomy.PERSON else 0) or self.ref_h
        return math.hypot(sa.cx - sb.cx, sa.fy - sb.fy if a.group == b.group == taxonomy.PERSON else sa.cy - sb.cy) / sc

    def foot_dist(self, a: Entity, b: Entity, k: int) -> float | None:
        sa, sb = self.s[a.id].get(k), self.s[b.id].get(k)
        if not sa or not sb:
            return None
        return math.hypot(sa.fx - sb.fx, sa.fy - sb.fy) / max(sa.h, sb.h)

    def speed(self, e: Entity, k0: int, k1: int) -> float | None:
        """World speed in heights/second between grid steps k0..k1 (None if not observed at both ends)."""
        a, b = self.s[e.id].get(k0), self.s[e.id].get(k1)
        if not a or not b or k1 <= k0:
            return None
        return math.hypot(b.wx - a.wx, b.wy - a.wy) / ((a.h + b.h) / 2) / ((k1 - k0) * STEP)

    def ks(self, e: Entity, t0: float, t1: float) -> list[int]:
        return [k for k in self.s[e.id] if t0 - 1e-9 <= k * STEP <= t1 + 1e-9]

    def state(self, e: Entity, t0: float, t1: float) -> str:
        """standing / walking / running for a person within a time window."""
        ks = sorted(self.ks(e, t0, t1))
        speeds = [v for i in range(len(ks) - 2) if (v := self.speed(e, ks[i], ks[i + 2])) is not None]
        if not speeds:
            return "is visible"
        m = statistics.median(speeds)
        return "stands" if m < STILL else "runs" if m >= RUN else "walks"


# ----------------------------------------------------------------------------------------------------------------
def _score(conf_parts: list[float], cues: int, max_cues: int, floor: float = 0.45) -> float:
    """Heuristic confidence: mean detection confidence of the entities involved, scaled by how many cues agree."""
    base = sum(conf_parts) / len(conf_parts) if conf_parts else 0.5
    return round(min(0.97, base * (floor + (1 - floor) * cues / max_cues)), 2)


def _holder_runs(sc: Scene, obj: Entity) -> list[dict]:
    """Intervals during which a person holds/carries the object (object box mostly inside the person's box)."""
    runs: list[dict] = []
    cur: dict | None = None
    for k, so in sorted(sc.s[obj.id].items()):
        best, best_ov = None, 0.0
        for p in sc.persons:
            sp = sc.s[p.id].get(k)
            if not sp or sp.area < 2 * so.area:
                continue
            ix = max(0.0, min(sp.x2, so.x2) - max(sp.x1, so.x1))
            iy = max(0.0, min(sp.y2, so.y2) - max(sp.y1, so.y1))
            ov = ix * iy / so.area
            if ov > best_ov:
                best, best_ov = p, ov
        pid = best.id if best and best_ov >= HOLD_OVERLAP else None
        if pid and cur and cur["pid"] == pid and k - cur["k1"] <= 3:
            cur["k1"] = k; cur["n"] += 1; cur["ov"] += best_ov
        else:
            if cur:
                runs.append(cur)
            cur = {"pid": pid, "k0": k, "k1": k, "n": 1, "ov": best_ov} if pid else None
    if cur:
        runs.append(cur)
    return [r for r in runs if r["n"] >= 3]


def analyse(entities: list[Entity], w: int, h: int, duration: float, scene: Scene | None = None) -> list[EventRec]:
    sc = scene or Scene(entities, w, h, duration)
    events: list[EventRec] = []
    events += _carrying_and_transfers(sc)
    events += _unattended(sc)
    events += _approaches(sc, events)
    events += _motion(sc)
    events += _vehicles(sc)
    events.sort(key=lambda e: (e.start, -taxonomy.SEVERITY_ORDER[e.severity]))
    return events[:300]


# ---------------------------------------------------------------------------------------------- carry / transfer
def _carrying_and_transfers(sc: Scene) -> list[EventRec]:
    out: list[EventRec] = []
    for obj in (e for e in sc.ents.values() if e.group == taxonomy.OBJECT and e.label in taxonomy.CARRYABLE):
        runs = _holder_runs(sc, obj)
        for r in runs:
            p = sc.ents[r["pid"]]
            t0, t1 = r["k0"] * STEP, r["k1"] * STEP
            if t1 - t0 >= 2.0:
                out.append(EventRec(
                    "carry", "normal", f"{p.name} carries a {obj.label}", f"{p.name} carries {_a(obj.label)} ({obj.name}).",
                    t0, t1, _score([p.conf, obj.conf, r["ov"] / r["n"]], 2, 2, 0.8), [p.id, obj.id], (t0 + t1) / 2,
                    {"holder": p.id, "object": obj.id}))
        # first pickup: object lay still, unheld and unattended, then somebody walks up and takes it
        if runs and sc.ents[runs[0]["pid"]]:
            r0 = runs[0]
            before = [k for k in sc.s[obj.id] if k < r0["k0"]]
            if len(before) >= 4:
                still = _obj_stationary(sc, obj, before)
                p = sc.ents[r0["pid"]]
                kb = r0["k0"] - 6
                d_then = sc.dist(p, obj, kb, sc.ref_h) if kb in sc.s[p.id] else None
                if still and (d_then is None or d_then > 2.0):
                    t = r0["k0"] * STEP
                    out.append(EventRec(
                        "pickup", "unusual", f"{p.name} picks up an unattended {obj.label}",
                        f"{p.name} walks up to {obj.ref()} lying unattended and picks it up.", t, t + 2,
                        _score([p.conf, obj.conf], 1, 2, 0.6), [p.id, obj.id], t, {"object": obj.id, "picker": p.id}))
        # hand-over / removal between two different people
        for r1, r2 in zip(runs, runs[1:]):
            if r1["pid"] == r2["pid"]:
                continue
            gap = (r2["k0"] - r1["k1"]) * STEP
            if gap > 20 or (r1["k1"] - r1["k0"]) * STEP < 1.5:
                continue
            out.append(_transfer(sc, obj, sc.ents[r1["pid"]], sc.ents[r2["pid"]], r1, r2, gap))
    return out


def _a(label: str) -> str:
    return ("an " if label[0] in "aeiou" else "a ") + label


def _obj_stationary(sc: Scene, obj: Entity, ks: list[int]) -> bool:
    ss = [sc.s[obj.id][k] for k in ks]
    ref = max(statistics.median(s.h for s in ss), 1.0)
    return (max(s.wx for s in ss) - min(s.wx for s in ss) + max(s.wy for s in ss) - min(s.wy for s in ss)) / ref < 1.0


def _transfer(sc, obj, a: Entity, b: Entity, r1, r2, gap) -> EventRec:
    kt = r2["k0"]
    t = kt * STEP
    d_at = _nearest(sc, a, b, kt)
    before = [d for k in range(kt - 12, kt - 1) if (d := sc.foot_dist(a, b, k)) is not None]
    after = [d for k in range(kt + 2, kt + 11) if (d := sc.foot_dist(a, b, k)) is not None]
    b_new = b.first >= t - 4.0
    approached = b_new or (len(before) >= 2 and d_at is not None and max(before) - d_at >= 0.6)
    moved_away = bool(after and d_at is not None and max(after) - d_at >= 0.8 and len(after) >= 2)
    run_speeds = [v for k in range(kt, kt + 12) if (v := sc.speed(b, k, k + 2)) is not None]
    fled = bool(run_speeds) and max(run_speeds) >= RUN
    together = sum(1 for k in range(kt - 30, kt - 5) if (d := sc.foot_dist(a, b, k)) is not None and d <= 1.5) * STEP

    cues = sum([approached, moved_away, fled])
    conf = _score([a.conf, b.conf, obj.conf], cues, 3, 0.55)
    where = f"{obj.ref()}, previously carried by {a.name}"
    if together >= 6.0:
        sev, kind, title = "normal", "handover", f"{a.name} and {b.name} exchange {_a(obj.label)}"
        desc = f"{b.name} receives {where}; the two had been together beforehand, so this looks like a hand-over."
    else:
        kind = "transfer"
        sev = "high" if (approached and moved_away and fled) else "suspicious" if (approached and moved_away) else "unusual"
        title = f"{b.name} appears to take {a.name}'s {obj.label}"
        parts = [f"{b.name} {'approaches ' + a.name + ' and ' if approached else ''}appears to take {where}"]
        if moved_away:
            parts.append("then moves away from " + a.name + (" quickly" if fled else ""))
        desc = ", ".join(parts) + "."
        if gap > 3:
            desc = f"{b.name} picks up {where} about {gap:.0f}s after {a.name} lost it."
            sev = "unusual" if sev != "high" else sev
    return EventRec(kind, sev, title, desc, t, t + min(4.0, max(1.0, sc.duration - t)), conf, [a.id, b.id, obj.id], t,
                    {"victim": a.id, "taker": b.id, "object": obj.id, "approached": approached, "moved_away": moved_away,
                     "fled": fled, "together_before_s": together})


def _nearest(sc, a, b, k):
    for dk in (0, 1, -1, 2, -2):
        d = sc.foot_dist(a, b, k + dk)
        if d is not None:
            return d
    return None


# ---------------------------------------------------------------------------------------------------- unattended
def _unattended(sc: Scene) -> list[EventRec]:
    out: list[EventRec] = []
    for obj in (e for e in sc.ents.values() if e.group == taxonomy.OBJECT and e.label in taxonomy.BAGS):
        runs = _holder_runs(sc, obj)
        t_left = runs[-1]["k1"] * STEP if runs else obj.first
        holder = sc.ents[runs[-1]["pid"]] if runs else None
        ks = [k for k in sc.s[obj.id] if k * STEP > t_left + 0.5]
        if len(ks) < 6:
            continue
        # count how long the object lies still with nobody within 2.5 person-heights
        quiet, started = [], False
        for k in sorted(ks):
            near = [d for p in sc.persons if (d := sc.dist(p, obj, k, sc.ref_h)) is not None and d <= 2.5]
            if near:
                if started:
                    break          # somebody came back: the unattended period is over
                continue           # the owner is still walking away: wait until they are clear of the object
            started = True
            quiet.append(k)
        if len(quiet) < 4 or not _obj_stationary(sc, obj, quiet):
            continue
        span = (quiet[-1] - quiet[0]) * STEP
        if span < UNATTENDED_AFTER and not (quiet[-1] * STEP >= sc.duration - 0.6 and span >= UNATTENDED_AFTER * 0.75):
            continue
        sev = "suspicious" if span >= UNATTENDED_STRONG else "unusual"
        if holder:
            kind, title = "abandoned", f"{obj.label.capitalize()} left behind by {holder.name}"
            desc = f"{holder.name} leaves {obj.ref()} behind; it stays unattended for at least {span:.0f}s."
        else:
            kind, title = "unattended", f"Unattended {obj.label}"
            desc = f"{obj.ref().capitalize()} remains unattended with nobody nearby for at least {span:.0f}s."
        out.append(EventRec(kind, sev, title, desc, quiet[0] * STEP, quiet[-1] * STEP,
                            _score([obj.conf] + ([holder.conf] if holder else []), 1 + (span >= UNATTENDED_STRONG), 2, 0.6),
                            [obj.id] + ([holder.id] if holder else []), quiet[0] * STEP + 1, {"object": obj.id, "seconds": span}))
    return out


# ------------------------------------------------------------------------------------------- approach / follow
def _approaches(sc: Scene, existing: list[EventRec]) -> list[EventRec]:
    out: list[EventRec] = []
    P = sc.persons[:25]
    for i, a in enumerate(P):
        for b in P[i + 1:]:
            common = sorted(set(sc.s[a.id]) & set(sc.s[b.id]))
            if len(common) < 4:
                continue
            d = {k: sc.foot_dist(a, b, k) for k in common}
            close_k = next((k for k in common if d[k] <= 1.2 and any(
                d.get(k - j) is not None and d[k - j] >= 3.0 for j in range(2, 21))), None)
            if close_k is None:
                # one of them walking into an already-close position is not an "approach"; check following instead
                out += _following(sc, a, b, common)
                continue
            mover = max((a, b), key=lambda e: _disp(sc, e, close_k - 8, close_k))
            other = b if mover is a else a
            t = close_k * STEP
            out.append(EventRec("approach", "normal", f"{mover.name} approaches {other.name}",
                                f"{mover.name} walks up to {other.name}.", t, t + 2, _score([a.conf, b.conf], 1, 1, 0.8),
                                [mover.id, other.id], t, {"mover": mover.id}))
            # close contact followed by one person leaving quickly while the other stays: flag unless already
            # explained by a transfer event involving the same people.
            explained = any(e.kind in ("transfer", "handover") and {a.id, b.id} <= set(e.entities) and abs(e.start - t) < 10
                            for e in existing)
            if not explained:
                end_close = max((k for k in common if k >= close_k and d[k] <= 1.5), default=close_k)
                sp = {e.id: [v for k in range(end_close, end_close + 8) if (v := sc.speed(e, k, k + 2)) is not None]
                      for e in (a, b)}
                for flee, stay in ((a, b), (b, a)):
                    if sp[flee.id] and sp[stay.id] and max(sp[flee.id]) >= RUN and statistics.median(sp[stay.id]) < 0.6:
                        te = end_close * STEP
                        out.append(EventRec(
                            "approach_flee", "unusual", f"Close contact, then {flee.name} leaves quickly",
                            f"{flee.name} comes close to {stay.name} and then moves away quickly while {stay.name} stays.",
                            t, te + 3, _score([a.conf, b.conf], 2, 3, 0.5), [flee.id, stay.id], te, {"fled": flee.id}))
                        break
    return out


def _disp(sc, e, k0, k1):
    ks = [k for k in sc.s[e.id] if k0 <= k <= k1]
    if len(ks) < 2:
        return 0.0
    a, b = sc.s[e.id][min(ks)], sc.s[e.id][max(ks)]
    return math.hypot(a.wx - b.wx, a.wy - b.wy)


def _following(sc: Scene, a: Entity, b: Entity, common: list[int]) -> list[EventRec]:
    if (common[-1] - common[0]) * STEP < 8.0:
        return []
    sa = [v for k in common[:-2] if (v := sc.speed(a, k, k + 2)) is not None]
    sb = [v for k in common[:-2] if (v := sc.speed(b, k, k + 2)) is not None]
    if not sa or not sb or statistics.median(sa) < 0.4 or statistics.median(sb) < 0.4:
        return []
    direct = [sc.foot_dist(a, b, k) for k in common]
    dm = statistics.mean(direct)
    if not (1.0 <= dm <= 4.0):
        return []
    for lead, fol in ((a, b), (b, a)):
        lagged = []
        for tau in (2, 3, 4, 6):  # follower reaches where the leader was tau*0.5 s earlier
            ds = [math.hypot(sc.s[fol.id][k].wx - sc.s[lead.id][k - tau].wx, sc.s[fol.id][k].wy - sc.s[lead.id][k - tau].wy)
                  / sc.s[fol.id][k].h for k in common if (k - tau) in sc.s[lead.id]]
            if len(ds) >= 6:
                lagged.append(statistics.mean(ds))
        if lagged and min(lagged) < 0.5 * dm and lead.first < fol.first + 3:
            t0, t1 = common[0] * STEP, common[-1] * STEP
            return [EventRec("following", "unusual", f"{fol.name} follows {lead.name}",
                             f"{fol.name} appears to follow {lead.name} at a short distance for about {t1 - t0:.0f}s "
                             "(they may also simply be walking together).", t0, t1,
                             _score([a.conf, b.conf], 1, 2, 0.5), [fol.id, lead.id], (t0 + t1) / 2, {"leader": lead.id})]
    return []


# ----------------------------------------------------------------------------------- running / loitering
def _motion(sc: Scene) -> list[EventRec]:
    out: list[EventRec] = []
    for p in sc.persons:
        ks = sorted(sc.s[p.id])
        run_start = None
        for k in ks:
            v = sc.speed(p, k, k + 2)
            if v is not None and v >= RUN:
                run_start = k if run_start is None else run_start
                last = k + 2
            elif run_start is not None:
                if (last - run_start) * STEP >= 1.5:
                    out.append(_run_event(sc, p, run_start, last))
                run_start = None
        if run_start is not None and (last - run_start) * STEP >= 1.5:
            out.append(_run_event(sc, p, run_start, last))
        # loitering: stays within ~1.5 person-heights of one spot for LOITER_SECONDS
        if p.duration >= LOITER_SECONDS:
            anchor = None
            for k in ks:
                s = sc.s[p.id][k]
                if anchor is None or math.hypot(s.wx - anchor[1], s.wy - anchor[2]) > 1.5 * s.h:
                    anchor = (k, s.wx, s.wy)
                elif (k - anchor[0]) * STEP >= LOITER_SECONDS:
                    t0 = anchor[0] * STEP
                    out.append(EventRec("loitering", "unusual", f"{p.name} stays in one place",
                                        f"{p.name} remains in the same spot for at least {k * STEP - t0:.0f}s.", t0, k * STEP,
                                        _score([p.conf], 1, 1, 0.8), [p.id], t0 + LOITER_SECONDS / 2, {}))
                    break
    return out


def _run_event(sc, p, k0, k1) -> EventRec:
    t0, t1 = k0 * STEP, k1 * STEP
    return EventRec("running", "unusual", f"{p.name} runs", f"{p.name} runs through the scene.", t0, t1,
                    _score([p.conf], 1, 1, 0.8), [p.id], (t0 + t1) / 2, {})


def _vehicles(sc: Scene) -> list[EventRec]:
    out: list[EventRec] = []
    for veh in (e for e in sc.ents.values() if e.label in taxonomy.MOTOR_VEHICLES):
        for p in sc.persons:
            ks = [k for k in sorted(set(sc.s[p.id]) & set(sc.s[veh.id])) if _gap(sc, p, veh, k) <= 0.5]
            if len(ks) < 12:
                continue
            span = (ks[-1] - ks[0]) * STEP
            if span < 6.0:
                continue
            path = sum(math.hypot(sc.s[p.id][b].wx - sc.s[p.id][a].wx, sc.s[p.id][b].wy - sc.s[p.id][a].wy) / sc.s[p.id][b].h
                       for a, b in zip(ks, ks[1:]) if b - a <= 2)
            if path < 1.0:  # just standing/sitting beside it
                continue
            out.append(EventRec("vehicle_proximity", "unusual", f"{p.name} moves around {veh.ref()}",
                                f"{p.name} stays right next to {veh.ref()} for about {span:.0f}s while moving around it.",
                                ks[0] * STEP, ks[-1] * STEP, _score([p.conf, veh.conf], 1, 2, 0.5), [p.id, veh.id],
                                (ks[0] + ks[-1]) / 2 * STEP, {"vehicle": veh.id}))
    return out


def _gap(sc, p, veh, k) -> float:
    """Distance between a person's box and a vehicle box in person heights (0 when they overlap)."""
    a, b = sc.s[p.id][k], sc.s[veh.id][k]
    dx = max(0.0, max(a.x1, b.x1) - min(a.x2, b.x2))
    dy = max(0.0, max(a.y1, b.y1) - min(a.y2, b.y2))
    return math.hypot(dx, dy) / a.h
