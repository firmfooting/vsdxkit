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
