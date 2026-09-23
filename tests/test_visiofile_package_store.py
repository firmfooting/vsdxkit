"""`VisioFile` over `PackageStore`: the trees it edits are the store's trees."""

from __future__ import annotations

import copy
import io
import os
import xml.etree.ElementTree as ET
import zipfile

import pytest
from helpers.broken_package import rewritten

from vsdxkit import VisioFile, namespace, r_namespace
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
    """Fails if `zip_file_contents` is a copy of the package rather than a view over `_package`.

    Matching the store's names in archive order is not enough: a dict built
    from the archive at open does that too, and is a second copy of the
    package that the store's writes never reach. A part the store gains after
    the mapping was taken has to show up through it.
    """
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        contents = vis.zip_file_contents
        assert list(contents) == [f"{vis.directory}{name}" for name in vis._package.names()]
        vis._package.write_bytes("/visio/vsdxkit-marker.xml", b"<Marker/>")
        key = f"{vis.directory}/visio/vsdxkit-marker.xml"
        assert list(contents)[-1] == key
        assert contents[key].getvalue() == b"<Marker/>"


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


def test_assigning_a_document_part_replaces_it_in_the_store(vsdx_copy):
    """Fails if the `app_xml` setter stops writing the new tree through to the store."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        replacement = ET.ElementTree(ET.fromstring(serialise_part(vis.app_xml)))
        root = replacement.getroot()
        assert root is not None
        root.set("VsdxkitMarker", "1")
        vis.app_xml = replacement
        assert vis.app_xml is replacement
        assert b"VsdxkitMarker" in (vis._package.read_bytes("/docProps/app.xml") or b"")


def test_assigning_page_xml_replaces_the_page_part(vsdx_copy):
    """Fails if the `Page.xml` setter stops writing the new tree through to the
    store. Jinja rendering replaces every page it renders this way."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        replacement = ET.ElementTree(ET.fromstring(serialise_part(page.xml)))
        replacement.getroot().set("VsdxkitMarker", "1")
        page.xml = replacement
        assert page.xml is replacement
        assert b"VsdxkitMarker" in (vis._package.read_bytes(vis._part_name(page.filename)) or b"")


def test_a_removed_page_does_not_write_its_part_back(vsdx_copy):
    """Fails if the `Page.xml` setter writes through even when the page's own
    part is no longer in the package, resurrecting a part `remove_page_by_index`
    already removed."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[1]
        name = vis._part_name(page.filename)
        vis.remove_page_by_index(1)
        page.xml = ET.ElementTree(ET.Element("PageContents"))
        assert vis._package.part(name) is None


def test_reassigning_the_same_tree_keeps_the_promotion_baseline(vsdx_copy):
    """Fails if the `app_xml` setter re-writes the part even when handed back
    the tree the store already holds, discarding the promotion baseline that
    lets an untouched part save as the bytes it arrived as."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        before = vis._package.part("/docProps/app.xml")
        vis.app_xml = vis.app_xml
        assert vis._package.part("/docProps/app.xml") is before


def test_an_added_page_is_in_the_store_before_any_save(vsdx_copy):
    """Fails if `_create_page` never writes the new page part into the store,
    which is the only thing a save writes -- the added page would never reach
    disk at all."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.add_page("Added")
        held = vis._package.part(vis._part_name(page.filename))
        assert isinstance(held, XmlPart) and held.tree is page.xml


def test_a_copied_page_brings_its_rels_part_into_the_store(vsdx_copy):
    """Fails if `_create_page` assigns a copied page's `rels_xml` before its
    `rels_xml_filename`, so the `rels_xml` setter's write-through guard never
    sees a filename and the rels part never reaches the store."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        source = next(p for p in vis.pages if p.rels_xml is not None)
        copy = vis.copy_page(source)
        assert copy.rels_xml_filename is not None
        held = vis._package.part(vis._part_name(copy.rels_xml_filename))
        assert isinstance(held, XmlPart) and held.tree is copy.rels_xml


def test_importing_a_master_keeps_masters_parts_as_the_stores_trees(vsdx_copy):
    """#366 and the eager-write removal: masters.xml(.rels) are trees in the
    store, not bytes. Fails if the imported master's relationship is appended
    to a rels tree the store no longer holds -- `isinstance(rels, XmlPart)`
    alone would still pass with an orphaned tree, so this also asserts the
    imported `<Master>`'s own `r:id` is actually present in the stored
    masters.xml.rels."""
    with VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        page = vis.pages[0]
        page.connect_shapes(page.find_shape_by_id("1"), page.find_shape_by_id("5"))
        masters = vis._package.part("/visio/masters/masters.xml")
        rels = vis._package.part("/visio/masters/_rels/masters.xml.rels")
        assert isinstance(masters, XmlPart) and masters.tree.getroot() is vis.masters_xml
        assert isinstance(rels, XmlPart)
        masters_root = vis.masters_xml
        assert masters_root is not None
        imported_master = max(masters_root, key=lambda m: int(m.attrib["ID"]))
        imported_rel = imported_master.find(f"{namespace}Rel")
        assert imported_rel is not None
        imported_rel_id = imported_rel.attrib[f"{r_namespace}id"]
        stored_rels = vis._package.read_xml("/visio/masters/_rels/masters.xml.rels")
        assert stored_rels is not None
        assert imported_rel_id in {r.attrib["Id"] for r in stored_rels.getroot()}


def test_bootstrapping_masters_writes_trees(vsdx_copy):
    """Fails if `_bootstrap_masters` still writes masters.xml.rels as a bytes
    literal through `zip_file_contents` instead of a tree through the store."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        vis._bootstrap_masters()
        assert isinstance(vis._package.part("/visio/masters/masters.xml"), XmlPart)
        assert isinstance(vis._package.part("/visio/masters/_rels/masters.xml.rels"), XmlPart)


def test_a_removed_page_does_not_clobber_a_page_that_reuses_its_part_name(vsdx_copy, tmp_path):
    """Fails if `Page._attached()` asks only whether a part is at the page's name, not whether it is the page's tree.

    Removing a page frees its part name, and the next page added takes it.
    A caller still holding the removed page then finds "its" part present
    again, and an assignment to its `xml` or `rels_xml` writes over the new
    page's part -- or gives the new page a relationship part it never had.
    """
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        removed = vis.pages[0]
        vis.remove_page_by_index(0)
        fresh = vis.add_page(name="Fresh")
        assert fresh.filename == removed.filename  # the fixture has changed if this does not hold
        name = vis._part_name(fresh.filename)
        rels_name = vis._part_name(removed.rels_xml_filename)
        removed.xml = ET.ElementTree(ET.Element(f"{namespace}PageContents"))
        removed.rels_xml = ET.ElementTree(ET.Element("Relationships"))
        held = vis._package.part(name)
        assert isinstance(held, XmlPart) and held.tree is fresh.xml
        assert vis._package.part(rels_name) is None
        root = fresh.xml.getroot()
        assert root is not None
        root.set("VsdxkitMarker", "1")
        out = str(tmp_path / "test4_connectors-fresh.vsdx")
        vis.save_vsdx(out)
    with zipfile.ZipFile(out) as archive:
        assert b'VsdxkitMarker="1"' in archive.read("visio/pages/page1.xml")
