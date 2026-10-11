"""Layered layout of a flow graph on a fixed grid, with lanes, groups and orthogonal routes.

Pure functions over tuples: nothing here touches a document, a clock, a random
source or a hash-ordered container, so the same arguments give the same boxes
and routes on every platform. Ties are broken by the order of the arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from vsdxkit.errors import GraphError

GRID = 0.01
"""Every coordinate is a multiple of this many inches, so number formatting cannot differ between platforms."""


def snap(value: float) -> float:
    """Round `value` to the grid, as a float that prints the same everywhere."""
    return round(round(value / GRID) * GRID, 2)


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


def _order(rows: list[list[str]], slots: dict[str, _Slot], chains: list[list[str]], sweeps: int) -> None:
    """Order each layer's keys by barycentre sweeps; lane and track come first, so a stable sort keeps input order on ties."""
    up: dict[str, list[str]] = {k: [] for k in slots}
    down: dict[str, list[str]] = {k: [] for k in slots}
    for chain in chains:
        for a, b in pairwise(chain):
            down[a].append(b)
            up[b].append(a)
    position = {k: float(i) for row in rows for i, k in enumerate(row)}

    def sweep(layer: int, near: dict[str, list[str]]) -> None:
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
    :raises GraphError: lanes with a top-down direction, an edge naming a missing node, a node in an unknown lane or group,
        a repeated node, lane or group id, or a parent that is undeclared or nests more than one level
    """
    opts = options if options is not None else LayoutOptions()
    top_down = opts.direction == "top_down"
    if lanes and top_down:
        raise GraphError("lanes need direction='left_to_right'; a top-down layout has no bands to put them in")
    by_id = {n.id: n for n in nodes}
    for source, target in edges:
        if source not in by_id or target not in by_id:
            raise GraphError(f"edge {source!r} -> {target!r} names a node that is not on the page")
    lane_index = {name: i for i, name in enumerate(lanes)}
    group_index = {name: i + 1 for i, name in enumerate(groups)}
    parent_of = dict(opts.parents)
    for child, parent in opts.parents:
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
        if n.lane is not None and n.lane not in lane_index:
            raise GraphError(f"node {n.id!r} is in lane {n.lane!r}, which the page does not declare")
        if n.group is not None and n.group not in group_index:
            raise GraphError(f"node {n.id!r} is in group {n.group!r}, which the page does not declare")

    ids = [n.id for n in nodes]
    flipped = _break_cycles(ids, list(edges))
    layer_of = _layers(ids, list(edges), flipped)
    n_layers = max(layer_of.values(), default=-1) + 1

    slots: dict[str, _Slot] = {}
    for n in nodes:
        parent = parent_of.get(n.group) if n.group is not None else None
        track = (
            (0, 0)
            if n.group is None
            else (group_index[n.group], 0)
            if parent is None
            else (group_index[parent], group_index[n.group])
        )
        u, v = (n.height, n.width) if top_down else (n.width, n.height)
        slots[n.id] = _Slot(layer_of[n.id], u, v, lane_index[n.lane] if n.lane is not None else 0, track, True)

    chains: list[list[str]] = []
    for n, ((source, target), flip) in enumerate(zip(edges, flipped, strict=True)):
        a, b = (target, source) if flip else (source, target)
        chain = [a]
        if a != b:
            for layer in range(layer_of[a] + 1, layer_of[b]):
                key = f"\0{n}:{layer}"
                slots[key] = _Slot(layer, 0.0, 0.2, slots[a].lane, (0, 0), False)
                chain.append(key)
        chain.append(b)
        chains.append(chain)

    rows: list[list[str]] = [[] for _ in range(n_layers)]
    for key, slot in slots.items():
        rows[slot.layer].append(key)
    _order(rows, slots, chains, opts.sweeps)

    col_width = [max((slots[k].u_extent for k in row), default=0.0) for row in rows]
    col_left: list[float] = []
    cursor = opts.margin + (opts.lane_heading if lanes else 0.0)
    for w in col_width:
        col_left.append(cursor)
        cursor += w + opts.layer_gap
    u_total = cursor - opts.layer_gap + opts.margin if rows else 2 * opts.margin

    n_lanes = max(len(lanes), 1)
    # a lane band must contain the padding of the group boxes that touch its edges
    lane_pad = max(opts.lane_padding, opts.group_padding * (2 if parent_of else 1)) if lanes else 0.0
    track_keys = sorted({(s.lane, s.track) for s in slots.values()})
    track_height: dict[tuple[int, tuple[int, int]], float] = {}
    for key in track_keys:
        best = 0.0
        for row in rows:
            members = [slots[k] for k in row if (slots[k].lane, slots[k].track) == key]
            if members:
                best = max(best, sum(m.v_extent for m in members) + opts.node_gap * (len(members) - 1))
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
                cursor += opts.node_gap + 4 * opts.group_padding
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
            used = sum(m.v_extent for m in members) + opts.node_gap * (len(members) - 1)
            at = track_top[key] + (track_height[key] - used) / 2
            for m in members:
                m.v = at + m.v_extent / 2
                at += m.v_extent + opts.node_gap

    def page(u: float, v: float) -> tuple[float, float]:
        """Map a point from (along the flow, across it) to page inches."""
        return (snap(v), snap(u_total - u)) if top_down else (snap(u), snap(v_total - v))

    def centre_u(slot: _Slot) -> float:
        """The middle of a slot's column, along the flow."""
        return col_left[slot.layer] + col_width[slot.layer] / 2

    def right_u(slot: _Slot) -> float:
        """Where an edge leaves a slot: its far border, or the column's for a dummy."""
        return centre_u(slot) + (slot.u_extent if slot.real else col_width[slot.layer]) / 2

    def left_u(slot: _Slot) -> float:
        """Where an edge arrives at a slot: its near border, or the column's for a dummy."""
        return centre_u(slot) - (slot.u_extent if slot.real else col_width[slot.layer]) / 2

    boxes = {n.id: Box(*page(centre_u(slots[n.id]), slots[n.id].v), snap(n.width), snap(n.height)) for n in nodes}

    gap_edges: dict[int, list[tuple[float, float, int, int]]] = {}
    for n, chain in enumerate(chains):
        for hop, (a, b) in enumerate(pairwise(chain)):
            gap_edges.setdefault(slots[a].layer, []).append((min(slots[a].v, slots[b].v), max(slots[a].v, slots[b].v), n, hop))
    channel: dict[tuple[int, int], float] = {}
    for layer, items in gap_edges.items():
        items.sort()
        left = col_left[layer] + col_width[layer]
        for k, (_low, _high, n, hop) in enumerate(items):
            channel[(n, hop)] = left + opts.layer_gap * (k + 1) / (len(items) + 1)

    routes: dict[tuple[str, str, int], tuple[tuple[float, float], ...]] = {}
    seen_pairs: dict[tuple[str, str], int] = {}
    for n, ((source, target), flip, chain) in enumerate(zip(edges, flipped, chains, strict=True)):
        parallel = seen_pairs.get((source, target), 0)
        seen_pairs[(source, target)] = parallel + 1
        first_slot = slots[chain[0]]
        if source == target:
            r = first_slot.v_extent / 2 + 0.2
            c = centre_u(first_slot)
            bends = [
                (right_u(first_slot), first_slot.v),
                (right_u(first_slot) + 0.3, first_slot.v),
                (right_u(first_slot) + 0.3, first_slot.v - r),
                (c, first_slot.v - r),
                (c, first_slot.v - first_slot.v_extent / 2),
            ]
        else:
            bends = [(right_u(first_slot), first_slot.v)]
            for hop, (a, b) in enumerate(pairwise(chain)):
                sa, sb = slots[a], slots[b]
                cu = channel[(n, hop)]
                bends += [(cu, sa.v), (cu, sb.v), (left_u(sb), sb.v)]
                if hop + 1 < len(chain) - 1:
                    bends.append((right_u(sb), sb.v))
            if flip:
                bends.reverse()
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
            snap(width / 2), snap(height - (lane_top[i] + lane_bottom[i]) / 2), width, snap(lane_bottom[i] - lane_top[i])
        )
        for i, name in enumerate(lanes)
    }
    members_of: dict[str, list[str]] = {g: [] for g in groups}
    for n in nodes:
        g = n.group
        while g is not None:
            members_of[g].append(n.id)
            g = parent_of.get(g)
    group_boxes: dict[str, Box] = {}
    for g, member_ids in members_of.items():
        if member_ids:
            pad = opts.group_padding * (2 if g in parent_of.values() else 1)
            left = min(boxes[m].x - boxes[m].width / 2 for m in member_ids) - pad
            right = max(boxes[m].x + boxes[m].width / 2 for m in member_ids) + pad
            bottom = min(boxes[m].y - boxes[m].height / 2 for m in member_ids) - pad
            top = max(boxes[m].y + boxes[m].height / 2 for m in member_ids) + pad
            group_boxes[g] = Box(snap((left + right) / 2), snap((bottom + top) / 2), snap(right - left), snap(top - bottom))
    return Layout(boxes, group_boxes, lane_boxes, routes, width, height)
