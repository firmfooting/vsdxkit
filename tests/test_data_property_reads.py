"""Reading Shape Data must not change the document.

`DataProperty.value` used to clean up a `No Formula` formula and stamp a `STR`
unit while *reading*, so merely inspecting a shape's properties changed the
bytes the package saved — and the difference only showed up later, in a diff
against a file the caller believed they had not edited.
"""

import os
import zipfile
from xml.etree import ElementTree

import pytest

from vsdxkit import VisioFile, namespace

FIXTURES = os.path.dirname(os.path.realpath(__file__))

PACKAGES = sorted(name for name in os.listdir(FIXTURES) if name.endswith(".vsdx"))


def _members(path: str) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in sorted(archive.namelist())}


@pytest.mark.parametrize("filename", PACKAGES)
def test_reading_every_data_property_does_not_change_the_saved_package(filename, tmp_path):
    untouched = os.path.join(str(tmp_path), "untouched.vsdx")
    with VisioFile(os.path.join(FIXTURES, filename)) as vis:
        vis.save_vsdx(untouched)

    after_reading = os.path.join(str(tmp_path), "after_reading.vsdx")
    with VisioFile(os.path.join(FIXTURES, filename)) as vis:
        for page in vis.pages:
            for shape in page.all_shapes:
                for prop in shape.data_properties.values():
                    prop.value  # noqa: B018 - reading is the operation under test
        vis.save_vsdx(after_reading)

    assert _members(after_reading) == _members(untouched)


def _property_row_without_a_value_cell(shape):
    section = shape.xml.find(f'{namespace}Section[@N="Property"]')
    if section is None:
        return None
    for row in section.findall(f"{namespace}Row"):
        if row.find(f'{namespace}Cell[@N="Value"]') is None:
            return row
    return None


