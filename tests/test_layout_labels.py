"""Label placement (A7): a label sits on its own route, in one lane band, clear of everything else."""

import random
from types import SimpleNamespace as NS

import layout_corpus as corpus
import pytest
from helpers import route_metrics as rm

from vsdxkit import layout as layout_module
from vsdxkit.errors import GraphError
from vsdxkit.layout import LayoutNode, LayoutOptions, PageTarget, layered_layout


def box(x, y, w, h):
    return NS(x=x, y=y, width=w, height=h)


def lay(routes, labels, nodes=None, lanes=None):
    return NS(nodes=nodes or {}, routes=routes, labels=labels, lanes=lanes or {}, width=10, height=6)


def test_a_label_on_its_own_segment_is_clean():
    assert rm.label_violations(lay({("a", "b", 0): ((0, 1), (6, 1))}, {("a", "b", 0): box(3, 1, 1, 0.3)})) == []


def test_a_label_off_its_route_is_a_violation():
    assert rm.label_violations(lay({("a", "b", 0): ((0, 1), (6, 1))}, {("a", "b", 0): box(3, 2, 1, 0.3)}))


def test_a_label_across_a_lane_border_is_a_violation():
    lanes = {"L0": box(5, 1.5, 10, 3), "L1": box(5, 4.5, 10, 3)}
    routes = {("a", "b", 0): ((3, 0.5), (3, 5))}
    assert rm.label_violations(lay(routes, {("a", "b", 0): box(3, 3, 1, 0.3)}, lanes=lanes))


def test_a_label_on_another_routes_segment_is_a_violation():
    routes = {("a", "b", 0): ((0, 1), (6, 1)), ("c", "d", 0): ((3, 0), (3, 2))}
    assert rm.label_violations(lay(routes, {("a", "b", 0): box(3, 1, 1, 0.3)}))


def test_a_label_on_a_node_another_label_or_an_obstacle_is_a_violation():
    routes = {("a", "b", 0): ((0, 1), (6, 1)), ("c", "d", 0): ((0, 1), (6, 1))}
    mine = {("a", "b", 0): box(3, 1, 1, 0.3)}
    assert rm.label_violations(lay(routes, mine, nodes={"n": box(3, 1, 1, 1)}))
    assert rm.label_violations(lay(routes, {**mine, ("c", "d", 0): box(3.2, 1, 1, 0.3)}))
    assert rm.label_violations(lay({("a", "b", 0): ((0, 1), (6, 1))}, mine), obstacles=[box(3, 1, 1, 1)])


@pytest.mark.parametrize("seed", range(8))
def test_a_label_sits_on_its_own_segment_or_the_build_raises(seed):
    try:
        layout = corpus.labelled_random_layout(seed, 24, 36)
    except GraphError as error:
        assert "->" in str(error) or "label" in str(error)  # names the edge; there is no third outcome
        return
    assert rm.label_violations(layout) == []


@pytest.mark.parametrize("seed", range(5))
def test_labels_in_lanes_stay_in_one_band(seed):
    try:
        layout = corpus.labelled_lane_layout(seed)
    except GraphError:
        return
    assert rm.label_violations(layout) == []


def test_a_label_spanning_layers_widens_one_gap():
    nodes = tuple(LayoutNode(f"s{i}", 2, 1, "L0") for i in range(8))
    chain = tuple((f"s{i}", f"s{i + 1}") for i in range(7))
    plain = layered_layout(nodes, chain, ("L0",), options=LayoutOptions(page=None))
    labels = (None,) * 7 + ((8.0, 0.3),)
    labelled = layered_layout(nodes, (*chain, ("s0", "s7")), ("L0",), options=LayoutOptions(page=None, edge_labels=labels))
    assert labelled.width - plain.width < 9.0  # one gap, not seven


def test_a_chain_of_labelled_edges_in_one_lane_does_not_grow_the_lane_by_the_sum():
    nodes = tuple(LayoutNode(f"s{i}", 2, 1, "L0") for i in range(16))
    edges = tuple((f"s{i}", f"s{i + 1}") for i in range(15))
    labels = tuple((1.0, 0.3) for _ in edges)
    lay_ = layered_layout(nodes, edges, ("L0",), options=LayoutOptions(page=None, edge_labels=labels))
    assert lay_.lanes["L0"].height < 3.0


