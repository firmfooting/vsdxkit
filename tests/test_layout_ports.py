"""Port pitch: parallel routes meet a side of a box at a set spacing."""

import sys
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
    nodes = (LayoutNode("a", 2, 2), LayoutNode("b", 2, 2))
    edges = (("a", "b"),) * 3  # boxes that overlap fully keep their ports on one side, where an L would leave it

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


def _tree_seed_marks(seed):
    """The strict xfail for the two seeds whose crossings survive ordering: seed 3 only crosses once the page wraps, seed 4 keeps one layer crossing."""
    reasons = {
        3: "the layers are crossing free but the snake wrap folds the tree so two routes cross; the wrap's fold is not an ordering matter",
        4: "barycentre sweeps and transposition leave one crossing between two layers of this tree",
    }
    return pytest.mark.xfail(strict=True, reason=reasons[seed]) if seed in reasons else ()


@pytest.mark.parametrize("seed", [pytest.param(n, marks=_tree_seed_marks(n)) for n in range(10)])
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


def _crossing_pairs(lay):
    keys = list(lay.routes)
    segs = {k: list(pairwise(rm.simplified(lay.routes[k]))) for k in keys}
    return [
        (a, b) for i, a in enumerate(keys) for b in keys[i + 1 :] if any(rm._crosses(x, y) for x in segs[a] for y in segs[b])
    ]


def test_a_cycle_in_the_channel_order_does_not_make_siblings_cross():
    from helpers.graphs import random_tree

    ids, edges = random_tree(5, 30)
    lay = layered_layout(tuple(LayoutNode(i, 2.0, 1.0) for i in ids), edges, options=LayoutOptions(page=None))
    assert not [p for p in _crossing_pairs(lay) if p[0][0] == p[1][0]], _crossing_pairs(lay)


@pytest.mark.parametrize("children", [12, 20, 40])
def test_a_gap_busier_than_the_pitched_channels_still_lays_out_with_clear_channels(children):
    nodes = (LayoutNode("hub", 2, 4), *(LayoutNode(f"t{i}", 1, 1) for i in range(children)))
    edges = tuple(("hub", f"t{i}") for i in range(children))
    lay = layered_layout(nodes, edges, options=LayoutOptions(page=None))
    assert rm.crossings(lay) == 0 and rm.shared_runs(lay) == []
    for route in lay.routes.values():
        assert all(a != b for a, b in pairwise(route))
    columns = sorted({round(r[2][0], 2) for r in lay.routes.values() if len(rm.simplified(r)) == 4})
    assert all(b - a >= 0.01 - 1e-9 for a, b in pairwise(columns))


def test_a_chain_of_equal_boxes_has_straight_edges():
    nodes = tuple(LayoutNode(f"s{i}", 2, 1) for i in range(4))
    lay = layered_layout(nodes, tuple((f"s{i}", f"s{i + 1}") for i in range(3)), options=LayoutOptions(page=None))
    assert all(rm.bends(r) == 0 for r in lay.routes.values())


def test_the_middle_child_of_a_hub_is_reached_by_a_straight_edge():
    lay = corpus.fixture_layout("hub5")
    children = sorted((k for k in lay.nodes if k.startswith("c")), key=lambda k: lay.nodes[k].x)
    assert rm.bends(lay.routes[("hub", children[2], 0)]) == 0


def test_two_edges_for_one_straight_run_do_not_share_it():
    nodes = (LayoutNode("a", 2, 1), LayoutNode("b", 2, 1), LayoutNode("c", 2, 1))
    lay = layered_layout(nodes, (("a", "c"), ("b", "c")), options=LayoutOptions(page=None))
    assert rm.shared_runs(lay) == [] and rm.port_gap_violations(lay) == []


def test_the_two_drops_into_the_sink_of_the_top_down_hub_have_no_jog():
    lay = corpus.fixture_layout("hub5_top_down")
    assert rm.bends(lay.routes[("c4", "archive", 0)]) <= 1
    assert rm.bends(lay.routes[("c2", "archive", 0)]) <= 2


def test_a_cross_lane_edge_between_adjacent_columns_has_one_bend():
    lay = corpus.fixture_layout("lanes3")
    for key in (("s2", "s3", 0), ("s4", "s5", 0), ("s6", "s7", 0)):
        assert rm.bends(lay.routes[key]) <= 1, key


