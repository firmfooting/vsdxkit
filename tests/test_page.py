import math
import os
from datetime import datetime

import pytest

import vsdx
from vsdx import Connect, Shape, VisioFile


@pytest.mark.parametrize("filename, count", [("test1.vsdx", 1), ("test2.vsdx", 1)])
def test_get_page_shapes(filename: str, count: int, basedir):
    # there should always be one single Shapes object in the page that contains Shape objects
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        assert len(page._shapes) == count  # _shapes() is internal function to get container object


@pytest.mark.parametrize("filename, child_count", [("test1.vsdx", 4), ("test2.vsdx", 6), ("test10_nested_shapes.vsdx", 2)])
def test_get_page_child_shapes(filename: str, child_count: int, basedir):
    # Check that page has expected number of top level shapes
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        # check that page has expected number of child shapes
        assert len(page.child_shapes) == child_count


@pytest.mark.parametrize(
    "filename, all_count",
    [
        ("test1.vsdx", 4),
        ("test2.vsdx", 14),
        ("test10_nested_shapes.vsdx", 8),
    ],
)
def test_get_page_all_shapes(filename: str, all_count: int, basedir):
    # Check that page has expected number of total shapes (all_shapes searches recursively)
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        # check that page has expected number of all_shapes
        assert len(page.all_shapes) == all_count


@pytest.mark.parametrize(
    "filename, page_index, height_width",
    [
        ("test1.vsdx", 0, (8.26771653543307, 11.69291338582677)),
        ("test2.vsdx", 0, (8.26771653543307, 11.69291338582677)),
        ("test1.vsdx", 1, (8.26771653543307, 11.69291338582677)),
        ("test2.vsdx", 1, (8.26771653543307, 11.69291338582677)),
    ],
)
def test_get_page_size(filename: str, page_index: int, height_width: tuple, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index]
        print(VisioFile.pretty_print_element(page._pagesheet_xml))
        print(f"\n w x h={page.width} x {page.height}")
        assert (page.width, page.height) == height_width


@pytest.mark.parametrize(
    "filename, page_index, page_scale",
    [
        ("test1.vsdx", 0, 0.5),
        ("test2.vsdx", 0, 0.5),
        ("test1.vsdx", 1, 0.5),
        ("test2.vsdx", 1, 0.5),
    ],
)
def test_set_page_size(filename: str, page_index: int, page_scale: float, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_set_page_size_{page_index}.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index]
        # print(VisioFile.pretty_print_element(page._pagesheet_xml))
        print(f"\n w x h={page.width} x {page.height}")
        page_width = page.width * page_scale
        page_height = page.height * page_scale
        page.width = page_width
        page.height = page_height
        print(f"\n w x h={page.width} x {page.height}")
        vis.save_vsdx(out_file)

        with VisioFile(out_file) as vis:
            page = vis.pages[page_index]
            print(f"\n w x h={page.width} x {page.height}")
            assert page.width == page_width
            assert page.height == page_height


@pytest.mark.parametrize(
    "filename, page_index, expected_bounds",
    [
        (
            "test1.vsdx",
            0,
            {
                "Shape Text": (0.25, 9.868, 2.415, 11.443),
                "Shape to remove": (3.051, 9.868, 5.217, 11.443),
                "Shape to copy": (5.852, 9.868, 8.018, 11.443),
            },
        ),
        (
            "test2.vsdx",
            0,
            {
                "Shape Text": (0.0, 0.0, 2.165, 1.575),
                "Group shape text": (0.25, 9.868, 2.415, 11.443),
            },
        ),
        ("test1.vsdx", 2, {"Shape was here already": (0.645, 9.011, 2.811, 10.586)}),
        ("test2.vsdx", 2, {"Shape already here": (0.25, 9.868, 2.415, 11.443)}),
    ],
)
def test_get_page_bounds(filename: str, page_index: int, expected_bounds: dict, basedir):
    """Shape bounds must match fixture-derived absolute expectations.

    Expected values are the coordinates observed in the fixture documents;
    they pin the bounds calculation against silent zeroing or offset shifts.
    """
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index]
        assert page.all_shapes  # a bounds test needs shapes to bound

        shape_by_text = {s.text: s for s in page.all_shapes if s.text}
        assert shape_by_text, "fixture shapes carry no text to key expectations"
        for text, expected in expected_bounds.items():
            shape = shape_by_text.get(text)
            assert shape is not None, f"fixture shape {text!r} not found on page {page_index}"
            actual = tuple(round(value, 3) for value in shape.bounds)
            assert actual == expected, f"{text!r}: {actual} != {expected}"


