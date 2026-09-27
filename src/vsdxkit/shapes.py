"""Shapes, and the parts of a shape a caller reads and writes.

A :class:`Shape` is one shape on a page, or a group holding others; a
:class:`Connector` is a 1-D shape whose ends can be glued to shapes. A
:class:`Cell` is one of a shape's ShapeSheet cells, and a
:class:`DataProperty` one of its Shape Data properties. A
:class:`ShapeCollection` is a live scope of shapes to iterate and look shapes
up in, and :class:`PageView` is the page as a shape sees it.

Reach shapes through a page, as ``page.children`` (its top-level shapes) or
``page.shapes`` (every shape, at any depth), never by constructing one: each
is a view onto an element of the page's XML, and the page builds it.
``page.create_shape(...)`` and :meth:`~vsdxkit.shapes.Shape.copy` make new ones.
"""

from __future__ import annotations

import copy
import html
import math
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Mapping
from logging import Logger
from typing import Protocol
from xml.etree.ElementTree import Element

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


from vsdxkit import namespace
from vsdxkit._connectors import _ConnectorPage, _float_end, _glued_ends, _retarget_connector
from vsdxkit._formulae import calc_value
from vsdxkit._inheritance import InheritedRow
from vsdxkit._logging_support import get_logger
from vsdxkit._shape_part import AttachedShape, ShapePart
from vsdxkit._shape_tree import find_or_create_shapes_tag, is_connector_element, iter_children, iter_edges, parent_of
from vsdxkit._xmlio import PartTree, insert_row_in_index_order, make_cell_element, to_float, xml_value
from vsdxkit.errors import InvalidOperationError, NotFoundError, PackageError
from vsdxkit.geometry import Geometry, GeometryCell
from vsdxkit.glue import ConnectorOptions, Glue, Routing
from vsdxkit.shape_kind import ShapeKind

_logger: Logger = get_logger(__name__)
"""This module's logger, under the ``vsdxkit`` hierarchy the library never configures a handler for."""


class PageView(Protocol):
    """A page, as :attr:`Shape.page` gives it.

    The type of a shape's back-reference to its page. It lists the page's
    public API apart from ``swimlanes``, ``require_swimlanes`` and ``vis``,
    whose types are declared above this module, and it can be written as the
    page can: ``shape.page.name = "Summary"`` renames the page. At runtime
    the object is that :class:`vsdxkit.pages.Page` itself.

    A shape on a master page has a master page here. Renaming one, or
    reading or setting its ``background``, raises
    :class:`vsdxkit.errors.InvalidOperationError`, because a master page has
    no entry in the document's page list.
    """

    @property
    def name(self) -> str:
        """The page's name.

        Setting it writes the new name as both the page's name and its
        universal name, in the document's page list and its ``app.xml``
        titles. On a master page it raises
        :class:`vsdxkit.errors.InvalidOperationError`.
        """
        ...

    @name.setter
    def name(self, value: str) -> None: ...

    @property
    def background(self) -> bool:
        """Whether the page is a background page, which other pages can show behind their own shapes.

        Setting it takes a ``bool``. On a master page, reading or setting it
        raises :class:`vsdxkit.errors.InvalidOperationError`.
        """
        ...

    @background.setter
    def background(self, value: bool) -> None: ...

    @property
    def index_num(self) -> int | None:
        """The page's zero-based position in its document's pages, or ``None`` for a master page or one removed from the document."""
        ...

    @property
    def xml(self) -> PartTree:
        """The page's part, parsed: its shapes and its ``Connect`` records.

        The value is an ``xml.etree.ElementTree.ElementTree``, which a caller
        reads and edits with the standard library.

        Assigning a tree replaces the part the document saves, while the page
        is still in its document. The setter takes such a tree.
        """
        ...

    # `PartTree`, where `Page.xml`'s setter takes `PartTree | None`: mypy reads
    # `Page`'s class-level `xml: PartTree` as its setter type, and a wider
    # setter here would stop `Page` satisfying this protocol
    @xml.setter
    def xml(self, value: PartTree) -> None: ...

    @property
    def width(self) -> float:
        """The page's width, in inches, from its page sheet's ``PageWidth`` cell.

        Setting it takes a positive number, or a string that reads as one;
        anything else raises :class:`ValueError`, and ``None`` raises
        :class:`TypeError`.
        """
        ...

    @width.setter
    def width(self, value: float | str | None) -> None: ...

    @property
    def height(self) -> float:
        """The page's height, in inches, from its page sheet's ``PageHeight`` cell.

        Setting it takes what :attr:`width` takes, and refuses what it refuses.
        """
        ...

    @height.setter
    def height(self, value: float | str | None) -> None: ...

    @property
    def is_master_page(self) -> bool:
        """Whether this is one of the document's master pages rather than a drawing page."""
        ...

    @property
    def children(self) -> ShapeCollection:
        """The page's top-level shapes."""
        ...

    @property
    def shapes(self) -> ShapeCollection:
        """Every shape on the page, at any depth, connectors included: depth first, parents first."""
        ...

    @property
    def connectors(self) -> tuple[Connector, ...]:
        """Every connector on the page, at any depth, glued at both ends, one or neither."""
        ...

    def connect(
        self,
        source: Shape,
        target: Shape,
        *,
        glue: Glue = Glue.DYNAMIC,
        routing: Routing = Routing.DEFAULT,
        from_point: int = 0,
        to_point: int = 0,
    ) -> Connector:
        """Create a connector glued from ``source`` to ``target``, both shapes on this page.

        See :meth:`vsdxkit.pages.Page.connect` for the options and what it raises.
        """
        ...

    def create_shape(
        self,
        kind_or_prototype: ShapeKind | Shape,
        *,
        x: float,
        y: float,
        width: float | None = None,
        height: float | None = None,
        text: str | None = None,
    ) -> Shape:
        """Create a shape on this page, centred on ``x``, ``y``.

        See :meth:`vsdxkit.pages.Page.create_shape` for the arguments and what it raises.
        """
        ...

    def apply_text_context(self, context: dict[str, object]) -> None:
        """Replace each ``{{key}}`` in the text of every shape on the page with its value from ``context``."""
        ...

    def find_replace(self, old: str, new: str) -> None:
        """Replace ``old`` with ``new`` in the text of every shape on the page."""
        ...


class _PageSeam(PageView, _ConnectorPage, Protocol):
    """What a shape needs from its page beyond the public view: the page's
    own bookkeeping, and the document operations the page passes on."""

    @property
    def _page_id(self) -> str:
        """The page's ID in the package: a drawing page's in pages.xml, a master's in masters.xml.

        A copied shape is pointed at the master it instances by this ID.
        """
        ...

    @property
    def _filename(self) -> str:
        """The name of the page's part, which a copy relates its destination page to for each master it uses."""
        ...

    @property
    def _pagesheet_xml(self) -> Element:
        """The page's `PageSheet` element, where `universal_name` reads a master's Layer section."""
        ...

    def _children(self) -> list[Shape]:
        """What :attr:`children` holds, as a list, for the library's own walks."""
        ...

    def _attached(self) -> bool:
        """Whether the page is still in its document: a shape is attached only while its page is."""
        ...

    def _delete(self, shapes: Iterable[Shape], gone_ids: set[str]) -> None:
        """The one deletion: `shapes`, the connectors glued to any of `gone_ids`, and every record naming them."""
        ...

    def _ensure_page_master_rel(self, master_part_name: str) -> None:
        """Ensure this page's rels relate it to the master part named `master_part_name`."""
        ...

    def _carry_relationships(self, copied: Element, source: _PageSeam) -> None:
        """Relate this page to what each ``r:id`` in `copied` names on `source`, and point the copy at it."""
        ...

    def _peer(self, other: PageView) -> _PageSeam:
        """`other` as a page of this library, for a shape copied onto it."""
        ...

    def _same_document(self, other: _PageSeam) -> bool:
        """Whether `other` is a page of this page's document, which decides whether a copy crosses documents."""
        ...

    def _master_by_id(self, master_id: str) -> _PageSeam | None:
        """The master page with this ID, as `Shape.master_page_ID` names it, or None."""
        ...

    def _master_is_one_d(self, master_id: str, master_shape_id: str | None) -> bool:
        """Whether the master shape an instance inherits from is 1-D, which makes the instance a `Connector`."""
        ...

    def _master_revision(self) -> int:
        """The document's count of changes to its masters: `Shape.master_shape`'s memo holds while it stays the same."""
        ...

    def _masters_for(self, master_ids: list[str], source: _PageSeam) -> Mapping[str, _PageSeam]:
        """This document's master for each of `master_ids`, as `source`'s document numbers them."""
        ...

    def _copy_shape_xml(self, element: Element) -> Element:
        """A copy of `element` at this page's top level, with IDs unused on this page."""
        ...

    def _renumber_shape_ids(self, subtree: Element, id_map: dict[str, int] | None = None) -> dict[str, int]:
        """Give a subtree IDs unused on this page, and follow them everywhere the page writes them."""
        ...


def _is_connector(shape: Shape) -> bool:
    """Whether `shape` is 1-D, reading the master it inherits from as well as its own cells."""
    return _is_one_d(shape.xml, shape._parent, shape._page)


def _is_name_or_copy(name: str | None, base: str) -> bool:
    """Whether `name` is `base`, or a numbered copy of it: Visio names the second one `base.12`.

    Only a number follows the last dot. A shape its author named
    `base.backup` is not a copy Visio made.
    """
    if name == base:
        return True
    stem, dot, suffix = (name or "").rpartition(".")
    return bool(dot) and stem == base and suffix.isdigit()


def _is_one_d(xml: Element, parent: _PageSeam | Shape, page: _PageSeam) -> bool:
    """The one test of whether a shape element is 1-D, before or after it has a wrapper.

    A sub-shape with no ``Master`` of its own instances its group's, so the
    parent is needed to find the master it inherits from.
    """
    if is_connector_element(xml):
        return True
    master_id = xml.attrib.get("Master")
    if master_id is None and isinstance(parent, Shape):
        master_id = parent.master_page_ID
    if master_id is None:
        return False
    return page._master_is_one_d(master_id, xml.attrib.get("MasterShape"))


def _shape_ids(master: _PageSeam) -> frozenset[str]:
    """The IDs of every shape a master holds."""
    return frozenset(shape_id for shape in master.xml.iter(f"{namespace}Shape") if (shape_id := shape.attrib.get("ID")))


def _drop_unreachable_master_shapes(
    root: Element, members: dict[str, frozenset[str]], dropped: set[Element], *, root_names_inherited: bool
) -> None:
    """Drop every `MasterShape` in `root`'s subtree that names no shape of the master it inherits from.

    A shape's master is its own `Master`, else its group's. A shape in
    `dropped` had a master that could not be resolved, and has none now: it
    and the shapes it holds inherit nothing from the groups around it.
    `MasterShape` on a shape that names a master itself is left alone, as the
    package validator leaves it: which master it reaches into is not settled.
    The exception is a copy's root that was given its group's master, whose
    `MasterShape` reaches into that master.
    """

    def check(element: Element, master: str | None, *, own_counts: bool) -> None:
        """Drop `element`'s `MasterShape` if `master` is None or holds no shape with that ID.

        An element naming its own `Master` is skipped unless `own_counts`
        says that `Master` is the one it was given from its group.
        """
        member = element.attrib.get("MasterShape")
        checked = member is not None and (element.attrib.get("Master") is None or own_counts)
        if checked and (master is None or member not in members.get(master, frozenset())):
            element.attrib.pop("MasterShape")

    masters: dict[Element, str | None] = {root: None if root in dropped else root.attrib.get("Master")}
    check(root, masters[root], own_counts=root_names_inherited)
    for parent, child in iter_edges(root):
        masters[child] = None if child in dropped else child.attrib.get("Master") or masters[parent]
        check(child, masters[child], own_counts=False)


def _coordinate_value(value: float | str | None) -> str:
    """Return a ShapeSheet coordinate value without serialising nulls."""
    if value is None:
        raise TypeError("coordinate value cannot be None")
    return xml_value(value)


