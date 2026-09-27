"""Moving a shape moves the shape (#430).

The geometry's rows are in the shape's own coordinates, so they stay put when
the shape moves. A 2-D shape moves by its pin; a 1-D shape by its two ends,
from which its pin, width and angle follow.
"""

import xml.etree.ElementTree as ET

import pytest

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.shape_kind import ShapeKind


def _rows(shape) -> list[dict[str, str]]:
    section = shape.xml.find(f'{namespace}Section[@N="Geometry"]')
    if section is None:
        return []
    return [
        {cell.get("N"): cell.get("V") for cell in row.findall(f"{namespace}Cell")}
        for row in section.findall(f"{namespace}Row")
    ]


def test_a_2d_shape_moves_by_its_pin_and_its_outline_stays_on_it(vsdx_copy):
    """A palette PROCESS shape draws its outline with absolute MoveTo/LineTo rows.

    test1's own 2-D shapes draw with relative rows instead, which the old
    move never touched, so they cannot show #430's bug: the old move shifted
    exactly the absolute rows this shape has, drawing its outline off it.
    """
    page = Document.open(vsdx_copy("test1.vsdx")).pages[0]
    shape = page.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0)
    rows, x, y = _rows(shape), shape.x, shape.y

    shape.move(1.0, 2.0)

    assert (shape.x, shape.y) == pytest.approx((x + 1.0, y + 2.0))
    assert _rows(shape) == rows


def test_a_moved_pin_loses_a_formula_it_had(vsdx_copy):
    """As dragging a shape does in Visio: the pin written is the pin shown."""
    shape = Document.open(vsdx_copy("test1.vsdx")).pages[0].shapes.require_id("1")
    shape.set_cell_formula("PinX", "GUARD(1)")

    shape.move(1.0, 0.0)

    assert shape.cells["PinX"].formula is None


def test_a_1d_shape_moves_both_ends_and_keeps_its_geometry(vsdx_copy):
    """#430: move shifted the begin and the geometry rows and left the end behind."""
    connector = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Conn A")
    begin, end, rows = (connector.begin_x, connector.begin_y), (connector.end_x, connector.end_y), _rows(connector)

    connector.move(1.0, 2.0)

    assert (connector.begin_x, connector.begin_y) == pytest.approx((begin[0] + 1.0, begin[1] + 2.0))
    assert (connector.end_x, connector.end_y) == pytest.approx((end[0] + 1.0, end[1] + 2.0))
    assert _rows(connector) == rows
    assert (connector.x, connector.y) == pytest.approx(((begin[0] + end[0]) / 2 + 1.0, (begin[1] + end[1]) / 2 + 2.0))


def test_moving_a_glued_connector_frees_both_ends(vsdx_copy):
    """As dragging a glued connector's body does in Visio."""
    connector = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0].shapes.by_id("6")

    connector.move(0.5, 0.5)

    assert (connector.source, connector.target) == (None, None)


def _connector_state(connector):
    """Everything a move can change on a glued connector: its element, cells and formulas included, and its records."""
    records = sorted((c.from_id, c.from_rel, c.to_id, c.to_rel) for c in connector._page._connects())
    return ET.tostring(connector.xml), records


def test_a_zero_move_of_a_glued_connector_changes_nothing(vsdx_copy):
    """Moving by nothing wrote all four ends, which freed both glued ends and dropped their formulas."""
    connector = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0].shapes.by_id("6")
    before = _connector_state(connector)

    connector.move(0, 0.0)

    assert _connector_state(connector) == before
    assert (connector.source.ID, connector.target.ID) == ("1", "2")


def test_a_zero_move_of_a_2d_shape_keeps_its_pin_formula(vsdx_copy):
    shape = Document.open(vsdx_copy("test1.vsdx")).pages[0].shapes.require_id("1")
    shape.set_cell_formula("PinX", "GUARD(1)")
    before = ET.tostring(shape.xml)

    shape.move(0.0, 0)

    assert ET.tostring(shape.xml) == before


@pytest.mark.parametrize("delta", [(1.0, 1.0), (0.0, 0.0)])
@pytest.mark.parametrize("text", ["Rect A", "Conn A"])
def test_moving_a_deleted_shape_is_refused_as_a_move(vsdx_copy, text, delta):
    """It was refused only by the first cell it read, so the message spoke of reading cell BeginX."""
    shape = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text(text)
    shape.delete()

    with pytest.raises(InvalidOperationError, match=r"^Shape\.move\(\) refused"):
        shape.move(*delta)


def _cell_element(shape, name):
    return shape.xml.find(f'{namespace}Cell[@N="{name}"]')


def test_a_1d_shape_missing_an_end_is_refused_rather_than_moved_by_its_pin(vsdx_copy):
    """`Line A` is 1-D, by the one test of that, `_is_one_d`; with no EndX it has no end to move.

    move used to decide by whether all four ends read, so it took this line for
    2-D and moved its pin, which Visio derives from the ends and puts back.
    """
    line = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Line A")
    line.xml.remove(_cell_element(line, "EndX"))
    pin = (line.x, line.y)

    with pytest.raises(InvalidOperationError, match=rf"shape ID {line.ID} .*EndX.*set_start_and_finish"):
        line.move(1.0, 1.0)

    assert (line.x, line.y) == pin


def test_set_start_and_finish_places_a_1d_shape_whose_begin_has_no_value(vsdx_copy):
    """`_is_one_d` says 1-D where a BeginX cell exists; `_place_ends` refused it as 2-D because the cell read None."""
    line = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Line A")
    del _cell_element(line, "BeginX").attrib["V"]
    assert line.begin_x is None

    line.set_start_and_finish((1.0, 2.0), (3.0, 2.0))

    assert (line.begin_x, line.begin_y, line.end_x, line.end_y) == (1.0, 2.0, 3.0, 2.0)


def test_a_none_end_is_refused_naming_the_shape(vsdx_copy):
    line = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Line A")

    with pytest.raises(InvalidOperationError, match=rf"^shape ID {line.ID}: start and finish coordinates cannot be None"):
        line.set_start_and_finish((None, 1.0), (2.0, 2.0))
