"""Cross-functional flowcharts: the swimlane diagram on a page.

Ground truth: tests/fixtures/com_reference/s05_swimlanes_cfflow.vsdx
(Visio 16 cross-functional flowchart capture).

Model (verified against the capture):

- CFF shapes (CFF Container, Swimlane List, Swimlane lanes, Phase List,
  Separator, and all flowchart shapes) live as TOP-LEVEL shapes on the page;
  Visio keeps them flat and links them logically
- lane membership is GEOMETRIC: a shape belongs to the lane whose vertical
  band contains the shape's centre (PinY). No membership cells exist
- each lane carries User-section rows: ``visHeadingText`` (label) and
  ``SwimlaneListGUID``; the heading text also appears in the lane's heading
  sub-shape (the child carrying ``MasterShape``)
- lanes stack at a fixed pitch; the observed pitch is 1.1811 inches (30 mm)
- User rows are stored as ``<Section N='User'><Row N='name'>`` which is NOT
  the same as plain ``<Cell N='...'>`` cells
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from typing import NamedTuple, Protocol

from vsdxkit import namespace
from vsdxkit._shape_tree import remap_sheet_references
from vsdxkit._xmlio import xml_value
from vsdxkit.errors import InvalidOperationError
from vsdxkit.shapes import PageView, Shape, _is_connector, _is_name_or_copy


class _DiagramPage(PageView, Protocol):
    """What a swimlane diagram needs from its page.

    The page sits above this module, so the diagram names only what it reads:
    the public view, for the top-level shapes it finds the container and
    lanes among, the name its messages give and the page a new lane is copied
    onto; and whether the page is still in its document.
    """

    def _attached(self) -> bool:
        """Whether the page is still in its document: a page that is not has no swimlane diagram to read."""
        ...


# observed lane pitch in the Visio 16 CFF capture (inches)
LANE_PITCH_INCHES = 1.18110236220472
"""The pitch lanes stack at, in inches: 30 mm, as Visio's own cross-functional flowchart spaces them.

:meth:`SwimlaneDiagram.add_lane` puts a new lane this far above the top one,
and grows the Swimlane List and the container by as much. A lane whose
height is missing or 0 is taken to be this tall.
"""

# how far apart, in inches, two lane edges can be and still be one edge: the
# lanes in the capture meet to within 1e-15
_EDGE_TOLERANCE = 1e-9
"""The distance in inches within which `_bands` snaps two lane edges to one, so adjoining lanes share an edge."""

# User-section row names written by Visio on lane shapes
ROW_HEADING_TEXT = "visHeadingText"
"""The User-section row in which Visio keeps a lane's label; :meth:`SwimlaneDiagram.set_lane_label` writes its ``Value`` cell."""

_CONTAINER_NAME = "CFF Container"
"""The name Visio gives the CFF container shape, which `_diagram_on` finds a page's diagram by; `_named` also takes a numbered copy."""
_SWIMLANE_LIST_NAME = "Swimlane List"
"""The name Visio gives the Swimlane List shape, which `add_lane` grows along with the container."""

_LANE_NAME = "Swimlane"
"""The name Visio gives each lane shape, which `SwimlaneDiagram.lanes` finds the lanes by."""

# top-level shape NameU values of the CFF machinery (excluded from membership)
_CFF_MACHINERY = (_CONTAINER_NAME, _SWIMLANE_LIST_NAME, "Phase List", "Separator", _LANE_NAME)
"""The names of the shapes that draw the diagram rather than belong to it, which `_is_member` leaves out of every lane."""


def _named(shape: Shape, name: str) -> bool:
    """Whether the shape is `name`, or a numbered copy of it, as `_is_name_or_copy` reads its name."""
    return _is_name_or_copy(shape.shape_name, name)


def _is_member(shape: Shape) -> bool:
    """Whether the top-level shape is part of the flowchart: not the CFF machinery, a lane or a connector."""
    return not any(_named(shape, name) for name in _CFF_MACHINERY) and not _is_connector(shape)


