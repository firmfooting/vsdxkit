"""The writes the diagram builder needs that the page API does not offer: Shape Data rows, outlines and open paths."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from xml.etree.ElementTree import Element

from vsdxkit import namespace
from vsdxkit.layout import snap
from vsdxkit.pages import Page
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.shapes import Shape

KIND_SHAPES: dict[str, ShapeKind] = {
    "start": ShapeKind.START_END,
    "end": ShapeKind.START_END,
    "process": ShapeKind.PROCESS,
    "decision": ShapeKind.DECISION,
    "data_store": ShapeKind.DATABASE,
    "external": ShapeKind.RECTANGLE,
    "document": ShapeKind.RECTANGLE,
    "subprocess": ShapeKind.RECTANGLE,
    "off_page": ShapeKind.RECTANGLE,
}
"""The bundled shape each node kind starts as. The last four are redrawn or restyled."""

DEFAULT_SIZE: dict[str, tuple[float, float]] = {
    "start": (2.0, 0.8),
    "end": (2.0, 0.8),
    "process": (2.2, 0.9),
    "decision": (2.6, 1.3),
    "data_store": (2.2, 0.9),
    "external": (2.2, 0.9),
    "document": (2.2, 1.0),
    "subprocess": (2.2, 0.9),
    "off_page": (1.6, 1.0),
}
"""Width and height in inches of each node kind before a long label widens it."""

_DASHED = "2"
"""A LinePattern index. Learn gives 0 as none and 1 as solid and calls 2 to 23 assorted, so what 2 draws is for the Visio shots to show."""


def _cell(name: str, value: str) -> Element:
    """A ``Cell`` element with this name and value."""
    return Element(f"{namespace}Cell", {"N": name, "V": value})


def add_data_rows(shape: Shape, rows: Mapping[str, str]) -> None:
    """Write each entry of `rows` as a string Shape Data row on `shape`, in the order given, replacing a row of the same name.

    The cells follow the order the bundled donors use. Type 0 is a string (Learn: Type Cell, Shape Data Section).
    """
    section = shape.xml.find(f'{namespace}Section[@N="Property"]')
    if section is None:
        section = Element(f"{namespace}Section", {"N": "Property"})
        leading = max((i + 1 for i, child in enumerate(shape.xml) if child.tag == f"{namespace}Cell"), default=0)
        shape.xml.insert(leading, section)
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


def draw_node(page: Page, kind: str, x: float, y: float, width: float, height: float, text: str) -> Shape:
    """A node of `kind` centred on `x`, `y` at this size, labelled `text`."""
    shape = page.create_shape(KIND_SHAPES[kind], x=x, y=y, width=width, height=height, text=text)
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


def draw_label(page: Page, x: float, y: float, text: str) -> Shape:
    """A borderless, unfilled text box centred on `x`, `y`, for an edge's label."""
    shape = page.create_shape(ShapeKind.RECTANGLE, x=x, y=y, width=snap(0.12 * len(text) + 0.3), height=0.3, text=text)
    shape.set_cell_value("FillPattern", "0")
    shape.set_cell_value("LinePattern", "0")
    shape.set_cell_value("VerticalAlign", "1")
    return shape


def draw_path(page: Page, points: Sequence[tuple[float, float]], *, arrow: bool, dashed: bool) -> Shape:
    """An open polyline through `points`, a 2-D shape with no fill, and an arrowhead at the last point when `arrow`."""
    left = min(p[0] for p in points)
    bottom = min(p[1] for p in points)
    width = max(max(p[0] for p in points) - left, 0.01)
    height = max(max(p[1] for p in points) - bottom, 0.01)
    shape = page.create_shape(
        ShapeKind.RECTANGLE,
        x=snap(left + width / 2),
        y=snap(bottom + height / 2),
        width=snap(width),
        height=snap(height),
        text="",
    )
    set_geometry(shape, [([(px - left, py - bottom) for px, py in points], False)], no_fill=True)
    if arrow:
        shape.end_arrow = True
    if dashed:
        shape.set_cell_value("LinePattern", _DASHED)
    return shape