# Visio brackets a shape's text with character (`cp`) and paragraph (`pp`)
# formatting runs. Editing the text has to leave those runs in place, so they
# are located by walking the Text element's children: the serialised form they
# take depends on which namespace prefix is in force, and matching it as text
# is what tied the old implementation to ElementTree's `ns0:` prefix.
_TEXT_RUN_TAGS = frozenset({f"{namespace}cp", f"{namespace}pp"})
"""The tags of the character and paragraph formatting runs that editing a shape's text leaves in place."""


def _is_formatting_run(element: Element) -> bool:
    """True for a self-closing character/paragraph formatting element."""
    return element.tag in _TEXT_RUN_TAGS and len(element) == 0 and not element.text


def _text_runs_of(text_element: Element | None) -> tuple[list[Element], str, list[Element], str]:
    """Split a `<Text>` element into leading runs, content, trailing runs and newlines.

    The leading and trailing runs are the element's own children, not copies, so
    a caller may re-append them after clearing it. Visio ends a Text element
    with a newline that is not part of the text; it is reported separately so
    that writing the text back puts it there again.

    Module level rather than a Shape method because it reads a bare `Text`
    element and nothing of the Shape around it.

    A run between two pieces of content is folded into the content string and
    cannot be recovered from it, which corrupts the text on write. See #317;
    fixing it means modelling the middle children as elements too.
    """
    if not isinstance(text_element, Element):
        return [], "", [], ""

    children = list(text_element)
    start = 0
    if not text_element.text:
        while start < len(children) and _is_formatting_run(children[start]):
            start += 1
            if children[start - 1].tail:
                break  # this run's trailing text is where the content starts

    end = len(children)
    while end > start:
        candidate = children[end - 1]
        tail = candidate.tail or ""
        if not _is_formatting_run(candidate):
            break
        # only whitespace may follow the final run; nothing at all may sit
        # between two runs, or the text before it belongs to the content
        if tail.strip() if end == len(children) else tail:
            break
        end -= 1

    leading = (text_element.text if start == 0 else children[start - 1].tail) or ""
    content = leading + "".join(html.unescape(ET.tostring(child, encoding="unicode")) for child in children[start:end])
    suffix = children[end:]
    trailing = ""
    if not suffix:
        # nothing follows the content, so a newline at its end is Visio's
        # terminator rather than text; a trailing run keeps its own tail
        stripped = content.rstrip("\n")
        content, trailing = stripped, content[len(stripped) :]
    return children[:start], content, suffix, trailing


def _substitute(text: str, context: dict[str, object]) -> str:
    """Replace every `{{key}}` in `text` with its value from `context`."""
    for key, value in context.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def _write_text(
    shape_xml: Element,
    value: str,
    *,
    prefix: list[Element],
    suffix: list[Element],
    trailing: str,
) -> None:
    """Write `value` as a shape element's text, putting back the runs around it.

    Every argument is required: this writes back a split the caller already
    holds, and deriving a missing one here would silently discard whichever the
    caller did pass.
    """
    value += trailing
    tag = f"{namespace}Text"
    text_element = shape_xml.find(tag)
    if not isinstance(text_element, Element):  # create Text element if not found
        text_element = Element(tag)
        shape_xml.append(text_element)
    attrib = dict(text_element.attrib)  # e.g. xml:space="preserve"
    text_element.clear()
    text_element.attrib.update(attrib)
    for run in prefix:
        run.tail = None
        text_element.append(run)
    if prefix:
        prefix[-1].tail = value
    else:
        text_element.text = value
    for run in suffix:
        text_element.append(run)


class Cell(ShapePart):
    """One of a shape's ShapeSheet cells: a name, a value and, sometimes, a formula.

    Reach a cell through :attr:`Shape.cells` or a shape's cell writers,
    rather than constructing one.
    """

    xml: Element
    """The ``<Cell>`` element this reads and writes."""
    shape: Shape
    """The shape the cell belongs to. A write through the cell is refused once that shape is detached."""

    def __init__(self, xml: Element, shape: Shape):
        """Wrap `xml`, one of `shape`'s cell elements; `Shape.cells` and the cell writers make these."""
        self.xml = xml
        self.shape = shape

    @property
    @override
    def _shape(self) -> AttachedShape:
        """The shape the detached-shape guard asks, so a write through a cell of a deleted shape is refused."""
        # the shape, not its document: a write through a part of a deleted
        # shape is refused, as a write to the shape itself is
        return self.shape

    @property
    def value(self) -> str | None:
        """The cell's value, its ``V`` attribute, as the text the file holds; ``None`` when it has none.

        Setting it writes ``str(value)`` to ``V`` and removes the formula, as
        typing a number into the ShapeSheet cell does in Visio, so the value
        is the one Visio shows. ``None`` raises :class:`TypeError`, and a
        write to a detached shape's cell raises
        :class:`~vsdxkit.errors.InvalidOperationError`.
        """
        return self.xml.attrib.get("V")

    @value.setter
    def value(self, value: float | str) -> None:
        self._set_value(value, keep_formula=False)

    def _set_value(self, value: float | str, *, keep_formula: bool) -> None:
        """Write `value` to ``V``, and without `keep_formula` remove ``F``, as typing a number into the ShapeSheet cell does in Visio.

        The library keeps the formula where the value it writes is the one the
        formula gives: the formula cache, the glue engine, and a 1-D shape's
        cells derived from its ends.
        """
        self._require_attached(f"writing the value of cell {self.name!r}")
        text = xml_value(value)
        self.xml.attrib["V"] = text
        if not keep_formula:
            self.xml.attrib.pop("F", None)

    @property
    def formula(self) -> str | None:
        """The cell's formula, its ``F`` attribute, or ``None`` when it has none.

        Setting it writes a string to ``F`` and leaves the value as it was:
        nothing here evaluates the formula. It refuses what :attr:`value`
        refuses.
        """
        return self.xml.attrib.get("F")

    @formula.setter
    def formula(self, value: str) -> None:
        self._require_attached(f"writing the formula of cell {self.name!r}")
        self.xml.attrib["F"] = xml_value(value)

    @property
    def name(self) -> str | None:
        """The cell's name, its ``N`` attribute, such as ``PinX``; ``None`` for a cell without one."""
        return self.xml.attrib.get("N")

    def __repr__(self) -> str:
        """Shows the cell's name, value and formula."""
        return f"Cell: name={self.name} val={self.value} formula={self.formula}"


class DataProperty(InheritedRow, ShapePart):
    """Represents a single Data Property item associated with a Shape object

    A property a shape inherits from its master is handed out marked
    :attr:`inherited`. Setting :attr:`value`, or calling
    :meth:`set_attribute`, on one materialises an override row on the
    instance rather than writing to the master page's XML.
    """

    shape: Shape
    """The shape the property was read through: for a property inherited from a master, the instance."""
    xml: Element
    """The property's ``<Row>`` element.

    For an inherited property it is the master's row, until the first write
    through :attr:`value` or :meth:`set_attribute`, or a call to
    :meth:`make_local`, gives the instance a row of its own.
    """
    name: str | None
    """The row's ``N`` attribute, which an override row shares with its master's row; ``None`` for a row without one."""

    def __init__(self, *, xml: Element, shape: Shape):
        """init a DataProperty from a property xml element in a Shape object"""
        self.shape = shape  # reference back to Shape object
        self.xml = xml  # reference to xml used to create DataProperty
        self.name = xml.attrib.get("N")

    @property
    def label(self) -> str | None:
        """The label Visio shows the property under, which :attr:`Shape.data_properties` keys by; ``None`` where there is none.

        It is read from the row on every access, as are :attr:`value_type`,
        :attr:`prompt` and :attr:`sort_key`. Visio inherits each cell on its
        own, so a cell the row lacks, as an override of a master's property
        lacks most of them, is read from the master's row of the same name,
        or, where a master's shape is itself an instance of another master,
        from the nearest row up that chain that has it; each gives ``None``
        where no row has it. A property read from the master reads the
        shape's own row as well, once another object for it has written one,
        as :attr:`value` does. The four are read-only:
        :meth:`set_attribute` writes them.
        """
        return self._field("Label")

    @property
    def value_type(self) -> str | None:
        """The ``Type`` cell's value, as Visio numbers property types (``"0"`` text, ``"2"`` number, ``"5"`` date, and so on); ``None`` where there is none."""
        return self._field("Type")

    @property
    def prompt(self) -> str | None:
        """The ``Prompt`` cell's value, the description Visio gives the property; ``None`` where there is none."""
        return self._field("Prompt")

    @property
    def sort_key(self) -> str | None:
        """The ``SortKey`` cell's value, which orders the properties in Visio's Shape Data window; ``None`` where there is none."""
        return self._field("SortKey")

    def _field(self, cell: str) -> str | None:
        """Cell `cell`'s value, as `_cell_or_masters` finds the cell: this row's, or a master's row of the same ``N`` up the chain."""
        element = self._cell_or_masters(cell)
        return None if element is None else element.attrib.get("V")

    def _cell_or_masters(self, cell: str) -> Element | None:
        """Cell `cell` of this row, or else of the nearest master's row of the same ``N`` that has it; ``None`` where none does.

        A master's shape can itself be an instance of another master, and
        Visio inherits each cell on its own down the whole chain, as
        :attr:`Shape.data_properties` lists the properties it inherits.

        A property still marked inherited looks first in the instance's own
        row of its ``N``, where another object for the property has written
        one since this one was read: Visio reads that row over the master's.
        """
        rows = [self.xml]
        if self.inherited:
            own = self._row_in(self.shape.xml)
            if own is not None:
                rows.insert(0, own)
        for row in rows:
            element = row.find(f'{namespace}Cell[@N="{cell}"]')
            if element is not None:
                return element
        master_shape = self.shape.master_shape
        while master_shape is not None:
            row = self._row_in(master_shape.xml)
            element = None if row is None else row.find(f'{namespace}Cell[@N="{cell}"]')
            if element is not None:
                return element
            master_shape = master_shape.master_shape
        return None

    def _row_in(self, shape_xml: Element) -> Element | None:
        """The row of this property's ``N`` in the Property section of `shape_xml`, a shape's element, or ``None``.

        Looked up directly, not through that shape's properties, which would
        rebuild them on every read. On the instance's own element it is the
        override a write goes to; on a master's, the row it reads over.
        """
        section = shape_xml.find(f'{namespace}Section[@N="Property"]')
        if self.name is None or section is None:
            return None
        return next((row for row in section.iterfind(f"{namespace}Row") if row.get("N") == self.name), None)

    @property
    @override
    def _shape(self) -> AttachedShape:
        """The shape the detached-shape guard asks: the instance, for an inherited property, so a write is refused once it is deleted."""
        # the shape, not its document: a write through a part of a deleted
        # shape is refused, as a write to the shape itself is
        return self.shape

    def _inherited_by(self, shape: Shape) -> DataProperty:
        """This property as an instance of the master sees it, marked inherited.

        The copy reads the master's Row element, so label, type and prompt are
        already resolved; the first write to :attr:`value` calls
        :meth:`make_local`, which gives ``shape`` a row of its own.
        """
        prop = copy.copy(self)
        prop.shape = shape
        prop.inherited = True
        return prop

    @override
    def _materialise(self) -> None:
        """Add an override row for this property to the instance's shape.

        Visio matches an override to the master's row by the row's ``N``
        attribute, and reads label, type and prompt from the master, so the
        new row needs nothing but that name; the caller is about to write the
        ``Value`` cell. A master row with no name has nothing to match on, so
        the label is carried down to keep the property addressable.

        Where the instance already has a row of that name, written through
        another object for this property, that row is reused: Visio reads
        one override row per name.
        """
        # make_local() is public and reaches here directly, not only through
        # the guarded value setter, and this is the only materialisation path
        self._require_attached("materialising an inherited data property")
        existing = self._row_in(self.shape.xml)
        if existing is not None:
            self.xml = existing
            return
        section = self.shape.xml.find(f'{namespace}Section[@N="Property"]')
        if section is None:
            section = ET.fromstring(f'<Section xmlns="{namespace[1:-1]}" N="Property"/>')
            self.shape._insert_section(section)

        row = ET.fromstring(f'<Row xmlns="{namespace[1:-1]}"/>')
        if self.name is not None:
            row.attrib["N"] = self.name
        else:
            label_cell = self.xml.find(f'{namespace}Cell[@N="Label"]')
            if label_cell is not None:
                row.append(copy.deepcopy(label_cell))
        section.append(row)
        self.xml = row
        _logger.debug("materialised inherited data property %r on shape %s", self.label, self.shape.ID)

    @property
    def value(self) -> str | None:
        """Get the value of the data property, or None when it has none.

        An override row with no ``Value`` cell, such as one a relabel through
        :meth:`set_attribute` wrote, reads the master's row's, as Visio does.

        Reading is free of side effects: it neither creates the ``Value`` cell
        nor tidies a ``No Formula`` formula, so inspecting a document does not
        change the bytes it saves.
        """
        value_cell = self._cell_or_masters("Value")
        if not isinstance(value_cell, Element):
            return None
        if value_cell.attrib.get("V") is not None:
            return value_cell.attrib.get("V")  # value from the V attribute
        return value_cell.text or None  # or from the element's inner text

    @value.setter
    def value(self, value: float | str | None) -> None:
        """Set the value of the data property, creating the cell if absent.

        The value wins: writing removes the ``Value`` cell's formula, whatever
        it is, as typing into the Shape Data window does in Visio. Visio
        recalculates a formula on open, so one left beside the value, a
        ``GUARD`` or a ``CONTAINERSHEETREF`` included, would replace it. That
        covers the placeholder ``No Formula`` as well, which left beside a
        value makes the cell disagree with itself. Upstream dave-howard/vsdx#79.

        The cell's declared unit is left alone. Stamping ``STR`` over it would
        retype a date or numeric property as a string, and a cell created here
        declares no unit rather than guessing one from the value.

        A property inherited from a master is given an override row on this
        shape first, so the master's value is left as it was, and with it every
        other shape drawn from that master.
        """
        # ahead of make_local(), which materialises an override row: a refused
        # write must not leave an empty property behind on the shape
        self._require_attached(f"writing data property {(self.label or self.name)!r}")
        self.make_local()
        text = "" if value is None else str(value)
        value_cell = self.xml.find(f'{namespace}Cell[@N="Value"]')
        if not isinstance(value_cell, Element):
            value_cell = Element(f"{namespace}Cell")
            value_cell.attrib["N"] = "Value"
            value_cell.attrib["V"] = text
            self.xml.append(value_cell)
            return
        if value_cell.attrib.get("V") is None and value_cell.text:
            value_cell.text = text  # this row carries its value as inner text
        else:
            value_cell.attrib["V"] = text
        value_cell.attrib.pop("F", None)  # the value wins, as in Visio (#300)

    def get_attribute(self, name: str, attrib: str) -> str | None:
        """Get the attribute value of the cell element"""
        element = self._get_element(name)
        if isinstance(element, Element):
            return element.attrib.get(attrib)

    def set_attribute(self, name: str, attrib: str, value: str) -> bool:
        """Set attribute `attrib` of cell `name` of this property's row; ``False`` where neither the row nor its master's has that cell.

        A property inherited from a master is given a row of its own first,
        or the one the instance already has for it, and a cell the row lacks
        is copied down from the master's row of the same name, so the master
        is left as it was.

        Writing ``V`` removes the cell's formula, whether the cell was copied
        down or was this row's own, as :attr:`value` does: the value wins, as
        typing into the ShapeSheet does in Visio, which would otherwise
        recalculate the formula over it on open. Any other attribute leaves
        the formula as it is.
        """
        self._require_attached("DataProperty.set_attribute()")
        source = self._cell_or_masters(name)
        if source is None:
            return False
        self.make_local()
        element = self._get_element(name)
        if element is None:
            element = copy.deepcopy(source)
            self.xml.append(element)
        element.attrib[attrib] = value
        if attrib == "V":
            element.attrib.pop("F", None)  # the value wins, as in Visio (#300)
        return True

    def _get_element(self, name: str) -> Element | None:
        """Get the value of the data property as an xml element"""
        element = self.xml.find(f'{namespace}Cell[@N="{name}"]')
        return element


