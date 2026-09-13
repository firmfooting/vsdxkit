"""The Connect constructor must not produce half-initialised objects."""

import os
import xml.etree.ElementTree as ET

import pytest

import vsdx
from vsdx import Connect

FIXTURES = os.path.dirname(os.path.realpath(__file__))
namespace = "{http://schemas.microsoft.com/office/visio/2012/main}"


@pytest.fixture
def page_with_connector(vsdx_copy):
    path = vsdx_copy("test8_simple_connector.vsdx")
    with vsdx.VisioFile(path) as visio:
        yield visio.pages[0]


def _valid_connect_xml() -> ET.Element:
    return ET.Element(
        f"{namespace}Connect",
        {"FromSheet": "5", "ToSheet": "2", "FromCell": "BeginX", "ToCell": "PinX"},
    )


def test_constructor_builds_complete_state_from_valid_xml(page_with_connector):
    connect = Connect(xml=_valid_connect_xml(), page=page_with_connector)
    assert connect.from_id == "5"
    assert connect.to_id == "2"
    assert connect.from_rel == "BeginX"
    assert connect.to_rel == "PinX"
    assert connect.xml is not None
    assert connect.page is page_with_connector
    assert repr(connect)  # __repr__ works on the declared state


def test_constructor_rejects_missing_xml(page_with_connector):
    with pytest.raises(ValueError, match="requires the connection's XML"):
        Connect(xml=None, page=page_with_connector)


def test_constructor_rejects_wrong_tag(page_with_connector):
    bogus = ET.Element("NotAConnect", {"FromSheet": "1", "ToSheet": "2", "FromCell": "BeginX", "ToCell": "PinX"})
    with pytest.raises(ValueError, match="NotAConnect"):
        Connect(xml=bogus, page=page_with_connector)


@pytest.mark.parametrize("missing", ["FromSheet", "ToSheet"])
def test_constructor_rejects_missing_required_attribute(page_with_connector, missing):
    attribs = {"FromSheet": "5", "ToSheet": "2", "FromCell": "BeginX", "ToCell": "PinX"}
    del attribs[missing]
    bogus = ET.Element(f"{namespace}Connect", attribs)
    with pytest.raises(ValueError, match=missing):
        Connect(xml=bogus, page=page_with_connector)


@pytest.mark.parametrize("optional", ["FromCell", "ToCell"])
def test_optional_cell_attributes_read_as_none(page_with_connector, optional):
    """Connect_Type declares the cell attributes optional; absence is None, not an error."""
    attribs = {"FromSheet": "5", "ToSheet": "2", "FromCell": "BeginX", "ToCell": "PinX"}
    del attribs[optional]
    element = ET.Element(f"{namespace}Connect", attribs)
    connect = Connect(xml=element, page=page_with_connector)
    assert getattr(connect, "from_rel" if optional == "FromCell" else "to_rel") is None
    assert repr(connect)


def test_constructor_rejects_missing_page():
    with pytest.raises(ValueError, match="page"):
        Connect(xml=_valid_connect_xml(), page=None)
