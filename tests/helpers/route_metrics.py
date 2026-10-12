"""The numbers behind acceptance checks A1 to A8 (spec section 3), from a layout and nothing else.

A layout here is any object with ``nodes`` (id to a box with ``x``, ``y``, ``width``, ``height``),
``routes`` (key to points), ``labels``, ``width`` and ``height``. This module does not import vsdxkit.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping
from itertools import combinations, pairwise
from typing import Any

EPS = 1e-6
Point = tuple[float, float]
Key = tuple[str, str, int]


def simplified(route: tuple[Point, ...]) -> list[Point]:
    """`route` without repeated points and without points in the middle of a straight run."""
    pts: list[Point] = []
    for p in route:
        if not pts or abs(p[0] - pts[-1][0]) > EPS or abs(p[1] - pts[-1][1]) > EPS:
            pts.append(p)
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        same_x = abs(a[0] - b[0]) < EPS and abs(b[0] - c[0]) < EPS
        same_y = abs(a[1] - b[1]) < EPS and abs(b[1] - c[1]) < EPS
        if not (same_x or same_y):
            out.append(b)
    out.append(pts[-1])
    return out


def bends(route: tuple[Point, ...]) -> int:
    """How many times `route` turns."""
    return max(len(simplified(route)) - 2, 0)


def _horizontal(seg: tuple[Point, Point]) -> bool:
    return abs(seg[0][1] - seg[1][1]) < EPS


def _crosses(a: tuple[Point, Point], b: tuple[Point, Point]) -> bool:
    """Whether two segments cross at a point interior to both."""
    if _horizontal(a) == _horizontal(b):
        return False
    h, v = (a, b) if _horizontal(a) else (b, a)
    lo, hi = sorted((h[0][0], h[1][0]))
    vlo, vhi = sorted((v[0][1], v[1][1]))
    return lo + EPS < v[0][0] < hi - EPS and vlo + EPS < h[0][1] < vhi - EPS


def crossings(layout: Any) -> int:
    """How many pairs of route segments cross (A4)."""
    routes = [simplified(layout.routes[k]) for k in sorted(layout.routes)]
    return sum(_crosses(s, t) for r, q in combinations(routes, 2) for s in pairwise(r) for t in pairwise(q))


def shared_runs(layout: Any, together: Collection[Key] = frozenset()) -> list[tuple[Key, Key]]:
    """Pairs of routes that run along one line for a positive length (A3); two routes both in `together` are exempt."""
    found = []
    for k1, k2 in combinations(sorted(layout.routes), 2):
        if k1 in together and k2 in together:
            continue
        for s in pairwise(simplified(layout.routes[k1])):
            for t in pairwise(simplified(layout.routes[k2])):
                if _horizontal(s) != _horizontal(t):
                    continue
                axis = 1 if _horizontal(s) else 0
                span = 0 if _horizontal(s) else 1
                if abs(s[0][axis] - t[0][axis]) > EPS:
                    continue
                lo = max(min(s[0][span], s[1][span]), min(t[0][span], t[1][span]))
                hi = min(max(s[0][span], s[1][span]), max(t[0][span], t[1][span]))
                if hi - lo > EPS:
                    found.append((k1, k2))
    return sorted(set(found))


def _side(box: Any, p: Point) -> str | None:
    """The side of `box` that `p` lies on, checked left, right, bottom, top; a corner belongs to the first match."""
    left, right = box.x - box.width / 2, box.x + box.width / 2
    bottom, top = box.y - box.height / 2, box.y + box.height / 2
    inside_y, inside_x = bottom - EPS <= p[1] <= top + EPS, left - EPS <= p[0] <= right + EPS
    for name, hit in (
        ("left", abs(p[0] - left) < EPS and inside_y),
        ("right", abs(p[0] - right) < EPS and inside_y),
        ("bottom", abs(p[1] - bottom) < EPS and inside_x),
        ("top", abs(p[1] - top) < EPS and inside_x),
    ):
        if hit:
            return name
    return None


def side_ends(layout: Any) -> dict[tuple[str, str], list[tuple[float, float, Key]]]:
    """Per (node, side), each edge end there as (coordinate along the side, coordinate of the far end, key). Self-loops are left out."""
    out: dict[tuple[str, str], list[tuple[float, float, Key]]] = {}
    for key in sorted(layout.routes):
        route = layout.routes[key]
        if key[0] == key[1] or len(route) < 2:
            continue
        for node_id, near, far in ((key[0], route[0], route[-1]), (key[1], route[-1], route[0])):
            side = _side(layout.nodes[node_id], near)
            if side is None:
                continue
            pair = (near[1], far[1]) if side in ("left", "right") else (near[0], far[0])
            out.setdefault((node_id, side), []).append((*pair, key))
    return out


def required_pitch(extent: float, count: int, pitch: float = 0.2) -> float:
    """A1: the least gap between ports on a side of length `extent` that holds `count` of them."""
    return max(0.1, min(pitch, extent / (count + 1)))


def port_gap_violations(layout: Any, pitch: float = 0.2, exempt: Collection[Key] = frozenset()) -> list[str]:
    """A1: one line for each side whose ports are closer than the required pitch; ends of `exempt` routes are skipped."""
    bad = []
    for (node, side), items in sorted(side_ends(layout).items()):
        items = [i for i in items if i[2] not in exempt]
        if len(items) < 2:
            continue
        box = layout.nodes[node]
        extent = box.height if side in ("left", "right") else box.width
        coords = sorted(c for c, _f, _k in items)
        gap = min(b - a for a, b in pairwise(coords))
        need = required_pitch(extent, len(items), pitch)
        if gap < need - EPS:
            bad.append(f"{node} {side}: ports {gap:.2f} apart, need {need:.2f}")
    return bad


def port_order_violations(layout: Any) -> list[str]:
    """A2: one line for each side whose ports, in order along it, do not have their far ends in the same order."""
    bad = []
    for (node, side), items in sorted(side_ends(layout).items()):
        fars = [f for _c, f, _k in sorted(items)]
        if any(b < a - EPS for a, b in pairwise(fars)):
            bad.append(f"{node} {side}: ports are out of order against their far ends")
    return bad


def aspect(layout: Any) -> float:
    """The page's width over its height (A8)."""
    return layout.width / layout.height


def layout_digest(layouts: Mapping[str, Any]) -> str:
    """A sha256 over the boxes, routes, labels and size of each named layout, every float to two decimals."""

    def f(v: float) -> str:
        return f"{v + 0.0:.2f}".replace("-0.00", "0.00")

    def b(box: Any) -> list[str]:
        return [f(box.x), f(box.y), f(box.width), f(box.height)]

    record = {
        name: {
            "size": [f(lay.width), f(lay.height)],
            "nodes": {k: b(v) for k, v in lay.nodes.items()},
            "routes": {"|".join(map(str, k)): [[f(x), f(y)] for x, y in r] for k, r in sorted(lay.routes.items())},
            "labels": {"|".join(map(str, k)): b(v) for k, v in sorted(lay.labels.items())},
        }
        for name, lay in sorted(layouts.items())
    }
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
