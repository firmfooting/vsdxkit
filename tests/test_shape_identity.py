"""A `Shape` is its element: identity, and what a wrapper does once its shape is gone (Phase 3, #101).

Each test names the defect it pins. Wrappers are minted per traversal, so two
wrappers of one shape are routine; they must be one key in a set or a dict,
whatever has happened to the shape's ID, its page's name or the file since.
"""

import pytest

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.shapes import Shape


def test_two_wrappers_of_one_shape_are_equal_and_hash_alike(vsdx_copy):
    """Fails if two traversals' wrappers of one shape are different keys."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    page = vis.pages[0]
    first = page.shapes.require_text("Sub-shape 1")
    second = page.shapes.require_text("Group shape text").children.require_text("Sub-shape 1")
    assert first is not second
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1
    assert first != page.shapes.require_text("Sub-shape 2")


def test_equality_ignores_the_wrapper_s_class(vsdx_copy):
    """Fails if a subclass's wrapper of a shape is not equal to a plain one: Connector will be such a subclass."""

    class Special(Shape):
        pass

    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    plain = page.shapes.require_id("1")
    special = Special(xml=plain.xml, parent=plain.parent, page=page)
    assert special == plain and plain == special
    assert hash(special) == hash(plain)


def test_a_shape_s_hash_survives_rename_renumber_and_save(vsdx_copy, tmp_path):
    """Fails if a set of shapes loses a member when its page is renamed, its ID changes, or the file is saved."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shape = page.shapes.require_id("5")
    members = {shape}
    page.name = "Renamed"
    vis.renumber_shape_ids(shape.xml, page)
    assert shape.ID != "5"
    vis.save(str(tmp_path / "saved.vsdx"))
    assert shape in members
    assert page.shapes.require_id(shape.ID) in members


def test_a_shape_is_attached_until_it_is_deleted(vsdx_copy):
    """Fails if `is_attached` is wrong either side of a delete, or misses a deleted group's members."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    page = vis.pages[0]
    group = page.shapes.require_text("Shape to remove")
    member = group.children.require_text("Sub-shape to remove")
    other = page.shapes.require_text("Shape Text")
    assert group.is_attached and member.is_attached
    group.delete()
    assert not group.is_attached
    assert not member.is_attached
    assert other.is_attached


def test_a_shape_on_a_deleted_page_is_detached(vsdx_copy):
    """Fails if a shape whose page was removed from the document still reports itself attached."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shape = page.shapes.require_id("1")
    vis.pages.delete(page)
    assert not shape.is_attached


def test_a_moved_shape_is_attached_through_every_wrapper(vsdx_copy):
    """Fails if a second wrapper of a shape that was moved into a group thinks the shape is gone."""
    vis = Document.open(vsdx_copy("test2.vsdx"))
    page = vis.pages[0]
    moved = page.shapes.require_text("Scenario: {{scenario}}")
    other_wrapper = page.children.require_text("Scenario: {{scenario}}")
    group = page.shapes.require_text("Shape to copy")
    group.append_shape(moved)
    assert moved.is_attached
    assert other_wrapper.is_attached


def test_a_detached_shape_refuses_reads_and_writes(vsdx_copy):
    """Fails if a deleted shape still answers or accepts changes, as if it were on the page."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shape = page.shapes.require_id("1")
    cell = shape.cells["PinX"]
    shape.delete()
    for read in (
        lambda: shape.text,
        lambda: shape.x,
        lambda: shape.cell_value("PinX"),
        lambda: shape.data_properties,
        lambda: shape.cells,
        lambda: list(shape.children),
    ):
        with pytest.raises(InvalidOperationError, match=r"shape 1 .*no longer"):
            read()
    with pytest.raises(InvalidOperationError, match="no longer"):
        shape.text = "changed"
    with pytest.raises(InvalidOperationError, match="no longer"):
        cell.value = "2"


def test_a_detached_shape_keeps_its_id_repr_and_hash(vsdx_copy):
    """Fails if a deleted shape cannot be named in a message, or falls out of the sets it was in."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shape = page.shapes.require_id("1")
    members = {shape}
    before = hash(shape)
    shape.delete()
    assert shape.ID == "1"
    assert "ID=1" in repr(shape)
    assert hash(shape) == before
    assert shape in members
