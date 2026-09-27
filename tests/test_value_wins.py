"""A value written to a cell is the value Visio shows (#300, #319).

Visio recalculates a cell's formula on open and discards the value beside
it, so a write that leaves the formula in place does not land. Writing a
value replaces the formula, as typing a number into the ShapeSheet does.
The library's own writes, which store the value a formula gives, keep it.
"""

import pytest

from vsdxkit.document import Document


def _conn_a(vsdx_copy):
    """test9's 'Conn A': a master instance whose own Width is GUARD(EndX-BeginX), with its own LineTo row 2."""
    return Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Conn A")


def test_a_cell_value_write_drops_the_formula(vsdx_copy):
    connector = _conn_a(vsdx_copy)
    width = connector.cells["Width"]
    assert width.formula == "GUARD(EndX-BeginX)"

    width.value = 2.5

    assert (width.value, width.formula) == ("2.5", None)


def test_a_geometry_cell_value_write_drops_the_formula(vsdx_copy):
    row = _conn_a(vsdx_copy).geometry.rows["2"]
    cell = row.cells["X"]
    cell.formula = "Width*1"

    cell.value = 1.5

    assert (cell.value, cell.formula) == ("1.5", None)


def test_a_geometry_row_coordinate_write_drops_the_formula(vsdx_copy):
    row = _conn_a(vsdx_copy).geometry.rows["2"]
    row.cells["X"].formula = "Width*1"

    row.x = 1.5

    assert (row.cells["X"].value, row.cells["X"].formula) == ("1.5", None)


def test_set_line_to_drops_the_formula(vsdx_copy):
    geometry = _conn_a(vsdx_copy).geometry
    geometry.rows["2"].cells["X"].formula = "Width*1"

    geometry.set_line_to(1.5, 0.0)

    assert geometry.rows["2"].cells["X"].formula is None


def test_the_formula_cache_keeps_the_formula_it_evaluates(vsdx_copy):
    """`_refresh_formula_values` writes the value a formula gives; dropping the formula would freeze it."""
    connector = _conn_a(vsdx_copy)
    expected = connector.end_x - connector.begin_x

    connector._refresh_formula_values()

    assert connector.cells["Width"].formula == "GUARD(EndX-BeginX)"
    assert float(connector.cells["Width"].value) == pytest.approx(expected)
