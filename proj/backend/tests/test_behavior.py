"""Behaviour-engine tests on SCRIPTED trajectories (synthetic - they check the reasoning rules, not real footage)."""
from app.behavior import analyse
from app.entities import Entity

W, H = 2000, 600


def ent(group, label, seq, box_fn, t0, t1, conf=0.9, pan=0.0):
    """box_fn(t) -> (x1,y1,x2,y2) in WORLD pixels. pan = camera content shift in frame-fractions per second."""
    obs, t = [], t0
    while t <= t1 + 1e-9:
        x1, y1, x2, y2 = box_fn(t)
        sx = pan * t
        obs.append((round(t, 2), x1 / W + sx, y1 / H, x2 / W + sx, y2 / H, conf, sx, 0.0))
        t += 0.1
    return Entity(f"{label}{seq}", group, label, seq, [seq], obs)


def person(seq, cx_fn, t0, t1, **kw):
    return ent("person", "person", seq, lambda t: (cx_fn(t) - 35, 250, cx_fn(t) + 35, 450), t0, t1, **kw)


def bag_following(fn_a, fn_b, t_switch, t1):
    def box(t):
        cx = (fn_a if t < t_switch else fn_b)(t)
        return (cx - 10, 340, cx + 20, 370)  # inside the holder's box
    return ent("object", "handbag", 1, box, 0, t1)


def kinds(evs):
    return [(e.kind, e.severity) for e in evs]


def test_theft_scenario_is_high_priority_and_hedged():
    a = lambda t: 300.0                                                      # victim stands still
    b = lambda t: 1900 + (380 - 1900) * min(1, max(0, (t - 3) / 3)) if t < 6 else 380 + 500 * (t - 6)
    A = person(1, a, 0, 14)
    B = person(2, b, 3, 9)                    # enters from the right at t=3, walks up to the victim, runs off after t=6
    bag = bag_following(a, b, 6.0, 9)
    evs = analyse([A, B, bag], W, H, 14)
    tr = [e for e in evs if e.kind == "transfer"]
    assert len(tr) == 1 and tr[0].severity == "high", kinds(evs)
    t = tr[0]
    assert 5.5 <= t.start <= 6.5 and t.details["approached"] and t.details["moved_away"] and t.details["fled"]
    assert "appears to take" in t.description and "Person 2" in t.description and "Person 1" in t.description
    assert any(e.kind == "carry" and e.entities[0] == A.id for e in evs)     # the victim carried the bag first
    assert 0.3 < t.confidence < 1


def test_handover_between_people_standing_together_is_normal():
    a, b = (lambda t: 300.0), (lambda t: 400.0)
    evs = analyse([person(1, a, 0, 14), person(2, b, 0, 14), bag_following(a, b, 9.0, 14)], W, H, 14)
    assert [(k, s) for k, s in kinds(evs) if k in ("transfer", "handover")] == [("handover", "normal")]


def test_bag_left_behind_is_flagged_after_it_stays_alone():
    a = lambda t: 300.0 if t < 4 else 300.0 + 400 * (t - 4)
    A = person(1, a, 0, 8)                                                   # owner walks out of the scene
    bag = ent("object", "handbag", 1,
              lambda t: (290, 340, 320, 370) if t >= 4 else (a(t) - 10, 340, a(t) + 20, 370), 0, 26)
    evs = analyse([A, bag], W, H, 26)
    ab = [e for e in evs if e.kind == "abandoned"]
    assert len(ab) == 1 and ab[0].severity == "suspicious" and "Person 1" in ab[0].description


def test_running_detected_but_walking_is_not():
    runner = person(1, lambda t: 200 + 520 * t, 0, 3)                        # 520 px/s on a 200 px person = 2.6 heights/s
    walker = person(2, lambda t: 200 + 90 * t, 0, 12)
    evs = analyse([runner, walker], W, H, 12)
    assert [e.entities for e in evs if e.kind == "running"] == [[runner.id]]


def test_camera_pan_does_not_create_motion_events():
    # three people standing still in the world while the camera pans fast: image positions slide, world positions don't
    ps = [person(i + 1, lambda t, x=400 + 500 * i: float(x), 0, 12, pan=-0.12) for i in range(3)]
    evs = analyse(ps, W, H, 12)
    assert not [e for e in evs if e.kind in ("running", "following")], kinds(evs)


def test_nothing_detected_means_no_events():
    assert analyse([], W, H, 10) == []
