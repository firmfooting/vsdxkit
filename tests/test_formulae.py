"""The ShapeSheet formulas this library evaluates itself.

Each entry in `func_map` claims to compute the Visio formula it is keyed by. A
test that only checks the value is self-consistent cannot tell whether it
computes the *right* formula, so the cases below are chosen to distinguish the
implementation from its plausible neighbours.
"""

import math

import pytest

import vsdx
from vsdx import namespace

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
    angle = vsdx.calc_value(_Connector(begin, end), ATAN2)

    assert angle == pytest.approx(expected), f"a connector running {heading}"


def test_a_diagonal_cannot_pin_the_argument_order():
    """Stated so the cases above are not later 'simplified' into this one.

    On a 45-degree line the rise equals the run, so both orderings give the same
    answer. Testing only the easy case is how the arguments came to be the wrong
    way round and stayed that way.
    """
    rise, run = 1.0, 1.0
    diagonal = vsdx.calc_value(_Connector((0.0, 0.0), (run, rise)), ATAN2)

    assert diagonal == pytest.approx(math.pi / 4)
    assert math.atan2(rise, run) == math.atan2(run, rise), "this case is blind to the swap"


def test_every_formula_in_the_table_is_callable():
    """The table is a lookup from Visio formula text to an implementation."""
    from vsdx.formulae import func_map

    assert func_map, "the formula table is empty"
    assert all(callable(f) for f in func_map.values())
