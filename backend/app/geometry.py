"""Tiny planar-geometry helpers (all coordinates normalised 0-1)."""
from __future__ import annotations

Point = tuple[float, float]


def cross(o: Point, a: Point, b: Point) -> float:
    """z-component of (a-o) x (b-o)."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def side(p: Point, a: Point, b: Point) -> float:
    """Signed side of point p relative to the directed line a->b (0 = on the line)."""
    return cross(a, b, p)


def point_in_polygon(p: Point, poly: list[Point]) -> bool:
    """Ray-casting point-in-polygon test."""
    x, y = p
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def crosses_line(p0: Point, p1: Point, a: Point, b: Point) -> bool:
    """True if the movement p0->p1 strictly crosses the finite segment a-b."""
    s0, s1 = side(p0, a, b), side(p1, a, b)
    if s0 * s1 >= 0:  # same side, or touching the line without passing through
        return False
    sa, sb = cross(p0, p1, a), cross(p0, p1, b)
    return sa * sb <= 0  # segment endpoints straddle the motion path