@pytest.mark.parametrize(
    "filename, page_index, page_name",
    [
        ("test1.vsdx", 0, "Page-1"),
        ("test2.vsdx", 0, "Page-1"),
        ("test1.vsdx", 1, "Page-2"),
        ("test2.vsdx", 1, "Page-2"),
    ],
)
def test_get_page_name(filename: str, page_index: int, page_name: str, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index]
        print(VisioFile.pretty_print_element(page._pagesheet_xml))
        assert page.name == page_name


@pytest.mark.parametrize(
    "filename, page_index, page_name",
    [
        ("test1.vsdx", 0, "Page1"),
        ("test2.vsdx", 0, "Page1"),
        ("test1.vsdx", 1, "Page2"),
        ("test2.vsdx", 1, "Page2"),
    ],
)
def test_set_page_name(filename: str, page_index: int, page_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_set_page_name_{page_name}.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index]
        print(VisioFile.pretty_print_element(page._pagesheet_xml))
        page.name = page_name
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.pages[page_index]
        assert page.name == page_name


@pytest.mark.parametrize("filename, count", [("test1.vsdx", 4), ("test2.vsdx", 6)])
def test_get_page_sub_shapes(filename: str, count: int, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        shapes = page.child_shapes
        print(f"shape count={len(shapes)}")
        assert len(shapes) == count


@pytest.mark.parametrize("filename, shape_id", [("test1.vsdx", "6"), ("test2.vsdx", "6")])
def test_get_shape_with_text(filename: str, shape_id: str, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        shape = page.find_shape_by_text("{{date}}")  # type: Shape
        assert shape_id == shape.ID


@pytest.mark.parametrize("filename", ["test1.vsdx", "test2.vsdx", "test3_house.vsdx"])
def test_apply_context(filename: str, tmp_path, basedir):
    date_str = str(datetime.today().date())
    context = {"scenario": "test", "date": date_str}
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_VISfilter_applied.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        original_shape = page.find_shape_by_text("{{date}}")  # type: Shape
        assert original_shape.ID
        page.apply_text_context(context)
        vis.save_vsdx(out_file)

    # open and find date_str
    with VisioFile(out_file) as vis:
        page = vis.get_page(0)  # type: Page
        updated_shape = page.find_shape_by_text(date_str)  # type: Shape
        assert updated_shape.ID == original_shape.ID


@pytest.mark.parametrize("filename", ["test1.vsdx", "test2.vsdx", "test3_house.vsdx"])
def test_find_replace(filename: str, tmp_path, basedir):
    old = "Shape"
    new = "Figure"
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_VISfind_replace_applied.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.get_page(0)  # type: Page
        original_shapes = page.find_shapes_by_text(old)  # type: List[Shape]
        shape_ids = [s.ID for s in original_shapes]
        page.find_replace(old, new)
        vis.save_vsdx(out_file)

    # open and find date_str
    with VisioFile(out_file) as vis:
        page = vis.get_page(0)  # type: Page
        # test that each shape if has 'new' str in text
        for shape_id in shape_ids:
            shape = page.find_shape_by_id(shape_id)
            assert new in shape.text


# DataProperty


@pytest.mark.parametrize(
    ("filename", "page_index", "expected_shape_name", "property_label"),
    [
        ("test1.vsdx", 0, "Shape Text", "my_property_label"),
        ("test6_shape_properties.vsdx", 0, "Shape One", "my_property_label"),
        ("test6_shape_properties.vsdx", 0, "Shape One", "my_second_property_label"),
        ("test6_shape_properties.vsdx", 0, "Shape Three", "my_third_property_label"),
        ("test6_shape_properties.vsdx", 2, "A", "master_Prop"),
    ],
)
def test_find_shape_by_data_property_label(
    filename: str, page_index: int, expected_shape_name: str, property_label: str, basedir
):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        shape = vis.pages[page_index].find_shape_by_property_label(property_label)  # type: Shape

        # test that a shape is returned
        assert shape

        # test that returned shape has a DataProperty with property_name
        assert shape.data_properties[property_label]

        # test iot's the expected shape
        assert shape.text.replace("\n", "") == expected_shape_name


@pytest.mark.parametrize(
    ("filename", "page_index", "expected_shape_names", "property_label"),
    [
        ("test1.vsdx", 0, ["Shape Text"], "my_property_label"),
        ("test6_shape_properties.vsdx", 0, ["Shape One", "Shape Two"], "my_property_label"),
        ("test6_shape_properties.vsdx", 0, ["Shape One", "Shape Three"], "my_second_property_label"),
        ("test6_shape_properties.vsdx", 1, ["Shape A", "Shape C"], "label_one"),
        ("test6_shape_properties.vsdx", 2, ["A", "B", "C"], "master_Prop"),
    ],
)
def test_find_shapes_by_data_property_label(
    filename: str, page_index: int, expected_shape_names: list, property_label: str, basedir
):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        shapes = vis.pages[page_index].find_shapes_by_property_label(property_label)

        # test that a shape is returned
        assert len(shapes) == len(expected_shape_names)

        # get list of shape names (text) without carriage returns
        shape_names = sorted([s.text.replace("\n", "") for s in shapes])
        print(f"shape names={shape_names}")

        # test that the shapes returned have the expected names
        assert shape_names == expected_shape_names

        # test that each returned shape has a DataProperty with property_name
        for s in shapes:
            assert s.data_properties[property_label]


@pytest.mark.parametrize(
    ("filename", "page_index", "expected_shape_names", "property_label", "property_value"),
    [
        ("test1.vsdx", 0, ["Shape Text"], "my_property_label", "property value"),
        ("test6_shape_properties.vsdx", 0, ["Shape One"], "my_property_label", "property value"),
        ("test6_shape_properties.vsdx", 0, ["Shape Three"], "my_second_property_label", "a different value"),
        ("test6_shape_properties.vsdx", 1, ["Shape A", "Shape C"], "label_one", "0"),
        ("test6_shape_properties.vsdx", 2, ["A", "B"], "master_Prop", "master prop value"),
        ("test6_shape_properties.vsdx", 2, ["C"], "master_Prop", "override"),
    ],
)
def test_find_shapes_by_data_property_label_value(
    filename: str, page_index: int, expected_shape_names: list, property_label: str, property_value: str, basedir
):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        shapes = vis.pages[page_index].find_shapes_by_property_label_value(property_label, property_value)

        # test that a shape is returned
        assert len(shapes) == len(expected_shape_names)

        # get list of shape names (text) without carriage returns
        shape_names = sorted([s.text.replace("\n", "") for s in shapes])
        print(f"shape names={shape_names}")

        # test that the shapes returned have the expected names
        assert shape_names == expected_shape_names

        # test that each returned shape has a DataProperty with property_name
        for s in shapes:
            assert s.data_properties[property_label]
            print(f"{property_label}='{s.data_properties[property_label].value}'")


@pytest.mark.parametrize(
    ("filename", "page_index", "expected_shape_name", "property_label", "property_value"),
    [
        ("test1.vsdx", 0, "Shape Text", "my_property_label", "property value"),
        ("test6_shape_properties.vsdx", 0, "Shape One", "my_property_label", "property value"),
        ("test6_shape_properties.vsdx", 0, "Shape Three", "my_second_property_label", "a different value"),
        ("test6_shape_properties.vsdx", 1, "Shape A", "label_one", "0"),
        ("test6_shape_properties.vsdx", 2, "A", "master_Prop", "master prop value"),
        ("test6_shape_properties.vsdx", 2, "C", "master_Prop", "override"),
    ],
)
def test_find_shape_by_data_property_label_value(
    filename: str, page_index: int, expected_shape_name: str, property_label: str, property_value: str, basedir
):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        shape = vis.pages[page_index].find_shape_by_property_label_value(property_label, property_value)

        # test that the shapes returned have the expected names
        assert shape.text.replace("\n", "") == expected_shape_name


@pytest.mark.parametrize(
    ("filename", "page_index", "regex", "expected_shape_ids"),
    [
        ("test1.vsdx", 0, r"\s(\S{2})\s", ["2", "5", "6"]),
    ],
)
def test_find_shapes_by_regex(filename: str, page_index, regex: str, expected_shape_ids: list, basedir):
    """Test function Shape.find_shapes_by_regex(regex: str)
        test1.vsdx contains Shapes with text fields
            [(shp.ID,shp.text) for shp in shapes.all_shapes]:
            ('1', 'Shape Text\n')
            ('2', 'Shape to remove\n')
            ('5', 'Shape to copy\n')
            ('6', 'Shape for context filter: The scenario is {{scenario}} and this file was created on {{date}}\n')

    the regex matches the sequence '(whitespace)(two non-whitespace)(whitespace)' as for example with the strings ' to ' in ID=2,5 and also ' is ' and ' on ' in ID=6
    so we expect IDs=[2,5,6]
    """
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index]  # type: Page
        assert len(page.find_shapes_by_regex("")) == len(page.all_shapes)
        fil_shapes = page.find_shapes_by_regex(regex)
        assert [shp.ID for shp in fil_shapes] == expected_shape_ids


# Connectors


@pytest.mark.parametrize(
    ("filename", "expected_connects"),
    [
        ("test4_connectors.vsdx", ["from 7 to 5", "from 7 to 2", "from 6 to 2", "from 6 to 1"]),
    ],
)
def test_find_page_connects(filename: str, expected_connects: list, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]  # type: Page
        actual_connects = list()
        for c in page.connects:  # type: Connect
            actual_connects.append(f"from {c.from_id} to {c.to_id}")
        assert sorted(actual_connects) == sorted(expected_connects)


@pytest.mark.parametrize(
    ("filename", "shape_a_id", "shape_b_id", "expected_connector_ids"),
    [
        ("test4_connectors.vsdx", "1", "2", ["6"]),
        ("test4_connectors.vsdx", "1", "5", []),  # expect no connections
    ],
)
def test_find_connectors_between_ids(filename: str, shape_a_id: str, shape_b_id: str, expected_connector_ids: list, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]  # type: Page
        connectors = page.get_connectors_between(shape_a_id=shape_a_id, shape_b_id=shape_b_id)
        actual_connector_ids = sorted([c.ID for c in connectors])
        assert sorted(expected_connector_ids) == list(actual_connector_ids)


@pytest.mark.parametrize(
    ("filename", "shape_a_text", "shape_b_text", "expected_connector_ids"),
    [
        ("test4_connectors.vsdx", "Shape A", "Shape B", ["6"]),
        ("test4_connectors.vsdx", "Shape A", "Shape C", []),  # expect no connections
    ],
)
def test_find_connectors_between_shapes(
    filename: str, shape_a_text: str, shape_b_text: str, expected_connector_ids: list, basedir
):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]  # type: Page
        connectors = page.get_connectors_between(shape_a_text=shape_a_text, shape_b_text=shape_b_text)
        actual_connector_ids = sorted([c.ID for c in connectors])
        assert sorted(expected_connector_ids) == list(actual_connector_ids)


