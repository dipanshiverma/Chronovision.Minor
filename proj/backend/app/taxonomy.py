"""What ChronoVision can recognise (COCO classes of the YOLO model) and how it groups them.

Only categories the model really supports are listed. COCO has no "purse": handbags and purses are both "handbag"."""
from __future__ import annotations

PERSON, ANIMAL, OBJECT = "person", "animal", "object"

# COCO class id -> (group, label)
COCO: dict[int, tuple[str, str]] = {
    0: (PERSON, "person"),
    14: (ANIMAL, "bird"), 15: (ANIMAL, "cat"), 16: (ANIMAL, "dog"), 17: (ANIMAL, "horse"), 18: (ANIMAL, "sheep"),
    19: (ANIMAL, "cow"), 20: (ANIMAL, "elephant"), 21: (ANIMAL, "bear"), 22: (ANIMAL, "zebra"), 23: (ANIMAL, "giraffe"),
    1: (OBJECT, "bicycle"), 2: (OBJECT, "car"), 3: (OBJECT, "motorcycle"), 5: (OBJECT, "bus"), 7: (OBJECT, "truck"),
    13: (OBJECT, "bench"), 24: (OBJECT, "backpack"), 25: (OBJECT, "umbrella"), 26: (OBJECT, "handbag"),
    28: (OBJECT, "suitcase"), 39: (OBJECT, "bottle"), 41: (OBJECT, "cup"), 56: (OBJECT, "chair"), 57: (OBJECT, "couch"),
    60: (OBJECT, "dining table"), 62: (OBJECT, "tv"), 63: (OBJECT, "laptop"), 67: (OBJECT, "cell phone"), 73: (OBJECT, "book"),
}

VEHICLES = {"bicycle", "car", "motorcycle", "bus", "truck"}
MOTOR_VEHICLES = {"car", "motorcycle", "bus", "truck"}
BAGS = {"handbag", "backpack", "suitcase"}
CARRYABLE = BAGS | {"cell phone", "bottle", "laptop", "umbrella", "cup", "book"}

# Minimum detection confidence per group (small objects are detected less confidently, so the bar is lower).
MIN_CONF = {PERSON: 0.35, ANIMAL: 0.35, OBJECT: 0.25}

SEVERITY_ORDER = {"normal": 0, "unusual": 1, "suspicious": 2, "high": 3}
SEVERITY_LABEL = {
    "normal": "Normal Activity", "unusual": "Unusual Activity",
    "suspicious": "Potentially Suspicious", "high": "High-Priority Incident",
}


def max_severity(*sev: str) -> str:
    return max(sev, key=lambda s: SEVERITY_ORDER[s]) if sev else "normal"
