"""#89's acceptance: a save changes exactly the members that changed.

Expected sides are read with `zipfile` from the fixture, never through vsdxkit.
"""

from __future__ import annotations

import glob
import os
import re
import zipfile
from datetime import datetime

import pytest

import vsdxkit
from vsdxkit.xmlio import parse_part, serialise_part

BASEDIR = os.path.dirname(os.path.realpath(__file__))
FIXTURES = sorted(os.path.basename(p) for p in glob.glob(os.path.join(BASEDIR, "*.vsd[xm]")))


def _members(path) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        return [(i.filename, archive.read(i)) for i in archive.infolist() if not i.is_dir()]


@pytest.mark.parametrize("fixture", FIXTURES)
def test_open_and_save_is_byte_identical(fixture, vsdx_copy, tmp_path):
    source = vsdx_copy(fixture)
    target = tmp_path / f"out{os.path.splitext(fixture)[1]}"
    with vsdxkit.VisioFile(source) as vis:
        for page in vis.pages:  # read every shape, promoting nothing new but walking the trees
            _ = [shape.text for shape in page.all_shapes]
        vis.save_vsdx(str(target))
    assert _members(target) == _members(source)


def test_one_edit_changes_one_member(vsdx_copy, tmp_path):
    source = vsdx_copy("test8_simple_connector.vsdx")
    target = tmp_path / "out.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        shape = vis.pages[0].find_shape_by_text("Shape A")
        assert shape is not None
        shape.text = "Renamed A"
        page_member = vis.pages[0].filename[1:]
        vis.save_vsdx(str(target))
    before, after = dict(_members(source)), dict(_members(target))
    assert list(after) == list(before)
    assert [name for name in before if before[name] != after[name]] == [page_member]


def test_a_second_save_carries_a_second_edit(vsdx_copy, tmp_path):
    """Review Focus 3: comparing against the baseline must not use the change up."""
    source = vsdx_copy("test8_simple_connector.vsdx")
    first, second = tmp_path / "first.vsdx", tmp_path / "second.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        shape = vis.pages[0].find_shape_by_text("Shape A")
        assert shape is not None
        shape.text = "Once"
        vis.save_vsdx(str(first))
        shape.text = "Twice"
        vis.save_vsdx(str(second))
    with vsdxkit.VisioFile(str(second)) as vis:
        assert vis.pages[0].find_shape_by_text("Twice") is not None


def test_save_as_then_save_writes_the_original(vsdx_copy, tmp_path):
    """Review Focus 4, through VisioFile."""
    source = vsdx_copy("test8_simple_connector.vsdx")
    elsewhere = tmp_path / "elsewhere.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        vis.save_vsdx(str(elsewhere))
        shape = vis.pages[0].find_shape_by_text("Shape A")
        assert shape is not None
        shape.text = "In place"
        vis.save_vsdx()
    with vsdxkit.VisioFile(source) as vis:
        assert vis.pages[0].find_shape_by_text("In place") is not None
    with vsdxkit.VisioFile(str(elsewhere)) as vis:
        assert vis.pages[0].find_shape_by_text("In place") is None


def test_reassigning_filename_redirects_an_in_place_save(vsdx_copy, tmp_path):
    """Fails if an in-place save writes to the path the store was opened from when `vis.filename` has changed since.

    Before the store, `save_vsdx()` with no argument wrote to `self.filename`,
    so assigning it was how a caller pointed the next plain save somewhere
    else. The store remembers the absolute path it was opened from, which is
    what an unchanged `filename` means; a changed one is still the caller's
    destination. The source must be left as it was.
    """
    source = vsdx_copy("test8_simple_connector.vsdx")
    with open(source, "rb") as handle:
        original = handle.read()
    other = str(tmp_path / "other.vsdx")
    with vsdxkit.VisioFile(source) as vis:
        shape = vis.pages[0].find_shape_by_text("Shape A")
        assert shape is not None
        shape.text = "Redirected"
        vis.filename = other
        vis.save_vsdx()
    with vsdxkit.VisioFile(other) as vis:
        assert vis.pages[0].find_shape_by_text("Redirected") is not None
    with open(source, "rb") as handle:
        assert handle.read() == original