@pytest.mark.parametrize(
    ("filename", "page_index", "shape_a_text", "shape_b_text"),
    [
        ("test8_simple_connector.vsdx", 0, "Shape A", "Shape B"),
        ("test7_with_connector.vsdx", 0, "Shape Text", "Shape to remove"),
        ("test1.vsdx", 0, "Shape to remove", "Shape Text"),
        ("test1.vsdx", 0, "Shape Text", "Shape to copy"),
        ("test1.vsdx", 0, "Shape to copy", "Shape to remove"),
        ("test4_connectors.vsdx", 0, "Shape A", "Shape C"),
        ("test4_connectors.vsdx", 0, "Shape C", "Shape B"),
    ],
)
def test_add_connect_between_shapes(filename: str, page_index: int, shape_a_text: str, shape_b_text: str, tmp_path, basedir):
    out_file = os.path.join(
        str(tmp_path), f"{filename[:-5]}_test_add_connect_between_" + shape_a_text + "_" + shape_b_text + ".vsdx"
    )
    with VisioFile(os.path.join(basedir, filename)) as vis:
        print(f"filename:{out_file}")
        page = vis.pages[page_index]  # type: Page
        from_shape = page.find_shape_by_text(shape_a_text)
        to_shape = page.find_shape_by_text(shape_b_text)
        c = Connect.create(page=page, from_shape=from_shape, to_shape=to_shape)
        c.end_arrow = True
        new_connector_id = c.ID

        c.text = "NEW"
        vis.save_vsdx(out_file)

        # re-open saved file and check it is changed as expected
        with VisioFile(out_file) as vis:
            page = vis.pages[page_index]
            connector_ids = [c.connector_shape_id for c in page.connects]
            # new shape is referenced as connector_shape for new connector relationship
            assert new_connector_id in connector_ids
            # new shape exists in page
            c = page.find_shape_by_id(new_connector_id)
            assert page.find_shape_by_id(new_connector_id)


