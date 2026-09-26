"""Pytest Tests for Document class"""

import os
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element

import pytest

from vsdxkit import ext_prop_namespace, media, namespace, vt_namespace
from vsdxkit.document import Document


def _media_filename() -> str:
    return media.media_path(media.MEDIA)


# file structure


def test_invalid_file_type():
    """Test that opening an invalid file name results in a TypeError"""
    filename = __file__
    print(f"Opening invalid but existing {filename}")
    with pytest.raises(TypeError):
        Document.open(filename)
        pass


@pytest.mark.parametrize(
    "filename",
    [
        "test1.vsdx",
        "diagram_with_macro.vsdm",
    ],
)
def test_open_rel_path(filename: str, basedir, monkeypatch):
    """A package opens, and its pages load, when named by a relative path."""
    # run from the tests directory so the bare filename is genuinely relative,
    # rather than computing a relative path that can cross drives on Windows
    monkeypatch.chdir(basedir)
    assert os.path.exists(filename), "bare filename did not resolve against the new working directory"
    vis = Document.open(filename)
    assert vis.pages
    assert all(page.name for page in vis.pages)


def test_open_abs_path():
    """A package outside the tests tree opens the same way by absolute path."""
    filename = os.path.abspath(_media_filename())
    assert os.path.exists(filename)
    vis = Document.open(filename)
    assert vis.pages
    assert all(page.name for page in vis.pages)


def test_open_abs_path_save_rel_path(tmp_path, monkeypatch):
    # test opening media file (not in tests directory)with absolute path
    media_file_path = _media_filename()
    filename = os.path.abspath(media_file_path)

    assert os.path.exists(filename)
    # the destination must stay relative, so run from tmp_path rather than naming it
    monkeypatch.chdir(tmp_path)
    output_file = "abs_to_rel_out.vsdx"
    vis = Document.open(filename)
    vis.save(output_file)
    assert (tmp_path / output_file).exists()


def test_open_abs_path_save_abs_path(tmp_path):
    # test opening media file (not in tests directory) with absolute path
    filename = os.path.abspath(_media_filename())

    output_file = os.path.abspath(os.path.join(str(tmp_path), "abs_to_abs_out.vsdx"))
    vis = Document.open(filename)
    vis.save(output_file)
    assert os.path.exists(output_file)


# Helpers


@pytest.mark.parametrize(("filename", "shape_elements"), [("test1.vsdx", 4), ("test2.vsdx", 14), ("test3_house.vsdx", 10)])
def test_xml_findall_shapes(filename: str, shape_elements: int, basedir):
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    # find all Shape elements
    xml = page.xml.getroot()
    xpath = f".//{namespace}Shape"
    elements = xml.findall(xpath)
    print(f"{xpath} returns {len(elements)} elements vs {shape_elements}")
    assert len(elements) == shape_elements


@pytest.mark.parametrize(("filename", "group_shape_elements"), [("test1.vsdx", 0), ("test2.vsdx", 3), ("test3_house.vsdx", 2)])
def test_xml_findall_group_shapes(filename: str, group_shape_elements: int, basedir):
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    # find all Shape elements where attribute Type='Group'
    xml = page.xml.getroot()
    xpath = f".//{namespace}Shape[@Type='Group']"
    elements = xml.findall(xpath)
    print(f"{xpath} returns {len(elements)} elements vs {group_shape_elements}")
    assert len(elements) == group_shape_elements


# working with Pages


def _app_xml_page_count(vis) -> int:
    heading_pairs = vis._app_xml.getroot().find(f"{ext_prop_namespace}HeadingPairs")
    return int(heading_pairs.find(f".//{vt_namespace}i4").text)


def _app_xml_page_names(vis) -> list[str]:
    """The page names `docProps/app.xml` declares, in the order it lists them.

    `app.xml` is document metadata written alongside `pages.xml`, and the two
    going out of step is invisible from either one alone.
    """
    titles = vis._app_xml.getroot().find(f"{ext_prop_namespace}TitlesOfParts")
    vector = titles.find(f"{vt_namespace}vector")
    return [lpstr.text for lpstr in vector.findall(f"{vt_namespace}lpstr")]


@pytest.mark.parametrize(
    ("filename"),
    [
        ("test1.vsdx"),
    ],
)
def test_app_xml_page_names(filename: str, basedir):
    # test that page names in app.xml matches page names loaded
    vis = Document.open(os.path.join(basedir, filename))
    assert _app_xml_page_count(vis) == len(vis.pages)
    assert _app_xml_page_names(vis) == [p.name for p in vis.pages]


