"""`Page.apply_text_context` is the one way to substitute a context into shape text.

`Document.apply_text_context`, a static method handed bare elements, was a
second route to the same thing and could not resolve master inheritance. It
is gone (#116). These are its cases, asked of the page.
"""

import xml.etree.ElementTree as ET

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.pages import Page

NS = namespace[1:-1]


def _page_holding(vsdx_copy, inner: str) -> tuple[Page, ET.Element]:
    """A page of test1.vsdx whose top-level `<Shapes>` holds only `inner`, and that `<Shapes>`."""
    page = Document.open(vsdx_copy("test1.vsdx")).pages[0]
    shapes = page.xml.getroot().find(f"{namespace}Shapes")
    assert shapes is not None
    for child in list(shapes):
        shapes.remove(child)
    shapes.extend(ET.fromstring(f'<Shapes xmlns="{NS}">{inner}</Shapes>'))
    return page, shapes


def _texts(element: ET.Element) -> list[str]:
    return ["".join(text.itertext()) for text in element.iter(f"{namespace}Text")]


def _xml(element: ET.Element) -> str:
    return ET.tostring(element, encoding="unicode")


def test_it_substitutes_inside_a_group(vsdx_copy):
    """A group's children live in the group's own `<Shapes>`, one level down.

    Walking only the top level leaves every grouped shape with its
    placeholder intact.
    """
    page, shapes = _page_holding(
        vsdx_copy,
        '<Shape ID="1" Type="Group"><Text>outer {{who}}</Text>'
        '<Shapes><Shape ID="2"><Text>inner {{who}}</Text></Shape></Shapes></Shape>',
    )

    page.apply_text_context({"who": "Ada"})

    assert _texts(shapes) == ["outer Ada", "inner Ada"]


def test_it_does_not_raise_on_an_empty_text_element(vsdx_copy):
    """Visio writes `<Text/>`; four such elements ship in this repo's fixtures."""
    page, shapes = _page_holding(vsdx_copy, '<Shape ID="1"><Text /></Shape>')

    page.apply_text_context({"who": "Ada"})

    assert _texts(shapes) == [""]


def test_it_keeps_a_run_that_follows_the_text(vsdx_copy):
    """A trailing run is markup, not text, and has to survive the write.

    A run *between* two pieces of content does not survive the write. That is #317.
    """
    page, shapes = _page_holding(vsdx_copy, '<Shape ID="1"><Text>{{who}}<cp IX="0"/></Text></Shape>')

    page.apply_text_context({"who": "Ada"})

    text = next(iter(shapes.iter(f"{namespace}Text")))
    assert [child.tag for child in text] == [f"{namespace}cp"]
    assert text.text == "Ada"


def test_it_does_not_write_to_a_shapes_container(vsdx_copy):
    """A `<Shapes>` element is not a shape, even if it carries a `<Text>` child.

    The container is given text of its own here precisely so that a walk
    which treated it as a shape would be visible.
    """
    page, shapes = _page_holding(
        vsdx_copy,
        '<Shape ID="1" Type="Group"><Shapes><Text>container {{who}}</Text>'
        '<Shape ID="2"><Text>{{who}}</Text></Shape></Shapes></Shape>',
    )

    page.apply_text_context({"who": "Ada"})

    assert _texts(shapes) == ["container {{who}}", "Ada"]


def test_a_context_that_matches_nothing_leaves_the_xml_alone(vsdx_copy):
    """Writing back unchanged text is not free, so it is not done.

    A run between two pieces of content does not survive the round trip
    (#317), so a shape with nothing to substitute would be corrupted merely
    by being visited.
    """
    page, shapes = _page_holding(vsdx_copy, '<Shape ID="1"><Text>a<cp IX="0"/>b</Text></Shape>')
    before = _xml(shapes)

    page.apply_text_context({"nothing": "here"})

    assert _xml(shapes) == before


def test_it_coerces_non_string_values(vsdx_copy):
    page = Document.open(vsdx_copy("test1.vsdx")).pages[0]
    shape = next(iter(page.children))
    shape.text = "Year {{year}}"

    page.apply_text_context({"year": 2020})

    assert shape.text == "Year 2020"


def test_it_substitutes_text_a_shape_shows_from_its_master(vsdx_copy):
    """The case `Document.apply_text_context` could not resolve (#116): a shape with no `<Text>` of its own.

    Substituting into it has to write shape 3's own XML, not the master's -
    or every other shape sharing that master would show the substituted
    value too.
    """
    page = Document.open(vsdx_copy("test5_master.vsdx")).pages[0]
    shape = page.shapes.require_id("3")
    master = shape.master_shape
    assert master is not None
    master.text = "M {{who}}"

    page.apply_text_context({"who": "Ada"})

    assert shape.text == "M Ada"
    assert master.text == "M {{who}}"


def test_the_other_implementations_are_gone():
    """`get_shape_text`/`set_shape_text` duplicated `Shape.text`, and the static `apply_text_context` duplicated this.

    `set_shape_text` raised `IndexError` on an empty `<Text/>` and silently
    dropped the text on a shape with no `<Text>` at all.
    """
    for name in ("get_shape_text", "set_shape_text", "apply_text_context"):
        assert not hasattr(Document, name), name
