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
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Literal, cast

from vsdxkit.errors import GraphError


class _Crowded(GraphError):
    """A layout that could not give its routes lines of their own; the same graph may still fit with fewer border points."""


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


def _floor(value: float) -> float:
    """Round `value` down to the grid."""
    return snap(math.floor(value / GRID + 1e-9) * GRID)


def _even(value: float) -> float:
    """Round `value` up to an even number of grid steps, so a snapped centre keeps both borders on the grid."""
    return snap(math.ceil(value / (2 * GRID) - 1e-9) * 2 * GRID)


def _spread(count: int, extent: float, node: object, pitch: float = 0.2) -> list[float]:
    """Offsets, in inches on the grid and about zero, that keep `count` parallel routes `pitch` apart inside `extent`.

    The pitch shrinks to the side divided by (count + 1) on a short side but never below 0.1 inch, and the ports cover at most 80 percent of the side
    unless that would push the pitch below 0.1 inch; only a side too short to hold the ports 0.1 inch apart shrinks them further.

    :raises GraphError: when `extent` has fewer grid steps than `count`, so two routes would coincide
    """
    step = min(round(max(0.1, min(pitch, extent / (count + 1))) / GRID), round(extent / GRID) // count)
    if count > 1:
        step = min(step, max(int(0.8 * extent / GRID + 1e-9) // (count - 1), round(0.1 / GRID)))
    if step == 0:
        raise GraphError(f"node {node!r} is too small for {count} parallel edges; each needs a grid step of its border")
    start = -((count - 1) * step // 2)
    return [snap((start + i * step) * GRID) for i in range(count)]


def _break_cycle(left_over: set[int], before: Sequence[Sequence[int]], after: Sequence[Sequence[int]]) -> int:
    """The hop to place when every hop left waits on another: one on a cycle, the one most others wait on, else the lowest index.

    A hop that is only blocked by a cycle, because it waits on a member, must not go before that member.
    """
    seen: dict[int, int] = {}
    walk: list[int] = []
    at = min(left_over)
    while at not in seen:
        seen[at] = len(walk)
        walk.append(at)
        at = min(f for f in before[at] if f in left_over)
    cycle = walk[seen[at] :]

    def waiting(f: int) -> tuple[int, int]:
        """Sort key: the most hops waiting on `f` first, then the lowest index."""
        return (-sum(1 for g in after[f] if g in left_over), f)

    return min(cycle, key=waiting)


def _nests_left(
    items: Sequence[tuple[float, float, int, int]], rows_of: Sequence[Sequence[float]], chains: Sequence[Sequence[_Key]]
) -> list[list[int]]:
    """For each hop of a gap (low, high, edge, hop), the hops whose channel must lie nearer the layer the gap follows.

    Two hops that leave one node in the same direction nest the farthest target nearest the layer; two that arrive at one
    node from the same direction nest the nearest origin nearest the layer. A hop whose end lies strictly inside the run
    of another is ordered the same way, which covers hops of different nodes. In each case the vertical run of one is not
    crossed by the horizontal run of the other.
    """
    ends: dict[tuple[_Key, bool, bool], list[tuple[float, int]]] = {}
    for idx, (_lo, _hi, n, hop) in enumerate(items):
        delta = rows_of[n][hop + 1] - rows_of[n][hop]
        if delta:
            ends.setdefault((chains[n][hop], True, delta > 0), []).append((abs(delta), idx))
            ends.setdefault((chains[n][hop + 1], False, delta > 0), []).append((abs(delta), idx))
    nest: list[set[int]] = [set() for _ in items]
    for (_node, leaving, _up), group in ends.items():
        for dist_i, i in group:
            nest[i].update(j for dist_j, j in group if j != i and (dist_j > dist_i if leaving else dist_j < dist_i))
    # an end of one hop inside the run of another is crossed by it unless the channels are ordered: a hop that leaves
    # inside lies nearer the layer, and one that arrives inside lies farther
    starts = sorted((rows_of[n][hop], idx) for idx, (_lo, _hi, n, hop) in enumerate(items))
    stops = sorted((rows_of[n][hop + 1], idx) for idx, (_lo, _hi, n, hop) in enumerate(items))
    for i, (_lo, _hi, n, hop) in enumerate(items):
        low, high = sorted((rows_of[n][hop], rows_of[n][hop + 1]))
        for _row, j in starts[bisect_right(starts, (low + _EPS, -1)) : bisect_left(starts, (high - _EPS, -1))]:
            nest[i].add(j)
        for _row, j in stops[bisect_right(stops, (low + _EPS, -1)) : bisect_left(stops, (high - _EPS, -1))]:
            nest[j].add(i)
    for i in range(len(items)):
        nest[i].discard(i)
    return [sorted(found) for found in nest]


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
class PageTarget:
    """The page shape a layout aims for. There is no maximum size: the target steers the row count and the flow direction, and the page grows as large as the content needs."""

    aspect: float = 16 / 9
    """Width over height to aim for."""
    tolerance: float = 0.25
    """The band is ``aspect / (1 + tolerance)`` to ``aspect * (1 + tolerance)``."""
    wrap: Literal["snake", "rows", "none"] = "snake"
    """How a long flow is cut into rows: ``snake`` runs odd rows against the flow so a row ends above the next one's start, ``rows`` runs every row with the flow and accepts a long edge back to the start, ``none`` does not wrap."""
    direction: Literal["auto", "left_to_right", "top_down"] = "auto"
    """``auto`` lets the page target choose when ``LayoutOptions.direction`` is not given: the page is laid out both ways and the one nearer the aspect is kept, left to right on a tie. A ``LayoutOptions.direction`` you give is kept. ``left_to_right`` or ``top_down`` pins the direction and overrides ``LayoutOptions.direction``."""


@dataclass(frozen=True)
class LayoutOptions:
    """How a layout is spaced and which way it flows."""

    direction: Literal["left_to_right", "top_down"] | None = None
    """The way the flow runs, or None for not given, which flows left to right unless ``PageTarget.direction`` is ``auto`` and the other way fits the page target better. A direction you give is kept. Lanes need ``left_to_right``."""
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
    page: PageTarget | None = field(default_factory=PageTarget)
    """The page shape to aim for, or None for none."""
    parents: tuple[tuple[str, str], ...] = ()
    """Pairs of (child group id, parent group id): groups nest one level."""
    headings: tuple[tuple[str, float, float], ...] = ()
    """Per group, (group id, width, height) in inches of its heading text. The group's box is widened to the width and grows at the top to clear the height above its members; a box that then covers a node or group that is not its own is refused."""
    edge_labels: tuple[tuple[float, float] | None, ...] = ()
    """Per edge, in the order of ``edges``, the (width, height) in inches of its label, or None for none; empty means no edge has one. Each label is placed at its route, at the nearest spot clear of every node, heading, other group, lane heading and other label, so it may sit beside its route and not on it; the gaps it crosses are widened to hold it."""
    port_pitch: float = 0.2
    """Inches between the points where parallel routes meet one side of a box, at least 0.1; a short side shrinks it."""
    channel_pitch: float = 0.2
    """Inches between parallel routes in a channel between layers, at least one grid step. A default layer gap holds up to eight channels at this spacing; a busier gap keeps that width and its channels are spaced evenly in it, closer than this."""
    straighten_sweeps: int = 6
    """How many down-and-up passes move boxes toward their neighbours within their track; zero keeps each run centred."""
    pinned: tuple[tuple[str, int], ...] = ()
    """Pairs of (node id, layer): the node sits in that layer, which must come after every layer that feeds it, and its successors move after it. Layers left empty keep a column of width zero."""
    aligned: tuple[tuple[str, ...], ...] = ()
    """Groups of node ids drawn on one row (one column when flowing top down). The members of a group are in different layers, one lane and one track, and a node is in at most one group."""


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
    labels: dict[tuple[str, str, int], Box] = field(default_factory=dict)
    """Each labelled edge's label box, by the same key as its route: near the route, clear of nodes, headings and other labels. The page holds them, a margin from its edge."""
    rows: tuple[tuple[str, ...], ...] = ()
    """Node ids by wrapped row; empty when the layout is not wrapped."""
    fallbacks: int = 0
    """How many routes no straight, one-bend or channel route could serve, so they were searched for."""


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
    """Index of the lane band, or of the row band when a page without lanes is wrapped."""
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


def _layers(
    ids: list[str], edges: list[tuple[str, str]], flipped: list[bool], pinned: Mapping[str, int] | None = None
) -> dict[str, int]:
    """The longest-path layer of each node over the edges that remain once cycles are broken, with a pinned node in its pinned layer."""
    pins = pinned or {}
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
                if node in pins:
                    if pins[node] < 0:
                        raise GraphError(f"node {node!r} is pinned to layer {pins[node]}; a layer is zero or more")
                    if pins[node] < layer[node]:
                        feeder = max(preds[node], key=lambda p: layer[p])
                        raise GraphError(
                            f"node {node!r} is pinned to layer {pins[node]}, but {feeder!r}, which feeds it, is in layer {layer[feeder]}"
                        )
                    layer[node] = pins[node]
                stack.pop()
    return layer


def _partition_table(
    widths: Sequence[float], rows: int, forbidden: frozenset[int]
) -> tuple[list[list[float]], list[list[int]]]:
    """The dynamic-programming layers `best[k][i]` (least widest sum of the first `i` widths in `k` groups) and the cuts `cut[k][i]` that gave them, for every group count up to `rows`; where a cut can fall in more than one place, the earliest is kept."""
    n = len(widths)
    # snapped sums of every run, computed once: the same values the cost would otherwise recompute for each group count
    run = [[0.0] * (n + 1) for _ in range(n + 1)]
    for j in range(n):
        for i in range(j + 1, n + 1):
            run[j][i] = snap(math.fsum(widths[j:i]))
    best = [[math.inf] * (n + 1) for _ in range(rows + 1)]
    cut = [[0] * (n + 1) for _ in range(rows + 1)]
    best[0][0] = 0.0
    for k in range(1, rows + 1):
        prev, here, here_cut = best[k - 1], best[k], cut[k]
        for i in range(k, n + 1):
            for j in range(k - 1, i):
                if k > 1 and j in forbidden:
                    continue
                cost = max(prev[j], run[j][i])
                if cost < here[i] - _EPS:
                    here[i], here_cut[i] = cost, j
    return best, cut


def _starts_for(best: list[list[float]], cut: list[list[int]], n: int, rows: int) -> tuple[int, ...]:
    """The start indices of the partition into at most `rows` groups, from a table made by `_partition_table`: the most groups the forbidden cuts allow."""
    for k in range(min(rows, n), 0, -1):
        if best[k][n] < math.inf:
            starts: list[int] = []
            i = n
            for kk in range(k, 0, -1):
                i = cut[kk][i]
                starts.append(i)
            return tuple(sorted(starts))
    return (0,)


def _partition(widths: Sequence[float], rows: int, forbidden: frozenset[int] = frozenset()) -> tuple[int, ...]:
    """Start indices that cut `widths` into at most `rows` contiguous groups with the least widest sum (linear partition by dynamic programming, O(L squared times rows)); where the last cut can fall in more than one place, the earliest is kept."""
    n = len(widths)
    rows = max(1, min(rows, n))
    best, cut = _partition_table(widths, rows, forbidden)
    return _starts_for(best, cut, n, rows)


def _estimate(
    widths: Sequence[float],
    heights: Sequence[float],
    starts: Sequence[int],
    row_gap: float,
    frame: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[float, float]:
    """The page width and height if the layers are cut into rows at `starts`: the widest row, and the rows' tallest layers plus the gaps between rows.

    `frame` adds what surrounds them: to the width, to the height, and to the height only when there is more than one row.
    """
    ends = [*starts[1:], len(widths)]
    width = max(math.fsum(widths[a:b]) for a, b in zip(starts, ends, strict=True)) + frame[0]
    height = sum(max(heights[a:b]) for a, b in zip(starts, ends, strict=True)) + row_gap * (len(starts) - 1) + frame[1]
    return snap(width), snap(height + (frame[2] if len(starts) > 1 else 0.0))


def _choose_starts(
    widths: Sequence[float],
    heights: Sequence[float],
    row_gap: float,
    target: PageTarget,
    forbidden: frozenset[int],
    frame: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[int, ...]:
    """The row starts whose estimated aspect, snapped to the grid, is nearest the target's in log terms; the first of equal distances wins, so fewer rows."""
    if target.wrap == "none" or len(widths) < 2:
        return (0,)
    chosen: tuple[int, ...] = (0,)
    nearest = math.inf
    seen: set[tuple[int, ...]] = set()
    # one table serves every row count, since the layer for k groups does not depend on how many are asked for
    best, cut = _partition_table(widths, len(widths), forbidden)
    for rows in range(1, len(widths) + 1):
        starts = _starts_for(best, cut, len(widths), rows)
        if starts in seen:
            continue
        seen.add(starts)
        w, h = _estimate(widths, heights, starts, row_gap, frame)
        distance = abs(math.log(max(GRID, snap(w / h)) / target.aspect))
        if distance < nearest - _EPS:
            chosen, nearest = starts, distance
    return chosen


def _columns(
    widths: Sequence[float], gaps: Sequence[float], starts: Sequence[int], snake: bool, first: float
) -> tuple[list[float], list[bool]]:
    """Left edge of each layer's column, and whether its row runs against the flow (a snake's odd rows).

    A snake row starts centred under the last column of the row above. Everything is shifted so the leftmost column starts at `first`.
    """
    left = [0.0] * len(widths)
    mirrored = [False] * len(widths)
    ends = [*starts[1:], len(widths)]
    previous_centre = 0.0
    for r, (lo, hi) in enumerate(zip(starts, ends, strict=True)):
        back = snake and r % 2 == 1
        for i in range(lo, hi):
            mirrored[i] = back
            if i == lo:
                left[i] = previous_centre - widths[i] / 2 if (snake and r > 0) else 0.0
            elif back:
                left[i] = left[i - 1] - gaps[i - 1] - widths[i]
            else:
                left[i] = left[i - 1] + widths[i - 1] + gaps[i - 1]
        previous_centre = left[hi - 1] + widths[hi - 1] / 2
    shift = first - min(left, default=first)
    return [snap(x + shift) for x in left], mirrored


def _check_page(page: object) -> None:
    """Refuse a page target that is not a PageTarget or None, or whose fields are out of range, naming the option."""
    if page is None:
        return
    if not isinstance(page, PageTarget):
        raise GraphError(f"option page is {page!r}; it must be a PageTarget or None")
    for name, low in (("aspect", False), ("tolerance", True)):
        value = getattr(page, name)
        if not (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(value)
            and (value >= 0 if low else value > 0)
        ):
            raise GraphError(
                f"option page.{name} is {value!r}; it must be a finite number {'zero or more' if low else 'above zero'}"
            )
    if page.wrap not in ("snake", "rows", "none"):
        raise GraphError(f"option page.wrap is {page.wrap!r}; it must be 'snake', 'rows' or 'none'")
    if page.direction not in ("auto", "left_to_right", "top_down"):
        raise GraphError(f"option page.direction is {page.direction!r}; it must be 'auto', 'left_to_right' or 'top_down'")


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

    layer_of = {k: i for i, row in enumerate(rows) for k in row}
    between: list[list[tuple[_Key, _Key]]] = [[] for _ in rows]  # links from layer i to layer i + 1, either direction
    for chain in chains:
        for a, b in pairwise(chain):
            if layer_of[b] - layer_of[a] == 1:
                between[layer_of[a]].append((a, b))
            elif layer_of[a] - layer_of[b] == 1:
                between[layer_of[b]].append((b, a))

    def total() -> int:
        """Crossings over every pair of adjacent layers in the current order."""
        return sum(_count_crossings(rows[i], rows[i + 1], between[i]) for i in range(len(rows) - 1))

    best = [list(row) for row in rows]
    fewest = -1
    for _ in range(sweeps):
        for layer in range(1, len(rows)):
            sweep(layer, up)
        for layer in range(len(rows) - 2, -1, -1):
            sweep(layer, down)
        count = total()
        if fewest < 0 or count < fewest:
            fewest, best = count, [list(row) for row in rows]
    for row, kept in zip(rows, best, strict=True):
        row[:] = kept
    position.update({k: float(i) for row in rows for i, k in enumerate(row)})
    _transpose(rows, slots, between, position)


def _fit(wants: Sequence[float], extents: Sequence[float], low: float, high: float, gap: float) -> list[float]:
    """Centres in order, as near `wants` as the box extents, the `gap` and the bounds allow."""
    pos = list(wants)
    cursor = low
    for i, half in enumerate(e / 2 for e in extents):
        pos[i] = max(pos[i], cursor + half)
        cursor = pos[i] + half + gap
    limit = high
    for i in range(len(pos) - 1, -1, -1):
        half = extents[i] / 2
        pos[i] = min(pos[i], limit - half)
        limit = pos[i] - half - gap
    return [snap(p) for p in pos]


def _check_aligned(aligned: Sequence[Sequence[str]], known: set[str], layer_of: Mapping[str, int]) -> list[tuple[str, ...]]:
    """The align groups of two or more nodes as blocks, refusing an unknown id, a node in two groups and two members in one layer."""
    seen: set[str] = set()
    blocks: list[tuple[str, ...]] = []
    for group in aligned:
        if isinstance(group, str):
            raise GraphError(f"option aligned has {group!r}, a string; give each group as a tuple of ids")
        by_layer: dict[int, str] = {}
        for node_id in group:
            if node_id not in known:
                raise GraphError(f"option aligned names {node_id!r}, which is not a node")
            if node_id in seen:
                raise GraphError(f"node {node_id!r} is in two align groups")
            seen.add(node_id)
            if layer_of[node_id] in by_layer:
                raise GraphError(
                    f"align group {list(group)!r} has {by_layer[layer_of[node_id]]!r} and {node_id!r} in one layer; "
                    "they cannot share a row"
                )
            by_layer[layer_of[node_id]] = node_id
        if len(group) > 1:
            blocks.append(tuple(group))
    return blocks


def _straighten(
    rows: list[list[_Key]],
    slots: dict[_Key, _Slot],
    up: dict[_Key, list[_Key]],
    down: dict[_Key, list[_Key]],
    track_bounds: dict[tuple[int, tuple[int, int]], tuple[float, float]],
    gap: float,
    sweeps: int,
    blocks: Sequence[tuple[_Key, ...]] = (),
) -> None:
    """Refit each (lane, track) run toward the lower median of its neighbours' centres, down then up, `sweeps` times; the members of a block share the lower median of their members' wants."""
    block_of = {k: b for b in blocks for k in b}

    def want(k: _Key, near: dict[_Key, list[_Key]]) -> float:
        """The lower median of the centres of `k`'s neighbours, or its own centre with none."""
        centres = sorted(slots[n].v for n in near[k])
        return centres[(len(centres) - 1) // 2] if centres else slots[k].v

    def refit(layer: int, near: dict[_Key, list[_Key]]) -> None:
        """Move one layer's runs toward their `near` neighbours, each inside its track."""
        runs: dict[tuple[int, tuple[int, int]], list[_Key]] = {}
        for k in rows[layer]:
            runs.setdefault((slots[k].lane, slots[k].track), []).append(k)
        for key, keys in runs.items():
            wants = []
            for k in keys:
                if k in block_of:
                    mates = sorted(want(m, near) for m in block_of[k])
                    wants.append(mates[(len(mates) - 1) // 2])
                else:
                    wants.append(want(k, near))
            low, high = track_bounds[key]
            fitted = _fit(wants, [slots[k].v_extent for k in keys], low, high, gap)
            for k, v in zip(keys, fitted, strict=True):
                slots[k].v = v

    for _ in range(sweeps):
        for layer in range(1, len(rows)):
            refit(layer, up)
        for layer in range(len(rows) - 2, -1, -1):
            refit(layer, down)


def _align_blocks(
    rows: list[list[_Key]],
    slots: dict[_Key, _Slot],
    track_bounds: dict[tuple[int, tuple[int, int]], tuple[float, float]],
    gap: float,
    blocks: Sequence[tuple[_Key, ...]],
) -> None:
    """Give each block's members one centre, the lower median of theirs or else the first of theirs every member can take, or refuse the block."""
    row_of = {k: row for row in rows for k in row}
    for block in blocks:
        centres = sorted(slots[k].v for k in block)
        tried = [centres[(len(centres) - 1) // 2], *(slots[k].v for k in block)]
        for target in dict.fromkeys(tried):
            moved = {k: slots[k].v for k in block}
            for k in block:
                slots[k].v = target
            if all(_fits_in_run(k, row_of[k], slots, track_bounds, gap) for k in block):
                break
            for k, v in moved.items():
                slots[k].v = v
        else:
            raise GraphError(
                f"align group {list(block)!r} cannot share a row: a member's track or its neighbours leave no room at one coordinate"
            )


def _fits_in_run(
    key: _Key,
    row: list[_Key],
    slots: dict[_Key, _Slot],
    track_bounds: dict[tuple[int, tuple[int, int]], tuple[float, float]],
    gap: float,
) -> bool:
    """Whether `key` is inside its track and clear of the keys beside it in its layer."""
    me = slots[key]
    low, high = track_bounds[(me.lane, me.track)]
    half = me.v_extent / 2
    if me.v - half < low - 1e-6 or me.v + half > high + 1e-6:
        return False
    for other in row:
        o = slots[other]
        same_track = other != key and (o.lane, o.track) == (me.lane, me.track)
        if same_track and abs(o.v - me.v) < (o.v_extent + me.v_extent) / 2 + gap - 1e-6:
            return False
    return True


def _count_crossings(upper: Sequence[_Key], lower: Sequence[_Key], links: Collection[tuple[_Key, _Key]]) -> int:
    """Pairs of links between two adjacent layers whose ends are in opposite order; a shared end does not count."""
    # ponytail: quadratic in links per layer pair, an accumulator tree is the upgrade if a corpus needs it
    top = {k: i for i, k in enumerate(upper)}
    low = {k: i for i, k in enumerate(lower)}
    ends = sorted((top[a], low[b]) for a, b in links)
    return sum(1 for i, (a, b) in enumerate(ends) for c, d in ends[i + 1 :] if a < c and b > d)


def _transpose(
    rows: list[list[_Key]], slots: dict[_Key, _Slot], between: list[list[tuple[_Key, _Key]]], position: dict[_Key, float]
) -> None:
    """Swap adjacent keys of one layer, in index order, while that lowers the crossings; lane and track order stay."""

    def local(layer: int) -> int:
        """Crossings of the links on both sides of `layer`."""
        count = 0
        if layer > 0:
            count += _count_crossings(rows[layer - 1], rows[layer], between[layer - 1])
        if layer < len(rows) - 1:
            count += _count_crossings(rows[layer], rows[layer + 1], between[layer])
        return count

    improved = True
    while improved:
        improved = False
        for layer, row in enumerate(rows):
            for i in range(len(row) - 1):
                a, b = row[i], row[i + 1]
                if (slots[a].lane, slots[a].track) != (slots[b].lane, slots[b].track):
                    continue
                before = local(layer)
                row[i], row[i + 1] = b, a
                if local(layer) < before:
                    improved = True
                else:
                    row[i], row[i + 1] = a, b
    position.update({k: float(i) for row in rows for i, k in enumerate(row)})


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


def _spend(work: list[int], amount: int) -> None:
    """Charge `amount` search steps to `work`, and refuse the layout once it is past `_WORK_CAP`."""
    work[0] += amount
    if work[0] > _WORK_CAP:
        raise _Crowded(f"the layout is too crowded to route within its search limit of {_WORK_CAP} steps")


def _add_runs(
    lines: dict[tuple[int, float], list[tuple[float, float, int, int]]], n: int, pts: list[tuple[float, float]]
) -> None:
    """Add every segment of path `n`, `pts`, to `lines`, by line: (low, high, path, segment) under (axis, coordinate)."""
    for i, (a, b) in enumerate(pairwise(pts)):
        if a[1] == b[1]:
            lines.setdefault((0, round(a[1], 4)), []).append((min(a[0], b[0]), max(a[0], b[0]), n, i))
        else:
            lines.setdefault((1, round(a[0], 4)), []).append((min(a[1], b[1]), max(a[1], b[1]), n, i))


class _Runs:
    """The segments of every path, by line, kept up to date as paths are replaced instead of scanned again.

    Each scan is still charged to `work` as a fresh one of every path but `skip` would be, so the cap keeps its meaning.
    """

    def __init__(self, paths: list[list[tuple[float, float]]]) -> None:
        """Index `paths`, which this object updates in place as paths are replaced."""
        self.paths = paths
        self.lines: dict[tuple[int, float], list[tuple[float, float, int, int]]] = {}
        for n, pts in enumerate(paths):
            _add_runs(self.lines, n, pts)

    def scan(self, work: list[int], skip: int = -1) -> dict[tuple[int, float], list[tuple[float, float, int, int]]]:
        """Charge a scan of every path but `skip`, and return all lines, which include path `skip`'s own segments."""
        _spend(work, sum(len(pts) for n, pts in enumerate(self.paths) if n != skip))
        return self.lines

    def replace(self, n: int, pts: list[tuple[float, float]]) -> None:
        """Make `pts` the path `n`."""
        for a, b in pairwise(self.paths[n]):
            key = (0, round(a[1], 4)) if a[1] == b[1] else (1, round(a[0], 4))
            self.lines[key] = [r for r in self.lines[key] if r[2] != n]
        self.paths[n] = pts
        _add_runs(self.lines, n, pts)


def _first_clash(known: _Runs, ends: list[set[tuple[float, float]]], work: list[int]) -> tuple[int, int, int, int] | None:
    """The first two segments (path, segment, path, segment) of different paths that run along one line, or None."""
    lines = known.scan(work)
    for key in sorted(lines):
        runs = sorted(lines[key])
        for x, (_lo, hi, n, i) in enumerate(runs):
            for lo2, hi2, m, j in runs[x + 1 :]:
                if lo2 >= hi - _EPS:
                    break
                if m != n and not ends[n] & ends[m] and min(hi, hi2) - lo2 > _EPS:
                    return n, i, m, j
    return None


def _apart(
    paths: list[list[tuple[float, float]]],
    ends: list[set[tuple[float, float]]],
    fits: Callable[[int, list[tuple[float, float]]], bool],
    name: Callable[[int], tuple[str, str]],
    reroute: Callable[[int, dict[tuple[int, float], list[tuple[float, float, int, int]]]], list[tuple[float, float]] | None],
    work: list[int],
) -> None:
    """Move segments aside, one grid step at a time, until no two paths run along one line, or raise GraphError.

    Two paths may overlap where they share an end point. A path that is moved is the later one, and only a segment
    that is neither its first nor its last, so its ends stay on their borders; `fits` says whether a moved path is
    still legal. A pair that `_SEPARATIONS` steps either way cannot part is refused, and so is a layout whose
    scanning, with the route searches, passes `_WORK_CAP` steps in `work`.
    """
    runs = _Runs(paths)
    for _round in range(_REROUTES):
        # every route that runs along another is searched again, now that the routes after it are known
        for n in range(len(paths)):
            if name(n)[0] == name(n)[1]:
                continue
            rest = runs.scan(work, skip=n)
            now = _clashes(paths[n], n, rest, ends)
            if now:
                again = reroute(n, runs.scan(work, skip=n))
                if again is not None and fits(n, again) and _clashes(again, n, rest, ends) < now:
                    runs.replace(n, again)
    for _ in range(8 * len(paths) + 8):
        clash = _first_clash(runs, ends, work)
        if clash is None:
            return
        n, i, m, j = clash
        for who, seg in sorted(((n, i), (m, j)), reverse=True):
            pts = paths[who]
            if name(who)[0] == name(who)[1] or not 1 <= seg <= len(pts) - 3:
                continue
            others = runs.scan(work, skip=who)
            before = _clashes(pts, who, others, ends)
            for step in range(1, _SEPARATIONS + 1):
                moved = None
                for sign in (1, -1):
                    moved = _shifted(pts, seg, sign * step * GRID)
                    if moved is not None and fits(who, moved) and _clashes(moved, who, others, ends) < before:
                        break
                    moved = None
                if moved is not None:
                    runs.replace(who, moved)
                    break
            else:
                continue
            break
        else:
            # no segment will move aside, so search for a whole new route for one of the pair
            for who in (m, n) if m > n else (n, m):
                if name(who)[0] == name(who)[1]:
                    continue
                again = reroute(who, runs.scan(work, skip=who))
                rest = runs.scan(work, skip=who)
                if (
                    again is not None
                    and fits(who, again)
                    and _clashes(again, who, rest, ends) < _clashes(paths[who], who, rest, ends)
                ):
                    runs.replace(who, again)
                    break
            else:
                a, b = name(n), name(m)
                raise _Crowded(f"edge {a[0]!r} -> {a[1]!r} and edge {b[0]!r} -> {b[1]!r} cannot be kept apart")
    clash = _first_clash(runs, ends, work)
    if clash is not None:
        a, b = name(clash[0]), name(clash[2])
        raise _Crowded(f"edge {a[0]!r} -> {a[1]!r} and edge {b[0]!r} -> {b[1]!r} cannot be kept apart")


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


_AUTO_DIRECTION_NODES = 80
"""The most nodes for which an ``auto`` direction also lays the page out the other way; trying both doubles a layout, so a larger page keeps the configured direction."""

_AUTO_DIRECTION_EDGES_PER_NODE = 2
"""The most edges per node for which an ``auto`` direction also tries the other way; a dense page spends seconds in routing, and a second layout would double them."""

_PITCHED_CHANNELS = 8
"""The most channels a default layer gap widens to hold at the channel pitch; hops that do not meet share a channel line, and a 200 node graph with lanes and groups stops laying out when its gaps are much wider."""

_NUDGES = (0.03, -0.03, 0.07, -0.07, 0.09, -0.09)
"""Inches a dummy's row may move off its centre; none is zero, and the largest stays inside the dummy's 0.2 in slot."""

_CORRIDOR = 0.5
"""Inches of clear space kept round a group box, so a route has somewhere to go round it."""

_CHANNEL = 0.2
"""Inches between the levels that fold routes use in the corridor between two rows."""

_LANE_STEP = 0.02
"""Inches between the neighbouring lines a detour may use along one gap or corridor, so detours can run side by side."""

_WORK_CAP = 12_000_000
"""Search steps one layout may spend routing round groups and parting routes, so a very crowded one fails instead of running on."""

_DENSE_STATES = 4_000_000
"""States above which a detour's tables are sparse, not flat lists (a 1000 by 1000 grid is about 96 MB); routes are the same either way."""

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

_BORDER_CLEAR = 0.05
"""Most inches a route keeps from a group's border where it runs parallel to it, so it does not look like part of the box. A layout spaced tighter than this keeps what it has room for."""

_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
"""Unit steps along the flow, against it, across it and back, indexed as a heading."""


def _heading(a: tuple[float, float], b: tuple[float, float]) -> int:
    """The index into _STEPS of the direction from a to b."""
    return 0 if b[0] > a[0] else 1 if b[0] < a[0] else 2 if b[1] > a[1] else 3


def _candidates(path: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """The routes with fewer bends than `path` between its ends that leave and arrive as it does: straight, then one bend.

    The straight run and the two corners are in that order, so the first free one has the fewest bends; a
    corner that makes the route leave or arrive another way is not offered, because the ports are fixed.
    """
    start, end = path[0], path[-1]
    first, last = _heading(path[0], path[1]), _heading(path[-2], path[-1])
    tries = [[start, end]] if start[0] == end[0] or start[1] == end[1] else []
    tries += [[start, (end[0], start[1]), end], [start, (start[0], end[1]), end]]
    found = []
    for route in tries:
        if (
            start != end
            and _heading(route[0], route[1]) == first
            and _heading(route[-2], route[-1]) == last
            and len(_simplify(route)) < len(_simplify(path))
        ):
            found.append(route)
    return found


class _Sparse[T](dict[int, T]):
    """A table that answers `default` for a state not yet set, so it grows with the states a search visits."""

    def __init__(self, default: T) -> None:
        """An empty table answering `default`."""
        super().__init__()
        self.default = default

    def __missing__(self, key: int) -> T:
        """`default`, without storing it."""
        return self.default


def _table[T](size: int, default: T) -> list[T]:
    """A flat list of `size` copies of `default`, or a sparse table typed as one when a list is too big to allocate up front."""
    return [default] * size if size <= _DENSE_STATES else cast("list[T]", _Sparse(default))


class _Filtered(Mapping[tuple[int, float], list[tuple[float, float]]]):
    """The runs of `lines` as (low, high), keeping a run only when `keep` accepts the route index it belongs to; a line's list is built when it is asked for, because a search reads a few lines of many."""

    def __init__(
        self,
        lines: Mapping[tuple[int, float], Sequence[tuple[float, float, int] | tuple[float, float, int, int]]],
        keep: Callable[[int], bool],
    ) -> None:
        """Wrap `lines`, whose runs are (low, high, route, ...) tuples."""
        self._lines, self._keep = lines, keep

    def __getitem__(self, key: tuple[int, float]) -> list[tuple[float, float]]:
        """The kept runs of line `key`, or KeyError when it has none."""
        return [(run[0], run[1]) for run in self._lines[key] if self._keep(run[2])]

    def __iter__(self) -> Iterator[tuple[int, float]]:
        """The keys of every line."""
        return iter(self._lines)

    def __len__(self) -> int:
        """The number of lines."""
        return len(self._lines)


def _detour(
    path: list[tuple[float, float]],
    xs: set[float],
    ys: set[float],
    solid: list[_Rect],
    occupied: Mapping[tuple[int, float], list[tuple[float, float]]],
    work: list[int],
    borders: list[tuple[int, float, float, float]],
    clear: float,
) -> list[tuple[float, float]] | None:
    """The shortest few-bend orthogonal path from `path`'s first point to its last that avoids `solid`, or None.

    It also keeps `clear` inches off the length of every border in `borders`, which a route may still cross.

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
    for kind, coord, lo, hi in borders:
        # a line close beside a border is blocked along the border's length, so a route crosses it and never rides it
        lines, along, flags = (gx, gy, blocked_v) if kind == 1 else (gy, gx, blocked_h)
        for i in range(bisect_right(lines, coord - clear + _EPS), bisect_left(lines, coord + clear - _EPS)):
            for k in range(max(bisect_right(along, lo + _EPS) - 1, 0), min(bisect_left(along, hi - _EPS), len(flags[i]))):
                flags[i][k] = 1

    nx, ny = len(gx), len(gy)
    i0, j0 = gx.index(start[0]), gy.index(start[1])
    goal = (gx.index(end[0]), gy.index(end[1]))

    def covered(axis: int, coord: float) -> Callable[[float], float] | None:
        """A function giving how much of one line, up to a position, earlier routes cover, or None when none is covered."""
        runs = occupied.get((axis, round(coord, 4)))
        if not runs:
            return None
        joined: list[tuple[float, float]] = []
        for lo, hi in sorted(runs):
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

    # ponytail: the search state lives in flat lists indexed by cell * 4 + heading, not dicts, because a dense graph
    # runs this loop millions of times; a step's cost is -2.0 until first computed and -1.0 when the step is blocked
    def step_cost(i: int, j: int, nd: int) -> float:
        """The length of the step from (i, j) heading nd, dearer where an earlier route already runs, or -1.0 when blocked."""
        if nd < 2:
            ni = i + 1 if nd == 0 else i - 1
            if not 0 <= ni < nx or blocked_h[j][min(i, ni)]:
                return -1.0
            low, high = (gx[i], gx[ni]) if nd == 0 else (gx[ni], gx[i])
            up_to = along_x[j]
        else:
            nj = j + 1 if nd == 2 else j - 1
            if not 0 <= nj < ny or blocked_v[i][min(j, nj)]:
                return -1.0
            low, high = (gy[j], gy[nj]) if nd == 2 else (gy[nj], gy[j])
            up_to = along_y[i]
        if up_to is None:
            return high - low
        return high - low + _SHARING * (up_to(high) - up_to(low))

    first_cost = step_cost(i0, j0, first)
    if first_cost < 0:
        return None
    hop = (i0 + _STEPS[first][0]) * ny + j0 + _STEPS[first][1]
    to_go_x = [abs(x - gx[goal[0]]) for x in gx]
    to_go_y = [abs(y - gy[goal[1]]) for y in gy]
    best, came, costs = _table(nx * ny * 4, math.inf), _table(nx * ny * 4, -1), _table(nx * ny * 4, -2.0)
    pop, push = heapq.heappop, heapq.heappush
    bend = 0.5
    ahead = (ny, -ny, 1, -1)
    di, dj = (1, -1, 0, 0), (0, 0, 1, -1)
    options = ((0, 2, 3), (1, 2, 3), (2, 0, 1), (3, 0, 1))
    first_state = hop * 4 + first
    best[first_state] = first_cost
    heap = [(first_cost + _HURRY * (to_go_x[i0 + _STEPS[first][0]] + to_go_y[j0 + _STEPS[first][1]]), 0, first_state)]
    count = 0
    goal_cell = goal[0] * ny + goal[1]
    room = _WORK_CAP - work[0]
    pops = 0
    try:
        while heap:
            _f, _c, state = pop(heap)
            pops += 1
            if pops > room:
                work[0] += pops
                pops = 0
                _spend(work, 0)  # refuses the layout, with the message every other charge gives
            cell, d = state >> 2, state & 3
            if cell == goal_cell and d == last:
                points = [(gx[cell // ny], gy[cell % ny])]
                at = state
                while at >= 0:
                    points.append((gx[(at >> 2) // ny], gy[(at >> 2) % ny]))
                    at = came[at]
                points.append(start)
                return points[::-1]
            g0 = best[state]
            i, j = divmod(cell, ny)
            if _f - _HURRY * (to_go_x[i] + to_go_y[j]) > g0 + 1e-9:
                continue
            turned = g0 + bend
            for nd in (d,) if cell == goal_cell else options[d]:
                key = cell * 4 + nd
                hopped = costs[key]
                nxt = cell + ahead[nd]
                if hopped == -2.0:
                    hopped = costs[key] = step_cost(i, j, nd)
                    if hopped >= 0:
                        costs[nxt * 4 + (nd ^ 1)] = hopped  # the step back along the same gap costs the same
                if hopped < 0:
                    continue
                g = (g0 if nd == d else turned) + hopped
                new_state = nxt * 4 + nd
                if g < best[new_state] - 1e-9:
                    best[new_state] = g
                    came[new_state] = state
                    count += 1
                    push(heap, (g + _HURRY * (to_go_x[i + di[nd]] + to_go_y[j + dj[nd]]), count, new_state))
        return None
    finally:
        work[0] += pops


def _beside(pts: list[tuple[float, float]], borders: list[tuple[int, float, float, float]], clear: float) -> list[int]:
    """The segments of `pts` that run parallel to a border closer than `clear`.

    A border is (axis, coordinate, low, high) in the form `_add_runs` uses: axis 0 is a line of constant second coordinate.
    """
    found = []
    for i, (a, b) in enumerate(pairwise(pts)):
        axis = 0 if a[1] == b[1] else 1
        low, high = sorted((a[axis], b[axis]))
        if any(
            kind == axis and abs(a[1 - axis] - coord) < clear - _EPS and min(high, hi) - max(low, lo) > _EPS
            for kind, coord, lo, hi in borders
        ):
            found.append(i)
    return found


def _steps(count: int) -> Iterator[int]:
    """0, 1, -1, 2, -2, ... up to `count` on each side."""
    yield 0
    for k in range(1, count + 1):
        yield k
        yield -k


def _place_labels(
    sizes: tuple[tuple[float, float] | None, ...],
    edges: tuple[tuple[str, str], ...],
    routes: dict[tuple[str, str, int], tuple[tuple[float, float], ...]],
    fixed: list[Box],
    foreign: list[list[Box]],
    spans: list[tuple[float, float] | None],
    work: list[int],
    margin: float,
) -> dict[tuple[str, str, int], Box]:
    """Each labelled edge's label box, near its route and clear of `fixed`, of its own `foreign` boxes and of earlier labels.

    The box starts on a segment of the route and moves along it and then sideways until it is clear, so a crowded
    route can leave its label beside the route and not touching it. `margin` is kept between a label and the page's
    left and bottom edges.

    A label is tried along each segment, longest first and the middle first, in steps of half its length, then moved
    sideways in whole label heights or widths, nearest first, as far as there are labels to make room for. It stays
    on the page's left and bottom, and inside the (low, high) range across the flow in `spans` when there is one.
    The first spot that touches nothing wins; a label with no such spot is refused.
    """
    placed: dict[tuple[str, str, int], Box] = {}
    seen: Counter[tuple[str, str]] = Counter()
    count = sum(size is not None for size in sizes)
    for n, ((source, target), size) in enumerate(zip(edges, sizes or (None,) * len(edges), strict=True)):
        key = (source, target, seen[(source, target)])
        seen[(source, target)] += 1
        if size is None:
            continue
        width, height = size
        span = spans[n]
        segments = sorted(
            enumerate(pairwise(routes[key])),
            key=lambda item: (-(abs(item[1][0][0] - item[1][1][0]) + abs(item[1][0][1] - item[1][1][1])), item[0]),
        )
        for _i, ((x1, y1), (x2, y2)) in segments:
            flat = y1 == y2
            length = abs(x2 - x1) + abs(y2 - y1)
            along = (width if flat else height) / 2 + 0.01
            slides = [*(j * along / length for j in _steps(int(length / along / 2) + 1)), 0.5, -0.5]
            for slide in slides:
                t = min(max(0.5 + slide, 0.0), 1.0)
                for k in _steps(count + 3):
                    unit = k * ((height if flat else width) + 0.02)
                    # a label that would hang off the page's left or bottom is moved onto it; the page grows the other ways
                    x = snap(max(x1 + t * (x2 - x1) + (0.0 if flat else unit), margin + width / 2))
                    y = snap(max(y1 + t * (y2 - y1) + (unit if flat else 0.0), margin + height / 2))
                    if span is not None and not (span[0] - _EPS <= y - height / 2 and y + height / 2 <= span[1] + _EPS):
                        continue
                    candidate = Box(x, y, width, height)
                    _spend(work, len(fixed) + len(foreign[n]) + len(placed))
                    if not any(_boxes_meet(candidate, other) for other in (*fixed, *foreign[n], *placed.values())):
                        placed[key] = candidate
                        break
                else:
                    continue
                break
            else:
                continue
            break
        else:
            raise GraphError(
                f"the label of edge {source!r} -> {target!r} cannot be placed clear of the nodes, group headings, "
                "other groups, lane headings and other labels"
            )
    return placed


def _boxes_meet(a: Box, b: Box) -> bool:
    """Whether the insides of two boxes overlap."""
    return abs(a.x - b.x) < (a.width + b.width) / 2 - _EPS and abs(a.y - b.y) < (a.height + b.height) / 2 - _EPS


def layered_layout(
    nodes: tuple[LayoutNode, ...],
    edges: tuple[tuple[str, str], ...],
    lanes: tuple[str, ...] = (),
    groups: tuple[str, ...] = (),
    options: LayoutOptions | None = None,
) -> Layout:
    """Place `nodes` in layers along the flow, lanes as bands and groups as boxes, and route every edge.

    An edge that spans layers passes through a dummy slot in each one it crosses, so no route meets a node.

    Each edge that meets a node gets a border point of its own, ordered by where its other end lies, and self-loops
    leave from the first. A node too small to give every edge a grid step shares them as before, and so does a graph
    too dense for routes with points of their own to keep apart. Routes keep 0.05 inch off the length of a group's
    border (a self-loop stays inside its group's box, a grid step from it), except where spacing is tighter than that.

    Routes between layers run in channels, one line for each route, spaced ``LayoutOptions.channel_pitch`` apart (spread
    evenly in a gap too busy to hold them at that pitch). A run of edges that leave one box for boxes in line with it
    stays straight. The pitch between border points on one side of a box is ``LayoutOptions.port_pitch``.

    A dense graph may be refused: when routes cannot all be given lines of their own within a fixed number of search
    steps, the layout raises instead of returning routes that overlap. The limit holds for each of the two passes
    (border points of their own, then shared points). Measured with random graphs and the default options, these
    lay out: 60 nodes, 200 edges, 6 groups; 150 nodes, 240 edges, 4 lanes, 4 groups; 200 nodes, 320 edges, 4 lanes,
    4 groups (about 17 s); 200 nodes, 400 edges, no groups or lanes. 200 nodes and 400 edges in 20 groups is refused
    (after about 40 s). The ceiling falls with the number of groups and lanes more than with nodes.

    ``LayoutOptions.page`` is the page shape to aim for (a ``PageTarget``, 16:9 by default; ``None`` keeps one row).
    A page without lanes whose flow is left to right is cut into rows of layers, chosen so that the page's aspect,
    snapped to the grid, is nearest the target's in log terms (the fewer rows on a tie). With ``wrap="snake"`` odd rows
    run against the flow, with ``"rows"`` every row runs with it, and ``"none"`` does not wrap. A group is never split
    across rows. Lanes and top-down flows are not wrapped, and the page has no maximum size.

    The page target steers the direction only when ``LayoutOptions.direction`` is not given. With it unset and
    ``PageTarget.direction`` at ``auto``, a page without lanes of at most 80 nodes and two edges per node whose aspect
    lies outside the target's band is also laid out top down, and the result nearer the target is kept. A tie, an error
    from the other layout, a laned page or a larger page flows left to right. A ``LayoutOptions.direction`` you give is
    always kept; ``PageTarget(direction=...)`` pins one too, and ``page=None`` turns the target off.

    :param edges: pairs of (source id, target id); a repeat is a parallel edge, a pair of one id a self-loop
    :param lanes: lane ids, top to bottom
    :param groups: every group id; a node names its innermost group
    :raises GraphError: lanes with a top-down direction, an edge naming a missing node, a node in an unknown lane or
        group or without a lane when lanes are declared, a node size that is not finite and positive, a repeated node,
        lane or group id, a ``page`` that is not a PageTarget or None, a ``page.aspect`` that is not a finite number above
        zero, a ``page.tolerance`` that is not a finite number of zero or more, a ``page.wrap`` or ``page.direction``
        outside its choices, an option that is not a finite non-negative number, a layer_gap too small for the edges that
        cross it, a node too small to give each of its parallel edges a grid step of its border, an edge that cannot
        be routed round the groups it does not belong to, two edges that cannot be kept on lines of their own, a
        layout past the search limit, a group whose members sit in different lanes, or a parent that is undeclared,
        repeated for one child or nests more than one level
    """
    first = _laid_out(nodes, edges, lanes, groups, options)
    opts = options if options is not None else LayoutOptions()
    target = opts.page
    if (
        not isinstance(target, PageTarget)
        or opts.direction is not None
        or target.direction != "auto"
        or lanes
        or len(nodes) > _AUTO_DIRECTION_NODES
        or len(edges) > _AUTO_DIRECTION_EDGES_PER_NODE * len(nodes)
        or _aspect_miss(first, target) <= snap(math.log1p(target.tolerance))
    ):
        return first
    other = "top_down"
    try:
        second = _laid_out(nodes, edges, lanes, groups, replace(opts, direction=other))
    except GraphError:
        return first
    return second if _aspect_miss(second, target) < _aspect_miss(first, target) else first


def _aspect_miss(layout: Layout, target: PageTarget) -> float:
    """How far a layout's aspect lies from the target, as a log distance on the grid, or 0.0 for a layout of no size; the band edge is ``log1p(tolerance)``."""
    return snap(abs(math.log(layout.width / layout.height / target.aspect))) if layout.height > 0 and layout.width > 0 else 0.0


def _laid_out(
    nodes: tuple[LayoutNode, ...],
    edges: tuple[tuple[str, str], ...],
    lanes: tuple[str, ...],
    groups: tuple[str, ...],
    options: LayoutOptions | None,
) -> Layout:
    """One layout in the configured direction: border points of their own first, shared ones when the graph is too dense for that."""
    try:
        return _lay_out(nodes, edges, lanes, groups, options, True, [0])
    except _Crowded:
        # every edge at a node had a border point of its own; a graph too dense for that shares them, as it did before
        # the second pass has a search budget of its own, so a first pass that spent most of its own does not starve it
        # ponytail: a whole second layout, so a dense graph pays twice (150 nodes took 2.3 s, now 14 s); share points per node instead if that bites
        try:
            return _lay_out(nodes, edges, lanes, groups, options, False, [0])
        except _Crowded as error:
            raise _Crowded(
                f"{error} ({len(nodes)} nodes, {len(edges)} edges, {len(groups)} groups and {len(lanes)} lanes; "
                "fewer edges or groups lay out)"
            ) from None


def _blame(
    group_rect: dict[str, _Rect],
    grown: set[str],
    nodes: tuple[LayoutNode, ...],
    members_of: dict[str, list[str]],
    parent_of: dict[str, str],
    rect_of: Callable[[str], _Rect],
    heading_of: dict[str, tuple[float, float]],
) -> str | None:
    """What a grown group box covers that is not its own, as an error message, or None."""
    for g in sorted(grown):
        ulo, uhi, vlo, vhi = group_rect[g]
        why = "heading" if g in heading_of else "padding"
        fix = "shorten the heading" if g in heading_of else "add spacing between them"
        for n in nodes:
            if n.id not in members_of[g]:
                a, b, c, d = rect_of(n.id)
                if a < uhi - _EPS and b > ulo + _EPS and c < vhi - _EPS and d > vlo + _EPS:
                    return f"the {why} of group {g!r} makes its box cover node {n.id!r}; {fix}"
        for other, (a, b, c, d) in group_rect.items():
            related = parent_of.get(g) == other or parent_of.get(other) == g
            if other != g and not related and a < uhi - _EPS and b > ulo + _EPS and c < vhi - _EPS and d > vlo + _EPS:
                return f"the {why} of group {g!r} makes its box cover group {other!r}; {fix}"
    return None


def _blame(
    group_rect: dict[str, _Rect],
    grown: set[str],
    nodes: tuple[LayoutNode, ...],
    members_of: dict[str, list[str]],
    parent_of: dict[str, str],
    rect_of: Callable[[str], _Rect],
    heading_of: dict[str, tuple[float, float]],
) -> str | None:
    """What a grown group box covers that is not its own, as an error message, or None."""
    for g in sorted(grown):
        ulo, uhi, vlo, vhi = group_rect[g]
        why = "heading" if g in heading_of else "padding"
        fix = "shorten the heading" if g in heading_of else "add spacing between them"
        for n in nodes:
            if n.id not in members_of[g]:
                a, b, c, d = rect_of(n.id)
                if a < uhi - _EPS and b > ulo + _EPS and c < vhi - _EPS and d > vlo + _EPS:
                    return f"the {why} of group {g!r} makes its box cover node {n.id!r}; {fix}"
        for other, (a, b, c, d) in group_rect.items():
            related = parent_of.get(g) == other or parent_of.get(other) == g
            if other != g and not related and a < uhi - _EPS and b > ulo + _EPS and c < vhi - _EPS and d > vlo + _EPS:
                return f"the {why} of group {g!r} makes its box cover group {other!r}; {fix}"
    return None


def _lay_out(
    nodes: tuple[LayoutNode, ...],
    edges: tuple[tuple[str, str], ...],
    lanes: tuple[str, ...],
    groups: tuple[str, ...],
    options: LayoutOptions | None,
    own_points: bool,
    spent: list[int],
    slack: int = 0,
    no_l: frozenset[int] = frozenset(),
) -> Layout:
    """`layered_layout`, with `own_points` saying whether each edge at a node gets a border point of its own, and its search steps charged to `spent`. `slack` grid steps are added to the lane padding and the clearance between tracks, which a layout whose rounded group boxes came out too close asks for. The edges of `no_l` keep their Z routes, which a layout whose L route ran into something asks for."""
    opts = options if options is not None else LayoutOptions()
    page_direction = opts.page.direction if isinstance(opts.page, PageTarget) else "auto"
    direction = opts.direction or "left_to_right"
    top_down = (direction if lanes or page_direction == "auto" else page_direction) == "top_down"
    for name in ("layer_gap", "node_gap", "margin", "group_padding", "lane_padding", "lane_heading"):
        value = getattr(opts, name)
        if not (isinstance(value, int | float) and math.isfinite(value) and value >= 0):
            raise GraphError(f"option {name} is {value!r}; it must be a finite number of inches, zero or more")
    margin = _ceil(opts.margin)  # an off-grid margin would snap to less than was asked, even to nothing
    # spacing tighter than the clearance leaves room for less of it, so a layout that fitted without the clearance still does
    clear = snap(math.floor(min(_BORDER_CLEAR, opts.group_padding, opts.node_gap, opts.layer_gap) / GRID + 1e-9) * GRID)
    if not (isinstance(opts.sweeps, int) and not isinstance(opts.sweeps, bool) and opts.sweeps >= 1):
        raise GraphError(f"option sweeps is {opts.sweeps!r}; it must be a whole number, one or more")
    if not (
        isinstance(opts.straighten_sweeps, int)
        and not isinstance(opts.straighten_sweeps, bool)
        and opts.straighten_sweeps >= 0
    ):
        raise GraphError(f"option straighten_sweeps is {opts.straighten_sweeps!r}; it must be a whole number, zero or more")
    for name, least in (("port_pitch", 0.1), ("channel_pitch", GRID)):
        value = getattr(opts, name)
        if not (
            isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value) and value >= least - 1e-9
        ):
            raise GraphError(f"option {name} is {value!r}; it must be a finite number of inches, {least} or more")
    _check_page(opts.page)
    if opts.edge_labels and len(opts.edge_labels) != len(edges):
        raise GraphError(f"option edge_labels has {len(opts.edge_labels)} entries for {len(edges)} edges; give one per edge")
    for entry in (*opts.edge_labels, *(h[1:] if isinstance(h, tuple) and h else h for h in opts.headings)):
        if entry is not None and not (
            isinstance(entry, tuple)
            and len(entry) == 2
            and all(isinstance(v, int | float) and math.isfinite(v) and v > 0 for v in entry)
        ):
            raise GraphError(f"a label or heading size is {entry!r}; give (width, height), both finite and positive")
    if opts.direction not in (None, "left_to_right", "top_down"):
        raise GraphError(f"option direction is {opts.direction!r}; it must be 'left_to_right', 'top_down' or None")
    if lanes and direction == "top_down":
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
    heading_of = {g: (w, h) for g, w, h in opts.headings}
    if len(heading_of) != len(opts.headings) or any(g not in group_index for g in heading_of):
        raise GraphError("option headings names a group that is not declared, or names one twice")
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
    layer_of = _layers(ids, list(edges), flipped, dict(opts.pinned))
    blocks = _check_aligned(opts.aligned, set(ids), layer_of)
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
    explicit_gap = opts.layer_gap != LayoutOptions.layer_gap
    if u_gap < (busiest + 1) * GRID and explicit_gap:
        raise GraphError(
            f"option layer_gap is {opts.layer_gap}; {busiest} edges cross one gap and need at least "
            f"{busiest * GRID:g} inches to keep their channels apart"
        )
    if not explicit_gap:
        u_gap = max(u_gap, (min(busiest, _PITCHED_CHANNELS) + 1) * opts.channel_pitch)
    # channels start beyond the loops on the column, so no loop shares a line with a channel
    loop_count = Counter(source for source, target in edges if source == target)
    loop_zone: dict[int, float] = {}
    for node_id, count in loop_count.items():
        layer = slots[node_id].layer
        loop_zone[layer] = max(loop_zone.get(layer, 0.0), 0.3 + 0.1 * (count - 1) + GRID)
    crossing = Counter(slots[a].layer for chain in chains if chain[0] != chain[-1] for a, _b in pairwise(chain))
    u_gap = max([u_gap, *(loop_zone.get(layer, 0.0) + (crossing[layer] + 1) * GRID for layer in {*crossing, *loop_zone})])

    # a label sits on its route inside a gap, so each gap its route crosses is as long as its label along the flow,
    # and as long as all the labels of parallel edges together, which cannot share the same stretch of it
    stacked: dict[tuple[int, _Key, _Key], list[float]] = {}
    for chain, size in zip(chains, opts.edge_labels or (None,) * len(chains), strict=True):
        if size is not None and chain[0] != chain[-1]:
            for a, _b in pairwise(chain):
                stacked.setdefault((slots[a].layer, chain[0], chain[-1]), []).append(size[1] if top_down else size[0])
    gaps = [u_gap] * n_layers
    for (layer, _first, _last), extents in stacked.items():
        gaps[layer] = max(gaps[layer], math.fsum(extents) + 0.1)

    col_width = [max((slots[k].u_extent for k in row), default=0.0) for row in rows]
    # a long flow is cut into rows, each a band; lanes, top-down flows and short flows are never cut
    row_starts: tuple[int, ...] = (0,)
    if opts.page is not None and not lanes and not top_down and n_layers > 1:
        stack = [math.fsum(slots[k].v_extent for k in row) + v_gap * (len(row) - 1) for row in rows]
        forbidden: set[int] = set()
        for member_ids in members_of.values():
            held = [slots[m].layer for m in member_ids]
            forbidden.update(range(min(held, default=0) + 1, max(held, default=0) + 1))
        row_starts = _choose_starts(
            [w + g for w, g in zip(col_width, gaps, strict=True)],
            stack,
            2 * opts.lane_padding,
            opts.page,
            frozenset(forbidden),
            # the margins on both sides, less the gap each row's last column carries in its width, and a band's padding above and below
            (2 * margin - u_gap, 2 * margin, 2 * opts.lane_padding),
        )
    n_bands = len(row_starts)
    band_of_layer = [sum(1 for s in row_starts if s <= layer) - 1 for layer in range(n_layers)]
    mirrored = [False] * n_layers
    col_left: list[float] = []
    if n_bands > 1:
        assert opts.page is not None
        for slot in slots.values():
            slot.lane = band_of_layer[slot.layer]
        col_left, mirrored = _columns(col_width, gaps, row_starts, opts.page.wrap == "snake", margin)
        u_total = max(x + w for x, w in zip(col_left, col_width, strict=True)) + margin
    else:
        cursor = margin + (opts.lane_heading if lanes else 0.0)
        for w, gap in zip(col_width, gaps, strict=True):
            col_left.append(cursor)
            cursor += w + gap
        u_total = cursor - gaps[-1] + margin if rows else 2 * margin

    n_lanes = n_bands if n_bands > 1 else max(len(lanes), 1)
    # a lane band must contain the padding of the group boxes that touch its edges, and the snapping of their coordinates
    loop_reach = 0.2 + 0.1 * (most_loops - 1) + 2 * GRID if most_loops else 0.0
    # a heading taller than a group's padding grows the box at its top, so the lane and the gap between tracks leave room
    pad = opts.group_padding
    base = pad * (2 if parent_of else 1)

    def loops_above(g: str) -> float:
        """How far a member's self-loops reach above it, where a heading must clear them: nothing in a top-down flow."""
        counts = [loop_count[m] for m in members_of[g] if m in loop_count]
        return 0.0 if top_down or not counts else 0.2 + 0.1 * (max(counts) - 1) + GRID

    def reach(g: str) -> float:
        """How far above its topmost member a group's box can reach: its padding or heading, and a parent's clears its children's."""
        own = max(heading_of.get(g, (0.0, 0.0))[1] + loops_above(g), pad)
        kids = [reach(c) for c, p in parent_of.items() if p == g and members_of[c]]
        return max(2 * pad if kids else pad, max(kids, default=0.0) + own)

    lifts = [reach(g) - base for g in groups if members_of[g]]
    lift = _ceil(max([0.0, *lifts]))
    lane_pad = (
        max(opts.lane_padding, opts.group_padding * (2 if parent_of else 1) + (3 + slack) * GRID + lift, loop_reach)
        if lanes or n_bands > 1
        else 0.0
    )
    # between tracks, a group's loops and padding reach the track below, which keeps a grid step clear of them and two more for snapping
    track_clear = max(base, 0.2 + 0.1 * (most_loops - 1) + GRID if most_loops else 0.0) + base + (3 + slack) * GRID
    track_keys = sorted({(s.lane, s.track) for s in slots.values()})
    track_height: dict[tuple[int, tuple[int, int]], float] = {}
    for key in track_keys:
        best = 0.0
        for row in rows:
            members = [slots[k] for k in row if (slots[k].lane, slots[k].track) == key]
            if members:
                best = max(best, math.fsum(m.v_extent for m in members) + v_gap * (len(members) - 1))
        track_height[key] = best
    track_top: dict[tuple[int, tuple[int, int]], float] = {}
    lane_top: list[float] = []
    lane_bottom: list[float] = []
    # a lane holds the labels of the edges that stay in it, stacked if they must, since a label stays inside its lanes
    stacked_here: dict[int, list[float]] = {}
    for (source, target), size in zip(edges, opts.edge_labels or (None,) * len(edges), strict=True):
        ends = {lane_index[lane] for i in (source, target) if (lane := by_id[i].lane) is not None}
        if size is not None and len(ends) == 1:
            stacked_here.setdefault(ends.pop(), []).append(size[1] + 0.02)
    cursor = margin
    for lane in range(n_lanes):
        lane_top.append(cursor)
        cursor += lane_pad
        first = True
        for key in (k for k in track_keys if k[0] == lane):
            if not first:
                cursor += max(v_gap + 4 * opts.group_padding + (0.0 if top_down else lift) + slack * GRID, track_clear)
            first = False
            track_top[key] = cursor
            cursor += track_height[key]
        cursor += lane_pad + math.fsum(stacked_here.get(lane, ()))
        lane_bottom.append(cursor)
    v_total = cursor + margin
    for row in rows:
        runs: dict[tuple[int, tuple[int, int]], list[_Slot]] = {}
        for k in row:
            runs.setdefault((slots[k].lane, slots[k].track), []).append(slots[k])
        for key, members in runs.items():
            # fsum, because sum() on floats changed its rounding in 3.12 and the bytes must not depend on the version
            used = math.fsum(m.v_extent for m in members) + v_gap * (len(members) - 1)
            at = track_top[key] + (track_height[key] - used) / 2
            for m in members:
                m.v = snap(at + m.v_extent / 2)  # on the grid, so even extents put both borders on it
                at += m.v_extent + v_gap
    bounds = {key: (track_top[key], track_top[key] + track_height[key]) for key in track_keys}
    if opts.straighten_sweeps > 0:
        near_up: dict[_Key, list[_Key]] = {k: [] for k in slots}
        near_down: dict[_Key, list[_Key]] = {k: [] for k in slots}
        for chain in chains:
            for a, b in pairwise(chain):
                near_down[a].append(b)
                near_up[b].append(a)
        _straighten(rows, slots, near_up, near_down, bounds, v_gap, opts.straighten_sweeps, blocks)
    _align_blocks(rows, slots, bounds, v_gap, blocks)

    def centre_u(slot: _Slot) -> float:
        """The middle of a slot's column, along the flow."""
        return snap(col_left[slot.layer] + col_width[slot.layer] / 2)

    def right_u(slot: _Slot) -> float:
        """Where an edge leaves a slot: its far border along the flow, or the column's for a dummy; the physical left border in a mirrored row."""
        half = (slot.u_extent if slot.real else col_width[slot.layer]) / 2
        return centre_u(slot) + (-half if mirrored[slot.layer] else half)

    def left_u(slot: _Slot) -> float:
        """Where an edge arrives at a slot: its near border along the flow, or the column's for a dummy; the physical right border in a mirrored row."""
        half = (slot.u_extent if slot.real else col_width[slot.layer]) / 2
        return centre_u(slot) + (half if mirrored[slot.layer] else -half)

    def rect_of(node_id: str) -> _Rect:
        """A node's rectangle as (u low, u high, v low, v high)."""
        s = slots[node_id]
        a, b = sorted((left_u(s), right_u(s)))
        return (a, b, s.v - s.v_extent / 2, s.v + s.v_extent / 2)

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
                reach_u = 0.3 + extra + GRID
                rects.append(
                    (lo_a - reach_u, hi_a, lo_b - 0.2 - extra - GRID, hi_b)
                    if mirrored[slots[m].layer]
                    else (lo_a, hi_a + reach_u, lo_b - 0.2 - extra - GRID, hi_b)
                )
        if rects:
            group_rect[g] = (
                min(r[0] for r in rects),
                max(r[1] for r in rects),
                min(r[2] for r in rects),
                max(r[3] for r in rects),
            )

    # a heading widens its box and lifts its top clear of the members, children before parents so a parent holds them
    top, across = (0, 2) if top_down else (2, 0)  # the index of the top border and of the left border in a _Rect
    grown: set[str] = set()
    for g in sorted(group_rect, key=lambda name: name in parent_of.values()):
        r = list(group_rect[g])
        kids = [c for c, p in parent_of.items() if p == g and c in group_rect]
        for c in kids:
            # from the finished child box, which a self-loop may have pushed past its padding
            lo_a, hi_a, lo_b, hi_b = group_rect[c]
            wide = [
                min(r[0], lo_a - opts.group_padding),
                max(r[1], hi_a + opts.group_padding),
                min(r[2], lo_b - opts.group_padding),
                max(r[3], hi_b + opts.group_padding),
            ]
            if wide != r:
                r = wide
                grown.add(g)
        if g in heading_of:
            width, height = heading_of[g]
            held = min(
                [rect_of(m)[top] - (loops_above(g) if m in loop_count else 0.0) for m in members_of[g]]
                + [group_rect[c][top] for c in kids]
            )
            if held - r[top] < height - _EPS:
                r[top] -= _ceil(height - (held - r[top]))
                grown.add(g)
            if r[across + 1] - r[across] < width - _EPS:
                wider = _even(width - (r[across + 1] - r[across]))
                r[across] -= wider / 2
                r[across + 1] += wider / 2
                grown.add(g)
        # borders go outward to the grid first, so the box keeps every inch asked of it; an odd span grows a step
        # to keep its centre on the grid too
        for lo in (0, 2):
            r[lo], r[lo + 1] = _floor(r[lo]), _ceil(r[lo + 1])
            r[lo + 1] = snap(r[lo + 1] + GRID * (round((r[lo + 1] - r[lo]) / GRID) % 2))
        group_rect[g] = (r[0], r[1], r[2], r[3])
    # the rounded boxes decide whether the lanes and the gaps between tracks held them; if not, ask for a step more of each
    blame = _blame(group_rect, grown, nodes, members_of, parent_of, rect_of, heading_of)
    escaped = lanes and any(
        r[2] < lane_top[lo] - _EPS or r[3] > lane_bottom[hi] + _EPS
        for g, r in group_rect.items()
        if (spanned := sorted({lane_index[lane] for m in members_of[g] if (lane := by_id[m].lane) is not None}))
        for lo, hi in [(spanned[0], spanned[-1])]
    )
    if blame is not None or escaped:
        # ponytail: a whole further layout per step; derive the slack from the boxes if a graph ever needs more than a few
        if slack < 3:
            return _lay_out(nodes, edges, lanes, groups, options, own_points, spent, slack + 1, no_l)
        if blame is not None:
            raise GraphError(blame)

    # a group box can reach past the margin, so the page grows and shifts to hold it, plus a step for snapping
    lo_u = lo_v = 0.0
    hi_u, hi_v = u_total, v_total
    room = max(margin, _CORRIDOR) + GRID  # clear space round a group, where a route can pass it
    if n_bands > 1:  # a fold route runs round the end of a row, so the columns keep the same clear space
        lo_u = min(lo_u, min(col_left) - room)
        hi_u = max(hi_u, max(x + w for x, w in zip(col_left, col_width, strict=True)) + room)
    for r in group_rect.values():
        lo_u, hi_u = min(lo_u, r[0] - room), max(hi_u, r[1] + room)
        lo_v, hi_v = min(lo_v, r[2] - room), max(hi_v, r[3] + room)
    for node_id, count in loop_count.items():
        lo_a, hi_a, lo_b, _hi_b = rect_of(node_id)
        extra = 0.1 * (count - 1)
        lo_v = min(lo_v, lo_b - 0.2 - extra - GRID)
        if mirrored[slots[node_id].layer]:
            lo_u = min(lo_u, lo_a - 0.3 - extra - GRID)
        else:
            hi_u = max(hi_u, hi_a + 0.3 + extra + GRID)
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

    groups_of = {n.id: {g for g, ms in members_of.items() if n.id in ms} for n in nodes}
    twins = Counter((c[0], c[-1]) for c in chains)
    twin_seen: Counter[tuple[_Key, _Key]] = Counter()
    twin_rank: list[int] = []
    # every edge that leaves a node's far side (self-loops first, they nest outermost last) or arrives at its near side
    # gets a border point of its own, ordered by where its other end lies so the edges do not cross at the node
    side_edges: dict[tuple[_Key, bool], list[tuple[int, float, int]]] = {}
    for n, chain in enumerate(chains):
        if chain[0] == chain[-1]:
            side_edges.setdefault((chain[0], True), []).append((0, 0.0, n))
            continue
        side_edges.setdefault((chain[0], True), []).append((1, slots[chain[1]].v, n))
        side_edges.setdefault((chain[-1], False), []).append((1, slots[chain[-2]].v, n))
    end_offset: dict[tuple[int, bool], float] = {}
    side_order: dict[tuple[_Key, bool], list[int]] = {}

    def spread_side(key: _Key, leaving: bool, items: list[tuple[int, float, int]]) -> None:
        """Give the edges of one side of a box ports of their own, ordered by `items`, unless the box is too small for them all."""
        extent = slots[key].v_extent
        if own_points and round(extent / GRID) // len(
            items
        ):  # a node too small for them all keeps the offsets its parallel edges had
            side_order[(key, leaving)] = [n for _kind, _v, n in sorted(items)]
            for rank, (_kind, _v, n) in enumerate(sorted(items)):
                end_offset[(n, leaving)] = _spread(len(items), extent, key, opts.port_pitch)[rank]

    layer_slots: list[list[_Slot]] = [[] for _ in range(n_layers)]
    for slot in slots.values():
        layer_slots[slot.layer].append(slot)

    def l_side(n: int, leaving: bool) -> str | None:
        """The side across the flow (`low` or `high`) edge `n` takes for an L route, or None when it keeps its Z route.

        With `leaving` the edge leaves its source by that side, drops to the target's row and runs along it; without, it
        runs along the source's row and enters the target by that side. It needs boxes that do not overlap by a port
        pitch, so no straight run exists. The stub must be clear of every other slot in its box's layer, the run clear of
        every real box in the layers it crosses, and neither may enter a group the edge does not belong to.
        """
        chain = chains[n]
        if not own_points or n_bands > 1 or chain[0] == chain[-1] or n in banned:
            return None
        a, b = slots[chain[0]], slots[chain[-1]]
        if (n, not leaving) not in end_offset:
            return None
        if (
            min(a.v + a.v_extent / 2, b.v + b.v_extent / 2) - max(a.v - a.v_extent / 2, b.v - b.v_extent / 2)
            >= opts.port_pitch - 1e-9
        ):
            return None
        stem_key, stem, other = (chain[0], a, b) if leaving else (chain[-1], b, a)
        row = other.v + end_offset[(n, not leaving)]
        side = "high" if row > stem.v else "low"
        if abs(row - stem.v) < stem.v_extent / 2 + opts.port_pitch:
            return None  # the row lies on the stem's box or too near it for a stub of any length
        if side == "low" and stem_key in loop_count:
            return None  # the loops of a node leave by its low side
        border = stem.v + (stem.v_extent if side == "high" else -stem.v_extent) / 2
        low, high = sorted((border, row))
        if any(
            slot is not stem and slot.v - slot.v_extent / 2 - GRID < high and slot.v + slot.v_extent / 2 + GRID > low
            for slot in layer_slots[stem.layer]
        ):
            return None
        if any(
            slot.real and slot.v - slot.v_extent / 2 - GRID < row < slot.v + slot.v_extent / 2 + GRID
            for layer in range(a.layer + 1, b.layer)
            for slot in layer_slots[layer]
        ):
            return None
        own = groups_of[str(chain[0])] | groups_of[str(chain[-1])]
        keep = max(clear - GRID, GRID)
        reach = centre_u(stem) - stem.u_extent / 2, centre_u(stem), centre_u(stem) + stem.u_extent / 2
        run_from, run_to = (reach[0], left_u(b)) if leaving else (right_u(a), reach[2])
        for g, (ulo, uhi, vlo, vhi) in group_rect.items():
            if g not in own:
                fenced = (ulo - keep, uhi + keep, vlo - keep, vhi + keep)
                if _enters((run_from, row), (run_to, row), fenced) or any(
                    _enters((x, border), (x, row), fenced) for x in reach
                ):
                    return None
        return side

    # an L edge takes a port on the low or high side of its stem box, the stubs nested so they do not cross: along the
    # flow, arrivals come first and the nearest of them first, then departures and the farthest of them first
    banned = set(no_l)
    l_off: dict[int, float] = {}
    l_side_of: dict[int, str] = {}
    l_leaving: dict[int, bool] = {}
    for attempt in range(4):
        end_offset.clear()
        side_order.clear()
        l_off.clear()
        sides = {k: list(v) for k, v in side_edges.items()}
        for (key, leaving), items in sides.items():
            spread_side(key, leaving, items)
        l_found: dict[tuple[_Key, str], list[tuple[int, float, int]]] = {}
        l_taken: dict[int, tuple[bool, str]] = {}
        for n, chain in enumerate(chains):
            for leaving in (True, False):
                side = l_side(n, leaving) if (n, leaving) in end_offset else None
                if side is not None:
                    far = abs(
                        slots[chain[-1]].v
                        + end_offset.get((n, False), 0.0)
                        - slots[chain[0]].v
                        - end_offset.get((n, True), 0.0)
                    )
                    key = chain[0] if leaving else chain[-1]
                    l_found.setdefault((key, side), []).append((1, -far, n) if leaving else (0, far, n))
                    l_taken[n] = (leaving, side)
                    break
        for (key, _side), ports in l_found.items():
            if round(slots[key].u_extent / GRID) // len(ports) == 0:
                for _kind, _far, n in ports:  # a box too narrow for a port each keeps its Z routes
                    del l_taken[n]
                continue
            for (_kind, _far, n), off in zip(
                sorted(ports), _spread(len(ports), slots[key].u_extent, key, opts.port_pitch), strict=True
            ):
                l_off[n] = off
        l_leaving.clear()
        l_side_of.clear()
        for n, (leaving, side) in l_taken.items():
            l_leaving[n], l_side_of[n] = leaving, side
            key, was = (chains[n][0], True) if leaving else (chains[n][-1], False)
            sides[(key, was)] = [item for item in sides[(key, was)] if item[2] != n]
            end_offset.pop((n, was), None)
        for key, was in dict.fromkeys(
            (chains[n][0], True) if leaving else (chains[n][-1], False) for n, (leaving, _s) in l_taken.items()
        ):
            side_order.pop((key, was), None)
            if sides[(key, was)]:
                spread_side(key, was, sides[(key, was)])
        bad = {n for n, (leaving, _s) in l_taken.items() if l_side(n, leaving) is None}
        if not bad:
            break
        # a third failure gives every L route up, so the last pass has none left to check
        banned |= bad if attempt < 2 else set(l_taken)

    def port_window(n: int, leaving: bool) -> tuple[float, float]:
        """The rows edge `n`'s port on its box may take: on the side, and a pitch from its neighbours, which keeps their order."""
        key = chains[n][0] if leaving else chains[n][-1]
        slot = slots[key]
        order = side_order[(key, leaving)]
        at = order.index(n)
        reach = min(0.4 * slot.v_extent, slot.v_extent / 2 - GRID)
        offsets = [end_offset[(m, leaving)] for m in order]
        # a side already packed tighter than the pitch is held to the gap it has
        gap = min(
            max(0.1, min(opts.port_pitch, slot.v_extent / (len(order) + 1))), *(b - a for a, b in pairwise(offsets)), 1.0
        )
        low = slot.v - reach if not at else max(slot.v - reach, slot.v + offsets[at - 1] + gap)
        high = slot.v + reach if at == len(order) - 1 else min(slot.v + reach, slot.v + offsets[at + 1] - gap)
        return low, high

    def align_ports() -> None:
        """Give an edge between adjacent layers one row at both ends when its boxes overlap by a port pitch, so it runs straight."""
        hops: dict[int, list[tuple[int, int]]] = {}
        for m, chain in enumerate(chains):
            if chain[0] != chain[-1] and m not in l_off:
                for i in range(len(chain) - 1):
                    hops.setdefault(slots[chain[i]].layer, []).append((m, i))

        def row_at(m: int, i: int) -> float:
            """Where edge `m` currently meets the slot at index `i` of its chain."""
            chain = chains[m]
            extra = (
                end_offset.get((m, True), 0.0) if i == 0 else end_offset.get((m, False), 0.0) if i == len(chain) - 1 else 0.0
            )
            return slots[chain[i]].v + extra

        for n, chain in enumerate(chains):
            if len(chain) != 2 or chain[0] == chain[1] or (n, True) not in end_offset or (n, False) not in end_offset:
                continue
            a, b = slots[chain[0]], slots[chain[1]]
            if band_of_layer[a.layer] != band_of_layer[b.layer]:
                continue
            top = min(a.v + a.v_extent / 2, b.v + b.v_extent / 2)
            bottom = max(a.v - a.v_extent / 2, b.v - b.v_extent / 2)
            if top - bottom < opts.port_pitch - 1e-9:
                continue
            (a_low, a_high), (b_low, b_high) = port_window(n, True), port_window(n, False)
            first, last = math.ceil(max(a_low, b_low) / GRID - 1e-9), math.floor(min(a_high, b_high) / GRID + 1e-9)
            if first > last:
                continue
            # nearest the middle of the overlap on the grid, the lower line on a tie
            row = snap(min(max(math.floor((top + bottom) / 2 / GRID + 0.5 - 1e-9), first), last) * GRID)
            if any(
                min(row_at(m, i), row_at(m, i + 1)) - GRID / 2 < row < max(row_at(m, i), row_at(m, i + 1)) + GRID / 2
                for m, i in hops.get(a.layer, ())
                if m != n
            ):
                continue
            end_offset[(n, True)] = row - a.v
            end_offset[(n, False)] = row - b.v

    align_ports()
    rows_of: list[list[float]] = []
    for chain, (source, target) in zip(chains, edges, strict=True):
        ends = (chain[0], chain[-1])
        twin_rank.append(twin_seen[ends])
        twin_seen[ends] += 1
        n = len(rows_of)
        # a pass-through row is nudged within its dummy slot, so it rarely lies on the row of a box another edge uses
        nudge = _NUDGES[n % len(_NUDGES)]
        vs = [slots[k].v if slots[k].real else slots[k].v + nudge for k in chain]
        if source != target:
            # parallel edges leave and arrive at different points along the border so they never overlay
            narrow = min((source, target), key=lambda k: slots[k].v_extent)
            off = _spread(twins[ends], slots[narrow].v_extent, narrow, opts.port_pitch)[twin_rank[-1]]
            vs[0] += end_offset.get((n, True), off)
            vs[-1] += end_offset.get((n, False), off)
        rows_of.append(vs)

    gap_edges: dict[int, list[tuple[float, float, int, int]]] = {}
    for n, chain in enumerate(chains):
        if chain[0] == chain[-1] or n in l_off:
            continue  # a loop has no channel, and an L route runs on its own row
        for hop, (a, b) in enumerate(pairwise(chain)):
            if band_of_layer[slots[a].layer] != band_of_layer[slots[b].layer]:
                continue  # a fold hop has no channel of its own in a gap
            gap_edges.setdefault(slots[a].layer, []).append((min(slots[a].v, slots[b].v), max(slots[a].v, slots[b].v), n, hop))
    channel: dict[tuple[int, int], float] = {}

    def room_for(n: int, i: int, new: float) -> bool:
        """Whether row `i` of edge `n` can move to `new` and still sit on its box or inside its dummy."""
        slot = slots[chains[n][i]]
        return abs(new - slot.v) <= slot.v_extent / 2 - GRID

    def shares_point(n: int, i: int, new: float) -> bool:
        """Whether moving row `i` of edge `n` to `new` puts its end on the border point another edge has on that side."""
        if not own_points or i not in (0, len(chains[n]) - 1):
            return False
        end = 0 if i == 0 else -1
        return any(
            m != n and chains[m][end] == chains[n][i] and abs(rows_of[m][end] - new) < GRID / 2 for m in range(len(chains))
        )

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
            # nesting only orders channels; it never moves a row, so a cycle of it falls back to the heap's index order
            before = [
                sorted({*preds, *nested}) for preds, nested in zip(need, _nests_left(items, rows_of, chains), strict=True)
            ]
            preds_of = [list(preds) for preds in before]
            after: list[list[int]] = [[] for _ in items]
            for idx, preds in enumerate(before):
                for f in preds:
                    after[f].append(idx)
            ready = [idx for idx, preds in enumerate(before) if not preds]
            heapq.heapify(ready)
            order: list[int] = []
            left_over = set(range(len(items)))
            while left_over:
                idx = heapq.heappop(ready) if ready else _break_cycle(left_over, before, after)
                if idx not in left_over:
                    continue
                left_over.discard(idx)
                order.append(idx)
                for nxt in after[idx]:
                    before[nxt] = [f for f in before[nxt] if f != idx]
                    if not before[nxt] and nxt in left_over:
                        heapq.heappush(ready, nxt)
            # hops whose runs do not meet share a channel line, so siblings drop to one height unless a run is in the way
            tier: dict[int, int] = {}
            tier_runs: dict[int, list[tuple[float, float]]] = {}
            for idx in order:
                n, hop = items[idx][2], items[idx][3]
                span = tuple(sorted((rows_of[n][hop], rows_of[n][hop + 1])))
                slot_tier = max((tier[f] + 1 for f in preds_of[idx] if f in tier), default=0)
                while any(span[0] <= b + GRID and a <= span[1] + GRID for a, b in tier_runs.get(slot_tier, ())):
                    slot_tier += 1
                tier[idx] = slot_tier
                tier_runs.setdefault(slot_tier, []).append((span[0], span[1]))
            for idx, preds in enumerate(need):
                for f in preds:
                    if tier[f] >= tier[idx]:
                        stuck.append((items[idx][2], items[idx][3], items[f][2], items[f][3]))
            zone = loop_zone.get(layer, 0.0)
            # the gap of a mirrored layer lies on its physical left, and its channels fill it away from the column
            sign = -1 if mirrored[layer] else 1
            left = col_left[layer] - zone if mirrored[layer] else col_left[layer] + col_width[layer] + zone
            lines = max(tier.values(), default=-1) + 2
            for idx in order:
                channel[(items[idx][2], items[idx][3])] = left + sign * (gaps[layer] - zone) * (tier[idx] + 1) / lines
        if not stuck:
            break
        # two edges swapping rows cannot both be satisfied, so one of the two rows moves a little
        for en, eh, fn, fh in stuck:
            for n, i in ((en, eh + 1), (fn, fh)):
                moved = next(
                    (
                        d
                        for d in (0.03, -0.03, 0.07, -0.07)
                        if room_for(n, i, rows_of[n][i] + d) and not shares_point(n, i, rows_of[n][i] + d)
                    ),
                    None,
                )
                if moved is not None:
                    rows_of[n][i] += moved
                    break

    # lines a detour may turn on: the middle of each gap between columns, round each group, and between the tracks
    base_xs = {-shift_u, u_total - shift_u} if not lanes else {u_total - shift_u}
    for layer in range(n_layers - 1):
        if band_of_layer[layer] == band_of_layer[layer + 1]:
            base_xs.add(
                col_left[layer] - gaps[layer] / 2 if mirrored[layer] else col_left[layer] + col_width[layer] + gaps[layer] / 2
            )
    end_xs = {
        x
        for ulo, uhi, _vlo, _vhi in group_rect.values()
        for x in (ulo - max(clear, GRID) - GRID, uhi + max(clear, GRID) + GRID)
    }
    flat_ys = (
        {y for lane in range(n_lanes) for y in (lane_top[lane] + GRID, lane_bottom[lane] - GRID)}
        if lanes
        else {-shift_v, v_total - shift_v, *(lane_bottom[i] for i in range(n_bands - 1))}
    )
    for a, b in pairwise(track_keys):
        if a[0] == b[0]:
            flat_ys.add((track_top[a] + track_height[a] + track_top[b]) / 2)
    end_ys = {
        y
        for _ulo, _uhi, vlo, vhi in group_rect.values()
        for y in (vlo - max(clear, GRID) - GRID, vhi + max(clear, GRID) + GRID)
    }
    base_xs = {x for x in base_xs | end_xs if -shift_u <= x <= u_total - shift_u} - end_xs
    flat_ys = {y for y in flat_ys | end_ys if -shift_v <= y <= v_total - shift_v} - end_ys
    end_xs = {x for x in end_xs if -shift_u <= x <= u_total - shift_u}
    end_ys = {y for y in end_ys if -shift_v <= y <= v_total - shift_v}
    # the outermost group lines are the free corridors round the drawing, so they get side-by-side copies too
    base_xs |= {*(f(end_xs) for f in (min, max) if end_xs)}
    flat_ys |= {*(f(end_ys) for f in (min, max) if end_ys)}
    solids = [rect_of(n.id) for n in nodes]

    # the hops that cross a row boundary leave the near-boundary side of one column and enter the other, by a level of their own
    fold_hops: dict[int, list[tuple[float, int, int]]] = {}
    for n, chain in enumerate(chains):
        if chain[0] != chain[-1]:
            for hop, (a, b) in enumerate(pairwise(chain)):
                if band_of_layer[slots[a].layer] != band_of_layer[slots[b].layer]:
                    fold_hops.setdefault(band_of_layer[slots[a].layer], []).append((slots[a].v, n, hop))
    loop_extra: dict[_Key, int] = {}  # fold arrivals that share a self-looped node's top with its loops
    fold_plan: dict[tuple[int, int], tuple[float, float, float, float, float]] = {}  # (n, hop) -> (ua, ub, ya, yb, level)
    for band, found in fold_hops.items():
        found.sort()
        count = len(found)
        width = min(
            min(
                (slots[chains[n][h]].u_extent if slots[chains[n][h]].real else col_width[slots[chains[n][h]].layer])
                for _v, n, h in found
            ),
            min(
                (
                    slots[chains[n][h + 1]].u_extent
                    if slots[chains[n][h + 1]].real
                    else col_width[slots[chains[n][h + 1]].layer]
                )
                for _v, n, h in found
            ),
        )
        # a boundary too narrow for a port each keeps the column centre, and the search or the spacing pass separates the routes
        offsets = _spread(count, width, band, opts.channel_pitch) if round(width / GRID) // count else [0.0] * count
        ports = [
            (centre_u(slots[chains[n][h]]) + off, centre_u(slots[chains[n][h + 1]]) + off, n, h)
            for off, (_v, n, h) in zip(offsets, found, strict=True)
        ]
        # a self-loop uses border points on the top of its node, so the folds that arrive there share that node's spread with it
        arriving: dict[_Key, list[int]] = {}
        for idx, (_ua, _ub, n, h) in enumerate(ports):
            key = chains[n][h + 1]
            if slots[key].real and key in loop_count:
                arriving.setdefault(key, []).append(idx)
        for key, idxs in arriving.items():
            loops = twins[(key, key)]
            if round(slots[key].u_extent / GRID) // (loops + len(idxs)):
                loop_extra[key] = loop_extra.get(key, 0) + len(idxs)
                spread = _spread(loops + loop_extra[key], slots[key].u_extent, key, opts.port_pitch)
                for rank, idx in enumerate(idxs):
                    ua, _ub, n, h = ports[idx]
                    ports[idx] = (ua, centre_u(slots[key]) - spread[loops + loop_extra[key] - len(idxs) + rank], n, h)
        # a corridor of 2 * lane_pad lies on the boundary; levels are a channel apart, or closer when it is crowded
        top_level = lane_bottom[band] - lane_pad
        step = min(_CHANNEL, 2 * lane_pad / (count + 1))
        right = ports[0][1] > ports[0][0]
        # the edge with the larger start column takes the higher level for a jog to the right, the smaller for a jog to the left
        by_level = sorted(ports, key=lambda port: -port[0] if right else port[0])
        for level_rank, (ua, ub, n, h) in enumerate(by_level):
            sa, sb = slots[chains[n][h]], slots[chains[n][h + 1]]
            ya = sa.v + sa.v_extent / 2 if sa.real else rows_of[n][h]
            yb = sb.v - sb.v_extent / 2 if sb.real else rows_of[n][h + 1]
            fold_plan[(n, h)] = (ua, ub, ya, yb, top_level + (level_rank + 1) * step)

    # the hops that cross a row boundary leave the near-boundary side of one column and enter the other, by a level of their own
    fold_hops: dict[int, list[tuple[float, int, int]]] = {}
    for n, chain in enumerate(chains):
        if chain[0] != chain[-1]:
            for hop, (a, b) in enumerate(pairwise(chain)):
                if band_of_layer[slots[a].layer] != band_of_layer[slots[b].layer]:
                    fold_hops.setdefault(band_of_layer[slots[a].layer], []).append((slots[a].v, n, hop))
    loop_extra: dict[_Key, int] = {}  # fold arrivals that share a self-looped node's top with its loops
    fold_plan: dict[tuple[int, int], tuple[float, float, float, float, float]] = {}  # (n, hop) -> (ua, ub, ya, yb, level)
    for band, found in fold_hops.items():
        found.sort()
        count = len(found)
        width = min(
            min(
                (slots[chains[n][h]].u_extent if slots[chains[n][h]].real else col_width[slots[chains[n][h]].layer])
                for _v, n, h in found
            ),
            min(
                (
                    slots[chains[n][h + 1]].u_extent
                    if slots[chains[n][h + 1]].real
                    else col_width[slots[chains[n][h + 1]].layer]
                )
                for _v, n, h in found
            ),
        )
        # a boundary too narrow for a port each keeps the column centre, and the search or the spacing pass separates the routes
        offsets = _spread(count, width, band) if round(width / GRID) // count else [0.0] * count
        ports = [
            (centre_u(slots[chains[n][h]]) + off, centre_u(slots[chains[n][h + 1]]) + off, n, h)
            for off, (_v, n, h) in zip(offsets, found, strict=True)
        ]
        # a self-loop uses border points on the top of its node, so the folds that arrive there share that node's spread with it
        arriving: dict[_Key, list[int]] = {}
        for idx, (_ua, _ub, n, h) in enumerate(ports):
            key = chains[n][h + 1]
            if slots[key].real and key in loop_count:
                arriving.setdefault(key, []).append(idx)
        for key, idxs in arriving.items():
            loops = twins[(key, key)]
            if round(slots[key].u_extent / GRID) // (loops + len(idxs)):
                loop_extra[key] = loop_extra.get(key, 0) + len(idxs)
                spread = _spread(loops + loop_extra[key], slots[key].u_extent, key)
                for rank, idx in enumerate(idxs):
                    ua, _ub, n, h = ports[idx]
                    ports[idx] = (ua, centre_u(slots[key]) - spread[loops + loop_extra[key] - len(idxs) + rank], n, h)
        # a corridor of 2 * lane_pad lies on the boundary; levels are a channel apart, or closer when it is crowded
        top_level = lane_bottom[band] - lane_pad
        step = min(_CHANNEL, 2 * lane_pad / (count + 1))
        right = ports[0][1] > ports[0][0]
        # the edge with the larger start column takes the higher level for a jog to the right, the smaller for a jog to the left
        by_level = sorted(ports, key=lambda port: -port[0] if right else port[0])
        for level_rank, (ua, ub, n, h) in enumerate(by_level):
            sa, sb = slots[chains[n][h]], slots[chains[n][h + 1]]
            ya = sa.v + sa.v_extent / 2 if sa.real else rows_of[n][h]
            yb = sb.v - sb.v_extent / 2 if sb.real else rows_of[n][h + 1]
            fold_plan[(n, h)] = (ua, ub, ya, yb, top_level + (level_rank + 1) * step)

    routes: dict[tuple[str, str, int], tuple[tuple[float, float], ...]] = {}
    seen_pairs: dict[tuple[str, str], int] = {}
    built: list[tuple[list[tuple[float, float]], str, str, list[_Key], int]] = []
    # per fold edge, the path the search starts from if its fold route is blocked
    stubs: dict[int, list[tuple[float, float]]] = {}
    for n, ((source, target), flip, chain) in enumerate(zip(edges, flipped, chains, strict=True)):
        parallel = seen_pairs.get((source, target), 0)
        seen_pairs[(source, target)] = parallel + 1
        first_slot = slots[chain[0]]
        ends = (chain[0], chain[-1])
        i = twin_rank[n]
        if source == target:
            r = first_slot.v_extent / 2 + 0.2 + 0.1 * i
            c = (
                centre_u(first_slot)
                - _spread(twins[ends] + loop_extra.get(chain[0], 0), first_slot.u_extent, source, opts.port_pitch)[i]
            )
            dv = end_offset.get((n, True), _spread(twins[ends], first_slot.v_extent, source, opts.port_pitch)[i])
            out_u = right_u(first_slot) + (-1 if mirrored[first_slot.layer] else 1) * (0.3 + 0.1 * i)
            bends = [
                (right_u(first_slot), first_slot.v + dv),
                (out_u, first_slot.v + dv),
                (out_u, first_slot.v - r),
                (c, first_slot.v - r),
                (c, first_slot.v - first_slot.v_extent / 2),
            ]
        else:
            vs = rows_of[n]
            if n in l_off:
                last_slot = slots[chain[-1]]
                if l_leaving[n]:
                    stem = centre_u(first_slot) + l_off[n]
                    edge_v = first_slot.v + (first_slot.v_extent if l_side_of[n] == "high" else -first_slot.v_extent) / 2
                    bends: list[tuple[float, float]] = [(stem, edge_v), (stem, vs[-1]), (left_u(last_slot), vs[-1])]
                else:
                    stem = centre_u(last_slot) + l_off[n]
                    edge_v = last_slot.v + (last_slot.v_extent if l_side_of[n] == "high" else -last_slot.v_extent) / 2
                    bends = [(right_u(first_slot), vs[0]), (stem, vs[0]), (stem, edge_v)]
            else:
                bends = [] if (n, 0) in fold_plan else [(right_u(first_slot), vs[0])]
            stub = [(right_u(first_slot), vs[0])]
            for hop, sb in enumerate(slots[k] for k in ([] if n in l_off else chain[1:])):
                sa = slots[chain[hop]]
                if (n, hop) in channel:
                    cu = channel[(n, hop)]
                    bends += [(cu, vs[hop]), (cu, vs[hop + 1]), (left_u(sb), vs[hop + 1])]
                    stub += bends[-3:]
                else:
                    # a fold hop drops from its column to a level in the corridor, runs across, and drops into the next row
                    ua, ub, ya, yb, level = fold_plan[(n, hop)]
                    if hop:
                        bends.pop()  # the pass-through of the dummy before it, which now ends at the port column
                        bends.append((ua, vs[hop]))
                    bends += [(ua, ya), (ua, level), (ub, level), (ub, yb)]
                    # the stub leaves and arrives the way a route must, for the search to route when the fold route is blocked
                    out_x = right_u(sa) + (-1 if mirrored[sa.layer] else 1) * gaps[sa.layer] / 2
                    in_x = left_u(sb) - (-1 if mirrored[sb.layer] else 1) * gaps[sb.layer - 1] / 2
                    mid = (vs[hop] + vs[hop + 1]) / 2
                    stub += [(out_x, vs[hop]), (out_x, mid), (in_x, mid), (in_x, vs[hop + 1]), (left_u(sb), vs[hop + 1])]
                if hop + 1 < len(chain) - 1:
                    bends.append((right_u(sb), vs[hop + 1]))
                    stub.append((right_u(sb), vs[hop + 1]))
            if flip:
                stub.reverse()
            if any((n, k) in fold_plan for k in range(len(chain) - 1)):
                stubs[n] = [(snap(u), snap(v)) for u, v in stub]
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

    def shares_a_run(n: int, pts: list[tuple[float, float]]) -> bool:
        """Whether `pts` runs along a route already placed, other than one that shares an end point with edge `n`."""
        mine = {pts[0], pts[-1]}
        for a, b in pairwise(pts):
            key = (0, round(a[1], 4)) if a[1] == b[1] else (1, round(a[0], 4))
            low, high = (min(a[0], b[0]), max(a[0], b[0])) if key[0] == 0 else (min(a[1], b[1]), max(a[1], b[1]))
            if any(min(high, hi) - max(low, lo) > _EPS and not ends_of[m] & mine for lo, hi, m in occupied.get(key, ())):
                return True
        return False

    def lane_span(chain: list[_Key]) -> tuple[float, float]:
        """The range across the flow that an edge between the ends of `chain` may use."""
        if not lanes:
            return -shift_v, v_total - shift_v
        a, b = slots[chain[0]].lane, slots[chain[-1]].lane
        return lane_top[min(a, b)], lane_bottom[max(a, b)]

    # the heading of a box is text no route may cross, whichever group the route belongs to
    bands: list[_Rect] = []
    for g in group_rect:
        if g in heading_of:
            r, text_width = group_rect[g], heading_of[g][0]
            mid = (r[across] + r[across + 1]) / 2
            lo, hi = (mid - text_width / 2, mid + text_width / 2)
            bands.append((r[0], r[0] + heading_of[g][1], lo, hi) if top_down else (lo, hi, r[2], r[2] + heading_of[g][1]))
    foreign_of = [
        [
            *(
                (
                    r[0] - max(clear - GRID, GRID),
                    r[1] + max(clear - GRID, GRID),
                    r[2] - max(clear - GRID, GRID),
                    r[3] + max(clear - GRID, GRID),
                )
                for g, r in group_rect.items()
                if g not in groups_of[source] | groups_of[target]
            ),
            *bands,
        ]
        for _bends, source, target, _chain, _parallel in built
    ]
    # a route that would arrive through a heading is moved to arrive at the side of its box instead
    rerouted: set[int] = set()
    arrivals: dict[tuple[str, bool], list[tuple[int, int]]] = {}
    own_offset: dict[tuple[int, int], float] = {}

    def reattach(final: bool) -> None:
        """Move every end that would run through a heading to its box's side; the first pass only counts the ends per side."""
        for n, (bends, source, target, chain, _parallel) in enumerate(built):
            pts = [bends[0], *(b for a, b in pairwise(bends) if a != b)]
            if source == target or len(pts) < 2:
                continue
            for end in (0, -1):
                a, b = (pts[0], pts[1]) if end == 0 else (pts[-2], pts[-1])
                if any(_enters(a, b, band) for band in bands):
                    node_id = source if end == 0 else target
                    slot = slots[node_id]
                    far = pts[-1] if end == 0 else pts[0]
                    off = own_offset.get((n, end))
                    if off is None:
                        off = _spread(twins[(chain[0], chain[-1])], slot.u_extent, node_id, opts.port_pitch)[twin_rank[n]]
                    # self-loops leave and arrive on the low side, so a node that has one is entered on the other
                    low = far[1] < slot.v and node_id not in loop_count
                    arrivals.setdefault((node_id, low), []).append((n, end))
                    side = slot.v - slot.v_extent / 2 if low else slot.v + slot.v_extent / 2
                    pts[end] = (snap(centre_u(slot) - off), snap(side))
                    # one step outward gives the search the heading to leave or arrive with
                    out = (pts[end][0], side - 1 if low else side + 1)
                    pts = [pts[0], out, *pts[1:]] if end == 0 else [*pts[:-1], out, pts[-1]]
                    rerouted.add(n)
            if final and n in rerouted:
                built[n] = (pts, source, target, chain, _parallel)

    reattach(False)
    if l_off:
        # a heading moves an end to its box's low or high side, where the ports of an L route are, so those edges keep their Z routes
        taken_sides = {(node_id, "low" if low else "high") for node_id, low in arrivals}
        clash = frozenset(
            n for n in l_off if n in rerouted or (chains[n][0 if l_leaving[n] else -1], l_side_of[n]) in taken_sides
        )
        if clash:
            return _lay_out(nodes, edges, lanes, groups, options, own_points, spent, slack, no_l | clash)
    for (node_id, _low), ends_here in arrivals.items():
        extent = slots[node_id].u_extent
        if own_points and round(extent / GRID) // len(ends_here):  # as for the ends on a box's far and near sides
            for rank, end_key in enumerate(ends_here):
                own_offset[end_key] = _spread(len(ends_here), extent, node_id, opts.port_pitch)[rank]
    arrivals.clear()
    rerouted.clear()
    reattach(True)
    # a group's border is no place for a route to run, whichever group it belongs to
    borders = [
        line
        for r in group_rect.values()
        for line in ((1, r[0], r[2], r[3]), (1, r[1], r[2], r[3]), (0, r[2], r[0], r[1]), (0, r[3], r[0], r[1]))
    ]

    # the boxes by left edge and by bottom edge: a segment can enter only a box whose edge lies within one box-extent of it
    by_left = sorted(solids)
    solid_lefts = [r[0] for r in by_left]
    widest = max((r[1] - r[0] for r in by_left), default=0.0)
    by_bottom = sorted(solids, key=lambda r: r[2])
    solid_bottoms = [r[2] for r in by_bottom]
    tallest = max((r[3] - r[2] for r in by_bottom), default=0.0)

    def _solids_at(a: tuple[float, float], b: tuple[float, float]) -> list[_Rect]:
        """The boxes that a vertical segment a-b might enter: those whose left edge lies within a box width left of it."""
        return by_left[bisect_left(solid_lefts, a[0] - widest - _EPS) : bisect_right(solid_lefts, a[0] + _EPS)]

    def _solids_across(a: tuple[float, float], b: tuple[float, float]) -> list[_Rect]:
        """The boxes that a horizontal segment a-b might enter: those whose bottom edge lies within a box height below it."""
        return by_bottom[bisect_left(solid_bottoms, a[1] - tallest - _EPS) : bisect_right(solid_bottoms, a[1] + _EPS)]

    def runs_into_something(n: int, bends: list[tuple[float, float]]) -> bool:
        """Whether a route through `bends` enters a box or a group edge `n` does not belong to."""
        return any(
            _enters(a, b, r)
            for a, b in pairwise(bends)
            if a != b
            for r in (*foreign_of[n], *(_solids_at(a, b) if a[0] == b[0] else _solids_across(a, b)))
        )

    if l_off:
        blocked = frozenset(n for n in l_off if runs_into_something(n, built[n][0]))
        if blocked:  # the whole layout is redone with those edges on their Z routes, which the search can always start from
            return _lay_out(nodes, edges, lanes, groups, options, own_points, spent, slack, no_l | blocked)
    pending = []
    for n, (bends, source, target, chain, _parallel) in enumerate(built):
        foreign = foreign_of[n]
        hits = runs_into_something(n, bends)
        if source != target and n not in rerouted and n not in stubs and n not in l_off and len(_simplify(bends)) > 2:
            mine = {bends[0], bends[-1]}
            for cand in _candidates(_simplify(bends)):
                _spend(spent, len(cand))
                if not runs_into_something(n, cand) and not shares_a_run(n, cand):
                    bends, hits = cand, False
                    built[n] = (cand, source, target, chain, _parallel)
                    break
        if hits and n in stubs:
            built[n] = (stubs[n], source, target, chain, _parallel)
        if source != target and (n in rerouted or hits):
            pending.append((n, foreign))
        else:
            occupy(bends, n)
    # the lines round the whole drawing carry the routes that go the long way round, so they come in many copies
    outer_xs = {*(f(end_xs) for f in (min, max) if end_xs)}
    outer_ys = {*(f(end_ys) for f in (min, max) if end_ys)}

    def search(
        n: int, path: list[tuple[float, float]], others: Mapping[tuple[int, float], list[tuple[float, float]]], k: int
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
            around = _detour(path, xs, ys, [*solids, *foreign_of[n]], others, spent, borders, clear)
            if around is not None:
                break
        return around

    for k, (n, _foreign) in enumerate(pending):
        bends, source, target, chain, parallel = built[n]
        path = [bends[0], *(b for a, b in pairwise(bends) if a != b)]
        # routes that leave or arrive at the same border point may run along this one, so they do not count
        mine = {path[0], path[-1]}
        others = _Filtered(occupied, lambda m, mine=mine: not ends_of[m] & mine)
        around = search(n, path, others, k)
        if around is None:
            raise _Crowded(f"edge {source!r} -> {target!r} cannot be routed round the groups it does not belong to")
        built[n] = (around, source, target, chain, parallel)
        occupy(around, n)

    # a route may still run along another one; move a later segment aside a grid step at a time, or refuse
    paths = [_simplify(b[0]) for b in built]
    border_ends = [{p[0], p[-1]} for p in paths]

    def legal(n: int, pts: list[tuple[float, float]]) -> bool:
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

    def fits(n: int, pts: list[tuple[float, float]]) -> bool:
        """Whether `pts` is legal and clear of every group's border."""
        return legal(n, pts) and not _beside(pts, borders, clear)

    def reroute(
        n: int, lines: dict[tuple[int, float], list[tuple[float, float, int, int]]]
    ) -> list[tuple[float, float]] | None:
        """Edge `n` searched again, knowing every other route as it now stands in `lines`."""
        mine = {paths[n][0], paths[n][-1]}
        others = _Filtered(lines, lambda m, n=n, mine=mine: m != n and not border_ends[m] & mine)
        found = search(n, paths[n], others, n)
        return None if found is None else _simplify(found)

    for n, pts in enumerate(paths):
        # a segment beside a border moves aside a grid step at a time, as far as it takes, and stays if none is clear
        while built[n][1] != built[n][2] and (beside := [i for i in _beside(pts, borders, clear) if 1 <= i <= len(pts) - 3]):
            moved = next(
                (
                    m
                    for k in range(1, 3 * round(clear / GRID))
                    for sign in (1, -1)
                    if (m := _shifted(pts, beside[0], sign * k * GRID)) is not None
                    and legal(n, m)
                    and len(_beside(m, borders, clear)) < len(_beside(pts, borders, clear))
                ),
                None,
            )
            if moved is None:
                break
            pts = paths[n] = moved
    _apart(paths, border_ends, fits, lambda n: (built[n][1], built[n][2]), reroute, spent)

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
    group_boxes: dict[str, Box] = {}
    for g, (ulo, uhi, vlo, vhi) in group_rect.items():
        (x1, y1), (x2, y2) = page(ulo, vlo), page(uhi, vhi)
        left, right, bottom, top = min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)
        group_boxes[g] = Box(snap((left + right) / 2), snap((bottom + top) / 2), snap(right - left), snap(top - bottom))
    lane_boxes = {
        name: Box(
            snap(width / 2),
            snap(height - (lane_top[i] + lane_bottom[i]) / 2 - shift_v),
            width,
            snap(lane_bottom[i] - lane_top[i]),
        )
        for i, name in enumerate(lanes)
    }
    # a label must not hide a heading, a lane heading or a group it does not belong to, nor leave its lanes
    fixed = [
        *boxes.values(),
        *(
            Box(b.x, b.y + b.height / 2 - heading_of[g][1] / 2, min(heading_of[g][0], b.width), heading_of[g][1])
            for g, b in group_boxes.items()
            if g in heading_of
        ),
    ]
    if lanes and col_left:
        strip = snap(col_left[0] + shift_u)
        fixed.append(Box(strip / 2, height / 2, strip, height))
    spans: list[tuple[float, float] | None] = []
    for source, target in edges:
        ends = [lane_boxes[lane] for i in (source, target) if (lane := by_id[i].lane) is not None]
        spans.append((min(b.y - b.height / 2 for b in ends), max(b.y + b.height / 2 for b in ends)) if ends else None)
    foreign = [[b for g, b in group_boxes.items() if g not in groups_of[s] | groups_of[t]] for s, t in edges]
    labels = _place_labels(opts.edge_labels, edges, routes, fixed, foreign, spans, spent, margin)
    page_width = max([width, *(_ceil(b.x + b.width / 2 + margin) for b in labels.values())])
    page_height = max([height, *(_ceil(b.y + b.height / 2 + margin) for b in labels.values())])
    lane_boxes = {name: replace(b, x=snap(page_width / 2), width=page_width) for name, b in lane_boxes.items()}
    wrapped_rows = (
        tuple(
            tuple(k for layer in range(lo, hi) for k in rows[layer] if isinstance(k, str))
            for lo, hi in zip(row_starts, [*row_starts[1:], n_layers], strict=True)
        )
        if n_bands > 1
        else ()
    )
    return Layout(boxes, group_boxes, lane_boxes, routes, page_width, page_height, labels, wrapped_rows, len(pending))
