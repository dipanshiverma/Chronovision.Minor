"""Renders the annotated evidence frame saved with every event (zone/line overlay + real bounding box)."""
from __future__ import annotations

import cv2
import numpy as np

# BGR colours matching the UI palette (nectarine / peche / menthe)
COLORS = {"restricted": (86, 100, 235), "line": (96, 170, 250), "presence": (140, 200, 120)}
LABELS = {"restricted": "Restricted-Zone Entry", "line": "Line Crossing", "presence": "Prolonged Presence"}
MAX_WIDTH = 640


def _px(poly, w, h):
    return np.array([[int(x * w), int(y * h)] for x, y in poly], dtype=np.int32)


def render_evidence(frame, rules, bbox, category: str, track_id: int, t: float) -> np.ndarray:
    h, w = frame.shape[:2]
    img = frame.copy()
    col = COLORS.get(category, (255, 255, 255))

    # Draw only the overlay relevant to this event type.
    if category == "restricted" and rules.restricted_zone:
        pts = _px(rules.restricted_zone, w, h)
        layer = img.copy()
        cv2.fillPoly(layer, [pts], col)
        img = cv2.addWeighted(layer, 0.25, img, 0.75, 0)
        cv2.polylines(img, [pts], True, col, 2, cv2.LINE_AA)
    elif category == "line" and rules.line:
        a, b = rules.line
        cv2.line(img, (int(a[0] * w), int(a[1] * h)), (int(b[0] * w), int(b[1] * h)), col, 3, cv2.LINE_AA)
    elif category == "presence" and rules.presence_zone:
        pts = _px(rules.presence_zone, w, h)
        cv2.polylines(img, [pts], True, col, 2, cv2.LINE_AA)

    x1, y1, x2, y2 = (int(v) for v in bbox)
    cv2.rectangle(img, (x1, y1), (x2, y2), col, max(2, w // 400), cv2.LINE_AA)
    label = f"ID {track_id:02d}  {int(t // 60):02d}:{int(t % 60):02d}"
    scale = max(0.5, w / 1400)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    ty = max(th + 6, y1)
    cv2.rectangle(img, (x1, ty - th - 6), (x1 + tw + 8, ty + 2), col, -1)
    cv2.putText(img, label, (x1 + 4, ty - 3), cv2.FONT_HERSHEY_SIMPLEX, scale, (20, 20, 20), 2, cv2.LINE_AA)

    if w > MAX_WIDTH:
        img = cv2.resize(img, (MAX_WIDTH, int(h * MAX_WIDTH / w)), interpolation=cv2.INTER_AREA)
    return img


# ------------------------------------------------------------------------------------------------ scene frames
GROUP_COLORS = {"person": (127, 137, 215), "animal": (179, 199, 150), "object": (92, 185, 249)}  # BGR: nectarine/menthe/peche


def render_scene(frame, boxes, highlight: set | None = None, stamp: str | None = None) -> np.ndarray:
    """Annotated frame. boxes: [(entity_id, group, name, label, conf, (x1,y1,x2,y2) normalised)]. Highlighted entities
    (the ones an event is about) get a thicker box."""
    h, w = frame.shape[:2]
    img = frame.copy()
    scale = max(0.45, w / 1500)
    for eid, group, name, label, conf, (x1, y1, x2, y2) in boxes:
        col = GROUP_COLORS.get(group, (255, 255, 255))
        hot = bool(highlight and eid in highlight)
        p1, p2 = (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h))
        cv2.rectangle(img, p1, p2, col, max(2, int(w / 300)) + (2 if hot else 0), cv2.LINE_AA)
        text = f"{name}" + (f" {label}" if group != "person" else "") + f" {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
        ty = max(th + 6, p1[1])
        cv2.rectangle(img, (p1[0], ty - th - 6), (p1[0] + tw + 6, ty + 1), col, -1)
        cv2.putText(img, text, (p1[0] + 3, ty - 3), cv2.FONT_HERSHEY_SIMPLEX, scale, (20, 20, 20), 1, cv2.LINE_AA)
    if stamp:
        cv2.rectangle(img, (0, h - int(26 * scale) - 8), (int(len(stamp) * 11 * scale) + 12, h), (30, 30, 30), -1)
        cv2.putText(img, stamp, (6, h - 8), cv2.FONT_HERSHEY_SIMPLEX, scale * 0.9, (255, 255, 255), 1, cv2.LINE_AA)
    if w > MAX_WIDTH:
        img = cv2.resize(img, (MAX_WIDTH, int(h * MAX_WIDTH / w)), interpolation=cv2.INTER_AREA)
    return img


def render_crop(frame, box, pad: float = 0.12, size: int = 200) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = (x2 - x1), (y2 - y1)
    xa, xb = int(max(0, (x1 - pad * bw)) * w), int(min(1, (x2 + pad * bw)) * w)
    ya, yb = int(max(0, (y1 - pad * bh)) * h), int(min(1, (y2 + pad * bh)) * h)
    crop = frame[ya:max(yb, ya + 1), xa:max(xb, xa + 1)]
    ch, cw = crop.shape[:2]
    f = size / max(ch, cw)
    return cv2.resize(crop, (max(1, int(cw * f)), max(1, int(ch * f))), interpolation=cv2.INTER_AREA)
