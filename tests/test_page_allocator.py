"""The page allocates shape IDs: a loop's copies and a copy onto a fresh page get IDs of their own (#116)."""

import re

from vsdxkit.document import Document
from vsdxkit.shapes import Shape
from vsdxkit.templating import RenderTarget

_REFERENCE = re.compile(r"Sheet\.(\d+)!")


def _ids(shapes) -> list[str]:
    return [shape.ID for shape in shapes if shape.ID is not None]


def test_a_loop_over_a_group_gives_each_copy_its_own_ids_and_references(vsdx_copy):
    """Fails if a `{% for %}` copy of a group keeps its source's IDs, or its members still name the source group.

    Rendering renumbers each copy through the page, with no help from the
    document: `RenderTarget` declares only `pages`.
    """
    document = Document.open(vsdx_copy("test10_nested_shapes.vsdx"))
    page = document.pages[0]
    group = page.shapes.by_text("Shape 1")
    assert group is not None and group.children, "the fixture's group has moved"
    group.text = "{% for i in items %}Group {{ i }}"

    document.render({"items": ["a", "b"]})

    ids = _ids(page.shapes)
    assert len(ids) == len(set(ids)), f"duplicate IDs after the loop: {sorted(ids)}"
    groups = [shape for shape in page.shapes if shape.text.startswith("Group ")]
    assert sorted(shape.text for shape in groups) == ["Group a", "Group b"]
    for copied in groups:
        named = {
            match.group(1)
            for member in copied.children
            for name in ("PinX", "PinY", "Width", "Height")
            if (formula := member.cell_formula(name))
            for match in _REFERENCE.finditer(formula)
        }
        assert named == {copied.ID}, f"{copied.text}'s members name {named}, not their own group {copied.ID}"


def test_a_copy_onto_a_freshly_loaded_page_takes_an_id_that_page_does_not_use(vsdx_copy):
    """Fails if allocation trusts a high-water mark nothing has set yet: a freshly loaded page starts at 0.

    test1's third page holds one shape, ID 1, and nothing on it has been read,
    so the first free ID is 2 and not 1.
    """
    document = Document.open(vsdx_copy("test1.vsdx"))
    fresh = document.pages[2]
    assert _ids(fresh.shapes) == ["1"], "the fixture's third page has changed"
    source = document.pages[0].shapes.by_text("Shape to copy")
    assert isinstance(source, Shape)

    copied = source.copy(fresh)

    assert copied.ID == "2"
    assert sorted(_ids(fresh.shapes)) == ["1", "2"]


def test_the_document_allocates_nothing_and_rendering_needs_only_pages():
    """Fails if an ID helper comes back on `Document`, or `RenderTarget` asks for one again."""
    for name in (
        "copy_shape",
        "insert_shape",
        "renumber_shape_ids",
        "increment_shape_ids",
        "increment_sub_shape_ids",
        "set_new_id",
        "update_ids",
    ):
        assert not hasattr(Document, name), name
    assert [name for name in dir(RenderTarget) if not name.startswith("_")] == ["pages"]
