"""Crossing-aware ordering and straightening of the layered layout."""

from dataclasses import replace

import layout_corpus as corpus
import pytest
from helpers import route_metrics as rm

from vsdxkit import layout as lo
from vsdxkit.layout import LayoutNode, LayoutOptions, layered_layout


def test_a_crossing_is_two_links_in_opposite_order():
    links = [("a", "y"), ("b", "x")]
    assert lo._count_crossings(["a", "b"], ["x", "y"], links) == 1
    assert lo._count_crossings(["a", "b"], ["y", "x"], links) == 0
    assert lo._count_crossings(["a", "b"], ["x"], [("a", "x"), ("b", "x")]) == 0


def test_a_bipartite_graph_with_a_crossing_free_order_is_laid_out_without_crossings():
    nodes = tuple(LayoutNode(i, 2, 1) for i in ("a1", "a2", "a3", "b1", "b2", "b3"))
    edges = (("a1", "b3"), ("a2", "b2"), ("a3", "b1"))  # input order is the worst order
    lay = layered_layout(nodes, edges, options=LayoutOptions(page=None))
    assert rm.crossings(lay) == 0


@pytest.mark.parametrize("name", ["chain25", "lanes3"])
def test_the_long_fixtures_have_no_crossings(name):
    assert rm.crossings(corpus.fixture_layout(name)) == 0


def test_fit_keeps_wants_that_already_fit_and_pushes_apart_wants_that_overlap():
    assert lo._fit([1.0, 5.0], [1.0, 1.0], 0.0, 10.0, 0.4) == [1.0, 5.0]
    a, b = lo._fit([3.0, 3.0], [1.0, 1.0], 0.0, 10.0, 0.4)
    assert b - a >= 1.4 - 1e-9 and a >= 0.5 and b <= 9.5


def test_fit_stays_inside_the_bounds_when_the_run_fits():
    centres = lo._fit([0.0, 0.0, 0.0], [1.0, 1.0, 1.0], 0.0, 4.0, 0.25)
    assert centres[0] >= 0.5 and centres[-1] <= 3.5


def test_a_straightened_chain_has_no_bends():
    nodes = tuple(LayoutNode(f"s{i}", 2, 1 + (i % 2)) for i in range(5))
    edges = tuple((f"s{i}", f"s{i + 1}") for i in range(4))
    lay = layered_layout(nodes, edges, options=LayoutOptions(page=None))
    assert all(rm.bends(r) == 0 for r in lay.routes.values())


def test_a_ladder_is_stable_under_more_sweeps():
    nodes = tuple(LayoutNode(f"{c}{i}", 2, 1) for c in "ab" for i in range(6))
    edges = tuple((f"{c}{i}", f"{c}{i + 1}") for c in "ab" for i in range(5)) + tuple((f"a{i}", f"b{i}") for i in range(6))
    six = layered_layout(nodes, edges, options=LayoutOptions(page=None, straighten_sweeps=6))
    seven = layered_layout(nodes, edges, options=LayoutOptions(page=None, straighten_sweeps=7))
    assert {k: (b.x, b.y) for k, b in six.nodes.items()} == {k: (b.x, b.y) for k, b in seven.nodes.items()}


def test_straightening_never_leaves_a_lane_or_raises_it():
    nodes = (LayoutNode("a", 2, 1, "L0"), LayoutNode("b", 2, 1, "L1"), LayoutNode("c", 2, 1, "L1"))
    edges = (("a", "b"), ("a", "c"))
    on = layered_layout(nodes, edges, lanes=("L0", "L1"))
    off = layered_layout(nodes, edges, lanes=("L0", "L1"), options=LayoutOptions(straighten_sweeps=0))
    assert [on.lanes[k].height for k in on.lanes] == [off.lanes[k].height for k in off.lanes]
    for name in ("b", "c"):
        box, lane = on.nodes[name], on.lanes["L1"]
        assert lane.y - lane.height / 2 <= box.y - box.height / 2
        assert box.y + box.height / 2 <= lane.y + lane.height / 2


