"""The Visio formulas this library evaluates itself, for a cell it writes without a value.

Visio recalculates a formula on open; this library never opens the file it
writes, so a cell such as `TxtPinX` that Visio would compute needs a value of
its own or the shape renders wrong until Visio next touches it.
`func_map`/`calc_value` cover the handful of formula texts the library itself
writes; a formula from elsewhere in the package is left unevaluated.
"""

from __future__ import annotations

import math
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
        """The x of a 1-D shape's begin point, for the formulas that place a connector's text or centre."""
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


def _f(value: float | str | None) -> float:
    """Coerce an optional cell value to float (None -> 0.0)."""
    return float(value) if value is not None else 0.0


def width_x_1(shape: ShapeMetrics) -> float | None:
    """`shape`'s ``Width*1`` formula: its own width."""
    return shape.width


def width_x_0(shape: ShapeMetrics) -> int:
    """`shape`'s ``Width*0`` formula: always 0."""
    return 0


def middle_x(shape: ShapeMetrics) -> float:
    """`shape`'s ``(BeginX+EndX)/2`` (or its ``GUARD``ed form): the x midway between its 1-D ends."""
    # (BeginX+EndX)/2
    return (_f(shape.begin_x) + _f(shape.end_x)) / 2


def middle_y(shape: ShapeMetrics) -> float:
    """`shape`'s ``(BeginY+EndY)/2`` (or its ``GUARD``ed form): the y midway between its 1-D ends."""
    # (BeginY+EndY)/2
    return (_f(shape.begin_y) + _f(shape.end_y)) / 2


def center_x(shape: ShapeMetrics) -> float:
    """`shape`'s ``Width*0.5`` (or its ``GUARD``ed form): half its width."""
    # Width*0.5
    return _f(shape.width) * 0.5


def center_y(shape: ShapeMetrics) -> float:
    """`shape`'s ``Height*0.5`` (or its ``GUARD``ed form): half its height."""
    # Height*0.5
    return _f(shape.height) * 0.5


def diag_width(shape: ShapeMetrics) -> float:
    """`shape`'s ``SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)`` formula: the length between its 1-D ends."""
    # SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)
    width = _f(shape.end_x) - _f(shape.begin_x)
    height = _f(shape.end_y) - _f(shape.begin_y)
    return math.sqrt(width**2 + height**2)


def angle(shape: ShapeMetrics) -> float:
    """`shape`'s ``ATAN2(EndY-BeginY,EndX-BeginX)`` formula: its 1-D ends' angle, in radians."""
    # ATAN2(EndY-BeginY,EndX-BeginX). Both Visio's ATAN2 and math.atan2 take the
    # ordinate first, so the rise goes in front of the run.
    w = _f(shape.end_x) - _f(shape.begin_x)
    h = _f(shape.end_y) - _f(shape.begin_y)
    return math.atan2(h, w)


def width(shape: ShapeMetrics) -> float:
    """`shape`'s ``GUARD(EndX-BeginX)`` formula: the x span between its 1-D ends."""
    return _f(shape.end_x) - _f(shape.begin_x)


def height(shape: ShapeMetrics) -> float:
    """`shape`'s ``GUARD(EndY-BeginY)`` formula: the y span between its 1-D ends."""
    return _f(shape.end_y) - _f(shape.begin_y)


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


def calc_value(shape: ShapeMetrics, func_text: str) -> float | str | None:
    """`func_text` evaluated for `shape`, or ``None`` for a formula not in `func_map`."""
    f = func_map.get(func_text)
    if f is None:
        _logger.debug("calc_value(func_text='%s') no method found", func_text)
        return None
    return f(shape)