def test_a_canonically_equal_replacement_tree_saves_the_original_bytes(vsdx_copy, tmp_path):
    """Fails if assigning a new tree to a parsed part drops the baseline the part arrived with.

    Templating and page copying rebuild a page as a new tree and assign it
    wholesale. A rebuild that means exactly what the page meant is not an
    edit, and must save as the bytes the page arrived as -- which the store
    can only tell if the new tree is compared against the old part's
    baseline rather than written as a part with no history.
    """
    source = vsdx_copy("test1.vsdx")
    target = tmp_path / "out.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        page = vis.pages[0]
        page.xml = parse_part(serialise_part(page.xml))
        vis.save_vsdx(str(target))
    assert _members(target) == _members(source)


def test_rendering_a_template_rewrites_only_the_pages_it_changes(vsdx_copy, tmp_path):
    """Fails if a Jinja render's wholesale page replacement respells a page it did not change.

    Every page of test1.vsdx is rendered and replaced. Only page 1 holds Jinja
    expressions -- `{{scenario}}` and `{{date}}`, which an empty context
    renders as nothing -- so page 1 is the one page whose bytes may change;
    the other two mean what they meant and must save as they arrived.
    """
    source = vsdx_copy("test1.vsdx")
    target = tmp_path / "out.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        vis.jinja_render_vsdx(context={})
        vis.save_vsdx(str(target))
    pages = [name for name, _ in _members(source) if re.fullmatch(r"visio/pages/page\d+\.xml", name)]
    assert len(pages) == 3  # the fixture has changed if this does not hold
    before, after = dict(_members(source)), dict(_members(target))
    assert [name for name in pages if before[name] != after[name]] == ["visio/pages/page1.xml"]


def test_a_rendered_template_reaches_disk(vsdx_copy, tmp_path):
    """Jinja replaces each page's tree wholesale; nothing rewrites it at save any more."""
    source = vsdx_copy("test_jinja.vsdx")
    target = tmp_path / "rendered.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        vis.jinja_render_vsdx(context={"date": datetime(2026, 9, 23), "scenario": "VsdxkitRendered", "x": 2, "y": 2})
        vis.save_vsdx(str(target))
    with zipfile.ZipFile(target) as archive:
        pages = b"".join(archive.read(n) for n in archive.namelist() if n.startswith("visio/pages/page"))
    assert b"VsdxkitRendered" in pages


def test_a_tree_held_across_a_save_stays_the_documents_tree(vsdx_copy, tmp_path):
    """Fails if `save_vsdx` turns a part back into bytes, or swaps in a tree of its own.

    The trees a document edits are the store's own, and a save only writes them
    out. A save that re-serialised a part through the zip view would leave the
    caller's reference pointing at a tree the document no longer holds, and an
    edit made to it afterwards would never reach the next save.
    """
    source = vsdx_copy("test1.vsdx")
    first, second = tmp_path / "first.vsdx", tmp_path / "second.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        app, pages, page = vis.app_xml, vis.pages_xml, vis.pages[0].xml
        page_member = vis.pages[0].filename[1:]
        vis.save_vsdx(str(first))
        assert vis.app_xml is app
        assert vis.pages_xml is pages
        assert vis.pages[0].xml is page

        shape = next(page.getroot().iter("{http://schemas.microsoft.com/office/visio/2012/main}Shape"))
        shape.set("NameU", "HeldAcrossSave")
        vis.save_vsdx(str(second))
    with zipfile.ZipFile(first) as archive:
        assert b"HeldAcrossSave" not in archive.read(page_member)
    with zipfile.ZipFile(second) as archive:
        assert b"HeldAcrossSave" in archive.read(page_member)


def test_clearing_a_pages_rels_takes_its_part_out_of_the_package(vsdx_copy, tmp_path):
    """Fails if `Page.rels_xml = None` forgets the tree but leaves the part in the store.

    The save writes whatever the store holds, so a rels part the page no longer
    has would still reach the file.
    """
    source = vsdx_copy("test3_house.vsdx")
    target = tmp_path / "out.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        page = vis.pages[0]
        assert page.rels_xml_filename is not None
        rels_member = page.rels_xml_filename[1:]
        page.rels_xml = None
        vis.save_vsdx(str(target))
    with zipfile.ZipFile(source) as archive:
        assert rels_member in archive.namelist()
    with zipfile.ZipFile(target) as archive:
        assert rels_member not in archive.namelist()


def test_setting_a_pages_rels_on_a_closed_document_is_refused(vsdx_copy):
    """Fails if the `Page.rels_xml` setter stops asking whether the document is open.

    A closed document can no longer be saved, so the assignment could never
    reach a file; `Page.xml` refuses it for the same reason.
    """
    with vsdxkit.VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        page = vis.pages[0]
    with pytest.raises(vsdxkit.VisioFileNotOpen):
        page.rels_xml = None


