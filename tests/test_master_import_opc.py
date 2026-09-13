"""Importing a master must leave the saved package's OPC graph consistent.

Creating a connector into a document that already has masters imports the
connector master from the bundled media file. That import writes four separate
pieces of package wiring: a fresh master ID in ``masters.xml``, a content-type
override, a ``masters.xml.rels`` entry and a per-page relationship, plus the
master's name in ``app.xml``. Each comes from a different line, and dropping
any one of them yields a package Visio repairs or rejects while the in-memory
object model still looks right.

So these assertions read the saved archive rather than the ``VisioFile``.
``test3_house.vsdx`` is the fixture because it ships exactly one master, which
is what puts ``Connect.create()`` on the import branch rather than the
copy-the-whole-masters-folder branch.
"""

import os
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

import pytest

from vsdx import Connect, VisioFile

RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
VISIO_NS = "{http://schemas.microsoft.com/office/visio/2012/main}"
CONTENT_TYPES_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
EXT_PROPS_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}"
VT_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}"

MASTER_REL_TYPE = "http://schemas.microsoft.com/visio/2010/relationships/master"
MASTER_CONTENT_TYPE = "application/vnd.ms-visio.master+xml"


@dataclass(frozen=True)
class ImportedMaster:
    """The connector master ``Connect.create()`` imported, and the package holding it."""

    document: str
    master_id: str
    master_name: str


def _zip_names(path: str) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def _read_xml(path: str, member: str) -> ET.Element:
    with zipfile.ZipFile(path) as archive:
        return ET.fromstring(archive.read(member))


def _master_relationships(path: str, member: str) -> dict[str, str]:
    """Return rel-id -> target for the master relationships in a ``.rels`` part."""
    root = _read_xml(path, member)
    return {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in root.iter(f"{RELS_NS}Relationship")
        if rel.attrib.get("Type") == MASTER_REL_TYPE
    }


def _content_type_overrides(path: str) -> dict[str, str]:
    """Return PartName -> ContentType for every override in ``[Content_Types].xml``."""
    root = _read_xml(path, "[Content_Types].xml")
    return {
        override.attrib["PartName"]: override.attrib["ContentType"] for override in root.iter(f"{CONTENT_TYPES_NS}Override")
    }


def _master_elements(path: str) -> list[ET.Element]:
    return list(_read_xml(path, "visio/masters/masters.xml").iter(f"{VISIO_NS}Master"))


def _master_parts(path: str) -> set[str]:
    """Return the ``visio/masters/masterN.xml`` members present in the archive."""
    return {
        name
        for name in _zip_names(path)
        if name.startswith("visio/masters/master") and name.endswith(".xml") and name != "visio/masters/masters.xml"
    }


def _part_by_master_id(path: str) -> dict[str, str]:
    """Map each master's ID to the part filename it resolves to via masters.xml.rels."""
    master_rels = _master_relationships(path, "visio/masters/_rels/masters.xml.rels")
    resolved = {}
    for master in _master_elements(path):
        rel = master.find(f"{VISIO_NS}Rel")
        rel_id = rel.attrib.get(f"{R_NS}id") if rel is not None else None
        if rel_id in master_rels:
            resolved[master.attrib["ID"]] = master_rels[rel_id]
    return resolved


def _titles_of_parts(path: str) -> list[str]:
    root = _read_xml(path, "docProps/app.xml")
    titles = root.find(f"{EXT_PROPS_NS}TitlesOfParts")
    assert titles is not None, "app.xml has no TitlesOfParts element"
    return [entry.text or "" for entry in titles.iter(f"{VT_NS}lpstr")]


def _page_parts(path: str) -> list[str]:
    return sorted(
        name
        for name in _zip_names(path)
        if name.startswith("visio/pages/page") and name.endswith(".xml") and not name.endswith(".xml.rels")
    )


def _page_rels_member(page_part: str) -> str:
    return f"visio/pages/_rels/{page_part.rsplit('/', 1)[-1]}.rels"


def _master_ids_used_on_page(path: str, page_part: str) -> set[str]:
    root = _read_xml(path, page_part)
    return {shape.attrib["Master"] for shape in root.iter(f"{VISIO_NS}Shape") if shape.attrib.get("Master")}


@pytest.fixture
def imported_master(vsdx_copy, tmp_path) -> ImportedMaster:
    """Connect two shapes in a one-master document, then save it.

    ``Connect.create()`` is the only caller of ``_ensure_masters_for_shape``,
    so this is the only route to the import path through the public API.
    """
    source = vsdx_copy("test3_house.vsdx")
    document = os.path.join(str(tmp_path), "imported_master.vsdx")
    with VisioFile(source) as vis:
        page = vis.pages[0]
        connector = Connect.create(
            page=page,
            from_shape=page.find_shape_by_text("Shape to copy"),
            to_shape=page.find_shape_by_text("Shape to remove"),
        )
        master_id = connector.xml.attrib["Master"]
        vis.save_vsdx(document)
    return ImportedMaster(document=document, master_id=master_id, master_name="Dynamic connector")


