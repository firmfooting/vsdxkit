"""Section lookup in app.xml, for a package whose producer did not write English.

`HeadingPairs` names are display strings chosen by whatever wrote the file, and
Office localises them -- a German Excel writes `Arbeitsblätter` where an English
one writes `Worksheets`. A German Visio writes `Seiten` and `Master`.

Matching those names against the literals "Pages" and "Masters" therefore finds
nothing on such a file, and the caller is told the section does not exist. What
follows from that is worse than not finding it: adding a page appends a *second*
section called "Pages", so the document ends up claiming two page sections and
the titles are partitioned by counts that no longer describe them.
"""

import os
import zipfile
from xml.etree import ElementTree as ET

import pytest

import vsdxkit

EXT = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
VT = "{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}"


def _localise(source: str, destination: str, renames: dict[str, str]) -> None:
    """Rewrite the HeadingPairs section names, leaving everything else alone."""
    with zipfile.ZipFile(source) as archive:
        order = archive.namelist()
        members = {name: archive.read(name) for name in order}
    root = ET.fromstring(members["docProps/app.xml"])
    replaced = 0
    for entry in root.find(f"{EXT}HeadingPairs").iter(f"{VT}lpstr"):
        if entry.text in renames:
            entry.text = renames[entry.text]
            replaced += 1
    assert replaced == len(renames), f"expected to rename {len(renames)}, renamed {replaced}"
    members["docProps/app.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(destination, "w") as archive:
        for name in order:
            archive.writestr(name, members[name])


def _app_xml(path: str) -> tuple[list[str], list[str]]:
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("docProps/app.xml"))
    headings = [e.text or "" for e in root.find(f"{EXT}HeadingPairs").iter() if (e.text or "").strip()]
    titles = [e.text or "" for e in root.find(f"{EXT}TitlesOfParts").iter(f"{VT}lpstr")]
    return headings, titles


@pytest.fixture
def german(tmp_path, basedir) -> str:
    localised = str(tmp_path / "german.vsdx")
    _localise(os.path.join(basedir, "test4_connectors.vsdx"), localised, {"Pages": "Seiten", "Masters": "Master"})
    return localised


def test_adding_a_page_counts_it_in_the_section_that_is_already_there(german, tmp_path):
    """No second section, whatever the first one is called.

    Fails if section lookup goes back to matching the English literal and
    nothing else: `_set_app_xml_value` then creates the pair it could not find.
    """
    out = str(tmp_path / "out.vsdx")
    with vsdxkit.VisioFile(german) as vis:
        vis.add_page("NewPage")
        vis.save_vsdx(out)
    headings, titles = _app_xml(out)
    assert headings == ["Seiten", "4", "Master", "3"]
    assert titles[:4] == ["Page-1", "Page-2", "Page-3", "NewPage"]


def test_removing_a_page_counts_it_in_the_section_that_is_already_there(german, tmp_path):
    out = str(tmp_path / "out.vsdx")
    with vsdxkit.VisioFile(german) as vis:
        vis.remove_page_by_index(1)
        vis.save_vsdx(out)
    headings, titles = _app_xml(out)
    assert headings == ["Seiten", "2", "Master", "3"]
    assert titles == ["Page-1", "Page-3", "Dynamic connector", "Switch", "Router"]


def test_renaming_a_page_renames_its_title(german, tmp_path):
    out = str(tmp_path / "out.vsdx")
    with vsdxkit.VisioFile(german) as vis:
        vis.pages[1].name = "Umbenannt"
        vis.save_vsdx(out)
    headings, titles = _app_xml(out)
    assert headings == ["Seiten", "3", "Master", "3"]
    assert titles[:3] == ["Page-1", "Umbenannt", "Page-3"]


