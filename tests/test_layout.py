"""The layered layout: boxes never overlap, routes are orthogonal and meet no node, and the result depends on nothing but the arguments."""

import os
import subprocess
import sys
from itertools import pairwise

import pytest
from helpers.graphs import random_graph

from vsdxkit import layout as layout_module
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


def _on_border(p: tuple[float, float], box: Box) -> bool:
    left, right = box.x - box.width / 2, box.x + box.width / 2
    bottom, top = box.y - box.height / 2, box.y + box.height / 2
    inside = left - SHRINK <= p[0] <= right + SHRINK and bottom - SHRINK <= p[1] <= top + SHRINK
    return inside and any(abs(p[0] - e) < SHRINK for e in (left, right)) | any(abs(p[1] - e) < SHRINK for e in (bottom, top))


def _check_routes(layout: Layout) -> None:
    """Every route stays on the page, starts and ends on its boxes' borders, and differs from every other route."""
    seen: dict[tuple[tuple[float, float], ...], tuple[str, str, int]] = {}
    for key, points in layout.routes.items():
        source, target, _n = key
        assert _on_border(points[0], layout.nodes[source]), f"{key} starts off {source}'s border"
        assert _on_border(points[-1], layout.nodes[target]), f"{key} ends off {target}'s border"
        for x, y in points:
            assert -SHRINK <= x <= layout.width + SHRINK and -SHRINK <= y <= layout.height + SHRINK, f"{key} leaves the page"
        assert points not in seen, f"{key} repeats {seen[points]}"
        assert points[::-1] not in seen, f"{key} repeats {seen[points[::-1]]} reversed"
        seen[points] = key


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
@pytest.mark.parametrize("gaps", ["default", "minimum"])
def test_random_grouped_graphs_with_loops_avoid_foreign_groups_and_stay_in_lanes(seed, lanes, groups, direction, gaps):
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, 9, 14, lanes, groups)
    edges = (*edges, ("n0", "n0"), ("n0", "n0"), ("n1", "n1"), ("n3", "n3"), ("n2", "n4"), ("n2", "n4"))
    nodes = tuple(LayoutNode(*row) for row in rows)
    small = {"node_gap": 0.0, "layer_gap": 0.0, "margin": 0.0, "group_padding": 0.05} if gaps == "minimum" else {}
    options = LayoutOptions(direction=direction, parents=parents, **small)
    layout = layered_layout(nodes, edges, lane_ids, group_ids, options)
    _check(layout, nodes, parents)
    _check_routes(layout)
