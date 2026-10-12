import math
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pytest
from helpers.route_metrics import crossings, layout_digest, shared_runs
from test_layout import _check, _check_routes

from vsdxkit import layout as lo
from vsdxkit.errors import GraphError
from vsdxkit.layout import LayoutNode, LayoutOptions, PageTarget, layered_layout

TWO = (LayoutNode("a", 2, 1), LayoutNode("b", 2, 1))


def test_the_default_options_carry_the_default_page_target():
    assert LayoutOptions().page == PageTarget(aspect=16 / 9, tolerance=0.25, wrap="snake", direction="auto")


@pytest.mark.parametrize(
    ("page", "name"),
    [
        (PageTarget(aspect=0.0), "aspect"),
        (PageTarget(aspect=float("nan")), "aspect"),
        (PageTarget(tolerance=-0.1), "tolerance"),
        (PageTarget(wrap="spiral"), "wrap"),
        (PageTarget(direction="sideways"), "direction"),
        ("16:9", "page"),
    ],
)
def test_a_page_target_that_is_not_valid_is_refused_by_name(page, name):
    with pytest.raises(GraphError, match=name):
        layered_layout(TWO, (("a", "b"),), options=LayoutOptions(page=page))


def test_none_turns_the_target_off():
    assert layered_layout(TWO, (("a", "b"),), options=LayoutOptions(page=None)).rows == ()


def test_the_partition_minimises_the_widest_row_and_breaks_ties_early():
    assert lo._partition([4, 1, 1, 4], 2) == (0, 2)
    assert lo._partition([1, 1, 1, 1], 2) == (0, 2)
    assert lo._partition([3, 3, 3], 2) == (0, 1)  # (3 | 6) and (6 | 3) tie at 6; the earlier cut wins


def test_the_row_count_is_clamped_to_the_layer_count():
    assert lo._partition([2, 2], 5) == (0, 1)
    assert lo._partition([2], 3) == (0,)


def test_a_forbidden_cut_is_never_taken():
    assert lo._partition([1, 1, 1, 1], 2, forbidden=frozenset({2})) in {(0, 1), (0, 3)}
    assert lo._partition([1, 1, 1], 3, forbidden=frozenset({1, 2})) == (0,)


def test_the_row_choice_lands_a_long_chain_in_the_band():
    widths = [3.2] * 25
    heights = [1.0] * 25
    starts = lo._choose_starts(widths, heights, 0.5, lo.PageTarget(), frozenset())
    w, h = lo._estimate(widths, heights, starts, 0.5)
    assert 1.33 <= w / h <= 2.22 and len(starts) > 1


def test_a_page_already_in_the_band_is_not_wrapped():
    assert lo._choose_starts([1.0, 0.8], [1.0, 1.0], 0.5, lo.PageTarget(), frozenset()) == (0,)


def test_wrap_none_never_wraps():
    assert lo._choose_starts([3.2] * 25, [1.0] * 25, 0.5, lo.PageTarget(wrap="none"), frozenset()) == (0,)


def test_the_chosen_row_count_is_the_minimiser_over_every_row_count():
    widths = [2.0, 3.5, 1.0, 4.0, 2.5, 3.0, 1.5, 2.0, 3.2, 2.8]
    heights = [1.0, 2.0, 1.0, 1.5, 1.0, 1.0, 2.5, 1.0, 1.0, 1.2]
    target = lo.PageTarget()

    def distance(starts):
        w, h = lo._estimate(widths, heights, starts, 0.5)
        return abs(math.log(lo.snap(w / h) / target.aspect))

    chosen = lo._choose_starts(widths, heights, 0.5, target, frozenset())
    every = [lo._partition(widths, r) for r in range(1, len(widths) + 1)]
    assert distance(chosen) == min(distance(s) for s in every)


def test_a_very_tall_narrow_estimate_does_not_break_the_log():
    assert lo._choose_starts([0.1] * 3, [10.0] * 3, 0.5, lo.PageTarget(), frozenset())


