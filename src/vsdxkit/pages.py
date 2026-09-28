"""Pages, and a document's collection of them.

A :class:`Page` is one page of a document, or one of its master pages. A
:class:`PageCollection` is a document's pages, in order, and the one place
pages are created, copied and deleted. :class:`DocumentView` is the document
as a page gives it.

Reach a page through its document, as ``document.pages[0]`` or
``document.pages.by_name("Page-1")``, never by constructing one: the document
builds each page as it opens.
"""

from __future__ import annotations

import math
import os
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from enum import IntEnum
from pathlib import Path
from typing import Protocol, overload

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


from vsdxkit import namespace, r_namespace
from vsdxkit._connectors import _Connect, _float_ends, _glue_connector, _plan_connector
from vsdxkit._package import PackageStore, XmlPart
from vsdxkit._partnames import relationship_target, relationships_part_name, target_part_name
from vsdxkit._relationships import all_of, append_if_absent
from vsdxkit._shape_tree import (
    SHEET_REFERENCE,
    find_or_create_shapes_tag,
    iter_descendants,
    parent_of,
    remap_sheet_references,
)
from vsdxkit._xmlio import PartTree, require_element, to_float, xml_value
from vsdxkit.errors import InvalidOperationError, MissingPartError, NotFoundError, PackageError
from vsdxkit.glue import ConnectorOptions, Glue, Routing
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.shapes import (
    Connector,
    PageView,
    Shape,
    ShapeCollection,
    _is_connector,
    _PageSeam,
    _wrap_children,
    _wrap_descendants,
)
from vsdxkit.swimlanes import SwimlaneDiagram, _diagram_on

# the two places a Connect record names a shape: the connector it leads from,
# and the shape that connector is glued to
_CONNECT_SHEET_ATTRIBUTES = ("FromSheet", "ToSheet")
"""The attributes of a ``Connect`` record that name a shape, which removing and renumbering shapes rewrites."""

# how a shape names one of its page's relationships: an image's ForeignData Rel
_RELATIONSHIP_ID = f"{r_namespace}id"
"""The ``r:id`` attribute, as ElementTree spells it, by which `_carry_relationships` finds what a copied element names."""

# the cells that size and place a 2-D shape, which a group member ties to its group
_TRANSFORM_CELLS = ("Width", "Height", "LocPinX", "LocPinY", "Angle", "FlipX", "FlipY")
"""The cells whose formula `_detach` drops when it names a shape the copy has left behind."""


def _dimension_value(value: float | str | None) -> str:
    """Return a PageSheet dimension value without serialising nulls or zeros.

    A page with zero or negative width/height is not a valid Visio page, so
    unlike shape geometry the setters reject non-positive values outright.
    """
    if value is None:
        raise TypeError("page dimension cannot be None")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"page dimension must be a finite positive number, got {value!r}") from error
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"page dimension must be a finite positive number, got {value!r}")
    return xml_value(number)


def _left_behind(source: Shape, destination: Page) -> Callable[[str], bool]:
    """Whether a shape id a copy of `source` names is one the copy has left behind.

    A group member's Width can be ``Sheet.9!Width*1``, and at the top level
    Sheet.9 is not its group. On another page every id is another shape's.
    A reference to a shape still beside the copy is left alone.
    """
    if source._page is not destination:
        return lambda _: True
    groups = set()
    parent = source._parent
    while isinstance(parent, Shape):
        groups.add(parent.ID)
        parent = parent._parent
    return groups.__contains__


def _detach(shape: Shape, left_behind: Callable[[str], bool]) -> None:
    """Keep the size a copy had, without the formulas that took it from a shape it has left behind.

    Its own shapes, renumbered with it by the copy, are not left behind.
    """
    own = {element.attrib.get("ID") for element in shape.xml.iter(f"{namespace}Shape")}
    for name in _TRANSFORM_CELLS:
        cell = shape._cell(name)
        if cell is None or cell.formula is None:
            continue
        named = {match.group(2) for match in SHEET_REFERENCE.finditer(cell.formula)}
        if any(sheet not in own and left_behind(sheet) for sheet in named):
            # a library write: this removes a formula naming a shape the copy
            # left behind, keeping the value the cell already had
            cell.xml.attrib.pop("F", None)


def _place_one_d(shape: Shape, x: float, y: float, length: float | None) -> None:
    """Centre a 1-D shape on `x`, `y` by moving its ends, keeping its direction and, without `length`, its length.

    Its pin, width and angle are formulas of its ends, so Visio would put back
    any of them written directly. Its ends are left floating first: a copy of
    a glued connector would otherwise be pulled back to the original's shapes.
    """
    _float_ends(shape)
    begin_x, begin_y, end_x, end_y = shape.begin_x, shape.begin_y, shape.end_x, shape.end_y
    if begin_x is None or begin_y is None or end_x is None or end_y is None:
        raise InvalidOperationError(f"1-D shape ID {shape.ID} has no begin and end points to place it by")
    dx, dy = end_x - begin_x, end_y - begin_y
    if length is not None:
        current = math.hypot(dx, dy)
        # a zero-length line has no direction, so it is laid along the x axis
        dx, dy = (length * dx / current, length * dy / current) if current else (length, 0.0)
    shape.begin_x, shape.begin_y = x - dx / 2, y - dy / 2
    shape.end_x, shape.end_y = x + dx / 2, y + dy / 2
    shape._refresh_formula_values()


class _PagePosition(IntEnum):
    """Where `Document._get_index` puts a new page when no index is given; negative, so no page index can be taken for one."""

    LAST = -1
    """At the end of the document's pages."""
    AFTER = -2
    """Straight after the page being copied."""


