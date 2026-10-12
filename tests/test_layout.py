"""The layered layout: boxes never overlap, routes are orthogonal and meet no node, and the result depends on nothing but the arguments."""

import importlib.util
import os
import random
import subprocess
import sys
import time
from collections import Counter
from itertools import pairwise
from pathlib import Path

import pytest
from helpers.graphs import random_graph

from vsdxkit import builder as builder_module
from vsdxkit import layout as layout_module
from vsdxkit.errors import GraphError
from vsdxkit.layout import GRID, Box, Layout, LayoutNode, LayoutOptions, layered_layout, snap

SHRINK = 1e-6


def _overlap(a: Box, b: Box) -> bool:
    return abs(a.x - b.x) < (a.width + b.width) / 2 - SHRINK and abs(a.y - b.y) < (a.height + b.height) / 2 - SHRINK


def _segment_enters(p: tuple[float, float], q: tuple[float, float], box: Box) -> bool:
    """Whether the axis-parallel segment p-q passes through the inside of `box`."""
    left, right = box.x - box.width / 2 + SHRINK, box.x + box.width / 2 - SHRINK
    bottom, top = box.y - box.height / 2 + SHRINK, box.y + box.height / 2 - SHRINK
    (x1, y1), (x2, y2) = p, q
    return max(min(x1, x2), left) <= min(max(x1, x2), right) and max(min(y1, y2), bottom) <= min(max(y1, y2), top)


def _check(layout: Layout, nodes: tuple[LayoutNode, ...], parents: tuple[tuple[str, str], ...]) -> None:
    boxes = layout.nodes
    ids = list(boxes)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            assert not _overlap(boxes[a], boxes[b]), f"{a} overlaps {b}"
    for (source, target, _n), points in layout.routes.items():
        for p, q in pairwise(points):
            assert p[0] == q[0] or p[1] == q[1], f"{source}->{target} has a diagonal"
            for node_id, box in boxes.items():
                if node_id not in (source, target):
                    assert not _segment_enters(p, q, box), f"{source}->{target} runs through {node_id}"
        for x, y in points:
            assert snap(x) == x and snap(y) == y
    for what, box in [*boxes.items(), *layout.groups.items()]:
        assert box.x - box.width / 2 >= -SHRINK and box.x + box.width / 2 <= layout.width + SHRINK, f"{what} leaves the page"
        assert box.y - box.height / 2 >= -SHRINK and box.y + box.height / 2 <= layout.height + SHRINK, (
            f"{what} leaves the page"
        )
    members: dict[str, set[str]] = {}
    parent = dict(parents)
    for node in nodes:
        g = node.group
        while g is not None:
            members.setdefault(g, set()).add(node.id)
            g = parent.get(g)
    by_id = {node.id: node for node in nodes}
    for (source, target, _n), points in layout.routes.items():
        mine = {g for g, ids in members.items() if source in ids or target in ids}
        for g, box in layout.groups.items():
            for p, q in pairwise(points):
                if g not in mine:
                    assert not _segment_enters(p, q, box), f"{source}->{target} runs through group {g}"
                elif source == target:
                    assert (
                        box.x - box.width / 2 - SHRINK <= min(p[0], q[0]) and max(p[0], q[0]) <= box.x + box.width / 2 + SHRINK
                    )
                    assert (
                        box.y - box.height / 2 - SHRINK <= min(p[1], q[1])
                        and max(p[1], q[1]) <= box.y + box.height / 2 + SHRINK
                    )
        ends = [layout.lanes[by_id[i].lane] for i in (source, target) if by_id[i].lane is not None]
        if ends:
            low, high = min(b.y - b.height / 2 for b in ends), max(b.y + b.height / 2 for b in ends)
            assert all(low - SHRINK <= y <= high + SHRINK for _x, y in points), f"{source}->{target} leaves its lanes"
    for g, box in layout.groups.items():
        for node_id, other in boxes.items():
            if node_id not in members[g]:
                assert not _overlap(box, other), f"group {g} covers {node_id}"
    for g, box in layout.groups.items():
        lanes_of = {n.lane for n in nodes if n.id in members[g] and n.lane is not None}
        for name in lanes_of:
            lane = layout.lanes[name]
            assert abs(box.y - lane.y) <= lane.height / 2 - box.height / 2 + SHRINK, f"group {g} leaves lane {name}"
    for node in nodes:
        if node.lane is not None:
            lane = layout.lanes[node.lane]
            assert abs(boxes[node.id].y - lane.y) <= lane.height / 2 - boxes[node.id].height / 2 + SHRINK, (
                f"{node.id} leaves its lane"
            )


@pytest.mark.parametrize("seed", range(12))
@pytest.mark.parametrize(
    ("lanes", "groups", "direction"),
    [(0, 0, "left_to_right"), (0, 0, "top_down"), (3, 0, "left_to_right"), (3, 3, "left_to_right"), (0, 3, "top_down")],
)
def test_a_random_graph_lays_out_cleanly(seed, lanes, groups, direction):
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, 40, 60, lanes, groups)
    nodes = tuple(LayoutNode(*row) for row in rows)
    options = LayoutOptions(direction=direction, parents=parents)
    layout = layered_layout(nodes, edges, lane_ids, group_ids, options)
    _check(layout, nodes, parents)
    assert layout == layered_layout(nodes, edges, lane_ids, group_ids, options)


def test_a_200_node_graph_with_lanes_and_groups_lays_out_with_no_shared_run():
    """This size needs the shared-point pass, which has a search budget of its own (about 17 s; 60 s is a hang guard)."""
    rows, edges, lane_ids, group_ids, parents = random_graph(1, 200, 320, 4, 4)
    nodes = tuple(LayoutNode(*row) for row in rows)
    start = time.perf_counter()
    layout = layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))
    assert time.perf_counter() - start < 60
    assert len(layout.routes) == 320
    _check(layout, nodes, parents)
    _check_routes(layout, own_points=False)


def test_a_150_node_graph_with_lanes_and_groups_lays_out_with_no_shared_run():
    """The exit criterion: a graph of this size lays out with no violation, with a 60 s hang guard (about 14 s locally, most of it a first attempt that gives every edge a border point of its own)."""
    rows, edges, lane_ids, group_ids, parents = random_graph(1, 150, 240, 4, 4)
    nodes = tuple(LayoutNode(*row) for row in rows)
    start = time.perf_counter()
    layout = layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))
    assert time.perf_counter() - start < 60
    assert len(layout.routes) == 240
    _check(layout, nodes, parents)
    _check_routes(layout, own_points=False)


def test_lanes_stack_top_to_bottom_in_the_order_given():
    nodes = (LayoutNode("a", 1, 1, "first"), LayoutNode("b", 1, 1, "second"))
    layout = layered_layout(nodes, (("a", "b"),), ("first", "second"))
    assert layout.lanes["first"].y > layout.lanes["second"].y
    assert layout.nodes["a"].y > layout.nodes["b"].y


def test_a_flow_runs_left_to_right_and_top_down():
    nodes = (LayoutNode("a", 1, 1), LayoutNode("b", 1, 1))
    across = layered_layout(nodes, (("a", "b"),))
    assert across.nodes["a"].x < across.nodes["b"].x
    down = layered_layout(nodes, (("a", "b"),), options=LayoutOptions(direction="top_down"))
    assert down.nodes["a"].y > down.nodes["b"].y


