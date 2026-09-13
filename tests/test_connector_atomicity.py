"""Connector creation and retargeting must be failure-atomic.

Issue #9: both operations mutated the package before validating point-glue
inputs, so a caught ValueError left shapes, masters, relationships, cells or
Connect records half-changed. These tests snapshot the full observable state
and prove rejected inputs change nothing.
"""

import os

import pytest

from vsdx import Connect, VisioFile

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def _snapshot(page):
    """Observable package state: shapes, cells, records, masters, page rels."""
    shapes = sorted((s.ID, s.text, tuple(sorted(s.cells))) for s in page.all_shapes)
    records = sorted((c.from_id, c.to_id, c.from_rel, c.to_rel) for c in page.connects)
    document = page.vis
    master_parts = sorted(
        name for name in document.zip_file_contents if name.endswith((".xml", ".rels")) and "/masters/" in name
    )
    page_rels = sorted(name for name in document.zip_file_contents if name.endswith("page1.xml.rels"))
    document_rels = document.document_rels()
    rel_types = sorted(r.attrib.get("Type", "") for r in document_rels)
    return shapes, records, master_parts, page_rels, rel_types


@pytest.fixture
def atomicity_page(vsdx_copy):
    path = vsdx_copy("test8_simple_connector.vsdx")
    with VisioFile(path) as vis:
        yield vis.pages[0]


def test_create_rejects_invalid_connection_point_without_mutating_package(atomicity_page):
    shapes = atomicity_page.all_shapes
    a, b = shapes[0], shapes[1]
    before = _snapshot(atomicity_page)
    with pytest.raises(ValueError, match="connection point"):
        Connect.create(page=atomicity_page, from_shape=a, to_shape=b, route="point", from_cp=999)
    assert _snapshot(atomicity_page) == before


def test_create_rejects_negative_connection_point_without_mutating_package(atomicity_page):
    """Zero-based indices: negatives are invalid even before the upper bound."""
    shapes = atomicity_page.all_shapes
    a, b = shapes[0], shapes[1]
    before = _snapshot(atomicity_page)
    with pytest.raises(ValueError, match="connection point"):
        Connect.create(page=atomicity_page, from_shape=a, to_shape=b, route="point", from_cp=-1)
    assert _snapshot(atomicity_page) == before


def test_retarget_rejects_invalid_connection_point_without_mutating_package(vsdx_copy):
    """A rejected retarget must keep the connector's original records intact."""
    path = vsdx_copy("test4_connectors.vsdx")
    with VisioFile(path) as vis:
        page = vis.pages[0]
        connectors = [s for s in page.all_shapes if "BeginX" in s.cells]
        assert connectors, "fixture must contain a connector"
        connector = connectors[0]
        other = next(s for s in page.all_shapes if "BeginX" not in s.cells)
        records_before = sorted((c.from_id, c.to_id, c.from_rel, c.to_rel) for c in page.connects)
        with pytest.raises(ValueError, match="connection point"):
            Connect.retarget(
                page,
                connector,
                to_shape=other,
                route="point",
                to_cp=999,
            )
        records_after = sorted((c.from_id, c.to_id, c.from_rel, c.to_rel) for c in page.connects)
        assert records_after == records_before, "rejected retarget removed the connector's records"


def test_create_with_valid_point_glue_still_works(vsdx_copy):
    """The atomicity guard must not break the valid path (fixture with real connection points)."""
    path = vsdx_copy("fixtures/com_reference/s05_swimlanes_cfflow.vsdx")
    with VisioFile(path) as vis:
        page = vis.pages[0]
        a = page.find_shape_by_id("90")
        b = page.find_shape_by_id("97")
        assert a is not None and b is not None
        records_before = len(page.connects)
        connector = Connect.create(page=page, from_shape=a, to_shape=b, route="point")
        assert connector is not None
        assert len(page.connects) == records_before + 2