def _wrap(xml: Element, parent: _PageSeam | Shape, page: _PageSeam) -> Shape:
    """The wrapper for a shape element: a `Connector` for a 1-D shape, a `Shape` for any other.

    Every wrapper the library hands out is made here, so a connector is a
    `Connector` however it was reached.
    """
    if _is_one_d(xml, parent, page):
        return Connector(xml=xml, parent=parent, page=page)
    return Shape(xml=xml, parent=parent, page=page)


def _wrap_children(element: Element, parent: _PageSeam | Shape, page: _PageSeam) -> list[Shape]:
    """A Shape for each shape directly inside `element`, a page's contents root or a group."""
    children = []
    for slot, child in enumerate(iter_children(element)):
        shape = _wrap(child, parent, page)
        shape._slot = slot  # where the walk found it, for is_attached to try first
        children.append(shape)
    return children


def _wrap_descendants(element: Element, parent: _PageSeam | Shape, page: _PageSeam) -> list[Shape]:
    """A Shape for every shape inside `element`, at any depth, depth first and parents first.

    Each is given the wrapper of the shape it sits in as its parent, and
    `parent` for those directly inside `element`.
    """
    wrappers: dict[Element, _PageSeam | Shape] = {element: parent}
    slots: dict[Element, int] = {}
    shapes: list[Shape] = []
    for holder, child in iter_edges(element):
        shape = _wrap(child, wrappers[holder], page)
        shape._slot = slots.get(holder, 0)
        slots[holder] = shape._slot + 1
        wrappers[child] = shape
        shapes.append(shape)
    return shapes


def _as_shape(end: object) -> Shape:
    """An end the connector engine found, which is always one of this module's shapes.

    The engine looks ends up in ``page.shapes``, so the narrowing never fails.
    """
    if not isinstance(end, Shape):
        raise TypeError(f"expected a vsdxkit Shape, got {type(end).__name__}")
    return end