def test_a_cycle_a_self_loop_and_parallel_edges_all_get_routes():
    nodes = (LayoutNode("a", 1, 1), LayoutNode("b", 1, 1))
    layout = layered_layout(nodes, (("a", "b"), ("b", "a"), ("a", "a"), ("a", "b")))
    assert set(layout.routes) == {("a", "b", 0), ("b", "a", 0), ("a", "a", 0), ("a", "b", 1)}
    _check(layout, nodes, ())


def test_an_empty_graph_is_a_margin_sized_page():
    layout = layered_layout((), ())
    assert layout.nodes == {} and layout.width > 0 and layout.height > 0


def test_a_nested_group_stays_inside_its_lane_band_between_other_lanes():
    nodes = (
        LayoutNode("a", 1, 1, "top"),
        LayoutNode("b", 1, 1, "mid", "inner"),
        LayoutNode("c", 1, 1, "bottom"),
    )
    options = LayoutOptions(parents=(("inner", "outer"),))
    layout = layered_layout(nodes, (("a", "b"), ("b", "c")), ("top", "mid", "bottom"), ("outer", "inner"), options)
    _check(layout, nodes, options.parents)
    outer, mid = layout.groups["outer"], layout.lanes["mid"]
    assert outer.y + outer.height / 2 <= mid.y + mid.height / 2 + SHRINK
    assert outer.y - outer.height / 2 >= mid.y - mid.height / 2 - SHRINK


def test_a_parent_naming_an_undeclared_group_is_refused_by_name():
    nodes = (LayoutNode("a", 1, 1, group="kid"),)
    with pytest.raises(GraphError, match=r"kid.*ghost"):
        layered_layout(nodes, (), (), ("kid",), LayoutOptions(parents=(("kid", "ghost"),)))


def test_nesting_deeper_than_one_level_is_refused():
    nodes = (LayoutNode("a", 1, 1, group="c"),)
    options = LayoutOptions(parents=(("c", "b"), ("b", "a")))
    with pytest.raises(GraphError, match="nest one level"):
        layered_layout(nodes, (), (), ("a", "b", "c"), options)


@pytest.mark.parametrize(
    ("nodes", "lanes", "groups", "repeated"),
    [
        ((LayoutNode("a", 1, 1), LayoutNode("a", 2, 2)), (), (), "'a'"),
        ((LayoutNode("a", 1, 1),), ("x", "x"), (), "'x'"),
        ((LayoutNode("a", 1, 1),), (), ("g", "g"), "'g'"),
    ],
    ids=["node", "lane", "group"],
)
def test_a_repeated_id_is_refused_by_name(nodes, lanes, groups, repeated):
    with pytest.raises(GraphError, match=repeated):
        layered_layout(nodes, (), lanes, groups)


@pytest.mark.parametrize(
    ("nodes", "edges", "lanes", "options"),
    [
        ((LayoutNode("a", 1, 1, "x"),), (), ("x",), LayoutOptions(direction="top_down")),
        ((LayoutNode("a", 1, 1),), (("a", "ghost"),), (), None),
        ((LayoutNode("a", 1, 1, "nope"),), (), ("x",), None),
        ((LayoutNode("a", 1, 1, group="nope"),), (), (), None),
    ],
    ids=["lanes with top-down", "edge to a missing node", "unknown lane", "unknown group"],
)
def test_an_impossible_layout_is_refused(nodes, edges, lanes, options):
    with pytest.raises(GraphError):
        layered_layout(nodes, edges, lanes, (), options)


def test_the_layout_does_not_depend_on_the_hash_seed():
    """Fails if any ordering comes from a set or a dict that hash randomisation reorders."""
    code = (
        "import hashlib\n"
        "from helpers.graphs import random_graph\n"
        "from vsdxkit.layout import layered_layout, LayoutNode, LayoutOptions\n"
        "rows, e, l, g, p = random_graph(3, 60, 90, 3, 3)\n"
        "n = tuple(LayoutNode(*row) for row in rows)\n"
        "print(hashlib.sha256(repr(layered_layout(n, e, l, g, LayoutOptions(parents=p))).encode()).hexdigest())\n"
    )
    here = os.path.dirname(os.path.realpath(__file__))
    paths = os.pathsep.join([here, os.path.join(os.path.dirname(here), "src")])
    digests = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": paths},
            check=True,
        ).stdout
        for seed in ("0", "1", "2", "random")
    }
    assert len(digests) == 1


def test_a_group_spanning_two_lanes_is_refused_by_name():
    nodes = (LayoutNode("a", 1, 1, "x", "g"), LayoutNode("m", 1, 1, "y"), LayoutNode("b", 1, 1, "z", "g"))
    with pytest.raises(GraphError, match=r"'g'.*'x'.*'z'"):
        layered_layout(nodes, (), ("x", "y", "z"), ("g",))


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
@pytest.mark.parametrize("nested", [False, True])
def test_group_boxes_stay_on_the_page_when_padding_exceeds_the_margin(direction, nested):
    nodes = (LayoutNode("a", 1, 1, group="inner"), LayoutNode("b", 1, 1, group="inner"), LayoutNode("c", 1, 1))
    parents = (("inner", "outer"),) if nested else ()
    options = LayoutOptions(direction=direction, margin=0.1, group_padding=0.8, parents=parents)
    layout = layered_layout(nodes, (("a", "b"), ("b", "c")), (), ("outer", "inner") if nested else ("inner",), options)
    _check(layout, nodes, parents)


def test_a_node_without_a_lane_is_refused_when_lanes_are_declared():
    with pytest.raises(GraphError, match="'loose'"):
        layered_layout((LayoutNode("loose", 1, 1),), (), ("x",))


def test_a_node_id_that_looks_like_an_internal_key_survives():
    nodes = (LayoutNode("a", 1, 1), LayoutNode("\x002:1", 1, 1), LayoutNode("b", 1, 1), LayoutNode("c", 1, 1))
    edges = (("a", "b"), ("b", "c"), ("a", "c"))
    layout = layered_layout(nodes, edges)
    assert list(layout.nodes) == ["a", "\x002:1", "b", "c"]
    _check(layout, nodes, ())


def test_a_child_listed_twice_in_parents_is_refused_by_name():
    nodes = (LayoutNode("a", 1, 1, group="kid"),)
    options = LayoutOptions(parents=(("kid", "p1"), ("kid", "p2")))
    with pytest.raises(GraphError, match="'kid'"):
        layered_layout(nodes, (), (), ("kid", "p1", "p2"), options)


