"""Port pitch: parallel routes meet a side of a box at a set spacing."""

from itertools import pairwise

import layout_corpus as corpus
import pytest
from helpers import route_metrics as rm

from vsdxkit import layout as lo
from vsdxkit.errors import GraphError
from vsdxkit.layout import LayoutNode, LayoutOptions, layered_layout


def test_five_ports_on_a_three_inch_side_sit_at_the_pitch():
    offsets = lo._spread(5, 3.0, "n", 0.2)
    assert [round(b - a, 2) for a, b in pairwise(offsets)] == [0.2] * 4


def test_a_short_side_shrinks_the_pitch_and_a_tiny_one_is_still_refused_by_name():
    offsets = lo._spread(4, 0.6, "n", 0.2)
    assert min(b - a for a, b in pairwise(offsets)) >= 0.01
    assert offsets[-1] - offsets[0] <= 0.48 + 1e-9
    with pytest.raises(GraphError, match="node 'n' is too small"):
        lo._spread(5, 0.04, "n", 0.2)


def test_ports_cover_at_most_eighty_percent_of_a_side_where_the_cap_binds():
    offsets = lo._spread(12, 2.0, "n", 0.2)  # the uncapped pitch is 0.15 and would span 1.65
    assert offsets[-1] - offsets[0] <= 1.6 + 1e-9


def test_the_pitch_never_drops_below_a_tenth_until_the_side_cannot_hold_the_ports():
    held = lo._spread(10, 1.0, "n", 0.2)  # ten ports at 0.1 fit a one inch side, past the 80 percent cap
    assert round(held[1] - held[0], 2) == 0.1
    shrunk = lo._spread(12, 1.0, "n", 0.2)  # twelve at 0.1 do not
    assert min(b - a for a, b in pairwise(shrunk)) >= 0.01 and shrunk[1] - shrunk[0] < 0.1


def test_the_new_options_are_appended_after_the_existing_fields():
    opts = LayoutOptions(
        "left_to_right", 1.0, 0.4, 0.5, 0.25, 0.3, 0.6, 8, None, (("c", "p"),), (("c", 1.0, 0.2),), ((1.0, 0.2),)
    )
    assert (opts.page, opts.parents, opts.headings, opts.edge_labels) == (
        None,
        (("c", "p"),),
        (("c", 1.0, 0.2),),
        ((1.0, 0.2),),
    )
    assert (opts.port_pitch, opts.channel_pitch) == (0.2, 0.2)


def test_a_port_pitch_reaches_the_ports_of_a_layout():
    nodes = (LayoutNode("hub", 2, 4), *(LayoutNode(f"t{i}", 1, 1) for i in range(3)))
    edges = tuple(("hub", f"t{i}") for i in range(3))

    def gap(pitch):
        layout = layered_layout(nodes, edges, options=LayoutOptions(port_pitch=pitch, page=None))
        ys = sorted(r[0][1] for r in layout.routes.values())
        return round(min(b - a for a, b in pairwise(ys)), 2)

    assert gap(0.4) == 0.4 and gap(0.1) == 0.1


@pytest.mark.parametrize("name", ["hub5", "hub5_top_down", "fanin"])
def test_no_two_ports_on_a_side_are_closer_than_the_pitch(name):
    assert rm.port_gap_violations(corpus.fixture_layout(name)) == []


@pytest.mark.parametrize("option", ["port_pitch", "channel_pitch"])
@pytest.mark.parametrize("bad", [0.0, 0.005, float("nan"), float("inf"), -1.0, True])
def test_a_pitch_that_is_not_valid_is_refused_by_name(option, bad):
    with pytest.raises(GraphError, match=option):
        layered_layout((LayoutNode("a", 2, 1),), (), options=LayoutOptions(**{option: bad}))


def test_a_hub_with_five_children_has_no_crossing_and_no_shared_run():
    lay = corpus.fixture_layout("hub5")
    assert rm.crossings(lay) == 0 and rm.shared_runs(lay) == []


def test_a_top_down_hub_with_five_children_has_no_crossing_and_no_shared_run():
    lay = corpus.fixture_layout("hub5_top_down")
    assert rm.crossings(lay) == 0 and rm.shared_runs(lay) == []


def test_fan_in_has_no_crossing_either():
    lay = corpus.fixture_layout("fanin")
    assert rm.crossings(lay) == 0 and rm.port_order_violations(lay) == []


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(
            n,
            marks=pytest.mark.xfail(
                strict=True,
                reason="chain25's feedback edge shares the forward edge's side of p20; Task 28 routes feedback in an outer corridor",
            )
            if n == "chain25"
            else (),
        )
        for n in corpus.FIXTURES
    ],
)
def test_ports_are_ordered_against_their_far_ends_on_every_fixture(name):
    assert rm.port_order_violations(corpus.fixture_layout(name)) == []


def _tree_layout(seed):
    from helpers.graphs import random_tree

    ids, edges = random_tree(seed, 30)
    return layered_layout(tuple(LayoutNode(i, 2.0, 1.0) for i in ids), edges)


