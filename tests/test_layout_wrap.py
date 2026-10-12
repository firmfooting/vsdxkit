import math
from pathlib import Path

import pytest
from helpers.route_metrics import layout_digest

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
    assert layered_layout(nodes, edges, options=LayoutOptions(direction="top_down")).rows == ()
