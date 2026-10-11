"""Layered layout of a flow graph on a fixed grid, with lanes, groups and orthogonal routes.

Pure functions over tuples: nothing here touches a document, a clock, a random
source or a hash-ordered container, so the same arguments give the same boxes
and routes on every platform. Ties are broken by the order of the arguments.
"""

from __future__ import annotations

import heapq
import math
from collections import Counter
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
    """Inches between one layer's column and the next, where edges run."""
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


def _enters(a: tuple[float, float], b: tuple[float, float], rect: _Rect) -> bool:
    """Whether the axis-parallel segment a-b passes through the open inside of `rect`."""
    if a[0] == b[0]:
        return rect[0] < a[0] < rect[1] and max(min(a[1], b[1]), rect[2]) < min(max(a[1], b[1]), rect[3])
    return rect[2] < a[1] < rect[3] and max(min(a[0], b[0]), rect[0]) < min(max(a[0], b[0]), rect[1])


_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
"""Unit steps along the flow, against it, across it and back, indexed as a heading."""


def _heading(a: tuple[float, float], b: tuple[float, float]) -> int:
    """The index into _STEPS of the direction from a to b."""
    return 0 if b[0] > a[0] else 1 if b[0] < a[0] else 2 if b[1] > a[1] else 3


def _detour(
    path: list[tuple[float, float]], xs: set[float], ys: set[float], solid: list[_Rect]
) -> list[tuple[float, float]] | None:
    """The shortest few-bend orthogonal path from `path`'s first point to its last that avoids `solid`, or None.

    It leaves in the direction `path` does and arrives in the direction `path` does, and turns only on the lines
    `xs` and `ys`. Ties break by insertion order, so the result depends on the arguments alone.
    """
    start, end = path[0], path[-1]
    first, last = _heading(path[0], path[1]), _heading(path[-2], path[-1])
    gx, gy = sorted(xs | {start[0], end[0]}), sorted(ys | {start[1], end[1]})
    rows = [[(r[0], r[1]) for r in solid if r[2] < y < r[3]] for y in gy]
    cols = [[(r[2], r[3]) for r in solid if r[0] < x < r[1]] for x in gx]

    def free(i: int, j: int, d: int) -> tuple[int, int] | None:
        """The next grid point from (i, j) heading d, or None when off the grid or blocked."""
        ni, nj = i + _STEPS[d][0], j + _STEPS[d][1]
        if not (0 <= ni < len(gx) and 0 <= nj < len(gy)):
            return None
        if d < 2:
            low, high = sorted((gx[i], gx[ni]))
            blocked = any(a < high and low < b for a, b in rows[j])
        else:
            low, high = sorted((gy[j], gy[nj]))
            blocked = any(a < high and low < b for a, b in cols[i])
        return None if blocked else (ni, nj)

    i0, j0 = gx.index(start[0]), gy.index(start[1])
    goal = (gx.index(end[0]), gy.index(end[1]))
    hop = free(i0, j0, first)
    if hop is None:
        return None

    def cost(i: int, j: int, ni: int, nj: int) -> float:
        """The length of the step from (i, j) to (ni, nj)."""
        return abs(gx[ni] - gx[i]) + abs(gy[nj] - gy[j])

    def estimate(i: int, j: int) -> float:
        """A lower bound on the distance left from (i, j) to the goal."""
        return abs(gx[goal[0]] - gx[i]) + abs(gy[goal[1]] - gy[j])

    bend = 0.5
    best = {(hop[0], hop[1], first): cost(i0, j0, *hop)}
    came: dict[tuple[int, int, int], tuple[int, int, int] | None] = {(hop[0], hop[1], first): None}
    heap = [(best[(hop[0], hop[1], first)] + estimate(*hop), 0, hop[0], hop[1], first)]
    count = 0
    while heap:
        _f, _c, i, j, d = heapq.heappop(heap)
        if (i, j) == goal and d == last:
            points = [(gx[i], gy[j])]
            at: tuple[int, int, int] | None = (i, j, d)
            while at is not None:
                points.append((gx[at[0]], gy[at[1]]))
                at = came[at]
            points.append(start)
            return points[::-1]
        if _f - estimate(i, j) > best[(i, j, d)] + 1e-9:
            continue
        moves = [(d, 0.0)]
        if (i, j) != goal:
            moves += [(nd, bend) for nd in (0, 1, 2, 3) if (nd < 2) != (d < 2)]
        for nd, extra in moves:
            nxt = free(i, j, nd)
            if nxt is None:
                continue
            g = best[(i, j, d)] + extra + cost(i, j, *nxt)
            key = (nxt[0], nxt[1], nd)
            if g < best.get(key, math.inf) - 1e-9:
                best[key] = g
                came[key] = (i, j, d)
                count += 1
                heapq.heappush(heap, (g + estimate(*nxt), count, nxt[0], nxt[1], nd))
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
        group id, an option that is not a finite non-negative number, a layer_gap too small for the edges that cross it,
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

    loop_count = Counter(source for source, target in edges if source == target)

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
    for r in group_rect.values():
        lo_u, hi_u = min(lo_u, r[0] - GRID), max(hi_u, r[1] + GRID)
        lo_v, hi_v = min(lo_v, r[2] - GRID), max(hi_v, r[3] + GRID)
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

    gap_edges: dict[int, list[tuple[float, float, int, int]]] = {}
    for n, chain in enumerate(chains):
        for hop, (a, b) in enumerate(pairwise(chain)):
            gap_edges.setdefault(slots[a].layer, []).append((min(slots[a].v, slots[b].v), max(slots[a].v, slots[b].v), n, hop))
    channel: dict[tuple[int, int], float] = {}
    for layer, items in gap_edges.items():
        items.sort()
        left = col_left[layer] + col_width[layer]
        if u_gap < (len(items) + 1) * GRID:
            raise GraphError(
                f"option layer_gap is {opts.layer_gap}; {len(items)} edges cross that gap and need at least "
                f"{(len(items) + 1) * GRID - GRID:g} inches to keep their channels apart"
            )
        for k, (_low, _high, n, hop) in enumerate(items):
            channel[(n, hop)] = left + u_gap * (k + 1) / (len(items) + 1)

    # lines a detour may turn on: the middle of each gap between columns, round each group, and between the tracks
    base_xs = {-shift_u, u_total - shift_u} if not lanes else {u_total - shift_u}
    for layer in range(n_layers - 1):
        base_xs.add(col_left[layer] + col_width[layer] + u_gap / 2)
    for ulo, uhi, _vlo, _vhi in group_rect.values():
        base_xs |= {ulo - 2 * GRID, uhi + 2 * GRID}
    flat_ys = (
        {y for lane in range(n_lanes) for y in (lane_top[lane] + GRID, lane_bottom[lane] - GRID)}
        if lanes
        else {-shift_v, v_total - shift_v}
    )
    for a, b in pairwise(track_keys):
        if a[0] == b[0]:
            flat_ys.add((track_top[a] + track_height[a] + track_top[b]) / 2)
    for _ulo, _uhi, vlo, vhi in group_rect.values():
        flat_ys |= {vlo - 2 * GRID, vhi + 2 * GRID}
    base_xs = {x for x in base_xs if -shift_u <= x <= u_total - shift_u}
    flat_ys = {y for y in flat_ys if -shift_v <= y <= v_total - shift_v}
    solids = [rect_of(n.id) for n in nodes]
    groups_of = {n.id: {g for g, ms in members_of.items() if n.id in ms} for n in nodes}

    twins = Counter((c[0], c[-1]) for c in chains)
    twin_at: dict[tuple[_Key, _Key], int] = {}
    routes: dict[tuple[str, str, int], tuple[tuple[float, float], ...]] = {}
    seen_pairs: dict[tuple[str, str], int] = {}
    for n, ((source, target), flip, chain) in enumerate(zip(edges, flipped, chains, strict=True)):
        parallel = seen_pairs.get((source, target), 0)
        seen_pairs[(source, target)] = parallel + 1
        first_slot = slots[chain[0]]
        ends = (chain[0], chain[-1])
        i = twin_at.get(ends, 0)
        twin_at[ends] = i + 1
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
            # parallel edges leave and arrive at different points along the border so they never overlay
            narrow = min((source, target), key=lambda k: slots[k].v_extent)
            off = _spread(twins[ends], slots[narrow].v_extent, narrow)[i]
            vs = [slots[k].v for k in chain]
            vs[0] += off
            vs[-1] += off
            bends = [(right_u(first_slot), vs[0])]
            for hop, sb in enumerate(slots[k] for k in chain[1:]):
                cu = channel[(n, hop)]
                bends += [(cu, vs[hop]), (cu, vs[hop + 1]), (left_u(sb), vs[hop + 1])]
                if hop + 1 < len(chain) - 1:
                    bends.append((right_u(sb), vs[hop + 1]))
            if flip:
                bends.reverse()
        foreign = [
            (r[0] - GRID, r[1] + GRID, r[2] - GRID, r[3] + GRID)
            for g, r in group_rect.items()
            if g not in groups_of[source] | groups_of[target]
        ]
        lines = [(a, b) for a, b in pairwise(bends) if a != b]
        if source != target and any(_enters(a, b, r) for a, b in lines for r in foreign):
            # the direct channels cross a group the edge does not belong to, so search for a way round
            low = lane_top[min(slots[chain[0]].lane, slots[chain[-1]].lane)] if lanes else -shift_v
            high = lane_bottom[max(slots[chain[0]].lane, slots[chain[-1]].lane)] if lanes else v_total - shift_v
            ys = {y for y in flat_ys if low <= y <= high}
            path = [bends[0], *(b for a, b in pairwise(bends) if a != b)]
            around = _detour(path, base_xs, ys, [*solids, *foreign])
            if around is None:
                raise GraphError(f"edge {source!r} -> {target!r} cannot be routed round the groups it does not belong to")
            bends = around
        mapped: list[tuple[float, float]] = []
        for p in (page(u, v) for u, v in bends):
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
