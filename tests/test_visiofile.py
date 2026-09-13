"""Pytest Tests for VisioFile class"""

import io
import os
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from xml.etree.ElementTree import Element

import pytest

from vsdx import Media, PagePosition, VisioFile, ext_prop_namespace, namespace, vt_namespace
from vsdx.vsdxfile import file_to_xml


def _media_filename() -> str:
    media = Media()
    try:
        return media.media.filename
    finally:
        media.close()


# file structure


def test_apply_text_context_coerces_non_string_values():
    root = ET.fromstring(
        f'<PageContents xmlns="{namespace[1:-1]}"><Shapes><Shape ID="1"><Text>Year {{{{year}}}}</Text></Shape></Shapes></PageContents>'
    )

    VisioFile.apply_text_context(root, {"year": 2020})

    shape = root.find(f".//{namespace}Shape")
    assert shape is not None
    text = shape.find(f"{namespace}Text")
    assert text is not None
    assert "".join(text.itertext()) == "Year 2020"


def test_insert_shape_rejects_mismatched_page_path(vsdx_copy):
    filename = vsdx_copy("test2.vsdx")
    shape = ET.fromstring(f'<Shape xmlns="{namespace[1:-1]}" ID="1" />')
    shapes = Element(f"{namespace}Shapes")

    with VisioFile(filename) as vis:
        with pytest.raises(ValueError, match="does not match"):
            vis.insert_shape(shape, shapes, vis.pages[0], "not-the-page.xml")

    assert len(shapes) == 0


def test_insert_shape_accepts_equivalent_mixed_separator_path(vsdx_copy):
    filename = vsdx_copy("test2.vsdx")
    shape = ET.fromstring(f'<Shape xmlns="{namespace[1:-1]}" ID="1" />')
    shapes = Element(f"{namespace}Shapes")

    with VisioFile(filename) as vis:
        page = vis.pages[0]
        page_path = page.filename.replace("/", "\\")
        result = vis.insert_shape(shape, shapes, page, page_path)

    assert result is shapes
    assert len(shapes) == 1


def test_insert_shape_allocates_an_id_the_page_is_not_using(vsdx_copy, tmp_path):
    """A shape inserted into a loaded page must not reuse an ID already on it.

    Nothing tells the caller to prime the page's high-water mark, so an
    allocator that trusts it hands out 1 on a page that already has a shape 1.
    Duplicate IDs make Connect records ambiguous and Visio offers to repair the
    file on open.
    """
    filename = vsdx_copy("test1.vsdx")
    out_file = os.path.join(str(tmp_path), "test1_insert_shape.vsdx")
    shape = ET.fromstring(f'<Shape xmlns="{namespace[1:-1]}" ID="1" Type="Shape" />')

    with VisioFile(filename) as vis:
        page = vis.pages[0]
        shapes = page.xml.getroot().find(f"{namespace}Shapes")
        ids_before = [s.ID for s in page.all_shapes]

        vis.insert_shape(shape, shapes, page, page.filename)

        new_id = shape.attrib["ID"]
        assert new_id not in ids_before
        ids_after = [s.ID for s in page.all_shapes]
        assert sorted(ids_after) == sorted([*ids_before, new_id])
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        ids = [s.ID for s in page.all_shapes]
        assert new_id in ids
        assert len(ids) == len(set(ids))


def test_invalid_file_type():
    """Test that opening an invalid file name results in a TypeError"""
    filename = __file__
    print(f"Opening invalid but existing {filename}")
    with pytest.raises(TypeError):
        with VisioFile(filename):
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
    with VisioFile(filename) as vis:
        assert vis.pages
        assert all(page.name for page in vis.pages)


def test_open_abs_path():
    """A package outside the tests tree opens the same way by absolute path."""
    filename = os.path.abspath(_media_filename())
    assert os.path.exists(filename)
    with VisioFile(filename) as vis:
        assert vis.pages
        assert all(page.name for page in vis.pages)


