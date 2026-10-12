"""The writes the diagram builder needs that the page API does not offer: Shape Data rows, outlines and open paths."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from itertools import pairwise
from xml.etree.ElementTree import Element

from vsdxkit import namespace
from vsdxkit.layout import GRID, snap
from vsdxkit.pages import Page
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.shapes import Shape

KINDS: dict[str, tuple[ShapeKind, float, float]] = {
    "start": (ShapeKind.START_END, 2.0, 0.8),
    "end": (ShapeKind.START_END, 2.0, 0.8),
    "process": (ShapeKind.PROCESS, 2.2, 0.9),
    "decision": (ShapeKind.DECISION, 2.6, 1.3),
    "data_store": (ShapeKind.DATABASE, 2.2, 0.9),
    "external": (ShapeKind.RECTANGLE, 2.2, 0.9),
    "document": (ShapeKind.RECTANGLE, 2.2, 1.0),
    "subprocess": (ShapeKind.RECTANGLE, 2.2, 0.9),
    "off_page": (ShapeKind.RECTANGLE, 1.6, 1.0),
}
"""Each node kind's bundled shape (the last four are redrawn or restyled) and its width and height in inches before a long label grows it."""

_DASHED = "2"
"""A LinePattern index. Learn gives 0 as none and 1 as solid and calls 2 to 23 assorted, so what 2 draws is for the Visio shots to show."""


def _cell(name: str, value: str) -> Element:
    """A ``Cell`` element with this name and value."""
    return Element(f"{namespace}Cell", {"N": name, "V": value})


def add_data_rows(shape: Shape, rows: Mapping[str, str], *, clear: bool = False) -> None:
    """Write each entry of `rows` as a string Shape Data row on `shape`, in the order given, replacing a row of the same name.

    With `clear`, the rows the shape already has (the demonstration rows of a bundled donor) are removed first.

    The cells follow the order the bundled donors use. Type 0 is a string (Learn: Type Cell, Shape Data Section).
    """
    section = shape.xml.find(f'{namespace}Section[@N="Property"]')
    if section is None:
        section = Element(f"{namespace}Section", {"N": "Property"})
        leading = max((i + 1 for i, child in enumerate(shape.xml) if child.tag == f"{namespace}Cell"), default=0)
        shape.xml.insert(leading, section)
    if clear:
        for old in section.findall(f"{namespace}Row"):
            section.remove(old)
    for name, value in rows.items():
        for old in [r for r in section.findall(f"{namespace}Row") if r.attrib.get("N") == name]:
            section.remove(old)
        row = Element(f"{namespace}Row", {"N": name})
        for cell_name, cell_value in (
            ("Value", value),
            ("Prompt", ""),
            ("Label", name),
            ("Format", ""),
            ("SortKey", ""),
            ("Type", "0"),
            ("Invisible", "0"),
            ("Verify", "0"),
        ):
            row.append(_cell(cell_name, cell_value))
        section.append(row)


def set_geometry(shape: Shape, paths: Sequence[tuple[Sequence[tuple[float, float]], bool]], *, no_fill: bool = False) -> None:
    """Replace the shape's outline with `paths`, each a list of points in inches from the shape's bottom-left corner and whether it closes.

    A path is a MoveTo and then LineTo rows; a closed one ends with a LineTo back to its start. The rows are
    numbered from 1 across all the paths (Learn: MoveTo Row, LineTo Row, Geometry Section).
    """
    for old in shape.xml.findall(f'{namespace}Section[@N="Geometry"]'):
        shape.xml.remove(old)
    section = Element(f"{namespace}Section", {"N": "Geometry", "IX": "0"})
    for name, value in (
        ("NoFill", "1" if no_fill else "0"),
        ("NoLine", "0"),
        ("NoShow", "0"),
        ("NoSnap", "0"),
        ("NoQuickDrag", "0"),
    ):
        section.append(_cell(name, value))
    index = 1
    for points, closed in paths:
        route = [*points, points[0]] if closed and points[0] != points[-1] else list(points)
        for n, (x, y) in enumerate(route):
            row = Element(f"{namespace}Row", {"T": "MoveTo" if n == 0 else "LineTo", "IX": str(index)})
            row.append(_cell("X", repr(snap(x))))
            row.append(_cell("Y", repr(snap(y))))
            section.append(row)
            index += 1
    after = max(
        (i + 1 for i, child in enumerate(shape.xml) if child.tag in (f"{namespace}Cell", f"{namespace}Section")), default=0
    )
    shape.xml.insert(after, section)