def _page_dimension(cell: ET.Element, name: str) -> float:
    """A page dimension off its PageSheet cell, the way a shape cell is read.

    `to_float` is the one place a ShapeSheet number that is not a number is
    reported; a page's PageWidth is the same kind of cell and was read with a
    bare `float()`, so the same malformed document gave two different errors.
    """
    value = to_float(cell.attrib.get("V"), name)
    return 0.0 if value is None else value


def _pages_root(vis: _DocumentSeam) -> ET.Element:
    """The required root element of the document's pages.xml part."""
    pages_xml = vis._pages_xml
    if pages_xml is None:
        raise MissingPartError("document has no pages.xml part")
    return require_element(pages_xml.getroot(), "Pages root")


def _as_page(other: object) -> Page:
    """`other`, which a seam typed structurally, as the `Page` every caller in the library passes.

    Typed code can hand a look-alike through a `Protocol`; it is refused here
    rather than failing further in on a member it lacks.
    """
    if not isinstance(other, Page):
        raise TypeError(f"expected a vsdxkit Page, got {type(other).__name__}")
    return other


class DocumentView(Protocol):
    """A document, as :attr:`Page.vis` gives it.

    The type of a page's back-reference to its document. It lists the
    document's ``pages``, ``save`` and ``render``; for the rest of the
    document's API, use the :class:`vsdxkit.document.Document` you opened.
    At runtime the object is that ``Document`` itself.
    """

    @property
    def pages(self) -> PageCollection:
        """The document's pages, in order: see :class:`PageCollection`."""
        ...

    def save(self, target: str | os.PathLike[str] | None = None) -> Path:
        """Write the document, and return the absolute path it was written to.

        See :meth:`vsdxkit.document.Document.save` for ``target`` and what it raises.
        """
        ...

    def render(self, context: Mapping[str, object]) -> None:
        """Render the document as a Jinja template, in place.

        See :meth:`vsdxkit.document.Document.render` for what the templates can do.
        """
        ...


class _DocumentSeam(DocumentView, Protocol):
    """What a page needs from its document beyond the public view.

    A page's part, its entry in pages.xml and its title in app.xml live in
    the document's package. The masters, and the shapes a new shape is copied
    from, are the document's. `document` imports this module, so the page
    declares what it reads rather than importing `Document`.
    """

    @property
    def _pages_xml(self) -> PartTree | None:
        """The `pages.xml` part, the list of the document's pages, read from the store; None where the package has none.

        A page finds its own entry there, by position or by ID.
        """
        ...

    @property
    def _masters_xml(self) -> ET.Element | None:
        """The `<Masters>` root, read from the store so it can never be a stale copy; `is_master_page` and a master's page sheet are read there."""
        ...

    @property
    def _package(self) -> PackageStore:
        """The store holding the document's parts, which a page asks whether the part at its name is still its own."""
        ...

    def _set_part_xml(self, name: str, tree: PartTree | None) -> None:
        """Make `tree` the part called `name`, or take the part out for None: how a page writes its part and its rels part."""
        ...

    def _rename_page_in_app_xml(self, old_page_name: str, new_page_name: str) -> None:
        """Keep app.xml's list of page names in step with a page that was renamed."""
        ...

    def _master_page_by_id(self, id: str) -> Page | None:
        """The master page with this ID, as :attr:`Shape.master_page_ID` names it, or None."""
        ...

    def _master_is_one_d(self, master_id: str, master_shape_id: str | None) -> bool:
        """Whether the master shape an instance inherits from is 1-D; see :meth:`MasterCatalog.is_one_d`."""
        ...

    def _master_revision(self) -> int:
        """The catalog's :attr:`MasterCatalog.revision`: a master resolved at one count holds until the next."""
        ...

    def _masters_for(self, master_ids: list[str], source: _DocumentSeam) -> Mapping[str, Page]:
        """This document's master for each of `master_ids`, as `source` numbers its masters."""
        ...

    def _kind_source(self, kind: ShapeKind) -> Shape:
        """The bundled shape `kind` is copied from, one of the donors `vsdxkit._media` loads."""
        ...

    def _copy_connector(self, page: Page) -> Connector:
        """A copy of the bundled dynamic connector on `page`, one of this document's pages."""
        ...