def test_the_partition_and_the_estimate_agree_on_the_widest_row():
    widths = [0.1, 0.2, 0.7, 0.3, 0.1, 0.6] * 3
    starts = lo._partition(widths, 4)
    ends = [*starts[1:], len(widths)]
    widest = max(lo.snap(math.fsum(widths[a:b])) for a, b in zip(starts, ends, strict=True))
    assert lo._estimate(widths, [1.0] * len(widths), starts, 0.5)[0] == widest


def test_snake_columns_anchor_each_row_under_the_end_of_the_one_above():
    left, mirrored = lo._columns([1] * 6, [0.5] * 6, (0, 3), True, 0.0)
    assert left == [0.0, 1.5, 3.0, 3.0, 1.5, 0.0]
    assert mirrored == [False, False, False, True, True, True]


def test_plain_rows_all_start_at_the_margin():
    left, mirrored = lo._columns([1] * 4, [0.5] * 4, (0, 2), False, 0.5)
    assert left == [0.5, 2.0, 0.5, 2.0] and not any(mirrored)


def test_a_longer_odd_row_shifts_the_drawing_onto_the_page():
    left, _ = lo._columns([1, 1, 1, 1, 1], [0.5] * 5, (0, 1), True, 0.5)
    assert min(left) == 0.5


def _chain(n):
    nodes = tuple(LayoutNode(f"s{i}", 2.4, 1.0) for i in range(n))
    return nodes, tuple((f"s{i}", f"s{i + 1}") for i in range(n - 1))


def test_a_long_chain_wraps_into_the_band_and_keeps_its_order():
    nodes, edges = _chain(25)
    lay = layered_layout(nodes, edges)
    assert len(lay.rows) > 1
    assert 1.33 <= lay.width / lay.height <= 2.22
    assert [n for row in lay.rows for n in row] == [f"s{i}" for i in range(25)]
    assert set(lay.routes) == {(a, b, 0) for a, b in edges}


def test_a_snake_row_runs_against_the_flow():
    nodes, edges = _chain(25)
    lay = layered_layout(nodes, edges)
    first, second = lay.rows[0], lay.rows[1]
    assert lay.nodes[first[0]].x < lay.nodes[first[-1]].x
    assert lay.nodes[second[0]].x > lay.nodes[second[-1]].x


def test_wrap_rows_runs_every_row_with_the_flow():
    nodes, edges = _chain(25)
    lay = layered_layout(nodes, edges, options=LayoutOptions(page=PageTarget(wrap="rows")))
    assert all(lay.nodes[r[0]].x < lay.nodes[r[-1]].x for r in lay.rows)


def test_an_empty_page_and_a_single_node_do_not_wrap():
    assert layered_layout((), ()).rows == ()
    assert len(layered_layout((LayoutNode("a", 2, 1),), ()).rows) <= 1


def test_a_group_is_never_split_across_a_fold():
    nodes, edges = _chain(25)
    grouped = tuple(LayoutNode(n.id, n.width, n.height, None, "g" if 8 <= i <= 16 else None) for i, n in enumerate(nodes))
    lay = layered_layout(grouped, edges, groups=("g",))
    rows_of_group = {i for i, row in enumerate(lay.rows) for n in row if grouped[int(n[1:])].group == "g"}
    assert len(rows_of_group) == 1


def test_a_page_that_already_fits_is_laid_out_as_before():
    nodes = tuple(LayoutNode(f"s{i}", 1.0, 3.0) for i in range(3))  # an aspect already inside the band
    edges = (("s0", "s1"), ("s1", "s2"))
    wrapped = layered_layout(nodes, edges)
    assert wrapped.rows == ()
    plain = layered_layout(nodes, edges, options=LayoutOptions(page=None))
    assert layout_digest({"x": wrapped}) == layout_digest({"x": plain})


def test_page_none_reproduces_the_0_10_routes():
    """Expires when Phase 2 changes ports: delete it in that phase's first task."""
    import layout_corpus as corpus

    off = LayoutOptions(page=None)
    layouts = {s: corpus.fixture_layout(s, off) for s in corpus.FIXTURES}
    layouts.update({f"rand-{k}": corpus.random_layout(k, 40, 60, off) for k in range(5)})
    want = (Path(__file__).parent / "fixtures" / "routes_unwrapped.sha256").read_text(encoding="utf-8").strip()
    assert layout_digest(layouts) == want


