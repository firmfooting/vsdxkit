"""One primitive per operation, for creating or updating a named cell.

`set_cell_value` and `set_cell_formula` were copies of each other differing on
five lines, one of which declared the Visio namespace as a *prefix* rather than
as the default. The cell that copy produced sat outside the namespace, so the
shape could not find it again. Folding them onto one primitive is what stops
that recurring.
"""

import os

import pytest

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError

FIXTURES = os.path.dirname(os.path.realpath(__file__))

S05 = "fixtures/com_reference/s05_swimlanes_cfflow.vsdx"


@pytest.fixture
def shape(vsdx_copy):
    vis = Document.open(vsdx_copy("test1.vsdx"))
    yield next(iter(vis.pages[0].children))


def test_a_created_formula_cell_is_in_the_visio_namespace(shape):
    """The cell must be findable afterwards, which needs the default namespace."""
    shape.set_cell_formula("NewFormulaCell", "Width*2")

    assert shape.xml.find(f'{namespace}Cell[@N="NewFormulaCell"]') is not None
    assert "NewFormulaCell" in shape.cells


def test_a_created_value_cell_is_in_the_visio_namespace(shape):
    shape.set_cell_value("NewValueCell", "42")

    assert shape.xml.find(f'{namespace}Cell[@N="NewValueCell"]') is not None
    assert "NewValueCell" in shape.cells


def test_setting_a_formula_then_a_value_updates_one_cell(shape):
    """Two writers, one cell: a ShapeSheet row cannot appear twice."""
    shape.set_cell_formula("SharedCell", "Width*2")
    shape.set_cell_value("SharedCell", "9")

    matches = shape.xml.findall(f'{namespace}Cell[@N="SharedCell"]')
    assert len(matches) == 1, f"expected one SharedCell row, found {len(matches)}"


def test_a_created_cell_survives_save_and_reload(vsdx_copy, tmp_path):
    out = os.path.join(str(tmp_path), "out.vsdx")
    vis = Document.open(vsdx_copy("test1.vsdx"))
    next(iter(vis.pages[0].children)).set_cell_formula("Persisted", "Height*3")
    vis.save(out)

    vis = Document.open(out)
    cell = next(iter(vis.pages[0].children)).cells.get("Persisted")
    assert cell is not None
    assert cell.formula == "Height*3"


@pytest.mark.parametrize(
    ("label", "value"),
    [("quote", 'say "hi"'), ("ampersand", "A & B"), ("bracket", "<tag>"), ("apostrophe", "it's")],
)
def test_a_cell_value_needing_escaping_round_trips(vsdx_copy, tmp_path, label, value):
    """Values are data, not markup.

    The cell builders formatted XML as a string, so a value carrying a quote,
    an ampersand or an angle bracket produced a ParseError. Shape Data and
    shape text routinely contain all three.
    """
    out = os.path.join(str(tmp_path), "out.vsdx")
    vis = Document.open(vsdx_copy("test1.vsdx"))
    shape = next(iter(vis.pages[0].children))
    shape.get_or_create_cell(f"Escaped{label}", v=value)
    vis.save(out)

    vis = Document.open(out)
    assert next(iter(vis.pages[0].children)).cells[f"Escaped{label}"].value == value


@pytest.mark.parametrize("value", [5, 2.5, True])
def test_a_non_string_cell_value_is_coerced_before_it_reaches_the_tree(vsdx_copy, tmp_path, value):
    """Callers passed numbers when the builders used f-strings, which coerced for free.

    Building the element instead stores whatever it is given, and ElementTree
    refuses to serialise a non-string attribute -- at save, a long way from the
    call that caused it.
    """
    out = os.path.join(str(tmp_path), "out.vsdx")
    vis = Document.open(vsdx_copy("test1.vsdx"))
    next(iter(vis.pages[0].children)).get_or_create_cell("Coerced", v=value)
    vis.save(out)

    vis = Document.open(out)
    assert next(iter(vis.pages[0].children)).cells["Coerced"].value == str(value)


