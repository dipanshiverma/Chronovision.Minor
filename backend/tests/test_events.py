from app.events import EventEngine, RuleConfig, TrackObs
from app.geometry import crosses_line, point_in_polygon

W, H = 1000, 1000
ZONE = [(0.4, 0.4), (0.8, 0.4), (0.8, 0.9), (0.4, 0.9)]


def obs(tid, x, y, conf=0.9):  # feet point at (x, y) normalised
    return TrackObs(tid, (x * W - 20, y * H - 100, x * W + 20, y * H), conf)


def run(rules, path, tid=1, dt=0.1):
    eng, evs = EventEngine(rules), []
    for i, (x, y) in enumerate(path):
        evs += eng.update(i * dt, W, H, [obs(tid, x, y)])
    return evs + eng.finish()


def test_geometry():
    assert point_in_polygon((0.5, 0.5), ZONE) and not point_in_polygon((0.1, 0.1), ZONE)
    assert crosses_line((0.2, 0.5), (0.8, 0.5), (0.5, 0.0), (0.5, 1.0))
    assert not crosses_line((0.2, 0.5), (0.4, 0.5), (0.5, 0.0), (0.5, 1.0))
    assert not crosses_line((0.2, 1.5), (0.8, 1.5), (0.5, 0.0), (0.5, 1.0))  # passes beyond the finite segment


def test_restricted_entry_and_exit():
    path = [(0.1, 0.6)] * 3 + [(0.5, 0.6)] * 10 + [(0.1, 0.6)] * 5
    evs = run(RuleConfig(restricted_zone=ZONE, presence_zone=ZONE, dwell_seconds=99), path)
    assert [e.category for e in evs] == ["restricted"]
    e = evs[0]
    assert abs(e.start - 0.3) < 1e-6 and abs(e.end - 1.2) < 1e-6  # first frame inside -> last frame inside


def test_brief_flicker_is_ignored():
    path = [(0.1, 0.6)] * 3 + [(0.5, 0.6)] * 2 + [(0.1, 0.6)] * 6  # inside only 2 observations (< 3)
    assert run(RuleConfig(restricted_zone=ZONE, presence_zone=ZONE, dwell_seconds=99), path) == []


def test_line_crossing_direction_and_cooldown():
    rules = RuleConfig(line=((0.5, 0.0), (0.5, 1.0)), dwell_seconds=99)
    right = run(rules, [(0.3, 0.5), (0.45, 0.5), (0.55, 0.5), (0.7, 0.5)])
    left = run(rules, [(0.7, 0.5), (0.55, 0.5), (0.45, 0.5), (0.3, 0.5)])
    assert [e.category for e in right] == ["line"] and right[0].end is None
    assert right[0].details["direction"] != left[0].details["direction"]
    jitter = run(rules, [(0.49, 0.5), (0.51, 0.5), (0.49, 0.5), (0.51, 0.5)])  # re-crossing inside cooldown
    assert len(jitter) == 1


def test_prolonged_presence_needs_dwell_time():
    inside = [(0.5, 0.6)] * 60  # 6 s at dt=0.1
    assert run(RuleConfig(presence_zone=ZONE, dwell_seconds=10), inside) == []
    evs = run(RuleConfig(presence_zone=ZONE, dwell_seconds=4), inside)
    assert len(evs) == 1 and evs[0].category == "presence"
    assert abs(evs[0].start - 0.0) < 1e-6 and evs[0].end >= 5.8 and abs(evs[0].detected_at - 4.0) < 0.11


def test_disabled_category_and_unset_geometry_produce_nothing():
    path = [(0.5, 0.6)] * 20
    rules = RuleConfig(restricted_zone=ZONE, enabled={"restricted": False, "line": True, "presence": False})
    assert run(rules, path) == []
    assert run(RuleConfig(enabled={"restricted": True, "line": True, "presence": False}), path) == []


def test_lost_track_closes_open_event():
    eng = EventEngine(RuleConfig(restricted_zone=ZONE, presence_zone=ZONE, dwell_seconds=99))
    evs = []
    for i in range(6):
        evs += eng.update(i * 0.1, W, H, [obs(1, 0.5, 0.6)])
    evs += eng.update(5.0, W, H, [])  # track gone > timeout
    assert len(evs) == 1 and evs[0].end == 0.5


def test_person_cut_off_by_frame_edge_still_triggers_edge_to_edge_rules():
    # Feet exactly on the bottom edge (y = 1.0), zone and line both drawn edge-to-edge.
    zone = [(0.4, 0.0), (0.8, 0.0), (0.8, 1.0), (0.4, 1.0)]
    rules = RuleConfig(restricted_zone=zone, line=((0.3, 0.0), (0.3, 1.0)), presence_zone=zone, dwell_seconds=99)
    path = [(0.2, 1.0), (0.35, 1.0)] + [(0.5, 1.0)] * 6
    cats = sorted(e.category for e in run(rules, path))
    assert cats == ["line", "restricted"]
