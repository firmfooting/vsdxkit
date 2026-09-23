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

from vsdxkit.connectors import Connect
from vsdxkit.errors import MissingPartError, VisioFileNotOpen
from vsdxkit.masters import MasterCatalog
from vsdxkit.partnames import relationship_target, relationships_part_name
from vsdxkit.templating import JinjaTemplatingMixin
from vsdxkit.vsdxfile import VisioFile

RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MASTER_RELATIONSHIP = "http://schemas.microsoft.com/visio/2010/relationships/master"


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


def _master_instance(vis: VisioFile):
    return next(shape for shape in vis.pages[0].all_shapes if shape.xml.attrib.get("Master"))


def _page_rels_root(page) -> ET.Element:
    """The page's rels root, created empty where the page has none yet."""
    if page.rels_xml is None:
        page.rels_xml_filename = relationships_part_name(page.filename)
        page.rels_xml = ET.ElementTree(ET.Element(f"{RELS_NS}Relationships"))
    return page.rels_xml.getroot()


def test_loading_the_masters_twice_lists_each_master_once(vsdx_copy):
    """Fails if `load_master_pages` appends to what it already holds (#375)."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
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
    with VisioFile(vsdx_copy("test5_master.vsdx")) as source, VisioFile(vsdx_copy("test1.vsdx")) as target:
        shape = _master_instance(source)
        master_name = shape.master_page.name
        copy_id = shape.copy(target.pages[0]).ID
        target.save_vsdx(saved)

    with VisioFile(saved) as reopened:
        copied = reopened.pages[0].find_shape_by_id(copy_id)
        assert copied is not None
        assert copied.master_page is not None
        assert copied.master_page.name == master_name


def test_a_sub_shape_copied_onto_another_documents_page_names_its_master(vsdx_copy, tmp_path):
    """Fails if a sub-shape of a master instance, copied out of its group, keeps a `MasterShape` that reaches nothing.

    The sub-shape names no master itself: it inherits its group's. Out of the
    group, the copy has to name the master, which has to be imported.
    """
    saved = str(tmp_path / "sub_shape.vsdx")
    with (
        VisioFile(vsdx_copy("test_master_multiple_child_shapes.vsdx")) as source,
        VisioFile(vsdx_copy("test1.vsdx")) as target,
    ):
        sub_shape = next(
            shape
            for shape in source.pages[0].all_shapes
            if shape.xml.attrib.get("MasterShape") and not shape.xml.attrib.get("Master")
        )
        copy_id = sub_shape.copy(target.pages[0]).ID
        target.save_vsdx(saved)

    with VisioFile(saved) as reopened:
        copied = reopened.pages[0].find_shape_by_id(copy_id)
        assert copied is not None
        assert copied.master_shape is not None


def test_the_bootstrapped_masters_part_carries_the_imported_master(vsdx_copy, tmp_path):
    """Fails if the masters part a masterless document gains is lost, doubled, or unreadable on reopen (#367)."""
    saved = str(tmp_path / "bootstrapped.vsdx")
    with VisioFile(vsdx_copy("test5_master.vsdx")) as source, VisioFile(vsdx_copy("test1.vsdx")) as target:
        _master_instance(source).copy(target.pages[0])
        target.save_vsdx(saved)

    assert len(_masters(saved)) == 1
    assert len(_master_parts(saved)) == 1
    with VisioFile(saved) as reopened:
        assert len(reopened.master_pages) == 1


def test_copying_the_same_master_twice_imports_it_once(vsdx_copy, tmp_path):
    """Fails if a second copy of an instance of one master adds a second master part."""
    saved = str(tmp_path / "twice.vsdx")
    with VisioFile(vsdx_copy("test5_master.vsdx")) as source, VisioFile(vsdx_copy("test1.vsdx")) as target:
        shape = _master_instance(source)
        first = shape.copy(target.pages[0])
        second = shape.copy(target.pages[0])
        assert first.master_page_ID == second.master_page_ID
        target.save_vsdx(saved)

    assert len(_masters(saved)) == 1
    assert len(_master_parts(saved)) == 1


def test_a_connector_in_a_masterless_document_brings_one_master(vsdx_copy, tmp_path):
    """Guards the count: a masterless document gains exactly the connector's master.

    The bundled donor holds one master, so this cannot tell #375's wholesale
    copy of the donor's masters from an import of one. The hardcoded `rId1`
    half of #375 is pinned by the page relationship test below.
    """
    saved = str(tmp_path / "connected.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        shapes = page.child_shapes
        connector = Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
        master_name = connector.master_page.name
        vis.save_vsdx(saved)

    assert [m.attrib.get("NameU") for m in _masters(saved)] == [master_name]
    assert len(_master_parts(saved)) == 1


@pytest.mark.parametrize("fixture", ["test1.vsdx", "test3_house.vsdx"])
def test_a_page_master_relationship_takes_an_id_the_page_rels_does_not_hold(vsdx_copy, fixture):
    """Fails if a connector's page relationship reuses an id the page's rels part already holds (#357, #375).

    A masterless document took the hardcoded `rId1`. A document with masters
    took the id from `masters.xml.rels`, a separate id space. Both were guarded
    on Target only, so a page rels part already holding the id got a duplicate.
    """
    with VisioFile(vsdx_copy(fixture)) as vis:
        page = vis.pages[0]
        rels_root = _page_rels_root(page)
        held = {r.attrib["Id"] for r in rels_root}
        for number in range(1, 10):
            if f"rId{number}" not in held:
                ET.SubElement(
                    rels_root, f"{RELS_NS}Relationship", Id=f"rId{number}", Type="urn:unrelated", Target="unrelated.xml"
                )
        prefilled = {r.attrib["Id"] for r in rels_root}
        shapes = page.child_shapes
        connector = Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])

        target = relationship_target(page.filename, connector.master_page.filename)
        master_relationships = [
            r for r in rels_root if r.attrib["Type"] == MASTER_RELATIONSHIP and r.attrib["Target"] == target
        ]
        assert len(master_relationships) == 1
        assert master_relationships[0].attrib["Id"] not in prefilled
        ids = [r.attrib["Id"] for r in rels_root]
        assert len(ids) == len(set(ids))