def test_page_relationship_lookup_uses_opc_path_separator():
    from vsdx.vsdxfile import _page_relationship_path

    rel_dir = "C:\\diagram/visio/pages/_rels/"
    page_path = "C:\\diagram/visio/pages/page1.xml"

    assert _page_relationship_path(rel_dir, page_path) == f"{rel_dir}page1.xml.rels"


def test_close_does_not_delete_same_stem_directory(vsdx_copy):
    filename = Path(vsdx_copy("test1.vsdx"))
    sibling = filename.with_suffix("")
    sibling.mkdir()
    marker = sibling / "keep.txt"
    marker.write_text("keep")

    vis = VisioFile(str(filename))
    vis.close_vsdx()

    assert marker.read_text() == "keep"


def test_open_abs_path_save_rel_path(tmp_path, monkeypatch):
    # test opening media file (not in tests directory)with absolute path
    media_file_path = _media_filename()
    filename = os.path.abspath(media_file_path)

    assert os.path.exists(filename)
    # the destination must stay relative, so run from tmp_path rather than naming it
    monkeypatch.chdir(tmp_path)
    output_file = "abs_to_rel_out.vsdx"
    with VisioFile(filename) as vis:
        vis.save_vsdx(output_file)
    assert (tmp_path / output_file).exists()


def test_open_abs_path_save_abs_path(tmp_path):
    # test opening media file (not in tests directory)with absolute path
    media_file_path = _media_filename()
    filename = os.path.abspath(media_file_path)

    assert os.path.exists(filename)
    output_file = os.path.abspath(os.path.join(str(tmp_path), "abs_to_abs_out.vsdx"))
    print("output_file", output_file)
    with VisioFile(filename) as vis:
        vis.save_vsdx(output_file)


# Helpers


