"""Setters whose target element is optional in the document.

`Shape.text_color` wrote only into a `Section[@N="Character"]/Row/Cell[@N="Color"]`
that already existed. Most shapes have no such cell -- fifteen of the seventeen
on page 1 of the three fixtures below -- so the assignment was a silent no-op,
while `line_color` and `fill_color`, which go through `set_cell_value`, created
the cell they needed. `Container.set_lane_label` had the same shape from the other
side: it dropped the `False` that `set_user_row_value` returns for a lane with
no `visHeadingText` row (issue #263).
"""

import os
import xml.etree.ElementTree as ET

import pytest

from vsdx import VisioFile, namespace
from vsdx.containers import ROW_HEADING_TEXT, get_user_row

CFF_FIXTURE = "fixtures/com_reference/s05_swimlanes_cfflow.vsdx"

# Shape IDs measured to carry no Character/Color cell of their own. Named one by
# one rather than discovered at run time: a fixture that quietly gained a
# Character section would otherwise shrink this test to nothing.
SHAPES_WITHOUT_A_CHARACTER_COLOUR = [
    ("test1.vsdx", "1"),
    ("test1.vsdx", "2"),
    ("test1.vsdx", "5"),
    ("test1.vsdx", "6"),
    ("test12_colors.vsdx", "1"),
    ("test12_colors.vsdx", "5"),
    ("test3_house.vsdx", "1"),
    ("test3_house.vsdx", "5"),
    ("test3_house.vsdx", "8"),
    ("test3_house.vsdx", "9"),
]


def colour_cells(shape) -> list[ET.Element]:
    """The shape's own Character-section colour cells, read straight from its XML."""
    return shape.xml.findall(f'{namespace}Section[@N="Character"]/{namespace}Row/{namespace}Cell[@N="Color"]')


def character_runs(shape) -> list[ET.Element]:
    text = shape.xml.find(f"{namespace}Text")
    return text.findall(f"{namespace}cp") if text is not None else []


@pytest.mark.parametrize(("filename", "shape_id"), SHAPES_WITHOUT_A_CHARACTER_COLOUR)
def test_text_color_reaches_a_shape_that_has_no_character_cell(filename, shape_id, basedir, vsdx_copy, tmp_path):
    """The write has to land, and has to still be there after a save."""
    out_file = os.path.join(str(tmp_path), "out.vsdx")
    with VisioFile(os.path.join(basedir, filename)) as vis:
        shape = vis.pages[0].find_shape_by_id(shape_id)
        assert colour_cells(shape) == [], "fixture already carries the cell; this case proves nothing"

        shape.text_color = "#00ff00"

        assert shape.text_color == "#00ff00"
        vis.save_vsdx(out_file)

    with VisioFile(out_file) as vis:
        assert vis.pages[0].find_shape_by_id(shape_id).text_color == "#00ff00"


@pytest.mark.parametrize(("filename", "shape_id"), SHAPES_WITHOUT_A_CHARACTER_COLOUR)
def test_a_created_character_row_is_referenced_by_a_run(filename, shape_id, basedir):
    """A Character row only formats text that a `cp` run points at.

    Visio writes the row and the run together: of the 33 Character rows in the
    com_reference captures, the only twelve with no run belong to shapes that
    carry no Text element at all. A row nothing references is markup Visio
    reads and then ignores, which would leave the setter as silent as it was
    before.
    """
    with VisioFile(os.path.join(basedir, filename)) as vis:
        shape = vis.pages[0].find_shape_by_id(shape_id)
        text_before = shape.text

        shape.text_color = "#00ff00"

        row = shape.xml.find(f'{namespace}Section[@N="Character"]/{namespace}Row')
        assert row is not None, "no Character row was created to reference"
        runs = character_runs(shape)
        if shape.xml.find(f"{namespace}Text") is None:
            assert runs == [], "a shape with no text of its own needs no run"
        else:
            assert [run.attrib.get("IX") for run in runs] == [row.attrib.get("IX")]
        assert shape.text == text_before, "colouring text must not rewrite it"