@pytest.mark.parametrize("size", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("axis", ["width", "height"])
def test_a_node_size_that_is_not_finite_and_positive_is_refused_by_name(size, axis):
    node = LayoutNode("odd", size if axis == "width" else 1, size if axis == "height" else 1)
    with pytest.raises(GraphError, match="'odd'"):
        layered_layout((node,), ())


def test_snapping_does_not_make_neighbours_overlap():
    nodes = (LayoutNode("a", 1, 0.8), LayoutNode("b", 1, 1.23))
    layout = layered_layout(nodes, (), options=LayoutOptions(node_gap=0.001))
    assert not _overlap(layout.nodes["a"], layout.nodes["b"])


def test_a_self_loop_does_not_enter_a_neighbour_when_node_gap_is_small():
    nodes = (LayoutNode("a", 1, 1), LayoutNode("b", 1, 1))
    layout = layered_layout(nodes, (("b", "b"),), options=LayoutOptions(node_gap=0.1))
    for p, q in pairwise(layout.routes[("b", "b", 0)]):
        assert not _segment_enters(p, q, layout.nodes["a"])


def test_snap_follows_the_grid(monkeypatch):
    monkeypatch.setattr(layout_module, "GRID", 0.001)
    assert snap(1.2346) == 1.235


def _inside(p: tuple[float, float], box: Box) -> bool:
    return abs(p[0] - box.x) <= box.width / 2 + SHRINK and abs(p[1] - box.y) <= box.height / 2 + SHRINK


def _on_border(p: tuple[float, float], box: Box) -> bool:
    left, right = box.x - box.width / 2, box.x + box.width / 2
    bottom, top = box.y - box.height / 2, box.y + box.height / 2
    inside = left - SHRINK <= p[0] <= right + SHRINK and bottom - SHRINK <= p[1] <= top + SHRINK
    return inside and any(abs(p[0] - e) < SHRINK for e in (left, right)) | any(abs(p[1] - e) < SHRINK for e in (bottom, top))


def _overlap_length(
    a: tuple[tuple[float, float], tuple[float, float]], b: tuple[tuple[float, float], tuple[float, float]]
) -> float:
    """The length two axis-parallel segments share along one line, or 0.0."""
    for axis in (0, 1):
        other = 1 - axis
        if a[0][other] == a[1][other] == b[0][other] == b[1][other]:
            low = max(min(a[0][axis], a[1][axis]), min(b[0][axis], b[1][axis]))
            high = min(max(a[0][axis], a[1][axis]), max(b[0][axis], b[1][axis]))
            return max(0.0, high - low)
    return 0.0


def _check_no_shared_run(layout: Layout) -> None:
    """No two routes run along the same line for a positive length, unless they share an end point on a border."""
    items = list(layout.routes.items())
    for i, (key_a, pa) in enumerate(items):
        for key_b, pb in items[i + 1 :]:
            if {pa[0], pa[-1]} & {pb[0], pb[-1]}:
                continue
            for sa in pairwise(pa):
                for sb in pairwise(pb):
                    assert _overlap_length(sa, sb) < SHRINK, f"{key_a} and {key_b} share a run {sa} / {sb}"


def _check_distinct_ends(layout: Layout) -> None:
    """No two ends of different edges, and not both ends of a self-loop, meet at one point of a node's border.

    A side of a node is left out when the layout shares its points: `round(extent / GRID) // edges == 0`, where the
    edges are those with an end on that side (a self-loop counts once) and the extent is the side's length. A route
    against the flow ends on the side it would leave from, so the side is read off the end point, not the edge.
    """
    items: Counter[tuple[str, int, int]] = Counter()
    at: dict[tuple[str, int, int], list[tuple[tuple[str, str, int], int, tuple[float, float]]]] = {}

    def side(node_id: str, point: tuple[float, float]) -> tuple[str, int, int]:
        box = layout.nodes[node_id]
        dx, dy = point[0] - box.x, point[1] - box.y
        if abs(abs(dx) - box.width / 2) < SHRINK:
            return node_id, 0, 1 if dx > 0 else -1
        return node_id, 1, 1 if dy > 0 else -1

    for key, points in layout.routes.items():
        source, target, _n = key
        first, last = side(source, points[0]), side(target, points[-1])
        items[first] += 1
        at.setdefault(first, []).append((key, 0, points[0]))
        if source != target:
            items[last] += 1
        at.setdefault(last, []).append((key, -1, points[-1]))
    for found_side, found in at.items():
        box = layout.nodes[found_side[0]]
        if round((box.height if found_side[1] == 0 else box.width) / GRID) // max(1, items[found_side]) == 0:
            continue
        seen: dict[tuple[float, float], tuple[tuple[str, str, int], int]] = {}
        for key, end, point in found:
            other = seen.setdefault(point, (key, end))
            assert other == (key, end), f"{key} and {other} meet at {point} on {found_side[0]}"


BORDER_CLEAR = 0.04
"""Inches a route must keep from the border of a group along its length: the layout keeps 0.05, less the half step a Box's centre and width each lose in snapping."""


def _check_off_group_borders(layout: Layout) -> None:
    """No route segment runs parallel to a group's border closer than BORDER_CLEAR for 0.02 inch or more (a box snaps to the grid)."""
    for g, box in layout.groups.items():
        left, right = box.x - box.width / 2, box.x + box.width / 2
        bottom, top = box.y - box.height / 2, box.y + box.height / 2
        for key, points in layout.routes.items():
            if key[0] == key[1]:
                continue  # a group's box is drawn a grid step round its members' self-loops, which stay inside it
            for p, q in pairwise(points):
                if p[0] == q[0] and any(abs(p[0] - e) < BORDER_CLEAR - SHRINK for e in (left, right)):
                    along = min(max(p[1], q[1]), top) - max(min(p[1], q[1]), bottom)
                elif p[1] == q[1] and any(abs(p[1] - e) < BORDER_CLEAR - SHRINK for e in (bottom, top)):
                    along = min(max(p[0], q[0]), right) - max(min(p[0], q[0]), left)
                else:
                    continue
                assert along < 0.02, f"{key} runs along the border of group {g}"


def _check_routes(layout: Layout, *, own_points: bool = True, clear_of_borders: bool = True, drawn: bool = False) -> None:
    """Every route stays on the page, starts and ends on its boxes' borders, and differs from every other route.

    A graph too dense for every edge to have a border point of its own shares them (`own_points=False`), and spacing
    tighter than the clearance leaves routes no room to keep off group borders (`clear_of_borders=False`).

    With `drawn`, an end may lie inside its box on the line of its last segment: the builder runs it on to the node's outline.
    """
    seen: dict[tuple[tuple[float, float], ...], tuple[str, str, int]] = {}
    for key, points in layout.routes.items():
        source, target, _n = key
        for end, other, box, word in (
            (points[0], points[1], layout.nodes[source], "starts"),
            (points[-1], points[-2], layout.nodes[target], "ends"),
        ):
            run_on = drawn and _inside(end, box) and not _inside(other, box) and (end[0] == other[0] or end[1] == other[1])
            assert _on_border(end, box) or run_on, f"{key} {word} off the border of its box"
        for x, y in points:
            assert -SHRINK <= x <= layout.width + SHRINK and -SHRINK <= y <= layout.height + SHRINK, f"{key} leaves the page"
        assert points not in seen, f"{key} repeats {seen[points]}"
        assert points[::-1] not in seen, f"{key} repeats {seen[points[::-1]]} reversed"
        seen[points] = key
    _check_no_shared_run(layout)
    if own_points:
        _check_distinct_ends(layout)
    if clear_of_borders:
        _check_off_group_borders(layout)


@pytest.mark.parametrize("axis", ["width", "height"])
@pytest.mark.parametrize("size", [0.001, 1.234])
def test_a_box_has_the_extent_the_routes_attach_to(axis, size):
    node = LayoutNode("a", size if axis == "width" else 1, size if axis == "height" else 1)
    layout = layered_layout((node, LayoutNode("b", 1, 1)), (("a", "b"),))
    box = layout.nodes["a"]
    assert getattr(box, axis) >= size
    _check_routes(layout)


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
def test_a_self_loop_stays_on_the_page_when_the_margin_is_small(direction):
    layout = layered_layout((LayoutNode("a", 1, 1),), (("a", "a"),), options=LayoutOptions(direction=direction, margin=0.1))
    _check_routes(layout)


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
@pytest.mark.parametrize("loops", [False, True])
def test_parallel_edges_get_distinct_routes(direction, loops):
    pair = ("a", "a") if loops else ("a", "b")
    nodes = (LayoutNode("a", 1, 1), LayoutNode("b", 1, 1))
    options = LayoutOptions(direction=direction)
    layout = layered_layout(nodes, (pair, pair, pair, ("b", "a")), options=options)
    assert len(layout.routes) == 4
    _check_routes(layout)
    _check(layout, nodes, ())


@pytest.mark.parametrize("seed", range(30))
@pytest.mark.parametrize(
    ("lanes", "groups", "direction"),
    [(0, 0, "left_to_right"), (0, 0, "top_down"), (3, 0, "left_to_right"), (3, 3, "left_to_right"), (0, 3, "top_down")],
)
def test_random_small_graphs_with_parallel_edges_and_loops_route_cleanly(seed, lanes, groups, direction):
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, 7, 10, lanes, groups)
    edges = (*edges, edges[0], edges[0], (edges[1][0], edges[1][0]), (edges[1][0], edges[1][0]), edges[2][::-1])
    nodes = tuple(LayoutNode(*row) for row in rows)
    layout = layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(direction=direction, parents=parents, margin=0.1))
    assert len(layout.routes) == len(edges)
    _check(layout, nodes, parents)
    _check_routes(layout)


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
@pytest.mark.parametrize("loops", [False, True])
def test_a_node_too_small_for_its_parallel_edges_is_refused_by_name(direction, loops):
    pair = ("tiny", "tiny") if loops else ("tiny", "b")
    nodes = (LayoutNode("tiny", 0.01, 0.01), LayoutNode("b", 1, 1))
    with pytest.raises(GraphError, match=r"'tiny'.*3"):
        layered_layout(nodes, (pair, pair, pair), options=LayoutOptions(direction=direction))


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
@pytest.mark.parametrize("loops", [False, True])
def test_a_node_just_wide_enough_for_its_parallel_edges_keeps_them_apart(direction, loops):
    pair = ("a", "a") if loops else ("a", "b")
    nodes = (LayoutNode("a", 0.06, 0.06), LayoutNode("b", 1, 1))
    layout = layered_layout(nodes, (pair, pair, pair), options=LayoutOptions(direction=direction))
    _check_routes(layout)