def test_setting_a_pages_xml_to_none_is_refused(vsdx_copy):
    """Fails if `Page.xml = None` removes the page part.

    Unlike `rels_xml`, nothing else names a page's rels part, but pages.xml,
    pages.xml.rels and the content-type override all still point at the page
    part after this assignment, so removing it would leave the package
    promising a part it does not hold.
    """
    with vsdxkit.VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        page = vis.pages[0]
        part_name = page.filename
        with pytest.raises(ValueError, match=r"Page\.xml"):
            page.xml = None
        assert vis._package.part(part_name) is not None


def test_a_tree_assigned_after_a_pages_bytes_were_flushed_is_saved(vsdx_copy, tmp_path):
    """Fails if `Page.xml` stops writing through once a buffer's bytes replaced the page's tree in the store.

    Bytes written through `zip_file_contents` that do not parse land at
    `sync()` as plain bytes, so the store no longer holds the page's tree. A
    tree the caller assigns to the page afterwards is their later word; if
    the setter took the bytes for another page's part and kept out, the save
    would write the unparseable bytes and the file would not open again.
    """
    target = str(tmp_path / "saved.vsdx")
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        replacement = parse_part(serialise_part(page.xml))
        root = replacement.getroot()
        assert root is not None
        root.set("VsdxkitMarker", "1")
        buf = vis.zip_file_contents[f"{vis.directory}{page.filename}"]
        buf.seek(0)
        buf.write(b"not xml")
        vis.zip_file_contents.sync()
        page.xml = replacement
        vis.save_vsdx(target)
    with vsdxkit.VisioFile(target) as saved:
        assert saved.pages[0].xml.getroot().get("VsdxkitMarker") == "1"


def test_a_rels_tree_assigned_after_the_view_deleted_the_part_is_saved(vsdx_copy, tmp_path):
    """Fails if `Page.rels_xml` writes through only over the page's own rels tree, not where the part is gone.

    Deleting the member through `zip_file_contents` leaves the page attached
    and still holding its old rels tree. A tree the caller assigns afterwards
    is their later word and must bring the part back, or the save would leave
    the page's master and image relationships out of the file.
    """
    target = str(tmp_path / "saved.vsdx")
    with vsdxkit.VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = next(p for p in vis.pages if p.rels_xml is not None)
        assert page.rels_xml_filename is not None
        replacement = parse_part(serialise_part(page.rels_xml))
        del vis.zip_file_contents[f"{vis.directory}{page.rels_xml_filename}"]
        page.rels_xml = replacement
        member = page.rels_xml_filename[1:]
        vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert member in archive.namelist()


@pytest.mark.allow_invalid_package("unreadable-part")
def test_none_assigned_to_rels_after_the_view_wrote_bytes_over_them_removes_the_part(vsdx_copy, tmp_path):
    """Fails if `Page.rels_xml = None` keeps out when the page's rels part is bytes, not the page's tree.

    Bytes that do not parse, written through `zip_file_contents`, land at
    `sync()` as plain bytes. Assigning None afterwards must still take the
    part out, or the save writes the unparseable bytes.
    """
    target = str(tmp_path / "saved.vsdx")
    with vsdxkit.VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = next(p for p in vis.pages if p.rels_xml is not None)
        assert page.rels_xml_filename is not None
        buf = vis.zip_file_contents[f"{vis.directory}{page.rels_xml_filename}"]
        buf.seek(0)
        buf.write(b"not xml")
        vis.zip_file_contents.sync()
        page.rels_xml = None
        member = page.rels_xml_filename[1:]
        vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert member not in archive.namelist()


def test_a_tree_assigned_after_the_view_deleted_a_pages_part_is_saved(vsdx_copy, tmp_path):
    """Fails if `Page.xml` keeps out when the page's part is gone rather than someone else's.

    Deleting the member through `zip_file_contents` leaves the page in the
    document, and pages.xml, its relationship and the content-type override
    still name the part. A tree the caller assigns afterwards must bring the
    part back, or the saved package names a part it does not hold.
    """
    target = str(tmp_path / "saved.vsdx")
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        replacement = parse_part(serialise_part(page.xml))
        root = replacement.getroot()
        assert root is not None
        root.set("VsdxkitMarker", "1")
        del vis.zip_file_contents[f"{vis.directory}{page.filename}"]
        page.xml = replacement
        vis.save_vsdx(target)
    with vsdxkit.VisioFile(target) as saved:
        assert saved.pages[0].xml.getroot().get("VsdxkitMarker") == "1"
