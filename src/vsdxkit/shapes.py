from __future__ import annotations

import copy
import html
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Protocol
from xml.etree.ElementTree import Element

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


from vsdxkit import namespace
from vsdxkit.connectors import _ConnectorPage, _glued_ends, _retarget_connector
from vsdxkit.errors import InvalidOperationError, NotFoundError, PackageError
from vsdxkit.formulae import calc_value
from vsdxkit.geometry import Geometry, GeometryCell
from vsdxkit.glue import ConnectorOptions, Glue, Routing
from vsdxkit.inheritance import InheritedRow
from vsdxkit.logging_support import get_logger
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.shape_part import AttachedShape, ShapePart
from vsdxkit.shape_tree import find_or_create_shapes_tag, is_connector_element, iter_children, iter_edges, parent_of
from vsdxkit.xmlio import PartTree, make_cell_element, to_float, xml_value

logger = get_logger(__name__)


class PageView(Protocol):
    """A page, as :attr:`Shape.page` gives it.

    The type of a shape's back-reference to its page. It is read-only: it
    lists the page's public API apart from ``swimlanes``,
    ``require_swimlanes`` and ``vis``, whose types are declared above this
    module, and apart from the page's part-level attributes, such as
    ``filename``, ``page_id`` and ``rel_id``. To change a page (set
    ``name``, ``width``, ``height``, ``background`` and so on), or to reach
    those part-level attributes, use the :class:`vsdxkit.pages.Page` you
    hold, such as ``document.pages[0]``. At runtime the object is that
    ``Page`` itself.
    """

    @property
    def name(self) -> str: ...

    @property
    def background(self) -> bool: ...

    @property
    def index_num(self) -> int | None: ...

    @property
    def xml(self) -> PartTree: ...

    @property
    def width(self) -> float: ...

    @property
    def height(self) -> float: ...

    @property
    def is_master_page(self) -> bool: ...

    @property
    def children(self) -> ShapeCollection: ...

    @property
    def shapes(self) -> ShapeCollection: ...

    @property
    def connectors(self) -> tuple[Connector, ...]: ...

    def connect(
        self,
        source: Shape,
        target: Shape,
        *,
        glue: Glue = Glue.DYNAMIC,
        routing: Routing = Routing.DEFAULT,
        from_point: int = 0,
        to_point: int = 0,
    ) -> Connector: ...

    def create_shape(
        self,
        kind_or_prototype: ShapeKind | Shape,
        *,
        x: float,
        y: float,
        width: float | None = None,
        height: float | None = None,
        text: str | None = None,
    ) -> Shape: ...

    def apply_text_context(self, context: dict[str, object]) -> None: ...

    def find_replace(self, old: str, new: str) -> None: ...


class _PageSeam(PageView, _ConnectorPage, Protocol):
    """What a shape needs from its page beyond the public view: the page's
    own bookkeeping, and the document operations the page forwards."""

    @property
    def page_id(self) -> str: ...

    @property
    def filename(self) -> str: ...

    @property
    def _pagesheet_xml(self) -> Element: ...

    def _children(self) -> list[Shape]: ...

    def _attached(self) -> bool: ...

    def _delete(self, shapes: Iterable[Shape], gone_ids: set[str]) -> None: ...

    def _ensure_page_master_rel(self, master_part_name: str) -> None: ...

    def _carry_relationships(self, copied: Element, source: _PageSeam) -> None: ...

    def _peer(self, other: PageView) -> _PageSeam: ...

    def _same_document(self, other: _PageSeam) -> bool: ...

    def _master_by_id(self, master_id: str) -> _PageSeam | None: ...

    def _master_is_one_d(self, master_id: str, master_shape_id: str | None) -> bool: ...

    def _master_revision(self) -> int: ...

    def _masters_for(self, master_ids: list[str], source: _PageSeam) -> Mapping[str, _PageSeam]: ...

    def _copy_shape_xml(self, element: Element) -> Element: ...

    def _renumber_shape_ids(self, subtree: Element, id_map: dict[str, int] | None = None) -> dict[str, int]: ...


def is_connector(shape: Shape) -> bool:
    """Whether `shape` is 1-D, reading the master it inherits from as well as its own cells."""
    return _is_one_d(shape.xml, shape._parent, shape._page)


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


