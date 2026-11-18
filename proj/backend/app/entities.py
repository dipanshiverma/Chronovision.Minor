"""Turns raw tracker output into *unique entities* (Person 1, Animal 1, Object 1 ...).

ByteTrack gives every detection track an ID, but IDs fragment when someone is occluded or briefly missed. Counting
raw IDs would count one person several times. So we (1) drop very short/low-confidence noise tracks, and (2) stitch
fragments back together when a track ends and a new one of the same class begins close by in space and time.
This is a lightweight heuristic - it is NOT appearance re-identification - so a person who leaves the scene and
returns later is counted again, and long occlusions in crowds can still split an entity (documented limitation).
"""
from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import taxonomy

# observation tuple: (t, x1, y1, x2, y2, conf, shift_x, shift_y)  - box normalised 0-1, camera shift in frame fractions
Obs = tuple[float, float, float, float, float, float, float, float]

MIN_OBS = {taxonomy.PERSON: 3, taxonomy.ANIMAL: 3, taxonomy.OBJECT: 4}
MIN_DURATION = {taxonomy.PERSON: 0.5, taxonomy.ANIMAL: 0.5, taxonomy.OBJECT: 1.5}  # seconds; objects flicker more
MIN_MEAN_CONF = {taxonomy.PERSON: 0.40, taxonomy.ANIMAL: 0.40, taxonomy.OBJECT: 0.30}
MAX_GAP = 2.5  # seconds between a track ending and its continuation starting


@dataclass
class RawTrack:
    tid: int
    group: str
    labels: Counter = field(default_factory=Counter)
    obs: list[Obs] = field(default_factory=list)


class TrackBook:
    """Accumulates tracker output frame by frame."""

    def __init__(self) -> None:
        self.tracks: dict[int, RawTrack] = {}

    def add(self, t: float, tracks, w: int, h: int, shift: tuple[float, float]) -> None:
        for tr in tracks:
            x1, y1, x2, y2 = tr.bbox
            rt = self.tracks.setdefault(tr.track_id, RawTrack(tr.track_id, tr.group))
            rt.labels[tr.label] += tr.conf  # confidence-weighted vote: the class flips sometimes on small objects
            rt.obs.append((t, x1 / w, y1 / h, x2 / w, y2 / h, tr.conf, shift[0], shift[1]))


@dataclass
class Entity:
    id: str
    group: str
    label: str
    seq: int
    track_ids: list[int]
    obs: list[Obs]

    @property
    def name(self) -> str:
        return f"{self.group.capitalize()} {self.seq}"

    @property
    def first(self) -> float:
        return self.obs[0][0]

    @property
    def last(self) -> float:
        return self.obs[-1][0]

    @property
    def duration(self) -> float:
        return self.last - self.first

    @property
    def conf(self) -> float:
        return sum(o[5] for o in self.obs) / len(self.obs)

    def ref(self) -> str:
        """Human reference used in descriptions."""
        if self.group == taxonomy.PERSON:
            return self.name
        return f"the {self.label} ({self.name})"


def _centre(o: Obs, w: int, h: int, world: bool = True) -> tuple[float, float]:
    cx, cy = (o[1] + o[3]) / 2, (o[2] + o[4]) / 2
    if world:
        cx, cy = cx - o[6], cy - o[7]
    return cx * w, cy * h


def build_entities(book: TrackBook, w: int, h: int) -> list[Entity]:
    diag = math.hypot(w, h)
    kept: list[RawTrack] = []
    for rt in book.tracks.values():
        rt.obs.sort(key=lambda o: o[0])
        n = len(rt.obs)
        if n < MIN_OBS[rt.group] or rt.obs[-1][0] - rt.obs[0][0] < MIN_DURATION[rt.group]:
            continue
        if sum(o[5] for o in rt.obs) / n < MIN_MEAN_CONF[rt.group]:
            continue
        kept.append(rt)

    # --- stitch fragments: candidate pairs (a ends, b starts) of the same group and label ------------------
    def label_of(rt: RawTrack) -> str:
        return rt.labels.most_common(1)[0][0]

    cands = []
    for a in kept:
        for b in kept:
            if a is b or a.group != b.group or label_of(a) != label_of(b):
                continue
            gap = b.obs[0][0] - a.obs[-1][0]
            if gap < -0.05 or gap > MAX_GAP:
                continue
            ax, ay = _centre(a.obs[-1], w, h)
            bx, by = _centre(b.obs[0], w, h)
            dist = math.hypot(ax - bx, ay - by) / diag
            ha = a.obs[-1][4] - a.obs[-1][2]
            hb = b.obs[0][4] - b.obs[0][2]
            if not (0.6 <= (hb / ha if ha else 0) <= 1.6):
                continue
            allowed = 0.04 + 0.06 * max(gap, 0)
            if dist <= allowed:
                cands.append((dist / allowed, a.tid, b.tid))
    cands.sort()
    nxt: dict[int, int] = {}
    prv: dict[int, int] = {}
    for _, a, b in cands:
        if a in nxt or b in prv:
            continue
        # no cycles: follow b's chain forward and make sure it does not reach a
        c, ok = b, True
        while c in nxt:
            c = nxt[c]
            if c == a:
                ok = False
                break
        if ok and b != a:
            nxt[a], prv[b] = b, a

    by_tid = {rt.tid: rt for rt in kept}
    chains: list[list[RawTrack]] = []
    for rt in kept:
        if rt.tid in prv:
            continue
        chain, cur = [rt], rt.tid
        while cur in nxt:
            cur = nxt[cur]
            chain.append(by_tid[cur])
        chains.append(chain)

    # --- build entities, numbered per group by first appearance -------------------------------------------
    raw = []
    for chain in chains:
        obs = sorted((o for rt in chain for o in rt.obs), key=lambda o: o[0])
        votes: Counter = Counter()
        for rt in chain:
            votes.update(rt.labels)
        raw.append((obs[0][0], chain[0].group, votes.most_common(1)[0][0], [rt.tid for rt in chain], obs))
    raw.sort(key=lambda r: (r[0], r[3][0]))
    seq: dict[str, int] = defaultdict(int)
    out: list[Entity] = []
    for _, group, label, tids, obs in raw:
        seq[group] += 1
        out.append(Entity(f"n-{uuid.uuid4().hex[:8]}", group, label, seq[group], tids, obs))
    return out
