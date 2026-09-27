"""A coordinate written to a glued connector end frees that end, as dragging it away does in Visio.

The value wins over the glue formula. A Connect record left naming the end
would have Visio pull it back on open, so the record and the end's trigger go
with the formula, and only that end's.
"""

import math
from xml.etree import ElementTree as ET

import pytest

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.shapes import _is_name_or_copy


@pytest.fixture
def glued(vsdx_copy):
    """test4 page 1: connector 6, its begin glued to shape 1 and its end to shape 2."""
    page = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0]
    connector = page.shapes.by_id("6")
    assert (connector.source.ID, connector.target.ID) == ("1", "2")
    return connector


def _records(connector) -> set[tuple[str, str | None]]:
    return {(record.from_id, record.from_rel) for record in connector._page._connects() if record.from_id == connector.ID}


def test_writing_begin_x_frees_the_begin_and_keeps_the_end_glued(glued):
    glued.begin_x = 1.0

    assert glued.source is None
    assert glued.target is not None and glued.target.ID == "2"
    assert _records(glued) == {("6", "EndX")}
    assert (glued.cells["BeginX"].value, glued.cells["BeginX"].formula) == ("1.0", None)
    assert glued.cells["EndX"].formula is not None
    assert "BegTrigger" not in glued.cells


def test_writing_begin_x_removes_the_begintrigger_earlier_releases_wrote(glued):
    """Point glue before #106 wrote a `BeginTrigger` naming the begin's shape; freeing the begin takes it too."""
    glued.get_or_create_cell("BeginTrigger", f="_XFTRIGGER(Sheet1!EventXFMod)")

    glued.begin_x = 1.0

    assert "BeginTrigger" not in glued.cells
    assert glued.xml.find('.//{*}Cell[@N="BeginTrigger"]') is None


def test_writing_end_x_leaves_the_begintrigger_to_the_begin(glued):
    glued.get_or_create_cell("BeginTrigger", f="_XFTRIGGER(Sheet1!EventXFMod)")

    glued.end_x = 1.0

    assert glued.cells["BeginTrigger"].formula == "_XFTRIGGER(Sheet1!EventXFMod)"


def _state(connector) -> tuple[set[tuple[str, str | None]], dict[str, str | None]]:
    """The connector's glue records and every cell formula it holds, the two things freeing an end changes."""
    return _records(connector), {name: cell.formula for name, cell in connector.cells.items()}


@pytest.mark.parametrize("setter", ["begin_x", "begin_y", "end_x", "end_y"])
def test_a_refused_end_write_leaves_the_end_glued(glued, setter):
    """The value is refused before the end is freed, so the connector is as it was."""
    before = _state(glued)
    assert before[0] == {("6", "BeginX"), ("6", "EndX")}

    with pytest.raises(TypeError):
        setattr(glued, setter, None)

    assert _state(glued) == before


@pytest.mark.parametrize(
    ("start", "finish", "error"),
    [
        ((None, 1.0), (2.0, 2.0), InvalidOperationError),
        ((1.0, 1.0), (2.0, None), InvalidOperationError),
        (("one", 1.0), (2.0, 2.0), TypeError),
    ],
)
def test_a_refused_set_start_and_finish_leaves_both_ends_glued(glued, start, finish, error):
    before = _state(glued)

    with pytest.raises(error):
        glued.set_start_and_finish(start, finish)

    assert _state(glued) == before


@pytest.mark.parametrize(
    ("start", "finish"),
    [((2.0, "bad"), (3.0, 8.0)), ((2.0, 7.0), (3.0, "bad"))],
    ids=["start_y", "finish_y"],
)
@pytest.mark.parametrize("which", ["glued connector", "plain line"])
def test_an_invalid_y_is_refused_before_anything_is_written(vsdx_copy, which, start, finish):
    """A plain line never works out ``finish_y - start_y``, so its Y has to be checked before the first write."""
    if which == "glued connector":
        shape = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0].shapes.by_id("6")
    else:
        shape = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Line A")
    xml_before, records_before = ET.tostring(shape.xml), _records(shape)

    with pytest.raises(TypeError):
        shape.set_start_and_finish(start, finish)

    assert (ET.tostring(shape.xml), _records(shape)) == (xml_before, records_before)


def test_writing_end_y_frees_the_end(glued):
    glued.end_y = 3.0

    assert glued.source is not None
    assert glued.target is None
    assert _records(glued) == {("6", "BeginX")}


def test_set_start_and_finish_frees_both_ends(glued):
    glued.set_start_and_finish((1.0, 1.0), (2.0, 2.0))

    assert (glued.source, glued.target) == (None, None)
    assert _records(glued) == set()


