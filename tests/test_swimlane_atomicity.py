"""A swimlane that cannot be labelled is never put on the page.

`Container.add_swimlane` pre-checked whether the top lane had a
`visHeadingText` row. What raises is `set_user_row_value`, which also returns
False when the row exists but carries no `<Cell N="Value">`. That case walked
past the pre-check into the state the check existed to prevent: the clone
appended, the Swimlane List and CFF Container grown around it, and then a
`ValueError`. A caller that caught it and saved wrote a CFF diagram with an
extra unlabelled lane, which the structural validator cannot see because lane
membership is geometric (issue #330).
"""

import xml.etree.ElementTree as ET

import pytest

from vsdx import Shape, VisioFile, namespace
from vsdx.containers import ROW_HEADING_TEXT, get_user_row

CFF_FIXTURE = "fixtures/com_reference/s05_swimlanes_cfflow.vsdx"


def strip_value_cell(lane: Shape) -> None:
    """Leave the lane's heading row in place but take away the cell it writes.

    `get_user_row` finds the row; `set_user_row_value` finds nothing to write.
    That gap is #330.
    """
    row = get_user_row(lane, ROW_HEADING_TEXT)
    assert row is not None
    value_cells = [cell for cell in row.findall(f"{namespace}Cell") if cell.attrib.get("N") == "Value"]
    assert value_cells, "fixture lane has no Value cell to remove"
    for cell in value_cells:
        row.remove(cell)


def restore_value_cell(lane: Shape) -> None:
    """Put back what `strip_value_cell` took away."""
    row = get_user_row(lane, ROW_HEADING_TEXT)
    assert row is not None
    row.append(ET.fromstring(f'<Cell xmlns="{namespace[1:-1]}" N="Value" V="restored"/>'))


def test_add_swimlane_leaves_the_page_untouched_when_the_label_cannot_be_written(vsdx_copy):
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        page = vis.pages[0]
        container = page.get_container()
        strip_value_cell(container.lanes[0])
        before = ET.tostring(page.xml.getroot())

        with pytest.raises(ValueError):
            page.add_swimlane("Test lane")

        assert ET.tostring(page.xml.getroot()) == before


def test_add_swimlane_reports_the_lane_it_cloned_and_what_that_lane_lacks(vsdx_copy):
    """The message named the clone, and called a clone of a lane 'not a lane'."""
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        page = vis.pages[0]
        container = page.get_container()
        top_lane = container.lanes[0]
        strip_value_cell(top_lane)

        with pytest.raises(ValueError) as excinfo:
            page.add_swimlane("Test lane")

        message = str(excinfo.value)
        assert f"shape {top_lane.ID} " in message
        assert "Value" in message and ROW_HEADING_TEXT in message
        assert "is not a swimlane lane" not in message


def test_add_swimlane_leaves_the_page_untouched_when_the_lane_has_no_heading_shape(vsdx_copy):
    """The other way `_write_lane_label` refuses, and the one that used to put
    the label on the lane body and carry on."""
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        page = vis.pages[0]
        container = page.get_container()
        top_lane = container.lanes[0]
        top_lane.xml.remove(top_lane.xml.find(f"{namespace}Shapes"))
        before = ET.tostring(page.xml.getroot())

        with pytest.raises(ValueError):
            page.add_swimlane("Test lane")

        assert ET.tostring(page.xml.getroot()) == before


def test_add_swimlane_still_allocates_unique_ids_after_a_refused_call(vsdx_copy):
    """A refused call leaves the page's id mark raised, which is all it leaves.

    Shape ids need not be contiguous, so the gap is harmless -- but a later
    lane must still not collide with one already on the page.
    """
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        page = vis.pages[0]
        container = page.get_container()
        strip_value_cell(container.lanes[0])

        with pytest.raises(ValueError):
            page.add_swimlane("Refused")

        restore_value_cell(container.lanes[0])
        page.add_swimlane("Accepted")
        ids = [shape.ID for shape in page.all_shapes]
        assert len(ids) == len(set(ids))


def test_a_non_string_label_is_refused_before_either_half_is_written(vsdx_copy):
    """`Shape.text` rejects a non-str only once it is writing, so the User row
    was left holding a value `ET.tostring` cannot serialise: the document could
    then not be saved at all."""
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        page = vis.pages[0]
        container = page.get_container()
        lane = container.lanes[0]
        before = ET.tostring(page.xml.getroot())

        with pytest.raises(TypeError):
            container.set_lane_label(lane, 5)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            page.add_swimlane(5)  # type: ignore[arg-type]

        assert ET.tostring(page.xml.getroot()) == before


def test_set_lane_label_refuses_a_shape_that_was_never_a_lane(vsdx_copy):
    """A plain flowchart shape has neither half of a lane label to write.

    The existing #263 test strips the row from a real lane, which keeps its
    sub-shapes, so nothing covered a shape that is not a lane at all.
    """
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        page = vis.pages[0]
        container = page.get_container()
        decision = page.find_shape_by_text("Decision")
        assert decision is not None
        before = ET.tostring(decision.xml)

        with pytest.raises(ValueError, match="not a swimlane lane"):
            container.set_lane_label(decision, "Renamed")

        assert ET.tostring(decision.xml) == before


def test_set_lane_label_refuses_a_lane_whose_heading_row_has_no_value_cell(vsdx_copy):
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        container = vis.pages[0].get_container()
        lane = container.lanes[0]
        strip_value_cell(lane)
        before = ET.tostring(lane.xml)

        with pytest.raises(ValueError):
            container.set_lane_label(lane, "Renamed")

        assert ET.tostring(lane.xml) == before


def test_set_lane_label_refuses_a_lane_with_no_heading_shape(vsdx_copy):
    """The label used to land on the lane body when there was no heading shape (#307)."""
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        container = vis.pages[0].get_container()
        lane = container.lanes[0]
        assert container.lane_heading(lane) is not None
        # a lane with no sub-shapes at all, so nothing can carry the heading
        lane.xml.remove(lane.xml.find(f"{namespace}Shapes"))
        before = ET.tostring(lane.xml)

        with pytest.raises(ValueError):
            container.set_lane_label(lane, "Renamed")

        # neither the User row nor the lane body took the label
        assert ET.tostring(lane.xml) == before
