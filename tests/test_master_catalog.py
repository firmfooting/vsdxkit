"""`MasterCatalog` is the one owner of a document's masters (Phase 2, #93/#94).

Each test names the defect it pins. The saved packages go through the autouse
structural validator, so every save here is also checked for undeclared
masters, dangling relationships and missing content types.
"""

import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

import pytest

from vsdxkit._masters import MasterCatalog
from vsdxkit._partnames import relationship_target, relationships_part_name
from vsdxkit.document import Document
from vsdxkit.errors import MissingPartError

RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MASTER_RELATIONSHIP = "http://schemas.microsoft.com/visio/2010/relationships/master"
MAIN_NS = "http://schemas.microsoft.com/office/visio/2012/main"


def _master_parts(path: str) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return sorted(
            name
            for name in archive.namelist()
            if name.startswith("visio/masters/master") and name != "visio/masters/masters.xml"
        )


def _masters(path: str) -> list[ET.Element]:
    with zipfile.ZipFile(path) as archive:
        return list(ET.fromstring(archive.read("visio/masters/masters.xml")))


def _master_instance(vis: Document):
    return next(shape for shape in vis.pages[0].shapes if shape.xml.attrib.get("Master"))


def _page_rels_root(page) -> ET.Element:
    """The page's rels root, created empty where the page has none yet."""
    if page._rels_xml is None:
        page._rels_xml_filename = relationships_part_name(page._filename)
        page._rels_xml = ET.ElementTree(ET.Element(f"{RELS_NS}Relationships"))
    return page._rels_xml.getroot()