def test_a_tall_heading_adds_clearance_on_its_own_side_only():
    nodes = (LayoutNode("a", 2, 1, "L0", "g"),)
    lay_ = layered_layout(nodes, (), ("L0",), ("g",), LayoutOptions(page=None, headings=(("g", 3.0, 2.75),)))
    node, group, lane = lay_.nodes["a"], lay_.groups["g"], lay_.lanes["L0"]
    below_node = (node.y - node.height / 2) - (lane.y - lane.height / 2)
    above_node = (lane.y + lane.height / 2) - (node.y + node.height / 2)
    assert above_node > below_node + 1.0 and group.height < lane.height  # not a symmetric lift


def test_labels_that_no_port_pitch_can_clear_raise_naming_the_edge():
    nodes = (LayoutNode("a", 1, 1), LayoutNode("b", 1, 1))
    options = LayoutOptions(
        page=None, direction="left_to_right", edge_labels=((2.0, 0.5),) * 6
    )  # six routes need 1.25 inches of side
    with pytest.raises(GraphError, match=r"'a' -> 'b'"):
        layered_layout(nodes, (("a", "b"),) * 6, options=options)


@pytest.mark.parametrize("direction", ["left_to_right", "top_down"])
@pytest.mark.parametrize("count", [2, 3, 4])
@pytest.mark.parametrize("page", [None, "default"])
def test_parallel_labelled_edges_lay_out_on_their_own_routes(direction, count, page):
    nodes = (LayoutNode("a", 1.5, 0.8), LayoutNode("b", 1.5, 0.8))
    extra = {} if page == "default" else {"page": None}
    options = LayoutOptions(direction=direction, edge_labels=((0.66, 0.3),) * count, **extra)
    assert rm.label_violations(layered_layout(nodes, (("a", "b"),) * count, options=options)) == []


def test_a_label_never_hides_another_loops_run():
    nodes = (LayoutNode("a", 2, 1),)
    options = LayoutOptions(page=None, edge_labels=((1.0, 0.3), (1.0, 0.3)))
    assert rm.label_violations(layered_layout(nodes, (("a", "a"), ("a", "a")), options=options)) == []


def test_a_label_clears_a_group_heading():
    nodes = (LayoutNode("a", 2, 1, None, "g"), LayoutNode("b", 2, 1, None, "g"))
    options = LayoutOptions(page=None, headings=(("g", 2.0, 0.5),), edge_labels=((1.0, 0.3),))
    layout = layered_layout(nodes, (("a", "b"),), (), ("g",), options)
    group = layout.groups["g"]
    heading = box(group.x, group.y + group.height / 2 - 0.25, 2.0, 0.5)
    assert rm.label_violations(layout, obstacles=[heading]) == []


def test_a_decision_label_sits_on_the_first_segment():
    nodes = tuple(LayoutNode(i, 2, 1) for i in "dyn")
    options = LayoutOptions(page=None, edge_labels=((0.6, 0.3), (0.6, 0.3)), edge_first=(True, True))
    layout = layered_layout(nodes, (("d", "y"), ("d", "n")), options=options)
    for key, label in layout.labels.items():
        (x1, y1), (x2, y2) = layout.routes[key][:2]
        assert min(x1, x2) - 1e-6 <= label.x <= max(x1, x2) + 1e-6
        assert min(y1, y2) - 1e-6 <= label.y <= max(y1, y2) + 1e-6


def _on_border(point, node, tol=1e-6):
    """Whether `point` lies on the outline of the box `node`."""
    x, y = point
    inside_x = abs(x - node.x) <= node.width / 2 + tol
    inside_y = abs(y - node.y) <= node.height / 2 + tol
    on_x = abs(abs(x - node.x) - node.width / 2) <= tol
    on_y = abs(abs(y - node.y) - node.height / 2) <= tol
    return (on_x and inside_y) or (on_y and inside_x)


def test_the_shift_that_makes_room_for_a_label_leaves_routes_on_their_nodes():
    options = LayoutOptions(
        page=None, direction="top_down", edge_labels=((3.0, 0.3),)
    )  # a wide loop label hangs past the margin
    layout = layered_layout((LayoutNode("a", 1, 1),), (("a", "a"),), options=options)
    assert layout.nodes["a"].x > 1.0  # the drawing moved right to keep the label a margin from the left edge
    for (source, target, _rank), route in layout.routes.items():
        assert _on_border(route[0], layout.nodes[source]), (source, target)
        assert _on_border(route[-1], layout.nodes[target]), (source, target)
    assert rm.label_violations(layout) == []


