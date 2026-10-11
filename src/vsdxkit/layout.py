"""Layered layout of a flow graph on a fixed grid, with lanes, groups and orthogonal routes.

Pure functions over tuples: nothing here touches a document, a clock, a random
source or a hash-ordered container, so the same arguments give the same boxes
and routes on every platform. Ties are broken by the order of the arguments.
"""

from __future__ import annotations

import heapq
import math
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from vsdxkit.errors import GraphError

_Key = str | tuple[int, int]
"""A slot's key: a node's id, or (edge number, layer) for a dummy, which no string id can equal."""

GRID = 0.01
"""Every coordinate is a multiple of this many inches, so number formatting cannot differ between platforms."""


def snap(value: float) -> float:
    """Round `value` to the grid, as a float that prints the same everywhere."""
    return round(round(value / GRID) * GRID, max(0, -math.floor(math.log10(GRID))))


def _ceil(value: float) -> float:
    """Round `value` up to the grid, so an extent never shrinks when it is snapped."""
    return snap(math.ceil(value / GRID - 1e-9) * GRID)


def _even(value: float) -> float:
    """Round `value` up to an even number of grid steps, so a snapped centre keeps both borders on the grid."""
    return snap(math.ceil(value / (2 * GRID) - 1e-9) * 2 * GRID)


