"""One implementation of "substitute into shape text", reachable two ways.

`VisioFile.apply_text_context` and `Page.apply_text_context` are both public and
both claim to do this. They used to disagree.
"""

import xml.etree.ElementTree as ET

import vsdxkit
from vsdxkit import VisioFile, namespace

NS = namespace[1:-1]


def _shapes(inner: str) -> ET.Element:
    return ET.fromstring(f'<Shapes xmlns="{NS}">{inner}</Shapes>')


def _texts(element: ET.Element) -> list[str]:
    return ["".join(text.itertext()) for text in element.iter(f"{namespace}Text")]


def _xml(element: ET.Element) -> str:
    return ET.tostring(element, encoding="unicode")


class TestTheStaticEntryPoint:
    def test_it_substitutes_inside_a_group(self):
        """A group's children live in the group's own `<Shapes>`, one level down.

        Walking only the top level leaves every grouped shape with its
        placeholder intact.
        """
        root = _shapes(
            '<Shape ID="1"><Text>outer {{who}}</Text><Shapes><Shape ID="2"><Text>inner {{who}}</Text></Shape></Shapes></Shape>'
        )

        VisioFile.apply_text_context(root, {"who": "Ada"})

        assert _texts(root) == ["outer Ada", "inner Ada"]

    def test_it_does_not_raise_on_an_empty_text_element(self):
        """Visio writes `<Text/>`; four such elements ship in this repo's fixtures."""
        root = _shapes('<Shape ID="1"><Text /></Shape>')

        VisioFile.apply_text_context(root, {"who": "Ada"})

        assert _texts(root) == [""]

    def test_it_keeps_a_run_that_follows_the_text(self):
        """A trailing run is markup, not text, and has to survive the write.

        A run *between* two pieces of content does not survive, in either route.
        That is #317, and it predates this consolidation.
        """
        root = _shapes('<Shape ID="1"><Text>{{who}}<cp IX="0"/></Text></Shape>')

        VisioFile.apply_text_context(root, {"who": "Ada"})

        text = next(iter(root.iter(f"{namespace}Text")))
        assert [child.tag for child in text] == [f"{namespace}cp"]
        assert text.text == "Ada"

    def test_it_does_not_write_to_a_shapes_container(self):
        """A `<Shapes>` element is not a shape, even if it carries a `<Text>` child.

        The container is given text of its own here precisely so that a walk
        which treated it as a shape would be visible. The implementation this
        replaced did exactly that.
        """
        root = _shapes('<Shapes><Text>container {{who}}</Text><Shape ID="2"><Text>{{who}}</Text></Shape></Shapes>')

        VisioFile.apply_text_context(root, {"who": "Ada"})

        assert _texts(root) == ["container {{who}}", "Ada"]

    def test_a_context_that_matches_nothing_leaves_the_xml_alone(self):
        """Writing back unchanged text is not free, so it is not done.

        A run between two pieces of content does not survive the round trip
        (#317), so a shape with nothing to substitute would be corrupted merely
        by being visited. Both routes share this guard.
        """
        root = _shapes('<Shape ID="1"><Text>a<cp IX="0"/>b</Text></Shape>')
        before = _xml(root)

        VisioFile.apply_text_context(root, {"nothing": "here"})

        assert _xml(root) == before

    def test_it_leaves_master_inherited_text_alone(self):
        """The documented limit of this entry point, pinned so it stays documented.

        It is handed elements, so it has no master to resolve. A shape showing
        its master's text has no `<Text>` of its own and is skipped.
        `Page.apply_text_context` is the route that resolves inheritance.
        """
        root = _shapes('<Shape ID="1" Master="4" />')
        before = _xml(root)

        VisioFile.apply_text_context(root, {"who": "Ada"})

        assert _xml(root) == before


def test_the_second_implementation_is_gone():
    """`get_shape_text`/`set_shape_text` duplicated `Shape.text`, badly.

    `set_shape_text` raised `IndexError` on an empty `<Text/>` and silently
    dropped the text on a shape with no `<Text>` at all.
    """
    assert not hasattr(VisioFile, "get_shape_text")
    assert not hasattr(VisioFile, "set_shape_text")


def _seed_some(path: str) -> int:
    """Put a placeholder in the text of shapes that have their own `<Text>`.

    Deliberately not every shape. Assigning `shape.text` creates a `<Text>`
    element where there was none, which would give a master-inheriting shape
    local text and dissolve the one case where the two routes differ - leaving
    a parity assertion that cannot fail.
    """
    with vsdxkit.VisioFile(path) as document:
        seeded = 0
        for shape in document.pages[0].all_shapes:
            if shape.xml.find(f"{namespace}Text") is None:
                continue
            shape.text = f"shape {shape.ID} {{{{tok}}}}"
            seeded += 1
        document.save_vsdx(path)
        return seeded


def test_the_two_entry_points_agree_on_shapes_that_hold_their_own_text(vsdx_copy):
    """Same file, same context, same answer, over the shapes both can reach.

    `test2.vsdx` carries groups, which is what the static route used to miss.
    """
    through_page = vsdx_copy("test2.vsdx")
    seeded = _seed_some(through_page)
    assert seeded > 1, "the fixture has to have shapes with text for this to compare anything"

    with vsdxkit.VisioFile(through_page) as document:
        page = document.pages[0]
        page.apply_text_context({"tok": "SUBSTITUTED"})
        by_page = sorted(shape.text for shape in page.all_shapes)

    through_static = vsdx_copy("test2.vsdx")
    _seed_some(through_static)
    with vsdxkit.VisioFile(through_static) as document:
        page = document.pages[0]
        VisioFile.apply_text_context(page.xml.getroot(), {"tok": "SUBSTITUTED"})
        by_static = sorted(shape.text for shape in page.all_shapes)

    assert all("{{tok}}" not in text for text in by_page), "a placeholder was left behind"
    assert by_static == by_page
