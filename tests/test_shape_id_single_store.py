"""A `Shape` object's identity is whatever its element says, never a copy of it.

The block comment above `Shape.tag` in `shapes.py` is the code under test and
carries the reasoning; these pin it from the outside: glue written after a
renumber, the object's own id, the records it can still find, and the delete
cascade. Issue #320, and the same second-store fault as #278.

The tests that save get the package validator's look at the result: a Connect
record naming a shape that is not there is its `dangling-glue` defect.
"""

import pytest

from vsdx import VisioFile


def _records(page) -> list[tuple[str | None, str | None]]:
    """Every Connect record on the page, as (FromSheet, ToSheet)."""
    return [(c.from_id, c.to_id) for c in page.connects]


def test_glue_written_after_a_renumber_names_the_shape_that_is_there(vsdx_copy, tmp_path):
    """Connect records are written from `Shape.ID`, so a stale one dangles."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_id("2")
        other = page.find_shape_by_id("5")

        vis.increment_sub_shape_ids(shape, page)
        page.connect_shapes(shape, other)

        assert "2" not in [to_id for _, to_id in _records(page)]
        vis.save_vsdx(str(tmp_path / "connected_after_renumber.vsdx"))


def test_renumbering_moves_the_shape_object_with_its_element(vsdx_copy):
    """After a renumber, the id the object reports is the one the element carries."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_id("2")

        vis.increment_sub_shape_ids(shape, page)

        renumbered = shape.xml.attrib["ID"]
        assert renumbered != "2"
        assert renumbered == shape.ID


def test_a_renumbered_shape_still_finds_the_records_glued_to_it(vsdx_copy):
    """`Shape.connects` filters the page's records on this shape's id."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_id("2")
        assert len(shape.connects) == 2

        vis.increment_sub_shape_ids(shape, page)

        assert len(shape.connects) == 2


def test_a_connect_held_across_a_renumber_names_the_new_id(vsdx_copy):
    """`Connect` cached the same attributes `_remap_connect_records` rewrites."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_id("2")
        record = next(c for c in page.connects if c.to_id == "2")

        new_id = str(vis.increment_sub_shape_ids(shape, page)["2"])

        assert record.to_id == new_id


def test_deleting_a_renumbered_shape_takes_its_connectors_with_it(vsdx_copy, tmp_path):
    """The #278 delete cascade, entered after a renumber.

    `Page.delete_shape` gathers the connectors to remove by matching records
    against the shape's id, so a stale one left the connector behind as a line
    glued to nothing at one end.
    """
    with VisioFile(vsdx_copy("test7_with_connector.vsdx")) as vis:
        page = vis.pages[0]
        shape = page.find_shape_by_id("2")
        connector_id = next(from_id for from_id, to_id in _records(page) if to_id == "2")

        vis.increment_sub_shape_ids(shape, page)
        page.delete_shape(shape)

        assert page.find_shape_by_id(connector_id) is None
        vis.save_vsdx(str(tmp_path / "deleted_after_renumber.vsdx"))


def test_the_master_a_shape_names_is_read_from_its_element(vsdx_copy):
    """`Master` and `MasterShape` were cached alongside `ID`, and now read the same way."""
    with VisioFile(vsdx_copy("test5_master.vsdx")) as vis:
        shape = next(s for s in vis.pages[0].all_shapes if s.master_page_ID)
        master_shape = next(s for s in vis.pages[0].all_shapes if s.master_shape_ID)

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
    with VisioFile(vsdx_copy("test5_master.vsdx")) as vis:
        shape = next(s for s in vis.pages[0].child_shapes if "Master" in s.xml.attrib)

        shape.master_page_ID = "3"
        assert shape.xml.attrib["Master"] == "3"

        shape.master_page_ID = None
        assert "Master" not in shape.xml.attrib
        assert shape.master_page_ID is None


def test_a_sub_shape_inherits_the_master_of_whichever_group_holds_it(vsdx_copy):
    """The fallback is resolved per read, so a held shape follows a fresh walk.

    `append_shape` re-parents the object as well as the element. Resolved once
    at construction, the held shape kept reporting the master it had before the
    move while `page.all_shapes` reported the new one.
    """
    with VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        page = vis.pages[0]
        group = next(s for s in page.all_shapes if s.shape_type == "Group" and "Master" in s.xml.attrib)
        loose = next(s for s in page.child_shapes if s is not group and "Master" not in s.xml.attrib)

        group.append_shape(loose)

        assert loose.master_page_ID == group.master_page_ID
        assert loose.master_page_ID == page.find_shape_by_id(loose.ID).master_page_ID


def test_a_shape_cannot_be_appended_into_itself(vsdx_copy):
    """Otherwise the element becomes its own descendant and every walk recurses."""
    with VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        group = next(s for s in vis.pages[0].all_shapes if s.shape_type == "Group")

        with pytest.raises(ValueError, match="cannot be placed inside"):
            group.append_shape(group)


def test_the_identity_a_shape_reads_off_its_element_cannot_be_assigned(vsdx_copy):
    """Read-only, so nothing can put the second store back by accident."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        shape = vis.pages[0].find_shape_by_id("2")

        for attribute in ("ID", "master_shape_ID", "shape_type", "shape_name", "tag"):
            with pytest.raises(AttributeError):
                setattr(shape, attribute, "9")