def _user_row(shape: Shape, name: str) -> ET.Element | None:
    """The ``<Row N=name>`` element of the shape's User section, or None."""
    for section in shape.xml.findall(f"{namespace}Section"):
        if section.attrib.get("N") == "User":
            for row in section.findall(f"{namespace}Row"):
                if row.attrib.get("N") == name:
                    return row
    return None


def _value_cell(row: ET.Element) -> ET.Element | None:
    """The row's ``<Cell N="Value">``, where a User row keeps its value, or None."""
    for cell in row.findall(f"{namespace}Cell"):
        if cell.attrib.get("N") == "Value":
            return cell
    return None


def _band(lane: Shape) -> tuple[float, float]:
    """The (bottom, top) of a lane's band, from its centre and height."""
    centre = lane.y or 0.0
    height = lane.height or LANE_PITCH_INCHES
    return centre - height / 2, centre + height / 2


def _bands(lanes: tuple[Shape, ...]) -> dict[Shape, tuple[float, float]]:
    """Each lane's (bottom, top), with edges that meet to within rounding made one edge.

    Visio's own lanes meet only to within rounding: 3.6e-15 apart in the
    reference capture. Each edge is snapped to the first edge already seen
    within `_EDGE_TOLERANCE` of it, so adjoining lanes share one value and
    their half-open bands leave no gap and no overlap between them.
    """
    edges: list[float] = []

    def snap(value: float) -> float:
        """The first edge seen within `_EDGE_TOLERANCE` of `value`, or `value` itself, kept as an edge for later ones."""
        for edge in edges:
            if abs(edge - value) <= _EDGE_TOLERANCE:
                return edge
        edges.append(value)
        return value

    bands = {}
    for lane in lanes:
        bottom, top = _band(lane)
        bands[lane] = (snap(bottom), snap(top))
    return bands


def _holds(band: tuple[float, float], shape: Shape) -> bool:
    """Whether the shape's centre is in the band.

    The band includes its bottom edge and not its top, so a shape on the edge
    two lanes share is in the upper one only.
    """
    bottom, top = band
    return bottom <= (shape.y or 0.0) < top


def _heading(lane: Shape) -> Shape | None:
    """The lane's heading sub-shape: the child carrying MasterShape."""
    for child in lane.children:
        if child.master_shape_ID is not None:
            return child
    return None


def _diagram_on(page: _DiagramPage) -> SwimlaneDiagram | None:
    """The page's swimlane diagram, None where it has no CFF container.

    :raises InvalidOperationError: the page has more than one
    """
    if not page._attached():
        raise InvalidOperationError(f"page {page.name!r} is no longer in its document, so it has no swimlane diagram")
    containers = [shape for shape in page.children if _named(shape, _CONTAINER_NAME)]
    if len(containers) > 1:
        ids = ", ".join(str(shape.ID) for shape in containers)
        raise InvalidOperationError(f"page {page.name!r} has {len(containers)} CFF containers (shapes {ids}), not one")
    return SwimlaneDiagram(containers[0]) if containers else None


_NUM_LANES = "numLanes"
"""The User-section row of the container that counts the lanes, which Visio's own diagram has."""
_SETTINGS = "visCFFSettings"
"""The User-section row of a lane that spells the diagram's settings, lane count included, as text."""
_STG4 = re.compile(r"/stg4=\d+,")
"""The lane-count setting inside a lane's ``visCFFSettings`` text."""
_LANE_LIST = re.compile(r"DEPENDSON\(2(?:,Sheet\.\d+!SheetRef\(\))*\)")
"""The ``DEPENDSON`` call in the Swimlane List's ``Relationships`` formula that names its lanes."""
MAX_LANES = 5
"""The most lanes the creation is checked against Visio on; see ``tools/diagram_cases.py``."""
LANE_HEIGHTS = (0.5, 6.0)
"""The least and greatest lane height, in inches, that Visio was checked on."""
DIAGRAM_WIDTHS = (5.0, 22.0)
"""The least and greatest diagram width, in inches, that Visio was checked on."""
LABEL_CHARS_PER_INCH = 11
"""The most characters of a label for each inch of lane height: a longer label wraps out of the heading, which Visio showed."""
ID_CEILING = 1000
"""The bundled diagram's shape IDs start here, so a page may hold shapes only below it for a copy's IDs never to equal one of them."""


