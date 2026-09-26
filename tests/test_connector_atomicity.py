"""Connector creation and retargeting must be failure-atomic.

Issue #9: both operations mutated the package before validating point-glue
inputs, so a caught ValueError left shapes, masters, relationships, cells or
Connect records half-changed. These tests snapshot the full observable state
and prove rejected inputs change nothing.
"""

import os
import xml.etree.ElementTree as ET

import pytest
from helpers.connect_records import page_records

from vsdxkit import document_rels_namespace
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.glue import ConnectorOptions, Glue
from vsdxkit.partnames import DOCUMENT_PART, relationships_part_name

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def _parts(document):
    """Every part in the document's package, by name, as the save would write it."""
    return {name: document._package.read_bytes(name) for name in document._package.names()}


def _snapshot(page):
    """Observable package state: shapes, cells, records, masters, page rels."""
    shapes = sorted((s.ID, s.text, tuple(sorted(s.cells))) for s in page.shapes)
    records = sorted((c.from_id, c.to_id, c.from_rel, c.to_rel) for c in page_records(page))
    document = page.vis
    names = document._package.names()
    master_parts = sorted(name for name in names if name.endswith((".xml", ".rels")) and "/masters/" in name)
    page_rels = sorted(name for name in names if name.endswith("page1.xml.rels"))
    document_rels = (
        document._package.require_xml(relationships_part_name(DOCUMENT_PART))
        .getroot()
        .findall(f"{document_rels_namespace}Relationship")
    )
    rel_types = sorted(r.attrib.get("Type", "") for r in document_rels)
    return shapes, records, master_parts, page_rels, rel_types


@pytest.fixture
def atomicity_page(vsdx_copy):
    path = vsdx_copy("test8_simple_connector.vsdx")
    vis = Document.open(path)
    yield vis.pages[0]


def test_create_rejects_invalid_connection_point_without_mutating_package(atomicity_page):
    shapes = list(atomicity_page.shapes)
    a, b = shapes[0], shapes[1]
    before = _snapshot(atomicity_page)
    with pytest.raises(ValueError, match="connection point"):
        atomicity_page.connect(a, b, glue=Glue.POINT, from_point=999)
    assert _snapshot(atomicity_page) == before


def test_create_rejects_negative_connection_point_without_mutating_package(atomicity_page):
    """Zero-based indices: negatives are invalid even before the upper bound."""
    shapes = list(atomicity_page.shapes)
    a, b = shapes[0], shapes[1]
    before = _snapshot(atomicity_page)
    with pytest.raises(ValueError, match="connection point"):
        atomicity_page.connect(a, b, glue=Glue.POINT, from_point=-1)
    assert _snapshot(atomicity_page) == before


def test_retarget_rejects_invalid_connection_point_without_mutating_package(vsdx_copy):
    """A rejected retarget must keep the connector's original records intact."""
    path = vsdx_copy("test4_connectors.vsdx")
    vis = Document.open(path)
    page = vis.pages[0]
    connectors = [s for s in page.shapes if "BeginX" in s.cells]
    assert connectors, "fixture must contain a connector"
    connector = connectors[0]
    other = next(s for s in page.shapes if "BeginX" not in s.cells)
    records_before = sorted((c.from_id, c.to_id, c.from_rel, c.to_rel) for c in page_records(page))
    with pytest.raises(ValueError, match="connection point"):
        connector.retarget(target=other, options=ConnectorOptions(glue=Glue.POINT, to_point=999))
    records_after = sorted((c.from_id, c.to_id, c.from_rel, c.to_rel) for c in page_records(page))
    assert records_after == records_before, "rejected retarget removed the connector's records"


def test_create_with_valid_point_glue_still_works(vsdx_copy):
    """The atomicity guard must not break the valid path (fixture with real connection points)."""
    path = vsdx_copy("fixtures/com_reference/s05_swimlanes_cfflow.vsdx")
    vis = Document.open(path)
    page = vis.pages[0]
    a = page.shapes.by_id("90")
    b = page.shapes.by_id("97")
    assert a is not None and b is not None
    records_before = len(page_records(page))
    connector = page.connect(a, b, glue=Glue.POINT)
    assert connector is not None
    assert len(page_records(page)) == records_before + 2


def test_connect_on_a_removed_page_writes_nothing(vsdx_copy):
    """Fails if a page no longer in its document imports the connector's master, or takes a connector, before refusing."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    page = vis.pages[0]
    a, b = page.children.require_id("6"), page.children.require_id("16")
    vis.pages.delete(page)
    parts = _parts(vis)
    page_xml = ET.tostring(page.xml.getroot())

    with pytest.raises(InvalidOperationError, match="no longer in its document, so nothing can be connected on it"):
        page.connect(a, b)

    assert _parts(vis) == parts
    assert ET.tostring(page.xml.getroot()) == page_xml
