"""Tests for Shape class"""

import os
import xml.etree.ElementTree as ET

import pytest
from helpers.connect_records import records_naming

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.shapes import DataProperty, Shape


def _first_shape_containing(shapes, text: str):
    """The first shape whose text contains `text`, as the retired substring finders matched."""
    return next((shape for shape in shapes if text in shape.text), None)


@pytest.mark.parametrize(
    "filename, shape_id, expected_text",
    [
        ("test3_house.vsdx", "1", "Shape Text"),
        ("test3_house.vsdx", "11", "Shape to remove"),
        ("test2.vsdx", "9", "Group shape text"),
        ("test10_nested_shapes.vsdx", "5", "Shape 1.2.1"),
        ("test_master_multiple_child_shapes.vsdx", "3", "AWS Step Functions workflow "),
    ],
)
def test_get_shape_text(filename: str, shape_id: str, expected_text: str, basedir):
    # Check that a specific shape on a page has expected text value
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    shape = page.shapes.require_id(shape_id)
    # check that shape has expected text
    assert shape.text == expected_text


@pytest.mark.parametrize(
    "filename, shape_id, expected_text",
    [
        ("test3_house.vsdx", "1", "Shape Text"),
        ("test3_house.vsdx", "11", "Shape to remove"),
        ("test2.vsdx", "9", "Group shape text"),
        ("test10_nested_shapes.vsdx", "5", "Shape 1.2.1"),
    ],
)
def test_set_shape_text(filename: str, shape_id: str, expected_text: str, basedir):
    # Check that a specific shape on a page has expected text value after it is updated
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    shape = page.shapes.require_id(shape_id)
    # check that shape has expected text
    assert shape.text == expected_text
    shape.text = expected_text + "changed"
    shape = page.shapes.require_id(shape_id)
    assert shape.text == expected_text + "changed"


@pytest.mark.parametrize(
    "filename, attr, attr_value, expected_id",
    [
        ("test3_house.vsdx", "NameU", "House", "7"),
    ],
)
def test_get_shape_attr_value(filename: str, attr: str, attr_value: str, expected_id: str, basedir):
    # Check that a specific shape on a page has expected text value
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    shape = next((s for s in page.shapes if str(s.xml.attrib.get(attr)) == attr_value), None)
    # check that shape has expected text
    assert expected_id == shape.ID


@pytest.mark.parametrize(
    "filename, shape_id, child_count",
    [
        ("test3_house.vsdx", "7", 3),
        ("test3_house.vsdx", "11", 3),
        ("test2.vsdx", "9", 3),
        ("test10_nested_shapes.vsdx", "7", 2),
    ],
)
def test_get_shape_child_shapes(filename: str, shape_id: str, child_count: int, basedir):
    # Check that page has expected number of top level shapes
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    shape = page.shapes.require_id(shape_id)

    # check that page has expected number of child shapes
    assert len(shape.children) == child_count


@pytest.mark.parametrize(
    "filename, shape_id, all_count",
    [
        ("test3_house.vsdx", "7", 3),
        ("test3_house.vsdx", "11", 3),
        ("test2.vsdx", "9", 3),
        ("test10_nested_shapes.vsdx", "7", 6),
    ],
)
def test_get_shape_all_shapes(filename: str, shape_id: str, all_count: int, basedir):
    # Check that page has expected number of top level shapes
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page

    shape_group = page.shapes.require_id(shape_id)
    for shape in shape_group.descendants:
        print(shape)
    # check that page has expected number of child shapes
    assert len(shape_group.descendants) == all_count


@pytest.mark.parametrize(
    "filename, expected_locations",
    [
        ("test1.vsdx", "1.33,10.66 4.13,10.66 6.94,10.66 2.33,9.02 "),
        ("test2.vsdx", "2.33,8.72 1.33,10.66 4.13,10.66 5.91,8.72 1.61,8.58 3.25,8.65 "),
    ],
)
def test_shape_locations(filename: str, expected_locations: str, basedir):
    print("=== list_shape_locations ===")
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    shapes = list(page.children)
    locations = ""
    for shape in shapes:  # type: Shape
        locations += f"{shape.x:.2f},{shape.y:.2f} "
    print(f"Expected:{expected_locations}")
    print(f"  Actual:{locations}")
    assert locations == expected_locations


@pytest.mark.parametrize(
    "filename, shape_id, expected_center",
    [
        ("test1.vsdx", "1", (1.332677148526936, 10.65551182326173)),
        ("test2.vsdx", "2", (1.082677148526936, 0.7874015625650443)),  # center of a group shape
        ("test2.vsdx", "16", (1.6903102768832179, 8.188976116607332)),  # test center of a line
    ],
)
def test_shape_center(filename: str, shape_id: str, expected_center: str, basedir):

    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    shape = page.shapes.require_id(shape_id)

    assert shape.center_x_y == expected_center