@pytest.mark.parametrize(
    ("filename", "page_index"),
    [
        ("test1.vsdx", 0),
        ("test5_master.vsdx", 0),
    ],
)
def test_remove_page_by_index(filename: str, page_index: int, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_remove_page.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    page_count = len(vis.pages)
    vis.pages.delete(vis.pages[page_index])
    vis.save(out_file)

    # re-open file and confirm it has one less page
    vis = Document.open(out_file)
    assert len(vis.pages) == page_count - 1


@pytest.mark.parametrize(
    ("filename", "page_name"),
    [
        ("test1.vsdx", "1"),
        ("test2.vsdx", "2"),
        ("test3_house.vsdx", "1"),
        ("test4_connectors.vsdx", "2"),
        ("test5_master.vsdx", "1"),
        ("test6_shape_properties.vsdx", "2"),
        ("test7_with_connector.vsdx", "3"),
        ("test8_simple_connector.vsdx", "none"),
    ],
)
def test_remove_page_by_page_index(filename: str, page_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_remove_page_by_page_index.vsdx")
    expected_page_names = []
    vis = Document.open(os.path.join(basedir, filename))
    print(f"Found {len(vis.pages)} pages, {sorted([p.name for p in vis.pages])}")
    for page in list(vis.pages):
        print(f"page.name='{page.name}' index:{page.index_num}")
        if page_name in page.name:
            print(f"Removing page index {page.index_num}")
            vis.pages.delete(vis.pages[page.index_num])
        else:
            expected_page_names.append(page.name)

    vis.save(out_file)

    print(f"expected names={expected_page_names}")
    # re-open file and confirm it contains all and only those not deleted
    vis = Document.open(out_file)
    print(f"Found {len(vis.pages)} pages, {sorted([p.name for p in vis.pages])}")
    assert sorted(expected_page_names) == sorted([p.name for p in vis.pages])


@pytest.mark.parametrize(
    ("filename", "page_name"),
    [
        ("test1.vsdx", "Page-1"),
        ("test2.vsdx", "Page-2"),
        ("test3_house.vsdx", "Page-1"),
        ("test4_connectors.vsdx", "Page-2"),
        ("test5_master.vsdx", "Page 1"),
        ("test6_shape_properties.vsdx", "Page-2"),
        ("test7_with_connector.vsdx", "Page-3"),
    ],
)
def test_remove_page_by_name(filename: str, page_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_remove_page_by_name.vsdx")
    expected_page_names = []
    vis = Document.open(os.path.join(basedir, filename))
    print(f"Found {len(vis.pages)} pages, {sorted([p.name for p in vis.pages])}")
    for page in list(vis.pages):
        print(f"page.name='{page.name}' index:{page.index_num}")
        if page_name != page.name:
            expected_page_names.append(page.name)
    vis.pages.delete(vis.pages.require_name(page_name))
    vis.save(out_file)

    print(f"expected names={expected_page_names}")
    # re-open file and confirm it contains all and only those not deleted
    vis = Document.open(out_file)
    print(f"Found {len(vis.pages)} pages, {sorted([p.name for p in vis.pages])}")
    assert sorted(expected_page_names) == sorted([p.name for p in vis.pages])


@pytest.mark.parametrize(
    ("filename", "remove_index"),
    [
        ("test1.vsdx", 0),
        ("test1.vsdx", 1),
        ("test2.vsdx", 0),
    ],
)
def test_app_xml_page_names_after_remove_page(filename: str, remove_index: int, basedir):
    # test that page names in app.xml matches page names loaded
    vis = Document.open(os.path.join(basedir, filename))
    vis.pages.delete(vis.pages[remove_index])

    assert _app_xml_page_count(vis) == len(vis.pages)
    assert _app_xml_page_names(vis) == [p.name for p in vis.pages]


@pytest.mark.parametrize(("filename"), [("test1.vsdx")])
def test_add_page(filename: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_add_page.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    number_pages = len(vis.pages)

    new_page = vis.pages.create()
    assert new_page
    assert len(vis.pages) == number_pages + 1

    new_page_name = new_page.name
    vis.save(out_file)

    vis = Document.open(out_file)
    page = vis.pages.by_name(new_page_name)
    assert page


@pytest.mark.parametrize(
    ("filename", "page_name"),
    [
        ("test1.vsdx", "newname"),
        ("test1.vsdx", "Page-1"),
    ],
)
def test_add_page_name(filename: str, page_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_add_page_name_{page_name}.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    number_pages = len(vis.pages)

    new_page = vis.pages.create(page_name)
    assert new_page
    assert len(vis.pages) == number_pages + 1

    new_page_name = new_page.name
    vis.save(out_file)

    vis = Document.open(out_file)
    page = vis.pages.by_name(new_page_name)
    assert page


@pytest.mark.parametrize(
    ("filename", "index", "page_name"),
    [
        ("test1.vsdx", 1, None),
        ("test1.vsdx", 1, "newname"),
        ("test1.vsdx", 1, "Page-1"),
    ],
)
def test_add_page_at(filename: str, index: int, page_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_add_page_at_{page_name}.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    number_pages = len(vis.pages)

    new_page = vis.pages.create(page_name, index=index)
    assert new_page
    assert len(vis.pages) == number_pages + 1

    new_page_name = new_page.name
    vis.save(out_file)

    vis = Document.open(out_file)
    page = vis.pages.by_name(new_page_name)
    assert page


@pytest.mark.parametrize(
    ("filename", "new_page_name", "location"),
    [
        ("test1.vsdx", "new_page", 0),
        ("test1.vsdx", "new_page", 1),
        ("test2.vsdx", "new_page", 0),
        # `None` means append, rather than insert at an index.
        # No row reached that branch before.
        ("test1.vsdx", "new_page", None),
        ("test2.vsdx", "new_page", None),
    ],
)
def test_app_xml_page_names_after_add_page(filename: str, new_page_name: str, location: int | None, basedir):
    # test that page names in app.xml matches page names loaded
    vis = Document.open(os.path.join(basedir, filename))
    if location is None:
        vis.pages.create(new_page_name)
    else:
        vis.pages.create(new_page_name, index=location)

    assert _app_xml_page_count(vis) == len(vis.pages)

    # TitlesOfParts is document metadata and does not track pages.xml
    # order, so the comparison is order-insensitive now that insertion
    # positions are actually honoured
    assert sorted(_app_xml_page_names(vis)) == sorted(p.name for p in vis.pages)


def test_copy_page_clones_relationship_part(vsdx_copy, tmp_path):
    filename = vsdx_copy("test4_connectors.vsdx")
    output = tmp_path / "copied-page.vsdx"

    vis = Document.open(filename)
    source = vis.pages[0]
    assert source._rels_xml is not None
    source_rels = ET.tostring(source._rels_xml.getroot())

    copied = vis.pages.copy(source)

    assert copied._rels_xml is not None
    assert copied._rels_xml is not source._rels_xml
    assert ET.tostring(copied._rels_xml.getroot()) == source_rels
    assert copied._rels_xml_filename is not None
    member = copied._rels_xml_filename[1:]
    vis.save(str(output))

    with zipfile.ZipFile(output) as archive:
        assert member in archive.namelist()


@pytest.mark.parametrize(
    ("filename", "index", "page_name"),
    [
        ("test1.vsdx", 3, None),
        ("test1.vsdx", 0, "newname"),
        ("test1.vsdx", 2, "Page-1"),
        ("test2.vsdx", 2, "Page-1"),
        ("test4_connectors.vsdx", 0, "Page-1"),
    ],
)
def test_copy_page(filename: str, index: int, page_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_copy_page_{page_name}.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    number_pages = len(vis.pages)

    page = vis.pages[0]  # type: Page
    new_page = vis.pages.copy(page, index=index, name=page_name)
    assert new_page
    assert len(vis.pages) == number_pages + 1

    new_page_name = new_page.name
    vis.save(out_file)

    vis = Document.open(out_file)
    page = vis.pages.by_name(new_page_name)
    assert page


@pytest.mark.parametrize(
    ("filename", "page_index_to_copy", "in_page_name", "out_page_name"),
    [
        ("test1.vsdx", 0, None, "Page-1-1"),
        ("test1.vsdx", 0, "newname", "newname"),
        ("test1.vsdx", 0, "Page-1", "Page-1-1"),
        ("test1.vsdx", 1, None, "Page-2-1"),
        ("test1.vsdx", 1, "newname", "newname"),
        ("test1.vsdx", 1, "Page-1", "Page-1-1"),
    ],
)
def test_copy_page_naming(filename: str, page_index_to_copy: int, in_page_name: str, out_page_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_copy_page_naming.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[page_index_to_copy]  # type: Page
    new_page = vis.pages.copy(page, name=in_page_name)
    print(f"in_page_name:{in_page_name} out_page_name:{out_page_name} actual:{new_page.name}")
    assert new_page.name == out_page_name  # check new page has expected name
    vis.save(out_file)

    vis = Document.open(out_file)
    page = vis.pages.by_name(out_page_name)
    assert page  # check that page name persists through file save and open


@pytest.mark.parametrize(
    ("filename", "page_index_to_copy", "index", "out_page_index"),
    [
        # at the end, before the source (its own index), and after it (no index)
        ("test1.vsdx", 0, 3, 3),
        ("test1.vsdx", 0, 0, 0),
        ("test1.vsdx", 0, None, 1),
        ("test1.vsdx", 1, 3, 3),
        ("test1.vsdx", 1, 1, 1),
        ("test1.vsdx", 1, None, 2),
    ],
)
def test_copy_page_positions(
    filename: str, page_index_to_copy: int, index: int | None, out_page_index: int, tmp_path, basedir
):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_copy_page_position.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[page_index_to_copy]  # type: Page
    new_page = vis.pages.copy(page, index=index)
    assert vis.pages.index(new_page) == out_page_index  # check new page has expected index
    vis.save(out_file)

    vis = Document.open(out_file)
    page = vis.pages.by_name(new_page.name)
    index = vis.pages.index(page)
    assert index == out_page_index  # check that page location persists through file save and open


# working with Shapes


@pytest.mark.parametrize(("filename", "shape_name"), [("test1.vsdx", "Shape to copy"), ("test4_connectors.vsdx", "Shape B")])
def test_vis_copy_shape(filename: str, shape_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_vis_copy_shape.vsdx")

    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    # find and copy shape by name
    s = page.shapes.by_text(shape_name)  # type: Shape
    assert s  # check shape found
    print(f"Found shape id:{s.ID}")
    max_id = max(int(existing.ID) for existing in page.shapes)

    # note = this does add the shape, but prefer Shape.copy() as per next test which wraps this and returns Shape
    new_shape = page._copy_shape_xml(s.xml)

    assert isinstance(new_shape, Element)  # check _copy_shape_xml returns xml

    print(f"created new shape {type(new_shape)} {new_shape} {new_shape.attrib['ID']}")
    assert int(new_shape.attrib.get("ID")) > int(s.ID)
    assert int(new_shape.attrib.get("ID")) > max_id

    new_shape_id = new_shape.attrib["ID"]
    vis.save(out_file)

    # re-open saved file and check it is changed as expected
    vis = Document.open(out_file)
    page = vis.pages[0]
    s = page.shapes.by_id(new_shape_id)
    assert s


@pytest.mark.parametrize(("filename", "shape_name"), [("test1.vsdx", "Shape to copy"), ("test2.vsdx", "Shape to copy")])
def test_copy_shape_other_page(filename: str, shape_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_copy_shape_other_page.vsdx")

    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    page2 = vis.pages[1]  # type: Page
    page3 = vis.pages[2]  # type: Page
    # find and copy shape by name
    s = page.shapes.by_text(shape_name)  # type: Shape
    assert s  # check shape found
    shape_text = s.text
    print(f"Found shape id:{s.ID}")

    new_shape = page2._copy_shape_xml(s.xml)
    assert isinstance(new_shape, Element)  # check _copy_shape_xml returns xml
    print(f"created new shape {type(new_shape)} {new_shape} {new_shape.attrib['ID']}")
    page2_new_shape_id = new_shape.attrib["ID"]

    new_shape = page3._copy_shape_xml(s.xml)
    assert isinstance(new_shape, Element)  # check _copy_shape_xml returns xml
    print(f"created new shape {type(new_shape)} {new_shape} {new_shape.attrib['ID']}")
    print(f"created new shape {type(new_shape)} {new_shape} {new_shape.attrib['ID']}")
    page3_new_shape_id = new_shape.attrib["ID"]

    vis.save(out_file)

    # re-open saved file and check it is changed as expected
    vis = Document.open(out_file)
    page2 = vis.pages[1]
    s = page2.shapes.by_id(page2_new_shape_id)
    assert s
    assert s.text == shape_text
    page3 = vis.pages[2]
    s = page3.shapes.by_id(page3_new_shape_id)
    assert s
    assert s.text == shape_text


def test_every_xml_part_of_an_opened_document_parses(basedir):
    """Fails if a part named `.xml` or `.rels` cannot be promoted to a tree."""
    vis = Document.open(os.path.join(basedir, "test1.vsdx"))
    assert vis._package.names()
    for name in vis._package.names():
        if name.endswith((".xml", ".rels")):
            assert vis._package.read_xml(name) is not None


def test_a_document_has_no_close_state(vsdx_copy):
    """Fails if the context manager or `close_vsdx` come back: a document holds no file, so there is nothing to close."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    assert not hasattr(vis, "__enter__")
    assert not hasattr(vis, "close_vsdx")
    assert not hasattr(vis, "file_open")
    # Python 3.10 reports a missing __enter__ as AttributeError, 3.11 on as TypeError
    with pytest.raises((TypeError, AttributeError)):
        with vis:  # type: ignore[attr-defined]
            pass


def test_visiofilenotopen_is_gone():
    import vsdxkit.errors

    assert not hasattr(vsdxkit.errors, "VisioFileNotOpen")


def test_open_takes_a_path(vsdx_copy):
    vis = Document.open(Path(vsdx_copy("test1.vsdx")))
    assert vis.pages[0].name


def test_save_returns_the_absolute_path_it_wrote(vsdx_copy, tmp_path, monkeypatch):
    source = vsdx_copy("test1.vsdx")
    vis = Document.open(source)
    monkeypatch.chdir(tmp_path)

    written = vis.save("copy.vsdx")
    in_place = vis.save()

    assert written == tmp_path / "copy.vsdx"
    assert written.is_absolute() and zipfile.is_zipfile(written)
    assert in_place == Path(source).resolve()


def test_save_appends_the_package_kind_to_a_bare_name(vsdx_copy, tmp_path):
    vis = Document.open(vsdx_copy("test1.vsdx"))
    assert vis.save(tmp_path / "bare").name == "bare.vsdx"


def test_the_0x_names_are_gone(vsdx_copy):
    """Fails if a 0.x name comes back beside its 1.0 replacement (#108)."""
    import importlib.util

    import vsdxkit.document

    assert importlib.util.find_spec("vsdxkit.vsdxfile") is None
    assert not hasattr(vsdxkit.document, "VisioFile")
    vis = Document.open(vsdx_copy("test1.vsdx"))
    for name in ("save_vsdx", "jinja_render_vsdx", "open_vsdx_file", "debug", "limits"):
        assert not hasattr(vis, name), name
    with pytest.raises(TypeError):
        Document.open(vsdx_copy("test1.vsdx"), debug=True)  # type: ignore[call-arg]


def test_the_dead_document_members_are_gone():
    """Fails if a member Phase 7 deleted as dead comes back (#116)."""
    import dataclasses

    from vsdxkit.package import XmlPart
    from vsdxkit.pages import _PagePosition

    for name in (
        "get_shape_location",
        "set_shape_location",
        "get_shape_id",
        "apply_text_context",
        "pretty_print_element",
        "document_rels",
        "_part_tree",
        "_require_part_xml",
        "_get_styles_name_list",
        "_get_style_by_name",
        "_get_app_xml_value",
    ):
        assert not hasattr(Document, name), name
    # iteration skips aliases, so END is checked by name
    assert [position.name for position in _PagePosition] == ["LAST", "AFTER"]
    assert "END" not in _PagePosition.__members__
    assert "promoted_from" not in {field.name for field in dataclasses.fields(XmlPart)}


def test_the_package_internals_are_private(vsdx_copy):
    """Fails if a package internal of `Document` or `Page` is public again (#116, decision 1)."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    for name in (
        "pages_xml",
        "pages_xml_rels",
        "content_types_xml",
        "app_xml",
        "document_xml",
        "document_xml_rels",
        "masters_xml",
        "load_pages",
        "get_master_page_by_id",
        "PAGES",
        "MASTERS",
    ):
        assert not hasattr(vis, name), f"Document.{name}"
    page = vis.pages[0]
    for name in ("filename", "page_id", "rel_id", "master_unique_id", "rels_xml", "rels_xml_filename"):
        assert not hasattr(page, name), f"Page.{name}"
        assert hasattr(page, f"_{name}"), f"Page._{name}"


def test_masters_from_something_that_is_not_a_document_are_refused(vsdx_copy):
    """Fails if a look-alike source document gets past `_masters_for` and breaks on the master catalog it lacks."""

    class LooksLikeADocument:
        pages = ()

    vis = Document.open(vsdx_copy("test1.vsdx"))
    with pytest.raises(TypeError, match="LooksLikeADocument"):
        vis._masters_for(["1"], LooksLikeADocument())
