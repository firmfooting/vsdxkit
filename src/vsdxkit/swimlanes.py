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

import xml.etree.ElementTree as ET
from typing import Protocol

from vsdxkit import namespace
from vsdxkit.errors import InvalidOperationError
from vsdxkit.shapes import PageView, Shape, is_connector


class _DiagramPage(PageView, Protocol):
    """What a swimlane diagram needs from its page.

    The page sits above this module, so the diagram names only what it reads:
    the public view, for the top-level shapes it finds the container and
    lanes among, the name its messages give and the page a new lane is copied
    onto; and whether the page is still in its document.
    """

    def _attached(self) -> bool: ...


# observed lane pitch in the Visio 16 CFF capture (inches)
LANE_PITCH_INCHES = 1.18110236220472

# how far apart, in inches, two lane edges can be and still be one edge: the
# lanes in the capture meet to within 1e-15
_EDGE_TOLERANCE = 1e-9

# User-section row names written by Visio on lane shapes
ROW_HEADING_TEXT = "visHeadingText"
ROW_SWIMLANE_GUID = "SwimlaneListGUID"

CONTAINER_NAME = "CFF Container"
_SWIMLANE_LIST_NAME = "Swimlane List"

_LANE_NAME = "Swimlane"

# top-level shape NameU values of the CFF machinery (excluded from membership)
_CFF_MACHINERY = (CONTAINER_NAME, _SWIMLANE_LIST_NAME, "Phase List", "Separator", _LANE_NAME)


def _named(shape: Shape, name: str) -> bool:
    """Whether the shape is `name`, or a numbered copy of it: Visio names the second one `name.12`.

    Only a number follows the dot. A shape its author named `name.backup` is
    not a copy Visio made.
    """
    shape_name = shape.shape_name or ""
    base, dot, suffix = shape_name.partition(".")
    return base == name and (not dot or suffix.isdigit())


def _is_member(shape: Shape) -> bool:
    """Whether the top-level shape is part of the flowchart: not the CFF machinery, a lane or a connector."""
    return not any(_named(shape, name) for name in _CFF_MACHINERY) and not is_connector(shape)


def _user_row(shape: Shape, name: str) -> ET.Element | None:
    """The ``<Row N=name>`` element of the shape's User section, or None."""
    for section in shape.xml.findall(f"{namespace}Section"):
        if section.attrib.get("N") == "User":
            for row in section.findall(f"{namespace}Row"):
                if row.attrib.get("N") == name:
                    return row
    return None


def _value_cell(row: ET.Element) -> ET.Element | None:
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
    containers = [shape for shape in page.children if _named(shape, CONTAINER_NAME)]
    if len(containers) > 1:
        ids = ", ".join(str(shape.ID) for shape in containers)
        raise InvalidOperationError(f"page {page.name!r} has {len(containers)} CFF containers (shapes {ids}), not one")
    return SwimlaneDiagram(containers[0]) if containers else None


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
        new_lane.get_or_create_cell("PinY", v=str((top_lane.y or 0.0) + LANE_PITCH_INCHES))
        if label is not None:
            self._write_label(new_lane, label, subject=subject)
        # the list and the container grow upwards so the new lane sits inside them
        for grown in (self._swimlane_list(), self._container):
            if grown is None:
                continue
            grown.get_or_create_cell("PinY", v=str((grown.y or 0.0) + LANE_PITCH_INCHES / 2))
            grown.get_or_create_cell("Height", v=str((grown.height or 0) + LANE_PITCH_INCHES))
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
        shape.get_or_create_cell("PinY", v=str(lane.y or 0.0))

    def _swimlane_list(self) -> Shape | None:
        return next((shape for shape in self._page.children if _named(shape, _SWIMLANE_LIST_NAME)), None)

    def _require_lane(self, lane: Shape) -> None:
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
