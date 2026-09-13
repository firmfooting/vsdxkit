"""Container and swimlane support for vsdx documents.

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
  the same as plain ``<Cell N='...'>`` cells; helpers here handle both
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

import vsdxkit

from .document_part import DocumentPart
from .shapes import Shape

# observed lane pitch in the Visio 16 CFF capture (inches)
LANE_PITCH_INCHES = 1.18110236220472

# User-section row names written by Visio on lane shapes
ROW_HEADING_TEXT = "visHeadingText"
ROW_SWIMLANE_GUID = "SwimlaneListGUID"

# top-level shape NameU values of the CFF machinery (excluded from membership)
_CFF_MACHINERY = ("CFF Container", "Swimlane List", "Phase List", "Separator")


def get_user_row(shape: Shape, name: str) -> ET.Element | None:
    """Return the ``<Row N=name>`` element of the shape's User section, or None."""
    for section in shape.xml.findall(f"{vsdxkit.namespace}Section"):
        if section.attrib.get("N") == "User":
            for row in section.findall(f"{vsdxkit.namespace}Row"):
                if row.attrib.get("N") == name:
                    return row
    return None


def set_user_row_value(shape: Shape, name: str, value: str) -> bool:
    """Set the Value cell of a User-section row. Returns False if the row is
    absent (rows are only created where Visio itself creates them)."""
    row = get_user_row(shape, name)
    if row is None:
        return False
    for cell in row.findall(f"{vsdxkit.namespace}Cell"):
        if cell.attrib.get("N") == "Value":
            cell.attrib["V"] = value
            return True
    return False