class Shape:
    """One shape on a page, or a group holding other shapes.

    Reach a shape through ``page.shapes`` (every shape, at any depth) or
    ``page.children`` (a page's or a group's top-level shapes), rather than
    constructing one; ``page.create_shape(...)`` and :meth:`copy` make new
    ones.
    """

    xml: Element
    """The shape's ``<Shape>`` element, which this object is a view onto: reads come from it and writes go to it."""
    _parent: _PageSeam | Shape
    """The page, or the group `Shape`, this shape sits in: set by `_wrap`, repointed by `append_shape`."""
    _page: _PageSeam
    """The page the shape is on, a master page for a master's shape: the seam every page and document operation goes through."""
    _geometry: Geometry | None
    """The `Geometry` over `_geometry_xml`, built on the first read of `geometry` and held after it; None until then."""
    _geometry_xml: Element | None
    """The shape's own Geometry section, located when the wrapper is built, or None where it has none."""
    _master_shape: Shape | None
    """What `master_shape` last resolved, None included; good while `_master_shape_key` still matches."""
    _master_shape_resolved: bool
    """Whether `_master_shape` holds a resolution at all, since None is one."""
    _master_shape_key: tuple[str | None, str | None, int, tuple[Element, ...] | None] | None
    """The `_master_shape_state` the memo was built from; a different state resolves the master again."""
    _slot: int | None
    """Where the element last sat among its container's children, which `_held_by` tries first; None until found."""

    def __init__(self, xml: Element, parent: _PageSeam | Shape, page: _PageSeam):
        """Wrap `xml`, a shape element held by `parent` on `page`.

        The library builds every wrapper through `_wrap`, which picks
        `Connector` for a 1-D shape; a caller reaches shapes through a page.
        """
        self.xml = xml
        self._parent = parent
        self._page = page

        self._geometry = None
        self._master_shape = None
        self._master_shape_resolved = False
        self._slot = None  # where this element last sat among its container's children
        self._master_shape_key = None
        geometry = self.xml.find(f'{namespace}Section[@N="Geometry"]')
        # the section is located here, but the Geometry object over it is left
        # to the property: building one resolves this shape's master, and a
        # caller walking a page for ids or text never looks at geometry at all
        self._geometry_xml = geometry if type(geometry) is Element else None

    def __repr__(self) -> str:
        """Shows the tag, the ID, whether the shape is a master's, its ``Type`` and its text; only the tag and ID once detached."""
        if not self.is_attached:
            return f"<Shape tag={self.tag} ID={self.ID} detached >"
        return f"<Shape tag={self.tag} ID={self.ID} is_master=({self.is_master_shape}) type={self.shape_type} text='{self.text}' >"

    def __eq__(self, other: object) -> bool:
        """The same shape: the same element, whichever wrapper, of whichever class, holds it.

        An element belongs to one document, so its identity is the document's
        too. Nothing that can change - the shape's ID, its page's name, the
        file's name - takes part.
        """
        return isinstance(other, Shape) and other.xml is self.xml

    def __hash__(self) -> int:
        """Stable for the wrapper's life, through renames, renumbering, saves and deletion."""
        return id(self.xml)

    @property
    def is_attached(self) -> bool:
        """Whether this shape is still on its page, and its page still in its document.

        A shape deleted from its page, or on a page removed from the document,
        is detached. What its element's attributes and its place say stays
        readable: ``ID``, ``xml``, ``tag``, ``shape_type``, ``shape_name``,
        ``master_page_ID``, ``master_shape_ID``, the three style IDs,
        ``text_color``, ``page``, ``parent``, ``repr``, equality and hash. So
        does what is found through its page and master: ``is_master_shape``,
        ``master_page``, ``master_shape`` and ``universal_name``. ``children``
        and ``descendants`` hand out a collection, which raises when read.

        Reading its cells, coordinates, sizes, text, geometry, data properties
        or connectors raises :class:`~vsdxkit.errors.InvalidOperationError`, as does every
        write.
        """
        page = self._page
        if not page._attached():
            return False
        # the wrapper's own parent chain first: each link is checked against
        # its container's children, so a chain that holds proves the element is
        # on the page, at the cost of the siblings on the way up rather than
        # every element on the page. A chain that breaks is not proof of the
        # opposite - another wrapper may have moved the element into a group -
        # so only then is the page walked.
        return self._held_by_parents() or self.xml in page.xml.getroot().iter(self.xml.tag)

    def _held_by_parents(self) -> bool:
        """Whether every link of the wrapper's parent chain, up to the page, is still held by its container.

        True proves the element is on the page; False proves nothing, since
        another wrapper may have moved the element.
        """
        shape: Shape = self
        while True:
            container = shape._container()
            if container is None or not shape._held_by(container):
                return False
            parent = shape._parent
            if not isinstance(parent, Shape):
                return True  # the page's own Shapes element, found from its current root
            shape = parent

    def _container(self) -> Element | None:
        """The ``<Shapes>`` element this shape's parent keeps its shapes in, or ``None`` where it has none.

        The page's, for a top-level shape; the group's, for a member. It is
        where the shape's element sits, or sat before it was deleted.
        """
        parent = self._parent
        holder = parent.xml if isinstance(parent, Shape) else self._page.xml.getroot()
        return None if holder is None else holder.find(f"{namespace}Shapes")

    def _held_by(self, container: Element) -> bool:
        """Whether `container` holds this element among its children.

        Where the element last sat is tried first, so a shape read over and
        over costs one comparison rather than a pass over all its siblings.
        """
        slot = self._slot
        if slot is not None and slot < len(container) and container[slot] is self.xml:
            return True
        children = list(container)
        if self.xml not in children:
            return False
        self._slot = children.index(self.xml)
        return True

    def _require_attached(self, operation: str) -> None:
        """Raise :class:`InvalidOperationError`, naming `operation`, once the shape is detached.

        This is the guard `AttachedShape` asks for, so a shape's cells and
        properties refuse through it too.
        """
        if not self.is_attached:
            raise InvalidOperationError(
                f"{operation} refused: shape {self.ID} on page {self._page.name!r} is no longer in the document"
            )

    # A Shape is a view onto its element, not a snapshot of it. Everything below
    # is read from `self.xml` on each access rather than copied in __init__,
    # because a copy is a second store of the same fact and every writer of the
    # element then has to remember to update it. The ID allocator did not,
    # which left a live Shape naming an id that was no longer on the page: glue
    # written from it dangled, and deleting it missed the connectors glued to
    # it. See #320, and #278 for the same pattern in the Connect records.

    @property
    def tag(self) -> str:
        """The element's tag in ElementTree's ``{uri}name`` form: ``{http://schemas.microsoft.com/office/visio/2012/main}Shape``."""
        return self.xml.tag

    @property
    def ID(self) -> str | None:
        """This shape's page-scoped ID, as its element declares it.

        Read-only. An ID is not the shape's alone to change: the element
        attribute, the page's ``Connect`` records and the ``Sheet.N!``
        references in other shapes' formulas all name it. The page assigns a
        new ID when a shape is created, copied, repeated by a template loop,
        or appended into a group, and moves all three together.
        """
        return self.xml.attrib.get("ID")

    @property
    def page(self) -> PageView:
        """The page this shape is on. Still answers once the shape is deleted."""
        return self._page

    @property
    def parent(self) -> PageView | Shape:
        """The page, or the group shape, this shape sits in."""
        return self._parent

    @property
    def master_page_ID(self) -> str | None:
        """The ID of the master this shape instances, or its group's.

        A sub-shape of a group usually carries no ``Master`` of its own and
        instances whatever its group does, so it falls back to the parent's.
        This is the master's ID in the package, not its position in
        :attr:`vsdxkit.document.Document.master_pages`; :attr:`master_page` is
        the master itself.
        """
        own = self.xml.attrib.get("Master")
        if own is None and isinstance(self._parent, Shape):
            return self._parent.master_page_ID
        return own

    @master_page_ID.setter
    def master_page_ID(self, value: str | None) -> None:
        """Repoint the shape at another master, or at none.

        Writing ``None`` drops the attribute, which puts a sub-shape back to
        inheriting its group's master.

        :raises InvalidOperationError: if the shape is detached
        """
        self._require_attached("writing a shape's master_page_ID")
        if value is None:
            self.xml.attrib.pop("Master", None)
        else:
            self.xml.attrib["Master"] = value

    @property
    def master_shape_ID(self) -> str | None:
        """The id of the shape inside the master that this shape instances.

        Read-only, unlike :attr:`master_page_ID`: which member of a master an
        instance derives from is settled when the instance is created, and
        nothing in this library repoints it afterwards.
        """
        return self.xml.attrib.get("MasterShape")

    @property
    def shape_type(self) -> str | None:
        """The element's ``Type``: ``'Shape'``, ``'Group'``, ``'Foreign'`` and so on."""
        return self.xml.attrib.get("Type")

    @property
    def shape_name(self) -> str | None:
        """The shape's universal name, falling back to its localised one."""
        return self.xml.attrib.get("NameU") or self.xml.attrib.get("Name")

    @property
    def geometry(self) -> Geometry | None:
        """This shape's Geometry section, merged with the master's, or ``None``.

        Built on first read and then held for as long as this Shape object
        lives, so ``shape.geometry`` twice gives the same object and a row
        written through one read is seen by the next.

        Building it resolves the shape's master, which is why it is deferred:
        walking a page for ids or text mints a Shape per element and touches
        no geometry at all.

        Only the building is deferred. Which section it reads is decided when
        the Shape is built: a Geometry section added to or removed from the
        XML afterwards is seen from the next Shape for this element, not this
        one.
        """
        self._require_attached("reading a shape's geometry")
        if self._geometry_xml is None:
            return None
        if self._geometry is None:
            self._geometry = Geometry(xml=self._geometry_xml, shape=self)
        return self._geometry

    @property
    def is_master_shape(self) -> bool:
        """Returns True if the shape is a master or False if the shape inherits from a master shape or has no master"""
        return self._page.is_master_page  # shape is a 'master' if it is contained by a master page

    @property
    def universal_name(self) -> str | None:
        """The shape's universal name, its ``NameU`` attribute, or ``None``.

        Unlike :attr:`shape_name`, it does not fall back to the localised
        name. For an instance of a master, a ``NameUniv`` cell sitting
        directly in the Layer section of the master's page sheet takes its
        place; Visio writes that cell inside a layer's row, where this does
        not look.
        """
        name_univ = self.xml.attrib.get("NameU")  # default to shapes own unicode name
        if self.master_shape:
            page_sheet = self.master_shape._page._pagesheet_xml
            layer = page_sheet.find(f'{namespace}Section[@N="Layer"]')
            name_univ_cell = layer.find(f'{namespace}Cell[@N="NameUniv"]') if layer is not None else None
            if name_univ_cell is not None:
                name_univ = name_univ_cell.attrib.get("V") or name_univ
        return name_univ

    def copy(self, page: PageView | None = None) -> Shape:
        """Copy this Shape to the specified destination Page, and return the copy.

        If the destination page is not specified, the Shape is copied to its containing Page.

        :param page: The page where the new Shape will be placed.
            If not specified, the copy will be placed in the original shape's page.
        :type page: :class:`PageView` (Optional), which must be a :class:`vsdxkit.pages.Page` at runtime
        :raises TypeError: if ``page`` is not a :class:`vsdxkit.pages.Page`
        :raises InvalidOperationError: if this shape has been deleted or its page removed, or if the
            destination page is no longer in its document; nothing is written

        :return: :class:`Shape` the new copy of shape
        """
        # the source first: a deleted shape, or one on a removed page, is read
        # no more than it is written, and copying it would bring it back
        self._require_attached("Shape.copy()")
        dst_page = self._page if page is None else self._page._peer(page)
        if not dst_page._attached():
            raise InvalidOperationError(
                f"page {dst_page.name!r} is no longer in its document, so nothing can be copied onto it"
            )
        master_ids = [node.attrib["Master"] for node in self.xml.iter(f"{namespace}Shape") if node.attrib.get("Master")]
        # A sub-shape of a master instance names no master itself: it inherits
        # its group's. Copied onto a page it leaves that group, so the copy has
        # to name the master, or its MasterShape reaches into nothing.
        inherited = self.master_page_ID if not self.xml.attrib.get("Master") else None
        if inherited:
            master_ids.insert(0, inherited)
        # resolved, and imported from another document, before the copy: the
        # source still holds the masters its shapes name (#331)
        masters = dst_page._masters_for(master_ids, self._page)
        new_shape_xml = dst_page._copy_shape_xml(self.xml)
        cross_document = not dst_page._same_document(self._page)
        # within one document a dangling master is kept, as it is on any other
        # copy; only another document's copy drops it, below
        if inherited and (inherited in masters or not cross_document):
            new_shape_xml.attrib["Master"] = inherited
        dropped: set[Element] = set()
        for node in new_shape_xml.iter(f"{namespace}Shape"):
            master_id = node.attrib.get("Master")
            if not master_id:
                continue
            if master_id in masters:
                node.attrib["Master"] = masters[master_id]._page_id
            elif cross_document:
                # a master the source could not resolve: in another document it
                # would name a master that package does not declare, and Visio
                # drops the shape on open
                node.attrib.pop("Master")
                node.attrib.pop("MasterShape", None)
                dropped.add(node)
        if cross_document:
            # the master a copy now names may be built differently from the one
            # it was copied under - a MatchByName master answers for its name
            # alone - or may be gone altogether
            members = {master._page_id: _shape_ids(master) for master in masters.values()}
            _drop_unreachable_master_shapes(new_shape_xml, members, dropped, root_names_inherited=bool(inherited))
        # every page that shows an instance of a master relates to it, as Visio
        # writes it; a copy onto another page of this document adds one too
        for master in masters.values():
            dst_page._ensure_page_master_rel(master._filename)
        if not cross_document and dst_page is not self._page:
            dst_page._carry_relationships(new_shape_xml, self._page)

        # _copy_shape_xml put it at the page's top level, whatever the source sat in
        return _wrap(new_shape_xml, dst_page, dst_page)

    @property
    def master_shape(self) -> Shape | None:
        """The shape on this shape's master that it instances, or None.

        The result is held rather than rebuilt on every read. Resolving a
        master walks the master page and builds a Shape there, and a shape
        reads through its master for every cell it inherits: resolving it
        afresh each time made reading a page's coordinates over twice as slow.

        It is resolved again when what decides it changes: this shape's
        ``Master`` or ``MasterShape`` attribute, read from the XML each time;
        the masters the document holds, which change when a copy imports one;
        or the master element's own children, by identity, since the Shape
        held locates its Geometry section when it is built. The master's cells
        and properties are read live through the Shape held, so an edit to one
        shows up on the next read.
        """
        if self._master_shape_resolved and self._master_shape_key == self._master_shape_state():
            return self._master_shape
        self._master_shape = self._resolve_master_shape()
        self._master_shape_resolved = True
        self._master_shape_key = self._master_shape_state()
        return self._master_shape

    def _master_shape_state(self) -> tuple[str | None, str | None, int, tuple[Element, ...] | None]:
        """What the memo was built from.

        The reference this shape holds, which is writable - creating a
        connector repoints ``master_page_ID``; the catalog's count of master changes; and
        the master element's children, so a section added to, removed from or
        swapped on the master rebuilds the Shape that reads it.
        """
        master = self._master_shape
        children = None if master is None else tuple(master.xml)
        return (self.master_page_ID, self.master_shape_ID, self._page._master_revision(), children)

    def _resolve_master_shape(self) -> Shape | None:
        """Find `master_shape` afresh, for the memo to hold.

        The master's first top-level shape, or, where this shape names a
        `MasterShape`, the shape of that ID inside it. None without a master,
        where the document has no master of that ID, or where no shape inside
        has the ID `MasterShape` names. A master page with no shapes raises
        IndexError.
        """
        if self.master_page_ID is None:
            return None  # no master set for this Shape
        master_page = self._page._master_by_id(self.master_page_ID)
        if not master_page:
            return None  # None if no master page set for this Shape
        master_shape = master_page._children()[0]  # there's always a single master shape in a master page

        if self.master_shape_ID is not None:
            return master_shape.descendants.by_id(self.master_shape_ID)

        return master_shape

    @property
    def master_page(self) -> PageView | None:
        """This shape's master page, typed as a :class:`PageView`, or None."""
        if self.master_page_ID is None:
            return None
        return self._page._master_by_id(self.master_page_ID)

    @property
    def data_properties(self) -> dict[str, DataProperty]:
        """
        Get data properties of the shape - which labels, names, and values
        returns a dictionary of DataProperty objects indexed by property label

        Read from the XML on every call, so a property added, removed or
        relabelled - through this Shape object, another one for the same
        shape, or the XML itself - is in the next dictionary.

        Writing through an inherited property is safe: the property is marked
        inherited, so :attr:`DataProperty.value` and
        :meth:`DataProperty.set_attribute` give this shape an override row and
        leave the master alone. An override row replaces the master's property
        of the same name, under the label it now shows, so a property
        relabelled on this shape is listed once.

        :return: Dict[str, DataProperty]
        """
        self._require_attached("reading a shape's data properties")
        properties_xml = self.xml.find(f'{namespace}Section[@N="Property"]')
        property_rows: list[Element] = [] if properties_xml is None else properties_xml.findall(f"{namespace}Row")
        # marked copies, so neither this shape's rows nor a write through an
        # inherited property reaches what the master hands back
        master = self.master_shape
        properties: dict[str, DataProperty] = (
            {label: prop._inherited_by(self) for label, prop in master.data_properties.items()} if master is not None else {}
        )
        for prop in property_rows:
            data_prop = DataProperty(xml=prop, shape=self)
            # a property row without a Label cell, of its own or its master's,
            # keys under ""
            label = data_prop.label or ""
            if data_prop.name is not None:
                # Visio matches an override to its master's row by N, so the
                # master's property of that name is this one, whatever label
                # this row now gives it
                replaced = [key for key, seen in properties.items() if seen.inherited and seen.name == data_prop.name]
                for key in replaced:
                    if key != label:
                        del properties[key]
            properties[label] = data_prop
        return properties

    @property
    def cells(self) -> dict[str, Cell]:
        """This shape's own cells by name, read from its XML on every call.

        A top-level cell keys by its name, a Geometry row's cell by
        ``Geometry/{row type}/{name}`` and a Control row's by
        ``Control/{row name}/{name}``. A cell the shape inherits from its
        master is not here; :meth:`cell_value` and :meth:`cell_formula` look
        there too.

        The dictionary is built afresh, so a cell added through another Shape
        object for this shape, or straight to the XML, is in the next one.
        Changing the dictionary writes nothing.
        """
        self._require_attached("reading a shape's cells")
        return {name: Cell(xml=element, shape=self) for name, element in self._cell_elements()}

    def _cell_elements(self) -> Iterator[tuple[str, Element]]:
        """This shape's own cell elements, each with the name :attr:`cells` keys it under.

        A name can come round twice; the later element is the one that counts.
        """
        for element in self.xml.iterfind(f"{namespace}Cell"):
            name = element.get("N")
            if name is not None:
                yield name, element
        for section_name, row_key in (("Geometry", "T"), ("Control", "N")):
            section = self.xml.find(f'{namespace}Section[@N="{section_name}"]')
            if section is None:
                continue
            for row in section.iterfind(f"{namespace}Row"):
                row_name = row.get(row_key)
                if not row_name:
                    continue
                for element in row.iterfind(f"{namespace}Cell"):
                    name = element.get("N")
                    if name is not None:
                        yield f"{section_name}/{row_name}/{name}", element

    def _cell(self, name: str) -> Cell | None:
        """This shape's own cell `name`, as :attr:`cells` would key it, or ``None``.

        A plain name, the common case, is found among the top-level cells
        without reading the sections.
        """
        found = None
        if "/" in name:
            for key, element in self._cell_elements():
                if key == name:
                    found = element
        else:
            for element in self.xml.iterfind(f"{namespace}Cell"):
                if element.get("N") == name:
                    found = element
        return None if found is None else Cell(xml=found, shape=self)

    def cell_value(self, name: str) -> str | None:
        """The value of cell ``name``: this shape's own, else its master's; ``None`` where neither has the cell.

        ``name`` takes the forms :attr:`cells` keys by, such as ``PinX`` or
        ``Geometry/MoveTo/X``. A cell of the shape's own that has no value
        answers ``None`` without looking at the master.

        :raises InvalidOperationError: if the shape is detached
        """
        self._require_attached(f"reading cell {name}")
        cell = self._cell(name)
        if cell:
            return cell.value

        if self.master_page_ID is not None:
            master = self.master_shape
            if master is not None:
                return master.cell_value(name)
        return None

    def cell_formula(self, name: str) -> str | None:
        """The formula of cell ``name``: this shape's own, else its master's; ``None`` where neither has the cell.

        ``name`` is as :meth:`cell_value` takes it. A cell of the shape's own
        that has no formula answers ``None`` without looking at the master.

        :raises InvalidOperationError: if the shape is detached
        """
        self._require_attached(f"reading cell {name}")
        cell = self._cell(name)
        if cell:
            return cell.formula

        if self.master_page_ID is not None:
            master = self.master_shape
            if master is not None:
                return master.cell_formula(name)
        return None

    def _write_cell(self, name: str, *, v: str | None = None, f: str | None = None, keep_formula: bool = False) -> Cell:
        """Set cell `name`'s value or formula, and return the cell: the one function that creates or updates a shape's named cell.

        A value written without a formula replaces the cell's formula, as
        typing a number into the ShapeSheet does in Visio, unless
        `keep_formula` says the value is the one the formula gives: the glue
        engine's writes, the formula cache, and a 1-D shape's cells derived
        from its ends. A formula given is written, and a value beside it keeps
        it.

        A top-level cell the shape lacks is created, as a copy of the master's
        where the master has one, so its unit and other attributes carry over.
        A name holding ``/`` is a cell of a section row, such as
        ``Control/TextPosition/X``; it is written only where the shape has that
        cell of its own.

        :raises InvalidOperationError: if the shape is detached, or `name` is a
            section cell the shape does not have
        """
        # nearly every coordinate, size and colour setter arrives here, so one
        # guard covers them all; the message describes the write because which
        # setter the caller used is not knowable from here (issue #329)
        self._require_attached(f"writing shape cell {name!r}")
        cell = self._cell(name)
        if cell is None:
            if "/" in name:
                section, _, rest = name.partition("/")
                raise InvalidOperationError(
                    f"shape ID {self.ID} has no {section} cell {rest!r} of its own to write; "
                    "a cell in a section row is written only where the shape has that row and cell"
                )
            cell = Cell(xml=self._new_cell_element(name), shape=self)
        if f is not None:
            cell.formula = f
        if v is not None:
            cell._set_value(v, keep_formula=keep_formula or f is not None)
        return cell

    def _new_cell_element(self, name: str) -> Element:
        """A new top-level cell `name` among the shape's cells: a copy of its master's, formula and all, where the master has one."""
        master = self.master_shape
        master_cell = None if master is None else master.xml.find(f'{namespace}Cell[@N="{name}"]')
        if master_cell is not None:
            _logger.debug("creating cell from: %s", ET.tostring(master_cell))
        element = make_cell_element(name) if master_cell is None else ET.fromstring(ET.tostring(master_cell))
        # schema order: a shape's cells come before its Text and Sections
        cells = self.xml.findall(f"{namespace}Cell")
        self.xml.insert(list(self.xml).index(cells[-1]) + 1 if cells else 0, element)
        return element

    def set_cell_value(self, name: str, value: float | str) -> None:
        """Set a named cell's value, creating the cell if absent.

        A value without a formula replaces the cell's formula, as typing a
        number into the ShapeSheet does in Visio. A name holding ``/`` is a
        cell of a section row, such as ``Control/TextPosition/X``; it is
        refused where the shape does not have that row and cell of its own,
        rather than created at the shape's top level.

        :raises InvalidOperationError: if the shape is detached, or `name` is a
            section cell the shape does not have
        """
        self._write_cell(name, v=xml_value(value))

    def set_cell_formula(self, name: str, value: str) -> None:
        """Set a named cell's formula, creating the cell if absent.

        A name holding ``/`` is refused where the shape does not have that
        section cell of its own, as :meth:`set_cell_value` refuses it.

        :raises InvalidOperationError: if the shape is detached, or `name` is a
            section cell the shape does not have
        """
        self._write_cell(name, f=value)

    def _write_style_attribute(self, attribute: str, value: str | int) -> None:
        """Set one of the style references a Shape element carries as an attribute.

        LineStyle, FillStyle and TextStyle are attributes of the Shape element
        rather than cells, so they do not pass through :meth:`_write_cell` and
        need the detached-shape guard of their own (issue #329).
        """
        self._require_attached(f"writing shape attribute {attribute!r}")
        self.xml.attrib[attribute] = str(value)

    @property
    def line_style_id(self) -> str | None:
        """The ID of the style the shape's line takes, its ``LineStyle`` attribute; ``None`` where it has none of its own.

        Setting it takes an ID as a ``str`` or an ``int``, and does not check
        that the document has a style of that ID.
        """
        return self.xml.attrib.get("LineStyle")

    @line_style_id.setter
    def line_style_id(self, value: str | int) -> None:
        self._write_style_attribute("LineStyle", value)

    @property
    def fill_style_id(self) -> str | None:
        """The ID of the style the shape's fill takes, its ``FillStyle`` attribute; ``None`` where it has none of its own.

        Setting it takes what :attr:`line_style_id` takes.
        """
        return self.xml.attrib.get("FillStyle")

    @fill_style_id.setter
    def fill_style_id(self, value: str | int) -> None:
        self._write_style_attribute("FillStyle", value)

    @property
    def text_style_id(self) -> str | None:
        """The ID of the style the shape's text takes, its ``TextStyle`` attribute; ``None`` where it has none of its own.

        Setting it takes what :attr:`line_style_id` takes.
        """
        return self.xml.attrib.get("TextStyle")

    @text_style_id.setter
    def text_style_id(self, value: str | int) -> None:
        self._write_style_attribute("TextStyle", value)

    @property
    def line_weight(self) -> float | None:
        """The thickness of the shape's line, in inches, from its ``LineWeight`` cell or its master's; ``None`` where neither has one.

        Setting it writes the cell's value: a number, or a string written as
        it stands, and replaces the cell's formula, as typing a number into
        the ShapeSheet does in Visio.

        :raises MalformedPackageError: if the ``LineWeight`` value is not a number
        """
        val = self.cell_value("LineWeight")
        return to_float(val, cell="LineWeight")

    @line_weight.setter
    def line_weight(self, value: float | str) -> float | None:
        self.set_cell_value("LineWeight", xml_value(value))

    @property
    def line_color(self) -> str | None:
        """The colour of the shape's line, from its ``LineColor`` cell or its master's; ``None`` where neither has one.

        It is the text the file holds, such as ``#FF0000`` or an index into
        the document's colours. Setting it writes the cell's value as it
        stands, and replaces the cell's formula, as typing a number into the
        ShapeSheet does in Visio.
        """
        return self.cell_value("LineColor")

    @line_color.setter
    def line_color(self, value: str) -> None:
        self.set_cell_value("LineColor", xml_value(value))

    @property
    def fill_color(self) -> str | None:
        """The shape's fill colour, from its ``FillForegnd`` cell or its master's; ``None`` where neither has one.

        It takes and gives what :attr:`line_color` does.
        """
        return self.cell_value("FillForegnd")

    @fill_color.setter
    def fill_color(self, value: str) -> None:
        self.set_cell_value("FillForegnd", xml_value(value))

    def _character_row_index(self) -> str:
        """The Character row that formats the start of this shape's text.

        A `cp` run names the row for the text that follows it, so text sitting
        ahead of the first run - or a shape with no runs at all - takes row 0.
        Writing into whichever row happens to come first in the section is how
        a colour lands on a run nobody can see: `s05_swimlanes_cfflow.vsdx`
        shape 37 has a single row IX=1, which formats only the empty tail after
        its second run.
        """
        text = self.xml.find(f"{namespace}Text")
        if text is None or text.text:
            return "0"
        run = text.find(f"{namespace}cp")
        return run.attrib.get("IX", "0") if run is not None else "0"

    def _character_color_cell(self) -> Element | None:
        """The Color cell that formats this shape's text, or None."""
        section = self.xml.find(f'{namespace}Section[@N="Character"]')
        row = self._character_row(section) if section is not None else None
        return row.find(f'{namespace}Cell[@N="Color"]') if row is not None else None

    def _character_row(self, section: Element) -> Element | None:
        """The row of `section` that `_character_row_index` names, which formats the start of the text; None where there is none."""
        index = self._character_row_index()
        for row in section.findall(f"{namespace}Row"):
            if row.attrib.get("IX", "0") == index:
                return row
        return None

    def _create_character_color_cell(self) -> Element:
        """Give the shape a Character row carrying a Color cell.

        Text colour lives in a section rather than in a plain cell, which is
        why it did not go through :meth:`_write_cell` and why it alone among
        the colour setters used to write nothing at all on a shape that had no
        such row -- fifteen of the seventeen shapes on page 1 of test1,
        test12_colors and test3_house.

        The row is only half of it. A Character row formats the run that names
        it, so the row has to carry the index the text actually asks for, and
        text with no run at all needs one writing.
        """
        section = self.xml.find(f'{namespace}Section[@N="Character"]')
        if section is None:
            section = Element(f"{namespace}Section", {"N": "Character"})
            self._insert_section(section)
        row = self._character_row(section)
        if row is None:
            row = Element(f"{namespace}Row", {"IX": self._character_row_index()})
            insert_row_in_index_order(section, row)
        cell = make_cell_element("Color")
        row.append(cell)
        self._name_character_row_in_text(row.attrib.get("IX", "0"))
        return cell

    def _insert_section(self, section: Element) -> None:
        """Put a new section where Visio writes one.

        A section belongs to the run of Cell, Trigger and Section children that
        opens a shape, ahead of its Text and its Shapes. Geometry closes that
        run: no section in this repository's fixtures is written after it,
        while Text is (connectors in test5_master carry Geometry last), so
        Geometry rather than Text is the marker to stop at. Appending to the
        shape instead puts the section after a group's `Shapes` child, which
        Visio never does.
        """
        insert_at = 0
        for index, child in enumerate(self.xml):
            if child.tag == f"{namespace}Section" and child.attrib.get("N") == "Geometry":
                insert_at = index
                break
            if child.tag in (f"{namespace}Cell", f"{namespace}Trigger", f"{namespace}Section"):
                insert_at = index + 1
        self.xml.insert(insert_at, section)

    def _name_character_row_in_text(self, row_index: str) -> None:
        """Open the shape's text with a run that names a Character row.

        Only when the text carries no runs at all, in which case the row is
        index 0 and this is the run Visio would have written beside it. Text
        that already has runs named the row this wrote into, by construction.
        A shape with no Text element of its own has no run to write here; its
        text comes from its master.
        """
        text = self.xml.find(f"{namespace}Text")
        if text is None or text.find(f"{namespace}cp") is not None:
            return
        run = Element(f"{namespace}cp", {"IX": row_index})
        run.tail = text.text
        text.text = None
        text.insert(0, run)

    @property
    def text_color(self) -> str | None:
        """Get text color of shape - the colour formatting the start of its text.

        Setting it writes the colour and removes the cell's formula, as :attr:`line_color` does.
        """
        cell = self._character_color_cell()
        return cell.attrib.get("V") if cell is not None else None

    @text_color.setter
    def text_color(self, value: str | int) -> None:
        """Set text color of shape - the colour formatting the start of its text"""
        # text colour lives in a Character section row, not in a cell, so it
        # does not reach the _write_cell guard
        self._require_attached("writing a shape's text colour")
        # coerced before anything is created: a rejected value used to leave a
        # Character row and a text run behind and then raise
        text = xml_value(value)
        cell = self._character_color_cell()
        if cell is None:
            cell = self._create_character_color_cell()
        cell.attrib["V"] = text
        cell.attrib.pop("F", None)  # the value is the one Visio shows (#300)

    @property
    def end_arrow(self) -> str | None:
        """The arrowhead at the line's end, from its ``EndArrow`` cell or its master's; ``None`` where neither has one.

        It is the text the file holds: an arrowhead's index, ``"0"`` for none.
        Setting it takes an index, or ``True`` for arrowhead 13 and ``False``
        for none.
        """
        return self.cell_value("EndArrow")

    @end_arrow.setter
    def end_arrow(self, value: int) -> None:
        if value is True:
            value = 13  # 13 is standard arrow
        if value is False:
            value = 0  # no arrow
        self.set_cell_value("EndArrow", xml_value(value))

    @property
    def x(self) -> float | None:
        """The x of the shape's pin, in inches from its parent's left edge; ``None`` where neither the shape nor its master has a ``PinX`` cell.

        The pin is the point the shape rotates about, usually its centre.
        Setting it moves the shape: it writes the cell's value, a number or a
        string written as it stands, and replaces the cell's formula, as
        typing a number into the ShapeSheet does in Visio. ``None`` raises
        :class:`TypeError`.

        :raises MalformedPackageError: if the ``PinX`` value is not a number
        """
        return to_float(self.cell_value("PinX"), cell="PinX")

    @x.setter
    def x(self, value: float | str) -> None:
        self.set_cell_value("PinX", _coordinate_value(value))

    @property
    def y(self) -> float | None:
        """The y of the shape's pin, in inches from its parent's bottom edge; ``None`` where neither the shape nor its master has a ``PinY`` cell.

        Setting it writes the cell's value, as :attr:`x` does.

        :raises MalformedPackageError: if the ``PinY`` value is not a number
        """
        return to_float(self.cell_value("PinY"), cell="PinY")

    @y.setter
    def y(self, value: float | str) -> None:
        self.set_cell_value("PinY", _coordinate_value(value))

    @property
    def loc_x(self) -> float | None:
        """The x of the pin in the shape's own coordinates, in inches from its left edge; ``None`` where neither the shape nor its master has a ``LocPinX`` cell.

        Setting it writes the cell's value, as :attr:`x` does.

        :raises MalformedPackageError: if the ``LocPinX`` value is not a number
        """
        return to_float(self.cell_value("LocPinX"), cell="LocPinX")

    @loc_x.setter
    def loc_x(self, value: float | str) -> None:
        self.set_cell_value("LocPinX", _coordinate_value(value))

    @property
    def loc_y(self) -> float | None:
        """The y of the pin in the shape's own coordinates, in inches from its bottom edge; ``None`` where neither the shape nor its master has a ``LocPinY`` cell.

        Setting it writes the cell's value, as :attr:`x` does.

        :raises MalformedPackageError: if the ``LocPinY`` value is not a number
        """
        return to_float(self.cell_value("LocPinY"), cell="LocPinY")

    @loc_y.setter
    def loc_y(self, value: float | str) -> None:
        self.set_cell_value("LocPinY", _coordinate_value(value))

    @property
    def begin_x(self) -> float | None:
        """The x of a 1-D shape's begin point, in inches in its parent's coordinates; ``None`` where neither the shape nor its master has a ``BeginX`` cell, as on a 2-D shape.

        Setting it writes the cell's value, as :attr:`x` does. A glued begin
        end is freed first: its ``Connect`` record, trigger and glue formulas
        go, as dragging the end away does in Visio. The other end stays
        glued.

        :raises MalformedPackageError: if the ``BeginX`` value is not a number
        """
        return to_float(self.cell_value("BeginX"), cell="BeginX")

    @begin_x.setter
    def begin_x(self, value: float | str) -> None:
        self._write_end("BeginX", value)

    @property
    def begin_y(self) -> float | None:
        """The y of a 1-D shape's begin point, in inches in its parent's coordinates; ``None`` where neither the shape nor its master has a ``BeginY`` cell.

        Setting it writes the cell's value, as :attr:`begin_x` does, for its end.

        :raises MalformedPackageError: if the ``BeginY`` value is not a number
        """
        return to_float(self.cell_value("BeginY"), cell="BeginY")

    @begin_y.setter
    def begin_y(self, value: float | str) -> None:
        self._write_end("BeginY", value)

    @property
    def end_x(self) -> float | None:
        """The x of a 1-D shape's end point, in inches in its parent's coordinates; ``None`` where neither the shape nor its master has an ``EndX`` cell.

        Setting it writes the cell's value, as :attr:`begin_x` does, for its end.

        :raises MalformedPackageError: if the ``EndX`` value is not a number
        """
        return to_float(self.cell_value("EndX"), cell="EndX")

    @end_x.setter
    def end_x(self, value: float | str) -> None:
        self._write_end("EndX", value)

    @property
    def end_y(self) -> float | None:
        """The y of a 1-D shape's end point, in inches in its parent's coordinates; ``None`` where neither the shape nor its master has an ``EndY`` cell.

        Setting it writes the cell's value, as :attr:`begin_x` does, for its end.

        :raises MalformedPackageError: if the ``EndY`` value is not a number
        """
        return to_float(self.cell_value("EndY"), cell="EndY")

    @end_y.setter
    def end_y(self, value: float | str) -> None:
        self._write_end("EndY", value)

    def _write_end(self, name: str, value: float | str) -> None:
        """Write end coordinate `name`, freeing that end first if it is glued, as dragging a glued end away does in Visio.

        The value is converted before the end is freed, so a value refused
        leaves the end glued, as it was.
        """
        self._require_attached(f"writing shape cell {name!r}")
        coordinate = _coordinate_value(value)
        begin = name.startswith("Begin")
        end_cell = "BeginX" if begin else "EndX"
        if any(record.from_id == self.ID and record.from_rel == end_cell for record in self._page._connects()):
            _float_end(self, begin=begin)
        self.set_cell_value(name, coordinate)

    def move(self, x_delta: float, y_delta: float) -> None:
        """Move the shape by ``x_delta`` and ``y_delta`` inches.

        A 2-D shape moves by its pin, and the value written replaces a
        formula the pin had, as dragging the shape does in Visio. A pin the
        shape lacks is taken as 0, and written. A 1-D shape moves by its two
        ends, which frees an end that was glued; its pin, width and angle are
        formulas of its ends, and follow them. The geometry is in the shape's
        own coordinates, so it is not touched. A move by zero in both
        directions changes nothing: a glued end stays glued, and a pin
        formula stays.

        :raises InvalidOperationError: if the shape is detached, or it is a
            1-D shape missing one of its ends, moved by more than zero; place
            such a shape by its ends with :meth:`set_start_and_finish`
        """
        self._require_attached("Shape.move()")
        if x_delta == 0 and y_delta == 0:
            return  # moving by nothing must not free glue or replace formulas
        if not _is_connector(self):
            self.x = (self.x or 0.0) + x_delta
            self.y = (self.y or 0.0) + y_delta
            return
        begin_x, begin_y, end_x, end_y = self.begin_x, self.begin_y, self.end_x, self.end_y
        if begin_x is None or begin_y is None or end_x is None or end_y is None:
            ends = {"BeginX": begin_x, "BeginY": begin_y, "EndX": end_x, "EndY": end_y}
            missing = ", ".join(name for name, value in ends.items() if value is None)
            raise InvalidOperationError(
                f"shape ID {self.ID} is 1-D but has no {missing} value to move; "
                "place it by its ends with set_start_and_finish()"
            )
        self.begin_x, self.begin_y = begin_x + x_delta, begin_y + y_delta
        self.end_x, self.end_y = end_x + x_delta, end_y + y_delta
        # derived from the ends: written as the library writes them, so a
        # formula stays and the refresh below gives it the new ends' value
        self._write_cell("PinX", v=xml_value((self.x or 0.0) + x_delta), keep_formula=True)
        self._write_cell("PinY", v=xml_value((self.y or 0.0) + y_delta), keep_formula=True)
        self._refresh_formula_values()

    def get_or_create_cell(self, name: str, v: str | None = None, f: str | None = None) -> Cell:
        """Set or create a named cell on this shape, through :meth:`_write_cell`.

        Existing cells have their V/F attributes updated in place. New cells
        are inserted after the last direct Cell child so the shape keeps the
        schema ordering (cells ahead of Text/Sections). A value without a
        formula replaces the cell's formula, as typing a number into the
        ShapeSheet does in Visio.

        :param name: cell name (N attribute), e.g. 'PinX'
        :param v: value to set on the V attribute (optional)
        :param f: formula to set on the F attribute (optional)
        :return: the Cell object
        """
        return self._write_cell(name, v=v, f=f)

    @property
    def height(self) -> float | None:
        """The shape's height, in inches; ``None`` where neither the shape nor its master has a ``Height`` cell.

        Setting it writes the cell's value, as :attr:`x` does; the geometry
        is left as it was.

        :raises MalformedPackageError: if the ``Height`` value is not a number
        """
        return to_float(self.cell_value("Height"), cell="Height")

    @height.setter
    def height(self, value: float | str) -> float | None:
        self.set_cell_value("Height", _coordinate_value(value))

    @property
    def width(self) -> float | None:
        """The shape's width, in inches, which for a 1-D shape is its length; ``None`` where neither the shape nor its master has a ``Width`` cell.

        Setting it writes the cell's value, as :attr:`height` does.

        :raises MalformedPackageError: if the ``Width`` value is not a number
        """
        return to_float(self.cell_value("Width"), cell="Width")

    @width.setter
    def width(self, value: float | str) -> float | None:
        self.set_cell_value("Width", _coordinate_value(value))

    @property
    def angle(self) -> float | None:
        """The shape's rotation about its pin, in radians, anticlockwise; ``None`` where neither the shape nor its master has an ``Angle`` cell.

        Setting it writes the cell's value, as :attr:`x` does.

        :raises MalformedPackageError: if the ``Angle`` value is not a number
        """
        return to_float(self.cell_value("Angle"), cell="Angle")

    @angle.setter
    def angle(self, value: float | str) -> None:
        self.set_cell_value("Angle", _coordinate_value(value))

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """The shape's extent as ``(x0, y0, x1, y1)``, in inches in its parent's coordinates.

        For a 1-D shape these are its begin and end points, in that order, so
        ``x0`` may be greater than ``x1``. For a 2-D shape they are its pin
        less its local pin, and that corner plus its width and height; the
        rotation is not applied. A missing cell counts as 0, and a shape with
        none of ``BeginX``, ``PinX`` and ``LocPinX`` gives four zeros.
        """
        # the extent in the parent's coordinates: the page's only for a top-level shape
        s = self
        if s.begin_x is None and s.x is None and s.loc_x is None:
            return 0.0, 0.0, 0.0, 0.0  # shape has no bounds
        bx = s.begin_x if s.begin_x is not None else (s.x or 0.0) - (s.loc_x or 0.0)
        by = s.begin_y if s.begin_y is not None else (s.y or 0.0) - (s.loc_y or 0.0)
        ex = s.end_x if s.end_x is not None else bx + (s.width or 0.0)
        ey = s.end_y if s.end_y is not None else by + (s.height or 0.0)

        return bx, by, ex, ey

    @property
    def relative_bounds(self) -> tuple[float, float, float, float]:
        """The shape's :attr:`bounds`, shifted by its group's ``x0`` and ``y0`` when it sits in a group.

        That puts a group member's extent in the coordinates the group sits
        in: the page's, for a member of a top-level group. Only the one group
        is added, so a shape two groups deep is not brought to the page. A
        shape outside any group gives its :attr:`bounds` unchanged.
        """
        # a group member's bounds are in the group's coordinates; adding the
        # group's corner puts them in the coordinates the group sits in
        bx, by, ex, ey = self.bounds
        if isinstance(self._parent, Shape) and self._parent.shape_type == "Group":
            pbx, pby, _pex, _pey = self._parent.bounds
            bx += pbx
            by += pby
            ex += pbx
            ey += pby

        return bx, by, ex, ey

    @property
    def center_x_y(self) -> tuple[float | None, float | None]:
        """A centre for the shape as ``(x, y)``, in inches in its parent's coordinates.

        For a 2-D shape it is the pin, either half ``None`` where that cell
        is missing. For a 1-D shape it is the begin point plus half the
        width and half the height, a missing cell counting as 0.
        """
        if self.begin_x is not None:
            x = self.begin_x + ((self.width or 0.0) / 2)
            y = (self.begin_y or 0.0) + ((self.height or 0.0) / 2)
        else:
            x = self.x
            y = self.y
        return x, y

    def set_start_and_finish(
        self, start: tuple[float | None, float | None], finish: tuple[float | None, float | None]
    ) -> None:
        """Place a line or connector by its two ends, and draw it between them.

        Writing an end frees it if it is glued, as dragging it away does in
        Visio; :meth:`Connector.retarget` glues an end to another shape. The
        pin, width, height and angle follow the ends: where they are formulas
        of the ends, the formulas stay, and their values are refreshed. A
        plain line with no ``Angle`` formula is placed as Visio's own lines
        are: as long as its ends are apart, with no height, turned to point
        from start to finish, and pinned at its middle. The text pin is at
        the middle of the width and height the shape is then drawn with, in
        its own coordinates.

        :raises InvalidOperationError: if the shape is detached, it is a 2-D shape, or a coordinate is ``None``
        """
        # nothing at all is written on a shape with no BeginX, so leaving this
        # to the coordinate setters below would make the refusal depend on the
        # shape it was asked of
        self._require_attached("Shape.set_start_and_finish()")
        self._place_ends(start, finish, keep_glue=False)

    def _place_ends(
        self, start: tuple[float | None, float | None], finish: tuple[float | None, float | None], *, keep_glue: bool
    ) -> None:
        """Place a 1-D shape by its ends: the body of :meth:`set_start_and_finish`.

        The glue engine calls it with `keep_glue`, to put the ends it has just
        glued where they render before Visio recalculates, leaving their glue
        formulas and records in place. Without it, the end setters write the
        ends, and free a glued one.
        """
        if not _is_connector(self):
            raise InvalidOperationError(
                f"shape ID {self.ID} is 2-D, so it has no start and finish; move it with move(), or x and y"
            )
        start_x, start_y = start
        finish_x, finish_y = finish
        if start_x is None or start_y is None or finish_x is None or finish_y is None:
            raise InvalidOperationError(
                f"shape ID {self.ID}: start and finish coordinates cannot be None; give a number for each of the four"
            )
        # lines/connectors are defined in different ways
        # Check whether shape is a connector based on name in known languages,
        # a second connector on the page included: Visio names it
        # `Dynamic connector.58`
        is_connector = _is_name_or_copy(self.universal_name, "Dynamic connector")
        # worked out before anything is written, so a coordinate that is
        # not a number is refused with the shape, and its glue, as it was
        span_x, span_y = finish_x - start_x, finish_y - start_y
        # A plain line runs along its own x axis, turned by its Angle. Where
        # an Angle formula holds the angle, the formulas place the line: an
        # ATAN2(...) turns it, as Visio's own lines do (test9 'Line A'), and
        # a connector's GUARD(0DA) keeps it square, with its spans for its
        # size; the values written below are refreshed from them. A line
        # with no Angle formula, as a Lucidchart line has, is placed here.
        turned = not is_connector and self.cell_formula("Angle") is None
        if turned:
            # as long as its ends are apart, with no height, pointing from
            # start to finish, and pinned at its middle: what Visio's SQRT(...),
            # ATAN2(...) and (BeginX+EndX)/2 give its own lines
            width, height = math.hypot(span_x, span_y), 0.0
            pin_x, pin_y = (start_x + finish_x) / 2, (start_y + finish_y) / 2
        else:
            # a dynamic connector's height is its y span; a plain line's is 0
            width, height = span_x, span_y if is_connector else 0.0
            pin_x, pin_y = start_x, start_y

        if keep_glue:
            for name, value in (("BeginX", start_x), ("BeginY", start_y), ("EndX", finish_x), ("EndY", finish_y)):
                self._write_cell(name, v=xml_value(value), keep_formula=True)
        else:
            self.begin_x, self.begin_y = start_x, start_y
            self.end_x, self.end_y = finish_x, finish_y
        self._write_cell("Width", v=xml_value(width), keep_formula=True)
        self._write_cell("Height", v=xml_value(height), keep_formula=True)
        if turned:
            self._write_cell("Angle", v=xml_value(math.atan2(span_y, span_x)), keep_formula=True)
        self._write_cell("PinX", v=xml_value(pin_x), keep_formula=True)
        self._write_cell("PinY", v=xml_value(pin_y), keep_formula=True)
        # the geometry and the text pin follow the width and height the shape
        # is drawn with, which a formula of the ends, such as a GUARD(EndY-BeginY)
        # height, gives only once it is refreshed
        self._refresh_formula_values()
        drawn_width, drawn_height = self.width, self.height
        # both were written above, and a refresh writes only numbers
        assert drawn_width is not None and drawn_height is not None
        if self.geometry is not None:
            self.geometry._set_point("moveto", "Shape.set_start_and_finish()", 0.0, 0.0, 0, keep_formula=True)
            self.geometry._set_point("lineto", "Shape.set_start_and_finish()", drawn_width, drawn_height, 0, keep_formula=True)
        txt_pin_x = self._cell("TxtPinX")
        txt_pin_y = self._cell("TxtPinY")
        if txt_pin_x and txt_pin_y:
            text_x, text_y = drawn_width / 2, drawn_height / 2
            txt_pin_x._set_value(text_x, keep_formula=True)
            txt_pin_y._set_value(text_y, keep_formula=True)
            # Visio's Controls row names its anchor cells XDyn and YDyn,
            # not DynX/DynY; a shape without a TextPosition row of its own
            # is left alone rather than given stray top-level cells
            for cell_name, value in (("X", text_x), ("Y", text_y), ("XDyn", text_x), ("YDyn", text_y)):
                if self._cell(f"Control/TextPosition/{cell_name}") is not None:
                    self._write_cell(f"Control/TextPosition/{cell_name}", v=xml_value(value), keep_formula=True)
        self._refresh_formula_values()

    def _refresh_formula_values(self) -> None:
        """Recompute the value held beside each formula this shape's cells carry, as Visio would on open.

        A formula this library cannot evaluate keeps the value it had.
        A cell the shape only inherits is left alone: it is the master's, and Visio recomputes it for this shape on open.
        """
        cells: list[Cell | GeometryCell] = list(self.cells.values())
        if self.geometry is not None:
            cells.extend(self.geometry.cells)
            for r in self.geometry.rows.values():
                cells.extend(r.cells.values())
        own = set(self.xml.iter(f"{namespace}Cell"))
        for c in cells:
            if c.xml not in own:
                continue  # a cell only inherited is the master's; Visio recomputes it for this instance on open
            formula = c.formula
            if formula and c.name is not None:
                master = self.master_shape
                if formula == "Inh" and master is not None:
                    master_c = master._cell(c.name)
                    formula = master_c.formula if master_c else formula
                if formula is None:
                    continue
                v = calc_value(self, formula)
                if v is not None:
                    c._set_value(v, keep_formula=True)

    def _text_runs(self) -> tuple[list[Element], str, list[Element], str]:
        """This shape's text, split by `_text_runs_of`, with master inheritance applied.

        Inheritance is the part only a Shape can resolve: a shape with no Text
        element of its own shows its master's text, and inherits none of the
        master's formatting runs.
        """
        text_element = self.xml.find(f"{namespace}Text")
        if not isinstance(text_element, Element) and self.master_page_ID:
            master = self.master_shape
            if master is not None and master.text:
                return [], master.text, [], ""
        return _text_runs_of(text_element)

    @property
    def text(self) -> str:
        """The shape's text, without the formatting runs at its start and end or the newline Visio closes it with.

        A shape with no ``Text`` element of its own shows its master's text,
        and ``""`` where the master has none either. Setting it takes a string, writes it as
        the shape's own text and puts back the runs at its start and end. A
        run between two pieces of text is read as its XML markup, and written
        back as literal text (#317).

        Reading or setting it raises :class:`~vsdxkit.errors.InvalidOperationError` once the
        shape is detached.
        """
        self._require_attached("reading a shape's text")
        return self._text_runs()[1]

    @text.setter
    def text(self, value: str) -> None:
        self._require_attached("writing a shape's text")
        prefix, _, suffix, trailing = self._text_runs()
        _write_text(self.xml, value, prefix=prefix, suffix=suffix, trailing=trailing)

    @property
    def children(self) -> ShapeCollection:
        """The shapes directly inside this one: a group's members, or none."""
        return ShapeCollection(self._children, self._scope)

    @property
    def descendants(self) -> ShapeCollection:
        """Every shape inside this one, at any depth, depth first and parents first."""
        return ShapeCollection(self._descendants, self._scope)

    def _scope(self) -> str:
        """How a collection of the shapes inside this one names its scope in a message: ``shape 5 on page 'Page-1'``."""
        return f"shape {self.ID} on page {self._page.name!r}"

    def _children(self) -> list[Shape]:
        """What :attr:`children` holds, as a list, for the library's own walks."""
        self._require_attached("reading a shape's children")
        return _wrap_children(self.xml, self, self._page)

    def _descendants(self) -> list[Shape]:
        """What :attr:`descendants` holds, as a list, for the library's own walks.

        Each is given the wrapper of the shape it sits in as its parent: a
        sub-shape with no ``Master`` of its own instances its group's.
        """
        self._require_attached("reading a shape's descendants")
        return _wrap_descendants(self.xml, self, self._page)

    def apply_text_filter(self, context: dict[str, object]) -> None:
        """Substitute `context` into the text of this shape and every shape inside it."""
        # a shape whose text has nothing to substitute never reaches the text
        # setter, so its guard alone would let this one through
        self._require_attached("Shape.apply_text_filter()")
        self._rewrite_texts(lambda text: _substitute(text, context))

    def find_replace(self, old: str, new: str) -> None:
        """Replace `old` with `new` in the text of this shape and every shape inside it."""
        self._require_attached("Shape.find_replace()")
        self._rewrite_texts(lambda text: text.replace(old, new))

    def _rewrite_texts(self, rewrite: Callable[[str], str]) -> None:
        """Pass the text of this shape and every shape inside it through `rewrite`, writing back only what changed.

        Writing back text that did not change is not free. A run between two
        pieces of content does not survive the round trip (#317), and a shape
        showing its master's text would gain a copy of it as its own. So a shape
        with nothing to change must not be altered by being visited.
        """
        for shape in (self, *self._descendants()):
            text = shape.text
            rewritten = rewrite(text)
            if rewritten != text:
                shape.text = rewritten

    def delete(self) -> None:
        """Delete this shape from its page, with every connector glued to it.

        A group takes its members with it, so a connector glued to a member goes
        too, and so does every ``Connect`` record naming any of them. A
        connector deleted directly takes only its own records. Afterwards this
        shape, and every shape held for one that went with it, is detached.

        :raises InvalidOperationError: if the shape is already detached
        """
        self._require_attached("deleting a shape")
        # every id about to disappear: the shape and, for a group, everything
        # it contains
        self._page._delete([self], {str(self.ID)} | {str(shape.ID) for shape in self._descendants()})

    def append_shape(self, append_shape: Shape) -> None:
        """Place another shape on this page inside this one, keeping the IDs it already has.

        A group holds its children in a ``<Shapes>`` container, created here
        when the group has none. Appending to the group's own ``<Shape>``
        element instead made the new shape a sibling of that container, which
        the schema does not allow and which this library's own traversal cannot
        see, neither through ``children`` nor through ``Page._descendants()``.

        A shape already on this page, such as a fresh ``shape.copy()``, is
        moved: its element is taken out of whatever held it first, so it never
        has two parents, and it keeps its IDs, so the ``Connect`` records
        naming it still hold. A shape on another page is refused; copy it
        onto this page first.

        :raises InvalidOperationError: if this shape is detached or is not a
            group, if ``append_shape`` is detached or is on another page, or
            if it would end up inside itself
        """
        # ahead of every check and every write, so a detached group refuses
        # before anything is moved into it
        self._require_attached("Shape.append_shape()")
        if not append_shape.is_attached:
            raise InvalidOperationError(
                f"shape ID {append_shape.ID} was deleted, or is on a removed page, so it cannot be placed; "
                "a deleted shape stays deleted"
            )
        if self.shape_type != "Group":
            raise InvalidOperationError(
                f"shape ID={self.ID} has type {self.shape_type!r} and cannot contain shapes; "
                "only a group shape holds sub-shapes"
            )
        if append_shape._page is not self._page:
            raise InvalidOperationError(
                f"shape ID={append_shape.ID} belongs to page {append_shape._page.name!r}, not {self._page.name!r}; "
                "use Shape.copy(page) to place a shape on another page"
            )
        # A shape already on this page is moved, not placed. Rejecting it would
        # leave no usable route: Shape.copy() attaches its clone to the
        # destination page, so `group.append_shape(other.copy())` -- the obvious
        # call, and the one the old error message recommended -- would raise.
        # Detaching first is also what stops the element gaining a second
        # parent, which is the problem the rejection existed to prevent.
        if any(element is self.xml for element in append_shape.xml.iter()):
            # Appending a shape into itself, or into something already inside
            # it, makes the element its own descendant: the page loses both
            # shapes (they are detached from the page and re-parented into each
            # other) and every walk of the subtree recurses forever. `a.append_
            # shape(b); b.append_shape(a)` is the way in.
            raise InvalidOperationError(
                f"shape ID={append_shape.ID} cannot be placed inside shape ID={self.ID}, "
                "which is the shape itself or one of the shapes inside it"
            )
        current_parent = parent_of(self._page.xml.getroot(), append_shape.xml)
        # append_shape.is_attached, checked above, and the page-identity check
        # just passed both mean its element is reachable from this page's
        # root by parent links; parent_of and is_attached both test that by
        # identity, so it always finds a parent here. A move keeps the ids
        # append_shape already has, or every Connect record naming it would
        # be left dangling.
        assert current_parent is not None
        current_parent.remove(append_shape.xml)
        # creates the <Shapes> element an empty group lacks
        container = find_or_create_shapes_tag(self.xml)
        container.append(append_shape.xml)
        # The ID follows the element on its own; the parent is the Shape
        # object's own state and nothing else updates it.
        append_shape._parent = self

    @property
    def connectors(self) -> tuple[Connector, ...]:
        """Every connector on the page glued to this shape at either end, in page order."""
        return tuple(connector for connector, _ in self._incidence())

    @property
    def connected_shapes(self) -> tuple[Shape, ...]:
        """The shape at the other end of each of :attr:`connectors`, each once, in connector order.

        A floating end leads nowhere, and a connector glued back to this shape
        leads nowhere else, so neither adds anything.
        """
        shapes: list[Shape] = []
        for _, ends in self._incidence():
            for end in ends:
                if end is not None and end != self and end not in shapes:
                    shapes.append(end)
        return tuple(shapes)

    def _incidence(self) -> list[tuple[Connector, tuple[Shape | None, Shape | None]]]:
        """Each connector glued to this shape, with the shapes its begin and end are glued to.

        One pass over the page's records and one walk of its shapes, however
        many connectors there are. Only a record from ``BeginX`` or ``EndX``
        glues an end.
        """
        self._require_attached("reading the connectors glued to a shape")
        ends: dict[str, dict[str, str]] = {}
        for record in self._page._connects():
            if record.from_rel in ("BeginX", "EndX"):
                ends.setdefault(record.from_id, {})[record.from_rel] = record.to_id
        glued = {connector_id for connector_id, named in ends.items() if self.ID in named.values()}
        if not glued:
            return []
        shapes = list(self._page.shapes)
        by_id: dict[str, list[Shape]] = {}
        for shape in shapes:
            if shape.ID is not None:
                by_id.setdefault(shape.ID, []).append(shape)

        def resolve(shape_id: str | None) -> Shape | None:
            """The one shape on the page with ID `shape_id`; None for a floating end or an ID no shape has.

            Two shapes with the ID raise PackageError, as `ShapeCollection.by_id` does.
            """
            # an end with no record is floating, whatever shapes lack an ID
            if shape_id is None:
                return None
            found = by_id.get(shape_id, [])
            if len(found) > 1:
                # as ShapeCollection.by_id reports it: a page with two shapes
                # of one ID is invalid, and neither is the one a record names
                raise PackageError(
                    f"page {self._page.name!r} holds {len(found)} shapes with ID {shape_id}; "
                    "shape IDs are unique on a page, so the page is not valid"
                )
            return found[0] if found else None

        resolve(self.ID)
        incidence: list[tuple[Connector, tuple[Shape | None, Shape | None]]] = []
        for connector_id in glued:
            connector = resolve(connector_id)
            if isinstance(connector, Connector):
                named = ends[connector_id]
                incidence.append((connector, (resolve(named.get("BeginX")), resolve(named.get("EndX")))))
        order = {shape: position for position, shape in enumerate(shapes)}
        return sorted(incidence, key=lambda item: order[item[0]])