def _without_the_pages_section(source: str, destination: str, masters_label: str) -> None:
    """A document that names only a masters section, and only master titles.

    Both halves matter. Dropping the HeadingPairs pair but leaving the page
    titles in the vector describes no real document: the masters count would
    then cover the page titles, and any reader is entitled to conclude those
    three titles are the masters.
    """
    with zipfile.ZipFile(source) as archive:
        order = archive.namelist()
        members = {name: archive.read(name) for name in order}
    root = ET.fromstring(members["docProps/app.xml"])
    vector = root.find(f"{EXT}HeadingPairs").find(f"{VT}vector")
    variants = list(vector)
    assert len(variants) == 4, "expected Pages and Masters pairs to strip one from"
    for variant in variants[:2]:
        vector.remove(variant)
    vector.set("size", str(len(vector)))
    label = vector.find(f".//{VT}lpstr")
    assert label.text == "Masters", f"expected the surviving pair to be Masters, got {label.text!r}"
    label.text = masters_label

    titles = root.find(f"{EXT}TitlesOfParts").find(f"{VT}vector")
    entries = list(titles)
    assert len(entries) == 6, f"expected 3 pages and 3 masters, got {len(entries)}"
    for entry in entries[:3]:  # the page titles go with the section that named them
        titles.remove(entry)
    titles.set("size", str(len(titles)))

    members["docProps/app.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(destination, "w") as archive:
        for name in order:
            archive.writestr(name, members[name])


@pytest.mark.parametrize("masters_label", ["Masters", "Master"], ids=["english", "localised"])
def test_a_missing_section_is_created_rather_than_taking_one_that_is_named(masters_label, tmp_path, basedir):
    """The fallback must not claim a section that is demonstrably the other one.

    A document naming only masters has them at position 0, so "the first
    section" puts the new page's title among the masters and increments their
    count -- leaving no pages section behind either, which is worse than
    reporting it missing, since that at least gets one created.

    The `localised` case is the one that matters and the one an English-label
    guard cannot answer: a guard listing "Masters" as spoken for says nothing
    about `Master`, `Schablonen` or anything else the producer chose. What the
    producer cannot translate is the titles, so that is what is asked.

    Fails if the fallback goes back to taking a position on faith.
    """
    stripped = str(tmp_path / "masters_only.vsdx")
    _without_the_pages_section(os.path.join(basedir, "test4_connectors.vsdx"), stripped, masters_label)

    out = str(tmp_path / "out.vsdx")
    with vsdxkit.VisioFile(stripped) as vis:
        vis.add_page("NewPage")
        vis.save_vsdx(out)
    headings, titles = _app_xml(out)
    assert headings == [masters_label, "3", "Pages", "1"]
    assert titles == ["Dynamic connector", "Switch", "Router", "NewPage"]


def test_renaming_the_only_page_of_a_localised_document_still_renames_its_title(tmp_path, basedir):
    """One page, and the name is the thing being changed.

    `Page.name` updates the page before it updates app.xml, so at the moment the
    section has to be found, the document says the page is called the new name
    and app.xml still says the old one. With one page there is nothing else to
    recognise the section by, and asking which section names the document's
    pages gets the answer "none of them".

    The caller knows the name it is replacing, so it says so. Fails if the
    resolver goes back to asking only what the pages are called now.
    """
    localised = str(tmp_path / "german_house.vsdx")
    _localise(os.path.join(basedir, "test3_house.vsdx"), localised, {"Pages": "Seiten", "Masters": "Master"})
    out = str(tmp_path / "out.vsdx")
    with vsdxkit.VisioFile(localised) as vis:
        vis.pages[0].name = "Umbenannt"
        vis.save_vsdx(out)
    headings, titles = _app_xml(out)
    assert headings == ["Seiten", "1", "Master", "1"]
    assert titles == ["Umbenannt", "House"]


def test_a_master_sharing_the_only_page_s_name_does_not_make_the_masters_the_pages(tmp_path, basedir):
    """Two sections, the same overlap, and no way to tell them apart.

    A master may be called what a page is called -- the library allows it -- so
    on a one-page document a masters section listed first scores exactly what
    the pages section scores. Taking the first is how the page title ends up
    among the masters.

    What this pins is the damage, not the choice: an ambiguous answer must not
    be resolved by picking one. Fails if the tie goes back to first-wins.
    """
    source = os.path.join(basedir, "test3_house.vsdx")
    colliding = str(tmp_path / "collision.vsdx")
    with zipfile.ZipFile(source) as archive:
        order = archive.namelist()
        members = {name: archive.read(name) for name in order}
    root = ET.fromstring(members["docProps/app.xml"])

    headings = root.find(f"{EXT}HeadingPairs").find(f"{VT}vector")
    pairs = list(headings)
    assert len(pairs) == 4, f"expected two pairs, got {len(pairs) // 2}"
    for variant in pairs:  # masters first, so a tie resolved by position picks them
        headings.remove(variant)
    for variant in pairs[2:] + pairs[:2]:
        headings.append(variant)
    for entry in headings.iter(f"{VT}lpstr"):
        if entry.text == "Pages":
            entry.text = "Seiten"
        elif entry.text == "Masters":
            entry.text = "Master"

    titles = root.find(f"{EXT}TitlesOfParts").find(f"{VT}vector")
    entries = list(titles)
    assert [e.text for e in entries] == ["Page-1", "House"], [e.text for e in entries]
    entries[1].text = "Page-1"  # the master is now called what the page is called
    titles.remove(entries[0])
    titles.append(entries[0])  # masters first here too, matching the headings

    members["docProps/app.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(colliding, "w") as archive:
        for name in order:
            archive.writestr(name, members[name])

    out = str(tmp_path / "out.vsdx")
    with vsdxkit.VisioFile(colliding) as vis:
        vis.add_page("NewPage")
        vis.save_vsdx(out)
    headings_out, titles_out = _app_xml(out)
    master_count = int(headings_out[headings_out.index("Master") + 1])
    assert master_count == 1, f"the new page was counted among the masters: {headings_out}"
    assert titles_out[:master_count] == ["Page-1"], f"the new page's title landed in the masters slice: {titles_out}"
