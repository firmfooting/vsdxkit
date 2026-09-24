"""`Document` over `PackageStore`: the trees it edits are the store's trees."""

from __future__ import annotations

import copy
import os
import xml.etree.ElementTree as ET
import zipfile

import pytest
from helpers.broken_package import rewritten

from vsdxkit import namespace, r_namespace
from vsdxkit.document import Document
from vsdxkit.errors import MalformedPackageError, PartParseError, VsdxError
from vsdxkit.package import XmlPart
from vsdxkit.xmlio import serialise_part


def test_the_page_tree_is_the_stores_tree(vsdx_copy):
    """Fails if the loader parses its own copy instead of promoting the store's part."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    held = vis._package.part(page.filename)
    assert isinstance(held, XmlPart) and held.tree is page.xml


def test_the_document_parts_are_the_stores_trees(vsdx_copy):
    """Fails if load_pages/load_master_pages parse a private copy instead of the store's tree."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
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
        Document.open(path)
    except ET.ParseError as error:
        assert isinstance(error, PartParseError)
        assert "/visio/pages/page1.xml" in str(error)
        assert error.position is not None
    else:  # pragma: no cover - the assertion is the failure
        pytest.fail("a malformed page opened without an ET.ParseError")
    try:
        Document.open(path)
    except ValueError:
        pass
    else:  # pragma: no cover - the assertion is the failure
        pytest.fail("a malformed page opened without a ValueError")


@pytest.mark.allow_invalid_package  # a page that is not XML is the point
def test_malformed_xml_at_open_is_also_a_vsdx_error_with_its_position(basedir, tmp_path):
    """Fails if the malformed-part error falls outside the `VsdxError` hierarchy, or loses the parser's position.

    The sibling above holds the two spellings a malformed part had before the
    hierarchy. `except VsdxError` is the third, and the one #365 promises
    covers the open path; the `position` has to come across on the error
    itself, not only on its `__cause__`, so the catch reads the same as it did.
    """
    path = rewritten(
        os.path.join(basedir, "test1.vsdx"),
        str(tmp_path / "broken.vsdx"),
        {"visio/pages/page1.xml": b"<PageContents>"},
    )
    try:
        Document.open(path)
    except VsdxError as error:
        assert isinstance(error, MalformedPackageError)
        assert "/visio/pages/page1.xml" in str(error)
        assert error.position == error.__cause__.position
        assert error.code == error.__cause__.code
    else:  # pragma: no cover - the assertion is the failure
        pytest.fail("a malformed page opened without a VsdxError")


def test_assigning_a_document_part_replaces_it_in_the_store(vsdx_copy):
    """Fails if the `app_xml` setter stops writing the new tree through to the store."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
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
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    replacement = ET.ElementTree(ET.fromstring(serialise_part(page.xml)))
    replacement.getroot().set("VsdxkitMarker", "1")
    page.xml = replacement
    assert page.xml is replacement
    assert b"VsdxkitMarker" in (vis._package.read_bytes(page.filename) or b"")


def test_a_removed_page_does_not_write_its_part_back(vsdx_copy):
    """Fails if the `Page.xml` setter writes through even when the page's own
    part is no longer in the package, resurrecting a part `remove_page_by_index`
    already removed."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    page = vis.pages[1]
    name = page.filename
    vis.remove_page_by_index(1)
    page.xml = ET.ElementTree(ET.Element("PageContents"))
    assert vis._package.part(name) is None


def test_reassigning_the_same_tree_keeps_the_promotion_baseline(vsdx_copy):
    """Fails if the `app_xml` setter re-writes the part even when handed back
    the tree the store already holds, discarding the promotion baseline that
    lets an untouched part save as the bytes it arrived as."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    before = vis._package.part("/docProps/app.xml")
    vis.app_xml = vis.app_xml
    assert vis._package.part("/docProps/app.xml") is before


def test_an_added_page_is_in_the_store_before_any_save(vsdx_copy):
    """Fails if `_create_page` never writes the new page part into the store,
    which is the only thing a save writes -- the added page would never reach
    disk at all."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.add_page("Added")
    held = vis._package.part(page.filename)
    assert isinstance(held, XmlPart) and held.tree is page.xml


def test_a_copied_page_brings_its_rels_part_into_the_store(vsdx_copy):
    """Fails if `_create_page` assigns a copied page's `rels_xml` before its
    `rels_xml_filename`, so the `rels_xml` setter's write-through guard never
    sees a filename and the rels part never reaches the store."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    source = next(p for p in vis.pages if p.rels_xml is not None)
    copy = vis.copy_page(source)
    assert copy.rels_xml_filename is not None
    held = vis._package.part(copy.rels_xml_filename)
    assert isinstance(held, XmlPart) and held.tree is copy.rels_xml


def test_a_copied_page_still_writes_its_rels_past_an_orphan_at_the_next_name(vsdx_copy):
    """Fails if `_unused_page_part_name` checks only whether pageN.xml exists.

    An orphan `pages/_rels/pageN.xml.rels` at the name a new page is about to
    take makes the store already hold a part there before the copied page's
    `rels_xml` is ever assigned. `Page._rels_attached()` then finds a rels
    part that is not this page's own tree and refuses to write over it, so
    the assignment silently never reaches the store.
    """
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    source = next(p for p in vis.pages if p.rels_xml is not None)
    candidate = vis._unused_page_part_name()
    orphan_name = f"/visio/pages/_rels/{candidate}.rels"
    vis._package.write_xml(orphan_name, ET.ElementTree(ET.Element("Relationships")))
    copy = vis.copy_page(source)
    held = vis._package.part(copy.rels_xml_filename)
    assert isinstance(held, XmlPart) and held.tree is copy.rels_xml


def test_importing_a_master_keeps_masters_parts_as_the_stores_trees(vsdx_copy):
    """#366 and the eager-write removal: masters.xml(.rels) are trees in the
    store, not bytes. Fails if the imported master's relationship is appended
    to a rels tree the store no longer holds -- `isinstance(rels, XmlPart)`
    alone would still pass with an orphaned tree, so this also asserts the
    imported `<Master>`'s own `r:id` is actually present in the stored
    masters.xml.rels."""
    vis = Document.open(vsdx_copy("test3_house.vsdx"))
    page = vis.pages[0]
    page.connect_shapes(page.shapes.require_id("1"), page.shapes.require_id("5"))
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
    """Fails if the masters bootstrap writes masters.xml.rels as a bytes
    literal rather than a tree through the store."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    vis._masters.bootstrap()
    assert isinstance(vis._package.part("/visio/masters/masters.xml"), XmlPart)
    assert isinstance(vis._package.part("/visio/masters/_rels/masters.xml.rels"), XmlPart)


