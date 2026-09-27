"""A write to an instance never edits its master (#273).

test9's 'Conn A' inherits MoveTo row 1 from its master, and test3's shape 7
inherits its ShapeClass property. A write to either must give the instance a
row of its own and leave the master's row, which every other instance reads,
as it was.
"""

import xml.etree.ElementTree as ET

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


def test_clearing_del_bool_through_a_second_wrapper_clears_the_row_the_first_deleted(conn_a):
    """The second wrapper still reads the master's row, which has no Del; the clear must reach the instance's row (#454).

    It read the master's unset Del, took the no-op return, and left row 1
    deleted, so a fresh wrapper no longer showed it.
    """
    other = conn_a.page.shapes.by_text("Conn A")
    first, second = conn_a.geometry.rows["1"], other.geometry.rows["1"]

    first.del_bool = True
    second.del_bool = False

    fresh = conn_a.page.shapes.by_text("Conn A")
    assert "1" in fresh.geometry.rows
    own = [row for row in conn_a.geometry.xml.findall(f"{namespace}Row") if row.get("IX") == "1"]
    assert [row.get("Del") for row in own] == [None]
    assert _master_row(conn_a, "1").attrib == {"T": "MoveTo", "IX": "1"}


def test_a_second_wrapper_reads_the_type_del_and_cells_the_first_wrote(conn_a):
    """Reads through a wrapper taken before another one wrote the row are of the instance's row, not the master's (#454).

    The second wrapper still pointed at the master's row, so it reported
    row 1 as a visible MoveTo at the master's X after the first had made it
    a deleted LineTo at another X.
    """
    other = conn_a.page.shapes.by_text("Conn A")
    first, second = conn_a.geometry.rows["1"], other.geometry.rows["1"]

    first.row_type = "LineTo"
    first.del_bool = True
    first.x = 5.0

    assert (second.row_type, second.del_bool) == ("LineTo", "1")
    assert (second.x, second.cells["X"].value, second.y) == (5.0, first.cells["X"].value, 0.0)
    assert second.inherited
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


def test_a_moved_rows_inh_cell_takes_the_formula_from_up_the_whole_master_chain(vsdx_copy):
    """Where the master's cell at the old index is itself ``Inh``, the formula is the one the chain above it resolves to.

    No fixture has such a chain, so one is made: shape 36's master shape, the
    CFF Container's shape 6, is pointed at the Process master, whose shape's
    row 3 computes X as ``Width*1``, and its own row 3 X becomes ``Inh``. Only
    the nearest master was read, so the moved cell kept ``Inh``.
    """
    path = vsdx_copy(S05)
    document = Document.open(path)
    shape = document.pages[0].shapes.require_id("36")
    middle = shape.master_shape
    middle.xml.set("Master", document.master_index["Process"]._page_id)
    assert middle.master_shape.geometry.rows["3"].cells["X"].formula == "Width*1"
    middle.geometry.rows["3"].cells["X"].xml.set("F", "Inh")

    shape.geometry.rows["3"].index = 9
    document.save(path)

    moved = Document.open(path).pages[0].shapes.require_id("36").geometry.rows["9"]
    assert _cell_attributes(moved) == {"X": ("10.90551181102363", "Width*1"), "Y": ("4.133858267716532", "Height*1")}


def test_a_moved_rows_inh_cell_takes_no_formula_past_a_master_that_deletes_the_row(vsdx_copy):
    """A nearer master that deletes the row ends the chain there: its `Inh` cell had no row to inherit from (#454).

    The chain of the test above, with the middle master's row 3 deleted. The
    walk went on past it to the Process master and gave the moved cell a
    formula it never had.
    """
    path = vsdx_copy(S05)
    document = Document.open(path)
    shape = document.pages[0].shapes.require_id("36")
    middle = shape.master_shape
    middle.xml.set("Master", document.master_index["Process"]._page_id)
    middle.xml.find(f'{namespace}Section[@N="Geometry"]/{namespace}Row[@IX="3"]').set("Del", "1")
    assert "3" not in middle.geometry.rows

    shape.geometry.rows["3"].index = 9
    document.save(path)

    moved = Document.open(path).pages[0].shapes.require_id("36").geometry.rows["9"]
    assert _cell_attributes(moved) == {"X": ("10.90551181102363", None), "Y": ("4.133858267716532", None)}


def test_a_row_moves_onto_an_index_another_wrapper_freed(conn_a):
    """The section as it stands says whether an index is free, not a `rows` another Shape object has made stale (#454).

    The first wrapper's move of row 2 leaves only a bare ``Del`` row at IX 2,
    which gives way; the second wrapper still held the inherited row 2 in its
    `rows`, and refused.
    """
    other = conn_a.page.shapes.by_text("Conn A")
    first, second = conn_a.geometry, other.geometry
    assert "2" in second.rows

    first.rows["2"].index = 7
    moved = second.rows["1"]
    moved.index = 2

    at_2 = [row for row in conn_a.geometry.xml.findall(f"{namespace}Row") if row.get("IX") == "2"]
    assert at_2 == [moved.xml]
    assert moved.xml.get("Del") is None
    assert second.rows["2"] is moved