@pytest.mark.parametrize("filename", ["test8_simple_connector.vsdx", "test4_connectors.vsdx"])
def test_add_multiple_connectors(filename: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_new_test_1.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        src_page = vis.pages[0]
        block_shape = src_page.child_shapes[0]
        new_page = vis.add_page("new page")
        new_shape1 = block_shape.copy(new_page)
        new_shape1.text = "new shape 1"
        new_shape2 = block_shape.copy(new_page)
        new_shape2.text = "new shape 2"
        Connect.create(page=new_page, from_shape=new_shape1, to_shape=new_shape2)
        new_shape3 = block_shape.copy(new_page)
        new_shape3.text = "new shape 3"
        Connect.create(page=new_page, from_shape=new_shape2, to_shape=new_shape3)
        vis.save_vsdx(out_file)

    # the contract is persistence: connector shapes and their Connect records
    # must survive save/reopen, for both created connectors
    with VisioFile(out_file) as vis:
        new_page = vis.pages[-1]
        shape1 = new_page.find_shape_by_text("new shape 1")
        shape2 = new_page.find_shape_by_text("new shape 2")
        shape3 = new_page.find_shape_by_text("new shape 3")
        assert shape1 is not None and shape2 is not None and shape3 is not None
        connectors = [s for s in new_page.all_shapes if "BeginX" in s.cells]
        assert len(connectors) >= 2
        # each Connect.create() yields one connector shape with one Connect
        # record per endpoint, so group endpoints by connector and require
        # both created pairs to appear in full
        endpoints_by_connector: dict[str, set[str]] = {}
        for connect in new_page.connects:
            if connect.from_id is not None:
                endpoints_by_connector.setdefault(connect.from_id, set()).add(str(connect.to_id))
        endpoint_sets = [set(ids) for ids in endpoints_by_connector.values()]
        assert {str(shape1.ID), str(shape2.ID)} in endpoint_sets, endpoints_by_connector
        assert {str(shape2.ID), str(shape3.ID)} in endpoint_sets, endpoints_by_connector


@pytest.mark.parametrize(
    ("filename", "page_index", "shape_a_label", "shape_a_value", "shape_b_label", "shape_b_value"),
    [
        ("test1.vsdx", 0, "Network Name", "Box01", "Network Name", "Box02"),
        ("test3_house.vsdx", 0, "Network Name", "House01", "Network Name", "Box01"),
        ("test4_connectors.vsdx", 2, "Network Name", "Box01", "Network Name", "Box02"),
        ("test4_connectors.vsdx", 2, "Network Name", "Box01", "Network Name", "Router01"),
        ("test4_connectors.vsdx", 2, "Network Name", "Switch01", "Network Name", "Router01"),
    ],
)
def test_add_connect_between_shapes_by_property(
    filename: str,
    page_index: int,
    shape_a_label: str,
    shape_a_value,
    shape_b_label: str,
    shape_b_value: str,
    tmp_path,
    basedir,
):
    out_file = os.path.join(
        str(tmp_path), f"{filename[:-5]}_test_add_connect_between_labels_" + shape_a_value + "_" + shape_b_value + ".vsdx"
    )
    with VisioFile(os.path.join(basedir, filename)) as vis:
        print(f"filename:{out_file}")
        page = vis.pages[page_index]  # type: Page
        from_shape = page.find_shape_by_property_label_value(shape_a_label, shape_a_value)
        to_shape = page.find_shape_by_property_label_value(shape_b_label, shape_b_value)

        c = Connect.create(page=page, from_shape=from_shape, to_shape=to_shape)
        c.end_arrow = True
        new_connector_id = c.ID

        c.text = "NEW"
        vis.save_vsdx(out_file)

        # re-open saved file and check it is changed as expected
        with VisioFile(out_file) as vis:
            page = vis.pages[page_index]
            connector_ids = [c.connector_shape_id for c in page.connects]
            # new shape is referenced as connector_shape for new connector relationship
            assert new_connector_id in connector_ids
            # new shape exists in page
            c = page.find_shape_by_id(new_connector_id)
            assert page.find_shape_by_id(new_connector_id)


def _only(page, matching) -> Shape:
    """The one shape on the page that `matching` accepts."""
    found = [shape for shape in page.all_shapes if matching(shape)]
    assert len(found) == 1, f"expected one matching shape, the page has {[s.text for s in page.all_shapes]}"
    return found[0]


@pytest.mark.parametrize(
    ("filename", "shape_text", "lx", "ly"),
    [
        ("test9_rect_and_line.vsdx", "Rect A", 2.0, 8.0),
        ("test9_rect_and_line.vsdx", "Line A", 2.0, 8.0),
        ("test9_rect_and_line.vsdx", "Conn A", 2.0, 8.0),
        ("test9_rect_and_line.vsdx", "Rect A", 2.0, 5.0),
        ("test9_rect_and_line.vsdx", "Line A", 2.0, 5.0),
        ("test9_rect_and_line.vsdx", "Conn A", 2.0, 5.0),
    ],
)
def test_copy_and_move_shape(filename: str, shape_text: str, lx: float, ly: float, tmp_path, basedir):
    """The copy goes where it was put, and the original stays where it was.

    A 2-D shape is put there by its pin; a 1-D one by its endpoints, and its pin
    then follows from them.

    There was no assertion in here at all. Its only oracle was the autouse
    structural validator, which says the package is not broken rather than that
    anything moved.
    """
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_copy_and_move_shape_{shape_text}_{lx}_{ly}.vsdx")
    marker = f" moved to {lx},{ly}"
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]  # type: Page
        shape = page.find_shape_by_text(shape_text)
        original_bounds = shape.bounds
        one_dimensional = shape.begin_x is not None

        cp1 = shape.copy()
        cp1.x, cp1.y = lx, ly
        cp1.text = cp1.text + marker
        if one_dimensional:
            cp1.begin_x, cp1.begin_y = lx, ly
            cp1.end_x, cp1.end_y = lx + cp1.width, ly + cp1.height
            cp1.x, cp1.y = cp1.center_x_y

        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        page = vis.pages[0]
        copy = _only(page, lambda shape: marker in shape.text)
        if one_dimensional:
            assert (copy.begin_x, copy.begin_y) == pytest.approx((lx, ly))
            assert (copy.end_x, copy.end_y) == pytest.approx((lx + copy.width, ly + copy.height))
            assert (copy.x, copy.y) == pytest.approx(copy.center_x_y)
        else:
            assert (copy.x, copy.y) == pytest.approx((lx, ly))

        original = _only(page, lambda shape: shape_text in shape.text and marker not in shape.text)
        assert original.bounds == pytest.approx(original_bounds), "copying the shape moved the original"


