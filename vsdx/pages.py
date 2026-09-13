from __future__ import annotations

import math
from collections.abc import Iterable
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .vsdxfile import VisioFile
import io
import xml.etree.ElementTree as ET

import deprecation

import vsdx

# from .vsdxfile import file_to_xml  # todo: refactor this away - defined in set_name() to break circular imports
from vsdx import namespace

from .connectors import Connect
from .shapes import Shape
from .xmlio import require_element, xml_value


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


class PagePosition(IntEnum):
    FIRST = 0
    LAST = -1
    END = -1
    AFTER = -2
    BEFORE = -3


def _pages_root(vis: VisioFile) -> ET.Element:
    """The required root element of the document's pages.xml part."""
    pages_xml = vis.pages_xml
    if pages_xml is None:
        raise ValueError("document has no pages.xml part")
    return require_element(pages_xml.getroot(), "Pages root")


class Page:
    """Represents a page or a master page in a vsdx file

    :param vis: the VisioFile object the page belongs to
    :type vis: :class:`VisioFile`
    :param name: the name of the page
    :type name: str
    :param connects: a list of Connect objects in the page
    :type connects: List of :class:`Connect`

    """

    xml: ET.ElementTree[ET.Element]

    def __init__(
        self, xml: ET.ElementTree[ET.Element], filename: str, page_name: str, page_id: str, rel_id: str, vis: VisioFile
    ):
        self._xml = xml
        self.filename = filename
        self._name = page_name
        self._background: bool | None = None
        self.page_id = page_id
        self.rel_id = rel_id
        self.master_unique_id: str | None = None
        self.master_base_id: str | None = None
        self.rels_xml_filename: str | None = None
        self.rels_xml: ET.ElementTree[ET.Element] | None = None
        self.vis = vis
        self.max_id = 0
        # todo: add page id - from pages_xml - PageSheet[ID]

    def __repr__(self):
        return f"<Page name={self.name} file={self.filename} >"

    @property
    def connects(self) -> list[Connect]:
        return self.get_connects()

    @deprecation.deprecated(
        deprecated_in="v0.5.0", removed_in="1.0.0", current_version=vsdx.__version__, details="Use Page.name property instead"
    )
    def set_name(self, value: str) -> None:
        from .vsdxfile import file_to_xml  # to break circular imports - is this really needed?

        pages_filename = self.vis._pages_filename()  # pages contains Page name, width, height, mapped to Id
        pages = file_to_xml(
            pages_filename, self.vis.zip_file_contents
        )  # this contains a list of pages with rel_id and filename
        if pages is None:
            raise ValueError(f"no pages.xml part found at {pages_filename}")
        pages_root = require_element(pages.getroot(), "Pages root")
        page = pages_root.find(f"{namespace}Page[{self._index() + 1}]")
        if page:
            page.attrib["Name"] = value
            self.name = value
            self.vis.pages_xml = pages

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
        page = self._page_xml()
        page.attrib["Name"] = value
        page.attrib["NameU"] = value
        self._name = value

    def _index(self) -> int:
        """Zero-based index of this page in its VisioFile (required)."""
        index = self.index_num
        if index is None:
            raise ValueError("page is not attached to a VisioFile")
        return index

    def _page_xml(self) -> ET.Element:
        """The Pages/Page element for this page (from pages.xml)."""
        root = _pages_root(self.vis)
        position = self._index() + 1
        return require_element(root.find(f"{namespace}Page[{position}]"), f"Page[{position}]")

    @property
    def background(self) -> bool:
        if self._background is not None:
            return self._background
        bg = self._page_xml().attrib.get("Background", "0") != "0"
        self._background = bg
        return self._background

    @background.setter
    def background(self, value: bool) -> None:
        self._page_xml().attrib["Background"] = "1" if value else "0"
        self._background = value

    def _get_page_name(self) -> str:
        return self.name

    def _set_page_name(self, value: str) -> None:
        self.name = value

    # built explicitly: the deprecation wrapper returns a plain function, so it
    # cannot be composed with @property/@x.setter (type checkers lose the setter)
    page_name = property(
        deprecation.deprecated(
            deprecated_in="v0.5.0", removed_in="1.0.0", current_version=vsdx.__version__, details="Use Page.name instead"
        )(_get_page_name),
        deprecation.deprecated(
            deprecated_in="v0.5.0", removed_in="1.0.0", current_version=vsdx.__version__, details="Use Page.name instead"
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
        return float(self._pagesheet_cell("PageWidth").attrib.get("V", 0.0))

    @width.setter
    def width(self, value: float | str | None) -> None:
        self._pagesheet_cell("PageWidth").attrib["V"] = _dimension_value(value)

    @property
    def height(self) -> float:
        return float(self._pagesheet_cell("PageHeight").attrib.get("V", 0.0))

    @height.setter
    def height(self, value: float | str | None) -> None:
        self._pagesheet_cell("PageHeight").attrib["V"] = _dimension_value(value)

    @property
    def xml(self) -> ET.ElementTree[ET.Element]:
        return self._xml

    @xml.setter
    def xml(self, value: ET.ElementTree[ET.Element]) -> None:
        self._xml = value

    @property
    def _shapes(self) -> list[Shape]:
        """Return a list of :class:`Shape` objects - for each 'Shapes'

        Note: typically returns one :class:`Shape` object which itself contains :class:`Shape` objects

        """
        return [Shape(xml=shapes, parent=self, page=self) for shapes in self.xml.findall(f"{namespace}Shapes")] or []

    @property
    @deprecation.deprecated(
        deprecated_in="0.5.0",
        removed_in="1.0.0",
        current_version=vsdx.__version__,
        details="Use Page.child_shapes property to access top level shapes of a Page",
    )
    def shapes(self) -> list[Shape]:
        """Return a list of :class:`Shape` objects

        Note: typically returns one :class:`Shape` object which itself contains :class:`Shape` objects

        """
        return [Shape(xml=shapes, parent=self, page=self) for shapes in self.xml.findall(f"{namespace}Shapes")]

    @deprecation.deprecated(
        deprecated_in="0.5.0",
        removed_in="1.0.0",
        current_version=vsdx.__version__,
        details="Use Page.child_shapes property to access top level shapes of a Page",
    )
    def sub_shapes(self) -> list[Shape]:
        return self.child_shapes

    @property
    def child_shapes(self) -> list[Shape]:
        """Return list of Shape objects at top level of VisioFile.Page

        :returns: list of `Shape` objects
        :rtype: List[Shape]
        """
        # note that self.shapes should always return a single shape
        shapes = self._shapes
        if shapes:
            return shapes[0].child_shapes
        return []  # empty list if no top shapes object

    def set_max_ids(self) -> int:
        # get maximum shape id from xml in page
        for shapes in self._shapes:
            for shape in shapes.child_shapes:
                id = shape.get_max_id()
                if id > self.max_id:
                    self.max_id = id

        return self.max_id

    @property
    def index_num(self) -> int | None:
        # return zero-based index of this page in parent VisioFile.pages list
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

    def _ensure_page_master_rel(self, master_rel_id: str, master_part_name: str):
        """Ensure this page's rels reference the given master part.

        Visio writes a per-page relationship to each master used by shapes on
        that page (Target '../masters/masterN.xml'). The rels part is created
        on demand; the filename is registered so save_vsdx persists it.
        """
        if self.rels_xml is None:
            rels_filename = self.filename.replace("visio/pages/", "visio/pages/_rels/") + ".rels"
            self.rels_xml_filename = rels_filename
            self.rels_xml = ET.ElementTree(
                ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
            )
        rels_root = self.rels_xml.getroot()
        assert rels_root is not None
        existing = {r.attrib.get("Target") for r in rels_root}
        target = f"../masters/{master_part_name}"
        if target in existing:
            return
        rel_element = ET.fromstring(
            f'<Relationship xmlns="http://schemas.openxmlformats.org/package/2006/relationships" '
            f'Type="http://schemas.microsoft.com/visio/2010/relationships/master" '
            f'Id="{master_rel_id}" Target="{target}"/>'
        )
        rels_root.append(rel_element)
        # persist into the zip contents so save picks it up even for pages
        # that never had a rels part before
        if self.rels_xml_filename:
            self.vis.zip_file_contents[self.rels_xml_filename] = io.BytesIO(
                ET.tostring(rels_root, xml_declaration=True, encoding="UTF-8")
            )

    def get_connects(self) -> list[Connect]:
        elements = self.xml.findall(f".//{namespace}Connect")  # search recursively
        connects = [Connect(xml=e, page=self) for e in elements]
        return connects

    def get_connectors_between(
        self, shape_a_id: str = "", shape_a_text: str = "", shape_b_id: str = "", shape_b_text: str = ""
    ) -> set[Shape]:
        shape_a = self.find_shape_by_id(shape_a_id) if shape_a_id else self.find_shape_by_text(shape_a_text)
        shape_b = self.find_shape_by_id(shape_b_id) if shape_b_id else self.find_shape_by_text(shape_b_text)
        if shape_a is None or shape_b is None:
            raise ValueError("get_connectors_between() requires two shapes that exist on this page")
        connector_ids = {a.ID for a in shape_a.connected_shapes}.intersection({b.ID for b in shape_b.connected_shapes})

        connectors: set[Shape] = set()
        for connector_id in connector_ids:
            found = self.find_shape_by_id(connector_id or "")
            if found is not None:
                connectors.add(found)
        return connectors

    def apply_text_context(self, context: dict[str, object]) -> None:
        for s in self._shapes:
            s.apply_text_filter(context)

    def find_replace(self, old: str, new: str) -> None:
        for s in self._shapes:
            s.find_replace(old, new)

    def find_shape_by_id(self, shape_id: str) -> Shape | None:
        for s in self._shapes:
            found = s.find_shape_by_id(shape_id)
            if found:
                return found

    def _find_shapes_by_id(self, shape_id: str) -> list[Shape]:
        # return all shapes by ID - should only be used internally where ID is not unique (i.e. copying shapes)
        found = list()
        for s in self._shapes:
            found = s.find_shapes_by_id(shape_id)
            if found:
                return found
        return found

    def find_shape_by_attr(self, attr: str, attr_value: str) -> Shape | None:
        for s in self._shapes:
            found = s.find_shape_by_attr(attr, attr_value)
            if found:
                return found

    def find_shapes_with_same_master(self, shape: Shape) -> list[Shape]:
        # return all shapes with master
        return [
            s
            for s in self.all_shapes
            if s.master_shape_ID == shape.master_shape_ID and s.master_page_ID == shape.master_page_ID
        ]

    def find_shape_by_text(self, text: str) -> Shape | None:
        for s in self._shapes:
            found = s.find_shape_by_text(text)
            if found:
                return found

    def find_shapes_by_text(self, text: str) -> list[Shape]:
        shapes = list()
        for s in self._shapes:
            found = s.find_shapes_by_text(text)
            if found:
                shapes.extend(found)
        return shapes

    def find_shapes_by_regex(self, regex: str) -> list[Shape]:
        """Search for shapes in this page's top shape by regex"""
        return self._shapes[0].find_shapes_by_regex(regex) if len(self._shapes) else []

    @property
    def all_shapes(self) -> list[Shape]:
        # return all shapes in page
        shapes = self._shapes
        return shapes[0].all_shapes if shapes else []

    def find_shape_by_property_label(self, property_label: str) -> Shape | None:
        """Search for shapes in this page's top shape by property label"""
        # note: use label rather than name as label is more easily visible in diagram
        return self._shapes[0].find_shape_by_property_label(property_label) if len(self._shapes) else None

    def find_shapes_by_property_label(self, property_label: str) -> list[Shape]:
        # return all matching shapes with property label
        shapes = list()
        for s in self._shapes:
            found = s.find_shapes_by_property_label(property_label)
            if found:
                shapes.extend(found)
        return shapes

    def find_shape_by_property_label_value(self, property_label: str, property_value: str) -> Shape | None:
        # return first matching shape with label
        # note: use label rather than name as label is more easily visible in diagram
        for s in self._shapes:
            found = s.find_shape_by_property_label_value(property_label, property_value)
            if found:
                return found

    def find_shapes_by_property_label_value(self, property_label: str, property_value: str) -> list[Shape]:
        # return all matching shapes with property label and value
        shapes = list()
        for s in self._shapes:
            found = s.find_shapes_by_property_label_value(property_label, property_value)
            if found:
                shapes.extend(found)
        return shapes

    def connect_shapes(
        self, from_shape: Shape, to_shape: Shape, route: str = "dynamic", from_cp: int = 0, to_cp: int = 0
    ) -> Shape:
        """Create a Visio-faithful dynamic connector between two shapes on this page.

        route: 'dynamic' (shape glue, default), 'point' (connection-point glue
        using from_cp/to_cp 0-based connection point indexes), optionally with
        routing behaviour 'straight', 'rightangle' or 'curved' - e.g.
        route='straight' or route='point|curved'.

        :returns: the new connector Shape
        :rtype: Shape
        """
        return vsdx.Connect.create(
            page=self, from_shape=from_shape, to_shape=to_shape, route=route, from_cp=from_cp, to_cp=to_cp
        )

    def get_container(self) -> vsdx.Container | None:
        """Return the page's CFF Container (swimlane diagram root), or None."""
        return vsdx.Container.find(self)

    def add_swimlane(self, label: str | None = None) -> Shape:
        """Add a swimlane to this page's CFF Container by cloning its top lane.

        :returns: the new lane Shape
        """
        container = self.get_container()
        if container is None:
            raise ValueError("page has no CFF Container")
        return container.add_swimlane(label)

    def add_shape_to_lane(self, shape: Shape, lane: Shape) -> None:
        """Move a shape so its centre lies within a CFF swimlane's geometric band."""
        container = self.get_container()
        if container is None:
            raise ValueError("page has no CFF Container")
        container.add_shape_to_lane(shape, lane)

    def reanchor_connector(
        self,
        connector_shape: Shape,
        from_shape: Shape | None = None,
        to_shape: Shape | None = None,
        route: str = "dynamic",
        from_cp: int = 0,
        to_cp: int = 0,
    ) -> Shape:
        """Retarget an existing connector to new endpoints (either end may be
        kept by passing None).

        :returns: the connector Shape
        """
        return vsdx.Connect.retarget(
            page=self,
            connector_shape=connector_shape,
            from_shape=from_shape,
            to_shape=to_shape,
            route=route,
            from_cp=from_cp,
            to_cp=to_cp,
        )

    def delete_shape(self, shape: Shape) -> None:
        """Delete a shape from this page, removing any incident connectors.

        A group takes its children with it, so connectors glued to a child and
        records naming one are removed alongside the group's own. Connectors
        are deleted first (including their Connect records), then the shape.

        :raises ValueError: if the shape is not on this page
        """
        shape_id = str(shape.ID)
        if not any(str(s.ID) == shape_id for s in self.all_shapes):
            # silently doing nothing would hide a double delete, or a shape
            # taken from another page
            raise ValueError(f"shape ID {shape.ID} is not on page {self.name!r}")
        # every id that is about to disappear: the shape and, for a group,
        # everything it contains
        doomed_ids = {shape_id} | {str(s.ID) for s in shape.all_shapes}
        # connectors are the FromSheet of Connect records whose ToSheet is one
        # of the doomed shapes, on a begin/end relationship
        connector_ids = {c.from_id for c in self.connects if c.to_id in doomed_ids and c.from_rel in ("BeginX", "EndX")}
        doomed = set()
        for s in self.all_shapes:
            sid = str(s.ID)
            # cell_value, not `in s.cells`: a connector may inherit BeginX from
            # its master, and one missed here survives as a detached line whose
            # glue record has just been removed
            if sid == shape_id or (sid in connector_ids and s.cell_value("BeginX") is not None):
                doomed.add(s)
        for s in doomed:
            self._remove_shape_xml(s)
        # a record naming a group child outlives the child otherwise: the child
        # goes with the group element rather than through _remove_shape_xml
        self.remove_connect_records(doomed_ids, match="either")

    def _remove_shape_xml(self, shape: Shape) -> None:
        """Remove a shape's xml and every Connect record that names it.

        Records naming the shape on either side go: one pointing *at* a shape
        that is gone dangles just as surely as one leading from it. Connectors
        glued to the shape are separate shapes and are passed through here in
        their own right by :meth:`delete_shape`.
        """
        self.remove_connect_records({str(shape.ID)}, match="either")
        for shapes_el in self.xml.iter(f"{namespace}Shapes"):
            if shape.xml in list(shapes_el):
                shapes_el.remove(shape.xml)
                break

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
        for connect in list(connects_el):
            named = (
                {connect.attrib.get("FromSheet")}
                if match == "from"
                else {
                    connect.attrib.get("FromSheet"),
                    connect.attrib.get("ToSheet"),
                }
            )
            if normalised_ids & named:
                connects_el.remove(connect)