@pytest.mark.parametrize("seed", range(10))
def test_a_random_tree_has_no_shared_run_and_ordered_ports(seed):
    lay = _tree_layout(seed)
    assert rm.shared_runs(lay) == []
    assert rm.port_order_violations(lay) == []


@pytest.mark.xfail(
    strict=True,
    reason="the layer order of a tree can still put two sibling subtrees across each other; Task 23 adds crossing-aware ordering",
)
@pytest.mark.parametrize("seed", range(10))
def test_a_random_tree_has_no_crossing(seed):
    assert rm.crossings(_tree_layout(seed)) == 0


def test_parallel_and_opposite_edges_keep_ports_and_channels_of_their_own():
    nodes = (LayoutNode("a", 2, 1), LayoutNode("b", 2, 1))
    lay = layered_layout(nodes, (("a", "b"), ("a", "b"), ("b", "a")))
    assert rm.shared_runs(lay) == [] and rm.port_gap_violations(lay) == []


def _items(*spans):
    """Gap items (low, high, edge, hop) for edges 0.. with one hop each."""
    return [(lo, hi, n, 0) for n, (lo, hi) in enumerate(spans)]


def test_two_edges_leaving_a_node_the_same_way_nest_the_farthest_first():
    chains = [["s", "x"], ["s", "y"]]
    rows_of = [[1.0, 2.0], [1.2, 5.0]]  # both go up; the second goes farther
    assert lo._nests_left(_items((1.0, 2.0), (1.2, 5.0)), rows_of, chains) == [[1], []]


def test_two_edges_arriving_at_a_node_the_same_way_nest_the_nearest_origin_first():
    chains = [["x", "t"], ["y", "t"]]
    rows_of = [[1.0, 3.2], [0.0, 3.0]]  # both come from below; the first origin is nearer and its port is the higher
    assert lo._nests_left(_items((1.0, 3.2), (0.0, 3.0)), rows_of, chains) == [[], [0]]


def test_edges_that_share_no_node_or_leave_in_opposite_directions_do_not_nest():
    chains = [["s", "x"], ["s", "y"], ["p", "q"]]
    rows_of = [[2.0, 4.0], [1.8, 0.0], [10.0, 20.0]]
    assert lo._nests_left(_items((2.0, 4.0), (0.0, 1.8), (10.0, 20.0)), rows_of, chains) == [[], [], []]


def test_a_hop_that_leaves_inside_the_run_of_another_hop_lies_nearer_the_layer():
    chains = [["a", "x"], ["b", "y"]]
    rows_of = [[8.0, 4.5], [6.6, 3.1]]  # both go down and their spans overlap
    assert lo._nests_left(_items((4.5, 8.0), (3.1, 6.6)), rows_of, chains) == [[1], []]


def test_siblings_drop_to_as_few_heights_as_their_overlapping_runs_allow():
    lay = corpus.fixture_layout("hub5_top_down")
    runs: dict[str, list[tuple[float, float, float]]] = {}
    for (source, _target, _i), route in lay.routes.items():
        for (x1, y1), (x2, y2) in pairwise(rm.simplified(route)):
            if y1 == y2 and x1 != x2:
                runs.setdefault(source, []).append((y1, min(x1, x2), max(x1, x2)))
    for source, found in runs.items():
        # the most runs that overlap one another at a point is the fewest heights that keep them apart
        deepest = max(sum(a - 0.1 < x < b + 0.1 for _y, a, b in found) for _y, x, _b in found)
        assert len({y for y, _a, _b in found}) <= deepest, (source, found)


def _gap_between(pitch):
    nodes = (LayoutNode("hub", 2, 4), *(LayoutNode(f"t{i}", 1, 1) for i in range(5)))
    edges = tuple(("hub", f"t{i}") for i in range(5))
    lay = layered_layout(nodes, edges, options=LayoutOptions(channel_pitch=pitch, page=None))
    return lay.nodes["t0"].x - lay.nodes["t0"].width / 2 - (lay.nodes["hub"].x + lay.nodes["hub"].width / 2)


def test_the_default_gap_widens_to_hold_its_channels_at_the_channel_pitch():
    assert _gap_between(0.4) >= 6 * 0.4 - 1e-9 > _gap_between(0.2)


def test_an_explicit_gap_keeps_its_width_and_only_a_gap_below_a_step_per_channel_is_refused():
    nodes = (LayoutNode("hub", 2, 4), *(LayoutNode(f"t{i}", 1, 1) for i in range(5)))
    edges = tuple(("hub", f"t{i}") for i in range(5))
    lay = layered_layout(nodes, edges, options=LayoutOptions(layer_gap=0.5, channel_pitch=0.4, page=None))
    assert 0.5 <= lay.nodes["t0"].x - 0.5 - (lay.nodes["hub"].x + 1.0) < 0.55
    with pytest.raises(GraphError, match="layer_gap"):
        layered_layout(nodes, edges, options=LayoutOptions(layer_gap=0.01, page=None))
