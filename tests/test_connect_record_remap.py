"""Renumbering a shape must take everything that names it with it.

`VisioFile.renumber_shape_ids` is the code under test and carries the reasoning;
these pin it from the outside: a record naming the renumbered shape at either
end, a shape nested inside a renumbered group, the formulas elsewhere on the
page that address it, and the case where all of it must stay put because the id
is still in use. Issues #278 and #328.

Each test saves as well as asserting, so the package validator gets a look at
the result. A record naming a shape that is not there is its `dangling-glue`
defect and a formula naming one is `stale-sheet-reference`; renumbering produced
the first before #278 and the second before #328.
"""

import os
import xml.etree.ElementTree as ET

from vsdx import Shape, VisioFile, namespace


def _records(page) -> list[tuple[str | None, str | None]]:
    """Every Connect record on the page, as (FromSheet, ToSheet)."""
    return [(c.from_id, c.to_id) for c in page.connects]


def test_renumbering_a_shape_moves_the_records_glued_to_it(vsdx_copy, tmp_path):
    """The renumbered shape is the `ToSheet` of two connectors' records."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_id("2")
        assert ("6", "2") in _records(page) and ("7", "2") in _records(page)

        new_id = str(vis.increment_sub_shape_ids(shape, page)["2"])

        assert ("6", new_id) in _records(page)
        assert ("7", new_id) in _records(page)
        assert "2" not in [to_id for _, to_id in _records(page)]
        vis.save_vsdx(str(tmp_path / "renumbered_shape.vsdx"))


def test_renumbering_a_connector_moves_the_records_leading_from_it(vsdx_copy, tmp_path):
    """The renumbered shape is the `FromSheet`: it is the connector itself."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        connector = page.find_shape_by_id("7")

        new_id = str(vis.increment_sub_shape_ids(connector, page)["7"])

        from_ids = [from_id for from_id, _ in _records(page)]
        assert from_ids.count(new_id) == 2  # the connector's begin and end
        assert "7" not in from_ids
        vis.save_vsdx(str(tmp_path / "renumbered_connector.vsdx"))


def test_renumbering_a_group_moves_records_naming_a_shape_inside_it(vsdx_copy, tmp_path):
    """#275 widened the fault: the whole subtree is renumbered now, not the root alone."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[2]
        group = page.find_shape_by_id("1")
        child = group.child_shapes[0]
        old_child_id = child.ID
        page.connect_shapes(child, page.find_shape_by_id("11"))

        new_child_id = str(vis.increment_sub_shape_ids(group, page)[old_child_id])

        to_ids = [to_id for _, to_id in _records(page)]
        assert new_child_id in to_ids
        assert old_child_id not in to_ids
        vis.save_vsdx(str(tmp_path / "renumbered_group.vsdx"))


POINT_GLUE_FIXTURE = os.path.join("fixtures", "com_reference", "s07_point_glue_masters.vsdx")


def test_renumbering_a_shape_moves_the_formulas_elsewhere_that_name_it(vsdx_copy, tmp_path):
    """A connector's endpoint formulas follow the shape they name, not just its record.

    Shape 3 is a connector glued to shape 2: its record names shape 2 and so do
    the formulas that place its end. Renumbering shape 2 rewrote the record,
    because that sweep covers the page, and left the formulas, because that one
    covered only the subtree being renumbered (#328).
    """
    with VisioFile(vsdx_copy(POINT_GLUE_FIXTURE)) as vis:
        page = vis.pages[0]
        connector = page.find_shape_by_id("3")
        assert "Sheet.2!" in connector.cell_formula("EndX")

        new_id = str(vis.increment_sub_shape_ids(page.find_shape_by_id("2"), page)["2"])

        connector = page.find_shape_by_id("3")
        for cell in ("EndX", "EndY", "EndTrigger"):
            assert f"Sheet.{new_id}!" in connector.cell_formula(cell)
            assert "Sheet.2!" not in connector.cell_formula(cell)
        vis.save_vsdx(str(tmp_path / "renumbered_glued_shape.vsdx"))


def test_copying_a_shape_leaves_the_records_of_the_original_alone(vsdx_copy, tmp_path):
    """The copy is numbered afresh; the shape it was copied from is not moving."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        before = _records(page)

        page.find_shape_by_id("2").copy()

        assert _records(page) == before
        vis.save_vsdx(str(tmp_path / "copied_shape.vsdx"))


def test_copying_a_shape_leaves_the_formulas_naming_the_original_alone(vsdx_copy, tmp_path):
    """Nothing was vacated, so the page-wide sweep has nothing to rewrite.

    The copy takes new ids while the shape it came from keeps its own, and a
    formula elsewhere on the page still means the shape it always named.
    """
    with VisioFile(vsdx_copy(POINT_GLUE_FIXTURE)) as vis:
        page = vis.pages[0]
        before = page.find_shape_by_id("3").cell_formula("EndX")

        page.find_shape_by_id("2").copy()

        assert page.find_shape_by_id("3").cell_formula("EndX") == before
        vis.save_vsdx(str(tmp_path / "copied_glued_shape.vsdx"))


def _drop_shape(page, shape_id: str) -> None:
    """Remove a shape's element, leaving the records that name it behind.

    A page written by an older vsdx, or by this one before #278, can hold a
    record naming an id no shape carries. Forging one is how a test gets that
    file without shipping a broken fixture.
    """
    shapes = page.xml.getroot().find(f"{namespace}Shapes")
    shapes.remove(page.find_shape_by_id(shape_id).xml)


def test_a_copy_does_not_inherit_glue_from_a_record_naming_a_missing_shape(vsdx_copy):
    """An id this page never had was vacated by nobody, so its records stay put.

    Not saved: the page still holds the stale record it started with, which is
    the `dangling-glue` the validator is right to object to.
    """
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        _drop_shape(page, "2")
        assert ("6", "2") in _records(page)

        vis.copy_shape(vis.pages[1].find_shape_by_id("2").xml, page)

        assert ("6", "2") in _records(page)


def test_an_appended_shape_does_not_inherit_glue_from_a_record_naming_a_missing_shape(vsdx_copy):
    """Same rule for a shape that arrives carrying the missing id itself."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        _drop_shape(page, "2")
        arriving = Shape(xml=ET.fromstring(f'<Shape xmlns="{namespace[1:-1]}" ID="2" Type="Shape"/>'), parent=page, page=page)

        page._shapes[0].append_shape(arriving)

        assert ("6", "2") in _records(page)
        assert arriving.ID != "2"  # it was renumbered, it just did not take the glue
