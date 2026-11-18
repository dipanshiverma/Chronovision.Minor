"""Rule-based temporal event detection over tracked trajectories (methodology Step 4).

The engine is pure Python and detector-agnostic: feed it tracked boxes per processed frame and it
emits events. Positions use the bottom-centre of the box (the "feet" point), normalised to 0-1.

Events
  restricted - a track's feet point stays inside the restricted polygon for >= min_inside_obs observations.
               start = first frame inside, end = when it leaves (or the track is lost / video ends).
  line       - a track's path between two consecutive observations crosses the counting line. Instant event.
  presence   - a track stays inside the dwell area (whole frame if none drawn) for >= dwell_seconds.
               start = when it entered, end = when it left.

Small hysteresis (min_inside_obs / min_outside_obs) stops detector jitter from creating false events.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .geometry import Point, crosses_line, point_in_polygon, side

CATEGORIES = ("restricted", "line", "presence")
_EDGE = 1.0 - 1e-6


@dataclass
class TrackObs:
    track_id: int
    bbox: tuple[float, float, float, float]  # pixels: x1, y1, x2, y2
    conf: float
    label: str = "person"
    group: str = "person"


@dataclass
class RuleConfig:
    restricted_zone: Optional[list[Point]] = None
    line: Optional[tuple[Point, Point]] = None
    presence_zone: Optional[list[Point]] = None  # None -> whole frame
    dwell_seconds: float = 10.0
    enabled: dict[str, bool] = field(default_factory=lambda: {c: True for c in CATEGORIES})
    min_inside_obs: int = 3
    min_outside_obs: int = 3
    track_timeout_s: float = 1.5
    line_cooldown_s: float = 2.0


@dataclass
class RawEvent:
    category: str
    track_id: int
    start: float
    end: Optional[float]
    confidence: float
    bbox: tuple[float, float, float, float]
    detected_at: float
    details: dict = field(default_factory=dict)
    evidence: object = None  # annotated frame (np.ndarray) or None


@dataclass
class _Zoned:
    """Shared state for zone-like rules (restricted / presence)."""
    in_run: int = 0
    out_run: int = 0
    first_t: Optional[float] = None
    conf_sum: float = 0.0
    conf_n: int = 0
    event: Optional[RawEvent] = None

    def reset(self) -> None:
        self.in_run = self.out_run = self.conf_n = 0
        self.first_t = None
        self.conf_sum = 0.0
        self.event = None


@dataclass
class _TrackState:
    last_seen: float = 0.0
    prev_pt: Optional[Point] = None
    last_line_t: float = -1e9
    restricted: _Zoned = field(default_factory=_Zoned)
    presence: _Zoned = field(default_factory=_Zoned)


Renderer = Callable[..., object]


class EventEngine:
    def __init__(self, rules: RuleConfig, renderer: Optional[Renderer] = None):
        self.rules = rules
        self.renderer = renderer
        self.states: dict[int, _TrackState] = {}

    # ------------------------------------------------------------------ public
    def update(self, t: float, w: int, h: int, tracks: list[TrackObs], frame=None) -> list[RawEvent]:
        out: list[RawEvent] = []
        seen: set[int] = set()
        for tr in tracks:
            seen.add(tr.track_id)
            s = self.states.setdefault(tr.track_id, _TrackState())
            s.last_seen = t
            # Feet point, clamped just inside the frame: a person cut off by the frame edge still counts as being
            # inside a zone (or crossing a line) that was drawn right up to that edge.
            p: Point = (min(max((tr.bbox[0] + tr.bbox[2]) / 2 / w, 0.0), _EDGE), min(max(tr.bbox[3] / h, 0.0), _EDGE))
            r = self.rules
            if r.enabled.get("restricted", True) and r.restricted_zone:
                self._zone_rule("restricted", s.restricted, point_in_polygon(p, r.restricted_zone),
                                tr, t, frame, out, needed=r.min_inside_obs)
            if r.enabled.get("line", True) and r.line:
                self._line_rule(s, tr, p, t, frame, out)
            if r.enabled.get("presence", True):
                inside = True if not r.presence_zone else point_in_polygon(p, r.presence_zone)
                self._zone_rule("presence", s.presence, inside, tr, t, frame, out, needed=None)
            s.prev_pt = p

        for tid in [k for k, v in self.states.items() if k not in seen and t - v.last_seen > self.rules.track_timeout_s]:
            out.extend(self._close(self.states.pop(tid)))
        return out

    def finish(self) -> list[RawEvent]:
        out: list[RawEvent] = []
        for s in self.states.values():
            out.extend(self._close(s))
        self.states.clear()
        return out

    # ----------------------------------------------------------------- internals
    def _make(self, category, tr, start, t, frame, end, conf, details=None) -> RawEvent:
        ev = RawEvent(category, tr.track_id, start, end, conf, tr.bbox, t, details or {})
        if frame is not None and self.renderer is not None:
            ev.evidence = self.renderer(frame, self.rules, tr.bbox, category, tr.track_id, t)
        return ev

    def _zone_rule(self, cat, z: _Zoned, inside: bool, tr, t, frame, out, needed) -> None:
        if inside:
            z.out_run = 0
            z.in_run += 1
            if z.in_run == 1:
                z.first_t, z.conf_sum, z.conf_n = t, 0.0, 0
            z.conf_sum += tr.conf
            z.conf_n += 1
            if z.event is None:
                ready = z.in_run >= needed if cat == "restricted" else (t - z.first_t) >= self.rules.dwell_seconds
                if ready:
                    z.event = self._make(cat, tr, z.first_t, t, frame, t, tr.conf)
            if z.event is not None:
                z.event.end = t
                z.event.confidence = z.conf_sum / z.conf_n
        else:
            if z.event is not None:
                z.out_run += 1
                if z.out_run >= self.rules.min_outside_obs:
                    out.append(z.event)
                    z.reset()
            elif z.in_run:
                z.out_run += 1
                if z.out_run >= self.rules.min_outside_obs:
                    z.reset()

    def _line_rule(self, s: _TrackState, tr, p: Point, t, frame, out) -> None:
        a, b = self.rules.line  # type: ignore[misc]
        if s.prev_pt is None or t - s.last_line_t < self.rules.line_cooldown_s:
            return
        if crosses_line(s.prev_pt, p, a, b):
            s.last_line_t = t
            direction = "forward" if side(s.prev_pt, a, b) < 0 else "reverse"
            out.append(self._make("line", tr, t, t, frame, None, tr.conf, {"direction": direction}))

    def _close(self, s: _TrackState) -> list[RawEvent]:
        out = [z.event for z in (s.restricted, s.presence) if z.event is not None]
        s.restricted.reset()
        s.presence.reset()
        return out
