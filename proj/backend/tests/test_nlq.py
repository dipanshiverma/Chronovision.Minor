from app.nlq import interpretation, parse_rules

NAMES = ["parking_lot.mp4", "corridor.mp4"]


def test_theft_and_events():
    pq = parse_rules("When did someone steal the handbag?")
    assert pq.kinds == ["transfer"] and pq.labels == ["handbag"]
    assert parse_rules("show all suspicious activities").min_severity == "suspicious"
    assert "pickup" in parse_rules("When was a bag picked up?").kinds
    assert {"unattended", "abandoned"} <= set(parse_rules("Did anyone leave an object unattended?").kinds)
    assert parse_rules("Show all instances where someone carried a backpack").kinds == ["carry"]


def test_counts_and_exists():
    pq = parse_rules("How many vehicles appeared?")
    assert pq.intent == "count" and "car" in pq.labels and "truck" in pq.labels
    pq = parse_rules("Were any animals detected?")
    assert pq.intent == "exists" and pq.groups == ["animal"]
    assert parse_rules("How many people are there").groups == ["person"]


def test_longest_and_time_windows():
    pq = parse_rules("Which person stayed in the area the longest?")
    assert pq.intent == "longest" and pq.groups == ["person"]
    pq = parse_rules("What happened between 00:20 and 00:40?")
    assert pq.intent == "segments" and (pq.time_from, pq.time_to) == (20, 40)
    assert parse_rules("running after 30 seconds").time_from == 30


def test_entered_building_is_not_pretended():
    pq = parse_rules("How many people entered the building?")
    assert pq.intent == "count" and pq.groups == ["person"] and pq.note and "cannot tell" in pq.note
    assert parse_rules("When did someone enter the restricted area?").kinds == ["restricted_entry"]


def test_video_hint_and_chips():
    pq = parse_rules("suspicious activity in corridor.mp4", NAMES)
    assert pq.video_hint == "corridor"
    assert "suspicious or worse" in interpretation(pq)
