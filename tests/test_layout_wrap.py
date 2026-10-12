import math

import pytest

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
