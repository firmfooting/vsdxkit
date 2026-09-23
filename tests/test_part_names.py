"""Pages and masters are named by their OPC part names (#91).

The names used to be pseudo-paths under the source file's path minus its
extension, a directory no file was ever in, and every use stripped them back
to part names. A part name is what the store, the relationship parts and
[Content_Types].xml all say.
"""

import os
import posixpath
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile

import pytest

from vsdxkit import media
from vsdxkit.connectors import Connect
from vsdxkit.errors import MalformedPackageError
from vsdxkit.partnames import relationships_part_name
from vsdxkit.shapes import find_or_create_shapes_tag
from vsdxkit.vsdxfile import VisioFile

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def test_loaded_pages_and_masters_are_named_by_part_name(vsdx_copy):
    """Fails if a loaded page or master is named by anything but its part name."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        assert vis.pages[0].filename == "/visio/pages/page1.xml"
        assert all(page.filename.startswith("/visio/pages/page") for page in vis.pages)
        assert vis.master_pages, "the fixture has changed: it should carry masters"
        assert all(master.filename.startswith("/visio/masters/master") for master in vis.master_pages)
        with_rels = [page for page in vis.pages if page.rels_xml_filename is not None]
        assert all(page.rels_xml_filename.startswith("/visio/pages/_rels/") for page in with_rels)


def test_added_and_copied_pages_are_named_by_part_name(vsdx_copy):
    """Fails if a page the library creates is named by anything but its part name."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        added = vis.add_page("Added")
        copied = vis.copy_page(vis.pages[0], name="Copied")
        for page in (added, copied):
            assert page.filename.startswith("/visio/pages/page")
            assert vis._package.part(page.filename) is not None
        assert copied.rels_xml_filename == relationships_part_name(copied.filename)


def test_a_document_has_no_directory_prefix_in_any_page_name(vsdx_copy):
    """Fails if the source path leaks into a page's name."""
    path = vsdx_copy("test2.vsdx")
    with VisioFile(path) as vis:
        stem = os.path.splitext(os.path.abspath(path))[0]
        assert not any(stem in page.filename for page in (*vis.pages, *vis.master_pages))


def test_a_page_rels_created_under_a_visio_pages_directory_lands_in_the_package(tmp_path):
    """Fails if the page-rels name is built by rewriting a path that contains `visio/pages/` twice.

    `_ensure_page_master_rel` derives the rels part from the page's name. With
    a pseudo-path, a source file kept under a directory called visio/pages had
    that directory rewritten too.
    """
    home = tmp_path / "visio" / "pages"
    home.mkdir(parents=True)
    path = home / "test1.vsdx"
    shutil.copy(os.path.join(FIXTURES, "test1.vsdx"), path)
    out = tmp_path / "out.vsdx"
    with VisioFile(str(path)) as vis:
        page = vis.pages[0]
        shapes = page.child_shapes
        page.connect_shapes(shapes[0], shapes[1])
        assert page.rels_xml_filename == "/visio/pages/_rels/page1.xml.rels"
        vis.save_vsdx(str(out))
    with zipfile.ZipFile(out) as archive:
        assert "visio/pages/_rels/page1.xml.rels" in archive.namelist()


@pytest.mark.allow_invalid_package("missing-part", "unresolved-page")
@pytest.mark.parametrize("target", ["../page1.xml", "a/../../page1.xml"])
def test_a_page_target_outside_the_pages_folder_still_fails_the_open(tmp_path, target):
    """Fails if joining a relationship Target onto a part name lets a traversal through."""
    source = os.path.join(FIXTURES, "test1.vsdx")
    crafted = tmp_path / "crafted.vsdx"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(crafted, "w") as rewritten:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == "visio/pages/_rels/pages.xml.rels":
                root = ET.fromstring(data)
                root[0].set("Target", target)
                data = ET.tostring(root)
            rewritten.writestr(entry, data)
    with pytest.raises(MalformedPackageError):
        VisioFile(str(crafted))


def test_insert_shape_takes_the_pages_part_name(vsdx_copy):
    """Fails if `insert_shape` refuses the name `Page.filename` now holds, or accepts another page's."""
    with VisioFile(vsdx_copy("test2.vsdx")) as vis:
        assert len(vis.pages) > 1, "the fixture has changed: it should have more than one page"
        page, other = vis.pages[0], vis.pages[1]
        shapes = find_or_create_shapes_tag(page.xml.getroot())
        source = page.child_shapes[0].xml
        vis.insert_shape(ET.fromstring(ET.tostring(source)), shapes, page, page.filename)
        with pytest.raises(ValueError):
            vis.insert_shape(ET.fromstring(ET.tostring(source)), shapes, page, other.filename)


