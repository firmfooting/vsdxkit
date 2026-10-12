"""The layout corpus the metrics, the ratchet and the digests measure."""

from dataclasses import replace

import layout_corpus as corpus


def _expected_routes(stem):
    """The (source, target, n) key of each non-page-link edge of fixture `stem`, n counting parallel edges."""
    seen, keys = {}, set()
    for edge in corpus._load(stem).page().edges:
        if edge.kind != "page-link":
            n = seen[edge.source, edge.target] = seen.get((edge.source, edge.target), -1) + 1
            keys.add((edge.source, edge.target, n))
    return keys


def _route_gaps(stem, lay):
    """The route keys fixture `stem` should have and `lay` lacks, then the ones it has and should not."""
    want = _expected_routes(stem)
    return want - set(lay.routes), set(lay.routes) - want


def test_every_fixture_lays_out_and_has_a_route_for_each_edge():
    for stem in corpus.FIXTURES:
        lay = corpus.fixture_layout(stem)
        assert lay.nodes, stem
        assert _route_gaps(stem, lay) == (set(), set()), stem


def test_the_route_check_notices_a_dropped_edge():
    lay = corpus.fixture_layout("hub5")
    dropped = dict(lay.routes)
    dropped.popitem()
    assert _route_gaps("hub5", replace(lay, routes=dropped))[0]


def test_the_corpus_is_the_same_twice():
    assert corpus.all_layouts() == corpus.all_layouts()


def test_a_random_tree_has_n_minus_one_edges_and_one_parent_each():
    ids, edges = corpus.random_tree(3, 12)
    assert len(ids) == 12 and len(edges) == 11 and len({t for _s, t in edges}) == 11