def test_an_index_written_with_a_leading_zero_is_the_index_it_names(conn_a):
    """``"01"`` is IX 1, as Visio orders rows by number; compared as text it looked free, and gave two rows at one index (#454)."""
    with pytest.raises(InvalidOperationError, match="IX=1;"):
        conn_a.geometry.rows["2"].index = "01"

    conn_a.geometry.rows["2"].index = "07"
    assert conn_a.geometry.rows["7"].xml.get("IX") == "7"


def test_a_row_moved_down_is_listed_where_the_section_reads_it(vsdx_copy):
    """`rows` is in the order Visio reads the section, as a fresh read gives it; a move re-filed the row at the end (#454).

    `start_pos` and `set_move_to(move_to_index=...)` go by that order, so
    before a save they addressed a different row than after it.
    """
    path = vsdx_copy("test9_rect_and_line.vsdx")
    document = Document.open(path)
    line = document.pages[0].shapes.by_text("Line A")
    assert line.master_shape is None and list(line.geometry.rows) == ["1", "2"]

    line.geometry.rows["2"].index = 0

    assert list(line.geometry.rows) == ["0", "1"]
    document.save(path)
    assert list(Document.open(path).pages[0].shapes.by_text("Line A").geometry.rows) == ["0", "1"]


def test_rows_are_listed_in_index_order_where_a_shape_has_a_master(vsdx_copy):
    """A fresh read listed the master's rows first and the shape's own after; a move listed them by index (#454).

    Conn A inherits row 1 and owns row 2; moved to 0, its row came first
    before a save and last after one, so position-based writers addressed
    different rows. Visio reads a section's rows by index.
    """
    path = vsdx_copy("test9_rect_and_line.vsdx")
    document = Document.open(path)
    connector = document.pages[0].shapes.by_text("Conn A")

    connector.geometry.rows["2"].index = 0

    assert list(connector.geometry.rows) == ["0", "1"]
    document.save(path)
    assert list(Document.open(path).pages[0].shapes.by_text("Conn A").geometry.rows) == ["0", "1"]


def test_a_row_does_not_move_onto_an_index_another_wrapper_filled(conn_a):
    """A row another Shape object moved to an index holds it, though this one's `rows` has never seen it there."""
    other = conn_a.page.shapes.by_text("Conn A")
    first, second = conn_a.geometry, other.geometry
    assert "7" not in second.rows

    first.rows["2"].index = 7

    with pytest.raises(InvalidOperationError, match="IX=7"):
        second.rows["1"].index = 7


def _own_rows(connector) -> list[tuple[dict[str, str], list[str | None]]]:
    """Each Row element of the connector's own section, in document order: its attributes and its cells' names."""
    return [
        (dict(row.attrib), [cell.get("N") for cell in row.findall(f"{namespace}Cell")])
        for row in connector.geometry.xml.findall(f"{namespace}Row")
    ]


def test_a_row_moved_away_and_back_reloads_as_it_was(vsdx_copy):
    """Row 1 moved to 7 leaves a bare Del="1" row at 1; moving it back takes that row's place (#454).

    The bare row counted as a row holding IX 1, so the move back raised, and
    nothing in the API could remove it: a reindex could not be undone.
    """
    path = vsdx_copy("test9_rect_and_line.vsdx")
    document = Document.open(path)
    connector = document.pages[0].shapes.by_text("Conn A")
    original = _rows_view(connector)
    row = connector.geometry.rows["1"]

    row.index = 7
    row.index = 1
    document.save(path)

    reloaded = Document.open(path).pages[0].shapes.by_text("Conn A")
    assert _rows_view(reloaded) == original
    assert _own_rows(reloaded) == [
        ({"T": "MoveTo", "IX": "1"}, ["X", "Y"]),
        ({"T": "LineTo", "IX": "2"}, ["X", "Y"]),
        ({"T": "LineTo", "IX": "3", "Del": "1"}, []),
    ]


def test_a_row_moved_onto_a_bare_deleted_row_overrides_the_masters_row_there(vsdx_copy):
    """Conn A's own row IX 3 is a bare Del="1" row hiding the master's row 3: the index is free, and the moved row takes its place.

    The moved row becomes the override of the master's row 3, so a cell of
    the master's there that the moved row lacks, here one named ``A``, is
    read through it, as Visio reads it.
    """
    path = vsdx_copy("test9_rect_and_line.vsdx")
    document = Document.open(path)
    connector = document.pages[0].shapes.by_text("Conn A")
    _master_row(connector, "3").append(ET.Element(f"{namespace}Cell", {"N": "A", "V": "0.5"}))
    view = _rows_view(connector)
    assert "3" not in view
    row_type, cells = view["2"]

    connector.geometry.rows["2"].index = 3
    written = _rows_view(connector)
    document.save(path)

    reloaded = Document.open(path).pages[0].shapes.by_text("Conn A")
    assert written == {"1": view["1"], "3": (row_type, {**cells, "A": ("0.5", None)})}
    assert _rows_view(reloaded) == written
    assert _own_rows(reloaded) == [({"T": "LineTo", "IX": "2", "Del": "1"}, []), ({"T": "LineTo", "IX": "3"}, ["X", "Y"])]