def _outline(kind: str, w: float, h: float) -> list[tuple[list[tuple[float, float]], bool]] | None:
    """The outline a kind draws itself with at this size, or None for a kind that keeps its bundled shape's."""
    if kind == "document":
        return [
            (
                [
                    (0, h),
                    (w, h),
                    (w, 0.15 * h),
                    (0.75 * w, 0.05 * h),
                    (0.5 * w, 0.15 * h),
                    (0.25 * w, 0.25 * h),
                    (0, 0.15 * h),
                ],
                True,
            )
        ]
    if kind == "subprocess":
        return [
            ([(0, 0), (w, 0), (w, h), (0, h)], True),
            ([(0.1 * w, 0), (0.1 * w, h)], False),
            ([(0.9 * w, 0), (0.9 * w, h)], False),
        ]
    if kind == "off_page":
        return [([(0, h), (w, h), (w, 0.3 * h), (0.5 * w, 0), (0, 0.3 * h)], True)]
    return None


_ROUNDED = {"start": 0.25, "end": 0.25, "data_store": 0.5}
"""The Rounding cell each rounded-rectangle kind's donor carries, in inches: the corner radius."""

_TOL = 1e-9
"""Tolerance for a parallel edge and for a point that is on a line."""


def _polygon(kind: str, w: float, h: float) -> list[tuple[float, float]] | None:
    """The closed straight-sided outline of `kind` in its own coordinates, or None when it is not one."""
    if kind == "decision":  # the donor's POLYLINE(0, 0, 1,0.5, 0.5,0, 0,0.5) from (0.5, 1), in fractions of width and height
        return [(0.5 * w, h), (w, 0.5 * h), (0.5 * w, 0), (0, 0.5 * h)]
    outline = _outline(kind, w, h)
    return outline[0][0] if outline is not None and kind != "subprocess" else None


def _depth(
    kind: str, box: tuple[float, float, float, float], end: tuple[float, float], d: tuple[float, float]
) -> float | None:
    """How far in direction `d` (axis-aligned, into the node) the outline lies from `end`, a route's end on the box border.

    None leaves the end where it is: the kind fills its box, or the end is not on the node.
    """
    cx, cy, w, h = box
    k = 0 if d[0] else 1
    size, centre = (w, h), (cx, cy)
    if kind in _ROUNDED:
        r = min(
            _ROUNDED[kind], w / 2, h / 2
        )  # Visio draws a larger Rounding as half the shorter side (recorded: 2.2 x 0.9 in -> 0.45 in)
        reach = (centre[k] - d[k] * size[k] / 2 - end[k]) * d[
            k
        ]  # the run from the end to the drawn border, which the layout may have grown past
        if abs(reach) > 0.01:
            return None
        gap = abs(end[1 - k] - centre[1 - k]) - (size[1 - k] / 2 - r)  # how far into the corner arc the end lies
        if gap <= 0:
            return reach
        return reach + r - math.sqrt(r * r - gap * gap) if gap <= r else None
    polygon = _polygon(kind, w, h)
    if polygon is None:
        return None
    local = (end[0] - (cx - w / 2), end[1] - (cy - h / 2))
    best = None
    for a, b in pairwise([*polygon, polygon[0]]):
        e = (b[0] - a[0], b[1] - a[1])
        denom = d[0] * e[1] - d[1] * e[0]
        if abs(denom) < _TOL:
            continue  # the ray runs along this edge
        t = ((a[0] - local[0]) * e[1] - (a[1] - local[1]) * e[0]) / denom
        u = ((a[0] - local[0]) * d[1] - (a[1] - local[1]) * d[0]) / denom
        if -0.005 <= t <= size[k] + _TOL and -_TOL <= u <= 1 + _TOL and (best is None or t < best):
            best = max(t, 0.0)
    return best


