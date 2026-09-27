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


def test_two_wrappers_of_one_inherited_row_write_one_override_row(conn_a):
    """Each Shape wrapper resolves the row as inherited; the second write reuses the row the first made."""
    other = conn_a.page.shapes.by_text("Conn A")
    assert other is not conn_a
    first, second = conn_a.geometry.rows["1"], other.geometry.rows["1"]
    assert first.inherited and second.inherited

    first.row_type = "LineTo"
    first.x = 5.0
    second.del_bool = True

    own = [row for row in conn_a.geometry.xml.findall(f"{namespace}Row") if row.get("IX") == "1"]
    assert [dict(row.attrib) for row in own] == [{"T": "LineTo", "IX": "1", "Del": "1"}]
    assert first.xml is second.xml is own[0]
    # the cell the first wrote is read through the second, and the master's Y still inherited
    assert (second.x, second.y) == (5.0, 0.0)
    assert _master_row(conn_a, "1").attrib == {"T": "MoveTo", "IX": "1"}


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


def _rows_view(connector) -> dict[str, tuple[str | None, dict[str, tuple[str | None, str | None]]]]:
    """Each row Conn A shows, by index: its type, and each cell's value and formula."""
    return {
        ix: (row.row_type, {name: (cell.value, cell.formula) for name, cell in row.cells.items()})
        for ix, row in connector.geometry.rows.items()
    }


@pytest.mark.parametrize(
    "moved",
    [
        pytest.param("1", id="an inherited row"),
        pytest.param("2", id="an own row over the master's"),
    ],
)
def test_a_row_moved_to_a_new_index_reloads_as_it_reads(vsdx_copy, moved):
    """The master's row at the old index is hidden, and the moved row keeps every cell it read (#273).

    Before, only the override moved: after a save the master's row came
    back at the old index, and the moved row lost the cells it had read from
    the master (test9 Conn A's row 1 moved to 7 reloaded as rows 1, 2 and 7).
    """
    path = vsdx_copy("test9_rect_and_line.vsdx")
    document = Document.open(path)
    connector = document.pages[0].shapes.by_text("Conn A")
    read = _rows_view(connector)["1" if moved == "1" else "2"]

    connector.geometry.rows[moved].index = 7
    written = _rows_view(connector)
    document.save(path)

    reloaded = Document.open(path).pages[0].shapes.by_text("Conn A")
    assert sorted(written) == sorted({"1", "2"} - {moved} | {"7"})
    assert written["7"] == read
    assert _rows_view(reloaded) == written


S05 = "fixtures/com_reference/s05_swimlanes_cfflow.vsdx"


def _cell_attributes(row) -> dict[str, tuple[str | None, str | None]]:
    return {name: (cell.value, cell.formula) for name, cell in row.cells.items()}


def test_a_moved_rows_inh_cells_take_the_formula_of_the_masters_row_they_left(vsdx_copy):
    """s05 shape 36's own row 3 holds X and Y as ``F="Inh"``: at a new index they would inherit from another row, or none.

    The master's row 3 computes them as ``Width*1`` and ``Height*1``, so the
    moved row carries those, with the values it read, and Visio recalculates
    the same coordinates.
    """
    path = vsdx_copy(S05)
    document = Document.open(path)
    shape = document.pages[0].shapes.require_id("36")
    row = shape.geometry.rows["3"]
    assert {name: cell.formula for name, cell in row.cells.items()} == {"X": "Inh", "Y": "Inh"}
    assert "9" not in shape.geometry.rows

    row.index = 9
    document.save(path)

    moved = Document.open(path).pages[0].shapes.require_id("36").geometry.rows["9"]
    assert _cell_attributes(moved) == {"X": ("10.90551181102363", "Width*1"), "Y": ("4.133858267716532", "Height*1")}