def test_the_connector_master_is_imported_from_the_donor_not_the_target(vsdx_copy):
    """Fails if importing a master reads the target document's part of the same name.

    The bundled donor and the target now name their parts identically; only
    the store a name is looked up in says whose part it is. `test3_house.vsdx`
    ships exactly one master, which puts `Connect.create()` on the import
    branch (see tests/test_master_import_opc.py).
    """
    with VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        target_before = {master.filename: vis._package.read_bytes(master.filename) for master in vis.master_pages}
        page = vis.pages[0]
        shapes = page.child_shapes
        Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
        donor = media.donor(media.MEDIA)
        master_page_id = media.connector_shape().master_page_ID
        assert master_page_id is not None
        connector_master = donor.get_master_page_by_id(master_page_id)
        assert connector_master is not None
        imported = vis.master_index[connector_master.name]
        assert imported.filename not in target_before, "the import wrote over one of the target's own masters"
        assert vis._package.read_bytes(imported.filename) == donor._package.read_bytes(connector_master.filename)
        for name, data in target_before.items():
            assert vis._package.read_bytes(name) == data


def test_a_connector_reaches_a_master_kept_in_a_subfolder_of_the_masters_folder(tmp_path):
    """Fails if the page relationship `Connect.create` writes to a master drops the master's subfolder.

    Nothing requires a package to keep its masters directly in
    `/visio/masters/`: masters.xml reaches each one by a Target, and here that
    Target is `sub/masterN.xml`. `test4_connectors.vsdx` already holds a
    "Dynamic connector", so the connector reuses that master rather than
    importing one, and the page's Target has to name the part where it is.
    """
    crafted = tmp_path / "crafted.vsdx"
    with (
        zipfile.ZipFile(os.path.join(FIXTURES, "test4_connectors.vsdx")) as original,
        zipfile.ZipFile(crafted, "w") as rewritten,
    ):
        for entry in original.infolist():
            data = original.read(entry.filename)
            name = entry.filename
            if re.fullmatch(r"visio/masters/master\d+\.xml", name):
                name = name.replace("visio/masters/", "visio/masters/sub/")
            elif name == "visio/masters/_rels/masters.xml.rels":
                data = data.replace(b'Target="master', b'Target="sub/master')
            elif name == "[Content_Types].xml":
                data = re.sub(rb'PartName="/visio/masters/(master\d+\.xml)"', rb'PartName="/visio/masters/sub/\1"', data)
            elif name.startswith("visio/pages/_rels/page"):
                data = data.replace(b'Target="../masters/master', b'Target="../masters/sub/master')
            rewritten.writestr(name, data)
    with VisioFile(str(crafted)) as vis:
        assert "Dynamic connector" in vis.master_index, "the fixture has changed: it should hold the connector master"
        page = vis.pages[0]
        shapes = page.child_shapes
        Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
        rels_root = page.rels_xml.getroot()
        assert rels_root is not None
        targets = [rel.attrib["Target"] for rel in rels_root]
        assert targets
        # resolved here, `..` and all, because `target_part_name` joins a
        # Target as written; resolving it the way OPC does is #378
        resolved = {t: posixpath.normpath(posixpath.join(posixpath.dirname(page.filename), t)) for t in targets}
        assert {t: name for t, name in resolved.items() if vis._package.part(name) is None} == {}
        vis.save_vsdx(str(tmp_path / "out.vsdx"))


def test_a_document_has_no_zip_file_contents_or_directory(vsdx_copy):
    """Fails if the pre-store view or its pseudo-path root is still on `VisioFile` (#91)."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        assert not hasattr(vis, "zip_file_contents")
        assert not hasattr(vis, "directory")


@pytest.mark.parametrize("name", ["file_to_xml", "xml_to_file", "require_xml_tree", "require_root"])
def test_xmlio_has_no_helpers_over_the_old_mapping(name):
    """Fails if a helper that took the pre-store `{path: BytesIO}` mapping is still in `xmlio` (#91)."""
    import vsdxkit.xmlio

    assert not hasattr(vsdxkit.xmlio, name)
    assert not hasattr(vsdxkit.vsdxfile, name)


def test_a_removed_pages_xml_assignment_writes_nothing(vsdx_copy):
    """Fails if a page removed from the document can still write its part."""
    with VisioFile(vsdx_copy("test2.vsdx")) as vis:
        removed = vis.pages[-1]
        name = removed.filename
        vis.remove_page_by_index(len(vis.pages) - 1)
        removed.xml = ET.ElementTree(ET.fromstring(ET.tostring(removed.xml.getroot())))
        assert vis._package.part(name) is None


def test_a_page_with_no_rels_part_gets_one_on_assignment(vsdx_copy):
    """Fails if a live page with no relationship part cannot be given one."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        assert page.rels_xml is None, "the fixture has changed: page 1 should have no rels part"
        page.rels_xml_filename = f"/visio/pages/_rels/{page.filename.rsplit('/', 1)[-1]}.rels"
        page.rels_xml = ET.ElementTree(
            ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        )
        assert vis._package.part(page.rels_xml_filename) is not None