@pytest.mark.parametrize("seed", range(10))
@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
def test_random_tiny_nodes_with_parallel_edges_are_refused_or_distinct(seed, direction):
    rows, edges, _lanes, _groups, _parents = random_graph(seed, 6, 8, 0, 0)
    nodes = tuple(LayoutNode(r[0], 0.01 * (1 + seed % 3), 0.01 * (1 + seed % 3)) for r in rows)
    edges = (*edges, ("n0", "n1"), ("n0", "n1"), ("n0", "n1"), ("n2", "n2"), ("n2", "n2"), ("n2", "n2"))
    try:
        layout = layered_layout(nodes, edges, options=LayoutOptions(direction=direction))
    except GraphError:
        return
    _check_routes(layout)


def _n(node_id, lane=None, group=None):
    return LayoutNode(node_id, 1, 0.6, lane, group)


def test_a_route_goes_round_a_group_it_does_not_belong_to():
    nodes = (_n("p"), _n("g1", group="G"), _n("m"), _n("g3", group="G"), _n("q", group="H"))
    edges = (("g1", "m"), ("m", "g3"), ("p", "q"))
    layout = layered_layout(nodes, edges, groups=("G", "H"))
    _check(layout, nodes, ())
    _check_routes(layout)


def test_many_self_loops_stay_inside_their_lane():
    nodes = (_n("a", "A"), _n("b", "B"))
    layout = layered_layout(nodes, (("a", "a"),) * 5, ("A", "B"))
    _check(layout, nodes, ())
    _check_routes(layout)


@pytest.mark.parametrize("lanes", [(), ("A",)])
def test_a_self_loop_stays_inside_its_group_box(lanes):
    nodes = (_n("a", lanes[0] if lanes else None, "G"),)
    layout = layered_layout(nodes, (("a", "a"),) * 2, lanes, ("G",))
    _check(layout, nodes, ())


@pytest.mark.parametrize(
    "options",
    [
        {"layer_gap": -1.0},
        {"node_gap": float("nan")},
        {"margin": float("inf")},
        {"group_padding": -0.1},
        {"lane_padding": -0.1},
        {"lane_heading": float("-inf")},
        {"sweeps": 0},
    ],
)
def test_an_option_that_is_not_a_valid_size_is_refused_by_name(options):
    (name,) = options
    with pytest.raises(GraphError, match=name):
        layered_layout((_n("a"),), (), options=LayoutOptions(**options))


def test_a_layer_gap_too_small_for_its_channels_is_refused_by_name():
    nodes = tuple(_n(c) for c in "abcdef")
    edges = (("a", "d"), ("b", "e"), ("c", "f"), ("a", "e"), ("b", "f"))
    with pytest.raises(GraphError, match="layer_gap"):
        layered_layout(nodes, edges, options=LayoutOptions(layer_gap=0.0))
    _check_routes(layered_layout(nodes, edges, options=LayoutOptions(layer_gap=0.05)))


@pytest.mark.parametrize("seed", range(25))
@pytest.mark.parametrize(
    ("lanes", "groups", "direction"),
    [(0, 3, "left_to_right"), (0, 3, "top_down"), (2, 3, "left_to_right"), (3, 3, "left_to_right"), (1, 2, "left_to_right")],
)
@pytest.mark.parametrize("gaps", ["default", "tight"])
def test_random_grouped_graphs_with_loops_avoid_foreign_groups_and_stay_in_lanes(seed, lanes, groups, direction, gaps):
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, 9, 14, lanes, groups)
    # three parallel edges that may have to go round a group, and in the default case loops as well
    edges = (*edges, ("n2", "n4"), ("n2", "n4"), ("n2", "n4"), ("n1", "n3"), ("n1", "n3"))
    if gaps == "default":
        edges = (*edges, ("n0", "n0"), ("n0", "n0"), ("n1", "n1"), ("n3", "n3"))
    nodes = tuple(LayoutNode(*row) for row in rows)
    small = {"node_gap": 0.0, "layer_gap": 0.2, "margin": 0.0, "group_padding": 0.05} if gaps == "tight" else {}
    options = LayoutOptions(direction=direction, parents=parents, **small)
    layout = layered_layout(nodes, edges, lane_ids, group_ids, options)
    _check(layout, nodes, parents)
    _check_routes(layout, clear_of_borders=gaps != "tight")


def test_parallel_edges_that_go_round_a_group_run_side_by_side():
    nodes = (_n("p"), _n("g1", group="G"), _n("m"), _n("g3", group="G"), _n("q", group="H"))
    edges = (("g1", "m"), ("m", "g3"), ("p", "q"), ("p", "q"), ("p", "q"))
    layout = layered_layout(nodes, edges, groups=("G", "H"))
    assert len(layout.routes) == 5
    _check(layout, nodes, ())
    _check_routes(layout)


def test_a_200_node_400_edge_graph_lays_out_at_default_options():
    rows, edges, lane_ids, group_ids, parents = random_graph(2, 200, 400, 0, 0)
    nodes = tuple(LayoutNode(*row) for row in rows)
    start = time.perf_counter()
    layout = layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))
    assert time.perf_counter() - start < 60
    assert len(layout.routes) == 400
    _check(layout, nodes, parents)
    _check_routes(layout)


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
@pytest.mark.parametrize(("n", "m", "groups"), [(60, 120, 4), (60, 200, 6)])
def test_a_busy_grouped_graph_lays_out_with_no_shared_run(direction, n, m, groups):
    """The contract is a layout: these sizes route within the search limit."""
    rows, edges, lane_ids, group_ids, parents = random_graph(1, n, m, 0, groups)
    nodes = tuple(LayoutNode(*row) for row in rows)
    start = time.perf_counter()
    layout = layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(direction=direction, parents=parents))
    assert time.perf_counter() - start < 60
    assert len(layout.routes) == m
    _check(layout, nodes, parents)
    _check_routes(layout)


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
def test_a_crowded_graph_of_200_nodes_and_20_groups_is_refused_with_its_counts(direction):
    """Two passes of 12M steps each, about 40 s; the message names the graph's size and the limit."""
    rows, edges, lane_ids, group_ids, parents = random_graph(1, 200, 400, 0, 20)
    nodes = tuple(LayoutNode(*row) for row in rows)
    start = time.perf_counter()
    with pytest.raises(GraphError, match=r"search limit of 12000000 steps \(200 nodes, 400 edges, 20 groups and 0 lanes"):
        layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(direction=direction, parents=parents))
    assert time.perf_counter() - start < 120