@pytest.mark.parametrize(("filename", "shape_elements"), [("test1.vsdx", 4), ("test2.vsdx", 14), ("test3_house.vsdx", 10)])
def test_xml_findall_shapes(filename: str, shape_elements: int, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        # find all Shape elements
        xml = page.xml.getroot()
        xpath = f".//{namespace}Shape"
        elements = xml.findall(xpath)
        print(f"{xpath} returns {len(elements)} elements vs {shape_elements}")
        assert len(elements) == shape_elements


@pytest.mark.parametrize(("filename", "group_shape_elements"), [("test1.vsdx", 0), ("test2.vsdx", 3), ("test3_house.vsdx", 2)])
def test_xml_findall_group_shapes(filename: str, group_shape_elements: int, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        # find all Shape elements where attribute Type='Group'
        xml = page.xml.getroot()
        xpath = f".//{namespace}Shape[@Type='Group']"
        elements = xml.findall(xpath)
        print(f"{xpath} returns {len(elements)} elements vs {group_shape_elements}")
        assert len(elements) == group_shape_elements


# working with Pages


@pytest.mark.parametrize("filename, page_name", [("test1.vsdx", "Page-1"), ("test2.vsdx", "Page-1")])
def test_get_page(filename: str, page_name: str, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        # confirm page name as expected
        assert page.name == page_name


@pytest.mark.parametrize(
    ("filename"),
    [
        ("test1.vsdx"),
    ],
)
def test_app_xml_page_names(filename: str, basedir):
    # test that page names in app.xml matches page names loaded
    with VisioFile(os.path.join(basedir, filename)) as vis:
        HeadingPairs = vis.app_xml.getroot().find(f"{ext_prop_namespace}HeadingPairs")
        i4 = HeadingPairs.find(f".//{vt_namespace}i4")
        num_pages = int(i4.text)
        assert num_pages == len(vis.pages)

        # check page names from pages is same as page names from app.xml
        page_names = [p.name for p in vis.pages]
        TitlesOfParts = vis.app_xml.getroot().find(f"{ext_prop_namespace}TitlesOfParts")
        vector = TitlesOfParts.find(f"{vt_namespace}vector")
        app_xml_page_names = []
        for lpstr in vector.findall(f"{vt_namespace}lpstr"):
            page_name = lpstr.text
            app_xml_page_names.append(page_name)
        assert page_names == app_xml_page_names


@pytest.mark.parametrize(
    ("filename", "page_index"),
    [
        ("test1.vsdx", 0),
        ("test5_master.vsdx", 0),
    ],
)
def test_remove_page_by_index(filename: str, page_index: int, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_remove_page.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page_count = len(vis.pages)
        vis.remove_page_by_index(page_index)
        vis.save_vsdx(out_file)

    # re-open file and confirm it has one less page
    with VisioFile(out_file) as vis:
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
    with VisioFile(os.path.join(basedir, filename)) as vis:
        print(f"Found {len(vis.pages)} pages, {sorted([p.name for p in vis.pages])}")
        for page in list(vis.pages):
            print(f"page.name='{page.name}' index:{page.index_num}")
            if page_name in page.name:
                print(f"Removing page index {page.index_num}")
                vis.remove_page_by_index(page.index_num)
            else:
                expected_page_names.append(page.name)

        vis.save_vsdx(out_file)

    print(f"expected names={expected_page_names}")
    # re-open file and confirm it contains all and only those not deleted
    with VisioFile(out_file) as vis:
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
        ("test8_simple_connector.vsdx", "none"),  # no match
    ],
)
def test_remove_page_by_name(filename: str, page_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_remove_page_by_name.vsdx")
    expected_page_names = []
    with VisioFile(os.path.join(basedir, filename)) as vis:
        print(f"Found {len(vis.pages)} pages, {sorted([p.name for p in vis.pages])}")
        for page in list(vis.pages):
            print(f"page.name='{page.name}' index:{page.index_num}")
            if page_name != page.name:
                expected_page_names.append(page.name)
        vis.remove_page_by_name(page_name)
        vis.save_vsdx(out_file)

    print(f"expected names={expected_page_names}")
    # re-open file and confirm it contains all and only those not deleted
    with VisioFile(out_file) as vis:
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
    with VisioFile(os.path.join(basedir, filename)) as vis:
        vis.remove_page_by_index(remove_index)

        HeadingPairs = vis.app_xml.getroot().find(f"{ext_prop_namespace}HeadingPairs")
        i4 = HeadingPairs.find(f".//{vt_namespace}i4")
        num_pages = int(i4.text)
        assert num_pages == len(vis.pages)

        # check page names from pages is same as page names from app.xml
        page_names = [p.name for p in vis.pages]
        TitlesOfParts = vis.app_xml.getroot().find(f"{ext_prop_namespace}TitlesOfParts")
        vector = TitlesOfParts.find(f"{vt_namespace}vector")
        app_xml_page_names = []
        for lpstr in vector.findall(f"{vt_namespace}lpstr"):
            page_name = lpstr.text
            app_xml_page_names.append(page_name)
        assert page_names == app_xml_page_names


@pytest.mark.parametrize(("filename"), [("test1.vsdx")])
def test_add_page(filename: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_add_page.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        number_pages = len(vis.pages)

        new_page = vis.add_page()
        assert new_page
        assert len(vis.pages) == number_pages + 1

        new_page_name = new_page.name
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.get_page_by_name(new_page_name)
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
    with VisioFile(os.path.join(basedir, filename)) as vis:
        number_pages = len(vis.pages)

        new_page = vis.add_page(page_name)
        assert new_page
        assert len(vis.pages) == number_pages + 1

        new_page_name = new_page.name
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.get_page_by_name(new_page_name)
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
    with VisioFile(os.path.join(basedir, filename)) as vis:
        number_pages = len(vis.pages)

        new_page = vis.add_page_at(index, page_name)
        assert new_page
        assert len(vis.pages) == number_pages + 1

        new_page_name = new_page.name
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.get_page_by_name(new_page_name)
        assert page


@pytest.mark.parametrize(
    ("filename", "new_page_name", "location"),
    [
        ("test1.vsdx", "new_page", 0),
        ("test1.vsdx", "new_page", 1),
        ("test2.vsdx", "new_page", 0),
    ],
)
def test_app_xml_page_names_after_add_page(filename: str, new_page_name: str, location: int, basedir):
    # test that page names in app.xml matches page names loaded
    with VisioFile(os.path.join(basedir, filename)) as vis:
        if location is None:
            vis.add_page(new_page_name)
        else:
            vis.add_page_at(location, new_page_name)

        HeadingPairs = vis.app_xml.getroot().find(f"{ext_prop_namespace}HeadingPairs")
        i4 = HeadingPairs.find(f".//{vt_namespace}i4")
        num_pages = int(i4.text)
        assert num_pages == len(vis.pages)

        # check page names from pages is same as page names from app.xml;
        # TitlesOfParts is document metadata and does not track pages.xml
        # order, so the comparison is order-insensitive now that insertion
        # positions are actually honoured
        page_names = sorted(p.name for p in vis.pages)
        TitlesOfParts = vis.app_xml.getroot().find(f"{ext_prop_namespace}TitlesOfParts")
        vector = TitlesOfParts.find(f"{vt_namespace}vector")
        app_xml_page_names = []
        for lpstr in vector.findall(f"{vt_namespace}lpstr"):
            page_name = lpstr.text
            app_xml_page_names.append(page_name)
        assert sorted(app_xml_page_names) == page_names


def test_copy_page_clones_relationship_part(vsdx_copy, tmp_path):
    filename = vsdx_copy("test4_connectors.vsdx")
    output = tmp_path / "copied-page.vsdx"

    with VisioFile(filename) as vis:
        source = vis.pages[0]
        assert source.rels_xml is not None
        source_rels = ET.tostring(source.rels_xml.getroot())

        copied = vis.copy_page(source)

        assert copied.rels_xml is not None
        assert copied.rels_xml is not source.rels_xml
        assert ET.tostring(copied.rels_xml.getroot()) == source_rels
        assert copied.rels_xml_filename is not None
        member = copied.rels_xml_filename.removeprefix(f"{vis.directory}/")
        vis.save_vsdx(str(output))

    with zipfile.ZipFile(output) as archive:
        assert member in archive.namelist()


@pytest.mark.parametrize(
    ("filename", "index", "page_name"),
    [
        ("test1.vsdx", -1, None),
        ("test1.vsdx", 0, "newname"),
        ("test1.vsdx", 2, "Page-1"),
        ("test2.vsdx", 2, "Page-1"),
        ("test4_connectors.vsdx", 0, "Page-1"),
    ],
)
def test_copy_page(filename: str, index: int, page_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_copy_page_{page_name}.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        number_pages = len(vis.pages)

        page = vis.pages[0]  # type: Page
        new_page = vis.copy_page(page, index=index, name=page_name)
        assert new_page
        assert len(vis.pages) == number_pages + 1

        new_page_name = new_page.name
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.get_page_by_name(new_page_name)
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
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index_to_copy]  # type: Page
        new_page = vis.copy_page(page, name=in_page_name)
        print(f"in_page_name:{in_page_name} out_page_name:{out_page_name} actual:{new_page.name}")
        assert new_page.name == out_page_name  # check new page has expected name
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.get_page_by_name(out_page_name)
        assert page  # check that page name persists through file save and open


@pytest.mark.parametrize(
    ("filename", "page_index_to_copy", "page_position", "out_page_index"),
    [
        ("test1.vsdx", 0, PagePosition.LAST, 3),
        ("test1.vsdx", 0, PagePosition.BEFORE, 0),
        ("test1.vsdx", 0, PagePosition.AFTER, 1),
        ("test1.vsdx", 1, PagePosition.LAST, 3),
        ("test1.vsdx", 1, PagePosition.BEFORE, 1),
        ("test1.vsdx", 1, PagePosition.AFTER, 2),
    ],
)
def test_copy_page_positions(
    filename: str, page_index_to_copy: int, page_position: PagePosition, out_page_index: int, tmp_path, basedir
):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_copy_page_position.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index_to_copy]  # type: Page
        new_page = vis.copy_page(page, index=page_position)
        index = vis.pages.index(new_page)
        print(
            f"page_index_to_copy:{page_index_to_copy} page_position:{page_position} out_page_index:{out_page_index} "
            f"actual:{index}"
        )
        assert index == out_page_index  # check new page has expected index
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.get_page_by_name(new_page.name)
        index = vis.pages.index(page)
        assert index == out_page_index  # check that page location persists through file save and open


# working with Shapes


@pytest.mark.parametrize(("filename", "shape_name"), [("test1.vsdx", "Shape to copy"), ("test4_connectors.vsdx", "Shape B")])
def test_vis_copy_shape(filename: str, shape_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_vis_copy_shape.vsdx")

    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]  # type: Page
        # find and copy shape by name
        s = page.find_shape_by_text(shape_name)  # type: Shape
        assert s  # check shape found
        print(f"Found shape id:{s.ID}")
        max_id = max(int(existing.ID) for existing in page.all_shapes)

        # note = this does add the shape, but prefer Shape.copy() as per next test which wraps this and returns Shape
        new_shape = vis.copy_shape(shape=s.xml, page=page)

        assert isinstance(new_shape, Element)  # check copy_shape returns xml

        print(f"created new shape {type(new_shape)} {new_shape} {new_shape.attrib['ID']}")
        assert int(new_shape.attrib.get("ID")) > int(s.ID)
        assert int(new_shape.attrib.get("ID")) > max_id

        new_shape_id = new_shape.attrib["ID"]
        vis.save_vsdx(out_file)

    # re-open saved file and check it is changed as expected
    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        s = page.find_shape_by_id(new_shape_id)
        assert s


@pytest.mark.parametrize(("filename", "shape_name"), [("test1.vsdx", "Shape to copy"), ("test2.vsdx", "Shape to copy")])
def test_copy_shape_other_page(filename: str, shape_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_copy_shape_other_page.vsdx")

    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]  # type: Page
        page2 = vis.pages[1]  # type: Page
        page3 = vis.pages[2]  # type: Page
        # find and copy shape by name
        s = page.find_shape_by_text(shape_name)  # type: Shape
        assert s  # check shape found
        shape_text = s.text
        print(f"Found shape id:{s.ID}")

        new_shape = vis.copy_shape(shape=s.xml, page=page2)
        assert isinstance(new_shape, Element)  # check copy_shape returns xml
        print(f"created new shape {type(new_shape)} {new_shape} {new_shape.attrib['ID']}")
        page2_new_shape_id = new_shape.attrib["ID"]

        new_shape = vis.copy_shape(shape=s.xml, page=page3)
        assert isinstance(new_shape, Element)  # check copy_shape returns xml
        print(f"created new shape {type(new_shape)} {new_shape} {new_shape.attrib['ID']}")
        print(f"created new shape {type(new_shape)} {new_shape} {new_shape.attrib['ID']}")
        page3_new_shape_id = new_shape.attrib["ID"]

        vis.save_vsdx(out_file)

    # re-open saved file and check it is changed as expected
    with VisioFile(out_file) as vis:
        page2 = vis.pages[1]
        s = page2.find_shape_by_id(page2_new_shape_id)
        assert s
        assert s.text == shape_text
        page3 = vis.pages[2]
        s = page3.find_shape_by_id(page3_new_shape_id)
        assert s
        assert s.text == shape_text


def test_load_zip_file_contents(basedir):
    with VisioFile(os.path.join(basedir, "test1.vsdx")) as vis:
        assert vis.zip_file_contents
        assert len(vis.zip_file_contents) > 0
        for file_path, file_content in vis.zip_file_contents.items():
            print(f"file_path:{file_path} file_content:{type(file_content)}")
            assert file_content
            assert isinstance(file_content, io.BytesIO)

            # validate we can load xml
            if file_path.endswith(".xml"):
                xml = file_to_xml(file_path, vis.zip_file_contents)
                print(f"xml={type(xml)}")
                assert isinstance(xml, ET.ElementTree)