def test_text_color_updates_the_existing_cell_in_place(basedir):
    """An existing cell is updated, not duplicated, and the runs are left alone."""
    with VisioFile(os.path.join(basedir, "test12_colors.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_id("2")
        runs_before = [run.attrib.get("IX") for run in character_runs(shape)]

        shape.text_color = "#0000ff"

        assert len(shape.xml.findall(f'{namespace}Section[@N="Character"]')) == 1
        assert [cell.attrib.get("V") for cell in colour_cells(shape)] == ["#0000ff"]
        assert [run.attrib.get("IX") for run in character_runs(shape)] == runs_before
        # the cell keeps the formula that produced its old value, so Visio
        # recomputes over this write. Pinned rather than fixed: it is the same
        # for line_color and fill_color, and issue #300 covers all three
        assert colour_cells(shape)[0].attrib.get("F") == "THEMEGUARD(RGB(255,0,0))"


def test_text_color_fills_in_a_character_row_that_has_no_colour_cell(basedir):
    """A Character section may exist for an unrelated attribute, e.g. font size."""
    with VisioFile(os.path.join(basedir, "test1.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_id("1")
        section = ET.SubElement(shape.xml, f"{namespace}Section", {"N": "Character"})
        ET.SubElement(ET.SubElement(section, f"{namespace}Row", {"IX": "0"}), f"{namespace}Cell", {"N": "Size", "V": "0.16"})

        shape.text_color = "#00ff00"

        assert len(shape.xml.findall(f'{namespace}Section[@N="Character"]/{namespace}Row')) == 1
        assert [cell.attrib.get("V") for cell in colour_cells(shape)] == ["#00ff00"]


def test_text_color_lands_on_the_row_the_text_actually_names(vsdx_copy):
    """A Character section may hold a row the visible text does not use.

    `s05_swimlanes_cfflow.vsdx` shape 37 carries one row, IX 1, which formats
    only the empty tail after its second run. Writing into the first row found
    colours nothing, which is issue #263 by another route.
    """
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        shape = vis.pages[0].find_shape_by_id("37")
        runs = [run.attrib.get("IX") for run in character_runs(shape)]
        assert runs and runs[0] != "1", "fixture no longer has a row the first run does not name"

        shape.text_color = "#00ff00"

        rows = shape.xml.findall(f'{namespace}Section[@N="Character"]/{namespace}Row')
        coloured = {row.attrib.get("IX"): row.find(f'{namespace}Cell[@N="Color"]') for row in rows}
        assert coloured[runs[0]] is not None, "the run that formats the visible text has no colour"
        assert coloured[runs[0]].attrib.get("V") == "#00ff00"
        indices = [int(row.attrib["IX"]) for row in rows]
        assert indices == sorted(indices), "Visio writes Character rows in IX order"
        assert [int(row.attrib["IX"]) for row in rows] == sorted(int(row.attrib["IX"]) for row in rows)


def test_text_color_follows_a_run_that_names_a_row_out_of_range(basedir):
    """The row index comes from the text, not from counting from zero."""
    with VisioFile(os.path.join(basedir, "test1.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_id("1")
        text = shape.xml.find(f"{namespace}Text")
        run = ET.Element(f"{namespace}cp", {"IX": "3"})
        run.tail, text.text = text.text, None
        text.insert(0, run)

        shape.text_color = "#00ff00"

        rows = shape.xml.findall(f'{namespace}Section[@N="Character"]/{namespace}Row')
        assert [row.attrib.get("IX") for row in rows] == ["3"]
        assert shape.text_color == "#00ff00"


def test_a_created_section_goes_where_visio_puts_one(vsdx_copy):
    """A group holds its children in `Shapes`, and no section follows that."""
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        lane = vis.pages[0].get_container().lanes[0]
        assert lane.xml.find(f"{namespace}Shapes") is not None, "fixture lane is no longer a group"
        assert lane.xml.find(f'{namespace}Section[@N="Geometry"]') is None

        lane.text_color = "#00ff00"

        tags = [child.tag for child in lane.xml]
        last_section = max(i for i, tag in enumerate(tags) if tag == f"{namespace}Section")
        assert last_section < tags.index(f"{namespace}Shapes")


def test_a_rejected_colour_leaves_the_shape_untouched(basedir):
    """A setter that raises must not have half-written first."""
    with VisioFile(os.path.join(basedir, "test1.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_id("1")
        before = ET.tostring(shape.xml)

        with pytest.raises(TypeError):
            shape.text_color = None

        assert ET.tostring(shape.xml) == before


def test_add_swimlane_with_a_label_adds_no_lane_it_cannot_label(vsdx_copy):
    """The label is written last; the refusal must come before the clone."""
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        page = vis.pages[0]
        container = page.get_container()
        lane = container.lanes[0]
        lane.xml.find(f'{namespace}Section[@N="User"]').remove(get_user_row(lane, ROW_HEADING_TEXT))
        before = [existing.ID for existing in container.lanes]
        list_height = container.swimlane_list.height

        with pytest.raises(ValueError, match=ROW_HEADING_TEXT):
            page.add_swimlane("Test lane")

        assert [existing.ID for existing in container.lanes] == before
        assert container.swimlane_list.height == list_height


def test_set_lane_label_refuses_a_shape_that_is_not_a_lane(vsdx_copy):
    """A lane with no `visHeadingText` row cannot be labelled, and must say so."""
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        page = vis.pages[0]
        lane = page.get_container().lanes[0]
        row = get_user_row(lane, ROW_HEADING_TEXT)
        lane.xml.find(f'{namespace}Section[@N="User"]').remove(row)

        with pytest.raises(ValueError, match=ROW_HEADING_TEXT):
            page.get_container().set_lane_label(lane, "Renamed")


def test_set_lane_label_still_labels_a_real_lane(vsdx_copy):
    with VisioFile(vsdx_copy(CFF_FIXTURE)) as vis:
        page = vis.pages[0]
        container = page.get_container()
        lane = container.lanes[0]

        container.set_lane_label(lane, "Renamed")

        row = get_user_row(lane, ROW_HEADING_TEXT)
        assert [cell.attrib.get("V") for cell in row if cell.attrib.get("N") == "Value"] == ["Renamed"]
        assert container.lane_heading(lane).text == "Renamed"