@pytest.mark.parametrize("filename", ["test2.vsdx", "test3_house.vsdx"])
def test_remove_shape(filename: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_shape_removed.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    # get shape to remove
    shape = vis.pages[0].shapes.by_text("Shape to remove")  # type: Shape
    assert shape  # check shape found
    shape.delete()
    vis.save(out_file)

    vis = Document.open(out_file)
    # get shape that should have been removed
    shape = vis.pages[0].shapes.by_text("Shape to remove")  # type: Shape
    assert shape is None  # check shape not found


@pytest.mark.parametrize(("filename", "shape_names", "shape_locations"), [("test1.vsdx", {"Shape to remove"}, {(1.0, 1.0)})])
def test_set_shape_location(filename: str, shape_names: set, shape_locations: set, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_set_shape_location.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    # move shapes in list
    for shape_name, x_y in zip(shape_names, shape_locations, strict=True):
        shape = vis.pages[0].shapes.by_text(shape_name)  # type: Shape
        assert shape  # check shape found
        assert shape.x
        assert shape.y
        print(f"Moving shape '{shape_name}' from {shape.x}, {shape.y} to {x_y}")
        shape.x = x_y[0]
        shape.y = x_y[1]
    vis.save(out_file)

    # re-open saved file and check it is changed as expected
    vis = Document.open(out_file)
    # get each shape that should have been moved
    for shape_name, x_y in zip(shape_names, shape_locations, strict=True):
        shape = vis.pages[0].shapes.by_text(shape_name)  # type: Shape
        assert shape  # check shape found
        assert shape.x == x_y[0]
        assert shape.y == x_y[1]


@pytest.mark.parametrize(
    ("filename", "page_index", "shape_names", "shape_x_y_deltas"),
    [
        ("test1.vsdx", 0, {"Shape to remove"}, {(1.0, 1.0)}),
        ("test4_connectors.vsdx", 0, {"Shape B"}, {(1.0, 1.0)}),
        ("test4_connectors.vsdx", 1, {"B to C"}, {(1.0, 1.0)}),
    ],
)
def test_move_shape(filename: str, page_index: int, shape_names: set, shape_x_y_deltas: set, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_move_shape.vsdx")
    expected_shape_locations = {}

    vis = Document.open(os.path.join(basedir, filename))
    # move shapes in list
    for shape_name, x_y in zip(shape_names, shape_x_y_deltas, strict=True):
        shape = vis.pages[page_index].shapes.by_text(shape_name)  # type: Shape
        assert shape  # check shape found
        assert shape.x
        assert shape.y
        expected_shape_locations[shape_name] = (shape.x + x_y[0], shape.y + x_y[1])
        shape.move(x_y[0], x_y[1])

    vis.save(out_file)
    print(f"expected_shape_locations={expected_shape_locations}")

    # re-open saved file and check it is changed as expected
    vis = Document.open(out_file)
    # get each shape that should have been moved
    for shape_name in shape_names:
        shape = vis.pages[page_index].shapes.by_text(shape_name)  # type: Shape
        assert shape  # check shape found
        assert shape.x == expected_shape_locations[shape_name][0]
        assert shape.y == expected_shape_locations[shape_name][1]


@pytest.mark.parametrize(("filename", "shape_name"), [("test1.vsdx", "Shape to copy"), ("test4_connectors.vsdx", "Shape B")])
def test_shape_copy(filename: str, shape_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_shape_copy.vsdx")

    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    # find and copy shape by name
    shape = page.shapes.by_text(shape_name)  # type: Shape
    assert shape  # check shape found
    print(f"found {shape.ID}")
    max_id = max(int(existing.ID) for existing in page.shapes)

    new_shape = shape.copy()
    assert new_shape  # check new shape exists

    print(f"original shape {type(shape)} {shape} {shape.ID}")
    print(f"created new shape {type(new_shape)} {new_shape} {new_shape.ID}")
    assert int(new_shape.ID) > int(shape.ID)  # and new shape has > ID than original
    assert int(new_shape.ID) > max_id
    updated_text = shape.text + " (new copy)"
    new_shape.text = updated_text  # update text of new shape
    assert page.shapes.by_text(updated_text)
    new_shape_id = new_shape.ID
    vis.save(out_file)

    # re-open saved file and check it is changed as expected
    vis = Document.open(out_file)
    page = vis.pages[0]
    shape = page.shapes.require_id(new_shape_id)
    assert shape
    # check that new shape has expected text
    assert shape.text == updated_text


@pytest.mark.parametrize(("filename", "shape_name"), [("test1.vsdx", "Shape to copy"), ("test2.vsdx", "Shape to copy")])
def test_shape_copy_other_page(filename: str, shape_name: str, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_shape_copy_other_page.vsdx")

    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    page2 = vis.pages[1]  # type: Page
    page3 = vis.pages[2]  # type: Page
    # find and copy shape by name
    shape = page.shapes.by_text(shape_name)  # type: Shape
    assert shape  # check shape found
    shape_text = shape.text
    print(f"Found shape id:{shape.ID}")

    new_shape = shape.copy(page2)
    assert new_shape  # check copy_shape returns xml
    print(f"created new shape {type(new_shape)} {new_shape} {new_shape.ID}")
    page2_new_shape_id = new_shape.ID

    new_shape = shape.copy(page3)
    assert new_shape  # check copy_shape returns xml
    print(f"created new shape {type(new_shape)} {new_shape} {new_shape.ID}")
    page3_new_shape_id = new_shape.ID

    vis.save(out_file)

    # re-open saved file and check it is changed as expected
    vis = Document.open(out_file)
    page2 = vis.pages[1]
    shape = page2.shapes.require_id(page2_new_shape_id)
    assert shape
    assert shape.text == shape_text
    page3 = vis.pages[2]
    shape = page3.shapes.require_id(page3_new_shape_id)
    assert shape
    assert shape.text == shape_text


# DataProperty


@pytest.mark.parametrize(
    ("filename", "page_index", "shape_name"), [("test1.vsdx", 0, "Shape Text"), ("test6_shape_properties.vsdx", 2, "A")]
)
def test_get_shape_data_properties_type_is_dict_of_data_property(filename: str, page_index: int, shape_name: str, basedir):
    """check that Shape.data_properties is a dict of ShapeProperty"""
    vis = Document.open(os.path.join(basedir, filename))
    shape = vis.pages[page_index].shapes.by_text(shape_name)  # type: Shape

    props = shape.data_properties

    # check overall type
    assert isinstance(props, dict)

    # check each item type
    for prop in props.values():
        assert isinstance(prop, DataProperty)


@pytest.mark.parametrize(
    ("filename", "page_index", "shape_name", "property_dict"),
    [
        (
            "test1.vsdx",
            0,
            "Shape Text",
            {"my_property_label": "property value", "my_second_property_label": "another value", "Network Name": "Box01"},
        ),
        ("test6_shape_properties.vsdx", 2, "A", {"master_Prop": "master prop value"}),
        ("test6_shape_properties.vsdx", 2, "B", {"master_Prop": "master prop value", "shape_prop": "shape property value"}),
        ("test6_shape_properties.vsdx", 2, "C", {"master_Prop": "override"}),
        ("test6_shape_properties.vsdx", 2, "D", {"LongProp": 'value not in an "attrib"'}),
    ],
)
def test_get_shape_data_properties(filename: str, page_index: int, shape_name: str, property_dict: dict, basedir):
    vis = Document.open(os.path.join(basedir, filename))
    shape = vis.pages[page_index].shapes.by_text(shape_name)  # type: Shape

    props = shape.data_properties
    print(props)
    # check lengths are same
    assert len(props) == len(property_dict)

    # check each key/value is same as expected
    for property_label in props:
        prop = props[property_label]
        print(f"prop: lbl:'{prop.label}' name:'{prop.name}': val:'{prop.value}'")
        assert prop.value == property_dict.get(property_label)


@pytest.mark.parametrize(
    ("filename", "page_index", "shape_name", "property_dict"),
    [
        ("test1.vsdx", 0, "Shape Text", {"my_property_label": "1", "my_second_property_label": "2", "Network Name": "3"}),
        ("test6_shape_properties.vsdx", 2, "A", {"master_Prop": "1"}),
        ("test6_shape_properties.vsdx", 2, "B", {"master_Prop": "1", "shape_prop": "2"}),
        ("test6_shape_properties.vsdx", 2, "C", {"master_Prop": "1"}),
        ("test6_shape_properties.vsdx", 2, "D", {"LongProp": '1"'}),
        ("test6_shape_properties.vsdx", 2, "E", {"empty_prop": "E1"}),
        # ("test_shape_with_field.vsdx", 0, "Here is field", {"field_label": 'updated field value'}),
    ],
)
def test_set_shape_data_properties(filename: str, page_index: int, shape_name: str, property_dict: dict, tmp_path, basedir):
    """Check that we can set a prop value, and this change persists through save and load"""
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_set_shape_data_properties.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    shape = vis.pages[page_index].shapes.by_text(shape_name)

    props = shape.data_properties

    # check each key/value is not already set to required value
    for property_label in property_dict:
        prop = props[property_label]
        print(f"prop: lbl:'{prop.label}' name:'{prop.name}': val:'{prop.value}'")
        assert prop.value != property_dict.get(property_label)
        print(f"shape.text={shape.text}")
        print(vis.pretty_print_element(shape.xml))

    # check each key/value is expected after being set
    for property_label in property_dict:
        prop = props[property_label]
        prop.value = property_dict.get(property_label)
        print(f"checking prop after set: lbl:'{prop.label}' name:'{prop.name}': val:'{prop.value}'")
        assert prop.value == property_dict.get(property_label)

    vis.save(out_file)

    # re-open saved file and check it is changed as expected
    vis = Document.open(out_file)
    shape = vis.pages[page_index].shapes.by_text(shape_name)  # type: Shape
    # check each key/value is not already set to required value
    for property_label in property_dict:
        prop = props[property_label]
        print(f"checking prop after load: lbl:'{prop.label}' name:'{prop.name}': val:'{prop.value}'")
        assert prop.value == property_dict.get(property_label)
        # check that Value doesn't contain a 'F="No Formula"' attribute
        assert prop.get_attribute("Value", "F") != "No Formula"


@pytest.mark.parametrize(
    ("filename", "page_index", "container_shape_name", "expected_shape_name", "property_label"),
    [
        ("test6_shape_properties.vsdx", 1, "Container", "Shape A", "label_one"),
    ],
)
def test_find_sub_shape_by_data_property_label(
    filename: str, page_index: int, container_shape_name: str, expected_shape_name: list, property_label: str, basedir
):
    """Test that we can find a shape and it's text inside a container shape based on the sub shapes labels"""
    vis = Document.open(os.path.join(basedir, filename))
    container_shape = vis.pages[page_index].shapes.by_text(container_shape_name)

    shape = container_shape.descendants.by_property(property_label)

    # test that a shape is returned
    assert shape

    # test that the shape returned has the expected names
    assert shape.text.replace("\n", "") == expected_shape_name


@pytest.mark.parametrize(
    ("filename", "page_index", "property_label", "expected_shape_text"),
    [("test_master_multiple_child_shapes.vsdx", 0, "title", "AWS Step Functions workflow ")],
)
def test_find_shape_by_data_property_label(
    filename: str, page_index: int, property_label: str, expected_shape_text: str, basedir
):
    """Test that we can find a shape and it's text inside a page based on the shapes labels"""
    vis = Document.open(os.path.join(basedir, filename))
    shape = vis.pages[page_index].shapes.by_property(property_label)

    # test that a shape is returned
    assert shape

    # test that shape has a DataProperty with expected property label
    assert [prop for prop in shape.data_properties.values() if prop.label == property_label]

    # test that the shape returned has the expected text
    assert shape.text.replace("\n", "") == expected_shape_text


# Connectors


@pytest.mark.parametrize(
    ("filename", "shape_id", "expected_shape_ids"),
    [
        ("test4_connectors.vsdx", "1", ["2"]),
        ("test4_connectors.vsdx", "2", ["1", "5"]),
    ],
)
def test_find_connected_shapes(filename: str, shape_id: str, expected_shape_ids: list, basedir):
    """The shapes at the other end of each connector glued to the shape: 6 runs 1 to 2, and 7 runs 5 to 2."""
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page
    actual_connect_shape_ids = list()
    shape = page.shapes.require_id(shape_id)
    for c_shape in shape.connected_shapes:  # type: Shape
        actual_connect_shape_ids.append(c_shape.ID)
    assert sorted(actual_connect_shape_ids) == sorted(expected_shape_ids)


@pytest.mark.parametrize(
    ("filename", "shape_id", "expected_shape_ids", "expected_from", "expected_to", "expected_from_rels", "expected_to_rels"),
    [
        ("test4_connectors.vsdx", "1", ["2"], ["6"], ["1"], ["BeginX"], ["PinX"]),
        ("test4_connectors.vsdx", "2", ["1", "5"], ["6", "7"], ["2", "2"], ["BeginX", "EndX"], ["PinX", "PinX"]),
        # nothing is glued to a connector, so it is connected to nothing, though its own records name it
        ("test4_connectors.vsdx", "6", [], ["6", "6"], ["1", "2"], ["BeginX", "EndX"], ["PinX", "PinX"]),
        ("test4_connectors.vsdx", "7", [], ["7", "7"], ["5", "2"], ["BeginX", "EndX"], ["PinX", "PinX"]),
    ],
)
def test_find_connected_shape_relationships(
    filename: str,
    shape_id: str,
    expected_shape_ids: list,
    expected_from: list,
    expected_to: list,
    expected_from_rels: list,
    expected_to_rels: list,
    basedir,
):
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]  # type: Page

    shape = page.shapes.require_id(shape_id)
    shape_ids = [s.ID for s in shape.connected_shapes]
    from_ids = [c.from_id for c in records_naming(shape)]
    to_ids = [c.to_id for c in records_naming(shape)]
    from_rels = [c.from_rel for c in records_naming(shape)]
    to_rels = [c.to_rel for c in records_naming(shape)]

    assert sorted(shape_ids) == sorted(expected_shape_ids)
    assert sorted(from_ids) == sorted(expected_from)
    assert sorted(to_ids) == sorted(expected_to)
    assert sorted(from_rels) == sorted(expected_from_rels)
    assert sorted(to_rels) == sorted(expected_to_rels)


@pytest.mark.parametrize(
    "filename, page_index, shape_text, expected_coords",
    [
        (
            "test7_with_connector.vsdx",
            0,
            "Tall Box",
            [
                ("RelMoveTo", [("X", "0", None), ("Y", "0", None)]),
                ("RelLineTo", [("X", "1", None), ("Y", "0", None)]),
                ("RelLineTo", [("X", "1", None), ("Y", "1", None)]),
                ("RelLineTo", [("X", "0", None), ("Y", "1", None)]),
                ("RelLineTo", [("X", "0", None), ("Y", "0", None)]),
            ],
        ),
        (
            "test1.vsdx",
            0,
            "Shape Text",
            [
                ("RelMoveTo", [("X", "0", None), ("Y", "0", None)]),
                ("RelLineTo", [("X", "1", None), ("Y", "0", None)]),
                ("RelLineTo", [("X", "1", None), ("Y", "1", None)]),
                ("RelLineTo", [("X", "0", None), ("Y", "1", None)]),
                ("RelLineTo", [("X", "0", None), ("Y", "0", None)]),
            ],
        ),
        (
            "test2.vsdx",
            2,
            "Already here",
            [
                (
                    "Ellipse",
                    [
                        ("X", "0.2460629842730571", "Width*0.5"),
                        ("Y", "0.2519684958956088", "Height*0.5"),
                        ("A", "0.4921259685461141", "Width*1"),
                        ("B", "0.2519684958956088", "Height*0.5"),
                        ("C", "0.2460629842730571", "Width*0.5"),
                        ("D", "0.5039369917912175", "Height*1"),
                    ],
                )
            ],
        ),
        (
            "test4_connectors.vsdx",
            1,
            "A to B",
            [
                ("MoveTo", [("X", "0", None), ("Y", "0.09842519685039441", None)]),
                ("LineTo", [("X", "0.6358267353988465", None), ("Y", "0.09842519685039441", None)]),
            ],
        ),
    ],
)
def test_get_shape_geometry(filename: str, page_index: str, shape_text: str, expected_coords: list, basedir):
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[page_index]
    shape = page.shapes.by_text(shape_text)

    coords = [(r.row_type, [(c.name, c.value, c.func) for c in r.cells.values()]) for r in shape.geometry.rows.values()]
    print(f"coords={coords}")
    print(Document.pretty_print_element(shape.xml))
    if shape.master_shape:
        print(Document.pretty_print_element(shape.master_shape.xml))
    assert coords == expected_coords


@pytest.mark.parametrize("filename_2", ["test1.vsdx", "test2.vsdx"])
def test_shapes_of_two_documents_are_never_equal(filename_2, basedir):
    """Fails if a shape equals one in another document: two opens of one file are two documents (#101)."""
    vis = Document.open(os.path.join(basedir, "test1.vsdx"))
    shape_1 = vis.pages[0].shapes.by_text("Shape Text")

    vis = Document.open(os.path.join(basedir, filename_2))
    shape_2 = vis.pages[0].shapes.by_text("Shape Text")

    assert shape_1 != shape_2


@pytest.mark.parametrize(
    "filename, page_index, shape_text, expected_bounds",
    [
        ("test1.vsdx", 0, "Shape Text", ["0.25", "9.87", "2.42", "11.44"]),  # standard shape
        ("test2.vsdx", 0, "Sub-shape 2", ["0.54", "0.17", "1.62", "0.51"]),  # sub shape in a group
        ("test2.vsdx", 0, "Scenario:", ["0.73", "8.19", "2.49", "8.97"]),  # line
    ],
)
def test_shape_bounds(filename, page_index, shape_text, expected_bounds, basedir):
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[page_index]
    shape = _first_shape_containing(page.shapes, shape_text)
    print([f"{n:.2f}" for n in shape.bounds])
    assert [f"{n:.2f}" for n in shape.bounds] == expected_bounds


@pytest.mark.parametrize(
    "filename, page_index",
    [
        ("test1.vsdx", 0),
        ("test1.vsdx", 2),
        ("test2.vsdx", 0),
        # 1-D shapes, whose boxes are degenerate on purpose: a horizontal line
        # is zero high, and a right-to-left one has its end left of its begin
        ("test4_connectors.vsdx", 0),
        ("test5_master.vsdx", 0),
        ("test7_with_connector.vsdx", 0),
    ],
)
def test_all_shape_bounds(filename, page_index, basedir):
    """Every shape on the page has a box, and knows where its group put it.

    `assert shape.bounds` and `assert shape.relative_bounds` were the whole of
    this test, and a 4-tuple is always truthy: hard-coding `Shape.bounds` to
    `0.0, 0.0, 0.0, 0.0` left all three parameter cases passing.
    `test_shape_bounds` pins exact coordinates for three named shapes; this one
    is for the shapes nobody named, so it asserts what holds of all of them.

    Not that the box is non-empty. `bounds` comes from the endpoints on a 1-D
    shape, and a horizontal line is zero high while a right-to-left one ends
    left of where it begins - 8 of the 146 shapes in this corpus are one or the
    other. An assertion those fail is one that fails a correct library, which is
    how it ends up deleted.
    """
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[page_index]
    shapes = list(page.shapes)
    assert shapes, "a bounds test needs shapes to bound"
    for shape in shapes:
        bx, by, ex, ey = shape.bounds
        assert shape.bounds != (0.0, 0.0, 0.0, 0.0), f"shape {shape.ID} has no box at all"

        # relative_bounds is the box with the enclosing group's origin added
        # on, so the offset between the two is the parent's, and it is zero
        # for a shape sitting on the page. (The names are the wrong way
        # round - #76 - but the relation between them is what is checked.)
        parent = shape.parent
        offset_x, offset_y = (0.0, 0.0)
        if isinstance(parent, Shape) and parent.shape_type == "Group":
            offset_x, offset_y = parent.bounds[0], parent.bounds[1]
        assert shape.relative_bounds == pytest.approx((bx + offset_x, by + offset_y, ex + offset_x, ey + offset_y)), (
            f"shape {shape.ID}: {shape.relative_bounds} is not {shape.bounds} offset by {(offset_x, offset_y)}"
        )


@pytest.mark.parametrize(
    "filename, page_index, shape_text, expected_bounds",
    [
        ("test1.vsdx", 0, "Shape Text", ["0.25", "9.87", "2.42", "11.44"]),  # standard shape
        ("test2.vsdx", 0, "Sub-shape 2", ["0.79", "10.04", "1.87", "10.37"]),  # sub shape in a group
        ("test2.vsdx", 0, "Scenario:", ["0.73", "8.19", "2.49", "8.97"]),  # line
    ],
)
def test_shape_relative_bounds(filename, page_index, shape_text, expected_bounds, basedir):
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[page_index]
    shape = _first_shape_containing(page.shapes, shape_text)
    print([f"{n:.2f}" for n in shape.relative_bounds])
    assert [f"{n:.2f}" for n in shape.relative_bounds] == expected_bounds


@pytest.mark.parametrize(
    "filename, page_index, shape_text, arrow",
    [
        ("test2.vsdx", 0, "Scenario:", True),  # add end arrow
        ("test2.vsdx", 0, "Scenario:", False),  # no end arrow
    ],
)
def test_shape_end_arrow(filename, page_index, shape_text, arrow, tmp_path, basedir):
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_test_shape_end_arrow_{arrow}.vsdx")

    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[page_index]
    shape = _first_shape_containing(page.shapes, shape_text)
    shape.end_arrow = arrow
    expected_arrow = "13" if arrow else "0"
    assert shape.end_arrow == expected_arrow
    vis.save(out_file)

    vis = Document.open(out_file)
    page = vis.pages[page_index]
    shape = _first_shape_containing(page.shapes, shape_text)
    assert shape.end_arrow == expected_arrow


@pytest.mark.parametrize(
    "filename, page_index, shape_text, expected_universal_name",
    [
        ("test3_house.vsdx", 0, "context filter", "House"),
        ("test4_connectors.vsdx", 1, "Shape A", None),  # no master and no name
        ("test4_connectors.vsdx", 1, "A to B", "Dynamic connector"),  # master with Layer and UnivName Cell
        ("test4_connectors.vsdx", 2, "Switch", "Switch"),  # master with no Layer
        ("test4_connectors.vsdx", 2, "Router", "Router"),  # master with no Layer
    ],
)
def test_shape_universal_name(filename, page_index, shape_text, expected_universal_name, basedir):
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[page_index]
    shape = _first_shape_containing(page.shapes, shape_text)
    assert shape.universal_name == expected_universal_name


@pytest.mark.parametrize(
    "filename, expected_master_shape_name",
    [
        (
            "test_master_multiple_child_shapes.vsdx",  # master with multiple child shapes
            "AWS Step Functions workflow ",
        )
    ],
)  # expected master shape name
def test_get_shape_master_page(filename: str, expected_master_shape_name: str, basedir):
    vis = Document.open(os.path.join(basedir, filename))
    child_shape = next(iter(vis.pages[0].children))
    assert child_shape.master_page.name == expected_master_shape_name


@pytest.mark.parametrize(
    "filename, shape_id, expected_angle",
    [
        ("test11_rotate.vsdx", "1", 0.52),
        ("test11_rotate.vsdx", "2", -1.39),
        ("test11_rotate.vsdx", "5", 2.53),
        ("test11_rotate.vsdx", "6", -0.26),
    ],
)
def test_get_shape_angle(filename: str, shape_id: str, expected_angle: float, basedir):
    vis = Document.open(os.path.join(basedir, filename))
    page = vis.pages[0]
    # check angle is close enough to expected
    assert abs(page.shapes.require_id(shape_id).angle - expected_angle) < 0.01


# Which property each `color_param` row names. A chain of `if`/`elif` asserts
# nothing for a row matching none of its branches, so a typo in the table below
# would add a test that passed having checked nothing.
_COLOUR_ATTRIBUTES = {"line": "line_color", "text": "text_color", "fill": "fill_color"}


def _colour_of(shape, color_param: str) -> str:
    assert color_param in _COLOUR_ATTRIBUTES, f"unknown colour {color_param!r}; expected one of {list(_COLOUR_ATTRIBUTES)}"
    return getattr(shape, _COLOUR_ATTRIBUTES[color_param])


@pytest.mark.parametrize(
    ("filename", "page_index", "shape_text", "color_param", "expected_colour"),
    [
        ("test12_colors.vsdx", 0, "Line Color", "line", "#ff0000"),
        ("test12_colors.vsdx", 0, "Text Color", "text", "#ff0000"),
        ("test12_colors.vsdx", 0, "Fill Color", "fill", "#ff0000"),
        ("test12_colors.vsdx", 1, "Line Color", "line", "#00ff00"),
        ("test12_colors.vsdx", 1, "Text Color", "text", "#00ff00"),
        ("test12_colors.vsdx", 1, "Fill Color", "fill", "#00ff00"),
    ],
)
def test_get_shape_line_color(
    filename: str, page_index: int, shape_text: str, color_param: str, expected_colour: str, basedir
):
    """Test that we can get a shapes line, text, or fill color"""
    vis = Document.open(os.path.join(basedir, filename))
    shape = vis.pages[page_index].shapes.by_text(shape_text)
    assert _colour_of(shape, color_param) == expected_colour


@pytest.mark.parametrize(
    ("filename", "page_index", "shape_text", "color_param", "expected_colour"),
    [
        ("test12_colors.vsdx", 0, "Line Color", "line", "#00ff00"),
        ("test12_colors.vsdx", 0, "Text Color", "text", "#00ff00"),
        ("test12_colors.vsdx", 0, "Fill Color", "fill", "#00ff00"),
        ("test12_colors.vsdx", 1, "Line Color", "line", "#0000ff"),
        ("test12_colors.vsdx", 1, "Text Color", "text", "#0000ff"),
        ("test12_colors.vsdx", 1, "Fill Color", "fill", "#0000ff"),
    ],
)
def test_set_shape_line_color(
    filename: str, page_index: int, shape_text: str, color_param: str, expected_colour: str, tmp_path, basedir
):
    """Test that we can set a shapes line, text, or fill color"""
    out_file = os.path.join(str(tmp_path), f"{filename[:-5]}_{page_index}_set_shape_{color_param}_color.vsdx")
    vis = Document.open(os.path.join(basedir, filename))
    shape = vis.pages[page_index].shapes.by_text(shape_text)
    setattr(shape, _COLOUR_ATTRIBUTES[color_param], expected_colour)
    vis.save(out_file)

    vis = Document.open(out_file)
    shape = vis.pages[page_index].shapes.by_text(shape_text)
    assert _colour_of(shape, color_param) == expected_colour


def _loose_shape(page, shape_id: str = "1"):
    """A Shape wrapping a standalone <Shape> element, not yet placed anywhere."""
    xml = ET.fromstring(f'<Shape xmlns="{namespace[1:-1]}" ID="{shape_id}" Type="Shape"><Text>appended</Text></Shape>')
    return Shape(xml=xml, parent=page, page=page)


def test_append_shape_puts_the_shape_inside_the_group(vsdx_copy, tmp_path):
    """A group holds its children in a <Shapes> container, not in the group element.

    Appending to the group element itself makes the new shape a sibling of that
    container, which the schema does not allow and which child_shapes and
    page.shapes cannot see.
    """
    filename = vsdx_copy("test2.vsdx")
    out_file = os.path.join(str(tmp_path), "test2_append_shape.vsdx")

    vis = Document.open(filename)
    page = vis.pages[0]
    group = page.shapes.require_id("9")
    assert group.shape_type == "Group"
    ids_before = [s.ID for s in page.shapes]

    new_shape = _loose_shape(page)
    group.append_shape(new_shape)

    assert group.xml.findall(f"{namespace}Shape") == []  # no <Shape> directly under the group
    shapes_tag = group.xml.find(f"{namespace}Shapes")
    assert new_shape.xml in list(shapes_tag)

    new_id = new_shape.xml.attrib["ID"]
    assert new_id not in ids_before
    assert new_id in [s.ID for s in group.children]
    assert new_id in [s.ID for s in page.shapes]
    vis.save(out_file)

    vis = Document.open(out_file)
    page = vis.pages[0]
    group = page.shapes.require_id("9")
    assert new_id in [s.ID for s in group.children]
    ids = [s.ID for s in page.shapes]
    assert len(ids) == len(set(ids))
    assert page.shapes.require_id(new_id).text.strip() == "appended"


def test_append_shape_creates_a_shapes_container_for_an_empty_group(vsdx_copy):
    """A group that has been emptied has no <Shapes> tag; appending must make one."""
    filename = vsdx_copy("test2.vsdx")

    vis = Document.open(filename)
    page = vis.pages[0]
    group = page.shapes.require_id("9")
    group.xml.remove(group.xml.find(f"{namespace}Shapes"))
    assert list(group.children) == []

    new_shape = _loose_shape(page)
    group.append_shape(new_shape)

    shapes_tag = group.xml.find(f"{namespace}Shapes")
    assert shapes_tag is not None
    assert list(shapes_tag) == [new_shape.xml]
    assert [s.ID for s in group.children] == [new_shape.xml.attrib["ID"]]


def test_append_shape_rejects_a_shape_that_cannot_hold_sub_shapes(vsdx_copy):
    """Only a group holds sub-shapes; anything else produces XML Visio repairs."""
    filename = vsdx_copy("test2.vsdx")

    vis = Document.open(filename)
    page = vis.pages[0]
    plain = page.shapes.require_id("6")
    assert plain.shape_type != "Group"

    with pytest.raises(ValueError, match="cannot contain shapes"):
        plain.append_shape(_loose_shape(page))

    assert plain.xml.find(f"{namespace}Shapes") is None


def test_append_shape_moves_a_shape_that_is_already_on_the_page(vsdx_copy):
    """A shape already on the page is moved into the group, not rejected.

    Rejecting it left no usable route: `Shape.copy()` attaches its clone to the
    destination page, so `group.append_shape(other.copy())` -- the call the old
    error message recommended -- raised. Detaching first is also what prevents
    the element gaining a second parent.
    """
    vis = Document.open(vsdx_copy("test2.vsdx"))
    page = vis.pages[0]
    group = page.shapes.require_id("9")
    existing = page.shapes.require_id("6")

    group.append_shape(existing)

    assert "6" in [s.ID for s in group.children]
    ids = [s.ID for s in page.shapes]
    assert ids.count("6") == 1, "the shape must not be on the page twice"
    assert len(ids) == len(set(ids))


def test_appending_a_copy_places_it_in_the_group(vsdx_copy):
    """The documented copy-and-append path works end to end."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    page = vis.pages[0]
    group = page.shapes.require_id("9")
    before = {s.ID for s in page.shapes}

    group.append_shape(page.shapes.require_id("6").copy())

    ids = [s.ID for s in page.shapes]
    assert len(ids) == len(set(ids)), "the copy must get an id of its own"
    assert set(ids) - before, "a new shape should have appeared"


def test_moving_a_shape_into_a_group_keeps_its_id(vsdx_copy):
    """A move is the same shape, so Connect records naming it stay valid."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    page = vis.pages[0]
    group = page.shapes.require_id("9")
    existing = page.shapes.require_id("6")

    group.append_shape(existing)

    assert existing.ID == "6"


def test_append_shape_rejects_a_shape_built_against_another_page(vsdx_copy):
    """IDs are page-scoped, so a shape may only be appended on its own page."""
    filename = vsdx_copy("test2.vsdx")

    vis = Document.open(filename)
    page, other_page = vis.pages[0], vis.pages[1]
    group = page.shapes.require_id("9")

    with pytest.raises(ValueError, match="belongs to page"):
        group.append_shape(_loose_shape(other_page))


def test_a_group_member_copied_onto_its_own_page_names_its_master(vsdx_copy):
    """Fails if `Shape.copy()` with no page leaves the copy leaning on the group it is no longer in (#104).

    The copy lands at the page's top level. It used to keep the source's group
    as its parent and name no master, so it answered for the group's master
    until the page was walked again, and was saved with a MasterShape pointing
    into nothing.
    """
    vis = Document.open(vsdx_copy("test5_master.vsdx"))
    page = vis.pages[0]
    member = page.shapes.require_id("2")
    assert member.xml.attrib.get("Master") is None
    assert member.master_page_ID == "1"  # its group's

    copy = member.copy()

    assert copy.parent is page
    assert copy.xml.attrib.get("Master") == "1"
    rewalked = page.children.require_id(copy.ID)
    assert rewalked.master_shape is not None
    assert rewalked.master_shape.ID == member.master_shape.ID