def test_connect_still_glues_both_ends(vsdx_copy):
    """The engine places the ends it glues through `_place_ends`, which keeps its glue."""
    page = Document.open(vsdx_copy("test8_simple_connector.vsdx")).pages[0]
    source, target = page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B")

    connector = page.connect(source, target)

    assert (connector.source, connector.target) == (source, target)


def test_retarget_still_glues(glued):
    page = glued._page
    other = page.shapes.by_id("5")

    glued.retarget(target=other)

    assert (glued.source.ID, glued.target.ID) == ("1", "5")


def test_a_diagonal_plain_line_keeps_its_length_formula(vsdx_copy):
    """test9 'Line A' is a plain line: its Width is a formula of its ends, which set_start_and_finish keeps."""
    line = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Line A")
    width_formula = line.cell_formula("Width")

    line.set_start_and_finish((2.0, 7.0), (3.0, 8.0))

    assert line.cell_formula("Width") == width_formula


def test_a_plain_lines_text_pin_is_in_its_own_coordinates(vsdx_copy):
    """test5_master shape 5 is a Lucidchart line, not named 'Dynamic connector': its text pin was set in the page's coordinates."""
    line = Document.open(vsdx_copy("test5_master.vsdx")).pages[0].shapes.by_id("5")

    line.set_start_and_finish((1.0, 7.5), (3.0, 7.5))

    assert float(line.cells["TxtPinX"].value) == pytest.approx(1.0)
    assert float(line.cells["TxtPinY"].value) == pytest.approx(0.0)
    assert float(line.cells["Control/TextPosition/X"].value) == pytest.approx(1.0)


def test_set_start_and_finish_refuses_a_2d_shape(vsdx_copy):
    """#301: it did nothing, silently, on a shape with no ends."""
    shape = Document.open(vsdx_copy("test1.vsdx")).pages[0].shapes.require_id("1")
    before = shape.x

    with pytest.raises(InvalidOperationError, match="2-D"):
        shape.set_start_and_finish((1.0, 1.0), (2.0, 2.0))

    assert shape.x == before


def _placed(line) -> dict[str, float]:
    return {name: float(line.cell_value(name)) for name in ("Width", "Height", "Angle", "PinX", "PinY", "TxtPinX", "TxtPinY")}


def test_a_diagonal_plain_line_is_as_long_as_its_ends_are_apart_with_its_text_at_its_middle(vsdx_copy):
    """test5_master shape 5 has no Width or Angle formula: it was given `finish_x - start_x`, 3, and no angle.

    A 3-by-4 placement is a line 5 long, pointing from start to finish, with
    its pin and its text at its middle, as Visio's own lines hold it (test9
    'Line A': Width is SQRT(...), Angle ATAN2(...), PinX (BeginX+EndX)/2).
    """
    line = Document.open(vsdx_copy("test5_master.vsdx")).pages[0].shapes.by_id("5")
    assert (line.cell_formula("Width"), line.cell_formula("Angle")) == (None, None)

    line.set_start_and_finish((1.0, 7.0), (4.0, 11.0))

    assert _placed(line) == pytest.approx(
        {"Width": 5.0, "Height": 0.0, "Angle": math.atan2(4.0, 3.0), "PinX": 2.5, "PinY": 9.0, "TxtPinX": 2.5, "TxtPinY": 0.0}
    )
    assert (line.begin_x, line.begin_y, line.end_x, line.end_y) == (1.0, 7.0, 4.0, 11.0)
    assert float(line.cells["Control/TextPosition/X"].value) == pytest.approx(2.5)


def test_a_diagonal_plain_lines_local_pin_follows_its_width(vsdx_copy):
    """Case 05b: shape 5's LocPinX is `Width*0.499973064698594`, which kept its old width's value, 0.9281.

    Visio 16 recomputes it to 2.49986 on open for the 5-inch line; the value
    beside the formula is what other consumers read.
    """
    line = Document.open(vsdx_copy("test5_master.vsdx")).pages[0].shapes.by_id("5")
    assert line.cell_formula("LocPinX") == "Width*0.499973064698594"

    line.set_start_and_finish((1.0, 7.0), (4.0, 11.0))

    assert float(line.cell_value("LocPinX")) == pytest.approx(5.0 * 0.499973064698594)


def test_a_plain_line_placed_right_to_left_points_left(vsdx_copy):
    line = Document.open(vsdx_copy("test5_master.vsdx")).pages[0].shapes.by_id("5")

    line.set_start_and_finish((4.0, 7.0), (1.0, 7.0))

    assert _placed(line) == pytest.approx(
        {"Width": 3.0, "Height": 0.0, "Angle": math.pi, "PinX": 2.5, "PinY": 7.0, "TxtPinX": 1.5, "TxtPinY": 0.0}
    )


