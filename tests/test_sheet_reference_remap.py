"""Copying shapes must remap every `Sheet.N` / `SheetN` reference in a formula.

`update_ids` used to rewrite a formula only when it began with the literal
`Sheet.`, which covers ordinary inherited cells but not the forms the connector
engine writes: `_XFTRIGGER(Sheet5!EventXFMod)` and
`PAR(PNT(Sheet5!Connections.X1,Sheet5!Connections.Y1))` carry no dot and are
never at the start. Copied connectors therefore kept pointing at the source
shapes and Visio silently dropped the glue.
"""

import os
import xml.etree.ElementTree as ET

from vsdx import VisioFile, namespace

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def _formula(shape, cell_name: str) -> str:
    cell = shape.xml.find(f'{namespace}Cell[@N="{cell_name}"]')
    assert cell is not None, f"{cell_name} cell missing"
    return cell.attrib.get("F", "")


POINT_GLUE_FIXTURE = os.path.join(FIXTURES, "fixtures", "com_reference", "s05_swimlanes_cfflow.vsdx")


def test_update_ids_remaps_shape_glue_trigger_formulas(vsdx_copy):
    """`_XFTRIGGER(SheetN!EventXFMod)` carries no dot and is not at the start."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        start = vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="A")
        end = vis.create_shape(page, "PALETTE_PROCESS", 6.0, 2.0, text="B")
        connector = page.connect_shapes(start, end)

        shapes_element = page.xml.getroot().find(f"{namespace}Shapes")
        vis.update_ids(shapes_element, {start.ID: 900, end.ID: 901})

        assert _formula(connector, "BegTrigger") == "_XFTRIGGER(Sheet900!EventXFMod)"
        assert _formula(connector, "EndTrigger") == "_XFTRIGGER(Sheet901!EventXFMod)"


def test_update_ids_remaps_point_glue_formulas():
    """A point-glue formula carries two references to the same shape."""
    with VisioFile(POINT_GLUE_FIXTURE) as vis:
        page = vis.pages[0]
        start = page.find_shape_by_id("90")
        end = page.find_shape_by_id("97")
        connector = page.connect_shapes(start, end, route="point")

        shapes_element = page.xml.getroot().find(f"{namespace}Shapes")
        vis.update_ids(shapes_element, {start.ID: 900, end.ID: 901})

        assert _formula(connector, "BeginX") == "PAR(PNT(Sheet900!Connections.X1,Sheet900!Connections.Y1))"
        assert _formula(connector, "EndY") == "PAR(PNT(Sheet901!Connections.X1,Sheet901!Connections.Y1))"
        assert _formula(connector, "BeginTrigger") == "_XFTRIGGER(Sheet900!EventXFMod)"


def test_update_ids_leaves_references_outside_the_copy_untouched(vsdx_copy):
    """A reference to a shape that is not being copied must not be rewritten."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        start = vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="A")
        end = vis.create_shape(page, "PALETTE_PROCESS", 6.0, 2.0, text="B")
        connector = page.connect_shapes(start, end)

        shapes_element = page.xml.getroot().find(f"{namespace}Shapes")
        vis.update_ids(shapes_element, {start.ID: 900})

        assert "Sheet900!" in _formula(connector, "BegTrigger")
        assert f"Sheet{end.ID}!" in _formula(connector, "EndTrigger")


def test_update_ids_matches_whole_ids_only(vsdx_copy):
    """`Sheet.1` must not be rewritten because `Sheet.12` is in the id map."""
    shapes = ET.fromstring(
        f'<Shapes xmlns="{namespace[1:-1]}"><Shape ID="12"><Cell N="Width" F="Sheet.1!Width+Sheet.12!Width"/></Shape></Shapes>'
    )
    with VisioFile(os.path.join(FIXTURES, "test1.vsdx")) as vis:
        vis.update_ids(shapes, {"12": 700})
    cell = shapes.find(f"{namespace}Shape/{namespace}Cell")
    # the reference form is preserved; only the id changes
    assert cell.attrib["F"] == "Sheet.1!Width+Sheet.700!Width"


