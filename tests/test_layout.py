"""The layered layout: boxes never overlap, routes are orthogonal and meet no node, and the result depends on nothing but the arguments."""

import os
import subprocess
import sys
from itertools import pairwise

import pytest
from helpers.graphs import random_graph

from vsdxkit.errors import GraphError
from vsdxkit.layout import Box, Layout, LayoutNode, LayoutOptions, layered_layout, snap

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
    members: dict[str, set[str]] = {}
    parent = dict(parents)
    for node in nodes:
        g = node.group
        while g is not None:
            members.setdefault(g, set()).add(node.id)
            g = parent.get(g)
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


def test_a_200_node_graph_with_lanes_and_groups_has_no_route_through_a_shape():
    """The #53 exit criterion, checked geometrically."""
    rows, edges, lane_ids, group_ids, parents = random_graph(1, 200, 320, 4, 4)
    nodes = tuple(LayoutNode(*row) for row in rows)
    layout = layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))
    assert len(layout.routes) == 320
    _check(layout, nodes, parents)


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