@pytest.mark.parametrize(
    ("seed", "n", "m", "lanes", "groups", "cap", "laid_out"),
    [(793, 50, 200, 3, 6, 5_000_000, True), (793, 50, 200, 3, 6, 2_000_000, False), (325, 50, 250, 3, 6, 2_000_000, False)],
)
def test_dense_graphs_on_both_sides_of_the_ceiling_lay_out_or_are_refused_with_counts(
    monkeypatch, seed, n, m, lanes, groups, cap, laid_out
):
    """The first graph needs 4.7M steps for its first pass and 2.1M for its second, so 5M holds each; at 2M neither graph lays out."""
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, n, m, lanes, groups)
    nodes = tuple(LayoutNode(*row) for row in rows)
    monkeypatch.setattr(layout_module, "_WORK_CAP", cap)
    if laid_out:
        layout = layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))
        _check(layout, nodes, parents)
        _check_routes(layout, own_points=False)
    else:
        with pytest.raises(GraphError, match=rf"search limit of {cap} steps \({n} nodes, {m} edges, {groups} groups"):
            layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))


@pytest.mark.parametrize("seed", range(40))
def test_random_graphs_either_lay_out_cleanly_or_are_refused(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 30)
    lanes, groups = rng.choice([0, 0, 2, 3]), rng.choice([0, 0, 2, 3, 5])
    direction = "left_to_right" if lanes else rng.choice(["left_to_right", "top_down"])
    rows, edges, lane_ids, group_ids, parents = random_graph(rng.randrange(10**6), n, rng.randint(0, 3 * n), lanes, groups)
    if edges:
        extra = [edges[rng.randrange(len(edges))] for _ in range(rng.randint(0, 4))]
        loops = [(f"n{k}", f"n{k}") for k in rng.sample(range(n), min(n, rng.randint(0, 3)))]
        edges = (*edges, *extra, *loops)
    scale = rng.choice([1.0, 1.0, 0.05])
    nodes = tuple(LayoutNode(r[0], r[1] * scale, r[2] * scale, r[3], r[4]) for r in rows)
    options = LayoutOptions(
        direction=direction, parents=parents, margin=rng.choice([0.0, 0.1, 0.5]), node_gap=rng.choice([0.0, 0.1, 0.4])
    )
    try:
        layout = layered_layout(nodes, edges, lane_ids, group_ids, options)
    except GraphError:
        return  # a node too small for its parallel edges, or a layout too crowded to keep apart, is refused
    _check(layout, nodes, parents)
    _check_routes(layout, clear_of_borders=options.node_gap >= 0.05)


def test_scanning_for_shared_runs_counts_against_the_search_limit(monkeypatch):
    rows, edges, lane_ids, group_ids, parents = random_graph(1, 40, 80, 0, 0)
    nodes = tuple(LayoutNode(*row) for row in rows)
    layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))
    monkeypatch.setattr(layout_module, "_WORK_CAP", 50)
    with pytest.raises(GraphError, match="search limit of 50 steps"):
        layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))


def test_sweeps_must_not_be_a_bool():
    with pytest.raises(GraphError, match="sweeps"):
        layered_layout((_n("a"),), (), options=LayoutOptions(sweeps=True))


def _heading_sizes(seed, group_ids):
    rng = random.Random(seed)
    return tuple((g, rng.choice([0.8, 1.5, 3.0]), rng.choice([0.25, 0.5, 0.75])) for g in group_ids)


def _label_sizes(seed, edges):
    rng = random.Random(seed + 1000)
    return tuple((rng.choice([0.3, 0.66, 1.2]), rng.choice([0.3, 0.3, 0.55])) for _ in edges)


def _check_labels(layout: Layout, edges, labels) -> None:
    """Every label has its size, is on the page, and touches no node and no other label."""
    seen: dict[tuple[str, str], int] = {}
    keys = []
    for source, target in edges:
        keys.append((source, target, seen.get((source, target), 0)))
        seen[(source, target)] = seen.get((source, target), 0) + 1
    assert set(layout.labels) == set(keys)
    for key, size in zip(keys, labels, strict=True):
        box = layout.labels[key]
        assert (box.width, box.height) == size
        assert box.x - box.width / 2 >= -SHRINK and box.x + box.width / 2 <= layout.width + SHRINK, (
            f"label {key} leaves the page"
        )
        assert box.y - box.height / 2 >= -SHRINK and box.y + box.height / 2 <= layout.height + SHRINK, (
            f"label {key} leaves the page"
        )
        for node_id, node in layout.nodes.items():
            assert not _overlap(box, node), f"label {key} covers {node_id}"
    boxes = list(layout.labels.items())
    for i, (key, box) in enumerate(boxes):
        for other_key, other in boxes[i + 1 :]:
            assert not _overlap(box, other), f"labels {key} and {other_key} overlap"


def _check_labels_keep_out(layout: Layout, nodes, parents, edges, headings) -> None:
    """A label hides no heading, no lane heading and no group its edge does not touch, and stays inside its edge's lanes."""
    parent = dict(parents)
    groups_of = {}
    for node in nodes:
        found, g = set(), node.group
        while g is not None:
            found.add(g)
            g = parent.get(g)
        groups_of[node.id] = found
    by_id = {node.id: node for node in nodes}
    seen: dict[tuple[str, str], int] = {}
    for source, target in edges:
        key = (source, target, seen.get((source, target), 0))
        seen[(source, target)] = key[2] + 1
        label = layout.labels[key]
        for g, width, height in headings:
            if g in layout.groups:
                box = layout.groups[g]
                band = Box(box.x, box.y + box.height / 2 - height / 2, min(width, box.width), height)
                assert not _overlap(label, band), f"label {key} covers the heading of group {g}"
        for g, box in layout.groups.items():
            if g not in groups_of[source] | groups_of[target]:
                assert not _overlap(label, box), f"label {key} covers group {g}"
        ends = [layout.lanes[by_id[i].lane] for i in (source, target) if by_id[i].lane is not None]
        if ends:
            low, high = min(b.y - b.height / 2 for b in ends), max(b.y + b.height / 2 for b in ends)
            assert low - SHRINK <= label.y - label.height / 2 and label.y + label.height / 2 <= high + SHRINK, (
                f"label {key} leaves its lanes"
            )
            assert label.x - label.width / 2 >= 1.1 - SHRINK, f"label {key} covers the lane headings"


def _check_heading_bands(layout: Layout, headings) -> None:
    """No route enters the strip at the top of a group box, where its heading is drawn."""
    for g, width, height in headings:
        if g not in layout.groups:
            continue
        box = layout.groups[g]
        band = Box(box.x, box.y + box.height / 2 - height / 2, min(width, box.width), height)
        for key, points in layout.routes.items():
            for p, q in pairwise(points):
                assert not _segment_enters(p, q, band), f"{key} runs through the heading of group {g}"