def test_reading_a_property_with_no_value_cell_returns_none_and_creates_nothing(vsdx_copy):
    with VisioFile(vsdx_copy("test6_shape_properties.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_property_label("my_property_label")
        assert shape is not None
        section = shape.xml.find(f'{namespace}Section[@N="Property"]')
        row = section.findall(f"{namespace}Row")[0]
        value_cell = row.find(f'{namespace}Cell[@N="Value"]')
        if value_cell is not None:
            row.remove(value_cell)

        prop = next(p for p in shape.data_properties.values() if p.xml is row)

        assert prop.value is None
        assert row.find(f'{namespace}Cell[@N="Value"]') is None


def test_setting_a_property_with_no_value_cell_creates_it(vsdx_copy, tmp_path):
    """Upstream dave-howard/vsdx#79: setting a property that has no Value cell."""
    out = os.path.join(str(tmp_path), "out.vsdx")
    with VisioFile(vsdx_copy("test6_shape_properties.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_property_label("my_property_label")
        section = shape.xml.find(f'{namespace}Section[@N="Property"]')
        row = section.findall(f"{namespace}Row")[0]
        value_cell = row.find(f'{namespace}Cell[@N="Value"]')
        if value_cell is not None:
            row.remove(value_cell)
        prop = next(p for p in shape.data_properties.values() if p.xml is row)

        prop.value = "set through the setter"

        assert prop.value == "set through the setter"
        vis.save_vsdx(out)

    with VisioFile(out) as vis:
        shape = vis.pages[0].find_shape_by_property_label("my_property_label")
        reloaded = next(p for p in shape.data_properties.values() if p.label == "my_property_label")
        assert reloaded.value == "set through the setter"


def _append_property_row(shape, label: str, value: str):
    section = shape.xml.find(f'{namespace}Section[@N="Property"]')
    if section is None:
        # a shape whose properties all come from its master carries no section
        section = ElementTree.fromstring(f'<Section xmlns="{namespace[1:-1]}" N="Property"/>')
        shape.xml.append(section)
    row = ElementTree.fromstring(
        f'<Row xmlns="{namespace[1:-1]}" N="{label}"><Cell N="Label" V="{label}"/><Cell N="Value" V="{value}"/></Row>'
    )
    section.append(row)
    return row


def test_the_data_property_cache_follows_a_new_property_row(vsdx_copy):
    """A row added to the shape's XML after the first read must be visible."""
    with VisioFile(vsdx_copy("test6_shape_properties.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_property_label("my_property_label")
        before = set(shape.data_properties)

        _append_property_row(shape, "added_later", "42")

        assert "added_later" in shape.data_properties
        assert before < set(shape.data_properties)


def test_the_cache_follows_a_replaced_property_row(vsdx_copy):
    """Removing one row and adding another leaves the count unchanged."""
    with VisioFile(vsdx_copy("test6_shape_properties.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_property_label("my_property_label")
        assert "my_property_label" in shape.data_properties

        section = shape.xml.find(f'{namespace}Section[@N="Property"]')
        section.remove(section.findall(f"{namespace}Row")[0])
        _append_property_row(shape, "brand_new", "1")

        assert "brand_new" in shape.data_properties
        assert "my_property_label" not in shape.data_properties


def _value_cell(shape, label: str):
    prop = next(p for p in shape.data_properties.values() if p.label == label)
    return prop, prop.xml.find(f'{namespace}Cell[@N="Value"]')


def test_setting_a_value_keeps_a_declared_unit(vsdx_copy):
    """A date or numeric property must not be retyped as a string on write."""
    with VisioFile(vsdx_copy("test6_shape_properties.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_property_label("my_property_label")
        prop, cell = _value_cell(shape, "my_property_label")
        cell.attrib["U"] = "DATE"
        cell.attrib["F"] = "No Formula"

        prop.value = "41500"

        assert cell.attrib["U"] == "DATE"
        assert "F" not in cell.attrib


def test_setting_a_value_clears_no_formula_on_an_inner_text_row(vsdx_copy):
    """The inner-text row must get the same cleanup as the attribute row."""
    with VisioFile(vsdx_copy("test6_shape_properties.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_property_label("my_property_label")
        prop, cell = _value_cell(shape, "my_property_label")
        del cell.attrib["V"]
        cell.attrib["F"] = "No Formula"
        cell.text = "old"

        prop.value = "new"

        assert prop.value == "new"
        assert "F" not in cell.attrib


def test_creating_a_value_cell_does_not_assert_a_unit(vsdx_copy):
    """A cell created for a numeric property must not be declared a string."""
    with VisioFile(vsdx_copy("test6_shape_properties.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_property_label("my_property_label")
        prop, cell = _value_cell(shape, "my_property_label")
        prop.xml.remove(cell)

        prop.value = 3.5

        created = prop.xml.find(f'{namespace}Cell[@N="Value"]')
        assert created.attrib["V"] == "3.5"
        assert "U" not in created.attrib


# --- writing through a property inherited from a master ----------------------

# Shape 3 on Page-1 of test_master_multiple_child_shapes carries no Property
# section of its own; its `title` property comes from master shape 7.
INHERITED = "test_master_multiple_child_shapes.vsdx"


def _master_title_row(shape):
    section = shape.master_shape.xml.find(f'{namespace}Section[@N="Property"]')
    return section.find(f'{namespace}Row[@N="Row_1"]')


def test_an_inherited_property_is_marked_inherited(vsdx_copy):
    with VisioFile(vsdx_copy(INHERITED)) as vis:
        shape = vis.pages[0].find_shape_by_id("3")

        prop = shape.data_properties["title"]

        assert prop.inherited is True
        assert prop.shape is shape  # the instance, not the master it reads from
        assert shape.xml.find(f'{namespace}Section[@N="Property"]') is None


def test_setting_an_inherited_value_overrides_it_on_the_instance(vsdx_copy, tmp_path):
    """Issue #247: the write used to land in the master, changing every instance.

    Visio holds an overridden property in a row on the instance, matched to the
    master's row by name and carrying nothing but the new value.
    """
    out = os.path.join(str(tmp_path), "out.vsdx")
    with VisioFile(vsdx_copy(INHERITED)) as vis:
        shape = vis.pages[0].find_shape_by_id("3")
        prop = shape.data_properties["title"]
        master_row = _master_title_row(shape)
        before = ElementTree.tostring(master_row)

        prop.value = "written through the instance"

        assert prop.value == "written through the instance"
        assert prop.inherited is False
        assert ElementTree.tostring(_master_title_row(shape)) == before
        row = shape.xml.find(f'{namespace}Section[@N="Property"]/{namespace}Row[@N="Row_1"]')
        assert [(c.attrib.get("N"), c.attrib.get("V")) for c in row] == [("Value", "written through the instance")]
        vis.save_vsdx(out)

    with VisioFile(out) as vis:
        shape = vis.pages[0].find_shape_by_id("3")
        prop = shape.data_properties["title"]
        # the override still resolves its label, type and prompt from the master
        assert (prop.label, prop.value, prop.value_type) == ("title", "written through the instance", "0")
        assert shape.master_shape.data_properties["title"].value == "0"


def test_a_second_write_reuses_the_row_the_first_one_created(vsdx_copy):
    with VisioFile(vsdx_copy(INHERITED)) as vis:
        shape = vis.pages[0].find_shape_by_id("3")
        prop = shape.data_properties["title"]

        prop.value = "first"
        prop.value = "second"

        rows = shape.xml.findall(f'{namespace}Section[@N="Property"]/{namespace}Row')
        assert len(rows) == 1
        assert prop.value == "second"


def test_an_override_section_is_placed_before_the_shapes_text(vsdx_copy):
    """Visio rejects a Section that follows Text, so the new one goes ahead of it."""
    with VisioFile(vsdx_copy(INHERITED)) as vis:
        shape = vis.pages[0].find_shape_by_id("3")
        shape.xml.append(ElementTree.fromstring(f'<Text xmlns="{namespace[1:-1]}">hello</Text>'))

        shape.data_properties["title"].value = "written through the instance"

        assert [child.tag for child in shape.xml] == [f"{namespace}Section", f"{namespace}Text"]