def test_a_pin_places_a_node_in_its_layer():
    nodes = (LayoutNode("a", 2, 1), LayoutNode("b", 2, 1), LayoutNode("c", 2, 1))
    lay = layered_layout(nodes, (("a", "b"),), options=LayoutOptions(page=None, pinned=(("c", 2),)))
    assert lay.nodes["c"].x > lay.nodes["b"].x


def test_a_pin_at_or_before_a_predecessor_names_both_ids():
    nodes = (LayoutNode("a", 2, 1), LayoutNode("b", 2, 1))
    with pytest.raises(lo.GraphError, match=r"'b' is pinned to layer 0.*'a'.*layer 0"):
        layered_layout(nodes, (("a", "b"),), options=LayoutOptions(pinned=(("a", 0), ("b", 0))))


def test_a_pin_pushes_a_successor_and_does_not_collide_with_a_dummy():
    nodes = tuple(LayoutNode(i, 2, 1) for i in "abcd")
    lay = layered_layout(nodes, (("a", "b"), ("b", "c"), ("a", "d")), options=LayoutOptions(page=None, pinned=(("b", 3),)))
    xs = {k: b.x for k, b in lay.nodes.items()}
    assert xs["b"] < xs["c"] and len({round(x, 2) for x in xs.values()}) == 4


def test_a_pin_into_a_layer_a_long_edge_crosses_shares_no_box_or_run():
    nodes = tuple(LayoutNode(i, 2, 1) for i in "abcde")
    edges = (("a", "b"), ("b", "d"), ("d", "e"), ("a", "e"))  # a -> e crosses layers 1 to 2 on dummy slots
    lay = layered_layout(nodes, edges, options=LayoutOptions(page=None, pinned=(("c", 2),)))
    boxes = list(lay.nodes.values())
    for i, p in enumerate(boxes):
        for q in boxes[i + 1 :]:
            assert abs(p.x - q.x) >= (p.width + q.width) / 2 or abs(p.y - q.y) >= (p.height + q.height) / 2
    assert lay.nodes["c"].x == lay.nodes["d"].x > lay.nodes["b"].x
    assert rm.shared_runs(lay) == []


def test_a_pin_on_a_node_in_a_cycle_names_it():
    nodes = tuple(LayoutNode(i, 2, 1) for i in "abc")
    edges = (("a", "b"), ("b", "c"), ("c", "a"))
    for name in "abc":
        with pytest.raises(lo.GraphError, match=rf"'{name}' is pinned to a layer, but it lies on a cycle"):
            layered_layout(nodes, edges, options=LayoutOptions(pinned=((name, 4),)))


def test_a_pin_on_an_id_that_is_not_a_node_names_it():
    with pytest.raises(lo.GraphError, match=r"'ghost' is pinned to a layer, but the page has no such node"):
        layered_layout((LayoutNode("a", 2, 1),), (), options=LayoutOptions(pinned=(("ghost", 1),)))


def test_a_node_pinned_twice_is_refused_naming_it():
    with pytest.raises(lo.GraphError, match=r"'a' is pinned more than once"):
        layered_layout((LayoutNode("a", 2, 1),), (), options=LayoutOptions(pinned=(("a", 1), ("a", 2))))


def test_a_negative_pin_is_refused():
    with pytest.raises(lo.GraphError, match=r"'a' is pinned to layer -1"):
        layered_layout((LayoutNode("a", 2, 1),), (), options=LayoutOptions(pinned=(("a", -1),)))


def test_aligned_nodes_share_a_row():
    nodes = tuple(LayoutNode(i, 2, 1) for i in "abcd")
    lay = layered_layout(nodes, (("a", "b"), ("a", "c"), ("c", "d")), options=LayoutOptions(page=None, aligned=(("b", "d"),)))
    assert lay.nodes["b"].y == lay.nodes["d"].y


def test_aligned_nodes_share_a_row_without_sweeps():
    nodes = tuple(LayoutNode(i, 2, 1) for i in "abcd")
    lay = layered_layout(
        nodes,
        (("a", "b"), ("a", "c"), ("c", "d")),
        options=LayoutOptions(page=None, straighten_sweeps=0, aligned=(("b", "d"),)),
    )
    assert lay.nodes["b"].y == lay.nodes["d"].y