class Container(DocumentPart):
    """Read/write view over a CFF (swimlane) diagram structure.

    Membership is geometric: :meth:`lane_of` maps a shape to the lane whose
    vertical band contains its centre, mirroring Visio's own containment
    behaviour. There are no membership cells to write.
    """

    def __init__(self, page: vsdxkit.Page):
        self.page = page

    @property
    @override
    def _document(self) -> vsdxkit.VisioFile:
        return self.page.vis

    # ---- discovery -------------------------------------------------------

    @staticmethod
    def find(page: vsdxkit.Page) -> Container | None:
        """Return a Container for the page, or None if this is not a CFF page."""
        for shape in page.all_shapes:
            if shape.shape_name == "CFF Container":
                return Container(page)
        return None

    def _top_level_named(self, name_prefix: str) -> list[Shape]:
        shapes_tag = self.page.xml.find(f"{vsdxkit.namespace}Shapes")
        if shapes_tag is None:
            return []
        result = []
        for el in shapes_tag.findall(f"{vsdxkit.namespace}Shape"):
            name = el.attrib.get("NameU") or el.attrib.get("Name") or ""
            if name.startswith(name_prefix):
                result.append(Shape(xml=el, parent=self.page, page=self.page))
        return result

    @property
    def container_shape(self) -> Shape | None:
        matches = self._top_level_named("CFF Container")
        return matches[0] if matches else None

    @property
    def swimlane_list(self) -> Shape | None:
        matches = self._top_level_named("Swimlane List")
        return matches[0] if matches else None

    @property
    def lanes(self) -> list[Shape]:
        """Lane shapes in visual order, top lane first."""
        lanes = [
            s
            for s in self._top_level_named("Swimlane")
            if s.shape_name and s.shape_name.startswith("Swimlane") and not s.shape_name.startswith("Swimlane List")
        ]
        lanes.sort(key=lambda s: -(s.y or 0.0))  # top-to-bottom
        return lanes

    # ---- geometry --------------------------------------------------------

    @staticmethod
    def lane_band(lane: Shape) -> tuple[float, float]:
        """(bottom, top) Y band of a lane, from its centre and height."""
        centre = lane.y or 0.0
        height = lane.height or LANE_PITCH_INCHES
        return centre - height / 2, centre + height / 2

    def lane_of(self, shape: Shape) -> Shape | None:
        """The lane whose band contains the shape's centre, or None."""
        for lane in self.lanes:
            bottom, top = self.lane_band(lane)
            if bottom <= (shape.y or 0.0) <= top:
                return lane
        return None

    def members(self, lane: Shape) -> list[Shape]:
        """Flowchart shapes whose centre lies in the lane's band."""
        bottom, top = self.lane_band(lane)
        result = []
        for shape in self._top_level_named(""):  # all top-level shapes
            name = shape.shape_name or ""
            if name.startswith(_CFF_MACHINERY) or name.startswith("Swimlane"):
                continue
            if "BeginX" in shape.cells:  # connectors are not members
                continue
            if bottom <= (shape.y or 0.0) <= top:
                result.append(shape)
        return result

    # ---- operations ------------------------------------------------------

    def add_swimlane(self, label: str | None = None) -> Shape:
        """Add a lane above the current top lane by cloning it and shifting
        one lane pitch. The Swimlane List and CFF Container grow to match.

        :return: the new lane Shape
        """
        # the Page.* wrappers are guarded; a Container reached through
        # Page.get_container() was not, and took its refusal from
        # renumber_shape_ids, which the caller never called (issue #329)
        self._require_open("Container.add_swimlane()")
        lanes = self.lanes
        if not lanes:
            raise ValueError("page has no Swimlane lanes; not a CFF diagram")
        top_lane = lanes[0]
        shapes_tag = self.page.xml.find(f"{vsdxkit.namespace}Shapes")
        if shapes_tag is None:
            # not reachable: a page with no Shapes tag has no lanes either, so
            # the check above fires first. Kept to narrow the type for append()
            raise ValueError("page has no Shapes tag")

        # The lane is built and labelled while still detached, because labelling
        # is the step that can fail. It used to run after the clone was appended
        # and the list and container grown, so a caller that caught the
        # ValueError and saved wrote a diagram with an extra unlabelled lane,
        # which the structural validator cannot see (#330). A failed call still
        # burns the ids the clone was allocated; the page's id mark only rises,
        # so the next shape gets a higher number and nothing else changes.
        new_xml = vsdxkit.ET.fromstring(vsdxkit.ET.tostring(top_lane.xml))
        self.page.vis.renumber_shape_ids(new_xml, self.page)
        new_lane = Shape(xml=new_xml, parent=self.page, page=self.page)
        new_lane.get_or_create_cell("PinY", v=str((top_lane.y or 0.0) + LANE_PITCH_INCHES))
        if label:
            self._write_lane_label(new_lane, label, subject=f"shape {top_lane.ID} (cloned to make the new lane)")

        shapes_tag.append(new_xml)
        # grow the list and container so the new lane sits inside them
        pitch = LANE_PITCH_INCHES
        lane_list = self.swimlane_list
        if lane_list is not None:
            lane_list.get_or_create_cell("PinY", v=str((lane_list.y or 0.0) + pitch / 2))
            lane_list.get_or_create_cell("Height", v=str((lane_list.height or 0) + pitch))
        container = self.container_shape
        if container is not None:
            container.get_or_create_cell("PinY", v=str((container.y or 0.0) + pitch / 2))
            container.get_or_create_cell("Height", v=str((container.height or 0) + pitch))

        return new_lane

    def set_lane_label(self, lane: Shape, label: str) -> None:
        """Set a lane's heading label (visHeadingText row + heading text).

        Raises rather than writing one half of the label. The ``visHeadingText``
        row is not created here: it is one of several rows Visio's
        cross-functional flowchart machinery writes together with the Swimlane
        List that owns the lane, and inventing one would produce a heading the
        CFF engine does not know about.

        :raises ValueError: if ``lane`` has no heading sub-shape, or no writable
            ``visHeadingText`` row.
        """
        self._require_open("Container.set_lane_label()")
        self._write_lane_label(lane, label, subject=f"shape {lane.ID}")

    def _write_lane_label(self, lane: Shape, label: str, *, subject: str) -> None:
        """Write both halves of a lane label, or neither.

        Every refusal is established before the first write, so a refusal
        leaves the lane as it was. ``subject`` names the shape the caller can
        act on, which for a clone is the lane it was copied from.

        The lane body used to take the label when the lane had no heading
        sub-shape, which was the one branch of #307 with no test. Which
        sub-shape is the heading is a separate question, and a wrong one:
        :meth:`lane_heading` takes the first child carrying a ``MasterShape``,
        and in the reference capture that is the lane band rather than the
        shape showing the text. Tracked by #337.
        """
        if not isinstance(label, str):
            # the second write is Shape.text, which rejects a non-str only once
            # it is already writing. The User row would be left holding a value
            # the document cannot serialise, so the file could not be saved at
            # all -- the same shape of defect as the abandoned lane above.
            raise TypeError(f"lane label must be a str, not {type(label).__name__}")
        heading = self.lane_heading(lane)
        if heading is None:
            raise ValueError(f"{subject} has no heading sub-shape, so it is not a swimlane lane")
        if not set_user_row_value(lane, ROW_HEADING_TEXT, label):
            raise ValueError(f"{subject} has no {ROW_HEADING_TEXT} row with a Value cell to write the label into")
        heading.text = label

    @staticmethod
    def lane_heading(lane: Shape) -> Shape | None:
        """The lane's heading sub-shape (child carrying MasterShape)."""
        for child in lane.child_shapes:
            if child.master_shape_ID is not None:
                return child
        return None

    def add_shape_to_lane(self, shape: Shape, lane: Shape) -> None:
        """Assign a shape to a lane by geometry: set the shape's PinY to the
        lane's centre, keeping its PinX. Mirrors Visio's own behaviour when a
        shape is dragged into a lane; membership stays geometric.
        """
        self._require_open("Container.add_shape_to_lane()")
        if self.lane_of(shape) is lane:
            return
        shape.get_or_create_cell("PinY", v=str(lane.y or 0.0))