def test_ordinary_labelled_graphs_are_rarely_refused():
    refused = 0
    for seed in range(20):
        try:
            corpus.labelled_random_layout(seed, 24, 36)
        except GraphError:
            refused += 1
    assert refused <= 1  # 0 of 20 today; a page cut into rows falls back to one row when a label fits nowhere


# graphs that laid out before the label refusal and were refused once labels needed a clear stretch
_ONCE_REFUSED = [("random", s) for s in (1, 11, 12, 16, 26, 36, 37)] + [("lanes", s) for s in (2, 18, 32)]


@pytest.mark.parametrize(("kind", "seed"), _ONCE_REFUSED)
def test_graphs_once_refused_for_a_label_now_lay_out(kind, seed):
    lay_ = corpus.labelled_random_layout(seed, 40, 60) if kind == "random" else corpus.labelled_lane_layout(seed)
    assert rm.label_violations(lay_) == []


def test_a_label_that_fits_nowhere_climbs_the_ladder_and_keeps_a_pinned_direction(monkeypatch):
    seen = []
    real = layout_module._laid_out_once

    def refuse_until_pageless(nodes, edges, lanes, groups, options):
        seen.append(options)
        if options.page is not None:
            raise layout_module._LabelRefused("no room")
        return real(nodes, edges, lanes, groups, options)

    monkeypatch.setattr(layout_module, "_laid_out_once", refuse_until_pageless)
    nodes = tuple(LayoutNode(i, 2, 1) for i in "abc")
    options = LayoutOptions(page=PageTarget(direction="top_down"), edge_labels=((1.0, 0.3), None))
    lay_ = layered_layout(nodes, (("a", "b"), ("b", "c")), options=options)
    assert seen[0] == options and seen[1].page.wrap == "none"
    assert seen[-1].page is None and seen[-1].direction == "top_down"
    assert lay_.fallbacks == len(seen) - 1 and lay_.height > lay_.width


def test_a_label_refused_after_the_whole_ladder_names_its_edge(monkeypatch):
    calls = []

    def refuse(nodes, edges, lanes, groups, options):
        calls.append(options)
        raise layout_module._LabelRefused("the label of edge 'a' -> 'b' cannot be placed")

    monkeypatch.setattr(layout_module, "_laid_out_once", refuse)
    with pytest.raises(GraphError, match=r"'a' -> 'b'"):
        layered_layout(
            (LayoutNode("a", 1, 1), LayoutNode("b", 1, 1)), (("a", "b"),), options=LayoutOptions(edge_labels=((1.0, 0.3),))
        )
    assert len({id(o) for o in calls}) == len(calls) == 1 + 1 + len(layout_module._ROOM_FACTORS) + 1


def _flow_page(seed):
    """A documentation-flow-like page: up to 8 stages, decisions with yes/no labels, a feedback edge, labels 1.0 to 1.5 wide."""
    rng = random.Random(seed)
    stages = rng.randint(4, 8)
    nodes, edges = [LayoutNode(f"s{i}", 2.0, 1.0) for i in range(stages)], []
    for i in range(stages - 1):
        if rng.random() < 0.4 and i + 2 < stages:
            nodes.append(LayoutNode(f"x{i}", 1.4, 1.0))
            edges += [(f"s{i}", f"s{i + 1}"), (f"s{i}", f"x{i}"), (f"x{i}", f"s{i + 2}")]
        else:
            edges.append((f"s{i}", f"s{i + 1}"))
    edges.append((f"s{stages - 1}", f"s{rng.randrange(stages - 1)}"))
    labels = tuple((round(rng.uniform(1.0, 1.5), 2), 0.3) for _ in edges)
    return tuple(nodes), tuple(edges), labels


@pytest.mark.parametrize("seed", range(40))
def test_flow_like_pages_lay_out_with_clean_labels(seed):
    nodes, edges, labels = _flow_page(seed)
    lay_ = layered_layout(nodes, edges, options=LayoutOptions(edge_labels=labels))
    assert len(lay_.labels) == len(edges) and rm.label_violations(lay_) == []
