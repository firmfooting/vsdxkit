"""A `<Connect>` record is read from the package, so a malformed one is a malformed package.

`Connect_Type` requires `FromSheet` and `ToSheet` and leaves `FromCell` and
`ToCell` optional. The graph queries read every record on the page, so a
record without a required attribute makes them raise `MalformedPackageError`,
and a record without an optional one is read like any other.
"""

import xml.etree.ElementTree as ET

import pytest

from vsdxkit.document import Document
from vsdxkit.errors import MalformedPackageError
from vsdxkit.shapes import Connector

NS = "{http://schemas.microsoft.com/office/visio/2012/main}"
VALID = {"FromSheet": "7", "ToSheet": "5", "FromCell": "BeginX", "ToCell": "PinX"}


def _page_with(vsdx_copy, attributes: dict[str, str]):
    page = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0]
    ET.SubElement(page.xml.find(f".//{NS}Connects"), f"{NS}Connect", attributes)
    return page


@pytest.mark.parametrize("missing", ["FromSheet", "ToSheet"])
def test_a_record_without_a_required_attribute_is_a_malformed_package(vsdx_copy, missing):
    """Fails if a record naming no connector, or nothing it is glued to, is read as floating or skipped."""
    attributes = {name: value for name, value in VALID.items() if name != missing}
    page = _page_with(vsdx_copy, attributes)
    connector = page.shapes.require_id("7")
    assert isinstance(connector, Connector)

    with pytest.raises(MalformedPackageError, match=missing):
        _ = page.shapes.require_id("5").connectors
    with pytest.raises(MalformedPackageError, match=missing):
        _ = connector.source


@pytest.mark.parametrize("optional", ["FromCell", "ToCell"])
def test_a_record_without_an_optional_attribute_is_read(vsdx_copy, optional):
    """Fails if a record that leaves out `FromCell` or `ToCell`, as the schema allows, is refused."""
    attributes = {name: value for name, value in VALID.items() if name != optional}
    page = _page_with(vsdx_copy, attributes)

    assert page.shapes.require_id("5").connectors