@pytest.mark.parametrize(
    ("filename", "shape_text", "start", "finish"),
    [
        ("test9_rect_and_line.vsdx", "Line A", (2.0, 7.0), (3.0, 8.0)),
        ("test9_rect_and_line.vsdx", "Conn A", (2.0, 7.0), (3.0, 8.0)),
    ],
)
def test_copy_and_move_line(filename: str, shape_text: str, start: tuple, finish: tuple, tmp_path, basedir):
    """A copied 1-D shape is placed by its endpoints, and its geometry follows them.

    There was no assertion in here either, and both parameter rows are 1-D
    shapes, so the `if cp1.begin_x is not None` the body hung on was never
    false.
    """
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_copy_and_move_line_{shape_text}_{start}_{finish}.vsdx")
    marker = f" moved to {start}-{finish}"
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[0]  # type: Page
        shape = page.find_shape_by_text(shape_text)
        assert shape.begin_x is not None, f"{shape_text!r} is not a 1-D shape"
        is_connector = shape.shape_name == "Dynamic connector"

        cp1 = shape.copy()
        cp1.text = cp1.text + marker
        cp1.begin_x, cp1.begin_y = start
        cp1.end_x, cp1.end_y = finish
        cp1.width = cp1.end_x - cp1.begin_x
        # a connector spans both axes; a line carries its slope in its geometry
        # and is zero high
        cp1.height = cp1.end_y - cp1.begin_y if is_connector else 0.0
        cp1.geometry.set_move_to(0.0, 0.0)
        cp1.geometry.set_line_to(cp1.width, cp1.height)

        txt_pin_x = cp1.cells.get("TxtPinX")
        txt_pin_y = cp1.cells.get("TxtPinY")
        if txt_pin_x and txt_pin_y:
            if is_connector:
                txt_pin_x.value, txt_pin_y.value = cp1.width / 2, cp1.height / 2
            else:
                txt_pin_x.value, txt_pin_y.value = cp1.center_x_y
            cp1.set_cell_value(name="Control/TextPosition/X", value=txt_pin_x.value)
            cp1.set_cell_value(name="Control/TextPosition/Y", value=txt_pin_y.value)
            cp1.set_cell_value(name="Control/TextPosition/XDyn", value=txt_pin_x.value)
            cp1.set_cell_value(name="Control/TextPosition/YDyn", value=txt_pin_y.value)

        # Cells that hold a formula still carry the value they were written
        # with, so every one is re-evaluated against the shape as it now is.
        cells = list(cp1.cells.values()) + cp1.geometry.cells
        for row in cp1.geometry.rows.values():
            cells.extend(row.cells.values())
        for cell in cells:  # type: Cell
            formula = cell.formula
            if not formula:
                continue
            if formula == "Inh" and cp1.master_shape:
                master_cell = cp1.master_shape.cells.get(cell.name)
                formula = master_cell.formula if master_cell else formula
            value = vsdx.calc_value(cp1, formula)
            if value is not None:
                cell.value = value

        vis.save_vsdx(out_file)

    span_x, span_y = finish[0] - start[0], finish[1] - start[1]
    with VisioFile(out_file) as vis:
        copy = _only(vis.pages[0], lambda shape: marker in shape.text)
        assert (copy.begin_x, copy.begin_y) == pytest.approx(start)
        assert (copy.end_x, copy.end_y) == pytest.approx(finish)

        # A connector's box is the bounding box of its route; a line is zero
        # high and as wide as it is long, its slope carried by the geometry
        # rather than by its height. Both are what the loop above computed, from
        # the endpoints, over cells the test never assigned.
        assert (copy.x, copy.y) == pytest.approx(((start[0] + finish[0]) / 2, (start[1] + finish[1]) / 2))
        width, height = (span_x, span_y) if is_connector else (math.hypot(span_x, span_y), 0.0)
        assert (copy.width, copy.height) == pytest.approx((width, height))

        # the drawn line has to agree with the endpoints, or the shape reports
        # one position and paints another
        rows = [(str(row.row_type).lower(), row.x, row.y) for row in copy.geometry.rows.values()]
        assert [(kind, x, pytest.approx(y)) for kind, x, y in rows] == [
            ("moveto", pytest.approx(0.0), pytest.approx(0.0)),
            ("lineto", pytest.approx(width), pytest.approx(height)),
        ], rows


