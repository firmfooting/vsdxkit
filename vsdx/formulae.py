import math

from .logging_support import get_logger
from .shapes import Shape

logger = get_logger(__name__)


def _f(value: float | str | None) -> float:
    """Coerce an optional cell value to float (None -> 0.0)."""
    return float(value) if value is not None else 0.0


def width_x_1(shape: Shape) -> float | str | None:
    return shape.width


def width_x_0(shape: Shape) -> int:
    return 0


def middle_x(shape: Shape) -> float:
    # (BeginX+EndX)/2
    return (_f(shape.begin_x) + _f(shape.end_x)) / 2


def middle_y(shape: Shape) -> float:
    # (BeginY+EndY)/2
    return (_f(shape.begin_y) + _f(shape.end_y)) / 2


def center_x(shape: Shape) -> float:
    # Width*0.5
    return _f(shape.width) * 0.5


def center_y(shape: Shape) -> float:
    # Height*0.5
    return _f(shape.height) * 0.5


def diag_width(shape: Shape) -> float:
    # SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)
    width = _f(shape.end_x) - _f(shape.begin_x)
    height = _f(shape.end_y) - _f(shape.begin_y)
    return math.sqrt(width**2 + height**2)


def angle(shape: Shape) -> float:
    # ATAN2(EndY-BeginY,EndX-BeginX). Both Visio's ATAN2 and math.atan2 take the
    # ordinate first, so the rise goes in front of the run.
    w = _f(shape.end_x) - _f(shape.begin_x)
    h = _f(shape.end_y) - _f(shape.begin_y)
    return math.atan2(h, w)


def width(shape: Shape) -> float:
    return _f(shape.end_x) - _f(shape.begin_x)


def height(shape: Shape) -> float:
    return _f(shape.end_y) - _f(shape.begin_y)


# map func text to functions
func_map = {
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


def calc_value(shape: Shape, func_text: str) -> float | str | None:
    f = func_map.get(func_text)
    if f:
        return f(shape=shape)
    elif shape.page.vis.debug:
        # show any non-matching formulae
        logger.debug("calc_value(func_text='%s') no method found", func_text)
