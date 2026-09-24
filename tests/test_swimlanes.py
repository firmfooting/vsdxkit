"""SwimlaneDiagram against the real Visio CFF capture (#110)."""

import copy
import itertools
import xml.etree.ElementTree as ET
import zipfile

import pytest

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError, NotFoundError
from vsdxkit.pages import Page
from vsdxkit.swimlanes import LANE_PITCH_INCHES, ROW_HEADING_TEXT, SwimlaneDiagram, _band, _user_row

FIXTURE = "fixtures/com_reference/s05_swimlanes_cfflow.vsdx"


def _label(lane):
    row = _user_row(lane, ROW_HEADING_TEXT)
    return next(c.attrib.get("V") for c in row if c.attrib.get("N") == "Value")


def _diagram(vsdx_copy):
    page = Document.open(vsdx_copy(FIXTURE)).pages[0]
    return page, page.require_swimlanes()


def _xml(element):
    return ET.tostring(element)


def test_a_cff_page_has_one_diagram_bound_to_its_container(vsdx_copy):
    page, diagram = _diagram(vsdx_copy)
    assert isinstance(page.swimlanes, SwimlaneDiagram)
    assert diagram.container.shape_name == "CFF Container"


def test_a_page_without_a_container_has_no_diagram(vsdx_copy):
    page = Document.open(vsdx_copy("test1.vsdx")).pages[0]
    assert page.swimlanes is None
    with pytest.raises(NotFoundError, match="no CFF container"):
        page.require_swimlanes()


def test_two_containers_make_the_page_ambiguous(vsdx_copy):
    page, diagram = _diagram(vsdx_copy)
    second = copy.deepcopy(diagram.container.xml)
    second.attrib["NameU"] = "CFF Container.99"
    page.xml.getroot().find(f"{namespace}Shapes").append(second)

    with pytest.raises(InvalidOperationError, match="2 CFF containers"):
        page.swimlanes  # noqa: B018
    with pytest.raises(InvalidOperationError, match="2 CFF containers"):
        page.require_swimlanes()


def test_lanes_are_in_visual_order(vsdx_copy):
    _, diagram = _diagram(vsdx_copy)
    lanes = diagram.lanes
    assert isinstance(lanes, tuple)
    assert [lane.y for lane in lanes] == sorted((lane.y for lane in lanes), reverse=True)
    assert [_label(lane) for lane in lanes] == ["Function 1", "Function 2", "Function 3"]


def test_membership_is_geometric(vsdx_copy):
    page, diagram = _diagram(vsdx_copy)
    for lane in diagram.lanes:
        bottom, top = _band(lane)
        members = diagram.shapes_in(lane)
        assert isinstance(members, tuple)
        for member in members:
            assert bottom <= member.y < top
            assert diagram.lane_for(member) == lane
    decision = page.shapes.require_text("Decision")
    assert decision in diagram.shapes_in(diagram.lane_for(decision))


def test_a_shape_on_a_shared_edge_is_in_the_upper_lane_only(vsdx_copy):
    page, diagram = _diagram(vsdx_copy)
    upper, lower = diagram.lanes[0], diagram.lanes[1]
    edge, _ = _band(upper)
    assert _band(lower)[1] == pytest.approx(edge)
    decision = page.shapes.require_text("Decision")
    decision.y = edge

    assert diagram.lane_for(decision) == upper
    assert decision in diagram.shapes_in(upper)
    assert decision not in diagram.shapes_in(lower)


def test_a_shape_near_an_edge_visio_rounded_is_in_exactly_one_lane(vsdx_copy):
    """Fails if two lanes whose edges meet only to within rounding both hold, or neither holds, a shape between them.

    In the capture, one pair of adjoining lane edges differs by about 3.6e-15.
    Shifting each lane's edges by the same tolerance keeps that discrepancy,
    one tolerance lower, so the shapes centred there are in both lanes or in
    neither.
    """
    page, diagram = _diagram(vsdx_copy)
    lanes = diagram.lanes
    pairs = [(upper, lower) for upper, lower in itertools.pairwise(lanes) if _band(upper)[0] != _band(lower)[1]]
    assert pairs, "the capture is expected to hold a pair of edges Visio rounded apart"
    decision = page.shapes.require_text("Decision")
    for upper, lower in pairs:
        edge = _band(lower)[1]
        for step in range(-40, 41):
            for base in (0.0, -1e-9, 1e-9):
                decision.y = edge + base + step * 2.5e-16
                assert diagram.lane_for(decision) in (upper, lower), decision.y


def test_only_a_numbered_copy_of_the_container_is_a_container(vsdx_copy):
    """Fails if a shape merely named like the container, such as `CFF Container.backup`, is taken for one."""
    page, diagram = _diagram(vsdx_copy)
    lookalike = copy.deepcopy(next(iter(diagram.shapes_in(diagram.lanes[0]))).xml)
    lookalike.attrib["ID"] = "9999"
    lookalike.attrib["NameU"] = "CFF Container.backup"
    page.xml.getroot().find(f"{namespace}Shapes").append(lookalike)

    assert page.require_swimlanes().container == diagram.container

    plain = Document.open(vsdx_copy("test1.vsdx")).pages[0]
    plain.xml.getroot().find(f"{namespace}Shapes").append(copy.deepcopy(lookalike))
    assert plain.swimlanes is None


