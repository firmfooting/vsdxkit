"""`MasterCatalog` is the one owner of a document's masters (Phase 2, #93/#94).

Each test names the defect it pins. The saved packages go through the autouse
structural validator, so every save here is also checked for undeclared
masters, dangling relationships and missing content types.
"""

import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

from vsdxkit.connectors import Connect
from vsdxkit.masters import MasterCatalog
from vsdxkit.templating import JinjaTemplatingMixin
from vsdxkit.vsdxfile import VisioFile

RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


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
        copy = shape.copy(target.pages[0])
        copy_id = copy.ID
        target.save_vsdx(saved)

    with VisioFile(saved) as reopened:
        copied = reopened.pages[0].find_shape_by_id(copy_id)
        assert copied is not None
        assert copied.master_page is not None
        assert copied.master_page.name == master_name


def test_the_bootstrapped_masters_part_carries_the_imported_master(vsdx_copy, tmp_path):
    """Fails if the masters part a masterless document gains is lost or doubled (#367)."""
    saved = str(tmp_path / "bootstrapped.vsdx")
    with VisioFile(vsdx_copy("test5_master.vsdx")) as source, VisioFile(vsdx_copy("test1.vsdx")) as target:
        _master_instance(source).copy(target.pages[0])
        target.save_vsdx(saved)

    assert len(_masters(saved)) == 1
    assert len(_master_parts(saved)) == 1


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
    """Fails if `Connect.create` copies every master the bundled donor holds (#375).

    The masterless branch used to copy the donor's whole masters folder under
    hardcoded `master1.xml` and `rId1`; the connector needs only its own master.
    """
    saved = str(tmp_path / "connected.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        shapes = page.child_shapes
        connector = Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
        master_name = connector.master_page.name
        vis.save_vsdx(saved)

    masters = _masters(saved)
    assert [m.attrib.get("NameU") for m in masters] == [master_name]
    assert len(_master_parts(saved)) == 1


def test_a_page_master_relationship_takes_an_id_the_page_rels_does_not_hold(vsdx_copy):
    """Fails if the page's master relationship reuses an id from masters.xml.rels (#357).

    The two rels parts have separate id spaces: an id free in one says nothing
    about the other, and relationship ids must be unique within a part.
    """
    with VisioFile(vsdx_copy("test5_master.vsdx")) as source, VisioFile(vsdx_copy("test4_connectors.vsdx")) as target:
        page = target.pages[0]
        assert page.rels_xml is not None
        rels_root = page.rels_xml.getroot()
        taken = {r.attrib["Id"] for r in rels_root}
        for number in range(1, 10):
            if f"rId{number}" not in taken:
                ET.SubElement(
                    rels_root, f"{RELS_NS}Relationship", Id=f"rId{number}", Type="urn:unrelated", Target="unrelated.xml"
                )
        _master_instance(source).copy(page)
        ids = [r.attrib["Id"] for r in rels_root]
        assert len(ids) == len(set(ids))


def test_the_masters_module_does_not_load_the_document_class():
    """Fails if `vsdxkit.masters` imports `vsdxkit.vsdxfile`, directly or through what it imports.

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
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        catalog = vis._masters
        assert isinstance(catalog, MasterCatalog)
        for page in catalog.pages:
            assert catalog.by_id(page.page_id) is page
            assert catalog.by_name(page.name) is page
        assert catalog.by_id("no-such-id") is None


def test_a_saved_copy_reopens_with_every_master_declared(vsdx_copy, tmp_path):
    """The autouse validator checks the save; this checks the reopen reads every master part."""
    saved = str(tmp_path / "reopen.vsdx")
    with VisioFile(vsdx_copy("test5_master.vsdx")) as source, VisioFile(vsdx_copy("test4_connectors.vsdx")) as target:
        _master_instance(source).copy(target.pages[0])
        target.save_vsdx(saved)
    with VisioFile(saved) as reopened:
        assert len(reopened.master_pages) == len(_masters(saved))
