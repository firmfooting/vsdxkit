"""`Shape.remove()` must not leave a page half-deleted.

`Page.delete_shape()` already removes incident connectors and their `Connect`
records; `Shape.remove()` detached the element and nothing else, so the same
deletion through the other API left dangling records and orphan connectors that
Visio repairs on open.
"""

import os
import xml.etree.ElementTree as ET

import pytest

from vsdx import VisioFile, namespace

basedir = os.path.dirname(os.path.realpath(__file__))


def _connect_records(page):
    connects = page.xml.find(f".//{namespace}Connects")
    return [] if connects is None else list(connects)


def _referencing(page, shape_id: str):
    return [
        record
        for record in _connect_records(page)
        if shape_id in (record.attrib.get("FromSheet"), record.attrib.get("ToSheet"))
    ]


def test_removing_a_connected_shape_takes_its_connector_with_it(vsdx_copy):
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        start = vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="A")
        end = vis.create_shape(page, "PALETTE_PROCESS", 6.0, 2.0, text="B")
        connector = page.connect_shapes(start, end)
        assert _referencing(page, start.ID)

        with pytest.warns(DeprecationWarning, match="delete_shape"):
            start.remove()

        assert _referencing(page, start.ID) == []
        assert _referencing(page, connector.ID) == []
        remaining = {shape.ID for shape in page.all_shapes}
        assert start.ID not in remaining
        assert connector.ID not in remaining, "the connector was left with nothing to glue to"


def test_remove_and_delete_shape_leave_the_page_in_the_same_state(vsdx_copy):
    """The two APIs are the same deletion and must not disagree."""

    def _state_after(delete):
        with VisioFile(vsdx_copy("test1.vsdx")) as vis:
            page = vis.pages[0]
            start = vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="A")
            end = vis.create_shape(page, "PALETTE_PROCESS", 6.0, 2.0, text="B")
            page.connect_shapes(start, end)
            delete(page, start)
            return (
                sorted(shape.ID for shape in page.all_shapes),
                sorted(ET.tostring(record, encoding="unicode") for record in _connect_records(page)),
            )

    with pytest.warns(DeprecationWarning):
        through_remove = _state_after(lambda page, shape: shape.remove())
    through_delete_shape = _state_after(lambda page, shape: page.delete_shape(shape))
    assert through_remove == through_delete_shape


def test_removing_a_group_child_removes_records_that_reference_it(vsdx_copy):
    """A record pointing into a group must not outlive the shape it points at."""
    with VisioFile(vsdx_copy("test10_nested_shapes.vsdx")) as vis:
        page = vis.pages[0]
        group = next(shape for shape in page.child_shapes if shape.child_shapes)
        child = group.child_shapes[0]

        connects = page.xml.find(f".//{namespace}Connects")
        if connects is None:
            connects = ET.SubElement(page.xml.getroot(), f"{namespace}Connects")
        connects.append(
            ET.fromstring(
                f'<Connect xmlns="{namespace[1:-1]}" FromSheet="{child.ID}" FromCell="BeginX" '
                f'FromPart="9" ToSheet="{group.ID}" ToCell="PinX" ToPart="3"/>'
            )
        )
        assert _referencing(page, child.ID)

        with pytest.warns(DeprecationWarning):
            child.remove()

        assert _referencing(page, child.ID) == []
        assert child.ID not in {shape.ID for shape in group.child_shapes}


def _add_connect(page, from_id, to_id):
    connects = page.xml.find(f".//{namespace}Connects")
    if connects is None:
        connects = ET.SubElement(page.xml.getroot(), f"{namespace}Connects")
    connects.append(
        ET.fromstring(
            f'<Connect xmlns="{namespace[1:-1]}" FromSheet="{from_id}" FromCell="BeginX" '
            f'FromPart="9" ToSheet="{to_id}" ToCell="PinX" ToPart="3"/>'
        )
    )


def test_deleting_a_group_takes_the_records_naming_its_children(vsdx_copy):
    """A group's children go with it, so records naming them must go too."""
    with VisioFile(vsdx_copy("test10_nested_shapes.vsdx")) as vis:
        page = vis.pages[0]
        group = next(shape for shape in page.child_shapes if shape.child_shapes)
        child = group.child_shapes[0]
        survivor = next(shape for shape in page.child_shapes if shape.ID != group.ID)
        _add_connect(page, "99", child.ID)
        _add_connect(page, "99", survivor.ID)

        page.delete_shape(group)

        assert _referencing(page, child.ID) == []
        assert _referencing(page, survivor.ID), "an unrelated record must survive"


def test_deleting_a_shape_that_is_not_on_the_page_is_an_error(vsdx_copy):
    """Silently doing nothing would hide a caller's mistake."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        shape = vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="A")
        page.delete_shape(shape)

        with pytest.raises(ValueError, match="not on page"):
            page.delete_shape(shape)


def test_removing_the_same_shape_twice_is_an_error(vsdx_copy):
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        shape = vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="A")
        with pytest.warns(DeprecationWarning):
            shape.remove()
        with pytest.warns(DeprecationWarning), pytest.raises(ValueError, match="not on page"):
            shape.remove()


def test_an_inherited_begin_cell_still_marks_a_shape_as_a_connector(vsdx_copy):
    """The 1-D test must see through master inheritance.

    A connector that inherits BeginX from its master would otherwise survive
    the shape it is glued to, as a detached line whose glue record has just
    been swept away.
    """
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        start = vis.create_shape(page, "PALETTE_PROCESS", 2.0, 2.0, text="A")
        end = vis.create_shape(page, "PALETTE_PROCESS", 6.0, 2.0, text="B")
        connector = page.connect_shapes(start, end)
        # move BeginX off the connector so it can only be found via the master
        begin_cell = connector.xml.find(f'{namespace}Cell[@N="BeginX"]')
        connector.xml.remove(begin_cell)
        master = connector.master_shape
        assert master is not None, "fixture connector is expected to have a master"
        master.xml.append(begin_cell)

        page.delete_shape(start)

        assert connector.ID not in {shape.ID for shape in page.all_shapes}
