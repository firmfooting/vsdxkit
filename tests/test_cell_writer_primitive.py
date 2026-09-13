"""One primitive per operation, for creating or updating a named cell.

`set_cell_value` and `set_cell_formula` were copies of each other differing on
five lines, one of which declared the Visio namespace as a *prefix* rather than
as the default. The cell that copy produced sat outside the namespace, so the
shape could not find it again. Folding them onto one primitive is what stops
that recurring.
"""

import os

import pytest

from vsdx import VisioFile, namespace

basedir = os.path.dirname(os.path.realpath(__file__))


@pytest.fixture
def shape(vsdx_copy):
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        yield vis.pages[0].child_shapes[0]


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
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        vis.pages[0].child_shapes[0].set_cell_formula("Persisted", "Height*3")
        vis.save_vsdx(out)

    with VisioFile(out) as vis:
        cell = vis.pages[0].child_shapes[0].cells.get("Persisted")
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
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        shape = vis.pages[0].child_shapes[0]
        shape.get_or_create_cell(f"Escaped{label}", v=value)
        vis.save_vsdx(out)

    with VisioFile(out) as vis:
        assert vis.pages[0].child_shapes[0].cells[f"Escaped{label}"].value == value


@pytest.mark.parametrize("value", [5, 2.5, True])
def test_a_non_string_cell_value_is_coerced_before_it_reaches_the_tree(vsdx_copy, tmp_path, value):
    """Callers passed numbers when the builders used f-strings, which coerced for free.

    Building the element instead stores whatever it is given, and ElementTree
    refuses to serialise a non-string attribute -- at save, a long way from the
    call that caused it.
    """
    out = os.path.join(str(tmp_path), "out.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        vis.pages[0].child_shapes[0].get_or_create_cell("Coerced", v=value)
        vis.save_vsdx(out)

    with VisioFile(out) as vis:
        assert vis.pages[0].child_shapes[0].cells["Coerced"].value == str(value)
