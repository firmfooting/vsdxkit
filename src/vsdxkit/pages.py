from __future__ import annotations

import math
import re
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from enum import IntEnum
from typing import TYPE_CHECKING, Protocol, overload

if TYPE_CHECKING:
    from vsdxkit.document import Document
import xml.etree.ElementTree as ET

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

import deprecation

import vsdxkit
from vsdxkit import namespace, r_namespace, relationships, retired_finders
from vsdxkit.connectors import Connect, _create_connector, _float_ends
from vsdxkit.errors import InvalidOperationError, MissingPartError, NotFoundError, PackageError
from vsdxkit.glue import ConnectorOptions, Glue, Routing
from vsdxkit.package import XmlPart
from vsdxkit.partnames import relationship_target, relationships_part_name, target_part_name
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.shape_tree import iter_descendants
from vsdxkit.shapes import Connector, Shape, ShapeCollection, _wrap_children, _wrap_descendants, is_connector, parent_of
from vsdxkit.swimlanes import SwimlaneDiagram, _diagram_on
from vsdxkit.xmlio import PartTree, require_element, to_float, xml_value

# the two places a Connect record names a shape: the connector it leads from,
# and the shape that connector is glued to
_CONNECT_SHEET_ATTRIBUTES = ("FromSheet", "ToSheet")

# how a shape names one of its page's relationships: an image's ForeignData Rel
_RELATIONSHIP_ID = f"{r_namespace}id"

# the cells that size and place a 2-D shape, which a group member ties to its group
_TRANSFORM_CELLS = ("Width", "Height", "LocPinX", "LocPinY", "Angle", "FlipX", "FlipY")

# a formula names another shape on its page as Sheet.5! (Visio) or Sheet5!
_SHEET_REFERENCE = re.compile(r"(?<!!)\bSheet\.?(\d+)!")


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


def _drop_formula(shape: Shape, name: str) -> None:
    """Keep the value just written to a cell and drop its formula, which Visio would recalculate over it on open.

    A prototype's pin can be a formula of the group it sat in, such as
    ``Sheet.9!Width*0.5``.
    """
    cell = shape._cell(name)
    if cell is not None:
        cell.xml.attrib.pop("F", None)


def _left_behind(source: Shape, destination: Page) -> Callable[[str], bool]:
    """Whether a shape id a copy of `source` names is one the copy has left behind.

    A group member's Width can be ``Sheet.9!Width*1``, and at the top level
    Sheet.9 is not its group. On another page every id is another shape's.
    A reference to a shape still beside the copy is left alone.
    """
    if source.page is not destination:
        return lambda _: True
    groups = set()
    parent = source.parent
    while isinstance(parent, Shape):
        groups.add(parent.ID)
        parent = parent.parent
    return groups.__contains__


def _detach(shape: Shape, left_behind: Callable[[str], bool]) -> None:
    """Keep the size a copy had, without the formulas that took it from a shape it has left behind.

    Its own shapes, renumbered with it by the copy, are not left behind.
    """
    own = {element.attrib.get("ID") for element in shape.xml.iter(f"{namespace}Shape")}
    for name in _TRANSFORM_CELLS:
        cell = shape._cell(name)
        formula = None if cell is None else cell.formula
        if formula is None:
            continue
        named = {match.group(1) for match in _SHEET_REFERENCE.finditer(formula)}
        if any(sheet not in own and left_behind(sheet) for sheet in named):
            _drop_formula(shape, name)


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


class PagePosition(IntEnum):
    FIRST = 0
    LAST = -1
    END = -1
    AFTER = -2
    BEFORE = -3


def _page_dimension(cell: ET.Element, name: str) -> float:
    """A page dimension off its PageSheet cell, the way a shape cell is read.

    `to_float` is the one place a ShapeSheet number that is not a number is
    reported; a page's PageWidth is the same kind of cell and was read with a
    bare `float()`, so the same malformed document gave two different errors.
    """
    value = to_float(cell.attrib.get("V"), name)
    return 0.0 if value is None else value


