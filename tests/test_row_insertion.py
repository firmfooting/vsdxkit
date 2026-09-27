"""One helper puts a section row in IX order, for geometry and for text formatting alike (#319)."""

import xml.etree.ElementTree as ET

from vsdxkit import namespace
from vsdxkit._xmlio import insert_row_in_index_order
from vsdxkit.document import Document

NS = namespace[1:-1]


def _section(*children: str) -> ET.Element:
    return ET.fromstring(f'<Section xmlns="{NS}" N="Geometry">{"".join(children)}</Section>')


def _row(ix: str) -> ET.Element:
    return ET.fromstring(f'<Row xmlns="{NS}" IX="{ix}"/>')


def _layout(section: ET.Element) -> list[str]:
    return [child.get("IX") or child.get("N") or "" for child in section]


def test_a_row_goes_between_the_rows_either_side_of_its_index_as_numbers():
    """IX 10 sorts after IX 3: as text it would sort first and redraw the path in another order."""
    section = _section('<Cell N="NoFill" V="0"/>', '<Row IX="1"/>', '<Row IX="2"/>', '<Row IX="10"/>')

    insert_row_in_index_order(section, _row("3"))

    assert _layout(section) == ["NoFill", "1", "2", "3", "10"]


def test_a_first_row_goes_after_the_sections_cells():
    """A Section is Cell*, Trigger*, Row*: a row among the cells is a file Visio offers to repair."""
    section = _section('<Cell N="NoFill" V="0"/>', '<Cell N="NoLine" V="0"/>')

    insert_row_in_index_order(section, _row("1"))

    assert _layout(section) == ["NoFill", "NoLine", "1"]


def test_an_index_that_is_not_a_number_sorts_after_every_number():
    section = _section('<Row IX="x"/>')

    insert_row_in_index_order(section, _row("5"))

    assert _layout(section) == ["5", "x"]


def test_an_index_of_digits_that_are_not_decimal_sorts_after_every_number():
    """``"²".isdigit()`` is true, and ``int("²")`` raises: such an index stopped every insertion into the section (#452)."""
    section = _section('<Row IX="²"/>')

    insert_row_in_index_order(section, _row("5"))

    assert _layout(section) == ["5", "²"]


def test_text_colour_on_a_shape_whose_character_section_has_a_non_numeric_index(vsdx_copy):
    """`_insert_character_row` did int(IX) on every sibling, so one odd index made text_color raise ValueError."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    shape = vis.pages[0].shapes.require_id("1")
    section = ET.SubElement(shape.xml, f"{namespace}Section", {"N": "Character"})
    ET.SubElement(ET.SubElement(section, f"{namespace}Row", {"IX": "a"}), f"{namespace}Cell", {"N": "Size", "V": "0.16"})

    shape.text_color = "#00ff00"

    assert [row.get("IX") for row in section.findall(f"{namespace}Row")] == ["0", "a"]