def test_a_diagram_whose_container_is_deleted_refuses_before_writing(vsdx_copy):
    """Fails if `add_lane` copies a lane and grows the Swimlane List for a container that is gone."""
    page, diagram = _diagram(vsdx_copy)
    page.delete_shape(diagram.container)
    before = page.xml.getroot()
    snapshot = copy.deepcopy(before)

    with pytest.raises(InvalidOperationError, match="no longer in the document"):
        diagram.add_lane("Late")
    with pytest.raises(InvalidOperationError, match="no longer in the document"):
        diagram.lanes  # noqa: B018

    assert _xml(before) == _xml(snapshot)


def test_overlapping_lanes_make_lane_for_refuse(vsdx_copy):
    page, diagram = _diagram(vsdx_copy)
    upper, lower = diagram.lanes[0], diagram.lanes[1]
    lower.height = lower.height * 3
    decision = page.shapes.require_text("Decision")
    decision.y = upper.y

    with pytest.raises(InvalidOperationError, match="overlapping lanes"):
        diagram.lane_for(decision)


def test_a_connector_whose_endpoints_come_from_its_master_is_not_a_member(vsdx_copy):
    """Fails if lane membership looks for BeginX only on the shape, not on the master it inherits from."""
    page, diagram = _diagram(vsdx_copy)
    connector = page.shapes.require_id("57")
    assert connector.master_shape is not None and "BeginX" in connector.master_shape.cells
    connector.xml.remove(connector.cells["BeginX"].xml)
    connector = page.shapes.require_id("57")
    assert "BeginX" not in connector.cells
    lane = diagram.lane_for(connector)
    assert lane is not None
    assert connector not in diagram.shapes_in(lane)


def test_add_lane_copies_the_top_lane_above_it_and_labels_it(vsdx_copy):
    path = vsdx_copy(FIXTURE)
    vis = Document.open(path)
    diagram = vis.pages[0].require_swimlanes()
    before = diagram.lanes
    container_height = diagram.container.height

    new_lane = diagram.add_lane("Test lane")

    assert diagram.lanes == (new_lane, *before)
    assert new_lane.ID not in {lane.ID for lane in before}
    assert new_lane.y == pytest.approx(before[0].y + LANE_PITCH_INCHES)
    assert _label(new_lane) == "Test lane"
    assert diagram.container.height == pytest.approx(container_height + LANE_PITCH_INCHES)
    vis.save(path)
    assert zipfile.ZipFile(path).testzip() is None
    assert len(Document.open(path).pages[0].require_swimlanes().lanes) == len(before) + 1


def test_add_lane_gives_the_copy_its_own_ids(vsdx_copy):
    page, diagram = _diagram(vsdx_copy)
    diagram.add_lane()
    ids = [shape.ID for shape in page.shapes]
    assert len(ids) == len(set(ids))


def test_move_to_lane_centres_the_shape_on_the_lane(vsdx_copy):
    path = vsdx_copy(FIXTURE)
    vis = Document.open(path)
    page = vis.pages[0]
    diagram = page.require_swimlanes()
    decision = page.shapes.require_text("Decision")
    x = decision.x
    target = diagram.lanes[0]
    assert diagram.lane_for(decision) != target

    diagram.move_to_lane(decision, target)

    assert (decision.x, decision.y) == pytest.approx((x, target.y))
    assert diagram.lane_for(decision) == target
    vis.save(path)
    reopened = Document.open(path).pages[0]
    assert (
        reopened.require_swimlanes().lane_for(reopened.shapes.require_text("Decision"))
        == (reopened.require_swimlanes().lanes[0])
    )


def test_move_to_lane_leaves_a_member_where_it_is(vsdx_copy):
    page, diagram = _diagram(vsdx_copy)
    decision = page.shapes.require_text("Decision")
    lane = diagram.lane_for(decision)
    y = decision.y

    diagram.move_to_lane(decision, lane)

    assert decision.y == y


@pytest.mark.parametrize("operation", ["shapes_in", "set_lane_label", "move_to_lane"])
def test_a_shape_that_is_not_a_lane_is_refused(vsdx_copy, operation):
    page, diagram = _diagram(vsdx_copy)
    decision = page.shapes.require_text("Decision")
    arguments = {
        "shapes_in": (decision,),
        "set_lane_label": (decision, "Renamed"),
        "move_to_lane": (decision, decision),
    }[operation]

    with pytest.raises(InvalidOperationError, match="not a swimlane lane"):
        getattr(diagram, operation)(*arguments)


def test_set_lane_label_writes_the_row_and_the_heading(vsdx_copy):
    _, diagram = _diagram(vsdx_copy)
    lane = diagram.lanes[0]

    diagram.set_lane_label(lane, "Renamed")

    assert _label(lane) == "Renamed"
    assert lane.descendants.matching_text("Renamed")


@pytest.mark.parametrize("name", ["get_container", "add_swimlane", "add_shape_to_lane"])
def test_the_0x_page_swimlane_calls_are_gone(name):
    assert not hasattr(Page, name)


def test_the_containers_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        __import__("vsdxkit.containers")
