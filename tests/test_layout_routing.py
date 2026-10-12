"""Property tests for the page shape: wrapping keeps the graph and picks the row count nearest the target."""

import math

import pytest
from helpers.graphs import random_graph

from vsdxkit import layout as lo
from vsdxkit.errors import GraphError
from vsdxkit.layout import LayoutNode, layered_layout


def chain(n):
    """A linear flow of `n` equal boxes."""
    nodes = tuple(LayoutNode(f"s{i}", 2.4, 1.0) for i in range(n))
    return nodes, tuple((f"s{i}", f"s{i + 1}") for i in range(n - 1))


@pytest.mark.parametrize("n", range(8, 61, 4))
def test_a_chain_of_8_to_60_steps_is_in_the_band_or_refused_never_a_strip(n):
    nodes, edges = chain(n)
    try:
        lay = layered_layout(nodes, edges)
    except GraphError:
        return
    assert 1.33 <= lay.width / lay.height <= 2.22


def test_the_row_count_is_the_one_that_minimises_the_distance_from_the_target(monkeypatch):
    nodes, edges = chain(25)
    lay = layered_layout(nodes, edges)
    chosen = round(abs(math.log(lay.width / lay.height / (16 / 9))), 2)
    for rows in range(1, 26):
        monkeypatch.setattr(
            lo,
            "_choose_starts",
            lambda w, h, g, t, f, frame=(0.0, 0.0, 0.0), rows=rows: lo._partition(w, rows, f),
        )
        forced = layered_layout(nodes, edges)
        assert chosen <= round(abs(math.log(forced.width / forced.height / (16 / 9))), 2) + 0.01


@pytest.mark.parametrize("seed", range(5))
def test_wrapping_preserves_the_graph(seed):
    rows, edges, *_ = random_graph(seed, 40, 60, 0, 0)
    nodes = tuple(LayoutNode(*row) for row in rows)
    lay = layered_layout(nodes, edges)
    assert set(lay.nodes) == {n.id for n in nodes}
    assert len(lay.routes) == len(edges)


def test_the_row_choice_for_a_long_flow_does_the_work_of_one_table(monkeypatch):
    """A14: choosing among every row count shares one partition table, so the grid snaps stay near L squared."""
    calls = [0]
    real = lo.snap

    def counting(value):
        calls[0] += 1
        return real(value)

    monkeypatch.setattr(lo, "snap", counting)
    widths = [2.4 + 0.1 * (i % 3) for i in range(100)]
    lo._choose_starts(widths, [1.0] * 100, 0.6, lo.PageTarget(), frozenset())
    assert calls[0] < 50_000


def test_equal_distances_from_the_target_keep_the_fewer_rows(monkeypatch):
    """A8 tie: with one row and two rows equally far from the target, the first (fewer rows) wins."""
    monkeypatch.setattr(
        lo,
        "_estimate",
        lambda w, h, starts, gap, frame=None: (
            (2.0, 1.0) if len(starts) == 1 else (1.0, 2.0) if len(starts) == 2 else (100.0, 1.0)
        ),
    )
    starts = lo._choose_starts([1.0] * 4, [1.0] * 4, 0.5, lo.PageTarget(aspect=1.0), frozenset())
    assert starts == (0,)