def test_a_connector_named_otherwise_keeps_the_height_its_formula_gives(vsdx_copy):
    """test4 shape 7 is a dynamic connector with no NameU, so the name test calls it a plain line.

    Its GUARD(0DA) Angle keeps it square and its GUARD(EndY-BeginY) Height is
    its y span: the geometry and the text pin follow that height, where they
    took the 0 written for a plain line, and no angle is written over the formula.
    """
    connector = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0].shapes.require_id("7")
    assert connector.universal_name != "Dynamic connector"

    connector.set_start_and_finish((1.0, 2.0), (4.0, 6.0))

    assert (connector.height, connector.angle, connector.cell_formula("Angle")) == (4.0, 0.0, "GUARD(0DA)")
    assert (float(connector.cell_value("TxtPinX")), float(connector.cell_value("TxtPinY"))) == (1.5, 2.0)
    assert (connector.geometry.rows["2"].x, connector.geometry.rows["2"].y) == (3.0, 4.0)


def test_a_connector_named_otherwise_with_its_angle_written_is_not_turned(vsdx_copy):
    """test4 shape 7 has no NameU; with a value written over its Angle it was turned as a plain line (#455 review).

    Its Width and Height are still formulas, so it is not a line whose size
    and angle only its placement decides: it keeps its spans, and no angle is
    written, where the plain-line branch gave it a length of 5 and ATAN2(4, 3).
    """
    connector = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0].shapes.require_id("7")
    connector.set_cell_value("Angle", 0)
    assert connector.cell_formula("Angle") is None

    connector.set_start_and_finish((1.0, 2.0), (4.0, 6.0))

    assert (connector.width, connector.height, connector.angle) == (3.0, 4.0, 0.0)
    assert (connector.geometry.rows["2"].x, connector.geometry.rows["2"].y) == (3.0, 4.0)


def test_a_plain_lines_text_pin_follows_the_width_its_formula_gives(vsdx_copy):
    """test9 'Line A' has Width SQRT(...): a text pin with no formula is set from the width the refresh computes, not from `finish_x - start_x`."""
    line = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Line A")
    line.set_cell_value("TxtPinX", "0")
    line.set_cell_value("TxtPinY", "0")

    line.set_start_and_finish((1.0, 1.0), (4.0, 5.0))

    assert (line.cell_formula("Width"), line.cell_formula("Angle")) == (
        "SQRT((EndX-BeginX)^2+(EndY-BeginY)^2)",
        "ATAN2(EndY-BeginY,EndX-BeginX)",
    )
    assert _placed(line) == pytest.approx(
        {"Width": 5.0, "Height": 0.0, "Angle": math.atan2(4.0, 3.0), "PinX": 2.5, "PinY": 3.0, "TxtPinX": 2.5, "TxtPinY": 0.0}
    )


S05 = "fixtures/com_reference/s05_swimlanes_cfflow.vsdx"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Dynamic connector", True),
        ("Dynamic connector.58", True),
        ("Dynamic connector.", False),
        ("Dynamic connector.backup", False),
        ("Dynamic connector.5.8", False),
        ("Dynamic connectors.58", False),
        ("Dynamic", False),
        (None, False),
    ],
)
def test_a_numbered_copy_of_a_name_has_only_digits_after_the_dot(name, expected):
    assert _is_name_or_copy(name, "Dynamic connector") is expected


def test_a_connector_with_a_suffixed_name_is_placed_as_a_connector(vsdx_copy):
    """s05 shape 58 is `Dynamic connector.58`, Visio's name for a second connector; with its Angle formula gone it was turned as a plain line.

    Its ends 3 across and 2 up make a connector 3 wide and 2 high, with no
    angle, where the plain-line branch made a line 3.6 long turned by
    ATAN2(2, 3).
    """
    connector = Document.open(vsdx_copy(S05)).pages[0].shapes.require_id("58")
    assert connector.universal_name == "Dynamic connector.58"
    connector.set_cell_value("Angle", 0)
    assert connector.cell_formula("Angle") is None

    connector.set_start_and_finish((1.0, 1.0), (4.0, 3.0))

    assert (connector.width, connector.height, connector.angle) == (3.0, 2.0, 0.0)
    assert (connector.geometry.rows["2"].x, connector.geometry.rows["2"].y) == (3.0, 2.0)


def test_a_connector_with_a_suffixed_name_keeps_its_height(vsdx_copy):
    """With its inherited GUARD(0DA) in place it was not turned, but it took a plain line's height of 0."""
    connector = Document.open(vsdx_copy(S05)).pages[0].shapes.require_id("58")

    connector.set_start_and_finish((1.0, 1.0), (4.0, 3.0))

    assert (connector.width, connector.height) == (3.0, 2.0)
    assert (connector.geometry.rows["2"].x, connector.geometry.rows["2"].y) == (3.0, 2.0)
