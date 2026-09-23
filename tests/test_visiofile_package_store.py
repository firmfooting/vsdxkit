"""`VisioFile` over `PackageStore`: the trees it edits are the store's trees."""

from __future__ import annotations

import copy
import io
import os
import xml.etree.ElementTree as ET
import zipfile

import pytest
from helpers.broken_package import rewritten

from vsdxkit import VisioFile
from vsdxkit.package import PartParseError, XmlPart
from vsdxkit.xmlio import serialise_part, xml_to_file


def test_the_page_tree_is_the_stores_tree(vsdx_copy):
    """Fails if the loader parses its own copy instead of promoting the store's part."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        held = vis._package.part(vis._part_name(page.filename))
        assert isinstance(held, XmlPart) and held.tree is page.xml


def test_the_document_parts_are_the_stores_trees(vsdx_copy):
    """Fails if load_pages/load_master_pages parse a private copy instead of the store's tree."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        for name, tree in [
            ("/visio/pages/pages.xml", vis.pages_xml),
            ("/visio/pages/_rels/pages.xml.rels", vis.pages_xml_rels),
            ("/[Content_Types].xml", vis.content_types_xml),
            ("/docProps/app.xml", vis.app_xml),
            ("/visio/document.xml", vis.document_xml),
            ("/visio/_rels/document.xml.rels", vis.document_xml_rels),
        ]:
            held = vis._package.part(name)
            assert isinstance(held, XmlPart) and held.tree is tree, name
        masters = vis._package.part("/visio/masters/masters.xml")
        assert isinstance(masters, XmlPart) and masters.tree.getroot() is vis.masters_xml


def test_zip_file_contents_is_a_view_of_the_store(vsdx_copy):
    """Fails if `zip_file_contents` is still a plain dict rather than a view over `_package`."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        assert list(vis.zip_file_contents) == [f"{vis.directory}{name}" for name in vis._package.names()]


@pytest.mark.allow_invalid_package  # a page that is not XML is the point
def test_malformed_xml_at_open_is_both_a_parse_error_and_a_value_error(basedir, tmp_path):
    """Fails if `_promoted` raises anything that is not both `ET.ParseError` and `ValueError`.

    Before #371 a malformed part reached the caller as the bare `ET.ParseError`
    the parser raised; since, the store has reported it as a `ValueError` that
    names the part. A caller written against either must still catch it, and
    the parser's `position` must survive the rewrap so the caller can still
    say where the part broke.
    """
    path = rewritten(
        os.path.join(basedir, "test1.vsdx"),
        str(tmp_path / "broken.vsdx"),
        {"visio/pages/page1.xml": b"<PageContents>"},
    )
    try:
        VisioFile(path)
    except ET.ParseError as error:
        assert isinstance(error, PartParseError)
        assert "/visio/pages/page1.xml" in str(error)
        assert error.position is not None
    else:  # pragma: no cover - the assertion is the failure
        pytest.fail("a malformed page opened without an ET.ParseError")
    try:
        VisioFile(path)
    except ValueError:
        pass
    else:  # pragma: no cover - the assertion is the failure
        pytest.fail("a malformed page opened without a ValueError")


def _held_tree(vis, page):
    held = vis._package.part(vis._part_name(page.filename))
    assert isinstance(held, XmlPart), "the page part was detached from its tree"
    return held.tree


def test_writing_a_page_back_through_the_view_keeps_the_tree_attached(vsdx_copy, tmp_path):
    """Fails if a view write of the bytes a page's own tree serialises to replaces its XmlPart with bytes.

    `xml_to_file(page.xml, page.filename, vis.zip_file_contents)` is how
    callers wrote a page back before the store existed. Its bytes are the tree
    the store already holds, so the write has nothing to change; replacing the
    part with those bytes anyway detaches `page.xml`, and an object-model edit
    made after it lands in a tree nothing saves.
    """
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        xml_to_file(page.xml, page.filename, vis.zip_file_contents)
        assert _held_tree(vis, page) is page.xml
        shape = page.child_shapes[0]
        shape.text = "written back, then edited"
        out = str(tmp_path / "out.vsdx")
        vis.save_vsdx(out)
    with VisioFile(out) as reopened:
        assert reopened.pages[0].child_shapes[0].text == "written back, then edited"


def test_different_xml_written_through_the_view_reaches_the_page_and_disk(vsdx_copy, tmp_path):
    """Fails if a view write of new, well-formed XML to a parsed page does not become that page's tree.

    The old dict made such a write the package's page. With the page parsed,
    the write has to land in the tree `page.xml` is, or the page object and
    the package disagree and the next save of the tree writes the caller's
    change away.
    """
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        tree = page.xml
        replacement = copy.deepcopy(tree.getroot())
        replacement.set("VsdxkitMarker", "1")
        vis.zip_file_contents[page.filename] = io.BytesIO(serialise_part(ET.ElementTree(replacement)))
        assert _held_tree(vis, page) is tree
        assert page.xml.getroot().get("VsdxkitMarker") == "1"
        out = str(tmp_path / "out.vsdx")
        vis.save_vsdx(out)
    with zipfile.ZipFile(out) as archive:
        assert b'VsdxkitMarker="1"' in archive.read("visio/pages/page1.xml")


def test_truncating_a_read_buffer_of_a_parsed_page_keeps_the_tree_attached(vsdx_copy):
    """Fails if a no-op truncate() on a parsed page's buffer replaces the page's XmlPart with bytes.

    `truncate()` writes the buffer through, and at the end of the buffer it
    changes nothing. Detaching the page for it would leave `page.xml` a tree
    the package no longer holds.
    """
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        buffer = vis.zip_file_contents[page.filename]
        buffer.read()
        buffer.truncate()
        assert _held_tree(vis, page) is page.xml
