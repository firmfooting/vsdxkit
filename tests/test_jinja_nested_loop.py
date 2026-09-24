"""A `{% for %}` on the first shape inside a group repeats that shape inside the group (#103).

The loop's opening statement goes into the ``<Shapes>`` element the shape sits
in, and its ``{% endfor %}`` onto the shape's tail, inside that same element.
It used to go into the text of the parent Shape's own element: right for the
page's ``<Shapes>``, which was held as a Shape, but for a group it opened the
loop before the group's cells and closed it inside its ``<Shapes>``, so the
rendered page did not parse.
"""

from vsdxkit.document import Document


def test_a_loop_on_a_group_s_first_member_repeats_it_inside_the_group(vsdx_copy):
    """Fails if the loop's opening statement lands anywhere but the group's own `<Shapes>`."""
    vis = Document.open(vsdx_copy("test10_nested_shapes.vsdx"))
    group = vis.pages[0].shapes.require_text("Shape 1.1")
    first = group.children.require_text("Shape 1.1.1")
    first.text = "{% for i in items %}Item {{ i }}"

    vis.render({"items": [1, 2, 3]})

    group = vis.pages[0].shapes.require_text("Shape 1.1")
    assert [shape.text for shape in group.children] == ["Item 1", "Item 2", "Item 3", "Shape 1.1.2"]
    assert len({shape.ID for shape in vis.pages[0].shapes}) == len(vis.pages[0].shapes)


def test_a_loop_on_a_page_s_first_shape_repeats_it_on_the_page(vsdx_copy):
    """Fails if a top-level loop stops landing in the page's `<Shapes>` now that no Shape wraps it."""
    vis = Document.open(vsdx_copy("test10_nested_shapes.vsdx"))
    first = vis.pages[0].children.require_text("Shape 1")
    first.text = "{% for i in items %}Group {{ i }}"

    vis.render({"items": ["a", "b"]})

    texts = [shape.text for shape in vis.pages[0].children]
    assert texts == ["Group a", "Group b", "Nested Shape Example"]
    assert len({shape.ID for shape in vis.pages[0].shapes}) == len(vis.pages[0].shapes)
