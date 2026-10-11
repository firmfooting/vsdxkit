"""The layered layout: boxes never overlap, routes are orthogonal and meet no node, and the result depends on nothing but the arguments."""

import os
import random
import subprocess
import sys
import time
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


def test_a_200_node_graph_with_lanes_and_groups_is_refused_not_drawn_with_shared_runs():
    """This many routes round this many groups cannot all get a line of their own, so the layout fails closed."""
    rows, edges, lane_ids, group_ids, parents = random_graph(1, 200, 320, 4, 4)
    nodes = tuple(LayoutNode(*row) for row in rows)
    with pytest.raises(GraphError, match=r"cannot be kept apart|too crowded"):
        layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))


def test_a_150_node_graph_with_lanes_and_groups_lays_out_with_no_shared_run():
    """The exit criterion: a graph of this size lays out with no violation, with a 60 s hang guard (about 2.3 s locally)."""
    rows, edges, lane_ids, group_ids, parents = random_graph(1, 150, 240, 4, 4)
    nodes = tuple(LayoutNode(*row) for row in rows)
    start = time.perf_counter()
    layout = layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))
    assert time.perf_counter() - start < 60
    assert len(layout.routes) == 240
    _check(layout, nodes, parents)
    _check_routes(layout)


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
    _check_no_shared_run(layout)


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
    _check_routes(layout)


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
def test_a_crowded_graph_of_200_nodes_and_20_groups_is_refused_not_drawn_with_shared_runs(direction):
    """About 18 s to reach the search limit."""
    rows, edges, lane_ids, group_ids, parents = random_graph(1, 200, 400, 0, 20)
    nodes = tuple(LayoutNode(*row) for row in rows)
    with pytest.raises(GraphError, match=r"too crowded|cannot be kept apart"):
        layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(direction=direction, parents=parents))


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
    _check_routes(layout)


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


def _label_and_heading_sizes(seed, edges, group_ids):
    rng = random.Random(seed)
    labels = tuple((rng.choice([0.3, 0.66, 1.2]), rng.choice([0.3, 0.3, 0.55])) for _ in edges)
    headings = tuple((g, rng.choice([0.8, 1.5, 3.0]), rng.choice([0.25, 0.5, 0.75])) for g in group_ids)
    return labels, headings


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
    [(0, 0, "left_to_right"), (0, 0, "top_down"), (3, 0, "left_to_right"), (3, 3, "left_to_right"), (0, 3, "top_down")],
)
def test_labels_and_headings_get_room_in_random_graphs(seed, lanes, groups, direction):
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, 7, 10, lanes, groups)
    edges = (*edges, edges[0], edges[0], (edges[1][0], edges[1][0]), edges[2][::-1])
    nodes = tuple(LayoutNode(*row) for row in rows)
    labels, headings = _label_and_heading_sizes(seed, edges, group_ids)
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
    plain = layered_layout(nodes, (("a", "b"),))
    wide = layered_layout(nodes, (("a", "b"),), options=LayoutOptions(edge_labels=((2.7, 0.3),)))
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
    layout = layered_layout(nodes, (("b", "a"),), options=LayoutOptions(edge_labels=((2.0, 0.3),)))
    right = max(box.x + box.width / 2 for box in layout.nodes.values())
    assert layout.width == pytest.approx(right + 0.5, abs=0.02)