class _Donors(NamedTuple):
    """The shapes of the bundled cross-functional flowchart that :func:`_create_diagram` copies."""

    container: Shape
    """The CFF Container."""
    swimlane_list: Shape
    """The Swimlane List."""
    lane: Shape
    """One lane, copied once for each band."""
    phase_list: Shape
    """The Phase List, which Visio's diagram always has."""
    separator: Shape
    """The Phase List's Separator."""


def _fit(shape: Shape, donor: Shape, left: float, bottom: float, right: float, top: float) -> None:
    """Size `shape` to these edges and pin it there, keeping the place of its local pin that `donor` has.

    The local pin is written as a value in the same proportion to the new size, because the formula that
    gives it (``Height*0.5``, for a lane) is the master's and a refresh leaves a cell only inherited alone.
    """
    width, height = right - left, top - bottom
    pin_x, pin_y = (donor.loc_x or 0.0) / (donor.width or 1.0) * width, (donor.loc_y or 0.0) / (donor.height or 1.0) * height
    for name, value in (("Width", width), ("Height", height), ("LocPinX", pin_x), ("LocPinY", pin_y)):
        shape._write_cell(name, v=xml_value(value), keep_formula=True)
    for member in (shape, *shape.descendants):
        member._refresh_formula_values()
    shape._write_cell("PinX", v=xml_value(left + pin_x), keep_formula=True)
    shape._write_cell("PinY", v=xml_value(bottom + pin_y), keep_formula=True)


_SIZED_CELLS = (
    "PinX",
    "PinY",
    "Width",
    "Height",
    "LocPinX",
    "LocPinY",
    "TxtPinX",
    "TxtPinY",
    "TxtWidth",
    "TxtHeight",
    "TxtLocPinX",
    "TxtLocPinY",
)
"""The cells of a sub-shape, its text block included, that follow its group's size through the master's formulas."""
_TITLE_REACH = 0.6
"""How far below its group's top edge a sub-shape's pin can sit and still be taken as anchored to that edge, in inches."""

_Size = tuple[float, float]
"""A width and a height in inches."""


def _renew(value: float, sizes: Sequence[tuple[_Size, _Size]]) -> float | None:
    """`value` as the resized shapes make it, or None where it is no dimension of theirs.

    `sizes` lists (size before, size after), the shape the value belongs to first. A value equal to a
    dimension, or half of one, becomes the same dimension afterwards; a value a short way under the top edge
    of the first shape keeps that distance from the new top edge.
    """
    # these matches hold only while the donor's dimensions stay distinct from each other and from their halves
    for (old_w, old_h), (new_w, new_h) in sizes:
        for old, new in ((old_w, new_w), (old_h, new_h)):
            if math.isclose(value, old, abs_tol=1e-6):
                return new
            if math.isclose(value, old / 2, abs_tol=1e-6):
                return new / 2
    (_old_w, old_h), (_new_w, new_h) = sizes[0]
    if 0 < old_h - value <= _TITLE_REACH and value > old_h / 2:
        return new_h - (old_h - value)
    return None


