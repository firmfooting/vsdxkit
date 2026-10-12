import pytest

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