def test_two_members_of_one_group_in_one_layer_are_refused():
    nodes = tuple(LayoutNode(i, 2, 1) for i in "abc")
    with pytest.raises(lo.GraphError, match=r"'b'.*'c'"):
        layered_layout(nodes, (("a", "b"), ("a", "c")), options=LayoutOptions(aligned=(("b", "c"),)))


def test_an_align_group_naming_an_unknown_node_or_repeating_one_is_refused():
    nodes = tuple(LayoutNode(i, 2, 1) for i in "abcd")
    edges = (("a", "b"), ("b", "c"), ("c", "d"))
    with pytest.raises(lo.GraphError, match="'z'"):
        layered_layout(nodes, edges, options=LayoutOptions(aligned=(("a", "z"),)))
    with pytest.raises(lo.GraphError, match=r"'b'.*two align groups"):
        layered_layout(nodes, edges, options=LayoutOptions(aligned=(("a", "b"), ("b", "c"))))


def test_an_align_group_that_cannot_share_a_row_is_refused_naming_its_members():
    nodes = (LayoutNode("a", 2, 1, "L0"), LayoutNode("b", 2, 1, "L1"))
    with pytest.raises(lo.GraphError, match=r"align group.*'a'.*'b'"):
        layered_layout(nodes, (("a", "b"),), lanes=("L0", "L1"), options=LayoutOptions(aligned=(("a", "b"),)))


def test_even_columns_give_every_layer_one_pitch():
    nodes = (LayoutNode("a", 1, 1), LayoutNode("b", 3, 1), LayoutNode("c", 2, 1))
    lay = layered_layout(nodes, (("a", "b"), ("b", "c")), options=LayoutOptions(page=None, columns="even"))
    xs = [lay.nodes[k].x for k in "abc"]
    assert round(xs[1] - xs[0], 2) == round(xs[2] - xs[1], 2)


def test_a_columns_value_that_is_not_known_is_refused_by_name():
    with pytest.raises(lo.GraphError, match="columns"):
        layered_layout((LayoutNode("a", 1, 1),), (), options=replace(LayoutOptions(), **{"columns": "wide"}))


def test_a_feedback_edge_leaves_no_dummy_and_runs_outside_the_drawing():
    lay = corpus.fixture_layout("chain25")
    route = lay.routes[("p20", "p14", 0)]
    assert rm.bends(route) <= 4
    assert lay.fallbacks == 0


def test_a_feedback_edge_does_not_widen_the_layers_it_jumps():
    nodes = tuple(LayoutNode(f"s{i}", 2, 1) for i in range(6))
    chain = tuple((f"s{i}", f"s{i + 1}") for i in range(5))
    plain = layered_layout(nodes, chain, options=LayoutOptions(page=None))
    back = layered_layout(nodes, (*chain, ("s5", "s1")), options=LayoutOptions(page=None))
    assert back.width == plain.width and back.height <= plain.height + 1.0


def test_a_feedback_edge_in_a_lane_stays_in_its_lane():
    nodes = tuple(LayoutNode(f"s{i}", 2, 1, "L0") for i in range(4))
    edges = (("s0", "s1"), ("s1", "s2"), ("s2", "s3"), ("s3", "s1"))
    lay = layered_layout(nodes, edges, lanes=("L0",))
    lane = lay.lanes["L0"]
    for _x, y in lay.routes[("s3", "s1", 0)]:
        assert lane.y - lane.height / 2 - 1e-6 <= y <= lane.y + lane.height / 2 + 1e-6


def test_several_feedback_edges_nest_and_do_not_share_a_run():
    nodes = tuple(LayoutNode(f"s{i}", 2, 1) for i in range(8))
    chain = tuple((f"s{i}", f"s{i + 1}") for i in range(7))
    lay = layered_layout(nodes, (*chain, ("s6", "s2"), ("s7", "s4")), options=LayoutOptions(page=None))
    assert rm.shared_runs(lay) == [] and rm.crossings(lay) <= 1
