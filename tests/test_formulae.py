"""The ShapeSheet formulas this library evaluates itself.

Each entry in `func_map` claims to compute the Visio formula it is keyed by. A
test that only checks the value is self-consistent cannot tell whether it
computes the *right* formula, so the cases below are chosen to distinguish the
implementation from its plausible neighbours.
"""

import math

import pytest

from vsdxkit import namespace
from vsdxkit._formulae import calc_value

NS = namespace[1:-1]

ATAN2 = "ATAN2(EndY-BeginY,EndX-BeginX)"


class _Connector:
    """The smallest thing `calc_value` needs: a shape with begin and end cells."""

    def __init__(self, begin: tuple[float, float], end: tuple[float, float]) -> None:
        self.begin_x, self.begin_y = begin
        self.end_x, self.end_y = end


@pytest.mark.parametrize(
    ("begin", "end", "expected", "heading"),
    [
        # Axis-aligned cases only. A diagonal cannot tell atan2(dy, dx) from
        # atan2(dx, dy): both give pi/4 for a 45-degree line, which is how the
        # arguments came to be the wrong way round unnoticed.
        ((0.0, 0.0), (1.0, 0.0), 0.0, "due east"),
        ((0.0, 0.0), (0.0, 1.0), math.pi / 2, "due north"),
        ((0.0, 0.0), (-1.0, 0.0), math.pi, "due west"),
        ((0.0, 0.0), (0.0, -1.0), -math.pi / 2, "due south"),
    ],
)
def test_angle_measures_anticlockwise_from_east(begin, end, expected, heading):
    """`ATAN2(EndY-BeginY, EndX-BeginX)` takes the ordinate first.

    Visio's ATAN2 and Python's `math.atan2` agree on argument order, so the
    formula the key names maps directly onto the call.
    """
    angle = calc_value(_Connector(begin, end), ATAN2)

    assert angle == pytest.approx(expected), f"a connector running {heading}"


def test_a_diagonal_cannot_pin_the_argument_order():
    """Stated so the cases above are not later 'simplified' into this one.

    On a 45-degree line the rise equals the run, so both orderings give the same
    answer. Testing only the easy case is how the arguments came to be the wrong
    way round and stayed that way.
    """
    rise, run = 1.0, 1.0
    diagonal = calc_value(_Connector((0.0, 0.0), (run, rise)), ATAN2)

    assert diagonal == pytest.approx(math.pi / 4)
    assert math.atan2(rise, run) == math.atan2(run, rise), "this case is blind to the swap"


def test_every_formula_in_the_table_is_callable():
    """The table is a lookup from Visio formula text to an implementation."""
    from vsdxkit._formulae import func_map

    assert func_map, "the formula table is empty"
    assert all(callable(f) for f in func_map.values())


class _Metrics:
    """A shape whose every metric is known, bar the ones named `None`."""

    def __init__(self, **missing: None) -> None:
        self.width: float | None = 2.0
        self.height: float | None = 1.0
        self.begin_x: float | None = 0.0
        self.begin_y: float | None = 0.0
        self.end_x: float | None = 3.0
        self.end_y: float | None = 4.0
        for name in missing:
            setattr(self, name, None)


_ENDS = ("begin_x", "begin_y", "end_x", "end_y")

# Each formula, and every metric it reads. `Width*0` reads nothing.
_READS = {
    "Width*1": ("width",),
    "Width*0.5": ("width",),
    "GUARD(Width*0.5)": ("width",),
    "Height*0.5": ("height",),
    "GUARD(Height*0.5)": ("height",),
    "(BeginX+EndX)/2": ("begin_x", "end_x"),
    "GUARD((BeginX+EndX)/2)": ("begin_x", "end_x"),
    "(BeginY+EndY)/2": ("begin_y", "end_y"),
    "GUARD((BeginY+EndY)/2)": ("begin_y", "end_y"),
    "SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)": _ENDS,
    ATAN2: _ENDS,
    "GUARD(EndX-BeginX)": ("begin_x", "end_x"),
    "GUARD(EndY-BeginY)": ("begin_y", "end_y"),
}


def test_the_reads_table_covers_every_formula():
    """A formula added to `func_map` is added here too, or the test below skips it."""
    from vsdxkit._formulae import func_map

    assert set(_READS) | {"Width*0"} == set(func_map)


@pytest.mark.parametrize(
    ("formula", "metric"),
    [(formula, metric) for formula, reads in _READS.items() for metric in reads],
)
def test_a_formula_with_an_unknown_input_has_no_value(formula, metric):
    """A metric the shape does not have makes the formula unevaluable, not zero.

    `None` tells `Shape._refresh_formula_values` to keep the value the cell
    had. A 0.0 would overwrite it with a number no shape reported: text pinned
    at the corner, or a connector of no length.
    """
    known = calc_value(_Metrics(), formula)
    unknown = calc_value(_Metrics(**{metric: None}), formula)

    assert known is not None, "the fully known shape must evaluate, or this proves nothing"
    assert unknown is None, f"{formula} gave {unknown!r} without {metric}"


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("Width*0.499973064698594", 2.0 * 0.499973064698594),
        ("Height*0.25", 0.25),
        ("Width*2", 4.0),
        ("Width*-0.5", -1.0),
        ("Height*+1.5", 1.5),
        ("Width*.5", 1.0),
        ("Width*3.", 6.0),
    ],
)
def test_a_width_or_height_times_a_number_is_evaluated(formula, expected):
    """Visio writes a local pin as a fraction of the size, such as test5_master shape 5's `Width*0.499973064698594`."""
    assert calc_value(_Metrics(), formula) == pytest.approx(expected)


@pytest.mark.parametrize(
    "formula",
    [
        "Width*0.5+1",
        "Width * 0.5",
        "Width*",
        "Width*1e3",
        "Width*0.5DL",
        "Width*--1",
        "Width*Height",
        "PinX*0.5",
        "0.5*Width",
        "GUARD(Width*0.3)",
        "width*0.3",
    ],
)
def test_the_fallback_refuses_anything_but_a_width_or_height_times_a_decimal(formula):
    assert calc_value(_Metrics(), formula) is None


@pytest.mark.parametrize(("formula", "metric"), [("Width*0.3", "width"), ("Height*0.3", "height")])
def test_the_fallback_has_no_value_without_its_metric(formula, metric):
    assert calc_value(_Metrics(), formula) is not None
    assert calc_value(_Metrics(**{metric: None}), formula) is None