def _renew_inherited_vertices(member: Shape, sizes: Sequence[tuple[_Size, _Size]]) -> None:
    """Give `member` an ``Inh`` vertex cell, holding the renewed number, for each master vertex it has no cell of its own for.

    A vertex the shape only inherits is drawn from the master's cached number until something recalculates it,
    and Visio's own file writes such a cell as ``F="Inh"`` beside the value it computed.
    """
    master = member.master_shape
    if master is None:
        return
    for master_section in master.xml.iterfind(f'{namespace}Section[@N="Geometry"]'):
        section = member.xml.find(f'{namespace}Section[@N="Geometry"][@IX="{master_section.attrib.get("IX", "0")}"]')
        for master_row in master_section.iterfind(f"{namespace}Row"):
            for master_cell in master_row.iterfind(f"{namespace}Cell"):
                raw = master_cell.attrib.get("V")
                renewed = (
                    None if master_cell.attrib.get("N") not in ("X", "Y") or raw in (None, "") else _renew(float(raw), sizes)
                )
                if renewed is None:
                    continue
                if section is None:
                    section = ET.Element(f"{namespace}Section", {"N": "Geometry", "IX": master_section.attrib.get("IX", "0")})
                    placed = [e for e in member.xml if e.tag in (f"{namespace}Cell", f"{namespace}Section")]
                    member.xml.insert(
                        list(member.xml).index(placed[-1]) + 1 if placed else 0, section
                    )  # schema order: cells, then sections, then text
                row = next(
                    (r for r in section.iterfind(f"{namespace}Row") if r.attrib.get("IX") == master_row.attrib.get("IX")), None
                )
                if row is None:
                    row = ET.SubElement(
                        section, f"{namespace}Row", {k: v for k, v in master_row.attrib.items() if k in ("T", "IX")}
                    )
                if row.find(f'{namespace}Cell[@N="{master_cell.attrib["N"]}"]') is None:
                    ET.SubElement(row, f"{namespace}Cell", {"N": master_cell.attrib["N"], "V": xml_value(renewed), "F": "Inh"})
        if section is not None:
            rows = sorted(section.iterfind(f"{namespace}Row"), key=lambda r: int(r.attrib.get("IX", "0")))
            for r in rows:
                section.remove(r)
            section.extend(rows)  # schema order: rows by IX


def _resync(shape: Shape, sizes: Sequence[tuple[_Size, _Size]]) -> None:
    """Bring the cached placement of the sub-shapes of `shape` in step with its new size.

    Sub-shapes state their placement as formulas inherited from the master: the lane band is as wide as its
    lane and the heading as wide as the lane is tall. A file that arrives with the old numbers is drawn with
    them until something recalculates the cell, so each cached number that is a dimension of the bundled
    shapes before they were resized is rewritten to the same dimension after (see `_renew`). The outline vertices
    of `shape` itself and of its sub-shapes are cached numbers of the same kind.
    """
    for member in shape.descendants:
        for name in _SIZED_CELLS:
            inherited = member._cell(name) is None
            raw = member.cell_value(name)
            renewed = None if raw in (None, "") else _renew(float(raw), sizes)
            if renewed is not None:
                cell = member._write_cell(name, v=xml_value(renewed), keep_formula=True)
                if inherited:
                    cell.formula = "Inh"  # the master's formula names its own shapes by Sheet.N; with Inh the oracle showed the right numbers
    for member in (shape, *shape.descendants):
        for section in member.xml.iterfind(f'{namespace}Section[@N="Geometry"]'):
            for vertex in section.iter(f"{namespace}Cell"):
                raw = vertex.attrib.get("V")
                renewed = None if vertex.attrib.get("N") not in ("X", "Y") or raw in (None, "") else _renew(float(raw), sizes)
                if renewed is not None:
                    vertex.attrib["V"] = xml_value(renewed)
        _renew_inherited_vertices(member, sizes)


def _user_value(shape: Shape, row: str) -> ET.Element:
    """The Value cell of a User-section row the shape has; the copy of Visio's own diagram always has these."""
    found = _user_row(shape, row)
    cell = None if found is None else _value_cell(found)
    if cell is None:
        raise InvalidOperationError(f"shape {shape.ID} has no {row} row to write; the bundled diagram changed")
    return cell


def _require_checked(bands: Sequence[tuple[str, float]], width: float) -> None:
    """Refuse a diagram outside the sizes the Visio oracle recalculated, naming the limit it crosses."""
    if len(bands) > MAX_LANES:
        raise InvalidOperationError(f"{len(bands)} lanes is more than the {MAX_LANES} that creation is checked on")
    low, high = DIAGRAM_WIDTHS
    if not low <= width <= high:
        raise InvalidOperationError(
            f"a diagram width of {width} inches is outside the {low} to {high} that creation is checked on"
        )
    low, high = LANE_HEIGHTS
    for label, height in bands:
        if not low <= height <= high:
            raise InvalidOperationError(
                f"a lane height of {height} inches is outside the {low} to {high} that creation is checked on"
            )
        if not label:
            raise InvalidOperationError("a lane label must not be empty")
        if len(label) > LABEL_CHARS_PER_INCH * height:
            raise InvalidOperationError(
                f"the label {label!r} has {len(label)} characters, more than the {LABEL_CHARS_PER_INCH} for each inch "
                f"of its {height} inch lane that fit in the heading"
            )


