"""Page removal must keep the OPC graph consistent; part names must be unused values."""

import os
import xml.etree.ElementTree as ET
import zipfile

from vsdxkit import VisioFile

FIXTURES = os.path.dirname(os.path.realpath(__file__))
RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _zip_graph(path: str) -> tuple[set[str], dict[str, str], list[str]]:
    """Return (member names, rel-id -> target for pages.xml.rels, pages.xml r:id values)."""
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        rels_root = ET.fromstring(archive.read("visio/pages/_rels/pages.xml.rels"))
        pages_root = ET.fromstring(archive.read("visio/pages/pages.xml"))
    rel_pairs = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root.iter(f"{RELS_NS}Relationship")}
    rel_ids_in_pages = [
        rel.attrib[f"{R_NS}id"] for rel in pages_root.iter("{http://schemas.microsoft.com/office/visio/2012/main}Rel")
    ]
    return names, rel_pairs, rel_ids_in_pages


def _content_type_part_names(path: str) -> set[str]:
    """Return the PartName of every Override in [Content_Types].xml."""
    with zipfile.ZipFile(path) as archive:
        types_root = ET.fromstring(archive.read("[Content_Types].xml"))
    return {el.attrib["PartName"] for el in types_root.iter() if el.tag.endswith("Override") and "PartName" in el.attrib}


def _save_copy(tmp_path, name: str = "doc.vsdx") -> str:
    document = str(tmp_path / name)
    with VisioFile(os.path.join(FIXTURES, "test1.vsdx")) as vis:
        vis.save_vsdx(document)
    return document


def test_remove_page_clears_relationship_and_content_type(tmp_path):
    document = _save_copy(tmp_path)
    with VisioFile(document) as vis:
        vis.remove_page_by_index(1)  # middle page
        vis.save_vsdx(document)

    names, rel_pairs, _ = _zip_graph(document)
    assert "visio/pages/page2.xml" not in names, "removed page part still present"
    assert "page2.xml" not in set(rel_pairs.values()), "dangling relationship to removed part"
    for rel_id, target in rel_pairs.items():
        assert f"visio/pages/{target}" in names, f"{rel_id} targets missing part {target}"
    page_overrides = {n for n in _content_type_part_names(document) if n.startswith("/visio/pages/")}
    assert page_overrides, "no page content-type overrides; the loop below would assert nothing"
    for part_name in page_overrides:
        assert part_name.lstrip("/") in names, f"content-type override for missing part {part_name}"


def test_remove_then_add_allocates_unused_part_and_resolves_graph(tmp_path):
    document = _save_copy(tmp_path)
    with VisioFile(document) as vis:
        vis.remove_page_by_index(1)
        new_page = vis.add_page("replacement")
        vis.save_vsdx(document)

    names, rel_pairs, rel_ids_in_pages = _zip_graph(document)
    for rel_id in rel_ids_in_pages:
        assert rel_id in rel_pairs, f"pages.xml references {rel_id} which has no relationship"
    for rel_id, target in rel_pairs.items():
        assert f"visio/pages/{target}" in names, f"{rel_id} targets missing part {target}"
    assert len(set(rel_pairs.values())) == len(rel_pairs), f"colliding relationship targets: {rel_pairs}"
    assert new_page.rel_id in rel_pairs
    assert new_page.filename.rsplit("/", 1)[-1] == rel_pairs[new_page.rel_id]
    assert f"visio/pages/{rel_pairs[new_page.rel_id]}" in names


def test_new_page_part_name_is_an_unused_value(tmp_path):
    document = _save_copy(tmp_path)
    with VisioFile(document) as vis:
        vis.remove_page_by_index(1)  # frees page2.xml
        new_page = vis.add_page("replacement")
    # page count went 3 -> 2; page-count derivation would say page3.xml (taken);
    # unused-value allocation must pick page2.xml
    assert new_page.filename.endswith("page2.xml")


def test_removed_page_reopening_round_trip(tmp_path):
    document = _save_copy(tmp_path)
    with VisioFile(document) as vis:
        vis.remove_page_by_index(1)
        vis.add_page("replacement")
        vis.save_vsdx(document)
    with VisioFile(document) as vis:
        assert [p.name for p in vis.pages] == ["Page-1", "Page-3", "replacement"]
        assert all(page.filename for page in vis.pages)
        assert all(page.rel_id for page in vis.pages)
