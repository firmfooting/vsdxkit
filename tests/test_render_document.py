"""`render_document` renders any document it is handed, as `Document.render` does (#113)."""

import xml.etree.ElementTree as ET
from types import MappingProxyType

import pytest

from vsdxkit.document import Document
from vsdxkit.templating import render_document


def _page_xml(document: Document) -> list[bytes]:
    return [ET.tostring(page.xml.getroot()) for page in document.pages]


def test_render_document_renders_as_document_render_does(vsdx_copy):
    """Fails if the method and the function stop being the same rendering, or the function renders nothing."""
    context = {"n": 2}
    unrendered = Document.open(vsdx_copy("test_jinja_self_refs.vsdx"))
    by_method = Document.open(vsdx_copy("test_jinja_self_refs.vsdx"))
    by_function = Document.open(vsdx_copy("test_jinja_self_refs.vsdx"))
    by_method.render(context)
    render_document(by_function, context)
    assert _page_xml(by_function) == _page_xml(by_method)
    assert _page_xml(by_function) != _page_xml(unrendered)
    # shape 2 is `{% set self.x=n*2 %}`: the statement is gone, and x is n * 2
    shape = by_function.pages[0].shapes.require_id("2")
    assert shape.text == "This shape sets x to n * 2"
    assert shape.x == pytest.approx(4.0)


def test_a_read_only_mapping_renders(vsdx_copy):
    """Fails if rendering needs a `dict`: the context is any `Mapping`."""
    document = Document.open(vsdx_copy("test_jinja_loop.vsdx"))
    items = ["Alpha-item", "Beta-item", "Gamma-item"]
    render_document(document, MappingProxyType({"date": "today", "scenario": "Mapped", "test_list": items}))
    texts = [shape.text for shape in document.pages[0].shapes]
    assert any("Mapped" in text for text in texts)
    assert all(any(item in text for text in texts) for item in items)


def test_document_has_no_base_but_object():
    """Fails if Document takes behaviour from a base class again (#94, #113)."""
    assert Document.__bases__ == (object,)