def test_a_moved_rows_inh_cell_over_a_master_value_keeps_the_value_alone(vsdx_copy):
    """Where the master's cell at the old index holds a value and no formula, the moved cell holds its value and no formula."""
    path = vsdx_copy(S05)
    document = Document.open(path)
    shape = document.pages[0].shapes.require_id("36")
    shape.master_shape.geometry.rows["3"].cells["X"].xml.attrib.pop("F")

    shape.geometry.rows["3"].index = 9
    document.save(path)

    moved = Document.open(path).pages[0].shapes.require_id("36").geometry.rows["9"]
    assert _cell_attributes(moved) == {"X": ("10.90551181102363", None), "Y": ("4.133858267716532", "Height*1")}


def test_moving_a_row_onto_an_index_a_deleted_row_holds_raises(conn_a):
    """Conn A's own row IX 3 carries Del="1": hidden from `rows`, but the index is still taken (#273)."""
    geometry = conn_a.geometry
    assert "3" not in geometry.rows
    rows_before = [dict(row.attrib) for row in geometry.xml.findall(f"{namespace}Row")]

    with pytest.raises(InvalidOperationError):
        geometry.rows["2"].index = 3

    assert [dict(row.attrib) for row in geometry.xml.findall(f"{namespace}Row")] == rows_before
    assert geometry.rows["2"].index == "2"


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


def test_an_override_rows_fields_read_through_every_master_up_the_chain(vsdx_copy):
    """A master's shape can itself be an instance of another master; a cell the chain's nearer rows lack is read from a farther one.

    No fixture has such a chain, so one is made: test6 page 3's shape 4, whose
    own Row_1 holds only a Value, is pointed at master 6, which has no
    Property section, and master 6's shape at master 2, which has Row_1 in
    full. The fields read only the nearest master's section, so they gave
    None and the property was listed under "".
    """
    shape = Document.open(vsdx_copy("test6_shape_properties.vsdx")).pages[2].shapes.require_id("4")
    shape.xml.set("Master", "6")
    middle = shape.master_shape
    assert middle.xml.find(f'{namespace}Section[@N="Property"]') is None
    middle.xml.set("Master", "2")
    assert middle.master_shape is not None

    properties = shape.data_properties

    assert list(properties) == ["master_Prop"]
    prop = properties["master_Prop"]
    assert (prop.label, prop.value_type, prop.prompt, prop.sort_key, prop.value) == ("master_Prop", "0", "", "", "override")


def test_set_attribute_writing_v_removes_the_formula_of_a_cell_it_copies_down(house_7):
    """The value wins (#300): a master's formula copied down with the cell would be recalculated over the value on open."""
    prop = house_7.data_properties["ShapeClass"]
    master_value = prop.xml.find(f'{namespace}Cell[@N="Value"]')
    master_value.set("F", 'GUARD("Location")')

    prop.set_attribute("Value", "V", "Changed")

    assert (prop.get_attribute("Value", "V"), prop.get_attribute("Value", "F")) == ("Changed", None)
    assert master_value.get("F") == 'GUARD("Location")'


def test_set_attribute_writing_v_removes_the_formula_of_a_cell_the_shape_owns(vsdx_copy):
    """s05 shape 54's own Function value is IFERROR(CONTAINERSHEETREF(...)), which Visio would put back on open."""
    shape = Document.open(vsdx_copy("fixtures/com_reference/s05_swimlanes_cfflow.vsdx")).pages[0].shapes.require_id("54")
    prop = shape.data_properties["Function"]
    assert not prop.inherited and prop.get_attribute("Value", "F")

    prop.set_attribute("Value", "V", "Sales")

    assert (prop.get_attribute("Value", "V"), prop.get_attribute("Value", "F")) == ("Sales", None)


def test_set_attribute_writing_another_attribute_leaves_the_formula(vsdx_copy):
    shape = Document.open(vsdx_copy("fixtures/com_reference/s05_swimlanes_cfflow.vsdx")).pages[0].shapes.require_id("54")
    prop = shape.data_properties["Function"]
    formula = prop.get_attribute("Value", "F")

    prop.set_attribute("Value", "U", "STR")

    assert prop.get_attribute("Value", "F") == formula