class Page:
    """A page of a document, or one of its master pages.

    Reach a page through its document, as ``document.pages[0]`` or
    ``document.pages.by_name("Page-1")``, rather than constructing one: the
    document builds each page as it opens. ``page.vis`` is the document the
    page belongs to.
    """

    xml: PartTree
    """The page's part, parsed: its shapes and its ``Connect`` records."""

    def __init__(self, xml: PartTree, filename: str, page_name: str, page_id: str, rel_id: str, vis: _DocumentSeam) -> None:
        """Wrap `xml`, the part stored as `filename`, under the name, ID and relationship ID its document `vis` lists it with.

        A drawing page's come from pages.xml, a master's from masters.xml; the
        document builds each page, and a caller never does.
        """
        self._xml = xml
        self._filename = filename
        self._name = page_name
        self._page_id = page_id
        self._rel_id = rel_id
        self._master_unique_id: str | None = None
        self._rels_xml_filename: str | None = None
        self._rels_tree: PartTree | None = None
        self._document = vis
        self._max_id = 0  # ID high-water mark, maintained by _increment_shape_ids

    def __repr__(self) -> str:
        """Shows the page's name and the name of its part."""
        return f"<Page name={self.name} file={self._filename} >"

    @property
    def vis(self) -> DocumentView:
        """The document this page belongs to."""
        return self._document

    def _connects(self) -> list[_Connect]:
        """Every ``<Connect>`` record on the page, in document order."""
        return [_Connect(element) for element in self.xml.findall(f".//{namespace}Connect")]

    @property
    def name(self) -> str:
        """The page's name.

        Setting it writes the new name as both the page's name and its
        universal name, in the document's page list and its ``app.xml``
        titles. A name another page already has is not refused here, though
        :meth:`vsdxkit.pages.PageCollection.by_name` then raises
        :class:`vsdxkit.errors.PackageError` for that name. On a master
        page, or one removed from its document, it raises
        :class:`vsdxkit.errors.InvalidOperationError`.
        """
        if self._name:
            return self._name
        page = self._page_xml()
        name = page.attrib.get("Name")
        name_u = page.attrib.get("NameU")
        return name_u or name or self._name or ""

    @name.setter
    def name(self, value: str) -> None:
        previous = self.name
        page = self._page_xml()
        page.attrib["Name"] = value
        page.attrib["NameU"] = value
        self._name = value
        # app.xml lists the page names too, and would keep the old one
        self._document._rename_page_in_app_xml(previous, value)

    def _index(self) -> int:
        """Zero-based index of this page in its Document (required)."""
        index = self.index_num
        if index is None:
            raise InvalidOperationError("page is not attached to a Document")
        return index

    def _page_xml(self) -> ET.Element:
        """The Pages/Page element for this page (from pages.xml)."""
        # by position among the Page children, not with a Page[n] path: a
        # positional predicate builds a map of the whole tree on every call
        index = self._index()
        pages = _pages_root(self._document).findall(f"{namespace}Page")
        return require_element(pages[index] if index < len(pages) else None, f"Page[{index + 1}]")

    @property
    def background(self) -> bool:
        """Whether the page is a background page, which other pages can show behind their own shapes.

        Setting it takes a ``bool``, and writes any true value as ``1``. On a
        master page, or one removed from its document, reading or setting it
        raises :class:`vsdxkit.errors.InvalidOperationError`.
        """
        return self._page_xml().attrib.get("Background", "0") != "0"

    @background.setter
    def background(self, value: bool) -> None:
        self._page_xml().attrib["Background"] = "1" if value else "0"

    @property
    def is_master_page(self) -> bool:
        """Whether this is one of the document's master pages rather than a drawing page."""
        if self._document._masters_xml is not None and self._master_unique_id:
            master_match = f'{namespace}Master[@UniqueID="{self._master_unique_id}"]'
            master_element = self._document._masters_xml.find(master_match)
            return master_element is not None
        return False

    @property
    def _pagesheet_xml(self) -> ET.Element:
        """The page's `PageSheet` element, found by the page's ID in pages.xml and then in masters.xml; `MissingPartError` in neither.

        pages.xml is asked first, so a master whose ID a drawing page also has
        is given that drawing page's `PageSheet`.
        """
        # get PageSheet element from _pages_xml based on _page_id
        ps = _pages_root(self._document).find(f'{namespace}Page[@ID="{self._page_id}"]/{namespace}PageSheet')
        if not isinstance(ps, ET.Element):
            masters_xml = self._document._masters_xml
            if masters_xml is not None:
                ps = masters_xml.find(f'{namespace}Master[@ID="{self._page_id}"]/{namespace}PageSheet')
        return require_element(ps, f"PageSheet for page_id={self._page_id}")

    def _pagesheet_cell(self, name: str) -> ET.Element:
        """A named Cell element on this page's PageSheet."""
        return require_element(self._pagesheet_xml.find(f'{namespace}Cell[@N="{name}"]'), f"PageSheet Cell {name}")

    @property
    def width(self) -> float:
        """The page's width, in inches, from its page sheet's ``PageWidth`` cell; ``0.0`` for a cell with no value.

        Setting it takes a positive number, or a string that reads as one;
        anything else raises :class:`ValueError`, and ``None`` raises
        :class:`TypeError`. On a master page whose ID a drawing page also
        has, this reads that drawing page's sheet instead of the master's
        own.

        :raises MissingPartError: if the page sheet has no ``PageWidth`` cell
        :raises MalformedPackageError: if the ``PageWidth`` value is not a number
        """
        return _page_dimension(self._pagesheet_cell("PageWidth"), "PageWidth")

    @width.setter
    def width(self, value: float | str | None) -> None:
        self._pagesheet_cell("PageWidth").attrib["V"] = _dimension_value(value)

    @property
    def height(self) -> float:
        """The page's height, in inches, from its page sheet's ``PageHeight`` cell; ``0.0`` for a cell with no value.

        Setting it takes what :attr:`width` takes, and refuses what it
        refuses; a master page whose ID a drawing page shares reads that
        drawing page's sheet here too.

        :raises MissingPartError: if the page sheet has no ``PageHeight`` cell
        :raises MalformedPackageError: if the ``PageHeight`` value is not a number
        """
        return _page_dimension(self._pagesheet_cell("PageHeight"), "PageHeight")

    @height.setter
    def height(self, value: float | str | None) -> None:
        self._pagesheet_cell("PageHeight").attrib["V"] = _dimension_value(value)

    @property
    def xml(self) -> PartTree:
        """The page's part, parsed: its shapes and its ``Connect`` records.

        The value is an ``xml.etree.ElementTree.ElementTree``, which a caller
        reads and edits with the standard library.

        Assigning a tree replaces the part the document saves, while the page
        is still in its document; a page removed from it only holds the tree.
        The setter takes such a tree; ``None`` raises :class:`vsdxkit.errors.InvalidOperationError`.
        """
        return self._xml

    @xml.setter
    def xml(self, value: PartTree | None) -> None:
        if value is None:
            raise InvalidOperationError(
                f"Page.xml cannot be set to None: {self._filename} cannot be removed through "
                f"this property, because pages.xml, pages.xml.rels and the content-type "
                f"override would still name it"
            )
        attached = self._attached()
        self._xml = value
        if attached:
            self._document._set_part_xml(self._filename, value)

    def _holds(self, filename: str, tree: PartTree | None) -> bool:
        """Whether the package's part at `filename` is `tree` itself."""
        held = self._document._package.part(filename)
        return isinstance(held, XmlPart) and held.tree is tree

    def _attached(self) -> bool:
        """Whether an assignment to `xml` may write this page's part.

        A caller may keep holding a `Page` after it has been removed from the
        document (`PageCollection.delete`); a later assignment to its
        `xml` must not resurrect the part it was removed from. Nor may it
        write over the part of the page added after it: removal frees the part
        name, and the next page takes it. So this asks whether the part at the
        page's name is this page's own tree, not merely whether there is one.

        The one other way in is a part that is gone while its page is still
        one of the document's. Nothing at open stops two pages' relationships
        targeting the same part, and then the two pages share it; removing one
        takes the part out from under the other. pages.xml still names the
        part, so a tree assigned to the page left behind must bring it back.
        """
        if self._holds(self._filename, self._xml):
            return True
        return self._document._package.part(self._filename) is None and any(page is self for page in self._document.pages)

    def _rels_attached(self) -> bool:
        """Whether an assignment to `_rels_xml` may write this page's relationship part.

        Only while the page itself is attached, and only over the relationship
        part the page holds -- or where the package holds none yet, which is
        how one is first created. A removed page's rels name is freed along
        with its page's, and the page that takes the name must not be given
        the removed page's relationships.
        """
        if self._rels_xml_filename is None or not self._attached():
            return False
        held = self._document._package.part(self._rels_xml_filename)
        if held is None:
            return True
        return isinstance(held, XmlPart) and held.tree is self._rels_tree

    @property
    def _rels_xml(self) -> PartTree | None:
        """The page's relationships part, parsed, or None for a page without one.

        Assigning a tree, or None to remove the part, writes through to the
        package only while `_rels_attached` allows it; otherwise the page just
        holds the new value.
        """
        return self._rels_tree

    @_rels_xml.setter
    def _rels_xml(self, value: PartTree | None) -> None:
        # None takes the rels part out of the package as well: the save writes
        # whatever the store holds, so a part left behind would reach the file
        attached = self._rels_attached()
        self._rels_tree = value
        if attached:
            assert self._rels_xml_filename is not None  # _rels_attached() says so
            self._document._set_part_xml(self._rels_xml_filename, value)

    @property
    def shapes(self) -> ShapeCollection:
        """Every shape on the page, at any depth, connectors included: depth first, parents first."""
        return ShapeCollection(self._descendants, self._scope)

    @property
    def children(self) -> ShapeCollection:
        """The page's top-level shapes."""
        return ShapeCollection(self._children, self._scope)

    def _children(self) -> list[Shape]:
        """What :attr:`children` holds, as a list, for the library's own walks."""
        root = self.xml.getroot()
        return [] if root is None else _wrap_children(root, self, self)

    def _descendants(self) -> list[Shape]:
        """What :attr:`shapes` holds, as a list, for the library's own walks."""
        root = self.xml.getroot()
        return [] if root is None else _wrap_descendants(root, self, self)

    def _scope(self) -> str:
        """How a collection of the page's shapes names its scope in a message: ``page 'Page-1'``."""
        return f"page {self.name!r}"

    def _set_max_ids(self) -> None:
        """Raise this page's ID high-water mark to cover every shape now on it.

        Private plumbing for ``_increment_shape_ids()``, which calls it
        at the start of each allocation run. It was public, and every caller
        that inserted a shape was expected to remember to call it first; the
        ones that forgot handed out IDs the page was already using. Monotonic
        and idempotent, so calling it again costs a scan and nothing else.
        """
        root = self.xml.getroot()
        if root is not None:
            ids = (int(shape_id) for element in iter_descendants(root) if (shape_id := element.attrib.get("ID")) is not None)
            self._max_id = max(self._max_id, *ids, 0)

    def _next_shape_id(self) -> int:
        """Hand out the next shape ID. ``_set_max_ids()`` syncs the mark first."""
        self._max_id += 1
        return self._max_id

    @property
    def index_num(self) -> int | None:
        """The page's zero-based position in its document's pages, or ``None`` for a master page or one removed from the document."""
        # return zero-based index of this page in parent Document.pages list
        return self._document.pages.index(self) if self in self._document.pages else None

    def _add_connect(self, element: ET.Element) -> None:
        """Append a ``Connect`` record to the page's ``Connects`` element, adding one at the end of the page's root if it has none."""
        connects = self.xml.find(f".//{namespace}Connects")
        if connects is None:
            connects = ET.fromstring(
                f"<Connects xmlns='{namespace[1:-1]}' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'/>"
            )
            root = require_element(self.xml.getroot(), "page root")
            root.append(connects)
            connects = require_element(self.xml.find(f".//{namespace}Connects"), "Connects")
        connects.append(element)

    def _ensure_page_master_rel(self, master_part_name: str) -> None:
        """Ensure this page's rels relate it to the master part named `master_part_name`.

        Visio writes a per-page relationship to each master used by shapes on
        that page. The Target is derived from the master's part name, so a
        master kept in a subfolder of the masters folder is reached there. The
        id comes from this page's own rels part: `masters.xml.rels` is a
        different id space, and an id free there says nothing here (#357). The
        rels part is created on demand; assigning it writes it into the package.
        """
        append_if_absent(
            self._rels_root(),
            rel_type="http://schemas.microsoft.com/visio/2010/relationships/master",
            target=relationship_target(self._filename, master_part_name),
        )

    # A shape asks its page, and the page asks its document: a shape never
    # reaches through the page to the document (#114).

    def _master_by_id(self, master_id: str) -> Page | None:
        """The master page with this ID, as `Shape.master_page_ID` names it, or None: the document's answer."""
        return self._document._master_page_by_id(master_id)

    def _master_is_one_d(self, master_id: str, master_shape_id: str | None) -> bool:
        """Whether the master shape an instance inherits from is 1-D, which makes the instance a `Connector`: the document's answer."""
        return self._document._master_is_one_d(master_id, master_shape_id)

    def _master_revision(self) -> int:
        """The document's count of changes to its masters: `Shape.master_shape`'s memo holds while it stays the same."""
        return self._document._master_revision()

    def _peer(self, other: PageView) -> Page:
        """`other` as a page of this library, for a shape copied onto it."""
        return _as_page(other)

    def _masters_for(self, master_ids: list[str], source: _PageSeam) -> Mapping[str, Page]:
        """This document's master for each of `master_ids`, as `source`'s document numbers them."""
        return self._document._masters_for(master_ids, _as_page(source)._document)

    def _copy_shape_xml(self, element: ET.Element) -> ET.Element:
        """A copy of `element` at this page's top level, with IDs unused on this page."""
        copied = ET.fromstring(ET.tostring(element))
        shapes = find_or_create_shapes_tag(self.xml.getroot())
        self._renumber_shape_ids(copied)
        shapes.append(copied)
        return copied

    def _renumber_shape_ids(self, subtree: ET.Element, id_map: dict[str, int] | None = None) -> dict[str, int]:
        """Give a subtree IDs unused on this page, and follow them everywhere the page writes them.

        One primitive, because a shape ID is written in two places: the
        ``Sheet.N!`` references inside cell formulas, and the ``FromSheet`` and
        ``ToSheet`` attributes of the page's ``Connect`` records. Allocating and
        then sweeping only the formulas is what left a renumbered shape's glue
        naming an ID that was no longer on the page.

        Both stores are swept over the same ground: the whole page. Sweeping the
        records page-wide and the formulas only inside the renumbered subtree
        left behind every *other* shape that named the vacated ID in a cell
        formula, so a connector's record moved on while the formula placing its
        endpoint still addressed a sheet that had gone (#328).

        A vacated ID is one that was on the page before and is gone after.
        Renumbering does not always retire an ID - ``_copy_shape_xml`` leaves the
        original where it was, and the Jinja loop renumbers the duplicates while
        the shape they were copied from keeps its ID. Nor is every ID in the map
        one this page ever had: a subtree arriving from elsewhere brings its own,
        and a stale record that happens to name one of those numbers belongs to
        whatever wrote the file, not to the shape now carrying it. When nothing
        was vacated neither sweep runs, and nothing on the page is rewritten.

        The subtree is swept twice when it is already on the page, and the second
        sweep cannot chain onto what the first wrote. A subtree on the page has
        every allocated ID stamped onto one of its shapes, so every allocated ID
        is in ``after`` and none of them can be a vacated ID; a subtree that is
        not on the page leaves ``before`` and ``after`` equal and vacates
        nothing. The one way past that is a caller seeding ``id_map`` with a
        mapping onto an ID the page is still using, which is not what the
        parameter is for.

        :param subtree: root of the subtree to renumber, normally a ``Shape`` element
        :param id_map: mapping to extend, so several subtrees renumbered
            together share one map; a new one is started when omitted
        :return: the ID map, old ID -> new ID
        """
        before = self._shape_ids()
        id_map = self._increment_shape_ids(subtree, id_map)
        remap_sheet_references(subtree, id_map)
        after = self._shape_ids()
        vacated = {old: new for old, new in id_map.items() if old in before and old not in after}
        if vacated:
            remap_sheet_references(require_element(self.xml.getroot(), "page root"), vacated)
            self._remap_connect_records(vacated)
        return id_map

    def _increment_shape_ids(self, subtree: ET.Element, id_map: dict[str, int] | None = None) -> dict[str, int]:
        """Give ``subtree`` and the shapes inside it IDs unused on this page, and map old to new.

        Allocation owns the page's high-water mark rather than trusting callers
        to prime it: ``_max_id`` is 0 on a freshly loaded page, so a caller that
        forgot handed out 1 to a page whose first shape was already 1.
        Duplicate IDs make ``Connect`` records ambiguous and Visio offers to
        repair the file. Every entry into this method syncs, including one that
        passes an ``id_map`` to collect the mapping, because a caller who has to
        remember is the fault being fixed. The page is scanned once here, and
        the walk below allocates without scanning again.

        That walk covers the whole subtree, to any depth. It used to descend
        into a ``Shapes`` container but then only stamp the ``Shape`` elements
        directly inside it, so a group's grandchildren arrived in the copy
        still carrying their original IDs.

        Only ``Shape`` elements are numbered. A ``Shapes`` container is not a
        shape and takes no ``ID`` in the schema, and numbering one consumed an
        ID that ``_set_max_ids`` could not see, since that scan looks at
        shapes; a later allocation could then hand the same number to a real
        shape. A root element outside the Visio namespace is left alone for the
        same reason, so a caller that hand-builds one must namespace it to have
        it numbered.

        :param subtree: root of the copied subtree, normally a ``Shape`` element
        :param id_map: mapping to extend, so several subtrees copied together
            share one map; a new one is started when omitted
        :return: the ID map, old ID -> new ID, for ``remap_sheet_references`` to apply
        """
        self._set_max_ids()
        if id_map is None:
            id_map = {}
        for element in subtree.iter(f"{namespace}Shape"):
            self._set_new_id(element, id_map)
        return id_map

    def _set_new_id(self, element: ET.Element, id_map: dict[str, int]) -> int:
        """Stamp the next free page ID onto one Shape element.

        Call this only for a ``Shape``; ``_increment_shape_ids`` is what decides
        which elements qualify.
        """
        max_id = self._next_shape_id()
        if element.attrib.get("ID"):
            current_id = element.attrib["ID"]
            id_map[current_id] = max_id  # record mappings
        element.attrib["ID"] = str(max_id)
        return max_id  # return new id for info

    def _same_document(self, other: _PageSeam) -> bool:
        """Whether `other` is a page of this page's document, which decides whether a copy crosses documents; `TypeError` for a look-alike that is not a `Page`."""
        return _as_page(other)._document is self._document

    def _rels_root(self) -> ET.Element:
        """This page's `<Relationships>` element, creating the part on demand; assigning it writes it into the package."""
        rels_xml: PartTree | None = self._rels_xml
        if rels_xml is None:
            self._rels_xml_filename = relationships_part_name(self._filename)
            rels_xml = ET.ElementTree(
                ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
            )
            self._rels_xml = rels_xml
        return require_element(rels_xml.getroot(), f"{self._rels_xml_filename} root")

    def _carry_relationships(self, copied: ET.Element, source: _PageSeam) -> None:
        """Relate this page to what each ``r:id`` in `copied` names on `source`, and point the copy at it.

        An image or embedded object reaches its part through its page's
        relationships, by an id that means nothing on another page. Within one
        document the part is shared, so the copy needs only a relationship of
        its own to the same part.
        """
        source_rels = _as_page(source)._rels_xml
        if source_rels is None:
            return
        by_id = {rel.attrib.get("Id"): rel for rel in all_of(source_rels.getroot())}
        for node in copied.iter():
            relationship = by_id.get(node.attrib.get(_RELATIONSHIP_ID))
            if relationship is None:
                continue  # none, or already dangling on the source page
            mode = relationship.attrib.get("TargetMode")
            target = relationship.attrib.get("Target", "")
            if mode != "External":
                target = relationship_target(self._filename, target_part_name(source._filename, target))
            carried = append_if_absent(
                self._rels_root(), rel_type=relationship.attrib.get("Type", ""), target=target, mode=mode
            )
            node.attrib[_RELATIONSHIP_ID] = carried.attrib["Id"]

    def apply_text_context(self, context: dict[str, object]) -> None:
        """Replace each ``{{key}}`` in the text of every shape on the page with its value from ``context``.

        The match is literal, with no spaces inside the braces, and each value
        is written as :func:`str` gives it. A shape whose text has nothing to
        replace is left as it was.
        """
        for shape in self._children():
            shape.apply_text_filter(context)

    def find_replace(self, old: str, new: str) -> None:
        """Replace ``old`` with ``new`` in the text of every shape on the page; a shape without ``old`` is left as it was."""
        for shape in self._children():
            shape.find_replace(old, new)

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

        :param glue: :attr:`~vsdxkit.glue.Glue.DYNAMIC` walks each end round its shape to the
            nearest side; :attr:`~vsdxkit.glue.Glue.POINT` glues the ends to ``from_point``
            and ``to_point``, 0-based rows of each shape's ``Connection`` section
        :param routing: the path between the ends; :attr:`~vsdxkit.glue.Routing.DEFAULT` is Visio's own
        :raises InvalidOperationError: the page is no longer in its document, a shape is not on this page,
            or a connection point does not exist; nothing is written
        :returns: the new connector
        """
        if not self._attached():
            raise InvalidOperationError(f"page {self.name!r} is no longer in its document, so nothing can be connected on it")
        options = ConnectorOptions(glue=glue, routing=routing, from_point=from_point, to_point=to_point)
        begin, end = _plan_connector(self, source, target, options)
        connector = self._document._copy_connector(self)
        _glue_connector(connector, begin, end, options)
        return connector

    @property
    def connectors(self) -> tuple[Connector, ...]:
        """Every connector on the page, at any depth, glued at both ends, one or neither."""
        return tuple(shape for shape in self.shapes if isinstance(shape, Connector))

    @property
    def swimlanes(self) -> SwimlaneDiagram | None:
        """The cross-functional flowchart on this page, or None for a page without one.

        :raises InvalidOperationError: the page has more than one CFF container
        """
        return _diagram_on(self)

    def require_swimlanes(self) -> SwimlaneDiagram:
        """The cross-functional flowchart on this page.

        :raises NotFoundError: the page has no CFF container
        :raises InvalidOperationError: the page has more than one
        """
        diagram = _diagram_on(self)
        if diagram is None:
            raise NotFoundError(f"page {self.name!r} has no CFF container, so no swimlane diagram")
        return diagram

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

        ``kind_or_prototype`` is a built-in :class:`~vsdxkit.shape_kind.ShapeKind`,
        or a shape from this document to copy: a prototype is how a shape
        with a custom master is made. Either way the new shape is a copy made
        by :meth:`~vsdxkit.shapes.Shape.copy`, the one way a shape is created.

        A 1-D shape, such as :attr:`~vsdxkit.shape_kind.ShapeKind.LINE`, is placed by its ends: it
        keeps its direction, and ``width`` is its length.

        :param width, height: the new size; the kind's or prototype's when omitted
        :param text: the label. A kind starts blank; a prototype keeps its text when omitted.
        :raises TypeError: if ``kind_or_prototype`` is neither a kind nor a shape
        :raises InvalidOperationError: if the page is no longer in its document; if a prototype is no
            longer in its document, or belongs to another document; if ``height`` is given for a 1-D
            shape; or if a 1-D shape lacks the begin and end points it is placed by
        :returns: the new shape
        """
        if not self._attached():
            raise InvalidOperationError(f"page {self.name!r} is no longer in its document, so nothing can be created on it")
        if isinstance(kind_or_prototype, ShapeKind):
            source = self._document._kind_source(kind_or_prototype)
        elif isinstance(kind_or_prototype, Shape):
            kind_or_prototype._require_attached("Page.create_shape()")
            if not self._same_document(kind_or_prototype._page):
                raise InvalidOperationError(
                    f"shape ID {kind_or_prototype.ID} belongs to another document; "
                    "a prototype must come from the document it is copied into"
                )
            source = kind_or_prototype
        else:
            kinds = ", ".join(f"ShapeKind.{kind.name}" for kind in ShapeKind)
            raise TypeError(f"create_shape takes a Shape or one of {kinds}, not {kind_or_prototype!r}")
        one_d = _is_connector(source)
        if one_d and height is not None:
            raise InvalidOperationError(f"shape ID {source.ID} is 1-D, so it has no height to set; its width is its length")
        # what the copy's formulas may no longer name: the groups the prototype
        # sat in, and on another page, every shape of the page it left
        left_behind = _left_behind(source, self)
        shape = source.copy(self)
        label = ("" if text is None else text) if isinstance(kind_or_prototype, ShapeKind) else text
        if one_d:
            _place_one_d(shape, x, y, width)
        else:
            # a 2-D shape is drawn around its pin
            shape.get_or_create_cell("PinX", v=str(x))
            shape.get_or_create_cell("PinY", v=str(y))
            _detach(shape, left_behind)
            if width is not None:
                shape.width = width
        if height is not None:
            shape.height = height
        if width is not None or height is not None:
            # LocPinX is Width*0.5 and the geometry scales with the size: their
            # values would otherwise describe the old size until Visio opens it
            shape._refresh_formula_values()
        if label is not None:
            shape.text = label
        return shape

    def _delete(self, shapes: Iterable[Shape], gone_ids: set[str]) -> None:
        """The one deletion: `shapes`, the connectors glued to any of `gone_ids`, and every record naming them.

        `gone_ids` are the shapes going away: those in `shapes` and everything
        inside them, and any already gone from the XML by another route, such
        as a Jinja ``showif`` that rendered them out. A Shape held for any of
        them is detached afterwards, since attachment is read from the XML.
        """
        # connectors are the FromSheet of Connect records whose ToSheet is one
        # of the shapes going, on a begin/end relationship
        connector_ids = {c.from_id for c in self._connects() if c.to_id in gone_ids and c.from_rel in ("BeginX", "EndX")}
        doomed = set(shapes)
        for s in self._descendants():
            # the master too: a connector may inherit BeginX from it, and one
            # missed here survives as a detached line whose glue record has just
            # been removed
            if str(s.ID) in connector_ids and _is_connector(s):
                doomed.add(s)
        for s in doomed:
            self._remove_shape_xml(s)
        # a record naming a group child outlives the child otherwise: the child
        # goes with the group element rather than through _remove_shape_xml
        self._remove_connect_records(gone_ids, match="either")

    def _remove_shape_xml(self, shape: Shape) -> None:
        """Remove a shape's xml and every Connect record that names it.

        Records naming the shape on either side go: one pointing *at* a shape
        that is gone dangles just as surely as one leading from it. Connectors
        glued to the shape are separate shapes and are passed through here in
        their own right by :meth:`vsdxkit.shapes.Shape.delete`.
        """
        self._remove_connect_records({str(shape.ID)}, match="either")
        container = parent_of(self.xml.getroot(), shape.xml)
        if container is not None:
            container.remove(shape.xml)

    def _remove_connect_records(
        self, connector_ids: Iterable[str | int], *, match: str = "from", from_cell: str | None = None
    ) -> None:
        """Remove Connect records naming any of these shapes.

        Single record-removal path, shared by the delete cascade and connector
        retargeting. ``match="from"`` removes only the records leading from
        these shapes, which is what retargeting wants: it is replacing a
        connector's own glue. ``match="either"`` also removes records pointing
        at them, for a shape that is going away entirely. With `from_cell`,
        only a record whose ``FromCell`` equals it is removed, for freeing one
        end of a connector without disturbing the other's record.
        """
        if match not in ("from", "either"):
            raise ValueError(f"match must be 'from' or 'either', not {match!r}")
        connects_el = self.xml.find(f".//{namespace}Connects")
        if connects_el is None:
            return
        normalised_ids = {str(connector_id) for connector_id in connector_ids}
        attributes = ("FromSheet",) if match == "from" else _CONNECT_SHEET_ATTRIBUTES
        for connect in list(connects_el):
            if normalised_ids & {connect.attrib.get(attribute) for attribute in attributes} and (
                from_cell is None or connect.attrib.get("FromCell") == from_cell
            ):
                connects_el.remove(connect)

    def _remap_connect_records(self, id_map: Mapping[str, int]) -> None:
        """Point the records at the new ids of shapes this page has renumbered.

        Shape ids live in two places: the ``Sheet.N!`` references inside cell
        formulas, which ``remap_sheet_references`` rewrites, and the ``FromSheet``
        and ``ToSheet`` attributes here. Records left behind when a shape is
        renumbered name an id that is no longer on the page, and Visio rebinds
        glue like that silently.

        Private plumbing for ``_renumber_shape_ids()``, which runs this
        and the formula sweep over the same page with the same map, and decides
        what belongs in that map: only the ids renumbering vacated. An id still
        in use, or one that was never on this page, names a record that means
        what it says, and remapping it would hand a copy the original's glue or
        let an arriving shape inherit glue from a record some other writer left
        behind.
        """
        connects_el = self.xml.find(f".//{namespace}Connects")
        if connects_el is None:
            return
        for connect in connects_el:
            for attribute in _CONNECT_SHEET_ATTRIBUTES:
                new_id = id_map.get(connect.attrib.get(attribute, ""))
                if new_id is not None:
                    connect.attrib[attribute] = str(new_id)

    def _shape_ids(self) -> set[str]:
        """Every shape id the page's xml declares right now.

        Read off the elements rather than through ``shapes``, which builds a
        ``Shape`` per element to answer a question about the xml.
        """
        root = self.xml.getroot()
        return {shape_id for element in iter_descendants(root) if (shape_id := element.attrib.get("ID"))}


