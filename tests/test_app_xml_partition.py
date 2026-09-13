"""`docProps/app.xml` is one list of titles cut into sections by a list of counts.

`TitlesOfParts` is a single vector. `HeadingPairs` says how to read it: three
Pages then three Masters means the first three titles name pages and the next
three name masters. Nothing in the vector says which is which, so a title
appended at the end of it is a master whatever the writer meant, and a count
raised in the wrong pair moves the boundary under titles that were already
right.

Within a section the order is `pages.xml` order for pages and `masters.xml`
order for masters; nothing here asserts that, because a page inserted at an
index still has its title added at the end of the Pages section.

These tests read the saved package rather than the in-memory tree: app.xml is
written at save time, and a title that never reaches the archive is the same
bug from the outside.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
import zipfile

import pytest
from helpers.broken_package import rewritten

from vsdxkit import Connect, VisioFile, ext_prop_namespace, namespace, vt_namespace

APP_PART = "docProps/app.xml"

# test4_connectors.vsdx as Visio wrote it: pages first, then masters.
PAGES_FIRST_HEADINGS = (
    '<HeadingPairs><vt:vector size="4" baseType="variant">'
    "<vt:variant><vt:lpstr>Pages</vt:lpstr></vt:variant><vt:variant><vt:i4>3</vt:i4></vt:variant>"
    "<vt:variant><vt:lpstr>Masters</vt:lpstr></vt:variant><vt:variant><vt:i4>3</vt:i4></vt:variant>"
    "</vt:vector></HeadingPairs>"
)
PAGES_FIRST_TITLES = (
    '<TitlesOfParts><vt:vector size="6" baseType="lpstr">'
    "<vt:lpstr>Page-1</vt:lpstr><vt:lpstr>Page-2</vt:lpstr><vt:lpstr>Page-3</vt:lpstr>"
    "<vt:lpstr>Dynamic connector</vt:lpstr><vt:lpstr>Switch</vt:lpstr><vt:lpstr>Router</vt:lpstr>"
    "</vt:vector></TitlesOfParts>"
)

# The same document with the two sections swapped. Every fixture in the repo
# writes Pages first, so a writer that takes whichever count comes first is
# right on all of them; this is a package where the two differ.
MASTERS_FIRST = (
    '<HeadingPairs><vt:vector size="4" baseType="variant">'
    "<vt:variant><vt:lpstr>Masters</vt:lpstr></vt:variant><vt:variant><vt:i4>3</vt:i4></vt:variant>"
    "<vt:variant><vt:lpstr>Pages</vt:lpstr></vt:variant><vt:variant><vt:i4>3</vt:i4></vt:variant>"
    "</vt:vector></HeadingPairs>"
    '<TitlesOfParts><vt:vector size="6" baseType="lpstr">'
    "<vt:lpstr>Dynamic connector</vt:lpstr><vt:lpstr>Switch</vt:lpstr><vt:lpstr>Router</vt:lpstr>"
    "<vt:lpstr>Page-1</vt:lpstr><vt:lpstr>Page-2</vt:lpstr><vt:lpstr>Page-3</vt:lpstr>"
    "</vt:vector></TitlesOfParts>"
)


def _app_xml(path: str) -> ET.Element:
    with zipfile.ZipFile(path) as archive:
        return ET.fromstring(archive.read(APP_PART))


def _counts(root: ET.Element) -> dict[str, int]:
    """Each HeadingPairs name mapped to its count."""
    heading_pairs = root.find(f"{ext_prop_namespace}HeadingPairs")
    assert heading_pairs is not None, "app.xml has no HeadingPairs element"
    variants = heading_pairs.findall(f".//{vt_namespace}variant")
    counts = {}
    for name_variant, count_variant in zip(variants[::2], variants[1::2], strict=True):
        name = name_variant.find(f"{vt_namespace}lpstr")
        count = count_variant.find(f"{vt_namespace}i4")
        assert name is not None and count is not None, "HeadingPairs is not name/count pairs"
        counts[name.text or ""] = int(count.text or 0)
    return counts


def _heading_pairs_values(root: ET.Element) -> list[str]:
    """HeadingPairs flattened to the text of each variant, in order.

    `_counts` pairs the variants up, which a document holding something else
    among them cannot be read that way at all. This says what is written, and
    leaves the reading to the test.
    """
    heading_pairs = root.find(f"{ext_prop_namespace}HeadingPairs")
    assert heading_pairs is not None, "app.xml has no HeadingPairs element"
    return [(next(iter(variant)).text or "") for variant in heading_pairs.findall(f".//{vt_namespace}variant")]


def _titles(root: ET.Element) -> list[str]:
    titles = root.find(f"{ext_prop_namespace}TitlesOfParts")
    assert titles is not None, "app.xml has no TitlesOfParts element"
    vector = titles.find(f"{vt_namespace}vector")
    assert vector is not None, "TitlesOfParts has no vector"
    entries = [entry.text or "" for entry in vector.findall(f"{vt_namespace}lpstr")]
    assert int(vector.attrib["size"]) == len(entries), "the vector's size attribute does not count its entries"
    return entries


def _sections(root: ET.Element) -> dict[str, list[str]]:
    """The titles belonging to each heading, cut out of the one vector by the counts.

    Raises if the counts do not add up to the vector: a title in neither
    section belongs to no part, and a test that quietly dropped it would pass
    on a file Visio reads differently from the writer that produced it.
    """
    counts, titles = _counts(root), _titles(root)
    assert sum(counts.values()) == len(titles), f"HeadingPairs {counts} does not partition {titles}"
    sections, start = {}, 0
    for name, count in counts.items():
        sections[name] = titles[start : start + count]
        start += count
    return sections


def _page_names(path: str) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        pages = ET.fromstring(archive.read("visio/pages/pages.xml"))
    return [page.attrib.get("NameU", "") for page in pages.findall(f"{namespace}Page")]


def _saved(vis: VisioFile, tmp_path, name: str = "out.vsdx") -> str:
    destination = os.path.join(str(tmp_path), name)
    vis.save_vsdx(destination)
    return destination


@pytest.fixture
def masters_first(basedir, tmp_path) -> str:
    """test4_connectors.vsdx with the Masters section written before the Pages section."""
    return rewritten(
        os.path.join(basedir, "test4_connectors.vsdx"),
        os.path.join(str(tmp_path), "test4_connectors-masters-first.vsdx"),
        {APP_PART: (PAGES_FIRST_HEADINGS + PAGES_FIRST_TITLES, MASTERS_FIRST)},
    )


def test_the_added_page_is_named_in_the_pages_section(basedir, tmp_path):
    with VisioFile(os.path.join(basedir, "test4_connectors.vsdx")) as vis:
        vis.add_page("NewPage")
        saved = _saved(vis, tmp_path)

    sections = _sections(_app_xml(saved))
    assert sections["Pages"] == ["Page-1", "Page-2", "Page-3", "NewPage"]
    assert sections["Masters"] == ["Dynamic connector", "Switch", "Router"]


def test_adding_a_page_counts_the_pages_not_whichever_section_comes_first(masters_first, tmp_path):
    with VisioFile(masters_first) as vis:
        vis.add_page("NewPage")
        saved = _saved(vis, tmp_path, "masters-first-add.vsdx")

    sections = _sections(_app_xml(saved))
    assert sections["Pages"] == ["Page-1", "Page-2", "Page-3", "NewPage"]
    assert sections["Masters"] == ["Dynamic connector", "Switch", "Router"]


def test_removing_a_page_counts_the_pages_not_whichever_section_comes_first(masters_first, tmp_path):
    with VisioFile(masters_first) as vis:
        vis.remove_page_by_name("Page-2")
        saved = _saved(vis, tmp_path, "masters-first-remove.vsdx")

    sections = _sections(_app_xml(saved))
    assert sections["Pages"] == ["Page-1", "Page-3"]
    assert sections["Masters"] == ["Dynamic connector", "Switch", "Router"]


def test_renaming_a_page_renames_its_title(basedir, tmp_path):
    with VisioFile(os.path.join(basedir, "test4_connectors.vsdx")) as vis:
        vis.pages[1].name = "Renamed"
        saved = _saved(vis, tmp_path, "renamed.vsdx")

    sections = _sections(_app_xml(saved))
    assert sections["Pages"] == ["Page-1", "Renamed", "Page-3"]
    assert sections["Masters"] == ["Dynamic connector", "Switch", "Router"]


def test_renaming_a_page_leaves_a_master_of_the_same_name_alone(masters_first, tmp_path):
    """The title to rewrite is the one in the Pages section, not the first one that matches.

    A master and a page can be called the same thing, and here the master's
    title is written first.
    """
    with VisioFile(masters_first) as vis:
        vis.pages[0].name = "Switch"
        vis.pages[0].name = "Renamed"
        saved = _saved(vis, tmp_path, "masters-first-rename.vsdx")

    sections = _sections(_app_xml(saved))
    assert sections["Masters"] == ["Dynamic connector", "Switch", "Router"]
    assert sections["Pages"] == ["Renamed", "Page-2", "Page-3"]


def test_removing_a_page_leaves_a_master_of_the_same_name_alone(masters_first, tmp_path):
    with VisioFile(masters_first) as vis:
        vis.pages[0].name = "Switch"
        vis.remove_page_by_name("Switch")
        saved = _saved(vis, tmp_path, "masters-first-remove-namesake.vsdx")

    sections = _sections(_app_xml(saved))
    assert sections["Masters"] == ["Dynamic connector", "Switch", "Router"]
    assert sections["Pages"] == ["Page-2", "Page-3"]


def test_the_imported_master_is_named_and_counted_in_the_masters_section(vsdx_copy, tmp_path):
    """A document that already has masters gains one when a connector is created."""
    with VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        page = vis.pages[0]
        Connect.create(
            page=page,
            from_shape=page.find_shape_by_text("Shape to copy"),
            to_shape=page.find_shape_by_text("Shape to remove"),
        )
        saved = _saved(vis, tmp_path, "house-connected.vsdx")

    sections = _sections(_app_xml(saved))
    assert sections["Pages"] == ["Page-1"]
    assert sections["Masters"] == ["House", "Dynamic connector"]


def test_a_document_with_no_masters_heading_gains_one_with_its_first_master(vsdx_copy, tmp_path):
    with VisioFile(vsdx_copy("test8_simple_connector.vsdx")) as vis:
        page = vis.pages[0]
        Connect.create(page=page, from_shape=page.child_shapes[0], to_shape=page.child_shapes[1])
        saved = _saved(vis, tmp_path, "simple-connected.vsdx")

    sections = _sections(_app_xml(saved))
    assert sections["Pages"] == ["Page-1"]
    assert sections["Masters"] == ["Dynamic connector"]


def test_a_master_is_listed_even_when_a_page_is_called_the_same_thing(vsdx_copy, tmp_path):
    """The Masters section is what says whether this master is already listed.

    Asking whether the name appears anywhere in app.xml answers a different
    question, and a page that happens to share the master's name answers it
    wrongly - leaving a document with a master no section of app.xml names.
    """
    with VisioFile(vsdx_copy("test8_simple_connector.vsdx")) as vis:
        page = vis.pages[0]
        page.name = "Dynamic connector"
        Connect.create(page=page, from_shape=page.child_shapes[0], to_shape=page.child_shapes[1])
        saved = _saved(vis, tmp_path, "namesake-page.vsdx")

    sections = _sections(_app_xml(saved))
    assert sections["Pages"] == ["Dynamic connector"]
    assert sections["Masters"] == ["Dynamic connector"]


def test_a_count_larger_than_the_vector_is_not_read_as_positions(basedir, tmp_path):
    """A section owns the titles that are there, however many its count claims.

    app.xml arrives from whatever wrote the file, so a count that does not
    match its titles is input rather than an internal error. Here the page
    being removed is not the one app.xml names, so every position the count
    claims gets looked at.
    """
    source = rewritten(
        os.path.join(basedir, "test1.vsdx"),
        os.path.join(str(tmp_path), "test1-overcounted.vsdx"),
        {
            APP_PART: (
                "<vt:i4>3</vt:i4></vt:variant></vt:vector></HeadingPairs>"
                '<TitlesOfParts><vt:vector size="3" baseType="lpstr">'
                "<vt:lpstr>Page-1</vt:lpstr><vt:lpstr>Page-2</vt:lpstr>",
                "<vt:i4>5</vt:i4></vt:variant></vt:vector></HeadingPairs>"
                '<TitlesOfParts><vt:vector size="3" baseType="lpstr">'
                "<vt:lpstr>Page-1</vt:lpstr><vt:lpstr>Unlisted</vt:lpstr>",
            )
        },
    )

    with VisioFile(source) as vis:
        vis.remove_page_by_name("Page-2")
        saved = _saved(vis, tmp_path, "overcounted-removed.vsdx")

    # nothing in the Pages section was named Page-2, so app.xml is left as it
    # was rather than edited by position
    assert _titles(_app_xml(saved)) == ["Page-1", "Unlisted", "Page-3"]
    assert _counts(_app_xml(saved)) == {"Pages": 5}


def test_a_count_read_for_a_later_section_is_not_written_back_to_it(basedir, tmp_path):
    """A count is only ever raised or lowered by one; it is never re-derived.

    A section whose count over-reports pushes every later section past the end
    of the vector. The page count is still the page count, and a writer that
    recomputed it from where the titles ended up would throw it away.
    """
    source = rewritten(
        os.path.join(basedir, "test4_connectors.vsdx"),
        os.path.join(str(tmp_path), "test4_connectors-overcounted.vsdx"),
        {APP_PART: (PAGES_FIRST_HEADINGS, MASTERS_FIRST[: MASTERS_FIRST.index("<TitlesOfParts>")].replace(">3<", ">99<", 1))},
    )

    with VisioFile(source) as vis:
        vis.add_page("NewPage")
        saved = _saved(vis, tmp_path, "overcounted-add.vsdx")

    assert _counts(_app_xml(saved)) == {"Masters": 99, "Pages": 4}


def test_renaming_a_page_in_a_document_that_lists_no_parts_leaves_app_xml_alone(basedir, tmp_path):
    """app.xml need not list the parts at all, and renaming a page is no reason to make it.

    Adding or removing a page writes parts into the package and needs app.xml
    to keep up. A rename does not, so a document whose metadata never named its
    pages is left as it is rather than made to raise.
    """
    source = rewritten(
        os.path.join(basedir, "test4_connectors.vsdx"),
        os.path.join(str(tmp_path), "test4_connectors-no-titles.vsdx"),
        {APP_PART: (PAGES_FIRST_TITLES, "")},
    )

    with VisioFile(source) as vis:
        vis.pages[1].name = "Renamed"
        saved = _saved(vis, tmp_path, "no-titles-renamed.vsdx")

    assert _page_names(saved) == ["Page-1", "Renamed", "Page-3"]
    assert _app_xml(saved).find(f"{ext_prop_namespace}TitlesOfParts") is None


def test_a_variant_that_is_neither_a_name_nor_a_count_moves_no_section(basedir, tmp_path):
    """One reading of HeadingPairs, for placing a title and for writing a count.

    A variant holding something else sits between the names and the counts, so
    a reader that pairs them off by position reads every name as the one
    before it. A reader that takes the count from the variant after the name
    is unmoved. Where those two readings were one each side of the same
    operation, the count was read from a section that was not there and
    written to one that was.
    """
    source = rewritten(
        os.path.join(basedir, "test4_connectors.vsdx"),
        os.path.join(str(tmp_path), "test4_connectors-odd-variant.vsdx"),
        {
            APP_PART: (
                '<HeadingPairs><vt:vector size="4" baseType="variant">',
                '<HeadingPairs><vt:vector size="5" baseType="variant"><vt:variant><vt:bool>true</vt:bool></vt:variant>',
            )
        },
    )

    with VisioFile(source) as vis:
        vis.add_page("NewPage")
        saved = _saved(vis, tmp_path, "odd-variant-add.vsdx")

    app_xml = _app_xml(saved)
    assert _heading_pairs_values(app_xml) == ["true", "Pages", "4", "Masters", "3"]
    assert _titles(app_xml) == [
        "Page-1",
        "Page-2",
        "Page-3",
        "NewPage",
        "Dynamic connector",
        "Switch",
        "Router",
    ]