def test_loading_the_masters_twice_lists_each_master_once(vsdx_copy):
    """Fails if `load_master_pages` appends to what it already holds (#375)."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    names = [page.name for page in vis.master_pages]
    vis.load_master_pages()
    assert [page.name for page in vis.master_pages] == names
    assert list(vis.master_index) == names


def test_copying_a_master_instance_into_another_document_declares_its_master(vsdx_copy, tmp_path):
    """Fails if `Shape.copy` across documents leaves the copy naming a master the target lacks (#331).

    Visio drops such a shape on open without an error. The autouse validator
    reports it as `undeclared-master`.
    """
    saved = str(tmp_path / "copied.vsdx")
    source = Document.open(vsdx_copy("test5_master.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    shape = _master_instance(source)
    master_name = shape.master_page.name
    copy_id = shape.copy(target.pages[0]).ID
    target.save(saved)

    reopened = Document.open(saved)
    copied = reopened.pages[0].shapes.by_id(copy_id)
    assert copied is not None
    assert copied.master_page is not None
    assert copied.master_page.name == master_name


def test_a_sub_shape_copied_onto_another_documents_page_names_its_master(vsdx_copy, tmp_path):
    """Fails if a sub-shape of a master instance, copied out of its group, keeps a `MasterShape` that reaches nothing.

    The sub-shape names no master itself: it inherits its group's. Out of the
    group, the copy has to name the master, which has to be imported.
    """
    saved = str(tmp_path / "sub_shape.vsdx")
    source = Document.open(vsdx_copy("test_master_multiple_child_shapes.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    sub_shape = next(
        shape for shape in source.pages[0].shapes if shape.xml.attrib.get("MasterShape") and not shape.xml.attrib.get("Master")
    )
    copy_id = sub_shape.copy(target.pages[0]).ID
    target.save(saved)

    reopened = Document.open(saved)
    copied = reopened.pages[0].shapes.by_id(copy_id)
    assert copied is not None
    assert copied.master_shape is not None


def test_the_bootstrapped_masters_part_carries_the_imported_master(vsdx_copy, tmp_path):
    """Fails if the masters part a masterless document gains is lost, doubled, or unreadable on reopen (#367)."""
    saved = str(tmp_path / "bootstrapped.vsdx")
    source = Document.open(vsdx_copy("test5_master.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    _master_instance(source).copy(target.pages[0])
    target.save(saved)

    assert len(_masters(saved)) == 1
    assert len(_master_parts(saved)) == 1
    reopened = Document.open(saved)
    assert len(reopened.master_pages) == 1


def test_copying_the_same_master_twice_imports_it_once(vsdx_copy, tmp_path):
    """Fails if a second copy of an instance of one master adds a second master part."""
    saved = str(tmp_path / "twice.vsdx")
    source = Document.open(vsdx_copy("test5_master.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    shape = _master_instance(source)
    first = shape.copy(target.pages[0])
    second = shape.copy(target.pages[0])
    assert first.master_page_ID == second.master_page_ID
    target.save(saved)

    assert len(_masters(saved)) == 1
    assert len(_master_parts(saved)) == 1


def test_a_connector_in_a_masterless_document_brings_one_master(vsdx_copy, tmp_path):
    """Guards the count: a masterless document gains exactly the connector's master.

    The bundled donor holds one master, so this cannot tell #375's wholesale
    copy of the donor's masters from an import of one. The hardcoded `rId1`
    half of #375 is pinned by the page relationship test below.
    """
    saved = str(tmp_path / "connected.vsdx")
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shapes = list(page.children)
    connector = page.connect(shapes[0], shapes[1])
    master_name = connector.master_page.name
    vis.save(saved)

    assert [m.attrib.get("NameU") for m in _masters(saved)] == [master_name]
    assert len(_master_parts(saved)) == 1


@pytest.mark.parametrize("fixture", ["test1.vsdx", "test3_house.vsdx"])
def test_a_page_master_relationship_takes_an_id_the_page_rels_does_not_hold(vsdx_copy, fixture):
    """Fails if a connector's page relationship reuses an id the page's rels part already holds (#357, #375).

    A masterless document took the hardcoded `rId1`. A document with masters
    took the id from `masters.xml.rels`, a separate id space. Both were guarded
    on Target only, so a page rels part already holding the id got a duplicate.
    """
    vis = Document.open(vsdx_copy(fixture))
    page = vis.pages[0]
    rels_root = _page_rels_root(page)
    held = {r.attrib["Id"] for r in rels_root}
    for number in range(1, 10):
        if f"rId{number}" not in held:
            ET.SubElement(rels_root, f"{RELS_NS}Relationship", Id=f"rId{number}", Type="urn:unrelated", Target="unrelated.xml")
    prefilled = {r.attrib["Id"] for r in rels_root}
    shapes = list(page.children)
    connector = page.connect(shapes[0], shapes[1])

    target = relationship_target(page._filename, connector.master_page._filename)
    master_relationships = [r for r in rels_root if r.attrib["Type"] == MASTER_RELATIONSHIP and r.attrib["Target"] == target]
    assert len(master_relationships) == 1
    assert master_relationships[0].attrib["Id"] not in prefilled
    ids = [r.attrib["Id"] for r in rels_root]
    assert len(ids) == len(set(ids))


def test_a_nameless_master_imports_under_a_name_of_its_own(vsdx_copy, tmp_path):
    """Fails if a master with neither NameU nor Name poisons the catalog it is imported into.

    A master page cannot be nameless: `Page.name` falls back to pages.xml, which
    a master page is not in, and every later lookup by name raised. The import
    is named `Master.N`, as Visio names a master it creates.
    """
    saved = str(tmp_path / "nameless.vsdx")
    source = Document.open(vsdx_copy("test4_connectors.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    for master in source._masters_xml:
        master.attrib.pop("NameU", None)
        master.attrib.pop("Name", None)
    source.load_master_pages()
    shape = _master_instance(source)
    shape.copy(target.pages[0])
    shape.copy(target.pages[0])
    assert len(target.master_pages) == 1
    (master,) = target.master_pages
    assert master.name == f"Master.{master._page_id}"
    assert target.master_index[master.name] is master
    target.save(saved)


def test_two_nameless_masters_import_under_two_names(vsdx_copy):
    """Fails if two nameless imports share a fallback name, hiding one from lookups and from TitlesOfParts."""
    source = Document.open(vsdx_copy("test_master.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    for master in source._masters.root:
        master.attrib.pop("NameU", None)
        master.attrib.pop("Name", None)
    source.load_master_pages()
    target._masters.import_masters(source._masters, [page._page_id for page in source.master_pages])
    names = [page.name for page in target.master_pages]
    assert len(names) == 2
    assert len(set(names)) == 2, names


def test_a_renamed_import_is_recognised_by_the_next_copy(vsdx_copy):
    """Fails if a master imported under a new name is imported again by every later copy of its instances."""
    source = Document.open(vsdx_copy("test5_master.vsdx"))
    target = Document.open(vsdx_copy("test_master.vsdx"))
    instance = _master_instance(source)
    own = _master_element(target, "Test Master")
    own.attrib["NameU"] = own.attrib["Name"] = instance.master_page.name
    target.load_master_pages()
    first = instance.copy(target.pages[0])
    second = instance.copy(target.pages[0])
    assert first.master_page is second.master_page
    assert first.master_page.name != instance.master_page.name


def test_a_nested_group_with_an_unresolvable_master_does_not_inherit_the_outer_one(vsdx_copy):
    """Fails if members of a nested group whose own master was dropped reach into the enclosing group's master."""
    source = Document.open(vsdx_copy("test_master_multiple_child_shapes.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    group = _master_instance(source)
    nested = next(child for child in group.children if child.shape_type == "Group")
    nested.xml.attrib["Master"] = "999"
    copied = group.copy(target.pages[0])
    copied_nested = next(child for child in copied.children if child.shape_type == "Group")
    assert "Master" not in copied_nested.xml.attrib
    assert [node.attrib.get("MasterShape") for node in copied_nested.xml.iter(f"{{{MAIN_NS}}}Shape")] == [None] * 4
    assert all(child.xml.attrib.get("MasterShape") for child in copied.children if child.shape_type != "Group")


def test_a_document_without_app_xml_still_takes_a_master(vsdx_copy, tmp_path):
    """Fails if importing a master into a package with no docProps/app.xml raises (#385).

    app.xml is optional, and a package without one has no TitlesOfParts to keep
    in step with its masters.
    """
    # named after its fixture, which declares docProps parts it does not hold:
    # the package validator excuses defects an output inherits from its input
    saved = str(tmp_path / "test5_master_connected.vsdx")
    source = Document.open(vsdx_copy("test4_connectors.vsdx"))
    target = Document.open(vsdx_copy("test5_master.vsdx"))
    assert target._app_xml is None, "fixture is expected to have no app.xml"
    page = target.pages[0]
    _master_instance(source).copy(page)
    shapes = list(page.children)
    page.connect(shapes[0], shapes[1])
    target.save(saved)


def test_a_master_that_cannot_be_read_leaves_the_target_as_it_was(vsdx_copy, monkeypatch):
    """Fails if importing several masters writes the first before finding the second unreadable."""
    source = Document.open(vsdx_copy("test4_connectors.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    first, second = source.master_pages[:2]
    read_bytes = source._package.read_bytes
    monkeypatch.setattr(source._package, "read_bytes", lambda name: None if name == second._filename else read_bytes(name))
    before = target._package.names()
    with pytest.raises(MissingPartError, match="could not be read"):
        target._masters.import_masters(source._masters, [first._page_id, second._page_id])
    assert target._package.names() == before
    assert target.master_pages == []


def test_a_copy_onto_another_page_of_the_same_document_relates_that_page_to_the_master(vsdx_copy):
    """Fails if a page gains a master instance without the page relationship Visio writes for it."""
    vis = Document.open(vsdx_copy("test3_house.vsdx"))
    shape = _master_instance(vis)
    new_page = vis.pages.create()
    shape.copy(new_page)
    target = relationship_target(new_page._filename, shape.master_page._filename)
    assert new_page._rels_xml is not None
    assert any(r.attrib["Type"] == MASTER_RELATIONSHIP and r.attrib["Target"] == target for r in new_page._rels_xml.getroot())


def test_a_copy_within_one_document_keeps_a_master_reference_it_cannot_resolve(vsdx_copy):
    """Fails if a copy within one document strips a dangling `Master`: repairing the source is not a copy's job.

    Only a copy into another document drops such a reference, where keeping it
    would name a master that package does not declare.
    """
    vis = Document.open(vsdx_copy("test3_house.vsdx"))
    shape = _master_instance(vis)
    shape.xml.attrib["Master"] = "999"
    copy = shape.copy(vis.pages[0])
    assert copy.xml.attrib["Master"] == "999"


def test_a_sub_shape_copied_within_one_document_keeps_its_group_s_dangling_master(vsdx_copy):
    """Fails if a sub-shape copied out of its group, in one document, loses the master its `MasterShape` reaches into."""
    vis = Document.open(vsdx_copy("test_master_multiple_child_shapes.vsdx"))
    group = _master_instance(vis)
    group.xml.attrib["Master"] = "999"
    sub_shape = next(child for child in group.children if child.master_shape_ID)
    copy = sub_shape.copy(vis.pages[0])
    assert copy.xml.attrib.get("Master") == "999"
    assert copy.xml.attrib.get("MasterShape") == sub_shape.master_shape_ID


def test_the_masters_module_does_not_load_the_document_class():
    """Guards the seam: `vsdxkit._masters` must not import `vsdxkit.document`, directly or through what it imports.

    The catalog is a lower layer: the document hands it a factory for master
    pages rather than the catalog reaching up for the class.
    """
    script = "import sys, vsdxkit._masters; print('vsdxkit.document' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "False"


def test_the_catalog_answers_by_id_and_by_name(vsdx_copy):
    """Fails if the catalog's lookups disagree with the pages it lists."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    catalog = vis._masters
    assert isinstance(catalog, MasterCatalog)
    for page in catalog.pages:
        assert catalog.by_id(page._page_id) is page
        assert catalog.by_name(page.name) is page
    assert catalog.by_id("no-such-id") is None


def _master_element(vis: Document, name: str) -> ET.Element:
    return next(master for master in vis._masters.root if master.attrib.get("NameU") == name)


def test_a_same_name_master_is_imported_when_neither_unique_id_nor_match_by_name_says_it_is_the_same(vsdx_copy, tmp_path):
    """Fails if masters match on name alone: Visio matches on UniqueID unless the document master sets MatchByName.

    Two masters of one name can be different shapes, and an instance of the
    one being copied must not be re-pointed at the other.
    """
    saved = str(tmp_path / "test_master_renamed.vsdx")
    source = Document.open(vsdx_copy("test_master.vsdx"))
    target = Document.open(vsdx_copy("test_master.vsdx"))
    own = _master_element(target, "Test Master")
    own.attrib["UniqueID"] = "{00000000-0000-0000-0000-000000000001}"
    before = {page._page_id for page in target.master_pages}
    instance = next(shape for shape in source.pages[0].shapes if shape.master_page == source.master_index["Test Master"])
    copied = instance.copy(target.pages[0])
    assert copied.master_page_ID not in before
    names = [page.name for page in target.master_pages]
    assert len(names) == len(set(names)), names
    target.save(saved)


def test_a_master_with_the_same_unique_id_is_reused(vsdx_copy):
    """Fails if a copy of a master the target already holds, unchanged, is imported a second time."""
    source = Document.open(vsdx_copy("test_master.vsdx"))
    target = Document.open(vsdx_copy("test_master.vsdx"))
    before = [page._page_id for page in target.master_pages]
    instance = next(shape for shape in source.pages[0].shapes if shape.master_page == source.master_index["Test Master"])
    copied = instance.copy(target.pages[0])
    assert [page._page_id for page in target.master_pages] == before
    assert copied.master_page is target.master_index["Test Master"]


def test_a_match_by_name_master_answers_for_its_name(vsdx_copy):
    """Fails if the document's own Dynamic connector, which sets MatchByName, is not the one a copied connector uses."""
    source = Document.open(vsdx_copy("fixtures/com_reference/s01_autoconnect_right.vsdx"))
    target = Document.open(vsdx_copy("test4_connectors.vsdx"))
    own = target.master_index["Dynamic connector"]
    assert own._master_unique_id != source.master_index["Dynamic connector"]._master_unique_id
    before = len(target.master_pages)
    connector = next(shape for shape in source.pages[0].shapes if shape.master_page_ID)
    copied = connector.copy(target.pages[0])
    assert copied.master_page is own
    assert len(target.master_pages) == before


def test_a_master_shape_the_reused_master_lacks_is_dropped(vsdx_copy, tmp_path):
    """Fails if a copied sub-shape keeps a `MasterShape` naming a shape the reused master does not have.

    A MatchByName master of the same name can be built differently, and a
    reference into it that reaches nothing loses the shape's inheritance.
    """
    saved = str(tmp_path / "reused_master.vsdx")
    fixture = "test_master_multiple_child_shapes.vsdx"
    source = Document.open(vsdx_copy(fixture))
    target = Document.open(vsdx_copy("test1.vsdx"))
    group = _master_instance(source)
    first = group.copy(target.pages[0])
    master = first.master_page
    # the target's master becomes one that matches by name and lacks a member
    element = target._masters.element_by_id(master._page_id)
    element.attrib["MatchByName"] = "1"
    element.attrib["UniqueID"] = "{00000000-0000-0000-0000-000000000002}"
    member = next(child for child in group.children if child.master_shape_ID)
    missing = member.master_shape_ID
    master_shapes = master.xml.getroot().find(f"{{{MAIN_NS}}}Shapes")[0].find(f"{{{MAIN_NS}}}Shapes")
    master_shapes.remove(next(s for s in master_shapes if s.attrib["ID"] == missing))
    first.delete()

    second = group.copy(target.pages[0])
    assert second.master_page is master
    references = [child.xml.attrib.get("MasterShape") for child in second.children]
    assert missing not in references
    assert any(references)
    target.save(saved)


def test_a_master_shape_whose_master_cannot_be_resolved_is_dropped(vsdx_copy):
    """Fails if a copied group whose own master is dangling leaves its members' `MasterShape` behind."""
    source = Document.open(vsdx_copy("test_master_multiple_child_shapes.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    group = _master_instance(source)
    group.xml.attrib["Master"] = "999"
    copied = group.copy(target.pages[0])
    assert [node.attrib for node in copied.xml.iter(f"{{{MAIN_NS}}}Shape") if "MasterShape" in node.attrib] == []
    sub_shape = next(child for child in group.children if child.master_shape_ID)
    copied_sub_shape = sub_shape.copy(target.pages[0])
    assert "MasterShape" not in copied_sub_shape.xml.attrib


def test_a_target_whose_app_xml_lists_no_titles_still_takes_a_copy(vsdx_copy):
    """Fails if a copy into a document whose app.xml has no TitlesOfParts raises: the element is optional."""
    source = Document.open(vsdx_copy("test_master.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    app = target._app_xml.getroot()
    app.remove(app.find("{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}TitlesOfParts"))
    plain = next(shape for shape in source.pages[0].shapes if not shape.master_page_ID)
    plain.copy(target.pages[0])
    _master_instance(source).copy(target.pages[0])
    assert len(target.master_pages) == 1


def test_same_name_masters_without_unique_ids_in_one_batch_import_once(vsdx_copy):
    """Fails if a batch imports two masters that copying them one at a time would treat as one."""
    source = Document.open(vsdx_copy("test_master.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    for master in source._masters.root:
        master.attrib.pop("UniqueID", None)
        master.attrib["NameU"] = master.attrib["Name"] = "Shared"
    ids = [page._page_id for page in source.master_pages]
    assert len(ids) == 2
    found = target._masters.import_masters(source._masters, ids)
    assert found[ids[0]] is found[ids[1]]
    assert len(target.master_pages) == 1


def test_a_colliding_import_takes_a_name_no_master_already_has(vsdx_copy):
    """Fails if the `Name.ID` a colliding import is given is itself taken, leaving a lookup by name ambiguous."""
    source = Document.open(vsdx_copy("test_master.vsdx"))
    target = Document.open(vsdx_copy("test_master.vsdx"))
    own = _master_element(target, "Test Master")
    own.attrib["UniqueID"] = "{00000000-0000-0000-0000-000000000003}"
    next_id = max(int(master.attrib["ID"]) for master in target._masters.root) + 1
    other = _master_element(target, "Test Master 2")
    other.attrib["NameU"] = other.attrib["Name"] = f"Test Master.{next_id}"
    target.load_master_pages()
    instance = next(shape for shape in source.pages[0].shapes if shape.master_page == source.master_index["Test Master"])
    instance.copy(target.pages[0])
    names = [master.attrib["NameU"] for master in target._masters.root]
    assert len(names) == len(set(names)), names


def test_a_target_whose_app_xml_has_no_heading_pairs_still_takes_a_copy(vsdx_copy):
    """Fails if a copy into a document whose app.xml has no HeadingPairs raises: without them no title has a section."""
    source = Document.open(vsdx_copy("test_master.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    app = target._app_xml.getroot()
    app.remove(app.find("{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}HeadingPairs"))
    _master_instance(source).copy(target.pages[0])
    assert len(target.master_pages) == 1