def _create_diagram(
    page: _DiagramPage, donors: _Donors, bands: Sequence[tuple[str, float]], *, left: float, top: float, width: float
) -> SwimlaneDiagram:
    """Copy the bundled diagram onto `page` with one lane for each band, sized and labelled; see `Page.create_swimlanes`."""
    if not bands:
        raise InvalidOperationError("a swimlane diagram needs at least one lane")
    if width <= 0 or any(height <= 0 for _label, height in bands):
        raise InvalidOperationError("the width and every lane height must be positive")
    _require_checked(bands, width)
    held = [int(shape.ID) for shape in page.shapes if shape.ID is not None]
    if max(held, default=0) + 4 + 3 * len(bands) + 3 >= ID_CEILING:
        raise InvalidOperationError(f"page {page.name!r} holds shapes with IDs too high to make room for a swimlane diagram")
    # donor margins are read before anything is copied: the container, the phases and the separator keep the
    # distances from the list's edges that Visio drew them at
    list_edges = donors.swimlane_list.bounds
    margins = {
        name: tuple(a - b for a, b in zip(shape.bounds, list_edges, strict=True))
        for name, shape in (
            ("container", donors.container),
            ("phase_list", donors.phase_list),
            ("separator", donors.separator),
        )
    }
    old_sizes = {
        shape.ID: (shape.width or 0.0, shape.height or 0.0)
        for shape in (donors.container, donors.swimlane_list, donors.phase_list, donors.separator, donors.lane)
    }
    container = donors.container.copy(page)
    swimlane_list = donors.swimlane_list.copy(page)
    phase_list = donors.phase_list.copy(page)
    separator = donors.separator.copy(page)
    lanes = [donors.lane.copy(page) for _band in bands]
    # the copies still name each other by the donor's IDs; the lane's own subtree was renumbered by the copy
    renamed = {
        donors.container.ID: container.ID,
        donors.swimlane_list.ID: swimlane_list.ID,
        donors.phase_list.ID: phase_list.ID,
        donors.separator.ID: separator.ID,
    }
    id_map = {old: int(new) for old, new in renamed.items() if old is not None and new is not None}
    for copied in (container, swimlane_list, phase_list, separator, *lanes):
        remap_sheet_references(copied.xml, id_map)
    total = sum(height for _label, height in bands)
    list_box = (left, top - total, left + width, top)
    _fit(swimlane_list, donors.swimlane_list, *list_box)
    for name, shape, donor in (
        ("container", container, donors.container),
        ("phase_list", phase_list, donors.phase_list),
        ("separator", separator, donors.separator),
    ):
        dl, db, dr, dt = margins[name]
        _fit(shape, donor, list_box[0] + dl, list_box[1] + db, list_box[2] + dr, list_box[3] + dt)
    cursor = top
    for lane, (_label, height) in zip(lanes, bands, strict=True):
        _fit(lane, donors.lane, left, cursor - height, left + width, cursor)
        cursor -= height
    tops = [
        (donors.container, container),
        (donors.swimlane_list, swimlane_list),
        (donors.phase_list, phase_list),
        (donors.separator, separator),
    ]
    for old, new in [*tops, *((donors.lane, lane) for lane in lanes)]:
        sizes = [((old_sizes[old.ID]), (new.width or 0.0, new.height or 0.0))]
        sizes += [(old_sizes[o.ID], (n.width or 0.0, n.height or 0.0)) for o, n in tops if o is not old]
        _resync(new, sizes)
    _relate(swimlane_list, lanes)
    _user_value(container, _NUM_LANES).attrib["V"] = str(len(bands))
    diagram = SwimlaneDiagram(container)
    for lane, (label, _height) in zip(diagram.lanes, bands, strict=True):
        _user_value(lane, ROW_HEADING_TEXT).attrib["V"] = label
        for part in lane.children:
            if part.text:
                part.text = label
        settings = _user_value(lane, _SETTINGS)
        settings.attrib["V"] = _STG4.sub(f"/stg4={len(bands)},", settings.attrib["V"])
    return diagram