def clip_route(
    points: Sequence[tuple[float, float]],
    source: tuple[str, tuple[float, float, float, float]],
    target: tuple[str, tuple[float, float, float, float]],
) -> list[tuple[float, float]]:
    """`points` with its first and last point moved along their own segment onto the outline of the node they touch.

    Each node is its kind and its box `(x, y, width, height)`. The layout ends a route on the box, so a kind whose outline
    lies inside it would leave the line short of the shape. A kind that fills its box keeps its endpoint.
    """
    out = list(points)
    if len(out) < 2:
        return out
    for index, neighbour, (kind, box) in ((0, 1, source), (-1, -2, target)):
        end, other = points[index], points[neighbour]
        dx, dy = end[0] - other[0], end[1] - other[1]
        if (dx != 0) == (dy != 0):  # not axis-aligned, or a zero-length segment
            continue
        d = (math.copysign(1.0, dx) if dx else 0.0, math.copysign(1.0, dy) if dy else 0.0)  # into the node
        depth = _depth(kind, box, end, d)
        if depth:
            out[index] = (round(end[0] + d[0] * depth, 6), round(end[1] + d[1] * depth, 6))
    return out


def draw_node(page: Page, kind: str, x: float, y: float, width: float, height: float, text: str) -> Shape:
    """A node of `kind` centred on `x`, `y` at this size, labelled `text`."""
    shape = page.create_shape(KINDS[kind][0], x=x, y=y, width=width, height=height, text=text)
    outline = _outline(kind, width, height)
    if outline is not None:
        set_geometry(shape, outline)
    if kind == "external":
        shape.set_cell_value("LinePattern", _DASHED)
    return shape


def draw_backdrop(page: Page, x: float, y: float, width: float, height: float, text: str, *, dashed: bool) -> Shape:
    """An unfilled labelled box, text at its top, to sit behind the shapes it surrounds."""
    shape = page.create_shape(ShapeKind.RECTANGLE, x=x, y=y, width=width, height=height, text=text)
    shape.set_cell_value("FillPattern", "0")
    shape.set_cell_value("VerticalAlign", "0")
    if dashed:
        shape.set_cell_value("LinePattern", _DASHED)
    return shape


LABEL_HEIGHT = 0.3
"""Height in inches of a one-line edge label's box."""


def label_size(text: str) -> tuple[float, float]:
    """Width and height in inches of an edge label's box: the width from its longest line, the height from its line count."""
    lines = text.split("\n")
    return snap(0.12 * max(len(line) for line in lines) + 0.3), snap(max(LABEL_HEIGHT, 0.25 * len(lines) + 0.05))


def draw_label(page: Page, x: float, y: float, text: str) -> Shape:
    """A borderless, unfilled text box centred on `x`, `y`, for an edge's label."""
    width, height = label_size(text)
    shape = page.create_shape(ShapeKind.RECTANGLE, x=x, y=y, width=width, height=height, text=text)
    shape.set_cell_value("FillPattern", "0")
    shape.set_cell_value("LinePattern", "0")
    shape.set_cell_value("VerticalAlign", "1")
    shape.set_cell_value("TextBkgnd", "#ffffff")  # the value Visio writes for an opaque white text background
    shape.set_cell_value("TextBkgndTrans", "0")
    return shape


def _even_steps(extent: float) -> float:
    """`extent` rounded up to an even number of grid steps, and at least two."""
    steps = max(math.ceil(round(extent / GRID, 6)), 2)
    return snap((steps + steps % 2) * GRID)


def draw_path(page: Page, points: Sequence[tuple[float, float]], *, arrow: bool, dashed: bool) -> Shape:
    """An open polyline through `points`, a 2-D shape with no fill, and an arrowhead at the last point when `arrow`."""
    left = snap(min(p[0] for p in points))
    bottom = snap(min(p[1] for p in points))
    # an even number of grid steps puts the centre on the grid, so the snapped pin and size leave the corner at left, bottom
    width = _even_steps(max(p[0] for p in points) - left)
    height = _even_steps(max(p[1] for p in points) - bottom)
    shape = page.create_shape(
        ShapeKind.RECTANGLE, x=snap(left + width / 2), y=snap(bottom + height / 2), width=width, height=height, text=""
    )
    set_geometry(shape, [([(px - left, py - bottom) for px, py in points], False)], no_fill=True)
    if arrow:
        shape.end_arrow = True
    if dashed:
        shape.set_cell_value("LinePattern", _DASHED)
    return shape