class Connector(Shape):
    """A 1-D shape: a line whose ends can each be glued to a shape.

    It is a :class:`Shape` in every other respect. Which shape each end is
    glued to is read from the page's ``Connect`` records on each access.
    """

    @override
    def __repr__(self) -> str:
        """Shows what a :class:`Shape`'s repr shows, headed ``<Connector`` instead."""
        return super().__repr__().replace("<Shape ", "<Connector ", 1)

    @property
    def source(self) -> Shape | None:
        """The shape the connector's begin end is glued to, or None when that end is floating."""
        self._require_attached("Connector.source")
        begin, _ = _glued_ends(self)
        return None if begin is None else _as_shape(begin[0])

    @property
    def target(self) -> Shape | None:
        """The shape the connector's end is glued to, or None when that end is floating."""
        self._require_attached("Connector.target")
        _, end = _glued_ends(self)
        return None if end is None else _as_shape(end[0])

    def retarget(
        self,
        *,
        source: Shape | None = None,
        target: Shape | None = None,
        options: ConnectorOptions | None = None,
    ) -> None:
        """Glue one or both ends to other shapes on the page.

        An end not named stays where it is, floating if it was. Without
        ``options`` the connector keeps its glue and routing: a moved end
        keeps the connection point it had, and one that was floating or glued
        dynamically is glued dynamically. A connection point the new shape
        does not have is refused, never dropped for dynamic glue. ``options``
        replaces the glue and routing of both ends.

        Everything is checked before anything is written.

        :raises InvalidOperationError: neither end is named, a shape is not on
            the page, or a connection point does not exist
        """
        _retarget_connector(self, source, target, options)


