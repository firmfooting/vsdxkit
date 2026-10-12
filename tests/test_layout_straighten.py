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