def test_a_colour_set_on_a_master_instance_is_not_overridden_by_the_masters_formula(vsdx_copy):
    """#300: shape 35 inherits LineColor from a master whose cell is a THEMEVAL formula; Visio drew the theme colour."""
    shape = Document.open(vsdx_copy(S05)).pages[0].shapes.by_id("35")
    assert shape.cell_formula("LineColor").startswith("IF(LUM(THEMEVAL())")

    shape.line_color = "#ff0000"

    assert (shape.cells["LineColor"].value, shape.cells["LineColor"].formula) == ("#ff0000", None)


def test_a_colour_whose_own_cell_says_inherit_takes_the_value(vsdx_copy):
    """Shape 35's own FillForegnd is F="Inh", which Visio reads as take the master's formula."""
    shape = Document.open(vsdx_copy(S05)).pages[0].shapes.by_id("35")
    assert shape.cells["FillForegnd"].formula == "Inh"

    shape.fill_color = "#00ff00"

    assert shape.cells["FillForegnd"].formula is None


def test_get_or_create_cell_is_the_same_writer(vsdx_copy):
    """#319: get_or_create_cell created a bare cell while set_cell_value copied the master's formula down."""
    shape = Document.open(vsdx_copy(S05)).pages[0].shapes.by_id("35")

    cell = shape.get_or_create_cell("LineColor", v="#123456")

    assert (cell.value, cell.formula) == ("#123456", None)
    assert cell.xml is shape.xml.find(f'{namespace}Cell[@N="LineColor"]')


def test_the_writer_returns_the_cell_it_wrote(vsdx_copy):
    """get_or_create_cell hands back what _write_cell wrote, with no second lookup to fail."""
    shape = Document.open(vsdx_copy("test5_master.vsdx")).pages[0].shapes.by_id("5")

    created = shape._write_cell("BrandNew", v="1")
    in_a_row = shape._write_cell("Control/TextPosition/DynX", v="2.0")

    assert created.xml is shape.xml.find(f'{namespace}Cell[@N="BrandNew"]')
    assert (in_a_row.name, in_a_row.value) == ("DynX", "2.0")
    assert in_a_row.xml is shape.cells["Control/TextPosition/DynX"].xml


def test_a_section_cell_the_shape_lacks_is_refused_not_created_at_the_top(shape):
    """#319: a name holding '/' became a top-level <Cell N="Control/TextPosition/X">, which is no ShapeSheet cell."""
    cells_before = [element.get("N") for element in shape.xml.findall(f"{namespace}Cell")]

    with pytest.raises(InvalidOperationError, match="Control"):
        shape.set_cell_value("Control/TextPosition/X", 1.0)

    assert [element.get("N") for element in shape.xml.findall(f"{namespace}Cell")] == cells_before


def test_a_section_cell_the_shape_has_is_written_in_its_row(vsdx_copy):
    """test5_master shape 5 has its own Control row TextPosition, whose DynX is the formula TextPosition."""
    shape = Document.open(vsdx_copy("test5_master.vsdx")).pages[0].shapes.by_id("5")

    shape.set_cell_value("Control/TextPosition/DynX", 2.0)

    cell = shape.cells["Control/TextPosition/DynX"]
    assert (cell.value, cell.formula) == ("2.0", None)
    assert shape.xml.find(f'{namespace}Cell[@N="Control/TextPosition/DynX"]') is None


def test_set_start_and_finish_writes_the_controls_row_dyn_anchors(vsdx_copy):
    """#319: Visio names a Controls row's anchor cells XDyn/YDyn, not DynX/DynY; test9 Conn A has both rows Visio wrote."""
    shape = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Conn A")

    shape.set_start_and_finish((2.0, 7.0), (4.0, 7.0))

    text_x, text_y = shape.cells["TxtPinX"].value, shape.cells["TxtPinY"].value
    assert shape.cells["Control/TextPosition/XDyn"].value == shape.cells["Control/TextPosition/X"].value == text_x
    assert shape.cells["Control/TextPosition/YDyn"].value == shape.cells["Control/TextPosition/Y"].value == text_y


def test_the_glue_engine_keeps_the_formulas_it_writes(vsdx_copy):
    """The engine's CellWrite leaves the half it does not name as it is, so glue stays formula-driven."""
    page = Document.open(vsdx_copy("test8_simple_connector.vsdx")).pages[0]
    connector = page.connect(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))

    assert connector.cells["BeginX"].formula is not None
    assert connector.cells["EndX"].formula is not None