class ShapeCollection:
    """A fixed scope of shapes, and the one way to look shapes up in it.

    The scope is a page's or a group's direct children, or everything below
    one, and it never changes. Iteration and every finder read the same
    members. The collection is live: each call walks its scope again, so a
    shape added or removed since the collection was taken is seen.

    Lookups say how many shapes they expect. ``by_*`` wants at most one and
    answers None for none; ``require_*`` wants exactly one and raises
    :class:`~vsdxkit.errors.NotFoundError` for none; both raise :class:`~vsdxkit.errors.InvalidOperationError`
    when several match, rather than choosing one. The exception is an ID:
    two shapes with one ID make the page invalid, so ``by_id`` and
    ``require_id`` raise :class:`~vsdxkit.errors.PackageError` for them. ``matching_*``
    returns every match.
    """

    def __init__(self, members: Callable[[], list[Shape]], scope: Callable[[], str]) -> None:
        """A collection that calls `members` afresh for every read, and names itself in messages with `scope`."""
        self._members = members
        self._scope = scope

    def __repr__(self) -> str:
        """Shows the scope, as ``<ShapeCollection page 'Page-1'>``."""
        return f"<ShapeCollection {self._scope()}>"

    def __iter__(self) -> Iterator[Shape]:
        """The shapes in scope now: the collection is read afresh on each iteration, so it sees shapes added since."""
        return iter(self._members())

    def __len__(self) -> int:
        """How many shapes are in scope now, walking the scope again to count them."""
        return len(self._members())

    def by_id(self, shape_id: str) -> Shape | None:
        """The shape with this page-scoped ID, or None.

        Two shapes with one ID make the page invalid, which is a
        :class:`~vsdxkit.errors.PackageError` rather than a choice between them.
        """
        matches = tuple(shape for shape in self._members() if shape_id == shape.ID)
        if len(matches) > 1:
            raise PackageError(
                f"{self._scope()} holds {len(matches)} shapes with ID {shape_id}; "
                "shape IDs are unique on a page, so the page is not valid"
            )
        return matches[0] if matches else None

    def require_id(self, shape_id: str) -> Shape:
        """The shape with this page-scoped ID."""
        return self._required(self.by_id(shape_id), f"ID {shape_id}")

    def matching_text(self, text: str) -> tuple[Shape, ...]:
        """Every shape whose text is `text`, exactly."""
        return tuple(shape for shape in self._members() if shape.text == text)

    def by_text(self, text: str) -> Shape | None:
        """The one shape whose text is `text`, exactly, or None."""
        return self._unique(self.matching_text(text), f"text {text!r}")

    def require_text(self, text: str) -> Shape:
        """The one shape whose text is `text`, exactly."""
        return self._required(self.by_text(text), f"text {text!r}")

    def matching_property(self, label: str, value: str | None = None) -> tuple[Shape, ...]:
        """Every shape with the Shape Data property labelled `label`, and with `value` where one is given.

        A property inherited from the shape's master counts. A value is
        compared as text, as Visio shows it.
        """
        return tuple(shape for shape in self._members() if _has_property(shape, label, value))

    def by_property(self, label: str, value: str | None = None) -> Shape | None:
        """The one shape with the property, as :meth:`matching_property` matches it, or None."""
        return self._unique(self.matching_property(label, value), _describe_property(label, value))

    def require_property(self, label: str, value: str | None = None) -> Shape:
        """The one shape with the property, as :meth:`matching_property` matches it."""
        return self._required(self.by_property(label, value), _describe_property(label, value))

    def _unique(self, matches: tuple[Shape, ...], wanted: str) -> Shape | None:
        """The one shape in `matches`, or None for none; several raise InvalidOperationError naming their IDs."""
        if len(matches) > 1:
            ids = ", ".join(str(shape.ID) for shape in matches)
            raise InvalidOperationError(
                f"{len(matches)} shapes in {self._scope()} match {wanted}: IDs {ids}; "
                "use the matching_* form to take every match"
            )
        return matches[0] if matches else None

    def _required(self, found: Shape | None, wanted: str) -> Shape:
        """`found`, as a `require_*` finder looked it up; None raises NotFoundError naming what was `wanted` and where."""
        if found is None:
            raise NotFoundError(f"no shape matches {wanted} in {self._scope()}")
        return found


def _has_property(shape: Shape, label: str, value: str | None) -> bool:
    """Whether `shape` has a property labelled `label` and, where `value` is given, whose value as text is `value`.

    A property with no value matches no `value`.
    """
    found = shape.data_properties.get(label)
    return found is not None and (value is None or found.value == value)


def _describe_property(label: str, value: str | None) -> str:
    """How a finder's message names the property it looked for: ``property 'Cost'``, or ``property 'Cost' = '10'``."""
    return f"property {label!r}" if value is None else f"property {label!r} = {value!r}"
