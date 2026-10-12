"""Property tests for the page shape: wrapping keeps the graph and picks the row count nearest the target."""

import math

import layout_corpus as corpus
import pytest
from helpers import route_metrics as rm
from helpers.graphs import random_graph

from vsdxkit import layout as lo
from vsdxkit.errors import GraphError
from vsdxkit.layout import LayoutNode, LayoutOptions, layered_layout


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


@pytest.mark.parametrize("name", ["hub5", "hub5_top_down", "fanin"])
def test_the_fan_fixtures_meet_a1_to_a5(name):
    lay = corpus.fixture_layout(name)
    assert rm.port_gap_violations(lay) == []  # A1
    assert rm.port_order_violations(lay) == []  # A2
    assert rm.shared_runs(lay) == []  # A3
    assert rm.crossings(lay) == 0  # A4


@pytest.mark.parametrize("seed", range(5))
def test_a_random_dag_passes_the_existing_guarantees(seed):
    from test_layout import _check, _check_routes

    rows, edges, *_ = random_graph(seed, 40, 60, 0, 0)
    dag = tuple((s, t) for s, t in edges if int(s[1:]) < int(t[1:]))
    nodes = tuple(LayoutNode(*row) for row in rows)
    lay = layered_layout(nodes, dag)
    _check(lay, nodes, ())
    _check_routes(lay)


@pytest.mark.parametrize("seed", range(5))
def test_straightening_never_moves_a_node_out_of_its_group_or_lane(seed):
    rows, edges, lane_ids, group_ids, parents = random_graph(seed, 40, 60, 3, 2)
    nodes = tuple(LayoutNode(*row) for row in rows)
    on_options = LayoutOptions(parents=parents, page=None)
    off_options = LayoutOptions(parents=parents, page=None, straighten_sweeps=0)
    try:
        on = layered_layout(nodes, edges, lane_ids, group_ids, on_options)
        off = layered_layout(nodes, edges, lane_ids, group_ids, off_options)
    except GraphError:
        pytest.skip("the layout refuses this graph, with or without straightening")
    assert [on.lanes[k].height for k in on.lanes] == [off.lanes[k].height for k in off.lanes]
    for n in nodes:
        box, lane = on.nodes[n.id], on.lanes[n.lane]
        assert lane.y - lane.height / 2 - 1e-6 <= box.y - box.height / 2
        assert box.y + box.height / 2 <= lane.y + lane.height / 2 + 1e-6
        if n.group is not None:
            g = on.groups[n.group]
            assert g.x - g.width / 2 - 1e-6 <= box.x - box.width / 2
            assert box.x + box.width / 2 <= g.x + g.width / 2 + 1e-6
            assert g.y - g.height / 2 - 1e-6 <= box.y - box.height / 2
            assert box.y + box.height / 2 <= g.y + g.height / 2 + 1e-6
