"""Swimlane / container tests against the real Visio CFF capture."""

import zipfile

from vsdxkit.containers import get_user_row, set_user_row_value
from vsdxkit.document import Document

FIXTURE = "fixtures/com_reference/s05_swimlanes_cfflow.vsdx"


def test_container_discovery(vsdx_copy):
    vis = Document.open(vsdx_copy(FIXTURE))
    page = vis.pages[0]
    container = page.get_container()
    assert container is not None
    assert container.container_shape.shape_name == "CFF Container"
    assert container.swimlane_list.shape_name == "Swimlane List"


def test_lanes_discovered_in_visual_order(vsdx_copy):
    vis = Document.open(vsdx_copy(FIXTURE))
    lanes = vis.pages[0].get_container().lanes
    assert len(lanes) == 3
    ys = [lane.y for lane in lanes]
    assert ys == sorted(ys, reverse=True)  # top lane first
    labels = []
    for lane in lanes:
        row = get_user_row(lane, "visHeadingText")
        values = [c.attrib.get("V") for c in row if c.attrib.get("N") == "Value"]
        labels.append(values[0])
    assert labels == ["Function 1", "Function 2", "Function 3"]


def test_membership_is_geometric(vsdx_copy):
    vis = Document.open(vsdx_copy(FIXTURE))
    container = vis.pages[0].get_container()
    lanes = container.lanes
    # every member lies inside its lane band
    for lane in lanes:
        bottom, top = container.lane_band(lane)
        for member in container.members(lane):
            assert bottom <= member.y <= top
    # decision shape sits in the middle lane per the capture
    decision = vis.pages[0].shapes.by_text("Decision")
    assert container.lane_of(decision) is not None


def test_a_connector_whose_endpoints_come_from_its_master_is_not_a_member(vsdx_copy):
    """Fails if lane membership looks for BeginX only on the shape, not on the master it inherits from."""
    vis = Document.open(vsdx_copy(FIXTURE))
    page = vis.pages[0]
    container = page.get_container()
    connector = page.shapes.require_id("57")
    assert connector.master_shape is not None and "BeginX" in connector.master_shape.cells
    connector.xml.remove(connector.cells["BeginX"].xml)
    connector = page.shapes.require_id("57")  # a Shape reads its cells when it is built
    assert "BeginX" not in connector.cells
    lane = next(lane for lane in container.lanes if _in_band(container, lane, connector))
    assert "57" not in [member.ID for member in container.members(lane)]


def _in_band(container, lane, shape) -> bool:
    bottom, top = container.lane_band(lane)
    return bottom <= shape.y <= top


def test_add_swimlane_clones_and_labels(vsdx_copy):
    path = vsdx_copy(FIXTURE)
    vis = Document.open(path)
    page = vis.pages[0]
    container = page.get_container()
    original_count = len(container.lanes)
    original_ids = {lane.ID for lane in container.lanes}
    new_lane = page.add_swimlane("Test lane")
    assert len(container.lanes) == original_count + 1
    assert new_lane.ID not in original_ids
    # positioned one pitch above the previous top lane
    previous_top = container.lanes[1]
    assert abs(new_lane.y - (previous_top.y + 1.18110236220472)) < 0.001
    row = get_user_row(new_lane, "visHeadingText")
    values = [c.attrib.get("V") for c in row if c.attrib.get("N") == "Value"]
    assert values == ["Test lane"]
    vis.save(path)
    assert zipfile.ZipFile(path).testzip() is None


def test_add_shape_to_lane_moves_geometry(vsdx_copy):
    path = vsdx_copy(FIXTURE)
    vis = Document.open(path)
    page = vis.pages[0]
    container = page.get_container()
    decision = page.shapes.by_text("Decision")
    original_y = decision.y
    target_lane = container.lanes[0]
    page.add_shape_to_lane(decision, target_lane)
    assert decision.y == target_lane.y
    assert container.lane_of(decision).ID == target_lane.ID
    assert original_y != decision.y
    vis.save(path)
    vis2 = Document.open(path)
    container = vis2.pages[0].get_container()
    decision = vis2.pages[0].shapes.by_text("Decision")
    assert container.lane_of(decision).ID == container.lanes[0].ID


def test_set_user_row_value_roundtrip(vsdx_copy):
    vis = Document.open(vsdx_copy(FIXTURE))
    lane = vis.pages[0].get_container().lanes[0]
    assert set_user_row_value(lane, "visHeadingText", "Renamed") is True
    row = get_user_row(lane, "visHeadingText")
    values = [c.attrib.get("V") for c in row if c.attrib.get("N") == "Value"]
    assert values == ["Renamed"]
    # absent rows return False rather than failing
    assert set_user_row_value(lane, "noSuchRow", "x") is False