def _check_headings(layout: Layout, nodes, parents, headings) -> None:
    """A heading's group box is as wide as its text and clears it above every member and child box."""
    parent = dict(parents)
    for g, width, height in headings:
        if g not in layout.groups:
            continue
        box = layout.groups[g]
        assert box.width >= width - SHRINK, f"group {g} is narrower than its heading"
        inside = []
        for n in nodes:
            h = n.group
            while h is not None:
                if h == g:
                    inside.append(layout.nodes[n.id])
                h = parent.get(h)
        inside += [layout.groups[c] for c, p in parents if p == g and c in layout.groups]
        top = max(b.y + b.height / 2 for b in inside)
        # snapping moves each border by up to half a grid step
        assert box.y + box.height / 2 - top >= height - 0.01 - SHRINK, f"group {g} does not clear its heading"


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize(
    ("lanes", "groups", "direction"),
    [(0, 3, "left_to_right"), (3, 3, "left_to_right"), (0, 3, "top_down"), (0, 1, "top_down")],
)
def test_headings_get_room_in_random_graphs(seed, lanes, groups, direction):
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, 7, 10, lanes, groups)
    edges = (*edges, edges[0], edges[0], (edges[1][0], edges[1][0]), edges[2][::-1])
    nodes = tuple(LayoutNode(*row) for row in rows)
    headings = _heading_sizes(seed, group_ids)
    options = LayoutOptions(direction=direction, parents=parents, headings=headings)
    layout = layered_layout(nodes, edges, lane_ids, group_ids, options)
    _check(layout, nodes, parents)
    _check_routes(layout)
    _check_headings(layout, nodes, parents, headings)
    _check_heading_bands(layout, headings)
    assert layout == layered_layout(nodes, edges, lane_ids, group_ids, options)


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize(
    ("lanes", "groups", "direction"),
    [(0, 0, "left_to_right"), (0, 0, "top_down"), (3, 0, "left_to_right"), (3, 3, "left_to_right"), (0, 3, "top_down")],
)
def test_labels_and_headings_get_room_in_random_graphs(seed, lanes, groups, direction):
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, 7, 10, lanes, groups)
    edges = (*edges, edges[0], edges[0], (edges[1][0], edges[1][0]), edges[2][::-1])
    nodes = tuple(LayoutNode(*row) for row in rows)
    labels, headings = _label_sizes(seed, edges), _heading_sizes(seed, group_ids)
    options = LayoutOptions(direction=direction, parents=parents, edge_labels=labels, headings=headings)
    layout = layered_layout(nodes, edges, lane_ids, group_ids, options)
    _check(layout, nodes, parents)
    _check_routes(layout)
    _check_labels(layout, edges, labels)
    _check_labels_keep_out(layout, nodes, parents, edges, headings)
    _check_headings(layout, nodes, parents, headings)
    _check_heading_bands(layout, headings)
    assert layout == layered_layout(nodes, edges, lane_ids, group_ids, options)


def test_a_label_wider_than_the_default_gap_widens_it_and_clears_both_nodes():
    nodes = (LayoutNode("a", 1.5, 0.8), LayoutNode("b", 1.5, 0.8))
    plain = layered_layout(nodes, (("a", "b"),), options=LayoutOptions(page=None))
    wide = layered_layout(nodes, (("a", "b"),), options=LayoutOptions(edge_labels=((2.7, 0.3),), page=None))
    assert wide.width - plain.width >= 1.7 - 0.02
    _check_labels(wide, (("a", "b"),), ((2.7, 0.3),))


def test_labels_of_parallel_edges_do_not_overlap_each_other():
    nodes = (LayoutNode("a", 1.5, 1.2), LayoutNode("b", 1.5, 1.2))
    edges = (("a", "b"),) * 3
    layout = layered_layout(nodes, edges, options=LayoutOptions(edge_labels=((0.66, 0.3),) * 3))
    _check_labels(layout, edges, ((0.66, 0.3),) * 3)


def test_a_group_heading_taller_and_wider_than_its_members_grows_the_box():
    nodes = (LayoutNode("a", 1.5, 0.8, group="g"),)
    headings = (("g", 4.0, 1.5),)
    layout = layered_layout(nodes, (), (), ("g",), LayoutOptions(headings=headings))
    _check_headings(layout, nodes, (), headings)
    _check(layout, nodes, ())


def test_a_heading_that_would_cover_a_node_outside_its_group_is_refused():
    nodes = (LayoutNode("a", 1.5, 0.8, group="g"), LayoutNode("b", 1.5, 0.8, group="h"))
    options = LayoutOptions(direction="top_down", headings=(("g", 9.0, 0.25),))
    with pytest.raises(GraphError, match="heading of group 'g'"):
        layered_layout(nodes, (), (), ("g", "h"), options)


@pytest.mark.parametrize(
    "options",
    [
        LayoutOptions(edge_labels=((0.3, 0.3), (0.3, 0.3))),
        LayoutOptions(edge_labels=((0.0, 0.3),)),
        LayoutOptions(headings=(("ghost", 1.0, 1.0),)),
        LayoutOptions(headings=(("g", 1.0, float("nan")),)),
        LayoutOptions(headings=(("g", 1.0, 1.0), ("g", 2.0, 1.0))),
        LayoutOptions(headings=(("g", 1.0),)),
        LayoutOptions(headings=(("g", 1.0, 1.0, 1.0),)),
        LayoutOptions(headings=(("g", "wide", 1.0),)),
        LayoutOptions(headings=((),)),
        LayoutOptions(edge_labels=(("wide", 0.3),)),
    ],
)
def test_a_label_or_heading_option_that_is_not_valid_is_refused(options):
    with pytest.raises(GraphError):
        layered_layout((LayoutNode("a", 1, 1, group="g"), LayoutNode("b", 1, 1)), (("a", "b"),), (), ("g",), options)


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
def test_no_route_runs_through_a_heading_even_one_that_ends_inside_its_group(direction):
    nodes = (LayoutNode("a", 1.5, 0.8), LayoutNode("b", 1.5, 0.8, group="g"))
    headings = (("g", 1.0, 0.75),)
    layout = layered_layout(nodes, (("a", "b"), ("b", "b")), (), ("g",), LayoutOptions(direction=direction, headings=headings))
    _check(layout, nodes, ())
    _check_routes(layout)
    _check_heading_bands(layout, headings)


def test_the_heading_of_an_empty_child_group_reserves_nothing():
    nodes = (LayoutNode("a", 1.5, 0.8, lane="x", group="p"),)
    options = dict(parents=(("c", "p"),))
    plain = layered_layout(nodes, (), ("x",), ("p", "c"), LayoutOptions(**options))
    long = layered_layout(nodes, (), ("x",), ("p", "c"), LayoutOptions(**options, headings=(("c", 1.0, 6.0),)))
    assert long == plain


def test_a_one_line_heading_that_fits_the_padding_still_keeps_routes_off_it():
    nodes = (LayoutNode("a", 1.5, 0.8), LayoutNode("b", 1.5, 0.8, group="g"))
    headings = (("g", 1.0, 0.25),)
    layout = layered_layout(nodes, (("a", "b"),), (), ("g",), LayoutOptions(direction="top_down", headings=headings))
    _check_routes(layout)
    _check_heading_bands(layout, headings)


def test_a_wide_label_entering_a_group_top_down_does_not_cover_its_heading():
    nodes = (LayoutNode("a", 1.5, 0.8), LayoutNode("b", 1.5, 0.8, group="g"))
    headings = (("g", 1.0, 0.25),)
    labels = ((3.0, 0.3),)
    options = LayoutOptions(direction="top_down", edge_labels=labels, headings=headings)
    layout = layered_layout(nodes, (("a", "b"),), (), ("g",), options)
    _check_labels(layout, (("a", "b"),), labels)
    _check_labels_keep_out(layout, nodes, (), (("a", "b"),), headings)


