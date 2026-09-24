"""`ShapeCollection`: fixed scopes, and explicit about how many shapes match (Phase 3, #100).

Each test names the defect it pins. A collection is live: it walks its scope
again on every call, so these tests also check that it sees what changed after
it was taken.
"""

import glob
import os

import pytest

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError, NotFoundError, PackageError
from vsdxkit.shapes import ShapeCollection

BASEDIR = os.path.dirname(os.path.realpath(__file__))


def _ids(shapes) -> list[str]:
    return [shape.ID for shape in shapes]


def _fixtures() -> list[str]:
    return sorted(
        os.path.relpath(path, BASEDIR) for path in glob.glob(os.path.join(BASEDIR, "**", "*.vs[dm]x"), recursive=True)
    )


@pytest.mark.parametrize("fixture", _fixtures())
def test_every_scope_holds_what_its_walk_holds(fixture):
    """Fails if a collection's members disagree with the traversal it is scoped to, on any fixture page."""
    vis = Document.open(os.path.join(BASEDIR, fixture))
    for page in vis.pages:
        assert _ids(page.children) == _ids(page.child_shapes)
        assert _ids(page.shapes) == _ids(page.all_shapes)
        assert len(page.shapes) == len(page.all_shapes)
        for shape in page.all_shapes:
            assert _ids(shape.children) == _ids(shape.child_shapes)
            assert _ids(shape.descendants) == _ids(shape.all_shapes)


def test_every_scope_is_a_shape_collection(basedir):
    """Fails if a scope hands back a list, which has none of the finders and silently goes stale."""
    vis = Document.open(os.path.join(basedir, "test2.vsdx"))
    page = vis.pages[0]
    group = page.shapes.require_text("Group shape text")
    for scope in (page.children, page.shapes, group.children, group.descendants):
        assert isinstance(scope, ShapeCollection)


def test_page_shapes_includes_connectors(basedir):
    """Fails if the page-wide scope leaves out 1-D shapes: the plan puts connectors in `Page.shapes`."""
    vis = Document.open(os.path.join(basedir, "test4_connectors.vsdx"))
    page = vis.pages[0]
    assert {"6", "7"} <= set(_ids(page.shapes))


def test_a_shape_that_is_not_a_group_has_no_children(basedir):
    """Fails if a plain shape's children are anything but empty."""
    vis = Document.open(os.path.join(basedir, "test1.vsdx"))
    shape = vis.pages[0].shapes.require_id("1")
    assert len(shape.children) == 0
    assert list(shape.descendants) == []


def test_a_collection_sees_a_shape_added_after_it_was_taken(vsdx_copy):
    """Fails if a collection is a snapshot: a shape copied onto the page later must be found by it."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shapes = page.shapes
    before = len(shapes)
    copy = page.shapes.require_text("Shape to copy").copy(page)
    assert len(shapes) == before + 1
    assert shapes.require_id(copy.ID).xml is copy.xml


def test_text_is_matched_exactly(basedir):
    """Fails if `by_text` matches a substring: "Shape" must not find the shape reading "Shape Text"."""
    vis = Document.open(os.path.join(basedir, "test1.vsdx"))
    shapes = vis.pages[0].shapes
    assert shapes.by_text("Shape") is None
    assert shapes.matching_text("Shape") == ()
    assert shapes.by_text("Shape Text").ID == "1"


def test_two_shapes_with_one_text_are_not_one_match(vsdx_copy):
    """Fails if a unique lookup silently takes the first of two shapes that read the same."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    original = page.shapes.require_text("Shape to copy")
    copy = original.copy(page)
    shapes = page.shapes
    with pytest.raises(InvalidOperationError, match=rf"\b{original.ID}\b.*\b{copy.ID}\b"):
        shapes.by_text("Shape to copy")
    with pytest.raises(InvalidOperationError, match="Shape to copy"):
        shapes.require_text("Shape to copy")
    matches = shapes.matching_text("Shape to copy")
    assert isinstance(matches, tuple)
    assert _ids(matches) == [original.ID, copy.ID]


def test_a_missing_text_is_none_or_not_found(basedir):
    """Fails if a miss is reported the wrong way: `by_*` answers None, `require_*` raises NotFoundError."""
    vis = Document.open(os.path.join(basedir, "test1.vsdx"))
    shapes = vis.pages[0].shapes
    assert shapes.by_text("No such text") is None
    with pytest.raises(NotFoundError, match=r"No such text.*page 'Page-1'"):
        shapes.require_text("No such text")


def test_two_shapes_with_one_property_are_not_one_match(basedir):
    """Fails if a unique property lookup takes the first of two shapes carrying the label."""
    vis = Document.open(os.path.join(basedir, "test6_shape_properties.vsdx"))
    shapes = vis.pages[0].shapes
    with pytest.raises(InvalidOperationError, match=r"my_property_label.*\b1\b.*\b2\b"):
        shapes.by_property("my_property_label")
    assert _ids(shapes.matching_property("my_property_label")) == ["1", "2"]
    assert shapes.require_property("my_property_label", "a different value").ID == "2"
    assert _ids(shapes.matching_property("my_second_property_label", "a different value")) == ["5"]
    assert shapes.by_property("my_property_label", "no such value") is None
    with pytest.raises(NotFoundError, match="no_such_label"):
        shapes.require_property("no_such_label")


def test_a_duplicate_id_is_a_package_error(vsdx_copy):
    """Fails if a page holding two shapes with one ID answers with either: IDs are page-unique, so the page is invalid."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shapes = page.shapes
    shapes.require_id("5").xml.attrib["ID"] = "2"
    with pytest.raises(PackageError, match=r"\b2\b"):
        shapes.by_id("2")
    assert shapes.by_id("99") is None
    with pytest.raises(NotFoundError, match="99"):
        shapes.require_id("99")


def test_a_group_s_scope_is_named_in_its_errors(basedir):
    """Fails if an error from a shape's collection does not say which shape it searched."""
    vis = Document.open(os.path.join(basedir, "test2.vsdx"))
    group = vis.pages[0].shapes.require_text("Group shape text")
    assert _ids(group.children) == ["1", "7", "8"]
    with pytest.raises(NotFoundError, match=rf"shape {group.ID} on page 'Page-1'"):
        group.descendants.require_text("Shape to copy")