def _is_formatting_run(element: Element) -> bool:
    """True for a self-closing character/paragraph formatting element."""
    return element.tag in _TEXT_RUN_TAGS and len(element) == 0 and not element.text


def _text_runs_of(text_element: Element | None) -> tuple[list[Element], str, list[Element], str]:
    """Split a `<Text>` element into leading runs, content, trailing runs and newlines.

    The leading and trailing runs are the element's own children, not copies, so
    a caller may re-append them after clearing it. Visio ends a Text element
    with a newline that is not part of the text; it is reported separately so
    that writing the text back puts it there again.

    Module level rather than a Shape method because it is also needed where
    there is no Shape to ask: `Document.apply_text_context` is handed bare
    elements.

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


def substitute(text: str, context: dict[str, object]) -> str:
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
    """Represents a Cell element in a vsdx xml file"""

    def __init__(self, xml: Element, shape: Shape):
        self.xml = xml
        self.shape = shape

    @property
    @override
    def _shape(self) -> AttachedShape:
        # the shape, not its document: a write through a part of a deleted
        # shape is refused, as a write to the shape itself is
        return self.shape

    @property
    def value(self) -> str | None:
        return self.xml.attrib.get("V")

    @value.setter
    def value(self, value: float | str) -> None:
        self._require_attached(f"writing the value of cell {self.name!r}")
        self.xml.attrib["V"] = xml_value(value)

    @property
    def formula(self) -> str | None:
        return self.xml.attrib.get("F")

    @formula.setter
    def formula(self, value: str) -> None:
        self._require_attached(f"writing the formula of cell {self.name!r}")
        self.xml.attrib["F"] = xml_value(value)

    @property
    def name(self) -> str | None:
        return self.xml.attrib.get("N")

    def __repr__(self):
        return f"Cell: name={self.name} val={self.value} func={self.formula}"


class DataProperty(InheritedRow, ShapePart):
    """Represents a single Data Property item associated with a Shape object

    A property a shape inherits from its master is handed out marked
    :attr:`~vsdxkit.inheritance.InheritedRow.inherited`. Setting :attr:`value` on
    one materialises an override row on the instance rather than writing to the
    master page's XML.
    """

    shape: Shape
    xml: Element
    name: str | None
    value_type: str | None
    label: str | None
    prompt: str | None
    sort_key: str | None

    def __init__(self, *, xml: Element, shape: Shape):
        """init a DataProperty from a property xml element in a Shape object"""
        name = xml.attrib.get("N")
        # the row's cells by name, first of each, in one pass: a property is
        # read whenever data_properties is, so four searches of the row apiece
        # added up
        cells: dict[str, Element] = {}
        for cell in xml.iterfind(f"{namespace}Cell"):
            cells.setdefault(cell.get("N", ""), cell)
        label_cell = cells.get("Label")

        # initialise empty DataProperty properties
        self.shape = shape  # reference back to Shape object
        self.xml = xml  # reference to xml used to create DataProperty
        self.name = name
        self.value_type = None
        self.label = None
        self.prompt = None
        self.sort_key = None

        if isinstance(label_cell, Element):
            value_type_cell = cells.get("Type")
            prompt_cell = cells.get("Prompt")
            sort_key_cell = cells.get("SortKey")

            # get values from each Cell Element
            self.value_type = value_type_cell.attrib.get("V") if isinstance(value_type_cell, Element) else None
            self.label = label_cell.attrib.get("V") if isinstance(label_cell, Element) else None
            self.prompt = prompt_cell.attrib.get("V") if isinstance(prompt_cell, Element) else None
            self.sort_key = sort_key_cell.attrib.get("V") if isinstance(sort_key_cell, Element) else None
        else:
            # over-ridden master shape properties have no label - only a name and value
            master_shape = shape.master_shape
            master_props: list[DataProperty] = (
                [p for p in master_shape.data_properties.values() if p.name == name] if master_shape is not None else []
            )
            if master_props:
                # get first match 0 - there should always be one item
                master_prop = master_props[0]  # type: DataProperty
                self.label = master_prop.label
                self.value_type = master_prop.value_type
                self.prompt = master_prop.prompt
                self.sort_key = master_prop.sort_key

    @property
    @override
    def _shape(self) -> AttachedShape:
        # the shape, not its document: a write through a part of a deleted
        # shape is refused, as a write to the shape itself is
        return self.shape

    def inherited_by(self, shape: Shape) -> DataProperty:
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
        """
        # make_local() is public and reaches here directly, not only through
        # the guarded value setter, and this is the only materialisation path
        self._require_attached("materialising an inherited data property")
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
        logger.debug("materialised inherited data property %r on shape %s", self.label, self.shape.ID)

    @property
    def value(self) -> str | None:
        """Get the value of the data property, or None when it has none.

        Reading is free of side effects: it neither creates the ``Value`` cell
        nor tidies a ``No Formula`` formula, so inspecting a document does not
        change the bytes it saves.
        """
        value_cell = self.xml.find(f'{namespace}Cell[@N="Value"]')
        if not isinstance(value_cell, Element):
            return None
        if value_cell.attrib.get("V") is not None:
            return value_cell.attrib.get("V")  # value from the V attribute
        return value_cell.text or None  # or from the element's inner text

    @value.setter
    def value(self, value: float | str | None) -> None:
        """Set the value of the data property, creating the cell if absent.

        Writing is also where a placeholder ``No Formula`` formula is cleared:
        leaving it beside a new value would make the cell disagree with itself,
        and Visio may not show the value at all. Upstream dave-howard/vsdx#79.

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
        if value_cell.attrib.get("F") == "No Formula":
            del value_cell.attrib["F"]

    def get_attribute(self, name: str, attrib: str) -> str | None:
        """Get the attribute value of the cell element"""
        element = self._get_element(name)
        if isinstance(element, Element):
            return element.attrib.get(attrib)

    def set_attribute(self, name: str, attrib: str, value: str) -> bool:
        """Set the attribute value of the cell element"""
        self._require_attached("DataProperty.set_attribute()")
        element = self._get_element(name)
        if isinstance(element, Element):
            element.attrib[attrib] = value
            return True
        return False

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
    """Represents a single shape, or a group shape containing other shapes"""

    xml: Element
    _parent: _PageSeam | Shape
    _page: _PageSeam
    _geometry: Geometry | None
    _geometry_xml: Element | None
    _master_shape: Shape | None
    _master_shape_resolved: bool
    _master_shape_key: tuple[str | None, str | None, int, tuple[Element, ...] | None] | None
    _slot: int | None

    def __init__(self, xml: Element, parent: _PageSeam | Shape, page: _PageSeam):
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
        is detached. Its ``ID``, ``xml``, ``repr`` and hash stay readable; any
        other read or write raises :class:`InvalidOperationError`.
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
        """The element's tag: ``<Shape>``, or ``<Shapes>`` for a group's container."""
        return self.xml.tag

    @property
    def ID(self) -> str | None:
        """This shape's page-scoped id, as its element declares it.

        Read-only. An id is not the shape's alone to change: the element
        attribute, the page's ``Connect`` records and the ``Sheet.N!``
        references in other shapes' formulas all name it, and only the
        page's allocator, ``Page._renumber_shape_ids``, moves the three
        together.
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
        """The id of the master this shape instances, or its group's.

        A sub-shape of a group usually carries no ``Master`` of its own and
        instances whatever its group does, so it falls back to the parent's.
        Note this is the master page's id, not its index in
        :attr:`Document.master_pages`.
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
        """
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

    @geometry.setter
    def geometry(self, value: Geometry | None) -> None:
        """Give the shape a Geometry, or ``None`` to report none at all.

        Here because this was a plain attribute before it was built on demand,
        and assigning it worked. It writes nothing to the shape's XML, so the
        two part company until the shape is read again.
        """
        # guarded although it writes no XML: it points the Shape at geometry
        # that the document it belongs to can no longer be saved with
        self._require_attached("replacing a shape's geometry")
        self._geometry = value
        self._geometry_xml = value.xml if value is not None else None

    @property
    def is_master_shape(self) -> bool:
        """Returns True if the shape is a master or False if the shape inherits from a master shape or has no master"""
        return self._page.is_master_page  # shape is a 'master' if it is contained by a master page

    @property
    def universal_name(self) -> str | None:
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
        :raises InvalidOperationError: if the destination page is no longer in its document; nothing is written

        :return: :class:`Shape` the new copy of shape
        """
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
                node.attrib["Master"] = masters[master_id].page_id
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
            members = {master.page_id: _shape_ids(master) for master in masters.values()}
            _drop_unreachable_master_shapes(new_shape_xml, members, dropped, root_names_inherited=bool(inherited))
        # every page that shows an instance of a master relates to it, as Visio
        # writes it; a copy onto another page of this document adds one too
        for master in masters.values():
            dst_page._ensure_page_master_rel(master.filename)
        if not cross_document and dst_page is not self._page:
            dst_page._carry_relationships(new_shape_xml, self._page)

        # _copy_shape_xml put it at the page's top level, whatever the source sat in
        return _wrap(new_shape_xml, dst_page, dst_page)

    @property
    def master_shape(self) -> Shape | None:
        """Get this shapes master

        Returns this Shape's master as a Shape object (or None)

        The result is held rather than rebuilt on every read. Resolving a
        master walks the master page and builds a Shape there, and a shape
        reads through its master for every cell it inherits: resolving it
        afresh each time made reading a page's coordinates over twice as slow.

        It is resolved again when what decides it changes: this shape's
        ``Master`` or ``MasterShape`` attribute, read from the XML each time;
        the masters the document holds, which
        :attr:`vsdxkit.masters.MasterCatalog.revision` counts; or the master
        element's own children, by identity, since the Shape held locates its
        Geometry section when it is built. The master's cells and properties
        are read live through the Shape held, so an edit to one shows up on the
        next read.
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

        Setting :attr:`DataProperty.value` on an inherited property is safe:
        the property is marked inherited, so writing to it creates an override
        row on this shape and leaves the master alone.
        :meth:`DataProperty.set_attribute` does not yet do this, and still
        writes an inherited property's cell in the master.

        :return: Dict[str, DataProperty]
        """
        self._require_attached("reading a shape's data properties")
        properties_xml = self.xml.find(f'{namespace}Section[@N="Property"]')
        property_rows: list[Element] = [] if properties_xml is None else properties_xml.findall(f"{namespace}Row")
        # marked copies, so neither this shape's rows nor a write through an
        # inherited property reaches what the master hands back
        master = self.master_shape
        properties: dict[str, DataProperty] = (
            {label: prop.inherited_by(self) for label, prop in master.data_properties.items()} if master is not None else {}
        )
        for prop in property_rows:
            data_prop = DataProperty(xml=prop, shape=self)
            # add properties to dict to allow fast lookup by property.label
            # (a property row without a Label cell keys under "")
            properties[data_prop.label or ""] = data_prop
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
        self._require_attached(f"reading cell {name}")
        cell = self._cell(name)
        if cell:
            return cell.formula

        if self.master_page_ID is not None:
            master = self.master_shape
            if master is not None:
                return master.cell_formula(name)
        return None

    def _write_cell(self, name: str, *, v: str | None = None, f: str | None = None) -> None:
        """Set a named cell's value or formula, creating the cell if absent.

        The single primitive behind :meth:`set_cell_value` and
        :meth:`set_cell_formula`. Those were copies of each other differing on
        five lines, and one of those lines built the new element with
        ``xmlns:ns0=`` instead of ``xmlns=`` -- declaring a prefix the element
        did not use, so the cell landed outside the Visio namespace and the
        shape could not find it again. Two implementations, one of them wrong,
        is the thing this exists to prevent.

        A cell the master defines is copied down first, so the attribute that
        is not being set keeps what it inherits.
        """
        # nearly every coordinate, size and colour setter arrives here, so one
        # guard covers them all; the message describes the write because which
        # setter the caller used is not knowable from here (issue #329)
        self._require_attached(f"writing shape cell {name!r}")
        cell = self._cell(name)
        if cell is not None:  # update in place
            if f is not None:
                cell.formula = f
            if v is not None:
                cell.value = v
            return

        cell_xml = None
        master = self.master_shape
        if master is not None:
            master_cell_xml = master.xml.find(f'{namespace}Cell[@N="{name}"]')
            if master_cell_xml is not None:
                logger.debug("creating cell from: %s", ET.tostring(master_cell_xml))
                cell_xml = ET.fromstring(ET.tostring(master_cell_xml))
        if cell_xml is None:
            cell_xml = make_cell_element(name)

        cell = Cell(xml=cell_xml, shape=self)
        if f is not None:
            cell.formula = f
        if v is not None:
            cell.value = v
        # schema order: a shape's cells come before its Text and Sections
        cells = self.xml.findall(f"{namespace}Cell")
        self.xml.insert(list(self.xml).index(cells[-1]) + 1 if cells else 0, cell_xml)

    def set_cell_value(self, name: str, value: float | str) -> None:
        """Set a named cell's value, creating the cell if absent."""
        self._write_cell(name, v=xml_value(value))

    def set_cell_formula(self, name: str, value: str) -> None:
        """Set a named cell's formula, creating the cell if absent."""
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
        return self.xml.attrib.get("LineStyle")

    @line_style_id.setter
    def line_style_id(self, value: str | int) -> None:
        self._write_style_attribute("LineStyle", value)

    @property
    def fill_style_id(self) -> str | None:
        return self.xml.attrib.get("FillStyle")

    @fill_style_id.setter
    def fill_style_id(self, value: str | int) -> None:
        self._write_style_attribute("FillStyle", value)

    @property
    def text_style_id(self) -> str | None:
        return self.xml.attrib.get("TextStyle")

    @text_style_id.setter
    def text_style_id(self, value: str | int) -> None:
        self._write_style_attribute("TextStyle", value)

    @property
    def line_weight(self) -> float | None:
        val = self.cell_value("LineWeight")
        return to_float(val, cell="LineWeight")

    @line_weight.setter
    def line_weight(self, value: float | str) -> float | None:
        self.set_cell_value("LineWeight", xml_value(value))

    @property
    def line_color(self) -> str | None:
        return self.cell_value("LineColor")

    @line_color.setter
    def line_color(self, value: str) -> None:
        self.set_cell_value("LineColor", xml_value(value))

    @property
    def fill_color(self) -> str | None:
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
            self._insert_character_row(section, row)
        cell = make_cell_element("Color")
        row.append(cell)
        self._name_character_row_in_text(row.attrib.get("IX", "0"))
        return cell

    @staticmethod
    def _insert_character_row(section: Element, row: Element) -> None:
        """Keep the section's rows in IX order, as Visio writes them."""
        index = int(row.attrib["IX"])
        for position, existing in enumerate(section):
            if int(existing.attrib.get("IX", "0")) > index:
                section.insert(position, row)
                return
        section.append(row)

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
        """Get text color of shape - the colour formatting the start of its text"""
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

    @property
    def end_arrow(self) -> str | None:
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
        return to_float(self.cell_value("PinX"), cell="PinX")

    @x.setter
    def x(self, value: float | str) -> None:
        self.set_cell_value("PinX", _coordinate_value(value))

    @property
    def y(self) -> float | None:
        return to_float(self.cell_value("PinY"), cell="PinY")

    @y.setter
    def y(self, value: float | str) -> None:
        self.set_cell_value("PinY", _coordinate_value(value))

    @property
    def loc_x(self) -> float | None:
        return to_float(self.cell_value("LocPinX"), cell="LocPinX")

    @loc_x.setter
    def loc_x(self, value: float | str) -> None:
        self.set_cell_value("LocPinX", _coordinate_value(value))

    @property
    def loc_y(self) -> float | None:
        return to_float(self.cell_value("LocPinY"), cell="LocPinY")

    @loc_y.setter
    def loc_y(self, value: float | str) -> None:
        self.set_cell_value("LocPinY", _coordinate_value(value))

    @property
    def line_to_x(self) -> float | None:
        return to_float(self.cell_value("Geometry/LineTo/X"), cell="Geometry/LineTo/X")

    @line_to_x.setter
    def line_to_x(self, value: float | str) -> None:
        self.set_cell_value("Geometry/LineTo/X", _coordinate_value(value))

    @property
    def line_to_y(self) -> float | None:
        return to_float(self.cell_value("Geometry/LineTo/Y"), cell="Geometry/LineTo/Y")

    @line_to_y.setter
    def line_to_y(self, value: float | str) -> None:
        self.set_cell_value("Geometry/LineTo/Y", _coordinate_value(value))

    @property
    def begin_x(self) -> float | None:
        return to_float(self.cell_value("BeginX"), cell="BeginX")

    @begin_x.setter
    def begin_x(self, value: float | str) -> None:
        self.set_cell_value("BeginX", _coordinate_value(value))

    @property
    def begin_y(self) -> float | None:
        return to_float(self.cell_value("BeginY"), cell="BeginY")

    @begin_y.setter
    def begin_y(self, value: float | str) -> None:
        self.set_cell_value("BeginY", _coordinate_value(value))

    @property
    def end_x(self) -> float | None:
        return to_float(self.cell_value("EndX"), cell="EndX")

    @end_x.setter
    def end_x(self, value: float | str) -> None:
        self.set_cell_value("EndX", _coordinate_value(value))

    @property
    def end_y(self) -> float | None:
        return to_float(self.cell_value("EndY"), cell="EndY")

    @end_y.setter
    def end_y(self, value: float | str) -> None:
        self.set_cell_value("EndY", _coordinate_value(value))

    def move(self, x_delta: float, y_delta: float) -> None:
        if self.geometry:
            self.geometry.move(x_delta, y_delta)
        if self.begin_x is not None:
            self.begin_x = self.begin_x + x_delta
        self.x = (self.x or 0.0) + x_delta
        if self.begin_y is not None:
            self.begin_y = self.begin_y + y_delta
        self.y = (self.y or 0.0) + y_delta

    def get_or_create_cell(self, name: str, v: str | None = None, f: str | None = None) -> Cell:
        """Set or create a named cell on this shape.

        Existing cells have their V/F attributes updated in place. New cells
        are inserted after the last direct Cell child so the shape keeps the
        schema ordering (cells ahead of Text/Sections).

        :param name: cell name (N attribute), e.g. 'PinX'
        :param v: value to set on the V attribute (optional)
        :param f: formula to set on the F attribute (optional)
        :return: the Cell object
        """
        # second entry point for writing a named cell; #319 folds it into
        # _write_cell, and the guard has to be on both until it does
        self._require_attached(f"writing shape cell {name!r}")
        cell = self._cell(name)
        if cell is not None:
            if f is not None:
                cell.formula = f
            if v is not None:
                cell.value = v
            return cell
        # built as an element, not formatted as a string: a value carrying a
        # quote, an ampersand or an angle bracket is data, and string
        # formatting turned it into a ParseError
        cell_el = make_cell_element(name, v=v, f=f)
        insert_at = 0
        for i, child in enumerate(list(self.xml)):
            if child.tag == f"{namespace}Cell":
                insert_at = i + 1
        self.xml.insert(insert_at, cell_el)
        return Cell(xml=cell_el, shape=self)

    @property
    def height(self) -> float | None:
        return to_float(self.cell_value("Height"), cell="Height")

    @height.setter
    def height(self, value: float | str) -> float | None:
        self.set_cell_value("Height", _coordinate_value(value))

    @property
    def width(self) -> float | None:
        return to_float(self.cell_value("Width"), cell="Width")

    @width.setter
    def width(self, value: float | str) -> float | None:
        self.set_cell_value("Width", _coordinate_value(value))

    @property
    def angle(self) -> float | None:
        return to_float(self.cell_value("Angle"), cell="Angle")

    @angle.setter
    def angle(self, value: float | str) -> None:
        self.set_cell_value("Angle", _coordinate_value(value))

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        # get absolute bounds of a shape relative to page
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
        # get bounds of a shape relative to it's parent (if shape has a parent)
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
        """Set the start and finish of a simple line or connector."""
        # nothing at all is written on a shape with no BeginX, so leaving this
        # to the coordinate setters below would make the refusal depend on the
        # shape it was asked of
        self._require_attached("Shape.set_start_and_finish()")
        if self.begin_x is not None:  # only apply changes to lines and connector shapes
            start_x, start_y = start
            finish_x, finish_y = finish
            if start_x is None or start_y is None or finish_x is None or finish_y is None:
                raise InvalidOperationError("connector start and finish coordinates cannot be None")
            self.x, self.y = start_x, start_y
            # lines/connectors are defined in different ways
            # Check whether shape is a connector based on name in known languages
            is_connector = self.universal_name == "Dynamic connector"

            self.begin_x, self.begin_y = start_x, start_y
            self.end_x, self.end_y = finish_x, finish_y
            width = finish_x - start_x
            height = finish_y - start_y if is_connector else 0.0
            self.width = width
            self.height = height
            self.x, self.y = start_x, start_y
            if self.geometry is not None:
                self.geometry.set_move_to(0.0, 0.0)
                self.geometry.set_line_to(width, height)
            txt_pin_x = self._cell("TxtPinX")
            txt_pin_y = self._cell("TxtPinY")
            if txt_pin_x and txt_pin_y:
                if is_connector:
                    text_x = width / 2
                    text_y = height / 2
                else:
                    text_x, text_y = self.center_x_y
                    if text_x is None or text_y is None:
                        raise InvalidOperationError("shape text coordinates cannot be None")
                txt_pin_x.value = text_x
                txt_pin_y.value = text_y
                self.set_cell_value(name="Control/TextPosition/X", value=text_x)
                self.set_cell_value(name="Control/TextPosition/Y", value=text_y)
                self.set_cell_value(name="Control/TextPosition/XDyn", value=text_x)
                self.set_cell_value(name="Control/TextPosition/YDyn", value=text_y)
            self._refresh_formula_values()

    def _refresh_formula_values(self) -> None:
        """Recompute the value held beside each formula this shape's cells carry, as Visio would on open.

        A formula this library cannot evaluate keeps the value it had.
        """
        cells: list[Cell | GeometryCell] = list(self.cells.values())
        if self.geometry is not None:
            cells.extend(self.geometry.cells)
            for r in self.geometry.rows.values():
                cells.extend(r.cells.values())
        for c in cells:
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
                    c.value = v

    def _text_runs(self) -> tuple[list[Element], str, list[Element], str]:
        """This shape's text, split by `text_runs`, with master inheritance applied.

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
        self._rewrite_texts(lambda text: substitute(text, context))

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
        """Place another shape inside this one, with IDs the page is not using.

        A group holds its children in a ``<Shapes>`` container, created here
        when the group has none. Appending to the group's own ``<Shape>``
        element instead made the new shape a sibling of that container, which
        the schema does not allow and which this library's own traversal cannot
        see, neither through ``children`` nor through ``Page._descendants()``.

        This places a shape, it does not move one. An element already in a page
        gains a second parent rather than changing parent, because
        ElementTree's elements have no parent to change; the page would then
        hold the same shape twice, under one ID and at one position. Copy the
        shape and append the copy instead.
        """
        # ahead of every check and every write, so a detached group refuses
        # before anything is moved into it
        self._require_attached("Shape.append_shape()")
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
        if current_parent is None:
            # New to the page, so it needs ids; a move keeps the ones it has,
            # or every Connect record naming the shape would be left dangling.
            self._page._renumber_shape_ids(append_shape.xml)
        else:
            current_parent.remove(append_shape.xml)
        # last, because it creates the <Shapes> element an empty group lacks:
        # running it ahead of the id allocation left that element behind when
        # the allocation refused the call
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
    :class:`NotFoundError` for none; both raise :class:`InvalidOperationError`
    when several match, rather than choosing one. ``matching_*`` returns every
    match.
    """

    def __init__(self, members: Callable[[], list[Shape]], scope: Callable[[], str]) -> None:
        self._members = members
        self._scope = scope

    def __repr__(self) -> str:
        return f"<ShapeCollection {self._scope()}>"

    def __iter__(self) -> Iterator[Shape]:
        return iter(self._members())

    def __len__(self) -> int:
        return len(self._members())

    def by_id(self, shape_id: str) -> Shape | None:
        """The shape with this page-scoped ID, or None.

        Two shapes with one ID make the page invalid, which is a
        :class:`PackageError` rather than a choice between them.
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
        if len(matches) > 1:
            ids = ", ".join(str(shape.ID) for shape in matches)
            raise InvalidOperationError(
                f"{len(matches)} shapes in {self._scope()} match {wanted}: IDs {ids}; "
                "use the matching_* form to take every match"
            )
        return matches[0] if matches else None

    def _required(self, found: Shape | None, wanted: str) -> Shape:
        if found is None:
            raise NotFoundError(f"no shape matches {wanted} in {self._scope()}")
        return found


def _has_property(shape: Shape, label: str, value: str | None) -> bool:
    found = shape.data_properties.get(label)
    return found is not None and (value is None or str(found.value) == value)


def _describe_property(label: str, value: str | None) -> str:
    return f"property {label!r}" if value is None else f"property {label!r} = {value!r}"