def _relate(swimlane_list: Shape, lanes: Sequence[Shape]) -> None:
    """Make the Swimlane List's ``Relationships`` formula name these lanes, top to bottom, as Visio's does."""
    named = "".join(f",Sheet.{lane.ID}!SheetRef()" for lane in lanes)
    for cell in swimlane_list.xml.findall(f'{namespace}Cell[@N="Relationships"]'):
        cell.attrib["F"] = _LANE_LIST.sub(f"DEPENDSON(2{named})", cell.attrib["F"])


class SwimlaneDiagram:
    """The cross-functional flowchart on a page: its lanes, and which shapes sit in each.

    Reach it as :attr:`vsdxkit.pages.Page.swimlanes`. Membership is geometric:
    a shape is in the lane whose band holds its centre, as Visio decides it.
    There are no membership cells to write.
    """

    def __init__(self, container: Shape) -> None:
        """Bind to one CFF container shape; the diagram is on the container's page."""
        self._page: _DiagramPage = container._page
        self._container = container

    def __repr__(self) -> str:
        """Shows the page's name, the container's ID and how many lanes there are, or ``detached`` for a container that has left the document."""
        if not self._container.is_attached:
            return f"<SwimlaneDiagram page={self._page.name!r} container={self._container.ID} detached>"
        return f"<SwimlaneDiagram page={self._page.name!r} container={self._container.ID} lanes={len(self.lanes)}>"

    @property
    def container(self) -> Shape:
        """The CFF container shape the diagram is bound to.

        :raises InvalidOperationError: the container is no longer in the document
        """
        self._require_container("reading a swimlane diagram's container")
        return self._container

    def _require_container(self, operation: str) -> None:
        """Refuse `operation` on a diagram whose container, or page, has left the document."""
        self._container._require_attached(operation)

    @property
    def lanes(self) -> tuple[Shape, ...]:
        """The lane shapes, top lane first.

        Every other operation reads the lanes first, so a diagram whose
        container has been deleted, or whose page has, refuses here before
        anything is written.

        :raises InvalidOperationError: the container is no longer in the document
        """
        self._require_container("reading a swimlane diagram's lanes")
        lanes = [shape for shape in self._page.children if _named(shape, _LANE_NAME)]
        lanes.sort(key=lambda lane: -(lane.y or 0.0))
        return tuple(lanes)

    def shapes_in(self, lane: Shape) -> tuple[Shape, ...]:
        """The flowchart shapes whose centre lies in the lane's band.

        The CFF machinery, the lanes themselves and connectors are not members.

        :raises InvalidOperationError: ``lane`` is not one of :attr:`lanes`
        """
        self._require_lane(lane)
        band = _bands(self.lanes)[lane]
        return tuple(shape for shape in self._page.children if _is_member(shape) and _holds(band, shape))

    def lane_for(self, shape: Shape) -> Shape | None:
        """The lane whose band holds the shape's centre, or None.

        :raises InvalidOperationError: lanes overlap where the shape is, so it is in more than one
        """
        holding = [lane for lane, band in _bands(self.lanes).items() if _holds(band, shape)]
        if len(holding) > 1:
            ids = ", ".join(str(lane.ID) for lane in holding)
            raise InvalidOperationError(f"shape {shape.ID} is in {len(holding)} overlapping lanes (shapes {ids})")
        return holding[0] if holding else None

    def add_lane(self, label: str | None = None) -> Shape:
        """Add a lane one pitch above the top lane, a copy of it, and grow the Swimlane List and container to match.

        Whether the new lane can take ``label`` is settled on the lane it is
        copied from before anything is written, so a refused label leaves the
        page as it was (#330).

        :raises InvalidOperationError: the diagram has no lanes, or the top lane cannot take a label
        :returns: the new lane
        """
        lanes = self.lanes
        if not lanes:
            raise InvalidOperationError(f"the swimlane diagram on page {self._page.name!r} has no lanes to copy")
        top_lane = lanes[0]
        subject = f"shape {top_lane.ID} (copied to make the new lane)"
        if label is not None:
            self._check_label(top_lane, label, subject=subject)
        new_lane = top_lane.copy(self._page)
        new_lane._write_cell("PinY", v=str((top_lane.y or 0.0) + LANE_PITCH_INCHES), keep_formula=True)
        if label is not None:
            self._write_label(new_lane, label, subject=subject)
        # the list and the container grow upwards so the new lane sits inside them
        for grown in (self._swimlane_list(), self._container):
            if grown is None:
                continue
            grown._write_cell("PinY", v=str((grown.y or 0.0) + LANE_PITCH_INCHES / 2), keep_formula=True)
            grown._write_cell("Height", v=str((grown.height or 0) + LANE_PITCH_INCHES), keep_formula=True)
        return new_lane

    def set_lane_label(self, lane: Shape, label: str) -> None:
        """Set a lane's label: its ``visHeadingText`` row and its heading's text, both or neither.

        The ``visHeadingText`` row is not created here: it is one of several
        rows Visio's cross-functional flowchart machinery writes together with
        the Swimlane List that owns the lane, and inventing one would produce a
        heading the CFF engine does not know about.

        :raises InvalidOperationError: ``lane`` is not one of :attr:`lanes`, or it
            has no heading sub-shape or no writable ``visHeadingText`` row
        """
        self._require_lane(lane)
        self._write_label(lane, label, subject=f"shape {lane.ID}")

    def move_to_lane(self, shape: Shape, lane: Shape) -> None:
        """Put a shape in a lane by centring it on the lane's band, keeping its PinX.

        This is what Visio does when a shape is dragged into a lane. A shape
        already in the lane is left where it is.

        :raises InvalidOperationError: ``lane`` is not one of :attr:`lanes`, or
            ``shape`` is not a top-level flowchart shape on the diagram's page
        """
        self._require_lane(lane)
        if not (_is_member(shape) and shape in self._page.children):
            raise InvalidOperationError(
                f"shape {shape.ID} is not a flowchart shape of the swimlane diagram on page {self._page.name!r}"
            )
        if _holds(_bands(self.lanes)[lane], shape):
            return
        shape._write_cell("PinY", v=str(lane.y or 0.0), keep_formula=True)

    def _swimlane_list(self) -> Shape | None:
        """The page's first top-level Swimlane List shape, which `add_lane` grows, or None for a page without one."""
        return next((shape for shape in self._page.children if _named(shape, _SWIMLANE_LIST_NAME)), None)

    def _require_lane(self, lane: Shape) -> None:
        """Refuse a `lane` that is not one of `lanes`, with `InvalidOperationError`."""
        if lane not in self.lanes:
            raise InvalidOperationError(f"shape {lane.ID} is not a swimlane lane of this diagram")

    def _write_label(self, lane: Shape, label: str, *, subject: str) -> None:
        """Write both halves of a lane label, or neither.

        Every refusal is established before the first write. ``subject`` names
        the shape the caller can act on, which for a copy is the lane it was
        copied from.

        Which sub-shape is the heading is a separate question, and a wrong one:
        :func:`_heading` takes the first child carrying a ``MasterShape``, and
        in the reference capture that is the lane band rather than the shape
        showing the text. Tracked by #337.
        """
        heading, value = self._check_label(lane, label, subject=subject)
        value.attrib["V"] = label
        heading.text = label

    def _check_label(self, lane: Shape, label: str, *, subject: str) -> tuple[Shape, ET.Element]:
        """Refuse a label `lane` cannot take, writing nothing; return the heading and the Value cell that will show it."""
        if not isinstance(label, str):
            # the second write is Shape.text, which rejects a non-str only once
            # it is already writing; the row would be left holding a value the
            # document cannot serialise
            raise TypeError(f"lane label must be a str, not {type(label).__name__}")
        heading = _heading(lane)
        if heading is None:
            raise InvalidOperationError(f"{subject} has no heading sub-shape, so it is not a swimlane lane")
        row = _user_row(lane, ROW_HEADING_TEXT)
        value = None if row is None else _value_cell(row)
        if value is None:
            raise InvalidOperationError(f"{subject} has no {ROW_HEADING_TEXT} row with a Value cell to write the label into")
        return heading, value