def test_import_adds_the_connector_master(imported_master: ImportedMaster):
    """Guard the fixture: the rest of this module asserts nothing if no master was imported."""
    names = [master.attrib.get("NameU") for master in _master_elements(imported_master.document)]
    assert imported_master.master_name in names, f"connector master was not imported, masters.xml holds {names}"
    assert len(_master_parts(imported_master.document)) == 2, "expected the shipped master plus the imported one"


def test_master_ids_are_unique(imported_master: ImportedMaster):
    """A reused ID silently redirects the shapes that reference it to the wrong master."""
    ids = [master.attrib["ID"] for master in _master_elements(imported_master.document) if "ID" in master.attrib]
    duplicates = sorted({master_id for master_id in ids if ids.count(master_id) > 1})
    assert not duplicates, f"masters.xml reuses ID(s) {duplicates}: {ids}"
    assert imported_master.master_id in ids, f"connector references master {imported_master.master_id}, absent from {ids}"


def test_every_master_part_has_a_content_type_override(imported_master: ImportedMaster):
    """OPC declares no default content type for master parts, so one without an override has none."""
    overrides = _content_type_overrides(imported_master.document)
    for part in sorted(_master_parts(imported_master.document)):
        assert f"/{part}" in overrides, f"{part} is in the archive with no content-type override"
        assert overrides[f"/{part}"] == MASTER_CONTENT_TYPE


def test_no_content_type_override_names_a_missing_master_part(imported_master: ImportedMaster):
    names = _zip_names(imported_master.document)
    for part_name, content_type in _content_type_overrides(imported_master.document).items():
        if content_type == MASTER_CONTENT_TYPE:
            assert part_name.lstrip("/") in names, f"content-type override for missing part {part_name}"


def test_every_master_part_is_reachable_from_masters_xml(imported_master: ImportedMaster):
    """masters.xml reaches its parts by r:id, so both ends of that hop have to resolve."""
    document = imported_master.document
    targets = _master_relationships(document, "visio/masters/_rels/masters.xml.rels")
    assert {f"visio/masters/{target}" for target in targets.values()} == _master_parts(document), (
        f"masters.xml.rels targets {sorted(targets.values())}, archive holds {sorted(_master_parts(document))}"
    )
    for master in _master_elements(document):
        rel = master.find(f"{VISIO_NS}Rel")
        assert rel is not None, f"master {master.attrib.get('ID')} has no Rel element"
        rel_id = rel.attrib[f"{R_NS}id"]
        assert rel_id in targets, f"master {master.attrib.get('ID')} references {rel_id}, absent from masters.xml.rels"


def test_every_page_relationship_targets_a_part_that_exists(imported_master: ImportedMaster):
    names = _zip_names(imported_master.document)
    for page_part in _page_parts(imported_master.document):
        rels_member = _page_rels_member(page_part)
        if rels_member not in names:
            continue
        for rel_id, target in _master_relationships(imported_master.document, rels_member).items():
            resolved = os.path.normpath(os.path.join(os.path.dirname(page_part), target)).replace(os.sep, "/")
            assert resolved in names, f"{rels_member} {rel_id} targets missing part {target}"


def test_every_master_a_page_uses_is_related_from_that_page(imported_master: ImportedMaster):
    """Visio resolves a shape's Master through the page's own relationships.

    Without the per-page relationship the master part is in the archive and
    listed in masters.xml, but the page that needs it cannot reach it.
    """
    document = imported_master.document
    part_by_master_id = _part_by_master_id(document)
    for page_part in _page_parts(document):
        used = _master_ids_used_on_page(document, page_part)
        if not used:
            continue
        rels_member = _page_rels_member(page_part)
        assert rels_member in _zip_names(document), f"{page_part} uses masters {sorted(used)} but has no rels part"
        page_targets = {target.rsplit("/", 1)[-1] for target in _master_relationships(document, rels_member).values()}
        for master_id in sorted(used):
            assert master_id in part_by_master_id, f"{page_part} uses master {master_id}, unresolvable from masters.xml"
            part = part_by_master_id[master_id]
            assert part in page_targets, f"{page_part} uses master {master_id} ({part}) with no relationship to it"


def test_every_master_name_is_listed_in_titles_of_parts(imported_master: ImportedMaster):
    """app.xml enumerates the masters by name, so a missing one leaves it disagreeing with masters.xml."""
    titles = _titles_of_parts(imported_master.document)
    for master in _master_elements(imported_master.document):
        name = master.attrib.get("NameU") or master.attrib.get("Name")
        assert name in titles, f"master {name!r} is missing from app.xml TitlesOfParts {titles}"
    assert imported_master.master_name in titles


def test_imported_master_survives_a_reopen(imported_master: ImportedMaster):
    """Reopening must find the imported master where the saved graph says it is."""
    with VisioFile(imported_master.document) as vis:
        master_page = vis.get_master_page_by_id(imported_master.master_id)
        assert master_page is not None, f"master {imported_master.master_id} did not survive the round trip"
        assert master_page.name == imported_master.master_name
        assert master_page.filename in vis.zip_file_contents