def test_a_removed_page_does_not_clobber_a_page_that_reuses_its_part_name(vsdx_copy, tmp_path):
    """Fails if `Page._attached()` asks only whether a part is at the page's name, not whether it is the page's tree.

    Removing a page frees its part name, and the next page added takes it.
    A caller still holding the removed page then finds "its" part present
    again, and an assignment to its `xml` or `rels_xml` writes over the new
    page's part -- or gives the new page a relationship part it never had.
    """
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    removed = vis.pages[0]
    vis.remove_page_by_index(0)
    fresh = vis.add_page(name="Fresh")
    assert fresh.filename == removed.filename  # the fixture has changed if this does not hold
    name = fresh.filename
    rels_name = removed.rels_xml_filename
    removed.xml = ET.ElementTree(ET.Element(f"{namespace}PageContents"))
    removed.rels_xml = ET.ElementTree(ET.Element("Relationships"))
    held = vis._package.part(name)
    assert isinstance(held, XmlPart) and held.tree is fresh.xml
    assert vis._package.part(rels_name) is None
    root = fresh.xml.getroot()
    assert root is not None
    root.set("VsdxkitMarker", "1")
    out = str(tmp_path / "test4_connectors-fresh.vsdx")
    vis.save(out)
    with zipfile.ZipFile(out) as archive:
        assert b'VsdxkitMarker="1"' in archive.read("visio/pages/page1.xml")


@pytest.mark.parametrize(
    ("attribute", "name"),
    [
        ("app_xml", "/docProps/app.xml"),
        ("document_xml", "/visio/document.xml"),
        ("document_xml_rels", "/visio/_rels/document.xml.rels"),
        ("pages_xml", "/visio/pages/pages.xml"),
        ("pages_xml_rels", "/visio/pages/_rels/pages.xml.rels"),
        ("content_types_xml", "/[Content_Types].xml"),
        ("masters_xml", "/visio/masters/masters.xml"),
    ],
)
def test_setting_a_document_part_to_none_is_refused(vsdx_copy, attribute, name):
    """Fails if a Document document-part setter takes None as "remove the part" again.

    Removing `app.xml` or `document.xml` from the store leaves the
    relationship that points at it and the content-type override that
    describes it, so the saved package promises a part it does not hold.
    None is refused, and the part stays where it was.
    """
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    before = vis._package.part(name)
    assert before is not None  # the fixture has changed if this does not hold
    with pytest.raises(ValueError, match=attribute):
        setattr(vis, attribute, None)
    assert vis._package.part(name) is before


def test_assigning_masters_xml_over_a_malformed_part_does_not_parse_it(vsdx_copy):
    """Fails if the `masters_xml` setter reads the current part through `read_xml`, which promotes it.

    The setter only needs to know whether the root it is handed is already
    the part's own. Asking that by promoting the part parses it, and a part
    whose bytes are not XML then makes an assignment that would replace it
    raise instead.
    """
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    vis._package.write_bytes("/visio/masters/masters.xml", b"<Masters")
    root = ET.Element(f"{namespace}Masters")
    vis.masters_xml = root
    held = vis._package.part("/visio/masters/masters.xml")
    assert isinstance(held, XmlPart) and held.tree.getroot() is root


def test_assigning_masters_xml_writes_through_to_disk(vsdx_copy, tmp_path):
    """Fails if the `masters_xml` setter stops putting the new root into the store, so the save never sees it."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    root = copy.deepcopy(vis.masters_xml)
    assert root is not None
    root.set("VsdxkitMarker", "1")
    vis.masters_xml = root
    assert vis.masters_xml is root
    out = str(tmp_path / "test4_connectors-masters.vsdx")
    vis.save(out)
    with zipfile.ZipFile(out) as archive:
        assert b'VsdxkitMarker="1"' in archive.read("visio/masters/masters.xml")


def test_page_set_name_renames_the_page_in_the_saved_file(vsdx_copy, tmp_path):
    """Fails if `Page.set_name` writes a private copy of pages.xml over the store's tree.

    It used to parse pages.xml afresh, set only `Name` on that copy, and assign
    the copy to `vis.pages_xml`, after `self.name = value` had already set
    `Name` and `NameU` on the store's own tree. The copy then replaced that
    tree, so the saved `NameU` kept the old name, and Visio shows `NameU`.
    """
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    with pytest.warns(DeprecationWarning):
        vis.pages[1].set_name("VsdxkitRenamed")
    out = str(tmp_path / "test4_connectors-renamed.vsdx")
    vis.save(out)
    with zipfile.ZipFile(out) as archive:
        pages = ET.fromstring(archive.read("visio/pages/pages.xml"))
    renamed = list(pages)[1]
    assert (renamed.get("Name"), renamed.get("NameU")) == ("VsdxkitRenamed", "VsdxkitRenamed")
