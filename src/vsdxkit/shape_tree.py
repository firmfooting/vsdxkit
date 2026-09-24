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

from collections.abc import Iterator
from xml.etree.ElementTree import Element

from vsdxkit import namespace

_SHAPE = f"{namespace}Shape"
_SHAPES = f"{namespace}Shapes"
_CELL = f"{namespace}Cell"


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
    # every wrapper a walk builds asks this: an ElementPath attribute predicate
    # tripled the cost of a walk, and any() over a generator costs half again
    # what this loop does
    for child in element:  # noqa: SIM110
        if child.get("N") == name and child.tag == _CELL:
            return True
    return False