def test_a_nameless_master_imports_as_unknown_and_leaves_the_catalog_usable(vsdx_copy, tmp_path):
    """Fails if a master with neither NameU nor Name poisons the catalog it is imported into.

    A master page cannot be nameless: `Page.name` falls back to pages.xml, which
    a master page is not in, and every later lookup by name raised.
    """
    saved = str(tmp_path / "nameless.vsdx")
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as source, VisioFile(vsdx_copy("test1.vsdx")) as target:
        for master in source.masters_xml:
            master.attrib.pop("NameU", None)
            master.attrib.pop("Name", None)
        source.load_master_pages()
        shape = _master_instance(source)
        shape.copy(target.pages[0])
        shape.copy(target.pages[0])
        assert "Unknown" in target.master_index
        target.save_vsdx(saved)


def test_a_document_without_app_xml_still_takes_a_master(vsdx_copy, tmp_path):
    """Fails if importing a master into a package with no docProps/app.xml raises (#385).

    app.xml is optional, and a package without one has no TitlesOfParts to keep
    in step with its masters.
    """
    # named after its fixture, which declares docProps parts it does not hold:
    # the package validator excuses defects an output inherits from its input
    saved = str(tmp_path / "test5_master_connected.vsdx")
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as source, VisioFile(vsdx_copy("test5_master.vsdx")) as target:
        assert target.app_xml is None, "fixture is expected to have no app.xml"
        page = target.pages[0]
        _master_instance(source).copy(page)
        shapes = page.child_shapes
        Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
        target.save_vsdx(saved)


def test_a_master_that_cannot_be_read_leaves_the_target_as_it_was(vsdx_copy, monkeypatch):
    """Fails if importing several masters writes the first before finding the second unreadable."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as source, VisioFile(vsdx_copy("test1.vsdx")) as target:
        first, second = source.master_pages[:2]
        read_bytes = source._package.read_bytes
        monkeypatch.setattr(source._package, "read_bytes", lambda name: None if name == second.filename else read_bytes(name))
        before = target._package.names()
        with pytest.raises(MissingPartError, match="could not be read"):
            target._masters.import_masters(source._masters, [first.page_id, second.page_id])
        assert target._package.names() == before
        assert target.master_pages == []


def test_a_copy_onto_another_page_of_the_same_document_relates_that_page_to_the_master(vsdx_copy):
    """Fails if a page gains a master instance without the page relationship Visio writes for it."""
    with VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        shape = _master_instance(vis)
        new_page = vis.add_page()
        shape.copy(new_page)
        target = relationship_target(new_page.filename, shape.master_page.filename)
        assert new_page.rels_xml is not None
        assert any(
            r.attrib["Type"] == MASTER_RELATIONSHIP and r.attrib["Target"] == target for r in new_page.rels_xml.getroot()
        )


def test_a_copy_within_one_document_keeps_a_master_reference_it_cannot_resolve(vsdx_copy):
    """Fails if a copy within one document strips a dangling `Master`: repairing the source is not a copy's job.

    Only a copy into another document drops such a reference, where keeping it
    would name a master that package does not declare.
    """
    with VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        shape = _master_instance(vis)
        shape.xml.attrib["Master"] = "999"
        copy = shape.copy(vis.pages[0])
        assert copy.xml.attrib["Master"] == "999"


def test_copying_into_a_closed_document_names_the_copy(vsdx_copy):
    """Fails if the refusal names an internal step rather than the operation the caller made."""
    with VisioFile(vsdx_copy("test5_master.vsdx")) as source:
        target = VisioFile(vsdx_copy("test1.vsdx"))
        page = target.pages[0]
        target.close_vsdx()
        with pytest.raises(VisioFileNotOpen, match=r"Shape\.copy\(\)"):
            _master_instance(source).copy(page)


def test_the_masters_module_does_not_load_the_document_class():
    """Guards the seam: `vsdxkit.masters` must not import `vsdxkit.vsdxfile`, directly or through what it imports.

    The catalog is a lower layer: the document hands it a factory for master
    pages rather than the catalog reaching up for the class.
    """
    script = "import sys, vsdxkit.masters; print('vsdxkit.vsdxfile' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "False"


def test_the_document_has_no_masters_mixin():
    """Fails if `VisioFile` still takes master behaviour from a mixin (#94)."""
    assert VisioFile.__bases__ == (JinjaTemplatingMixin,)


def test_the_catalog_answers_by_id_and_by_name(vsdx_copy):
    """Fails if the catalog's lookups disagree with the pages it lists."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        catalog = vis._masters
        assert isinstance(catalog, MasterCatalog)
        for page in catalog.pages:
            assert catalog.by_id(page.page_id) is page
            assert catalog.by_name(page.name) is page
        assert catalog.by_id("no-such-id") is None