def test_a_lane_gives_room_to_the_labels_that_stay_in_it():
    nodes = (LayoutNode("a", 1.5, 0.8, "x"), LayoutNode("b", 1.5, 0.8, "x"), LayoutNode("c", 1.5, 0.8, "y"))
    edges = (("a", "b"),) * 4 + (("b", "c"),)
    labels = ((0.66, 0.3),) * 5
    layout = layered_layout(nodes, edges, ("x", "y"), (), LayoutOptions(edge_labels=labels))
    _check_labels(layout, edges, labels)
    _check_labels_keep_out(layout, nodes, (), edges, ())


def test_25_parallel_labelled_edges_are_all_placed():
    nodes = (LayoutNode("a", 2.0, 8.0), LayoutNode("b", 2.0, 8.0))
    edges = (("a", "b"),) * 25
    labels = ((0.66, 0.3),) * 25
    layout = layered_layout(nodes, edges, options=LayoutOptions(edge_labels=labels))
    _check_labels(layout, edges, labels)


def test_the_page_ends_a_margin_after_the_last_column_when_labels_widen_the_gaps():
    nodes = (LayoutNode("a", 1.5, 0.8), LayoutNode("b", 1.5, 0.8))
    layout = layered_layout(nodes, (("b", "a"),), options=LayoutOptions(edge_labels=((2.0, 0.3),), page=None))
    right = max(box.x + box.width / 2 for box in layout.nodes.values())
    assert layout.width == pytest.approx(right + 0.5, abs=0.02)


@pytest.mark.parametrize("count", [4, 5])
def test_labels_keep_the_margin_from_the_page_edge(count):
    nodes = (LayoutNode("a", 1.5, 0.8), LayoutNode("b", 1.5, 0.8))
    edges = (("a", "b"),) * count
    labels = ((0.66, 0.3),) * count
    layout = layered_layout(nodes, edges, options=LayoutOptions(edge_labels=labels))
    for key, box in layout.labels.items():
        assert box.x - box.width / 2 >= 0.5 - SHRINK, key
        assert box.y - box.height / 2 >= 0.5 - SHRINK, key
        assert box.x + box.width / 2 <= layout.width - 0.5 + SHRINK, key
        assert box.y + box.height / 2 <= layout.height - 0.5 + SHRINK, key


