"""The one walk of a Visio shape tree, over XML elements.

A page or a master holds its top-level shapes in a `Shapes` element, and a
group holds its members in a `Shapes` element of its own; nothing else holds
shapes. Every traversal the wrappers offer - children, all shapes, the finders,
the ID high-water mark - is this walk, so they cannot disagree about which
shapes a page has or what order they come in.

These functions take and return elements and know nothing of the wrappers
built over them.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from xml.etree.ElementTree import Element

from vsdxkit import namespace

_SHAPE = f"{namespace}Shape"
"""The `<Shape>` tag, namespaced."""
_SHAPES = f"{namespace}Shapes"
"""The `<Shapes>` tag, namespaced: what holds a page's or a group's children."""
_CELL = f"{namespace}Cell"
"""The `<Cell>` tag, namespaced."""

# A ShapeSheet formula addresses another shape as `Sheet.5!Cell` or `Sheet5!Cell`.
# Visio writes the dotted form. This library's connector glue has written the
# undotted one -- `_XFTRIGGER(Sheet5!EventXFMod)`,
# `PAR(PNT(Sheet5!Connections.X1,...))` -- and files it saved carry it (#400).
# In both, the reference is nested inside a function call rather than at the
# start of the formula. Group 1 is the separator, `.` or empty, and group 2 the
# shape's ID.
#
# The lookbehind excludes the sheet of a cross-page reference: the `Sheet.5!` in
# `Pages[Page-2]!Sheet.5!Width` is an ID on the page named in front of it, and
# IDs are page-scoped, so remapping it through this page's map would repoint the
# reference at an unrelated shape. `tests/helpers/package_validator.py` draws
# the same line with its own copy of the pattern, and the two have to agree or
# one of them is wrong about which references a page owns.
SHEET_REFERENCE: re.Pattern[str] = re.compile(r"(?<!!)\bSheet(\.?)(\d+)!")
"""Matches a `Sheet.N!` or `SheetN!` shape reference in a cell formula."""


def iter_children(element: Element) -> Iterator[Element]:
    """The shapes directly below `element`, in document order.

    `element` is a page or master contents root, a `Shape`, or a `Shapes`
    element. Only a group holds a `Shapes` element, so any other shape has
    no children.
    """
    shapes = element if element.tag == _SHAPES else element.find(_SHAPES)
    if shapes is None:
        return
    yield from shapes.iterfind(_SHAPE)


def iter_edges(element: Element) -> Iterator[tuple[Element, Element]]:
    """Every shape below `element` with the element it sits under, depth first, parents first.

    The parent is `element` itself or a group `Shape`, never the `Shapes`
    element between them: a sub-shape inherits its group's master, so the
    group is the parent that means something.
    """
    for child in iter_children(element):
        yield element, child
        yield from iter_edges(child)


def iter_descendants(element: Element) -> Iterator[Element]:
    """Every shape below `element`, at any depth, depth first, parents first."""
    for _, child in iter_edges(element):
        yield child


def is_connector_element(element: Element, master: Element | None = None) -> bool:
    """Whether a shape is 1-D, which is what Visio's ``OneD`` reports.

    A 1-D shape has the 1-D Endpoints cells. A master instance may carry
    them only on its master, so `master` is the master shape it inherits
    from, where it has one.
    """
    return _has_cell(element, "BeginX") or (master is not None and _has_cell(master, "BeginX"))


def _has_cell(element: Element, name: str) -> bool:
    """Whether `element` has a direct ``<Cell N="name">`` child."""
    # every wrapper a walk builds asks this: an ElementPath attribute predicate
    # tripled the cost of a walk, and any() over a generator costs half again
    # what this loop does
    for child in element:  # noqa: SIM110
        if child.get("N") == name and child.tag == _CELL:
            return True
    return False


def remap_sheet_references(subtree: Element, id_map: Mapping[str, int]) -> None:
    """Rewrite the shape IDs in every cell formula under `subtree`, keeping each reference's own form.

    Covers `subtree`'s own cells as well as its descendants', and cells nested
    inside Sections, since a formula anywhere in the subtree may address a
    shape whose ID has just changed. An ID absent from `id_map` addresses a
    shape outside the renumbered subtree (the Swimlane List, for instance) and
    is left exactly as it is.
    """

    def replace(match: re.Match[str]) -> str:
        """One `SHEET_REFERENCE` match, remapped through `id_map` if it names a renumbered shape, else unchanged."""
        separator, shape_id = match.group(1), match.group(2)
        if shape_id not in id_map:
            return match.group(0)
        return f"Sheet{separator}{id_map[shape_id]}!"

    for cell in subtree.iter(_CELL):
        formula = cell.attrib.get("F")
        if formula is None or "Sheet" not in formula:
            continue
        remapped = SHEET_REFERENCE.sub(replace, formula)
        if remapped != formula:
            cell.attrib["F"] = remapped


def parent_of(root: Element, element: Element) -> Element | None:
    """The element that holds `element`, or None if it is not in this tree."""
    for candidate in root.iter():
        if element in list(candidate):
            return candidate
    return None


def find_or_create_shapes_tag(parent: Element) -> Element:
    """Return the ``<Shapes>`` container inside ``parent``, creating it if absent.

    A ``<Shape>`` is never a legal child of a ``<Shape>``: a group holds its
    children in a ``<Shapes>`` container, and a group that is currently empty
    has no such container until something is put into it. The same is true of a
    page, whose contents hang off one ``<Shapes>`` tag under ``<PageContents>``.
    """
    shapes_tag = parent.find(_SHAPES)
    if shapes_tag is None:
        shapes_tag = Element(_SHAPES)
        parent.append(shapes_tag)
    return shapes_tag