def test_update_ids_leaves_a_reference_to_another_pages_sheet_alone():
    """`Pages[Page-2]!Sheet.1!` names a sheet on that page, which this map is not about.

    Ids are page-scoped, so the number after a `Pages[...]!` prefix belongs to
    the page named in front of it, and rewriting it repoints the reference at a
    shape on a page this call never looked at. Only reachable since #328 made
    the sweep cover the whole page: a cross-page reference is written by some
    shape other than the one being renumbered.
    """
    shapes = ET.fromstring(
        f'<Shapes xmlns="{namespace[1:-1]}">'
        f'<Shape ID="9"><Cell N="Width" F="Pages[Page-2]!Sheet.1!Width+Sheet.1!Height"/></Shape>'
        f"</Shapes>"
    )
    with VisioFile(os.path.join(FIXTURES, "test1.vsdx")) as vis:
        vis.update_ids(shapes, {"1": 700})
    cell = shapes.find(f"{namespace}Shape/{namespace}Cell")
    assert cell.attrib["F"] == "Pages[Page-2]!Sheet.1!Width+Sheet.700!Height"


def test_update_ids_remaps_the_copied_shapes_own_cells(vsdx_copy):
    """A group's own formulas are part of the copy, not only its children's."""
    shapes = ET.fromstring(
        f'<Shapes xmlns="{namespace[1:-1]}">'
        f'<Shape ID="1"><Cell N="Width" F="Sheet.2!Width"/>'
        f'<Shapes><Shape ID="2"><Cell N="Height" F="Sheet.1!Height"/></Shape></Shapes>'
        f"</Shape></Shapes>"
    )
    with VisioFile(os.path.join(FIXTURES, "test1.vsdx")) as vis:
        vis.update_ids(shapes, {"1": 800, "2": 801})
    group = shapes.find(f"{namespace}Shape")
    assert group.find(f'{namespace}Cell[@N="Width"]').attrib["F"] == "Sheet.801!Width"
    child = group.find(f"{namespace}Shapes/{namespace}Shape")
    assert child.find(f'{namespace}Cell[@N="Height"]').attrib["F"] == "Sheet.800!Height"


def test_copying_a_group_remaps_its_children_references(vsdx_copy):
    """End to end: the master group in test5 references its own shape ID."""
    with VisioFile(vsdx_copy("test5_master.vsdx")) as vis:
        page = vis.pages[0]
        group = page.child_shapes[0]
        referenced = {
            cell.attrib["F"] for shape in group.xml.iter(f"{namespace}Cell") for cell in [shape] if "F" in shape.attrib
        }
        assert any("Sheet." in formula for formula in referenced), "fixture is expected to carry sheet references"

        copied = group.copy()

        stale = [
            cell.attrib["F"]
            for cell in copied.xml.iter(f"{namespace}Cell")
            if f"Sheet.{group.ID}!" in cell.attrib.get("F", "")
        ]
        assert stale == []


def test_copy_page_keeps_connector_glue(vsdx_copy):
    """Shape ids are page-scoped, so a page copy keeps them and stays glued.

    `copy_page` clones the page part verbatim rather than reallocating ids, so
    there is nothing for the remapper to do here; this guards that the two
    mechanisms do not start fighting each other.
    """
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        start = vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="A")
        end = vis.create_shape(page, "PALETTE_PROCESS", 6.0, 2.0, text="B")
        connector = page.connect_shapes(start, end)
        expected = {
            "BegTrigger": _formula(connector, "BegTrigger"),
            "EndTrigger": _formula(connector, "EndTrigger"),
        }

        copied = vis.copy_page(page)

        copied_connector = copied.find_shape_by_id(connector.ID)
        assert copied_connector is not None
        assert {name: _formula(copied_connector, name) for name in expected} == expected
        connects = [c for c in copied.connects if c.from_id == connector.ID]
        assert len(connects) == 2
