"""A write to an instance never edits its master (#273).

test9's 'Conn A' inherits MoveTo row 1 from its master, and test3's shape 7
inherits its ShapeClass property. A write to either must give the instance a
row of its own and leave the master's row, which every other instance reads,
as it was.
"""

import pytest

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError


@pytest.fixture
def conn_a(vsdx_copy):
    connector = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Conn A")
    assert connector.geometry.rows["1"].inherited
    return connector


def _master_row(connector, ix: str):
    section = connector.master_shape.xml.find(f'{namespace}Section[@N="Geometry"]')
    return next(row for row in section.findall(f"{namespace}Row") if row.get("IX") == ix)


def _instance_row_count(connector) -> int:
    return len(connector.geometry.xml.findall(f"{namespace}Row"))


def test_row_type_on_an_inherited_row_leaves_the_master_alone(conn_a):
    row = conn_a.geometry.rows["1"]

    row.row_type = "LineTo"

    assert _master_row(conn_a, "1").get("T") == "MoveTo"
    assert row.xml is not _master_row(conn_a, "1")
    assert row.xml.get("T") == "LineTo"


def test_del_bool_on_an_inherited_row_leaves_the_master_alone(conn_a):
    row = conn_a.geometry.rows["1"]

    row.del_bool = True

    assert _master_row(conn_a, "1").get("Del") is None
    assert row.xml.get("Del") == "1"


def test_clearing_del_bool_where_there_is_none_is_a_no_op(conn_a):
    """Clearing an unset Del on an inherited row must not materialise an override row (#273 round 2)."""
    row = conn_a.geometry.rows["1"]
    assert row.inherited
    assert row.del_bool is None
    rows_before = _instance_row_count(conn_a)

    row.del_bool = False

    assert row.del_bool is None
    assert row.inherited
    assert _instance_row_count(conn_a) == rows_before


def test_clearing_del_bool_where_there_is_none_on_an_own_row_is_also_a_no_op(conn_a):
    row = conn_a.geometry.rows["2"]
    assert not row.inherited
    assert row.del_bool is None

    row.del_bool = False

    assert row.del_bool is None


def test_index_on_an_inherited_row_leaves_the_master_alone_and_refiles_the_row(conn_a):
    geometry = conn_a.geometry
    row = geometry.rows["1"]

    row.index = 7

    assert _master_row(conn_a, "1").get("IX") == "1"
    assert geometry.rows["7"] is row
    assert row.xml.get("IX") == "7"


def test_reindexing_onto_an_occupied_ix_raises_and_leaves_everything_alone(conn_a):
    """Re-indexing row 1 onto 2 must not create a second Row IX=2 or orphan the real row 2 (#273 round 2)."""
    geometry = conn_a.geometry
    row1 = geometry.rows["1"]
    row2 = geometry.rows["2"]
    rows_before = _instance_row_count(conn_a)

    with pytest.raises(InvalidOperationError):
        row1.index = 2

    assert _master_row(conn_a, "1").get("IX") == "1"
    assert _master_row(conn_a, "2").get("IX") == "2"
    assert row1.inherited
    assert row1.xml.get("IX") == "1"
    assert geometry.rows["1"] is row1
    assert geometry.rows["2"] is row2
    assert _instance_row_count(conn_a) == rows_before


def test_reindexing_a_row_onto_its_own_index_is_a_no_op(conn_a):
    row = conn_a.geometry.rows["1"]
    rows_before = _instance_row_count(conn_a)

    row.index = 1

    assert row.inherited
    assert row.xml is _master_row(conn_a, "1")
    assert _instance_row_count(conn_a) == rows_before


def test_set_attribute_on_an_inherited_property_writes_the_instance_and_lands(vsdx_copy):
    """It wrote the master's cell; with make_local alone it would find no cell on the new row and return False."""
    shape = Document.open(vsdx_copy("test3_house.vsdx")).pages[0].shapes.by_id("7")
    prop = shape.data_properties["ShapeClass"]
    assert prop.inherited
    master_value = prop.xml.find(f'{namespace}Cell[@N="Value"]')

    assert prop.set_attribute("Value", "V", "Changed") is True

    assert master_value.get("V") == "Location"
    assert shape.data_properties["ShapeClass"].value == "Changed"