def _pages_root(vis: Document) -> ET.Element:
    """The required root element of the document's pages.xml part."""
    pages_xml = vis.pages_xml
    if pages_xml is None:
        raise MissingPartError("document has no pages.xml part")
    return require_element(pages_xml.getroot(), "Pages root")


class Page:
    """Represents a page or a master page in a vsdx file

    :param vis: the Document object the page belongs to
    :type vis: :class:`Document`
    :param name: the name of the page
    :type name: str
    :param connects: a list of Connect objects in the page
    :type connects: List of :class:`Connect`

    """

    xml: PartTree

    def __init__(self, xml: PartTree, filename: str, page_name: str, page_id: str, rel_id: str, vis: Document):
        self._xml = xml
        self.filename = filename
        self._name = page_name
        self.page_id = page_id
        self.rel_id = rel_id
        self.master_unique_id: str | None = None
        self.master_base_id: str | None = None
        self.rels_xml_filename: str | None = None
        self._rels_xml: PartTree | None = None
        self.vis = vis
        self._max_id = 0  # ID high-water mark, maintained by Document's ID allocator
        # todo: add page id - from pages_xml - PageSheet[ID]

    def __repr__(self):
        return f"<Page name={self.name} file={self.filename} >"

    @property
    def connects(self) -> list[Connect]:
        return self.get_connects()

    @deprecation.deprecated(
        deprecated_in="v0.5.0",
        removed_in="1.0.0",
        current_version=vsdxkit.__version__,
        details="Use Page.name property instead",
    )
    def set_name(self, value: str) -> None:
        # the `name` setter edits the store's own pages.xml tree, Name and NameU
        # both; this used to go on to overwrite that tree with a fresh parse
        # carrying only Name, which left NameU with the old name
        self.name = value

    @property
    def name(self) -> str:
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
        self.vis._rename_page_in_app_xml(previous, value)

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
        pages = _pages_root(self.vis).findall(f"{namespace}Page")
        return require_element(pages[index] if index < len(pages) else None, f"Page[{index + 1}]")

    @property
    def background(self) -> bool:
        return self._page_xml().attrib.get("Background", "0") != "0"

    @background.setter
    def background(self, value: bool) -> None:
        self._page_xml().attrib["Background"] = "1" if value else "0"

    def _get_page_name(self) -> str:
        return self.name

    def _set_page_name(self, value: str) -> None:
        self.name = value

    # built explicitly: the deprecation wrapper returns a plain function, so it
    # cannot be composed with @property/@x.setter (type checkers lose the setter)
    page_name = property(
        deprecation.deprecated(
            deprecated_in="v0.5.0", removed_in="1.0.0", current_version=vsdxkit.__version__, details="Use Page.name instead"
        )(_get_page_name),
        deprecation.deprecated(
            deprecated_in="v0.5.0", removed_in="1.0.0", current_version=vsdxkit.__version__, details="Use Page.name instead"
        )(_set_page_name),
        doc="Deprecated alias for :attr:`Page.name`.",
    )

    @property
    def is_master_page(self) -> bool:
        """Return True if this page has a master unique id and there is a match in masters xml"""
        if self.vis.masters_xml is not None and self.master_unique_id:
            master_match = f'{namespace}Master[@UniqueID="{self.master_unique_id}"]'
            master_element = self.vis.masters_xml.find(master_match)
            return master_element is not None
        return False

    @property
    def _pagesheet_xml(self) -> ET.Element:
        # get PageSheet element from pages_xml based on page_id
        ps = _pages_root(self.vis).find(f'{namespace}Page[@ID="{self.page_id}"]/{namespace}PageSheet')
        if not isinstance(ps, ET.Element):
            masters_xml = self.vis.masters_xml
            if masters_xml is not None:
                ps = masters_xml.find(f'{namespace}Master[@ID="{self.page_id}"]/{namespace}PageSheet')
        return require_element(ps, f"PageSheet for page_id={self.page_id}")

    def _pagesheet_cell(self, name: str) -> ET.Element:
        """A named Cell element on this page's PageSheet."""
        return require_element(self._pagesheet_xml.find(f'{namespace}Cell[@N="{name}"]'), f"PageSheet Cell {name}")

    @property
    def width(self) -> float:
        return _page_dimension(self._pagesheet_cell("PageWidth"), "PageWidth")

    @width.setter
    def width(self, value: float | str | None) -> None:
        self._pagesheet_cell("PageWidth").attrib["V"] = _dimension_value(value)

    @property
    def height(self) -> float:
        return _page_dimension(self._pagesheet_cell("PageHeight"), "PageHeight")

    @height.setter
    def height(self, value: float | str | None) -> None:
        self._pagesheet_cell("PageHeight").attrib["V"] = _dimension_value(value)

    @property
    def xml(self) -> PartTree:
        return self._xml

    @xml.setter
    def xml(self, value: PartTree | None) -> None:
        if value is None:
            raise InvalidOperationError(
                f"Page.xml cannot be set to None: {self.filename} cannot be removed through "
                f"this property, because pages.xml, pages.xml.rels and the content-type "
                f"override would still name it"
            )
        attached = self._attached()
        self._xml = value
        if attached:
            self.vis._set_part_xml(self.filename, value)

    def _holds(self, filename: str, tree: PartTree | None) -> bool:
        """Whether the package's part at `filename` is `tree` itself."""
        held = self.vis._package.part(filename)
        return isinstance(held, XmlPart) and held.tree is tree

    def _attached(self) -> bool:
        """Whether an assignment to `xml` may write this page's part.

        A caller may keep holding a `Page` after it has been removed from the
        document (`Document.remove_page_by_index`); a later assignment to its
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
        if self._holds(self.filename, self._xml):
            return True
        return self.vis._package.part(self.filename) is None and any(page is self for page in self.vis.pages)

    def _rels_attached(self) -> bool:
        """Whether an assignment to `rels_xml` may write this page's relationship part.

        Only while the page itself is attached, and only over the relationship
        part the page holds -- or where the package holds none yet, which is
        how one is first created. A removed page's rels name is freed along
        with its page's, and the page that takes the name must not be given
        the removed page's relationships.
        """
        if self.rels_xml_filename is None or not self._attached():
            return False
        held = self.vis._package.part(self.rels_xml_filename)
        if held is None:
            return True
        return isinstance(held, XmlPart) and held.tree is self._rels_xml

    @property
    def rels_xml(self) -> PartTree | None:
        return self._rels_xml

    @rels_xml.setter
    def rels_xml(self, value: PartTree | None) -> None:
        # None takes the rels part out of the package as well: the save writes
        # whatever the store holds, so a part left behind would reach the file
        attached = self._rels_attached()
        self._rels_xml = value
        if attached:
            assert self.rels_xml_filename is not None  # _rels_attached() says so
            self.vis._set_part_xml(self.rels_xml_filename, value)

    @property
    def shapes(self) -> ShapeCollection:
        """Every shape on the page, at any depth, connectors included: depth first, parents first."""
        return ShapeCollection(lambda: self.all_shapes, self._scope)

    @property
    def children(self) -> ShapeCollection:
        """The page's top-level shapes."""
        return ShapeCollection(lambda: self.child_shapes, self._scope)

    def _scope(self) -> str:
        return f"page {self.name!r}"

    @deprecation.deprecated(
        deprecated_in="0.5.0",
        removed_in="1.0.0",
        current_version=vsdxkit.__version__,
        details="Use Page.child_shapes property to access top level shapes of a Page",
    )
    def sub_shapes(self) -> list[Shape]:
        return self.child_shapes

    @property
    def child_shapes(self) -> list[Shape]:
        """Return list of Shape objects at top level of Document.Page

        :returns: list of `Shape` objects
        :rtype: List[Shape]
        """
        root = self.xml.getroot()
        return [] if root is None else _wrap_children(root, self, self)

    def _set_max_ids(self) -> None:
        """Raise this page's ID high-water mark to cover every shape now on it.

        Private plumbing for ``Document.increment_shape_ids()``, which calls it
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
        # return zero-based index of this page in parent Document.pages list
        return self.vis.pages.index(self) if self in self.vis.pages else None

    def add_connect(self, connect: Connect) -> None:
        connects = self.xml.find(f".//{namespace}Connects")
        if connects is None:
            connects = ET.fromstring(
                f"<Connects xmlns='{namespace[1:-1]}' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'/>"
            )
            root = require_element(self.xml.getroot(), "page root")
            root.append(connects)
            connects = require_element(self.xml.find(f".//{namespace}Connects"), "Connects")
        connects.append(connect.xml)

    def _ensure_page_master_rel(self, master_part_name: str) -> None:
        """Ensure this page's rels relate it to the master part named `master_part_name`.

        Visio writes a per-page relationship to each master used by shapes on
        that page. The Target is derived from the master's part name, so a
        master kept in a subfolder of the masters folder is reached there. The
        id comes from this page's own rels part: `masters.xml.rels` is a
        different id space, and an id free there says nothing here (#357). The
        rels part is created on demand; assigning it writes it into the package.
        """
        relationships.append_if_absent(
            self._rels_root(),
            rel_type="http://schemas.microsoft.com/visio/2010/relationships/master",
            target=relationship_target(self.filename, master_part_name),
        )

    def _rels_root(self) -> ET.Element:
        """This page's `<Relationships>` element, creating the part on demand; assigning it writes it into the package."""
        rels_xml: PartTree | None = self.rels_xml
        if rels_xml is None:
            self.rels_xml_filename = relationships_part_name(self.filename)
            rels_xml = ET.ElementTree(
                ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
            )
            self.rels_xml = rels_xml
        return require_element(rels_xml.getroot(), f"{self.rels_xml_filename} root")

    def _carry_relationships(self, copied: ET.Element, source: Page) -> None:
        """Relate this page to what each ``r:id`` in `copied` names on `source`, and point the copy at it.

        An image or embedded object reaches its part through its page's
        relationships, by an id that means nothing on another page. Within one
        document the part is shared, so the copy needs only a relationship of
        its own to the same part.
        """
        source_rels = source.rels_xml
        if source_rels is None:
            return
        by_id = {rel.attrib.get("Id"): rel for rel in relationships.all_of(source_rels.getroot())}
        for node in copied.iter():
            relationship = by_id.get(node.attrib.get(_RELATIONSHIP_ID))
            if relationship is None:
                continue  # none, or already dangling on the source page
            mode = relationship.attrib.get("TargetMode")
            target = relationship.attrib.get("Target", "")
            if mode != "External":
                target = relationship_target(self.filename, target_part_name(source.filename, target))
            carried = relationships.append_if_absent(
                self._rels_root(), rel_type=relationship.attrib.get("Type", ""), target=target, mode=mode
            )
            node.attrib[_RELATIONSHIP_ID] = carried.attrib["Id"]

    def get_connects(self) -> list[Connect]:
        elements = self.xml.findall(f".//{namespace}Connect")  # search recursively
        connects = [Connect(xml=e, page=self) for e in elements]
        return connects

    def apply_text_context(self, context: dict[str, object]) -> None:
        for shape in self.child_shapes:
            shape.apply_text_filter(context)

    def find_replace(self, old: str, new: str) -> None:
        for shape in self.child_shapes:
            shape.find_replace(old, new)

    @property
    def all_shapes(self) -> list[Shape]:
        """Every shape on the page, at any depth, depth first and parents first."""
        root = self.xml.getroot()
        return [] if root is None else _wrap_descendants(root, self, self)

    def find_shape_by_id(self, shape_id: str) -> Shape | None:
        """The first shape on the page with this ID, or None. Deprecated: use ``page.shapes.by_id(shape_id)``."""
        retired_finders.warn("Page.find_shape_by_id", "page.shapes.by_id(shape_id)")
        return retired_finders.first_by_id(self.shapes, shape_id)

    def find_shapes_by_id(self, shape_id: str) -> list[Shape]:
        """Every shape on the page with this ID. Deprecated: IDs are unique on a page, so use ``page.shapes.by_id(shape_id)``."""
        retired_finders.warn("Page.find_shapes_by_id", "page.shapes.by_id(shape_id)")
        return retired_finders.all_by_id(self.shapes, shape_id)

    def find_shape_by_attr(self, attr: str, attr_value: str) -> Shape | None:
        """The first shape on the page whose XML attribute `attr` is `attr_value`, or None. Deprecated."""
        retired_finders.warn("Page.find_shape_by_attr", "a comprehension over page.shapes")
        return retired_finders.first_by_attr(self.shapes, attr, attr_value)

    def find_shape_by_text(self, text: str) -> Shape | None:
        """The first shape on the page whose text contains `text`, or None.

        Deprecated: ``page.shapes.by_text(text)`` matches the whole text and refuses
        more than one match; for a substring, filter ``page.shapes`` directly.
        """
        retired_finders.warn("Page.find_shape_by_text", "page.shapes.by_text(text), which matches the whole text")
        return retired_finders.first_by_text(self.shapes, text)

    def find_shapes_by_text(self, text: str) -> list[Shape]:
        """Every shape on the page whose text contains `text`.

        Deprecated: ``page.shapes.matching_text(text)`` matches the whole text; for a
        substring, filter ``page.shapes`` directly.
        """
        retired_finders.warn("Page.find_shapes_by_text", "page.shapes.matching_text(text), which matches the whole text")
        return retired_finders.all_by_text(self.shapes, text)

    def find_shapes_by_regex(self, regex: str) -> list[Shape]:
        """Every shape on the page whose text `regex` matches. Deprecated: filter ``page.shapes`` directly."""
        retired_finders.warn("Page.find_shapes_by_regex", "a comprehension over page.shapes")
        return retired_finders.all_by_regex(self.shapes, regex)

    def find_shape_by_property_label(self, property_label: str) -> Shape | None:
        """The first shape on the page with this Shape Data label, or None. Deprecated: use ``page.shapes.by_property(label)``."""
        retired_finders.warn("Page.find_shape_by_property_label", "page.shapes.by_property(label)")
        return retired_finders.first_by_property(self.shapes, property_label)

    def find_shapes_by_property_label(self, property_label: str, shapes: list[Shape] | None = None) -> list[Shape]:
        """Every shape on the page with this Shape Data label. Deprecated: use ``page.shapes.matching_property(label)``.

        `shapes` was never read, and still is not.
        """
        retired_finders.warn("Page.find_shapes_by_property_label", "page.shapes.matching_property(label)")
        return retired_finders.all_by_property(self.shapes, property_label)

    def find_shape_by_property_label_value(self, property_label: str, property_value: str) -> Shape | None:
        """The first shape on the page whose property `property_label` is `property_value`, or None.

        Deprecated: use ``page.shapes.by_property(label, value)``.
        """
        retired_finders.warn("Page.find_shape_by_property_label_value", "page.shapes.by_property(label, value)")
        return retired_finders.first_by_property(self.shapes, property_label, property_value)

    def find_shapes_by_property_label_value(
        self, property_label: str, property_value: str, shapes: list[Shape] | None = None
    ) -> list[Shape]:
        """Every shape on the page whose property `property_label` is `property_value`.

        Deprecated: use ``page.shapes.matching_property(label, value)``. `shapes` was
        never read, and still is not.
        """
        retired_finders.warn("Page.find_shapes_by_property_label_value", "page.shapes.matching_property(label, value)")
        return retired_finders.all_by_property(self.shapes, property_label, property_value)

    def find_shapes_with_same_master(self, shape: Shape) -> list[Shape]:
        """Every shape on the page instancing `shape`'s master shape. Deprecated: filter ``page.shapes`` directly."""
        retired_finders.warn("Page.find_shapes_with_same_master", "a comprehension over page.shapes")
        return retired_finders.all_by_master(self.shapes, shape.master_page_ID, shape.master_shape_ID)

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

        :param glue: :attr:`Glue.DYNAMIC` walks each end round its shape to the
            nearest side; :attr:`Glue.POINT` glues the ends to ``from_point``
            and ``to_point``, 0-based rows of each shape's ``Connection`` section
        :param routing: the path between the ends; :attr:`Routing.DEFAULT` is Visio's own
        :raises InvalidOperationError: a shape is not on this page, or a connection point does not exist;
            nothing is written
        :returns: the new connector
        """
        options = ConnectorOptions(glue=glue, routing=routing, from_point=from_point, to_point=to_point)
        return _create_connector(self, source, target, options)

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
        by :meth:`Shape.copy`, the one way a shape is created.

        A 1-D shape, such as :attr:`ShapeKind.LINE`, is placed by its ends: it
        keeps its direction, and ``width`` is its length.

        :param width, height: the new size; the kind's or prototype's when omitted
        :param text: the label. A kind starts blank; a prototype keeps its text when omitted.
        :raises TypeError: if ``kind_or_prototype`` is neither a kind nor a shape
        :raises InvalidOperationError: if a prototype belongs to another document
        :returns: the new shape
        """
        # vsdxkit.media opens its donors as Documents, which import this
        # module, so importing it at module level would be a cycle
        from vsdxkit import media

        if not self._attached():
            raise InvalidOperationError(f"page {self.name!r} is no longer in its document, so nothing can be created on it")
        if isinstance(kind_or_prototype, ShapeKind):
            source = media._kind_shape(kind_or_prototype)
        elif isinstance(kind_or_prototype, Shape):
            kind_or_prototype._require_attached("Page.create_shape()")
            if kind_or_prototype.page.vis is not self.vis:
                raise InvalidOperationError(
                    f"shape ID {kind_or_prototype.ID} belongs to another document; "
                    "a prototype must come from the document it is copied into"
                )
            source = kind_or_prototype
        else:
            kinds = ", ".join(f"ShapeKind.{kind.name}" for kind in ShapeKind)
            raise TypeError(f"create_shape takes a Shape or one of {kinds}, not {kind_or_prototype!r}")
        one_d = is_connector(source)
        if one_d and height is not None:
            raise InvalidOperationError(f"shape ID {source.ID} is 1-D, so it has no height to set; its width is its length")
        # what the copy's formulas may no longer name: the groups the prototype
        # sat in, and on another page, every shape of the page it left
        left_behind = _left_behind(source, self)
        if isinstance(kind_or_prototype, ShapeKind):
            shape = media.copy_kind(kind_or_prototype, self)
            label = "" if text is None else text
        else:
            shape = kind_or_prototype.copy(self)
            label = text
        if one_d:
            _place_one_d(shape, x, y, width)
        else:
            # a 2-D shape is drawn around its pin
            shape.get_or_create_cell("PinX", v=str(x))
            shape.get_or_create_cell("PinY", v=str(y))
            _drop_formula(shape, "PinX")
            _drop_formula(shape, "PinY")
            _detach(shape, left_behind)
            if width is not None:
                shape.width = width
                _drop_formula(shape, "Width")
        if height is not None:
            shape.height = height
            _drop_formula(shape, "Height")
        if width is not None or height is not None:
            # LocPinX is Width*0.5 and the geometry scales with the size: their
            # values would otherwise describe the old size until Visio opens it
            shape._refresh_formula_values()
        if label is not None:
            shape.text = label
        return shape

    def delete_shape(self, shape: Shape) -> None:
        """Delete a shape from this page, removing any incident connectors.

        A group takes its children with it, so connectors glued to a child and
        records naming one are removed alongside the group's own. Connectors
        are deleted first (including their Connect records), then the shape.

        :raises NotFoundError: if the shape is not on this page
        """
        shape_id = str(shape.ID)
        # Identity, not id: Visio shape ids are page-scoped and collide freely
        # across pages, so matching on the number would accept a shape from a
        # different page and then delete whichever shape here shared its id.
        # Silently doing nothing would instead hide a double delete.
        # all_shapes walks the page and builds a Shape per element, so gather
        # both answers in one pass.
        on_this_page: list[Shape] = []
        id_is_taken_by_another_shape = False
        for candidate in self.all_shapes:
            if candidate.xml is shape.xml:
                on_this_page.append(candidate)
            elif str(candidate.ID) == shape_id:
                id_is_taken_by_another_shape = True
        if not on_this_page:
            # naming only the id would send a caller looking for it, finding a
            # different shape wearing the same number, and concluding the
            # library is wrong
            collision = (
                f"; a different shape on this page has id {shape.ID}, because ids are page-scoped"
                if id_is_taken_by_another_shape
                else ""
            )
            raise NotFoundError(f"shape ID {shape.ID} is not on page {self.name!r}{collision}")
        # every id that is about to disappear: the shape and, for a group,
        # everything it contains
        self._delete(on_this_page, {shape_id} | {str(s.ID) for s in shape.all_shapes})

    def _delete(self, shapes: Iterable[Shape], gone_ids: set[str]) -> None:
        """The one deletion: `shapes`, the connectors glued to any of `gone_ids`, and every record naming them.

        `gone_ids` are the shapes going away: those in `shapes` and everything
        inside them, and any already gone from the XML by another route, such
        as a Jinja ``showif`` that rendered them out. A Shape held for any of
        them is detached afterwards, since attachment is read from the XML.
        """
        # connectors are the FromSheet of Connect records whose ToSheet is one
        # of the shapes going, on a begin/end relationship
        connector_ids = {c.from_id for c in self.connects if c.to_id in gone_ids and c.from_rel in ("BeginX", "EndX")}
        doomed = set(shapes)
        for s in self.all_shapes:
            # the master too: a connector may inherit BeginX from it, and one
            # missed here survives as a detached line whose glue record has just
            # been removed
            if str(s.ID) in connector_ids and is_connector(s):
                doomed.add(s)
        for s in doomed:
            self._remove_shape_xml(s)
        # a record naming a group child outlives the child otherwise: the child
        # goes with the group element rather than through _remove_shape_xml
        self.remove_connect_records(gone_ids, match="either")

    def _remove_shape_xml(self, shape: Shape) -> None:
        """Remove a shape's xml and every Connect record that names it.

        Records naming the shape on either side go: one pointing *at* a shape
        that is gone dangles just as surely as one leading from it. Connectors
        glued to the shape are separate shapes and are passed through here in
        their own right by :meth:`delete_shape`.
        """
        self.remove_connect_records({str(shape.ID)}, match="either")
        container = parent_of(self.xml.getroot(), shape.xml)
        if container is not None:
            container.remove(shape.xml)

    def remove_connect_records(self, connector_ids: Iterable[str | int], *, match: str = "from") -> None:
        """Remove Connect records naming any of these shapes.

        Single record-removal path, shared by the delete cascade and connector
        retargeting. ``match="from"`` removes only the records leading from
        these shapes, which is what retargeting wants: it is replacing a
        connector's own glue. ``match="either"`` also removes records pointing
        at them, for a shape that is going away entirely.
        """
        if match not in ("from", "either"):
            raise ValueError(f"match must be 'from' or 'either', not {match!r}")
        connects_el = self.xml.find(f".//{namespace}Connects")
        if connects_el is None:
            return
        normalised_ids = {str(connector_id) for connector_id in connector_ids}
        attributes = ("FromSheet",) if match == "from" else _CONNECT_SHEET_ATTRIBUTES
        for connect in list(connects_el):
            if normalised_ids & {connect.attrib.get(attribute) for attribute in attributes}:
                connects_el.remove(connect)

    def _remap_connect_records(self, id_map: Mapping[str, int]) -> None:
        """Point the records at the new ids of shapes this page has renumbered.

        Shape ids live in two places: the ``Sheet.N!`` references inside cell
        formulas, which ``Document.update_ids`` rewrites, and the ``FromSheet``
        and ``ToSheet`` attributes here. Records left behind when a shape is
        renumbered name an id that is no longer on the page, and Visio rebinds
        glue like that silently.

        Private plumbing for ``Document.renumber_shape_ids()``, which runs this
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

        Read off the elements rather than through ``all_shapes``, which builds a
        ``Shape`` per element to answer a question about the xml.
        """
        root = self.xml.getroot()
        return {shape_id for element in iter_descendants(root) if (shape_id := element.attrib.get("ID"))}


class PageLifecycle(Protocol):
    """What a :class:`PageCollection` needs from the document that owns its pages."""

    def add_page_at(self, index: int, name: str | None = None) -> Page: ...

    def copy_page(self, page: Page, *, index: int | PagePosition = ..., name: str | None = None) -> Page: ...

    def remove_page_by_index(self, index: int) -> None: ...


class PageCollection(Sequence[Page]):
    """A document's pages, in order, and the one place pages are created, copied and deleted.

    A sequence: ``len``, iteration, indexing (negative indexes too), ``in``
    and ``index`` behave as they do on a tuple. It is live: a page added or
    removed through any route is seen by a collection taken before.
    """

    def __init__(self, pages: list[Page], lifecycle: PageLifecycle) -> None:
        self._pages = pages
        self._lifecycle = lifecycle

    def __repr__(self) -> str:
        return f"<PageCollection {[page.name for page in self._pages]!r}>"

    def __len__(self) -> int:
        return len(self._pages)

    @override
    def __iter__(self) -> Iterator[Page]:
        return iter(list(self._pages))

    @overload
    def __getitem__(self, index: int) -> Page: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[Page, ...]: ...

    def __getitem__(self, index: int | slice) -> Page | tuple[Page, ...]:
        if isinstance(index, slice):
            return tuple(self._pages[index])
        return self._pages[index]

    def by_name(self, name: str) -> Page | None:
        """The page called `name`, or None.

        Visio keeps page names unique in a document, so two pages of one name
        are a :class:`PackageError` rather than a choice between them.
        """
        matches = [page for page in self._pages if page.name == name]
        if len(matches) > 1:
            raise PackageError(f"the document has {len(matches)} pages called {name!r}; page names are unique in a document")
        return matches[0] if matches else None

    def require_name(self, name: str) -> Page:
        """The page called `name`."""
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
        position = PagePosition.LAST if index is None else self._insertion_index(index)
        return self._lifecycle.add_page_at(position, name)

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
        position = PagePosition.AFTER if index is None else self._insertion_index(index)
        return self._lifecycle.copy_page(page, index=position, name=name)

    def delete(self, page: Page) -> None:
        """Remove `page` from the document, with its part, its relationships and its title."""
        if page not in self:
            raise InvalidOperationError(f"page {page.name!r} is not one of this document's pages")
        self._lifecycle.remove_page_by_index(self.index(page))

    def _insertion_index(self, index: int) -> int:
        # negative indexes are refused rather than read from the end: the
        # document's own page positions use -1 to -3 for LAST, AFTER and BEFORE
        if not 0 <= index <= len(self._pages):
            raise InvalidOperationError(f"page index {index} is outside 0..{len(self._pages)}")
        return index
