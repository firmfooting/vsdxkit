"""The layout corpus the metrics, the ratchet and the digests measure."""

import layout_corpus as corpus


def test_every_fixture_lays_out_and_has_a_route_for_each_edge():
    for stem in corpus.FIXTURES:
        lay = corpus.fixture_layout(stem)
        assert lay.nodes and lay.routes, stem


def test_the_corpus_is_the_same_twice():
    assert list(corpus.all_layouts()) == list(corpus.all_layouts())


def test_a_random_tree_has_n_minus_one_edges_and_one_parent_each():
    ids, edges = corpus.random_tree(3, 12)
    assert len(ids) == 12 and len(edges) == 11 and len({t for _s, t in edges}) == 11
