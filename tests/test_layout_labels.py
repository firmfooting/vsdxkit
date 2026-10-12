"""Label placement (A7): a label sits on its own route, in one lane band, clear of everything else."""

from types import SimpleNamespace as NS

import layout_corpus as corpus
import pytest
from helpers import route_metrics as rm

from vsdxkit.errors import GraphError
from vsdxkit.layout import LayoutNode, LayoutOptions, layered_layout


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


def test_a_label_that_fits_no_segment_raises_naming_the_edge():
    nodes = (LayoutNode("a", 1, 1), LayoutNode("b", 1, 1))
    options = LayoutOptions(page=None, edge_labels=((2.0, 0.5), (2.0, 0.5)))  # parallel routes 0.2 apart under a 0.5 label
    with pytest.raises(GraphError, match=r"'a' -> 'b'"):
        layered_layout(nodes, (("a", "b"), ("a", "b")), options=options)


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