def test_lanes_never_wrap_and_a_top_down_flow_is_not_cut():
    nodes, edges = _chain(25)
    laned = tuple(LayoutNode(n.id, n.width, n.height, "l") for n in nodes)
    assert layered_layout(laned, edges, ("l",)).rows == ()
    assert (
        layered_layout(nodes, edges, options=LayoutOptions(direction="top_down", page=PageTarget(direction="top_down"))).rows
        == ()
    )


def _straight_down(route):
    return len({round(x, 2) for x, _y in route}) == 1


def test_the_edge_that_crosses_a_fold_is_a_short_join():
    nodes, edges = _chain(25)
    lay = layered_layout(nodes, edges)
    fold = [(row[-1], nxt[0]) for row, nxt in pairwise(lay.rows)]
    assert fold
    for a, b in fold:
        route = lay.routes[(a, b, 0)]
        assert _straight_down(route) and len(route) == 2


def test_an_edge_that_spans_a_fold_is_routed_clear_of_every_node():
    nodes, edges = _chain(25)
    skip = (*edges, ("s10", "s16"), ("s22", "s2"))
    lay = layered_layout(nodes, skip)
    assert len(lay.routes) == len(skip)
    _check(lay, nodes, ())
    _check_routes(lay)


def test_disconnected_chains_wrap_and_every_edge_has_a_route():
    a, ea = _chain(14)
    b = tuple(LayoutNode(f"t{i}", 2.4, 1.0) for i in range(14))
    eb = tuple((f"t{i}", f"t{i + 1}") for i in range(13))
    lay = layered_layout((*a, *b), (*ea, *eb))
    assert len(lay.routes) == 26 and len(lay.nodes) == 28
    _check(lay, (*a, *b), ())
    _check_routes(lay)


def test_two_edges_that_fold_together_do_not_share_a_run():
    nodes = (*(LayoutNode(f"s{i}", 2.4, 1.0) for i in range(24)), LayoutNode("x", 2.4, 1.0))
    edges = (*((f"s{i}", f"s{i + 1}") for i in range(23)), ("s11", "x"), ("s11", "s12"))
    lay = layered_layout(nodes, edges)
    assert shared_runs(lay) == [] and crossings(lay) == 0


def test_fold_routes_and_a_shifted_snake_stay_on_the_page_and_out_of_every_node():
    nodes, edges = _chain(25)
    skip = (*edges, ("s10", "s16"), ("s22", "s2"), ("s5", "s20"))
    for page in (PageTarget(), PageTarget(wrap="rows")):
        lay = layered_layout(nodes, skip, options=LayoutOptions(page=page))
        _check(lay, nodes, ())
        for (source, target, _n), route in lay.routes.items():
            for x, y in route:
                assert 0 <= x <= lay.width and 0 <= y <= lay.height
            for p, q in pairwise(route):
                for node_id, box in lay.nodes.items():
                    if node_id not in (source, target):
                        lx, hx = sorted((p[0], q[0]))
                        ly, hy = sorted((p[1], q[1]))
                        inside_x = hx > box.x - box.width / 2 and lx < box.x + box.width / 2
                        inside_y = hy > box.y - box.height / 2 and ly < box.y + box.height / 2
                        assert not (inside_x and inside_y), f"{source}->{target} enters {node_id}"


def test_several_folds_at_one_boundary_keep_their_levels_apart():
    nodes, edges = _chain(25)
    edges = (*edges, ("s0", "s5"), ("s2", "s5"), ("s3", "s5"))  # four edges fold into s5 from different start columns
    lay = layered_layout(nodes, edges, options=LayoutOptions(page=PageTarget(wrap="rows")))
    assert lay.rows[0][-1] == "s4"
    pieces = {}  # the last long run of each route, which is its level in the corridor, with the two drops that join it
    for key, route in lay.routes.items():
        if key[1] == "s5":
            long_runs = [i for i, (p, q) in enumerate(pairwise(route)) if p[1] == q[1] and abs(p[0] - q[0]) > lay.width / 2]
            i = long_runs[-1]
            pieces.update({(key, j): (route[j], route[j + 1]) for j in (i - 1, i, i + 1)})
    assert len(pieces) == 12
    group = SimpleNamespace(routes=pieces)
    assert shared_runs(group) == [] and crossings(group) == 0


