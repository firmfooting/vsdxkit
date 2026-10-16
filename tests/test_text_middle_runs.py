"""A formatting run between two pieces of a shape's text survives reading and writing it (#317)."""

import xml.etree.ElementTree as ET

from vsdxkit import namespace
from vsdxkit.document import Document

TEXT = f'<Text xmlns="{namespace[1:-1]}"><pp IX="0"/>A\n<pp IX="1"/>B</Text>'


def _shape(vsdx_copy):
    vis = Document.open(vsdx_copy("test1.vsdx"))
    shape = next(iter(vis.pages[0].shapes))
    old = shape.xml.find(f"{namespace}Text")
    if old is not None:
        shape.xml.remove(old)
    shape.xml.append(ET.fromstring(TEXT))
    return shape


def _xml(shape) -> str:
    return ET.tostring(shape.xml.find(f"{namespace}Text"), encoding="unicode")


def test_a_round_trip_leaves_the_text_element_unchanged(vsdx_copy):
    shape = _shape(vsdx_copy)
    before = _xml(shape)

    assert shape.text == "A\nB"
    shape.text = shape.text

    assert _xml(shape) == before


def test_setting_new_text_keeps_the_run_before_the_text_that_followed_it(vsdx_copy):
    shape = _shape(vsdx_copy)

    shape.text = "AA\nB"

    text = shape.xml.find(f"{namespace}Text")
    runs = text.findall(f"{namespace}pp")
    assert [r.attrib["IX"] for r in runs] == ["0", "1"]
    assert runs[1].tail == "B"
    assert shape.text == "AA\nB"


def test_a_substitution_before_the_run_moves_the_run_with_the_text_after_it(vsdx_copy):
    shape = _shape(vsdx_copy)

    shape.find_replace("A", "longer")

    assert shape.xml.find(f"{namespace}Text").findall(f"{namespace}pp")[1].tail == "B"