def test_an_l_route_is_not_taken_through_a_box_in_the_source_column():
    nodes = (
        LayoutNode("a", 2, 1, "L0"),
        LayoutNode("blocker", 2, 1, "L1"),
        LayoutNode("b", 2, 1, "L2"),
        LayoutNode("c", 2, 1, "L0"),
    )
    lay = layered_layout(nodes, (("a", "b"), ("c", "b")), lanes=("L0", "L1", "L2"))
    from test_layout import _check_routes

    _check_routes(lay)
    route = lay.routes[("a", "b", 0)]
    # the stub down from a would cross the blocker, so a runs along its own row and enters b by its top instead
    assert rm.bends(route) == 1 and route[0][1] == route[1][1]


def test_a_tall_target_is_reached_by_straight_runs_from_two_short_boxes():
    nodes = (LayoutNode("a", 2, 1), LayoutNode("b", 2, 1), LayoutNode("c", 2, 3))
    lay = layered_layout(nodes, (("a", "c"), ("b", "c")), options=LayoutOptions(page=None))
    assert [rm.bends(r) for r in lay.routes.values()] == [0, 0]
    assert rm.shared_runs(lay) == [] and rm.port_gap_violations(lay) == []


def test_forward_edges_between_adjacent_layers_have_at_most_two_bends():
    for name in ("hub5", "fanin"):  # every edge joins adjacent layers
        lay = corpus.fixture_layout(name)
        assert max(rm.bends(r) for r in lay.routes.values()) <= 2, name
    assert max(rm.bends(r) for r in corpus.fixture_layout("lanes3").routes.values()) <= 4


def _hub(extra_group=False):
    """A hub with three children one box height apart, so the outer two can only be reached by an L."""
    nodes = (LayoutNode("h", 2, 1), *(LayoutNode(f"t{i}", 2, 1) for i in range(3)))
    if extra_group:
        nodes += (LayoutNode("x", 2, 1, None, "g"),)  # a group the edges do not belong to, so the group checks run
    return nodes, tuple(("h", f"t{i}") for i in range(3))


def _veto(monkeypatch, caller, when=lambda frame: True, times=1):
    """Make `_enters` report a hit `times` times when called from a function named `caller`, to force a fallback."""
    real = lo._enters
    left = [times]

    def fake(a, b, rect):
        frame = sys._getframe(1)
        for _ in range(4):
            if frame.f_code.co_name == caller:
                if left[0] and when(frame) and (caller != "runs_into_something" or a[0] == b[0] != 0):
                    left[0] -= 1
                    return True
                break
            frame = frame.f_back
        return real(a, b, rect)

    monkeypatch.setattr(lo, "_enters", fake)
    return left


def _is_l(lay, key):
    return rm.bends(lay.routes[key]) <= 1


def test_the_unforced_hub_takes_l_routes_for_its_outer_children():
    nodes, edges = _hub(True)
    lay = layered_layout(nodes, edges, groups=("g",), options=LayoutOptions(page=None))
    assert [rm.bends(lay.routes[("h", f"t{i}", 0)]) for i in range(3)] == [1, 0, 1]


def test_an_l_route_that_runs_into_something_falls_back_to_its_z_route(monkeypatch):
    from test_layout import _check_routes

    nodes, edges = _hub(True)
    left = _veto(monkeypatch, "runs_into_something")
    lay = layered_layout(nodes, edges, groups=("g",), options=LayoutOptions(page=None))
    assert left == [0]  # the net fired
    _check_routes(lay)
    assert [rm.bends(lay.routes[("h", f"t{i}", 0)]) for i in range(3)] == [2, 0, 1]


def test_an_l_route_whose_end_a_heading_moves_falls_back_to_its_z_route(monkeypatch):
    from test_layout import _check_routes

    nodes, edges = _hub(True)
    options = LayoutOptions(page=None, headings=(("g", 1.0, 0.25),))
    left = _veto(monkeypatch, "reattach")
    lay = layered_layout(nodes, edges, groups=("g",), options=options)
    assert left == [0]
    _check_routes(lay)
    assert rm.bends(lay.routes[("h", "t0", 0)]) >= 2


def _verifying(frame):
    """Whether the `l_side` call is the check of a decision already taken: the stem end has left `end_offset`."""
    return (frame.f_locals["n"], frame.f_locals["leaving"]) not in frame.f_locals["end_offset"]


