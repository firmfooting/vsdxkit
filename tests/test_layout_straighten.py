"""Crossing-aware ordering and straightening of the layered layout."""

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


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(
            n,
            marks=pytest.mark.xfail(
                strict=True,
                reason="chain25's feedback edge leaves p20 across the forward edge into it; Task 28 routes feedback in an outer corridor",
            )
            if n == "chain25"
            else (),
        )
        for n in ("chain25", "lanes3")
    ],
)
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
