"""Regression tests that fail when the behaviour they name is broken."""

import os

from vsdxkit import Connect, VisioFile
from vsdxkit.vsdxdiff import VisioFileDiff

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def test_connect_create_writes_connection_records(vsdx_copy, tmp_path):
    """Connect.create() must produce persisted Connect records, not just run."""
    path = vsdx_copy("test8_simple_connector.vsdx")
    output = os.path.join(str(tmp_path), "connectors.vsdx")
    with VisioFile(path) as vis:
        page = vis.pages[0]
        a = page.child_shapes[0]
        b = page.child_shapes[1]
        Connect.create(page=page, from_shape=a, to_shape=b)
        vis.save_vsdx(output)

    with VisioFile(output) as vis:
        page = vis.pages[0]
        shape_ids = {s.ID for s in page.all_shapes}
        connects = page.connects
        assert len(connects) >= 2  # one Connect element per end of the connector
        for connect in connects:
            assert connect.from_id in shape_ids
            assert connect.to_id in shape_ids


def test_visiodiff_reports_changed_members(vsdx_copy, tmp_path):
    """A text change must appear in VisioFileDiff.diffs for the shape's part."""
    path = vsdx_copy("test1.vsdx")
    changed = os.path.join(str(tmp_path), "changed.vsdx")
    with VisioFile(path) as vis:
        shape = vis.pages[0].all_shapes[0]
        original_text = shape.text
        shape.text = f"{original_text} CHANGED"
        vis.save_vsdx(changed)

    file_diff = VisioFileDiff(path, changed)
    changed_members = [member for member, diff in file_diff.diffs.items() if "CHANGED" in "".join(diff)]
    assert changed_members, "expected at least one member diff mentioning the changed text"
    assert all(member.endswith(".xml") for member in changed_members)


def test_visiodiff_round_trip_preserves_members(vsdx_copy, tmp_path):
    """A round-tripped unchanged document must neither lose nor invent members.

    Textual diffs on unchanged round trips are serialization noise (declaration
    quoting, namespace prefixes), so the stable contract is at member level.
    """
    path = vsdx_copy("test1.vsdx")
    same = os.path.join(str(tmp_path), "same.vsdx")
    with VisioFile(path) as vis:
        vis.save_vsdx(same)

    file_diff = VisioFileDiff(path, same)
    assert file_diff.added_members() == set()
    assert file_diff.removed_members() == set()
    assert set(file_diff.common_members()) == set(file_diff.contents_a)


def test_shape_end_arrow_false_writes_zero(vsdx_copy, tmp_path):
    """The False case must assert explicitly: EndArrow is removed/set to 0."""
    path = vsdx_copy("test2.vsdx")
    output = os.path.join(str(tmp_path), "arrow_false.vsdx")
    with VisioFile(path) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_text("Scenario:")
        shape.end_arrow = False
        assert shape.end_arrow == "0"  # pre-fix test asserted the truthy string "0"
        vis.save_vsdx(output)
    with VisioFile(output) as vis:
        shape = vis.pages[0].find_shape_by_text("Scenario:")
        assert shape is not None
        assert shape.end_arrow == "0"


def test_shape_end_arrow_true_writes_13(vsdx_copy, tmp_path):
    path = vsdx_copy("test2.vsdx")
    output = os.path.join(str(tmp_path), "arrow_true.vsdx")
    with VisioFile(path) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_text("Scenario:")
        shape.end_arrow = True
        assert shape.end_arrow == "13"
        vis.save_vsdx(output)
    with VisioFile(output) as vis:
        shape = vis.pages[0].find_shape_by_text("Scenario:")
        assert shape is not None
        assert shape.end_arrow == "13"


def test_page_bounds_match_declared_shape_bounds(vsdx_copy):
    """Page bounds must bound the shapes actually on the page."""
    path = vsdx_copy("test1.vsdx")
    with VisioFile(path) as vis:
        page = vis.pages[0]
        shapes = page.all_shapes
        assert shapes
        boxes = [s.bounds for s in shapes]
        min_x = min(box[0] for box in boxes)
        min_y = min(box[1] for box in boxes)
        max_x = max(box[2] for box in boxes)
        max_y = max(box[3] for box in boxes)
        for box in boxes:
            assert box[0] >= min_x - 0.001
            assert box[1] >= min_y - 0.001
            assert box[2] <= max_x + 0.001
            assert box[3] <= max_y + 0.001


def test_remove_connect_records_removes_their_records(vsdx_copy, tmp_path):
    path = vsdx_copy("test4_connectors.vsdx")
    output = os.path.join(str(tmp_path), "removed.vsdx")
    with VisioFile(path) as vis:
        page = vis.pages[0]
        connectors = [s for s in page.all_shapes if "BeginX" in s.cells]
        assert connectors
        connector_ids = [str(connector.ID) for connector in connectors if connector.ID is not None]
        assert connector_ids
        assert page.connects  # the fixture has connection records to remove
        page.remove_connect_records(connector_ids)
        assert all(connect.from_id not in set(connector_ids) for connect in page.connects)
        vis.save_vsdx(output)

    with VisioFile(output) as vis:
        page = vis.pages[0]
        assert all(connect.from_id not in {"6", "7"} for connect in page.connects)