def test_an_l_route_that_fails_its_check_once_is_retried_without_it(monkeypatch):
    from test_layout import _check_routes

    nodes, edges = _hub(True)
    left = _veto(monkeypatch, "l_side", _verifying)
    lay = layered_layout(nodes, edges, groups=("g",), options=LayoutOptions(page=None))
    assert left == [0]
    _check_routes(lay)
    assert [rm.bends(lay.routes[("h", f"t{i}", 0)]) for i in range(3)] == [2, 0, 1]


def test_l_routes_that_keep_failing_their_check_are_all_given_up(monkeypatch):
    from test_layout import _check_routes

    nodes, edges = _hub(True)
    _veto(monkeypatch, "l_side", _verifying, times=10_000)
    lay = layered_layout(nodes, edges, groups=("g",), options=LayoutOptions(page=None))
    _check_routes(lay)
    assert [rm.bends(lay.routes[("h", f"t{i}", 0)]) for i in range(3)] == [2, 0, 2]


@pytest.mark.parametrize("pitch", [0.1, 0.4])
def test_a_port_pitch_reaches_the_ports_of_the_top_and_bottom_sides(pitch):
    nodes = (LayoutNode("h", 3, 1), *(LayoutNode(f"t{i}", 1, 1) for i in range(6)))
    lay = layered_layout(nodes, tuple(("h", f"t{i}") for i in range(6)), options=LayoutOptions(port_pitch=pitch, page=None))
    sides: dict[float, list[float]] = {}
    for r in lay.routes.values():
        if r[0][0] == r[1][0]:
            sides.setdefault(r[0][1], []).append(r[0][0])
    assert len(sides) == 2 and all(len(xs) >= 2 for xs in sides.values())
    for xs in sides.values():
        assert round(max(xs) - min(xs), 2) == round(pitch * (len(xs) - 1), 2)


def test_a_graph_of_simple_edges_never_reaches_the_search():
    for name in (
        "hub5",
        "hub5_top_down",
        "fanin",
        "lanes3",
    ):  # chain25 is left out: its feedback edge is searched until Task 28
        assert corpus.fixture_layout(name).fallbacks == 0, name


def test_a_route_round_a_foreign_group_is_searched_and_counted():
    from test_layout import _group_detour_case

    assert _group_detour_case().fallbacks == 1


def test_a_jog_between_ends_on_one_line_is_offered_the_straight_run_first():
    jog = [(0.0, 1.0), (0.5, 1.0), (0.5, 1.2), (1.0, 1.2), (1.0, 1.0), (2.0, 1.0)]
    assert lo._candidates(jog) == [[(0.0, 1.0), (2.0, 1.0)]]


def test_a_corner_is_offered_only_when_it_keeps_the_way_the_ends_leave_and_arrive():
    assert lo._candidates([(0.0, 0.0), (0.4, 0.0), (0.4, 1.0), (1.0, 1.0)]) == []  # both ends head along the flow
    stepped = [(0.0, 0.0), (0.4, 0.0), (0.4, 1.0), (1.0, 1.0), (1.0, 2.0)]  # leaves along the flow, arrives across it
    assert lo._candidates(stepped) == [[(0.0, 0.0), (1.0, 0.0), (1.0, 2.0)]]


def test_the_candidates_cut_the_bends_of_random_pages_and_the_searches_they_save_are_counted(monkeypatch):
    from helpers.graphs import random_graph

    def laid(seed, n, m, lanes, groups):
        rows, edges, lane_ids, group_ids, parents = random_graph(seed, n, m, lanes, groups)
        nodes = tuple(LayoutNode(*row) for row in rows)
        return layered_layout(nodes, edges, lane_ids, group_ids, LayoutOptions(parents=parents))

    def bends(layout):
        return sum(rm.bends(route) for route in layout.routes.values())

    with_candidates = [laid(20, 30, 45, 0, 0), laid(21, 20, 30, 0, 3)]
    monkeypatch.setattr(lo, "_candidates", lambda path: [])
    without = [laid(20, 30, 45, 0, 0), laid(21, 20, 30, 0, 3)]
    assert bends(with_candidates[0]) < bends(without[0])
    assert with_candidates[1].fallbacks < without[1].fallbacks