@pytest.mark.parametrize(
    "filename, page_index, expected_ids",
    [
        ("test1.vsdx", 0, ["1", "2", "5", "6"]),
        ("test1.vsdx", 1, []),  # empty page
        ("test1.vsdx", 2, ["1"]),
        ("test2.vsdx", 0, ["6", "9", "1", "7", "8", "11", "2", "10", "14", "5", "12", "13", "16", "17"]),
        ("test2.vsdx", 1, []),  # empty page
        ("test2.vsdx", 2, ["1", "2", "3", "4"]),
    ],
)
def test_page_all_shapes(filename, page_index, expected_ids, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index]
        # all_shapes() gets all shapes on a page, recursively
        shape_ids = [s.ID for s in page.all_shapes]
        print(shape_ids)
        assert shape_ids == expected_ids


@pytest.mark.parametrize(
    "filename, page_index, expected_page_id",
    [
        ("test1.vsdx", 0, "0"),
        ("test1.vsdx", 1, "4"),
        ("test1.vsdx", 2, "7"),
        ("test2.vsdx", 0, "0"),
        ("test2.vsdx", 1, "4"),
        ("test2.vsdx", 2, "5"),
        ("test4_connectors.vsdx", 0, "0"),
        ("test4_connectors.vsdx", 1, "4"),
        ("test4_connectors.vsdx", 2, "7"),
    ],
)
def test_page_id(filename, page_index, expected_page_id, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.pages[page_index]
        assert page.page_id == expected_page_id


@pytest.mark.parametrize(
    "filename, master_index, expected_page_id",
    [
        ("test3_house.vsdx", 0, "2"),
        ("test5_master.vsdx", 0, "1"),
        ("test4_connectors.vsdx", 0, "2"),
        ("test4_connectors.vsdx", 1, "6"),
        ("test4_connectors.vsdx", 2, "7"),
    ],
)
def test_master_page_id(filename, master_index, expected_page_id, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        page = vis.master_pages[master_index]
        assert page.page_id == expected_page_id


@pytest.mark.parametrize(
    "filename",
    [
        ("test1.vsdx"),
        ("test2.vsdx"),
        ("test4_connectors.vsdx"),
    ],
)
def test_page_has_page_sheet_xml(filename, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        for page in vis.pages:
            assert page._pagesheet_xml is not None


@pytest.mark.parametrize(
    "filename",
    [
        ("test3_house.vsdx"),
        ("test5_master.vsdx"),
        ("test4_connectors.vsdx"),
    ],
)
def test_master_page_has_sheet_xml(filename, basedir):
    with VisioFile(os.path.join(basedir, filename)) as vis:
        for page in vis.master_pages:
            print(page.page_id, page.name)
            assert page._pagesheet_xml is not None