def test_a_node_with_a_loop_that_receives_a_fold_keeps_the_loop_and_the_fold_on_different_points():
    nodes, edges = _chain(25)
    head = layered_layout(nodes, edges).rows[1][0]
    looped = (*edges, (head, head))
    lay = layered_layout(nodes, looped)
    assert head in lay.rows[1]
    _check(lay, nodes, ())
    _check_routes(lay)
    fold = next(r for (a, b, _n), r in lay.routes.items() if b == head and a != head)
    loop_points = {p for (a, b, _n), r in lay.routes.items() if a == b == head for p in (r[0], r[-1])}
    assert fold[-1] not in loop_points


def test_a_blocked_fold_route_falls_back_to_the_search_and_the_page_still_lays_out():
    """A tight grouped page whose fold route runs into a foreign group: without the fallback the edge cannot be routed."""
    from test_layout import random_graph

    rows, edges, lane_ids, group_ids, parents = random_graph(17, 9, 14, 0, 3)
    edges = (*edges, ("n2", "n4"), ("n2", "n4"), ("n2", "n4"), ("n1", "n3"), ("n1", "n3"))
    nodes = tuple(LayoutNode(*row) for row in rows)
    tight = LayoutOptions(
        parents=parents,
        node_gap=0.0,
        layer_gap=0.2,
        margin=0.0,
        group_padding=0.05,
        page=PageTarget(direction="left_to_right"),
    )
    lay = layered_layout(nodes, edges, lane_ids, group_ids, tight)
    assert len(lay.rows) > 1
    _check(lay, nodes, parents)
    _check_routes(lay, clear_of_borders=False)


def _miss(lay):
    return abs(math.log(lay.width / lay.height / (16 / 9)))


def _hub(n):
    kids = tuple(LayoutNode(f"c{i}", 2.4, 1.0) for i in range(n))
    return (LayoutNode("hub", 2.4, 1.0), *kids), tuple(("hub", k.id) for k in kids)


def test_a_wide_hub_top_down_becomes_a_left_to_right_page():
    nodes, edges = _hub(10)
    down = layered_layout(nodes, edges, options=LayoutOptions(direction="top_down", page=PageTarget(direction="top_down")))
    auto = layered_layout(nodes, edges, options=LayoutOptions(direction="top_down"))
    assert _miss(auto) < _miss(down)


def test_a_pinned_direction_is_not_second_guessed():
    nodes, edges = _chain(3)
    lay = layered_layout(nodes, edges, options=LayoutOptions(page=PageTarget(direction="top_down")))
    assert lay.height > lay.width


def test_a_tie_or_a_page_in_the_band_keeps_the_configured_direction():
    nodes = (LayoutNode("a", 2, 2), LayoutNode("b", 2, 2))
    ltr = layered_layout(nodes, (("a", "b"),))
    pinned = layered_layout(nodes, (("a", "b"),), options=LayoutOptions(page=PageTarget(direction="left_to_right")))
    assert (ltr.width, ltr.height) == (pinned.width, pinned.height)
    down = layered_layout(
        nodes, (("a", "b"),), options=LayoutOptions(direction="top_down", page=PageTarget(direction="top_down"))
    )
    assert down.height > down.width


def test_a_large_page_keeps_the_configured_direction():
    nodes, edges = _hub(lo._AUTO_DIRECTION_NODES)
    auto = layered_layout(nodes, edges, options=LayoutOptions(direction="top_down"))
    pinned = layered_layout(nodes, edges, options=LayoutOptions(direction="top_down", page=PageTarget(direction="top_down")))
    assert (auto.width, auto.height) == (pinned.width, pinned.height)


def test_lanes_ignore_the_page_target():
    nodes = (LayoutNode("a", 2, 1, "L0"), LayoutNode("b", 2, 1, "L1"))
    lay = layered_layout(
        nodes, (("a", "b"),), lanes=("L0", "L1"), options=LayoutOptions(page=PageTarget(direction="top_down"))
    )
    assert lay.rows == () and set(lay.lanes) == {"L0", "L1"}