def _spread(count: int, extent: float, node: object) -> list[float]:
    """Offsets, in inches on the grid and about zero, that keep `count` parallel routes apart inside `extent`.

    :raises GraphError: when `extent` has fewer grid steps than `count`, so two routes would coincide
    """
    step = min(10, round(extent / GRID) // count)
    if step == 0:
        raise GraphError(f"node {node!r} is too small for {count} parallel edges; each needs a grid step of its border")
    start = -((count - 1) * step // 2)
    return [snap((start + i * step) * GRID) for i in range(count)]


@dataclass(frozen=True)
class LayoutNode:
    """One box to place."""

    id: str
    """The caller's id for the box."""
    width: float
    """Width in inches."""
    height: float
    """Height in inches."""
    lane: str | None = None
    """The id of the lane the box belongs to, or None when the layout has no lanes."""
    group: str | None = None
    """The id of the innermost group the box belongs to, or None."""


@dataclass(frozen=True)
class LayoutOptions:
    """How a layout is spaced and which way it flows."""

    direction: Literal["left_to_right", "top_down"] = "left_to_right"
    """The way the flow runs. Lanes need ``left_to_right``."""
    layer_gap: float = 1.0
    """Inches between one layer's column and the next, where edges run. The default widens for a gap crossed by many edges; a smaller value of your own that cannot hold them is refused."""
    node_gap: float = 0.4
    """Inches between boxes in the same layer."""
    margin: float = 0.5
    """Inches left clear round the whole drawing."""
    group_padding: float = 0.25
    """Inches a group's box extends past its members."""
    lane_padding: float = 0.3
    """Inches above and below the boxes in a lane, raised to hold the padding of a group box that reaches the lane's edge."""
    lane_heading: float = 0.6
    """Inches left of the first layer for lane labels, when there are lanes."""
    sweeps: int = 8
    """How many up-and-down passes order the boxes within their layers."""
    parents: tuple[tuple[str, str], ...] = ()
    """Pairs of (child group id, parent group id): groups nest one level."""


@dataclass(frozen=True)
class Box:
    """A rectangle by its centre, in inches from the page's bottom-left corner."""

    x: float
    """Centre, across."""
    y: float
    """Centre, up."""
    width: float
    """Width in inches."""
    height: float
    """Height in inches."""


@dataclass(frozen=True)
class Layout:
    """Where everything goes."""

    nodes: dict[str, Box]
    """Each node's box, in the order the nodes were given."""
    groups: dict[str, Box]
    """Each group with members: the box round them and their padding."""
    lanes: dict[str, Box]
    """Each lane's band, the full width of the drawing."""
    routes: dict[tuple[str, str, int], tuple[tuple[float, float], ...]]
    """Each edge's bends, both ends included, by (source, target, n) where n counts parallel edges from 0."""
    width: float
    """Page width in inches."""
    height: float
    """Page height in inches."""


_Rect = tuple[float, float, float, float]
"""A rectangle as (low along the flow, high along the flow, low across it, high across it)."""


@dataclass
class _Slot:
    """A place in a layer: a real node, or a dummy an edge passes through."""

    layer: int
    """The layer's index along the flow."""
    u_extent: float
    """Size along the flow."""
    v_extent: float
    """Size across the flow."""
    lane: int
    """Index of the lane band."""
    track: tuple[int, int]
    """The group track inside the lane: (0, 0) is outside every group."""
    real: bool
    """Whether this is a node and not a dummy."""
    v: float = 0.0
    """Centre across the flow, once placed."""


def _break_cycles(ids: list[str], edges: list[tuple[str, str]]) -> list[bool]:
    """Per edge, whether a depth-first walk in input order finds it closing a cycle; those are laid out reversed."""
    out: dict[str, list[int]] = {i: [] for i in ids}
    for n, (source, _target) in enumerate(edges):
        out[source].append(n)
    state: dict[str, int] = {}
    flipped = [False] * len(edges)
    for root in ids:
        if root in state:
            continue
        state[root] = 1
        stack = [(root, iter(out[root]))]
        while stack:
            node, remaining = stack[-1]
            for n in remaining:
                target = edges[n][1]
                if target == node:
                    continue
                if state.get(target) == 1:
                    flipped[n] = True
                elif target not in state:
                    state[target] = 1
                    stack.append((target, iter(out[target])))
                    break
            else:
                state[node] = 2
                stack.pop()
    return flipped


def _layers(ids: list[str], edges: list[tuple[str, str]], flipped: list[bool]) -> dict[str, int]:
    """The longest-path layer of each node over the edges that remain once cycles are broken."""
    preds: dict[str, list[str]] = {i: [] for i in ids}
    for (source, target), flip in zip(edges, flipped, strict=True):
        if source != target:
            preds[source if flip else target].append(target if flip else source)
    layer: dict[str, int] = {}
    for root in ids:
        stack = [root]
        while stack:
            node = stack[-1]
            if node in layer:
                stack.pop()
                continue
            pending = [p for p in preds[node] if p not in layer]
            if pending:
                stack.extend(pending)
            else:
                layer[node] = 1 + max((layer[p] for p in preds[node]), default=-1)
                stack.pop()
    return layer


def _order(rows: list[list[_Key]], slots: dict[_Key, _Slot], chains: list[list[_Key]], sweeps: int) -> None:
    """Order each layer's keys by barycentre sweeps; lane and track come first, so a stable sort keeps input order on ties."""
    up: dict[_Key, list[_Key]] = {k: [] for k in slots}
    down: dict[_Key, list[_Key]] = {k: [] for k in slots}
    for chain in chains:
        for a, b in pairwise(chain):
            down[a].append(b)
            up[b].append(a)
    position = {k: float(i) for row in rows for i, k in enumerate(row)}

    def sweep(layer: int, near: dict[_Key, list[_Key]]) -> None:
        """Re-sort one layer by the mean position of each key's neighbours on the `near` side."""
        row = rows[layer]
        mean = {k: sum(position[p] for p in near[k]) / len(near[k]) for k in row if near[k]}
        row.sort(key=lambda k: (slots[k].lane, slots[k].track, mean.get(k, position[k])))
        position.update({k: float(i) for i, k in enumerate(row)})

    for _ in range(sweeps):
        for layer in range(1, len(rows)):
            sweep(layer, up)
        for layer in range(len(rows) - 2, -1, -1):
            sweep(layer, down)


def _blocks(a: tuple[float, float], b: tuple[float, float], rect: _Rect) -> bool:
    """Whether the axis-parallel segment a-b enters `rect` or runs along its border."""
    if a[0] == b[0]:
        return rect[0] - _EPS <= a[0] <= rect[1] + _EPS and max(min(a[1], b[1]), rect[2] + _EPS) < min(
            max(a[1], b[1]), rect[3] - _EPS
        )
    return rect[2] - _EPS <= a[1] <= rect[3] + _EPS and max(min(a[0], b[0]), rect[0] + _EPS) < min(
        max(a[0], b[0]), rect[1] - _EPS
    )


def _simplify(path: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """`path` without repeated points or points in the middle of a straight run."""
    pts = [path[0]]
    for p in path[1:]:
        if p != pts[-1]:
            pts.append(p)
    kept = [pts[0]]
    for a, b, c in zip(pts, pts[1:], pts[2:], strict=False):
        if not (a[0] == b[0] == c[0] or a[1] == b[1] == c[1]):
            kept.append(b)
    kept.append(pts[-1])
    return kept


def _runs(
    paths: list[list[tuple[float, float]]], skip: int = -1
) -> dict[tuple[int, float], list[tuple[float, float, int, int]]]:
    """Every segment of every path but `skip`, by line: (low, high, path, segment) under (axis, coordinate)."""
    lines: dict[tuple[int, float], list[tuple[float, float, int, int]]] = {}
    for n, pts in enumerate(paths):
        if n == skip:
            continue
        for i, (a, b) in enumerate(pairwise(pts)):
            if a[1] == b[1]:
                lines.setdefault((0, round(a[1], 4)), []).append((min(a[0], b[0]), max(a[0], b[0]), n, i))
            else:
                lines.setdefault((1, round(a[0], 4)), []).append((min(a[1], b[1]), max(a[1], b[1]), n, i))
    return lines


def _apart(
    paths: list[list[tuple[float, float]]],
    ends: list[set[tuple[float, float]]],
    fits: Callable[[int, list[tuple[float, float]]], bool],
    name: Callable[[int], tuple[str, str]],
    reroute: Callable[[int], list[tuple[float, float]] | None],
) -> None:
    """Move segments aside, one grid step at a time, until no two paths run along one line, or raise GraphError.

    Two paths may overlap where they share an end point. A path that is moved is the later one, and only a segment
    that is neither its first nor its last, so its ends stay on their borders; `fits` says whether a moved path is
    still legal. A pair that `_SEPARATIONS` steps either way cannot part is refused.
    """
    for _round in range(_REROUTES):
        # every route that runs along another is searched again, now that the routes after it are known
        for n in range(len(paths)):
            if name(n)[0] == name(n)[1]:
                continue
            rest = _runs(paths, skip=n)
            now = _clashes(paths[n], n, rest, ends)
            if now:
                again = reroute(n)
                if again is not None and fits(n, again) and _clashes(again, n, rest, ends) < now:
                    paths[n] = again
    for _ in range(8 * len(paths) + 8):
        lines = _runs(paths)
        clash = None
        for key in sorted(lines):
            runs = sorted(lines[key])
            for x, (_lo, hi, n, i) in enumerate(runs):
                for lo2, hi2, m, j in runs[x + 1 :]:
                    if lo2 >= hi - _EPS:
                        break
                    if m != n and not ends[n] & ends[m] and min(hi, hi2) - lo2 > _EPS:
                        clash = (n, i, m, j)
                        break
                if clash:
                    break
            if clash:
                break
        if clash is None:
            return
        n, i, m, j = clash
        for who, seg in sorted(((n, i), (m, j)), reverse=True):
            pts = paths[who]
            if name(who)[0] == name(who)[1] or not 1 <= seg <= len(pts) - 3:
                continue
            others = _runs(paths, skip=who)
            before = _clashes(pts, who, others, ends)
            for step in range(1, _SEPARATIONS + 1):
                moved = None
                for sign in (1, -1):
                    moved = _shifted(pts, seg, sign * step * GRID)
                    if moved is not None and fits(who, moved) and _clashes(moved, who, others, ends) < before:
                        break
                    moved = None
                if moved is not None:
                    paths[who] = moved
                    break
            else:
                continue
            break
        else:
            # no segment will move aside, so search for a whole new route for one of the pair
            for who in (m, n) if m > n else (n, m):
                if name(who)[0] == name(who)[1]:
                    continue
                again = reroute(who)
                rest = _runs(paths, skip=who)
                if (
                    again is not None
                    and fits(who, again)
                    and _clashes(again, who, rest, ends) < _clashes(paths[who], who, rest, ends)
                ):
                    paths[who] = again
                    break
            else:
                a, b = name(n), name(m)
                raise GraphError(f"edge {a[0]!r} -> {a[1]!r} and edge {b[0]!r} -> {b[1]!r} cannot be kept apart")
    raise GraphError("the routes cannot be kept apart")


def _shifted(pts: list[tuple[float, float]], seg: int, delta: float) -> list[tuple[float, float]] | None:
    """`pts` with segment `seg` moved across itself by `delta`, or None if a neighbouring segment would vanish or flip."""
    a, b = pts[seg], pts[seg + 1]
    axis = 1 if a[1] == b[1] else 0
    moved = list(pts)
    for k in (seg, seg + 1):
        p = list(pts[k])
        p[axis] = snap(p[axis] + delta)
        moved[k] = (p[0], p[1])
    for k in (seg - 1, seg + 1):
        before, after = pts[k], pts[k + 1]
        new_before, new_after = moved[k], moved[k + 1]
        if (new_after[axis] - new_before[axis]) * (after[axis] - before[axis]) <= 0:
            return None
    return moved


def _clashes(
    pts: list[tuple[float, float]],
    who: int,
    lines: dict[tuple[int, float], list[tuple[float, float, int, int]]],
    ends: list[set[tuple[float, float]]],
) -> int:
    """How many segments of `pts` run along a segment of another path that does not share an end point."""
    count = 0
    for a, b in pairwise(pts):
        key = (0, round(a[1], 4)) if a[1] == b[1] else (1, round(a[0], 4))
        low, high = (min(a[0], b[0]), max(a[0], b[0])) if key[0] == 0 else (min(a[1], b[1]), max(a[1], b[1]))
        count += sum(
            1
            for lo, hi, m, _j in lines.get(key, ())
            if m != who and min(high, hi) - max(low, lo) > _EPS and not (ends[who] & ends[m])
        )
    return count


def _enters(a: tuple[float, float], b: tuple[float, float], rect: _Rect) -> bool:
    """Whether the axis-parallel segment a-b passes through the open inside of `rect`."""
    left, right, bottom, top = rect[0] + _EPS, rect[1] - _EPS, rect[2] + _EPS, rect[3] - _EPS
    if a[0] == b[0]:
        return left < a[0] < right and max(min(a[1], b[1]), bottom) < min(max(a[1], b[1]), top)
    return bottom < a[1] < top and max(min(a[0], b[0]), left) < min(max(a[0], b[0]), right)


_NUDGES = (0.03, -0.03, 0.07, -0.07, 0.09, -0.09)
"""Inches a dummy's row may move off its centre; none is zero, and the largest stays inside the dummy's 0.2 in slot."""

_CORRIDOR = 0.5
"""Inches of clear space kept round a group box, so a route has somewhere to go round it."""

_LANE_STEP = 0.02
"""Inches between the neighbouring lines a detour may use along one gap or corridor, so detours can run side by side."""

_WORK_CAP = 12_000_000
"""Search steps one layout may spend routing round groups and parting routes, so a very crowded one fails instead of running on."""

_REROUTES = 2
"""How many times every route that runs along another is searched again, before single segments are moved aside."""

_SEPARATIONS = 12
"""How many grid steps, either way, a segment may move to part from another route before the layout is refused."""

_NEAR = 2.0
"""Inches round an edge's end points within which a detour first looks for lines to turn on."""

_HURRY = 2.0
"""How much the distance still to go outweighs the distance so far; above 1 the search is faster and the path a little longer."""

_EPS = 1e-6
"""Tolerance, in inches, for a line that lies on a border: it is not inside."""

_SHARING = 1000.0
"""Extra cost per inch of a detour that runs along another route, so a free line is preferred to a shared one."""

_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
"""Unit steps along the flow, against it, across it and back, indexed as a heading."""


def _heading(a: tuple[float, float], b: tuple[float, float]) -> int:
    """The index into _STEPS of the direction from a to b."""
    return 0 if b[0] > a[0] else 1 if b[0] < a[0] else 2 if b[1] > a[1] else 3


def _enters(a: tuple[float, float], b: tuple[float, float], rect: _Rect) -> bool:
    """Whether the axis-parallel segment a-b passes through the open inside of `rect`."""
    left, right, bottom, top = rect[0] + _EPS, rect[1] - _EPS, rect[2] + _EPS, rect[3] - _EPS
    if a[0] == b[0]:
        return left < a[0] < right and max(min(a[1], b[1]), bottom) < min(max(a[1], b[1]), top)
    return bottom < a[1] < top and max(min(a[0], b[0]), left) < min(max(a[0], b[0]), right)


_NUDGES = (0.03, -0.03, 0.07, -0.07, 0.09, -0.09)
"""Inches a dummy's row may move off its centre; none is zero, and the largest stays inside the dummy's 0.2 in slot."""

_CORRIDOR = 0.5
"""Inches of clear space kept round a group box, so a route has somewhere to go round it."""

_LANE_STEP = 0.02
"""Inches between the neighbouring lines a detour may use along one gap or corridor, so detours can run side by side."""

_RETRY_BUDGET = 1_000_000
"""Search steps after which a layout stops looking for a quieter line for a detour that runs along another route."""

_NEAR = 2.0
"""Inches round an edge's end points within which a detour first looks for lines to turn on."""

_HURRY = 2.0
"""How much the distance still to go outweighs the distance so far; above 1 the search is faster and the path a little longer."""

_EPS = 1e-6
"""Tolerance, in inches, for a line that lies on a border: it is not inside."""

_SHARING = 1000.0
"""Extra cost per inch of a detour that runs along another route, so a free line is preferred to a shared one."""

_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
"""Unit steps along the flow, against it, across it and back, indexed as a heading."""


def _heading(a: tuple[float, float], b: tuple[float, float]) -> int:
    """The index into _STEPS of the direction from a to b."""
    return 0 if b[0] > a[0] else 1 if b[0] < a[0] else 2 if b[1] > a[1] else 3


def _shared(
    path: list[tuple[float, float]], occupied: dict[tuple[int, float], list[tuple[float, float]]]
) -> set[tuple[int, float]]:
    """The lines (axis, coordinate) along which `path` runs over other routes, not counting its first and last segments."""
    pts = [path[0]]
    for a, b in pairwise(path):
        if a != b:
            pts.append(b)
    lines = set()
    for a, b in list(pairwise(pts))[1:-1]:
        horizontal = a[1] == b[1]
        low, high = (min(a[0], b[0]), max(a[0], b[0])) if horizontal else (min(a[1], b[1]), max(a[1], b[1]))
        key = (0, round(a[1], 4)) if horizontal else (1, round(a[0], 4))
        if any(min(high, h) > max(low, lo) for lo, h in occupied.get(key, ())):
            lines.add(key)
    return lines


def _detour(
    path: list[tuple[float, float]],
    xs: set[float],
    ys: set[float],
    solid: list[_Rect],
    occupied: dict[tuple[int, float], list[tuple[float, float]]],
    work: list[int],
) -> list[tuple[float, float]] | None:
    """The shortest few-bend orthogonal path from `path`'s first point to its last that avoids `solid`, or None.

    It leaves in the direction `path` does and arrives in the direction `path` does, and turns only on the lines
    `xs` and `ys`. Ties break by insertion order, so the result depends on the arguments alone.
    """
    start, end = path[0], path[-1]
    first, last = _heading(path[0], path[1]), _heading(path[-2], path[-1])
    # lines just off both ends, so a detour can turn before it meets a route that leaves or arrives close by
    for k in range(1, 5):
        for point, heading, sign in ((start, first, 1), (end, last, -1)):
            dx, dy = _STEPS[heading]
            if dx:
                xs = xs | {point[0] + sign * dx * k * _LANE_STEP}
            else:
                ys = ys | {point[1] + sign * dy * k * _LANE_STEP}
    gx, gy = sorted(xs | {start[0], end[0]}), sorted(ys | {start[1], end[1]})
    # a line on a box's border is blocked too, so no route runs along the edge of a box
    rows = [[(r[0] + _EPS, r[1] - _EPS) for r in solid if r[2] - _EPS <= y <= r[3] + _EPS] for y in gy]
    cols = [[(r[2] + _EPS, r[3] - _EPS) for r in solid if r[0] - _EPS <= x <= r[1] + _EPS] for x in gx]

    def spans(lines: list[float], blocking: list[list[tuple[float, float]]]) -> list[bytearray]:
        """Per line, a flag for each gap between neighbouring lines saying whether a box blocks it."""
        flags = []
        for intervals in blocking:
            row = bytearray(len(lines) - 1)
            for a, b in intervals:
                for k in range(max(bisect_right(lines, a) - 1, 0), min(bisect_left(lines, b), len(row))):
                    row[k] = 1
            flags.append(row)
        return flags

    blocked_h, blocked_v = spans(gx, rows), spans(gy, cols)

    def free(i: int, j: int, d: int) -> tuple[int, int] | None:
        """The next grid point from (i, j) heading d, or None when off the grid or blocked."""
        ni, nj = i + _STEPS[d][0], j + _STEPS[d][1]
        if not (0 <= ni < len(gx) and 0 <= nj < len(gy)):
            return None
        if d < 2:
            return None if blocked_h[j][min(i, ni)] else (ni, nj)
        return None if blocked_v[i][min(j, nj)] else (ni, nj)

    i0, j0 = gx.index(start[0]), gy.index(start[1])
    goal = (gx.index(end[0]), gy.index(end[1]))
    hop = free(i0, j0, first)
    if hop is None:
        return None

    def covered(axis: int, coord: float) -> Callable[[float], float]:
        """A function giving how much of one line, up to a position, earlier routes cover."""
        joined: list[tuple[float, float]] = []
        for lo, hi in sorted(occupied.get((axis, round(coord, 4)), ())):
            if joined and lo <= joined[-1][1]:
                joined[-1] = (joined[-1][0], max(joined[-1][1], hi))
            else:
                joined.append((lo, hi))
        starts = [lo for lo, _hi in joined]
        before = [0.0]
        for lo, hi in joined:
            before.append(before[-1] + hi - lo)

        def up_to(x: float) -> float:
            """The length of the line below `x` that is covered."""
            i = bisect_right(starts, x)
            return 0.0 if i == 0 else before[i - 1] + min(x, joined[i - 1][1]) - joined[i - 1][0]

        return up_to

    along_x = [covered(0, y) for y in gy]
    along_y = [covered(1, x) for x in gx]

    def cost(i: int, j: int, ni: int, nj: int) -> float:
        """The length of the step from (i, j) to (ni, nj), dearer where an earlier route already runs."""
        low, high = (gx[i], gx[ni]) if i != ni else (gy[j], gy[nj])
        low, high = min(low, high), max(low, high)
        up_to = along_x[j] if i != ni else along_y[i]
        return high - low + _SHARING * (up_to(high) - up_to(low))

    to_go_x = [abs(x - gx[goal[0]]) for x in gx]
    to_go_y = [abs(y - gy[goal[1]]) for y in gy]
    ny = len(gy)
    bend = 0.5
    # a state is a grid point and the heading it was reached with, packed into one integer
    first_state = (hop[0] * ny + hop[1]) * 4 + first
    best = {first_state: cost(i0, j0, *hop)}
    came: dict[int, int | None] = {first_state: None}
    heap = [(best[first_state] + _HURRY * (to_go_x[hop[0]] + to_go_y[hop[1]]), 0, first_state)]
    count = 0
    steps: dict[int, tuple[float, int, int] | None] = {}
    goal_cell = goal[0] * ny + goal[1]
    while heap:
        _f, _c, state = heapq.heappop(heap)
        work[0] += 1
        if work[0] > _WORK_CAP:
            raise GraphError("the layout is too crowded to route within its search limit")
        cell, d = divmod(state, 4)
        i, j = divmod(cell, ny)
        if cell == goal_cell and d == last:
            points = [(gx[i], gy[j])]
            at: int | None = state
            while at is not None:
                c, _d = divmod(at, 4)
                points.append((gx[c // ny], gy[c % ny]))
                at = came[at]
            points.append(start)
            return points[::-1]
        g0 = best[state]
        if _f - _HURRY * (to_go_x[i] + to_go_y[j]) > g0 + 1e-9:
            continue
        for nd in (d, *((2, 3) if d < 2 else (0, 1))) if cell != goal_cell else (d,):
            key = cell * 4 + nd
            if key in steps:
                hopped = steps[key]
            else:
                nxt = free(i, j, nd)
                hopped = steps[key] = None if nxt is None else (cost(i, j, *nxt), nxt[0], nxt[1])
            if hopped is None:
                continue
            g = g0 + (0.0 if nd == d else bend) + hopped[0]
            new_state = (hopped[1] * ny + hopped[2]) * 4 + nd
            if g < best.get(new_state, math.inf) - 1e-9:
                best[new_state] = g
                came[new_state] = state
                count += 1
                heapq.heappush(heap, (g + _HURRY * (to_go_x[hopped[1]] + to_go_y[hopped[2]]), count, new_state))
    return None


def layered_layout(
    nodes: tuple[LayoutNode, ...],
    edges: tuple[tuple[str, str], ...],
    lanes: tuple[str, ...] = (),
    groups: tuple[str, ...] = (),
    options: LayoutOptions | None = None,
) -> Layout:
    """Place `nodes` in layers along the flow, lanes as bands and groups as boxes, and route every edge.

    An edge that spans layers passes through a dummy slot in each one it crosses, so no route meets a node.

    :param edges: pairs of (source id, target id); a repeat is a parallel edge, a pair of one id a self-loop
    :param lanes: lane ids, top to bottom
    :param groups: every group id; a node names its innermost group
    :raises GraphError: lanes with a top-down direction, an edge naming a missing node, a node in an unknown lane or group
        or without a lane when lanes are declared, a node size that is not finite and positive, a repeated node, lane or
        group id, a layout too crowded to give every route its own line (it stops after a fixed number of search steps,
        and names two edges that could not be parted), an option that is not a finite non-negative number, a layer_gap too small for the edges that cross it,
        a node too small to give each of its parallel edges a grid step of its border, an edge that cannot be routed
        round the groups it does not belong to, a group whose members sit in different lanes, or a parent that is
        undeclared, repeated for one child or nests more than one level
    """
    opts = options if options is not None else LayoutOptions()
    top_down = opts.direction == "top_down"
    for name in ("layer_gap", "node_gap", "margin", "group_padding", "lane_padding", "lane_heading"):
        value = getattr(opts, name)
        if not (isinstance(value, int | float) and math.isfinite(value) and value >= 0):
            raise GraphError(f"option {name} is {value!r}; it must be a finite number of inches, zero or more")
    if not (isinstance(opts.sweeps, int) and opts.sweeps >= 1):
        raise GraphError(f"option sweeps is {opts.sweeps!r}; it must be a whole number, one or more")
    if opts.direction not in ("left_to_right", "top_down"):
        raise GraphError(f"option direction is {opts.direction!r}; it must be 'left_to_right' or 'top_down'")
    if lanes and top_down:
        raise GraphError("lanes need direction='left_to_right'; a top-down layout has no bands to put them in")
    by_id = {n.id: n for n in nodes}
    for source, target in edges:
        if source not in by_id or target not in by_id:
            raise GraphError(f"edge {source!r} -> {target!r} names a node that is not on the page")
    lane_index = {name: i for i, name in enumerate(lanes)}
    group_index = {name: i + 1 for i, name in enumerate(groups)}
    parent_of = dict(opts.parents)
    for i, (child, parent) in enumerate(opts.parents):
        if any(child == earlier for earlier, _ in opts.parents[:i]):
            raise GraphError(f"group {child!r} is listed as a child of more than one parent")
        for name in (child, parent):
            if name not in group_index:
                raise GraphError(f"group {child!r} has parent {parent!r}, and {name!r} is not a declared group")
        if parent in parent_of:
            raise GraphError(
                f"group {child!r} nests in {parent!r}, which nests in {parent_of[parent]!r}; groups nest one level"
            )
    for kind, names in (("node", [n.id for n in nodes]), ("lane", lanes), ("group", groups)):
        for i, name in enumerate(names):
            if name in names[:i]:
                raise GraphError(f"{kind} id {name!r} is repeated")
    for n in nodes:
        if not (math.isfinite(n.width) and math.isfinite(n.height) and n.width > 0 and n.height > 0):
            raise GraphError(f"node {n.id!r} has size {n.width} x {n.height}; both must be finite and positive")
        if n.lane is None and lanes:
            raise GraphError(f"node {n.id!r} has no lane, and the page declares lanes")
        if n.lane is not None and n.lane not in lane_index:
            raise GraphError(f"node {n.id!r} is in lane {n.lane!r}, which the page does not declare")
        if n.group is not None and n.group not in group_index:
            raise GraphError(f"node {n.id!r} is in group {n.group!r}, which the page does not declare")

    members_of: dict[str, list[str]] = {g: [] for g in groups}
    for n in nodes:
        g = n.group
        while g is not None:
            members_of[g].append(n.id)
            g = parent_of.get(g)
    for g, member_ids in members_of.items():
        spanned = sorted({lane for m in member_ids if (lane := by_id[m].lane) is not None}, key=lane_index.__getitem__)
        if len(spanned) > 1:
            raise GraphError(f"group {g!r} has members in lanes {spanned}; its box would cover the lanes between them")

    # snapping moves each centre by up to half a grid step, so packed neighbours keep one step more than asked
    most_loops = max(Counter(source for source, target in edges if source == target).values(), default=0)
    v_gap = max(opts.node_gap, 0.2 + 0.1 * (most_loops - 1) if most_loops else 0.0) + GRID
    u_gap = max(opts.layer_gap, 0.3 + 0.1 * (most_loops - 1) if most_loops else 0.0) + GRID

    ids = [n.id for n in nodes]
    flipped = _break_cycles(ids, list(edges))
    layer_of = _layers(ids, list(edges), flipped)
    n_layers = max(layer_of.values(), default=-1) + 1

    slots: dict[_Key, _Slot] = {}
    for n in nodes:
        parent = parent_of.get(n.group) if n.group is not None else None
        track = (
            (0, 0)
            if n.group is None
            else (group_index[n.group], 0)
            if parent is None
            else (group_index[parent], group_index[n.group])
        )
        u, v = (_even(n.height), _even(n.width)) if top_down else (_even(n.width), _even(n.height))
        slots[n.id] = _Slot(layer_of[n.id], u, v, lane_index[n.lane] if n.lane is not None else 0, track, True)

    chains: list[list[_Key]] = []
    for n, ((source, target), flip) in enumerate(zip(edges, flipped, strict=True)):
        a, b = (target, source) if flip else (source, target)
        chain: list[_Key] = [a]
        if a != b:
            for layer in range(layer_of[a] + 1, layer_of[b]):
                key = (n, layer)
                slots[key] = _Slot(layer, 0.0, 0.2, slots[a].lane, (0, 0), False)
                chain.append(key)
        chain.append(b)
        chains.append(chain)

    rows: list[list[_Key]] = [[] for _ in range(n_layers)]
    for key, slot in slots.items():
        rows[slot.layer].append(key)
    _order(rows, slots, chains, opts.sweeps)

    # every edge crossing a gap needs its own channel, a grid step apart; the default gap widens to hold them
    busiest = max(
        Counter(slots[a].layer for chain in chains if chain[0] != chain[-1] for a, _b in pairwise(chain)).values(), default=0
    )
    if u_gap < (busiest + 1) * GRID:
        if opts.layer_gap != LayoutOptions.layer_gap:
            raise GraphError(
                f"option layer_gap is {opts.layer_gap}; {busiest} edges cross one gap and need at least "
                f"{busiest * GRID:g} inches to keep their channels apart"
            )
        u_gap = (busiest + 1) * GRID
    # channels start beyond the loops on the column, so no loop shares a line with a channel
    loop_count = Counter(source for source, target in edges if source == target)
    loop_zone: dict[int, float] = {}
    for node_id, count in loop_count.items():
        layer = slots[node_id].layer
        loop_zone[layer] = max(loop_zone.get(layer, 0.0), 0.3 + 0.1 * (count - 1) + GRID)
    crossing = Counter(slots[a].layer for chain in chains if chain[0] != chain[-1] for a, _b in pairwise(chain))
    u_gap = max([u_gap, *(loop_zone.get(layer, 0.0) + (crossing[layer] + 1) * GRID for layer in {*crossing, *loop_zone})])

    col_width = [max((slots[k].u_extent for k in row), default=0.0) for row in rows]
    col_left: list[float] = []
    cursor = opts.margin + (opts.lane_heading if lanes else 0.0)
    for w in col_width:
        col_left.append(cursor)
        cursor += w + u_gap
    u_total = cursor - u_gap + opts.margin if rows else 2 * opts.margin

    n_lanes = max(len(lanes), 1)
    # a lane band must contain the padding of the group boxes that touch its edges, and the snapping of their coordinates
    loop_reach = 0.2 + 0.1 * (most_loops - 1) + 2 * GRID if most_loops else 0.0
    lane_pad = max(opts.lane_padding, opts.group_padding * (2 if parent_of else 1) + 2 * GRID, loop_reach) if lanes else 0.0
    track_keys = sorted({(s.lane, s.track) for s in slots.values()})
    track_height: dict[tuple[int, tuple[int, int]], float] = {}
    for key in track_keys:
        best = 0.0
        for row in rows:
            members = [slots[k] for k in row if (slots[k].lane, slots[k].track) == key]
            if members:
                best = max(best, sum(m.v_extent for m in members) + v_gap * (len(members) - 1))
        track_height[key] = best
    track_top: dict[tuple[int, tuple[int, int]], float] = {}
    lane_top: list[float] = []
    lane_bottom: list[float] = []
    cursor = opts.margin
    for lane in range(n_lanes):
        lane_top.append(cursor)
        cursor += lane_pad
        first = True
        for key in (k for k in track_keys if k[0] == lane):
            if not first:
                cursor += v_gap + 4 * opts.group_padding
            first = False
            track_top[key] = cursor
            cursor += track_height[key]
        cursor += lane_pad
        lane_bottom.append(cursor)
    v_total = cursor + opts.margin
    for row in rows:
        runs: dict[tuple[int, tuple[int, int]], list[_Slot]] = {}
        for k in row:
            runs.setdefault((slots[k].lane, slots[k].track), []).append(slots[k])
        for key, members in runs.items():
            used = sum(m.v_extent for m in members) + v_gap * (len(members) - 1)
            at = track_top[key] + (track_height[key] - used) / 2
            for m in members:
                m.v = snap(at + m.v_extent / 2)  # on the grid, so even extents put both borders on it
                at += m.v_extent + v_gap

    def centre_u(slot: _Slot) -> float:
        """The middle of a slot's column, along the flow."""
        return snap(col_left[slot.layer] + col_width[slot.layer] / 2)

    def right_u(slot: _Slot) -> float:
        """Where an edge leaves a slot: its far border, or the column's for a dummy."""
        return centre_u(slot) + (slot.u_extent if slot.real else col_width[slot.layer]) / 2

    def left_u(slot: _Slot) -> float:
        """Where an edge arrives at a slot: its near border, or the column's for a dummy."""
        return centre_u(slot) - (slot.u_extent if slot.real else col_width[slot.layer]) / 2

    def rect_of(node_id: str) -> _Rect:
        """A node's rectangle as (u low, u high, v low, v high)."""
        s = slots[node_id]
        return (left_u(s), right_u(s), s.v - s.v_extent / 2, s.v + s.v_extent / 2)

    def pad_of(g: str) -> float:
        """The padding of a group's box: a parent clears its children's boxes too."""
        return opts.group_padding * (2 if g in parent_of.values() else 1)

    # a group box holds its members, their padding and the loops on them
    group_rect: dict[str, _Rect] = {}
    for g, member_ids in members_of.items():
        rects = []
        for m in member_ids:
            lo_a, hi_a, lo_b, hi_b = rect_of(m)
            pad = pad_of(g)
            rects.append((lo_a - pad, hi_a + pad, lo_b - pad, hi_b + pad))
            if m in loop_count:
                extra = 0.1 * (loop_count[m] - 1)
                rects.append((lo_a, hi_a + 0.3 + extra + GRID, lo_b - 0.2 - extra - GRID, hi_b))
        if rects:
            group_rect[g] = (
                min(r[0] for r in rects),
                max(r[1] for r in rects),
                min(r[2] for r in rects),
                max(r[3] for r in rects),
            )

    # a group box can reach past the margin, so the page grows and shifts to hold it, plus a step for snapping
    lo_u = lo_v = 0.0
    hi_u, hi_v = u_total, v_total
    room = max(opts.margin, _CORRIDOR) + GRID  # clear space round a group, where a route can pass it
    for r in group_rect.values():
        lo_u, hi_u = min(lo_u, r[0] - room), max(hi_u, r[1] + room)
        lo_v, hi_v = min(lo_v, r[2] - room), max(hi_v, r[3] + room)
    for node_id, count in loop_count.items():
        lo_a, hi_a, lo_b, _hi_b = rect_of(node_id)
        extra = 0.1 * (count - 1)
        lo_v, hi_u = min(lo_v, lo_b - 0.2 - extra - GRID), max(hi_u, hi_a + 0.3 + extra + GRID)
    shift_u, shift_v = _ceil(-lo_u), _ceil(-lo_v)
    u_total, v_total = _ceil(hi_u + shift_u), _ceil(hi_v + shift_v)

    def page(u: float, v: float) -> tuple[float, float]:
        """Map a point from (along the flow, across it) to page inches."""
        u, v = u + shift_u, v + shift_v
        return (snap(v), snap(u_total - u)) if top_down else (snap(u), snap(v_total - v))

    boxes = {
        n.id: Box(
            *page(centre_u(slots[n.id]), slots[n.id].v),
            *((slots[n.id].v_extent, slots[n.id].u_extent) if top_down else (slots[n.id].u_extent, slots[n.id].v_extent)),
        )
        for n in nodes
    }

    twins = Counter((c[0], c[-1]) for c in chains)
    twin_seen: Counter[tuple[_Key, _Key]] = Counter()
    twin_rank: list[int] = []
    rows_of: list[list[float]] = []
    for chain, (source, target) in zip(chains, edges, strict=True):
        ends = (chain[0], chain[-1])
        twin_rank.append(twin_seen[ends])
        twin_seen[ends] += 1
        # a pass-through row is nudged within its dummy slot, so it rarely lies on the row of a box another edge uses
        nudge = _NUDGES[len(rows_of) % len(_NUDGES)]
        vs = [slots[k].v if slots[k].real else slots[k].v + nudge for k in chain]
        if source != target:
            # parallel edges leave and arrive at different points along the border so they never overlay
            narrow = min((source, target), key=lambda k: slots[k].v_extent)
            off = _spread(twins[ends], slots[narrow].v_extent, narrow)[twin_rank[-1]]
            vs[0] += off
            vs[-1] += off
        rows_of.append(vs)

    gap_edges: dict[int, list[tuple[float, float, int, int]]] = {}
    for n, chain in enumerate(chains):
        if chain[0] == chain[-1]:
            continue  # a loop has no channel
        for hop, (a, b) in enumerate(pairwise(chain)):
            gap_edges.setdefault(slots[a].layer, []).append((min(slots[a].v, slots[b].v), max(slots[a].v, slots[b].v), n, hop))
    channel: dict[tuple[int, int], float] = {}

    def room_for(n: int, i: int, new: float) -> bool:
        """Whether row `i` of edge `n` can move to `new` and still sit on its box or inside its dummy."""
        slot = slots[chains[n][i]]
        return abs(new - slot.v) <= slot.v_extent / 2 - GRID

    for _round in range(6):
        stuck: list[tuple[int, int, int, int]] = []
        channel.clear()
        for layer, items in gap_edges.items():
            items.sort()
            # an edge that arrives on the row another leaves on must have its channel right of that edge's, or their runs overlap
            starts: dict[float, list[int]] = {}
            for idx, (_lo, _hi, n, hop) in enumerate(items):
                starts.setdefault(round(rows_of[n][hop], 6), []).append(idx)
            need = [
                [f for f in starts.get(round(rows_of[n][hop + 1], 6), []) if f != idx]
                for idx, (_lo, _hi, n, hop) in enumerate(items)
            ]
            before = [list(preds) for preds in need]
            after: list[list[int]] = [[] for _ in items]
            for idx, preds in enumerate(before):
                for f in preds:
                    after[f].append(idx)
            ready = [idx for idx, preds in enumerate(before) if not preds]
            heapq.heapify(ready)
            order: list[int] = []
            left_over = set(range(len(items)))
            while left_over:
                idx = heapq.heappop(ready) if ready else min(left_over)
                if idx not in left_over:
                    continue
                left_over.discard(idx)
                order.append(idx)
                for nxt in after[idx]:
                    before[nxt] = [f for f in before[nxt] if f != idx]
                    if not before[nxt] and nxt in left_over:
                        heapq.heappush(ready, nxt)
            position = {idx: k for k, idx in enumerate(order)}
            for idx, preds in enumerate(need):
                for f in preds:
                    if position[f] > position[idx]:
                        stuck.append((items[idx][2], items[idx][3], items[f][2], items[f][3]))
            zone = loop_zone.get(layer, 0.0)
            left = col_left[layer] + col_width[layer] + zone
            for k, idx in enumerate(order):
                channel[(items[idx][2], items[idx][3])] = left + (u_gap - zone) * (k + 1) / (len(items) + 1)
        if not stuck:
            break
        # two edges swapping rows cannot both be satisfied, so one of the two rows moves a little
        for en, eh, fn, fh in stuck:
            for n, i in ((en, eh + 1), (fn, fh)):
                moved = next((d for d in (0.03, -0.03, 0.07, -0.07) if room_for(n, i, rows_of[n][i] + d)), None)
                if moved is not None:
                    rows_of[n][i] += moved
                    break

    # lines a detour may turn on: the middle of each gap between columns, round each group, and between the tracks
    base_xs = {-shift_u, u_total - shift_u} if not lanes else {u_total - shift_u}
    for layer in range(n_layers - 1):
        base_xs.add(col_left[layer] + col_width[layer] + u_gap / 2)
    end_xs = {x for ulo, uhi, _vlo, _vhi in group_rect.values() for x in (ulo - 2 * GRID, uhi + 2 * GRID)}
    flat_ys = (
        {y for lane in range(n_lanes) for y in (lane_top[lane] + GRID, lane_bottom[lane] - GRID)}
        if lanes
        else {-shift_v, v_total - shift_v}
    )
    for a, b in pairwise(track_keys):
        if a[0] == b[0]:
            flat_ys.add((track_top[a] + track_height[a] + track_top[b]) / 2)
    end_ys = {y for _ulo, _uhi, vlo, vhi in group_rect.values() for y in (vlo - 2 * GRID, vhi + 2 * GRID)}
    base_xs = {x for x in base_xs | end_xs if -shift_u <= x <= u_total - shift_u} - end_xs
    flat_ys = {y for y in flat_ys | end_ys if -shift_v <= y <= v_total - shift_v} - end_ys
    end_xs = {x for x in end_xs if -shift_u <= x <= u_total - shift_u}
    end_ys = {y for y in end_ys if -shift_v <= y <= v_total - shift_v}
    # the outermost group lines are the free corridors round the drawing, so they get side-by-side copies too
    base_xs |= {*(f(end_xs) for f in (min, max) if end_xs)}
    flat_ys |= {*(f(end_ys) for f in (min, max) if end_ys)}
    solids = [rect_of(n.id) for n in nodes]
    groups_of = {n.id: {g for g, ms in members_of.items() if n.id in ms} for n in nodes}

    routes: dict[tuple[str, str, int], tuple[tuple[float, float], ...]] = {}
    seen_pairs: dict[tuple[str, str], int] = {}
    built: list[tuple[list[tuple[float, float]], str, str, list[_Key], int]] = []
    for n, ((source, target), flip, chain) in enumerate(zip(edges, flipped, chains, strict=True)):
        parallel = seen_pairs.get((source, target), 0)
        seen_pairs[(source, target)] = parallel + 1
        first_slot = slots[chain[0]]
        ends = (chain[0], chain[-1])
        i = twin_rank[n]
        if source == target:
            r = first_slot.v_extent / 2 + 0.2 + 0.1 * i
            c = centre_u(first_slot) - _spread(twins[ends], first_slot.u_extent, source)[i]
            dv = _spread(twins[ends], first_slot.v_extent, source)[i]
            bends = [
                (right_u(first_slot), first_slot.v + dv),
                (right_u(first_slot) + 0.3 + 0.1 * i, first_slot.v + dv),
                (right_u(first_slot) + 0.3 + 0.1 * i, first_slot.v - r),
                (c, first_slot.v - r),
                (c, first_slot.v - first_slot.v_extent / 2),
            ]
        else:
            vs = rows_of[n]
            bends = [(right_u(first_slot), vs[0])]
            for hop, sb in enumerate(slots[k] for k in chain[1:]):
                cu = channel[(n, hop)]
                bends += [(cu, vs[hop]), (cu, vs[hop + 1]), (left_u(sb), vs[hop + 1])]
                if hop + 1 < len(chain) - 1:
                    bends.append((right_u(sb), vs[hop + 1]))
            if flip:
                bends.reverse()
        # on the grid before any comparison, so two lines that print the same are the same line
        built.append(([(snap(u), snap(v)) for u, v in bends], source, target, chain, parallel))

    occupied: dict[tuple[int, float], list[tuple[float, float, int]]] = {}
    ends_of: dict[int, set[tuple[float, float]]] = {}

    def occupy(path: list[tuple[float, float]], n: int) -> None:
        """Record the segments of edge `n`'s `path`, so a later detour can keep off them."""
        ends_of[n] = {path[0], path[-1]}
        for a, b in pairwise(path):
            if a[1] == b[1] and a[0] != b[0]:
                occupied.setdefault((0, round(a[1], 4)), []).append((min(a[0], b[0]), max(a[0], b[0]), n))
            elif a[0] == b[0] and a[1] != b[1]:
                occupied.setdefault((1, round(a[0], 4)), []).append((min(a[1], b[1]), max(a[1], b[1]), n))

    def lane_span(chain: list[_Key]) -> tuple[float, float]:
        """The range across the flow that an edge between the ends of `chain` may use."""
        if not lanes:
            return -shift_v, v_total - shift_v
        a, b = slots[chain[0]].lane, slots[chain[-1]].lane
        return lane_top[min(a, b)], lane_bottom[max(a, b)]

    foreign_of = [
        [
            (r[0] - GRID, r[1] + GRID, r[2] - GRID, r[3] + GRID)
            for g, r in group_rect.items()
            if g not in groups_of[source] | groups_of[target]
        ]
        for _bends, source, target, _chain, _parallel in built
    ]
    pending = []
    for n, (bends, source, target, _chain, _parallel) in enumerate(built):
        foreign = foreign_of[n]
        lines = [(a, b) for a, b in pairwise(bends) if a != b]
        if source != target and any(_enters(a, b, r) for a, b in lines for r in foreign):
            pending.append((n, foreign))
        else:
            occupy(bends, n)
    # the lines round the whole drawing carry the routes that go the long way round, so they come in many copies
    outer_xs = {*(f(end_xs) for f in (min, max) if end_xs)}
    outer_ys = {*(f(end_ys) for f in (min, max) if end_ys)}
    spent = [0]

    def search(
        n: int, path: list[tuple[float, float]], others: dict[tuple[int, float], list[tuple[float, float]]], k: int
    ) -> list[tuple[float, float]] | None:
        """A way for edge `n` from the first point of `path` to its last that avoids boxes and foreign groups."""
        low, high = lane_span(built[n][3])
        # each edge gets its own shifted copy of every line, so detours of different edges tend to run side by side
        shifts = [sign * (k % 12 + 1) * _LANE_STEP for sign in (-1, 1)]
        near_u = (min(path[0][0], path[-1][0]) - _NEAR, max(path[0][0], path[-1][0]) + _NEAR)
        near_v = (min(path[0][1], path[-1][1]) - _NEAR, max(path[0][1], path[-1][1]) + _NEAR)
        around = None
        for wide in (False, True):  # the lines near the end points first; every line if nothing close by works
            keep_ys = [y for y in flat_ys if wide or near_v[0] <= y <= near_v[1] or y in (min(flat_ys), max(flat_ys))]
            keep_xs = [x for x in base_xs if wide or near_u[0] <= x <= near_u[1] or x in (min(base_xs), max(base_xs))]
            near_end_ys = [y for y in end_ys if wide or near_v[0] <= y <= near_v[1] or y in (min(end_ys), max(end_ys))]
            near_end_xs = [x for x in end_xs if wide or near_u[0] <= x <= near_u[1] or x in (min(end_xs), max(end_xs))]
            ys = {
                snap(y)
                for y in (
                    *keep_ys,
                    *near_end_ys,
                    *(y + o for y in (*keep_ys, *near_end_ys) for o in shifts),
                    *(y + m * _LANE_STEP for y in outer_ys for m in range(-20, 21)),
                )
                if low <= y <= high and -shift_v <= y <= v_total - shift_v
            }
            xs = {
                snap(x)
                for x in (
                    *keep_xs,
                    *near_end_xs,
                    *(x + o for x in (*keep_xs, *near_end_xs) for o in shifts),
                    *(x + m * _LANE_STEP for x in outer_xs for m in range(-20, 21)),
                )
                if -shift_u <= x <= u_total - shift_u
            }
            around = _detour(path, xs, ys, [*solids, *foreign_of[n]], others, spent)
            if around is not None:
                break
        return around

    for k, (n, _foreign) in enumerate(pending):
        bends, source, target, chain, parallel = built[n]
        path = [bends[0], *(b for a, b in pairwise(bends) if a != b)]
        # routes that leave or arrive at the same border point may run along this one, so they do not count
        mine = {path[0], path[-1]}
        others = {key: [(lo, hi) for lo, hi, m in runs if not ends_of[m] & mine] for key, runs in occupied.items()}
        around = search(n, path, others, k)
        if around is None:
            raise GraphError(f"edge {source!r} -> {target!r} cannot be routed round the groups it does not belong to")
        built[n] = (around, source, target, chain, parallel)
        occupy(around, n)

    # a route may still run along another one; move a later segment aside a grid step at a time, or refuse
    paths = [_simplify(b[0]) for b in built]
    border_ends = [{p[0], p[-1]} for p in paths]

    def fits(n: int, pts: list[tuple[float, float]]) -> bool:
        """Whether `pts` stays on the page, in the lanes of edge `n`'s ends, off every box and off foreign groups."""
        low, high = lane_span(built[n][3])
        if any(
            not (-shift_u <= u <= u_total - shift_u and max(low, -shift_v) <= v <= min(high, v_total - shift_v))
            for u, v in pts
        ):
            return False
        return not any(_blocks(a, b, r) for a, b in pairwise(pts) for r in solids) and not any(
            _enters(a, b, r) for a, b in pairwise(pts) for r in foreign_of[n]
        )

    def reroute(n: int) -> list[tuple[float, float]] | None:
        """Edge `n` searched again, knowing every other route as it now stands."""
        mine = {paths[n][0], paths[n][-1]}
        others = {
            key: [(lo, hi) for lo, hi, m, _j in runs if not border_ends[m] & mine]
            for key, runs in _runs(paths, skip=n).items()
        }
        found = search(n, paths[n], others, n)
        return None if found is None else _simplify(found)

    _apart(paths, border_ends, fits, lambda n: (built[n][1], built[n][2]), reroute)

    for pts, (_bends, source, target, _chain, parallel) in zip(paths, built, strict=True):
        mapped: list[tuple[float, float]] = []
        for p in (page(u, v) for u, v in pts):
            if not mapped or mapped[-1] != p:
                mapped.append(p)
        kept = [mapped[0]]
        for a, b, c in zip(mapped, mapped[1:], mapped[2:], strict=False):
            if not (a[0] == b[0] == c[0] or a[1] == b[1] == c[1]):
                kept.append(b)
        kept.append(mapped[-1])
        routes[(source, target, parallel)] = tuple(kept)

    width = snap(v_total if top_down else u_total)
    height = snap(u_total if top_down else v_total)
    lane_boxes = {
        name: Box(
            snap(width / 2),
            snap(height - (lane_top[i] + lane_bottom[i]) / 2 - shift_v),
            width,
            snap(lane_bottom[i] - lane_top[i]),
        )
        for i, name in enumerate(lanes)
    }
    group_boxes: dict[str, Box] = {}
    for g, (ulo, uhi, vlo, vhi) in group_rect.items():
        (x1, y1), (x2, y2) = page(ulo, vlo), page(uhi, vhi)
        left, right, bottom, top = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
        group_boxes[g] = Box(snap((left + right) / 2), snap((bottom + top) / 2), snap(right - left), snap(top - bottom))
    return Layout(boxes, group_boxes, lane_boxes, routes, width, height)