def test_moving_a_row_onto_an_index_a_deleted_row_holds_raises(conn_a):
    """A Del="1" row that keeps its cells is a row the user deleted: hidden from `rows`, but the index is still taken (#273, #454)."""
    conn_a.geometry.rows["2"].del_bool = True
    geometry = conn_a.page.shapes.by_text("Conn A").geometry
    assert "2" not in geometry.rows
    rows_before = [dict(row.attrib) for row in geometry.xml.findall(f"{namespace}Row")]

    with pytest.raises(InvalidOperationError):
        geometry.rows["1"].index = 2

    assert [dict(row.attrib) for row in geometry.xml.findall(f"{namespace}Row")] == rows_before
    assert geometry.rows["1"].index == "1"
    assert geometry.rows["1"].inherited


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


def test_a_held_property_reads_the_override_another_handle_made(house_7):
    """A handle taken while the property was inherited reads the row a second handle wrote, not the master's."""
    held = house_7.data_properties["ShapeClass"]
    other = house_7.data_properties["ShapeClass"]
    assert held is not other and held.inherited

    other.set_attribute("Label", "V", "Renamed")
    other.value = "Written"

    assert (held.label, held.value) == ("Renamed", "Written")
    assert (held.value_type, held.prompt, held.sort_key) == ("0", "", "")
    held.value = "Again"
    [row] = _property_rows(house_7, "ShapeClass")
    assert held.xml is other.xml is row
    assert other.value == "Again"


def test_a_held_property_reads_an_override_a_nearer_master_made_since(vsdx_copy):
    """A handle holds the farthest master's row; a row a nearer master has written since is the one Visio reads (#454).

    No fixture has such a chain, so one is made as in
    test_an_override_rows_fields_read_through_every_master_up_the_chain,
    with shape 4's own Property section removed so its property is
    inherited all the way from master 2.
    """
    shape = Document.open(vsdx_copy("test6_shape_properties.vsdx")).pages[2].shapes.require_id("4")
    shape.xml.remove(shape.xml.find(f'{namespace}Section[@N="Property"]'))
    shape.xml.set("Master", "6")
    middle = shape.master_shape
    middle.xml.set("Master", "2")
    held = shape.data_properties["master_Prop"]
    assert held.inherited

    middle.data_properties["master_Prop"].value = "middle"
    middle.data_properties["master_Prop"].set_attribute("Label", "V", "Relabelled")

    assert (held.value, held.label) == ("middle", "Relabelled")
    assert shape.data_properties["Relabelled"].value == "middle"


def test_a_held_property_its_master_no_longer_has_reads_nothing(house_7):
    """A named row is found by its ``N`` up the chain as it stands; the row handed out is not read once no master has it (#454)."""
    held = house_7.data_properties["ShapeClass"]
    master_row = held.xml
    master_section = house_7.master_shape.xml.find(f'{namespace}Section[@N="Property"]')
    master_section.remove(master_row)

    assert (held.label, held.value) == (None, None)
    assert held.set_attribute("Label", "V", "Renamed") is False
    assert _property_rows(house_7, "ShapeClass") == []


def test_a_value_written_through_a_property_its_master_no_longer_has_is_refused(house_7):
    """Reads give nothing and `set_attribute` refuses; a value write made a row of the obsolete ``N`` all the same (#454)."""
    held = house_7.data_properties["ShapeClass"]
    master_section = house_7.master_shape.xml.find(f'{namespace}Section[@N="Property"]')
    master_section.remove(held.xml)

    with pytest.raises(InvalidOperationError, match="ShapeClass"):
        held.value = "Written"

    assert _property_rows(house_7, "ShapeClass") == []


def test_writing_an_unnamed_inherited_property_keeps_its_other_fields(house_7):
    """A row with no ``N`` has no name to inherit its cells through, so the override carries every one of them (#454)."""
    master_row = house_7.data_properties["ShapeClass"].xml
    del master_row.attrib["N"]
    prop = house_7.data_properties["ShapeClass"]
    assert prop.inherited and prop.name is None

    prop.value = "Written"

    assert (prop.label, prop.value_type, prop.prompt, prop.sort_key, prop.value) == ("ShapeClass", "0", "", "", "Written")
    fresh = house_7.data_properties["ShapeClass"]
    assert (fresh.value_type, fresh.prompt, fresh.sort_key, fresh.value) == ("0", "", "", "Written")
    assert master_row.find(f'{namespace}Cell[@N="Value"]').get("V") == "Location"


def test_get_attribute_reads_a_cell_as_the_fields_do(house_7):
    """`get_attribute` reads the row a second handle wrote, and a cell the row lacks from the master's row."""
    held = house_7.data_properties["ShapeClass"]
    other = house_7.data_properties["ShapeClass"]

    other.set_attribute("Label", "V", "Renamed")

    assert held.get_attribute("Label", "V") == "Renamed"
    assert other.get_attribute("Type", "V") == other.value_type == "0"
    assert other.get_attribute("NoSuchCell", "V") is None


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