@pytest.fixture
def house_7(vsdx_copy):
    """test3's shape 7, whose ShapeClass (label ShapeClass, type 0, prompt and sort key empty) is its master's."""
    shape = Document.open(vsdx_copy("test3_house.vsdx")).pages[0].shapes.by_id("7")
    assert shape.data_properties["ShapeClass"].inherited
    return shape


def _property_rows(shape, name: str) -> list:
    return [row for row in shape.xml.findall(f'{namespace}Section[@N="Property"]/{namespace}Row') if row.get("N") == name]


def test_relabelling_an_inherited_property_keeps_the_masters_other_fields(house_7):
    """Visio inherits each cell on its own: an override row carrying only a Label still takes Type and Prompt from the master."""
    prop = house_7.data_properties["ShapeClass"]

    prop.set_attribute("Label", "V", "Renamed")

    assert (prop.label, prop.value_type, prop.prompt, prop.sort_key) == ("Renamed", "0", "", "")
    fresh = house_7.data_properties["Renamed"]
    assert (fresh.value_type, fresh.prompt, fresh.sort_key, fresh.value) == ("0", "", "", "Location")


def test_a_relabelled_property_is_listed_once(house_7):
    """The override row replaces the master's property of its N, whatever label it now shows."""
    house_7.data_properties["ShapeClass"].set_attribute("Label", "V", "Renamed")

    properties = house_7.data_properties

    assert [prop.name for prop in properties.values()].count("ShapeClass") == 1
    assert "ShapeClass" not in properties
    assert properties["Renamed"].inherited is False


def test_a_value_written_after_a_relabel_leaves_one_row(house_7):
    """A property read before the relabel is still inherited; its write reuses the row the relabel made."""
    held = house_7.data_properties["ShapeClass"]
    house_7.data_properties["ShapeClass"].set_attribute("Label", "V", "Renamed")

    held.value = "Written"
    house_7.data_properties["Renamed"].value = "Again"

    [row] = _property_rows(house_7, "ShapeClass")
    assert held.xml is row
    assert house_7.data_properties["Renamed"].value == "Again"


def test_set_attribute_twice_leaves_one_row(house_7):
    prop = house_7.data_properties["ShapeClass"]

    prop.set_attribute("Label", "V", "Renamed")
    prop.set_attribute("SortKey", "V", "1")
    house_7.data_properties["Renamed"].set_attribute("Prompt", "V", "Asked")

    [row] = _property_rows(house_7, "ShapeClass")
    assert {cell.get("N"): cell.get("V") for cell in row} == {"Label": "Renamed", "Prompt": "Asked", "SortKey": "1"}
    assert (prop.label, prop.prompt, prop.sort_key, prop.value_type) == ("Renamed", "Asked", "1", "0")


def test_set_attribute_on_an_override_row_copies_the_masters_cell_it_lacks(house_7):
    """A value write gives the instance a row holding only Value; relabelling it next must still land."""
    house_7.data_properties["ShapeClass"].value = "Written"

    assert house_7.data_properties["ShapeClass"].set_attribute("Label", "V", "Renamed") is True

    [row] = _property_rows(house_7, "ShapeClass")
    assert {cell.get("N"): cell.get("V") for cell in row} == {"Value": "Written", "Label": "Renamed"}
    assert list(house_7.data_properties) == ["ShapeType", "Renamed"]


def test_reading_an_override_rows_fields_does_not_rebuild_the_masters_properties(house_7, monkeypatch):
    """Each field read looked the master's property up through `master_shape.data_properties`, rebuilt every call."""
    house_7.data_properties["ShapeClass"].value = "Written"
    prop = house_7.data_properties["ShapeClass"]
    master = house_7.master_shape
    reads = []
    original = type(master).data_properties

    def counting(self):
        if self is master:
            reads.append(self)
        return original.fget(self)

    monkeypatch.setattr(type(master), "data_properties", property(counting))

    assert (prop.label, prop.value_type, prop.prompt, prop.sort_key) == ("ShapeClass", "0", "", "")
    assert reads == []


def test_the_formula_cache_leaves_an_inherited_geometry_cell_alone(vsdx_copy):
    """#273 part 3: the refresh wrote the value it computed into the master's cell, which every other instance reads."""
    connector = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Conn A")
    master_x = _master_row(connector, "1").find(f'{namespace}Cell[@N="X"]')
    master_x.set("F", "Width*1")
    master_x.set("V", "0")

    connector._refresh_formula_values()

    assert master_x.get("V") == "0"
