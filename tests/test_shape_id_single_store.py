"""A `Shape` object's identity is whatever its element says, never a copy of it.

The block comment above `Shape.tag` in `shapes.py` is the code under test and
carries the reasoning; these pin it from the outside: glue written after a
renumber, the object's own id, the records it can still find, and the delete
cascade. Issue #320, and the same second-store fault as #278.

The tests that save get the package validator's look at the result: a Connect
record naming a shape that is not there is its `dangling-glue` defect.
"""

import pytest
from helpers.connect_records import page_records

from vsdxkit.document import Document


def _records(page) -> list[tuple[str | None, str | None]]:
    """Every Connect record on the page, as (FromSheet, ToSheet)."""
    return [(c.from_id, c.to_id) for c in page_records(page)]


def test_glue_written_after_a_renumber_names_the_shape_that_is_there(vsdx_copy, tmp_path):
    """Connect records are written from `Shape.ID`, so a stale one dangles."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    page = vis.pages[0]
    shape = page.shapes.require_id("2")
    other = page.shapes.require_id("5")

    page._renumber_shape_ids(shape.xml)
    page.connect(shape, other)

    assert "2" not in [to_id for _, to_id in _records(page)]
    vis.save(str(tmp_path / "connected_after_renumber.vsdx"))


def test_renumbering_moves_the_shape_object_with_its_element(vsdx_copy):
    """After a renumber, the id the object reports is the one the element carries."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    page = vis.pages[0]
    shape = page.shapes.require_id("2")

    page._renumber_shape_ids(shape.xml)

    renumbered = shape.xml.attrib["ID"]
    assert renumbered != "2"
    assert renumbered == shape.ID


def test_a_renumbered_shape_still_finds_the_connectors_glued_to_it(vsdx_copy):
    """`Shape.connectors` matches the page's records on this shape's id."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    page = vis.pages[0]
    shape = page.shapes.require_id("2")
    assert len(shape.connectors) == 2

    page._renumber_shape_ids(shape.xml)

    assert len(shape.connectors) == 2


def test_a_connector_held_across_a_renumber_resolves_to_the_new_id(vsdx_copy):
    """A connector's ends read the records `_remap_connect_records` rewrites, not a copy of them."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    page = vis.pages[0]
    shape = page.shapes.require_id("2")
    held = shape.connectors

    new_id = str(page._renumber_shape_ids(shape.xml)["2"])

    assert [(c.source, c.target) for c in held].count((None, None)) == 0
    assert all(new_id in {end.ID for end in (c.source, c.target) if end is not None} for c in held)


def test_deleting_a_renumbered_shape_takes_its_connectors_with_it(vsdx_copy, tmp_path):
    """The #278 delete cascade, entered after a renumber.

    `Shape.delete` gathers the connectors to remove by matching records
    against the shape's id, so a stale one left the connector behind as a line
    glued to nothing at one end.
    """
    vis = Document.open(vsdx_copy("test7_with_connector.vsdx"))
    page = vis.pages[0]
    shape = page.shapes.require_id("2")
    connector_id = next(from_id for from_id, to_id in _records(page) if to_id == "2")

    page._renumber_shape_ids(shape.xml)
    shape.delete()

    assert page.shapes.by_id(connector_id) is None
    vis.save(str(tmp_path / "deleted_after_renumber.vsdx"))


def test_the_master_a_shape_names_is_read_from_its_element(vsdx_copy):
    """`Master` and `MasterShape` were cached alongside `ID`, and now read the same way."""
    vis = Document.open(vsdx_copy("test5_master.vsdx"))
    shape = next(s for s in vis.pages[0].shapes if s.master_page_ID)
    master_shape = next(s for s in vis.pages[0].shapes if s.master_shape_ID)

    shape.xml.attrib["Master"] = "999"
    master_shape.xml.attrib["MasterShape"] = "998"

    assert shape.master_page_ID == "999"
    assert master_shape.master_shape_ID == "998"


def test_repointing_a_shape_at_a_master_writes_the_element(vsdx_copy):
    """`master_page_ID` is still writable, and `Connect.create` no longer writes it twice.

    A top-level shape carrying `Master` itself: the setter writes this shape's
    own attribute, and a sub-shape cleared this way would report the group's
    master back rather than None.
    """
    vis = Document.open(vsdx_copy("test5_master.vsdx"))
    shape = next(s for s in vis.pages[0].children if "Master" in s.xml.attrib)

    shape.master_page_ID = "3"
    assert shape.xml.attrib["Master"] == "3"

    shape.master_page_ID = None
    assert "Master" not in shape.xml.attrib
    assert shape.master_page_ID is None


def test_a_sub_shape_inherits_the_master_of_whichever_group_holds_it(vsdx_copy):
    """The fallback is resolved per read, so a held shape follows a fresh walk.

    `append_shape` re-parents the object as well as the element. Resolved once
    at construction, the held shape kept reporting the master it had before the
    move while `page.shapes` reported the new one.
    """
    vis = Document.open(vsdx_copy("test3_house.vsdx"))
    page = vis.pages[0]
    group = next(s for s in page.shapes if s.shape_type == "Group" and "Master" in s.xml.attrib)
    loose = next(s for s in page.children if s is not group and "Master" not in s.xml.attrib)

    group.append_shape(loose)

    assert loose.master_page_ID == group.master_page_ID
    assert loose.master_page_ID == page.shapes.require_id(loose.ID).master_page_ID


def test_a_shape_cannot_be_appended_into_itself(vsdx_copy):
    """Otherwise the element becomes its own descendant and every walk recurses."""
    vis = Document.open(vsdx_copy("test3_house.vsdx"))
    group = next(s for s in vis.pages[0].shapes if s.shape_type == "Group")

    with pytest.raises(ValueError, match="cannot be placed inside"):
        group.append_shape(group)


def test_the_identity_a_shape_reads_off_its_element_cannot_be_assigned(vsdx_copy):
    """Read-only, so nothing can put the second store back by accident."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    shape = vis.pages[0].shapes.require_id("2")

    for attribute in ("ID", "master_shape_ID", "shape_type", "shape_name", "tag"):
        with pytest.raises(AttributeError):
            setattr(shape, attribute, "9")