def _layout_of_case(monkeypatch, name):
    """The layout the builder draws a case file with (tests/fixtures/diagrams), as the Visio harness is shown it."""
    spec = importlib.util.spec_from_file_location(
        f"case_{name}", Path(__file__).parent / "fixtures" / "diagrams" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seen: list[Layout] = []
    real = builder_module.layered_layout
    monkeypatch.setattr(builder_module, "layered_layout", lambda *a, **k: seen.append(real(*a, **k)) or seen[-1])
    module.build()
    return seen[0]


def test_a_self_loop_leaves_a_node_from_its_own_point_not_the_next_edges(monkeypatch):
    layout = _layout_of_case(monkeypatch, "every_kind")
    assert layout.routes[("n3", "n3", 0)][0] != layout.routes[("n3", "n4", 0)][0]
    _check_routes(layout)


def test_routes_into_one_node_arrive_at_different_points_and_none_rides_a_group_border(monkeypatch):
    layout = _layout_of_case(monkeypatch, "groups_and_lanes")
    assert layout.routes[("s1", "s4", 0)][-1] != layout.routes[("s3", "s4", 0)][-1]
    _check_routes(layout)


def test_a_route_keeps_clear_of_the_heading_of_a_group_it_enters(monkeypatch):
    layout = _layout_of_case(monkeypatch, "groups_and_lanes")
    _check_heading_bands(layout, [("g2", *builder_module._heading_size("Second look"))])


def _check_clearance(layout: Layout, nodes, parents, options: LayoutOptions) -> None:
    """Every box keeps the padding and the margin asked of it, however the options fall on the grid."""
    pad, margin = options.group_padding, options.margin
    tol = 1e-9

    def edges_of(b: Box):
        return b.x - b.width / 2, b.x + b.width / 2, b.y - b.height / 2, b.y + b.height / 2

    def holds(outer: Box, inner: Box, by: float) -> bool:
        (ol, orr, ob, ot), (il, ir, ib, it) = edges_of(outer), edges_of(inner)
        return ol <= il - by + tol and orr >= ir + by - tol and ob <= ib - by + tol and ot >= it + by - tol

    parent = dict(parents)
    members: dict[str, list[str]] = {}
    for node in nodes:
        g = node.group
        while g is not None:
            members.setdefault(g, []).append(node.id)
            g = parent.get(g)
    for g, box in layout.groups.items():
        for m in members[g]:
            assert holds(box, layout.nodes[m], pad), f"group {g} keeps less than its padding round {m}"
        for node_id, other in layout.nodes.items():
            if node_id not in members[g]:
                apart = max(
                    abs(box.x - other.x) - (box.width + other.width) / 2,
                    abs(box.y - other.y) - (box.height + other.height) / 2,
                )
                assert apart >= GRID - tol, f"group {g} is less than a grid step from {node_id}"
    related = {frozenset(p) for p in parents}
    for g, box in layout.groups.items():
        for h, other in layout.groups.items():
            if g < h and frozenset((g, h)) not in related:
                apart = max(
                    abs(box.x - other.x) - (box.width + other.width) / 2,
                    abs(box.y - other.y) - (box.height + other.height) / 2,
                )
                assert apart >= -tol, f"group {g} overlaps group {h}"
    for child, outer in parents:
        if child in layout.groups:
            assert holds(layout.groups[outer], layout.groups[child], pad), (
                f"group {outer} keeps less than its padding round {child}"
            )
    for what, box in [*layout.nodes.items(), *layout.groups.items()]:
        left, right, bottom, top = edges_of(box)
        assert min(left, bottom, layout.width - right, layout.height - top) >= margin - tol, (
            f"{what} is nearer the page edge than the margin"
        )


_DEGENERATE = [
    (0.0, 0.0, 0.0),
    (0.0, 0.0, 0.004),
    (0.004, 0.0, 0.013),
    (0.05, 0.0, 0.5),
    (0.25, 0.004, 0.013),
    (0.013, 0.013, 0.0),
    (0.004, 0.013, 0.0),
]


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
@pytest.mark.parametrize(("padding", "gap", "margin"), _DEGENERATE)
def test_zero_padding_zero_gap_and_off_grid_margins_keep_their_clearance(seed, direction, padding, gap, margin):
    rng = random.Random(seed)
    count = rng.randint(2, 8)
    laned = direction == "left_to_right" and seed % 2 == 0
    rows = [
        (
            f"n{i}",
            rng.choice([0.02, 0.1, 0.5, 1.0, 1.01]),
            rng.choice([0.02, 0.1, 0.5, 1.0, 1.01]),
            "L" if laned else None,
            rng.choice([None, "C", "P", "S"]),
        )
        for i in range(count)
    ]
    nodes = tuple(LayoutNode(*row) for row in rows)
    edges = tuple((f"n{rng.randrange(count)}", f"n{rng.randrange(count)}") for _ in range(rng.randint(0, 5)))
    edges += tuple((f"n{k}", f"n{k}") for k in rng.sample(range(count), rng.randint(0, 2)))
    parents = (("C", "P"),)
    options = LayoutOptions(
        direction=direction, parents=parents, group_padding=padding, node_gap=gap, margin=margin, lane_padding=0.004
    )
    try:
        layout = layered_layout(nodes, edges, ("L",) if laned else (), ("C", "P", "S"), options)
    except GraphError:
        return  # a node too small for its parallel edges is refused, as at the defaults
    _check(layout, nodes, parents)
    _check_routes(layout, own_points=False, clear_of_borders=False)
    _check_clearance(layout, nodes, parents, options)
    if laned:
        _check_lanes_hold_groups(layout)


def _check_lanes_hold_groups(layout: Layout) -> None:
    """Every group box lies inside the lane bands its members are in."""
    for g, box in layout.groups.items():
        assert any(
            lane.y - lane.height / 2 <= box.y - box.height / 2 + 1e-9
            and box.y + box.height / 2 <= lane.y + lane.height / 2 + 1e-9
            for lane in layout.lanes.values()
        ), f"group {g} leaves its lane"


@pytest.mark.parametrize("seed", range(150))
@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
def test_nested_off_grid_groups_never_leave_their_lane_or_raise(seed, direction):
    """Sizes and spacing off the grid, groups nested and side by side, no edges: the shapes that ran the rounding slack out."""
    rng = random.Random(seed)
    sizes = [0.02, 0.1, 0.5, 1.0, 1.01]
    laned = direction == "left_to_right"
    nodes = tuple(
        LayoutNode(f"n{i}", rng.choice(sizes), rng.choice(sizes), "L" if laned else None, rng.choice([None, "C", "P", "S"]))
        for i in range(rng.randint(3, 8))
    )
    options = LayoutOptions(
        direction=direction,
        parents=(("C", "P"),),
        group_padding=rng.choice([0.004, 0.013]),
        node_gap=0.013,
        lane_padding=0.004,
    )
    layout = layered_layout(nodes, (), ("L",) if laned else (), ("C", "P", "S"), options)
    _check_clearance(layout, nodes, options.parents, options)
    if laned:
        _check_lanes_hold_groups(layout)


def test_nested_off_grid_groups_stay_inside_their_lane():
    nodes = [
        LayoutNode("c1", 0.1, 1.0, "L", "C"),
        LayoutNode("c2", 1.01, 0.1, "L", "C"),
        LayoutNode("p1", 0.1, 1.0, "L", "P"),
        LayoutNode("p2", 0.02, 0.1, "L", "P"),
        LayoutNode("u", 0.1, 0.02, "L", None),
    ]
    options = LayoutOptions(parents=(("C", "P"),), group_padding=0.013, lane_padding=0.004, node_gap=0.013)
    layout = layered_layout(tuple(nodes), (), ("L",), ("C", "P"), options)
    _check_lanes_hold_groups(layout)


def test_nested_off_grid_groups_beside_a_sibling_group_lay_out_apart():
    nodes = [
        LayoutNode("u", 1.0, 0.1, None, None),
        LayoutNode("c1", 0.1, 0.02, None, "C"),
        LayoutNode("c2", 0.1, 0.1, None, "C"),
        LayoutNode("p1", 1.01, 0.5, None, "P"),
        LayoutNode("p2", 0.5, 0.5, None, "P"),
        LayoutNode("s1", 1.01, 0.5, None, "S"),
    ]
    options = LayoutOptions(direction="top_down", parents=(("C", "P"),), group_padding=0.004, node_gap=0.013)
    _clearance_of(
        nodes, [], ("C", "P", "S"), **{k: getattr(options, k) for k in ("direction", "parents", "group_padding", "node_gap")}
    )


def _clearance_of(nodes, edges, groups, **options):
    options = LayoutOptions(**options)
    layout = layered_layout(tuple(nodes), tuple(edges), (), groups, options)
    parents = options.parents
    _check(layout, tuple(nodes), parents)
    _check_clearance(layout, tuple(nodes), parents, options)


def test_a_group_box_holds_the_outer_loop_of_a_grid_sized_node_at_zero_padding():
    _clearance_of([LayoutNode("a", 0.02, 0.02, None, "G")], [("a", "a"), ("a", "a")], ("G",), group_padding=0.0)


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
def test_an_ungrouped_node_does_not_touch_the_group_of_a_node_with_a_loop_at_zero_padding_and_gap(direction):
    nodes = [LayoutNode("a", 1.01, 1.0, None, "G"), LayoutNode("b", 1.0, 0.5, None, None)]
    _clearance_of(nodes, [("a", "a")], ("G",), group_padding=0.0, node_gap=0.0, direction=direction)


def test_a_parent_group_clears_its_child_by_the_padding_when_a_loop_reaches_past_it():
    nodes = [LayoutNode("a", 1.0, 1.0, None, "C")]
    _clearance_of(nodes, [("a", "a")], ("C", "P"), group_padding=0.05, parents=(("C", "P"),))


def test_an_off_grid_margin_is_rounded_out_to_the_grid():
    _clearance_of([LayoutNode("a", 1.0, 1.0)], [], (), margin=0.004)


def test_groups_spaced_closer_than_the_border_clearance_still_lay_out():
    """The clearance from group borders gives way to the spacing there is; this layout was accepted before it existed."""
    rows, edges, lane_ids, group_ids, parents = random_graph(404, 17, 5, 0, 5)
    nodes = tuple(LayoutNode(*row) for row in rows)
    options = LayoutOptions(direction="top_down", parents=parents, group_padding=0.0, node_gap=0.05, layer_gap=0.1, margin=0.0)
    layout = layered_layout(nodes, edges, lane_ids, group_ids, options)
    _check(layout, nodes, parents)
    _check_routes(layout, clear_of_borders=False)


def test_the_shared_point_fallback_has_a_search_budget_of_its_own(monkeypatch):
    """The first attempt spends about 4.7M steps and the fallback about 2.1M, so a 5M cap holds each but not both."""
    rows, edges, lane_ids, group_ids, parents = random_graph(793, 50, 200, 3, 6)
    nodes = tuple(LayoutNode(*row) for row in rows)
    monkeypatch.setattr(layout_module, "_WORK_CAP", 5_000_000)
    layout = layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))
    _check(layout, nodes, parents)
    _check_routes(layout, own_points=False)


@pytest.mark.parametrize("direction", ["top_down"])
def test_a_channel_nudge_does_not_bring_two_edges_to_one_border_point(direction):
    """Both edges into node 3 once ended at one point: the nudge that parts two swapped rows undid their separate points."""
    nodes = (
        LayoutNode("0", 0.1, 0.1, None, "g"),
        LayoutNode("1", 0.06, 0.02),
        LayoutNode("2", 0.02, 0.02, None, "g"),
        LayoutNode("3", 0.06, 0.1),
    )
    edges = (("2", "3"), ("1", "3"), ("1", "0"))
    options = LayoutOptions(direction=direction, group_padding=0.05, headings=(("g", 0.5, 0.05),))
    layout = layered_layout(nodes, edges, (), ("g",), options)
    _check(layout, nodes, ())
    _check_routes(layout)


def test_detour_memory_follows_the_states_visited_not_the_grid() -> None:
    """A huge grid must not allocate route tables up front; the search is bounded by its work cap, not by memory."""
    import tracemalloc

    xs = {float(i) for i in range(1, 1500)}
    ys = {float(i) for i in range(1, 1500)}
    path = [(0.0, 0.0), (1.0, 0.0), (1.0, 3.0), (3.0, 3.0)]
    tracemalloc.start()
    try:
        route = layout_module._detour(path, xs, ys, [], {}, [0], [], 0.1)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert route is not None
    assert peak < 40_000_000