class _PageLifecycle(Protocol):
    """What a :class:`PageCollection` needs from the document that owns its pages."""

    def _add_page_at(self, index: int, name: str | None = None) -> Page:
        """Add a new page at the specified index of the document, or at the end for `_PagePosition.LAST`, and return it."""
        ...

    def _copy_page(self, page: Page, *, index: int | _PagePosition = ..., name: str | None = None) -> Page:
        """Copy an existing page and insert it in the document, straight after `page` for `_PagePosition.AFTER`, and return the copy."""
        ...

    def _remove_page_by_index(self, index: int) -> None:
        """Remove the document's page at this zero-based index, with its part, its relationships and its title in app.xml."""
        ...


class PageCollection(Sequence[Page]):
    """A document's pages, in order, and the one place pages are created, copied and deleted.

    A sequence: ``len``, iteration, indexing (negative indexes too), ``in``
    and ``index`` behave as they do on a tuple. It is live: a page added or
    removed through any route is seen by a collection taken before.
    """

    def __init__(self, pages: list[Page], lifecycle: _PageLifecycle) -> None:
        """A view of `pages`, the document's own list, which it reads live; `lifecycle`, the document, adds, copies and removes pages."""
        self._pages = pages
        self._lifecycle = lifecycle

    def __repr__(self) -> str:
        """Shows the pages' names, as ``<PageCollection ['Page-1', 'Page-2']>``."""
        return f"<PageCollection {[page.name for page in self._pages]!r}>"

    def __len__(self) -> int:
        """How many pages the document has now."""
        return len(self._pages)

    @override
    def __iter__(self) -> Iterator[Page]:
        """The pages as they are when iteration starts: a page added or removed while iterating does not disturb it."""
        return iter(list(self._pages))

    @overload
    def __getitem__(self, index: int) -> Page: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Page, ...]: ...

    def __getitem__(self, index: int | slice) -> Page | tuple[Page, ...]:
        """The page at a zero-based index, negative ones counting from the end, or a slice's pages as a tuple; :class:`IndexError` out of range."""
        if isinstance(index, slice):
            return tuple(self._pages[index])
        return self._pages[index]

    def by_name(self, name: str) -> Page | None:
        """The page called `name`, or None.

        Visio keeps page names unique in a document, so two pages of one name
        are a :class:`~vsdxkit.errors.PackageError` rather than a choice between them.
        """
        matches = [page for page in self._pages if page.name == name]
        if len(matches) > 1:
            raise PackageError(f"the document has {len(matches)} pages called {name!r}; page names are unique in a document")
        return matches[0] if matches else None

    def require_name(self, name: str) -> Page:
        """The page called `name`.

        :raises NotFoundError: if the document has no page called `name`
        :raises PackageError: if the document has two pages called `name`,
            which comes through :meth:`by_name`
        """
        page = self.by_name(name)
        if page is None:
            raise NotFoundError(f"the document has no page called {name!r}")
        return page

    def create(self, name: str | None = None, index: int | None = None) -> Page:
        """Add an empty page, at the end or at `index`, and return it.

        `index` is where the page will sit, from 0 to ``len(pages)``. A name
        the document already uses gets a numeric suffix, and one is made up
        when `name` is None.
        """
        position = _PagePosition.LAST if index is None else self._insertion_index(index)
        return self._lifecycle._add_page_at(position, name)

    def copy(self, page: Page, name: str | None = None, index: int | None = None) -> Page:
        """Copy one of this document's pages, and return the copy.

        The copy goes straight after `page`, or at `index`, from 0 to
        ``len(pages)``. A page of another document is refused: copying pages
        across documents is not supported.
        """
        if page not in self:
            raise InvalidOperationError(
                f"page {page.name!r} belongs to another document; pages can be copied only within their own document"
            )
        position = _PagePosition.AFTER if index is None else self._insertion_index(index)
        return self._lifecycle._copy_page(page, index=position, name=name)

    def delete(self, page: Page) -> None:
        """Remove `page` from the document, with its part, its relationships and its title."""
        if page not in self:
            raise InvalidOperationError(f"page {page.name!r} is not one of this document's pages")
        self._lifecycle._remove_page_by_index(self.index(page))

    def _insertion_index(self, index: int) -> int:
        """`index` as a place to insert a page, from 0 to the number of pages; anything else raises `InvalidOperationError`."""
        # negative indexes are refused rather than read from the end: the
        # document's own page positions use -1 and -2 for LAST and AFTER
        if not 0 <= index <= len(self._pages):
            raise InvalidOperationError(f"page index {index} is outside 0..{len(self._pages)}")
        return index
