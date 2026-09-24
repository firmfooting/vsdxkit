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

from vsdxkit.vsdxfile import VisioFile
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
    vis = VisioFile(source)
    for page in vis.pages:  # read every shape, promoting nothing new but walking the trees
        _ = [shape.text for shape in page.all_shapes]
    vis.save_vsdx(str(target))
    assert _members(target) == _members(source)


def test_one_edit_changes_one_member(vsdx_copy, tmp_path):
    source = vsdx_copy("test8_simple_connector.vsdx")
    target = tmp_path / "out.vsdx"
    vis = VisioFile(source)
    shape = vis.pages[0].shapes.by_text("Shape A")
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
    vis = VisioFile(source)
    shape = vis.pages[0].shapes.by_text("Shape A")
    assert shape is not None
    shape.text = "Once"
    vis.save_vsdx(str(first))
    shape.text = "Twice"
    vis.save_vsdx(str(second))
    vis = VisioFile(str(second))
    assert vis.pages[0].shapes.by_text("Twice") is not None


def test_save_as_then_save_writes_the_original(vsdx_copy, tmp_path):
    """Review Focus 4, through VisioFile."""
    source = vsdx_copy("test8_simple_connector.vsdx")
    elsewhere = tmp_path / "elsewhere.vsdx"
    vis = VisioFile(source)
    vis.save_vsdx(str(elsewhere))
    shape = vis.pages[0].shapes.by_text("Shape A")
    assert shape is not None
    shape.text = "In place"
    vis.save_vsdx()
    vis = VisioFile(source)
    assert vis.pages[0].shapes.by_text("In place") is not None
    vis = VisioFile(str(elsewhere))
    assert vis.pages[0].shapes.by_text("In place") is None


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
    vis = VisioFile(source)
    shape = vis.pages[0].shapes.by_text("Shape A")
    assert shape is not None
    shape.text = "Redirected"
    vis.filename = other
    vis.save_vsdx()
    vis = VisioFile(other)
    assert vis.pages[0].shapes.by_text("Redirected") is not None
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
    vis = VisioFile(source)
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
    vis = VisioFile(source)
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
    vis = VisioFile(source)
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
    vis = VisioFile(source)
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
    vis = VisioFile(source)
    page = vis.pages[0]
    assert page.rels_xml_filename is not None
    rels_member = page.rels_xml_filename[1:]
    page.rels_xml = None
    vis.save_vsdx(str(target))
    with zipfile.ZipFile(source) as archive:
        assert rels_member in archive.namelist()
    with zipfile.ZipFile(target) as archive:
        assert rels_member not in archive.namelist()


def test_setting_a_pages_xml_to_none_is_refused(vsdx_copy):
    """Fails if `Page.xml = None` removes the page part.

    Unlike `rels_xml`, nothing else names a page's rels part, but pages.xml,
    pages.xml.rels and the content-type override all still point at the page
    part after this assignment, so removing it would leave the package
    promising a part it does not hold.
    """
    vis = VisioFile(vsdx_copy("test3_house.vsdx"))
    page = vis.pages[0]
    part_name = page.filename
    with pytest.raises(ValueError, match=r"Page\.xml"):
        page.xml = None
    assert vis._package.part(part_name) is not None


def test_a_rels_tree_assigned_after_the_part_is_cleared_is_saved(vsdx_copy, tmp_path):
    """Fails if `Page.rels_xml` writes through only over the page's own rels tree, not where the part is gone.

    `Page.rels_xml = None` takes the part out of the package and leaves the
    page attached with no rels part at all. A tree the caller assigns
    afterwards is their later word and must bring the part back, or the save
    would leave the page's master and image relationships out of the file.
    """
    target = str(tmp_path / "saved.vsdx")
    vis = VisioFile(vsdx_copy("test4_connectors.vsdx"))
    page = next(p for p in vis.pages if p.rels_xml is not None)
    assert page.rels_xml is not None
    replacement = parse_part(serialise_part(page.rels_xml))
    page.rels_xml = None
    page.rels_xml = replacement
    assert page.rels_xml_filename is not None
    member = page.rels_xml_filename[1:]
    vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert member in archive.namelist()


def _two_pages_on_one_part(source: str, crafted: str) -> None:
    """Write `source` again with its second page's relationship aimed at the first page's part."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(crafted, "w") as rewritten:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == "visio/pages/_rels/pages.xml.rels":
                data = data.replace(b'Target="page2.xml"', b'Target="page1.xml"')
            rewritten.writestr(entry, data)


@pytest.mark.allow_invalid_package("reused-page-part")
def test_a_tree_assigned_after_the_pages_part_is_removed_is_saved(vsdx_copy, tmp_path):
    """Fails if `Page.xml` keeps out when the page's part is gone rather than someone else's.

    Nothing at open stops two pages' relationships targeting one part, and
    then the two pages share it. Removing one (`remove_page_by_index`) takes
    the part out from under the other, which stays in the document with
    pages.xml and its own relationship still naming the part. A tree the
    caller assigns to it afterwards must bring the part back, or the saved
    package names a part it does not hold.
    """
    crafted = str(tmp_path / "crafted.vsdx")
    _two_pages_on_one_part(vsdx_copy("test2.vsdx"), crafted)
    target = str(tmp_path / "saved.vsdx")
    vis = VisioFile(crafted)
    first, second = vis.pages[0], vis.pages[1]
    assert first.filename == second.filename, "the crafted package should give both pages one part"
    replacement = parse_part(serialise_part(second.xml))
    root = replacement.getroot()
    assert root is not None
    root.set("VsdxkitMarker", "1")
    vis.remove_page_by_index(0)
    assert vis._package.part(second.filename) is None
    second.xml = replacement
    vis.save_vsdx(target)
    saved = VisioFile(target)
    assert saved.pages[0].xml.getroot().get("VsdxkitMarker") == "1"
