"""A coordinate written to a glued connector end frees that end, as dragging it away does in Visio.

The value wins over the glue formula. A Connect record left naming the end
would have Visio pull it back on open, so the record and the end's trigger go
with the formula, and only that end's.
"""

import pytest

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError


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
