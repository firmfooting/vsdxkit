"""The Visio formulas this library evaluates itself, for a cell it writes without a value.

Visio recalculates a formula on open; this library never opens the file it
writes, so a cell such as `TxtPinX` that Visio would compute needs a value of
its own or the shape renders wrong until Visio next touches it.
`func_map`/`calc_value` cover the handful of formula texts the library itself
writes, and ``Width`` or ``Height`` times a number, as Visio writes a local
pin; any other formula from elsewhere in the package is left unevaluated.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from logging import Logger
from typing import Protocol

from vsdxkit._logging_support import get_logger

_logger: Logger = get_logger(__name__)
"""This module's logger, under the `vsdxkit` hierarchy the library never configures a handler for."""


class ShapeMetrics(Protocol):
    """What a formula reads from a shape: its size, and the end points of a 1-D shape."""

    @property
    def width(self) -> float | None:
        """The shape's width, for `Width*1` and `Width*0.5`."""
        ...

    @property
    def height(self) -> float | None:
        """The shape's height, for `Height*0.5`."""
        ...

    @property
    def begin_x(self) -> float | None:
        """The x of a 1-D shape's begin point, for the formulas that derive its pin, width, height and angle from its ends."""
        ...

    @property
    def begin_y(self) -> float | None:
        """The y of a 1-D shape's begin point. Read alongside `begin_x`."""
        ...

    @property
    def end_x(self) -> float | None:
        """The x of a 1-D shape's end point. Read alongside `begin_x`."""
        ...

    @property
    def end_y(self) -> float | None:
        """The y of a 1-D shape's end point. Read alongside `begin_x`."""
        ...


# Each formula below gives None when a metric it reads is None, as Visio could
# not evaluate it either: `calc_value`'s caller then keeps the value the cell
# had, where a stand-in 0 would overwrite it with a number no shape reported.


def width_x_1(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``Width*1`` formula: its own width."""
    return shape.width


def width_x_0(shape: ShapeMetrics) -> int:
    """`shape`'s ``Width*0`` formula: always 0."""
    return 0


def middle_x(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``(BeginX+EndX)/2`` (or its ``GUARD``ed form): the x midway between its 1-D ends."""
    begin_x, end_x = shape.begin_x, shape.end_x
    if begin_x is None or end_x is None:
        return None
    return (begin_x + end_x) / 2


def middle_y(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``(BeginY+EndY)/2`` (or its ``GUARD``ed form): the y midway between its 1-D ends."""
    begin_y, end_y = shape.begin_y, shape.end_y
    if begin_y is None or end_y is None:
        return None
    return (begin_y + end_y) / 2


def center_x(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``Width*0.5`` (or its ``GUARD``ed form): half its width."""
    shape_width = shape.width
    return None if shape_width is None else shape_width * 0.5


def center_y(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``Height*0.5`` (or its ``GUARD``ed form): half its height."""
    shape_height = shape.height
    return None if shape_height is None else shape_height * 0.5


def width(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``GUARD(EndX-BeginX)`` formula: the x span between its 1-D ends."""
    begin_x, end_x = shape.begin_x, shape.end_x
    if begin_x is None or end_x is None:
        return None
    return end_x - begin_x


def height(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``GUARD(EndY-BeginY)`` formula: the y span between its 1-D ends."""
    begin_y, end_y = shape.begin_y, shape.end_y
    if begin_y is None or end_y is None:
        return None
    return end_y - begin_y


def diag_width(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)`` formula: the length between its 1-D ends."""
    run, rise = width(shape), height(shape)
    if run is None or rise is None:
        return None
    return math.sqrt(run**2 + rise**2)


def angle(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``ATAN2(EndY-BeginY,EndX-BeginX)`` formula: its 1-D ends' angle, in radians."""
    run, rise = width(shape), height(shape)
    if run is None or rise is None:
        return None
    # Both Visio's ATAN2 and math.atan2 take the ordinate first, so the rise
    # goes in front of the run.
    return math.atan2(rise, run)


# map func text to functions
func_map: dict[str, Callable[[ShapeMetrics], float | None]] = {
    "Width*1": width_x_1,
    "Width*0": width_x_0,
    "(BeginX+EndX)/2": middle_x,
    "(BeginY+EndY)/2": middle_y,
    "Width*0.5": center_x,
    "Height*0.5": center_y,
    "SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)": diag_width,
    "ATAN2(EndY-BeginY,EndX-BeginX)": angle,
    "GUARD((BeginX+EndX)/2)": middle_x,
    "GUARD((BeginY+EndY)/2)": middle_y,
    "GUARD(Width*0.5)": center_x,
    "GUARD(Height*0.5)": center_y,
    "GUARD(EndX-BeginX)": width,
    "GUARD(EndY-BeginY)": height,
}
"""Every formula text `calc_value` recognises, to the function that evaluates it."""


_SIZE_TIMES_NUMBER = re.compile(r"(Width|Height)\*([+-]?(?:\d+\.?\d*|\.\d+))")
"""``Width*<number>`` or ``Height*<number>``, the number a decimal literal, optionally signed: how Visio writes a local pin as a fraction of the size."""


def calc_value(shape: ShapeMetrics, func_text: str) -> float | None:
    """`func_text` evaluated for `shape`, or ``None`` for a formula it does not know or one reading a metric `shape` lacks.

    It knows the formulas in `func_map` and, as a fallback rather than a
    parser, ``Width`` or ``Height`` times a decimal number and nothing else:
    Visio writes a local pin that way, as test5_master's shape 5 has
    ``LocPinX`` ``Width*0.499973064698594``, which no fixed entry can name.
    """
    f = func_map.get(func_text)
    if f is not None:
        return f(shape)
    match = _SIZE_TIMES_NUMBER.fullmatch(func_text)
    if match is None:
        _logger.debug("calc_value(func_text='%s') no method found", func_text)
        return None
    metric = shape.width if match.group(1) == "Width" else shape.height
    return None if metric is None else metric * float(match.group(2))
