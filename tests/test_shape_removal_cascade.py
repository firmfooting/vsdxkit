"""`Shape.delete()` must not leave a page half-deleted.

It removes the connectors glued to the shape and their `Connect` records. 0.x's
`Shape.remove()` once detached the element and nothing else, leaving dangling
records and orphan connectors that Visio repairs on open.
"""

import os
import xml.etree.ElementTree as ET

import pytest

from vsdxkit import namespace
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.shape_kind import ShapeKind

FIXTURES = os.path.dirname(os.path.realpath(__file__))


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
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    start = page.create_shape(ShapeKind.PROCESS, x=2.0, y=2.0, text="A")
    end = page.create_shape(ShapeKind.PROCESS, x=6.0, y=2.0, text="B")
    connector = page.connect(start, end)
    assert _referencing(page, start.ID)

    start.delete()

    assert _referencing(page, start.ID) == []
    assert _referencing(page, connector.ID) == []
    remaining = {shape.ID for shape in page.shapes}
    assert start.ID not in remaining
    assert connector.ID not in remaining, "the connector was left with nothing to glue to"


def test_removing_a_group_child_removes_records_that_reference_it(vsdx_copy):
    """A record pointing into a group must not outlive the shape it points at."""
    vis = Document.open(vsdx_copy("test10_nested_shapes.vsdx"))
    page = vis.pages[0]
    group = next(shape for shape in page.children if shape.children)
    child = next(iter(group.children))

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

    child.delete()

    assert _referencing(page, child.ID) == []
    assert child.ID not in {shape.ID for shape in group.children}


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
    vis = Document.open(vsdx_copy("test10_nested_shapes.vsdx"))
    page = vis.pages[0]
    group = next(shape for shape in page.children if shape.children)
    child = next(iter(group.children))
    survivor = next(shape for shape in page.children if shape.ID != group.ID)
    _add_connect(page, "99", child.ID)
    _add_connect(page, "99", survivor.ID)

    group.delete()

    assert _referencing(page, child.ID) == []
    assert _referencing(page, survivor.ID), "an unrelated record must survive"


def test_deleting_the_same_shape_twice_is_an_error(vsdx_copy):
    """Silently doing nothing would hide a caller's mistake."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shape = page.create_shape(ShapeKind.PROCESS, x=2.0, y=2.0, text="A")
    shape.delete()

    with pytest.raises(InvalidOperationError, match="no longer in the document"):
        shape.delete()


def test_an_inherited_begin_cell_still_marks_a_shape_as_a_connector(vsdx_copy):
    """The 1-D test must see through master inheritance.

    A connector that inherits BeginX from its master would otherwise survive
    the shape it is glued to, as a detached line whose glue record has just
    been swept away.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    start = page.create_shape(ShapeKind.PROCESS, x=2.0, y=2.0, text="A")
    end = page.create_shape(ShapeKind.PROCESS, x=6.0, y=2.0, text="B")
    connector = page.connect(start, end)
    # move BeginX off the connector so it can only be found via the master
    begin_cell = connector.xml.find(f'{namespace}Cell[@N="BeginX"]')
    connector.xml.remove(begin_cell)
    master = connector.master_shape
    assert master is not None, "fixture connector is expected to have a master"
    master.xml.append(begin_cell)

    start.delete()

    assert connector.ID not in {shape.ID for shape in page.shapes}


def test_deleting_a_shape_leaves_a_shape_of_its_id_on_another_page(vsdx_copy):
    """Shape IDs are page-scoped and collide, so a deletion must not be matched on ID.

    `test1.vsdx` has a shape with ID 1 on both Page-1 and Page-3. 0.x's
    `shape.delete()` once matched on the ID and deleted whichever shape
    on the page it was called on shared the number.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page1, page3 = vis.pages[0], vis.pages[2]
    victim = page1.shapes.require_id("1")
    bystander_ids = [shape.ID for shape in page3.shapes]
    assert "1" in bystander_ids, "fixture must have colliding ids"

    victim.delete()

    assert [shape.ID for shape in page3.shapes] == bystander_ids
    assert page1.shapes.by_id("1") is None


def _three_connected(vis):
    """A-B and B-C joined by connectors: the page, the shapes and the connectors."""
    page = vis.pages[0]
    a = page.create_shape(ShapeKind.PROCESS, x=1.0, y=2.0, text="A")
    b = page.create_shape(ShapeKind.PROCESS, x=4.0, y=2.0, text="B")
    c = page.create_shape(ShapeKind.PROCESS, x=7.0, y=2.0, text="C")
    return page, (a, b, c), (page.connect(a, b), page.connect(b, c))


def test_a_half_glued_connector_goes_with_the_shape_it_is_glued_to(vsdx_copy):
    """Fails if a connector whose other end floats survives the one shape it was glued to (#105)."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page, (a, b, _), (ab, _) = _three_connected(vis)
    connects = page.xml.find(f".//{namespace}Connects")
    end_record = next(
        record
        for record in _connect_records(page)
        if record.attrib["FromSheet"] == ab.ID and record.attrib["FromCell"] == "EndX"
    )
    connects.remove(end_record)  # its end now floats; only its begin is glued, to A

    a.delete()

    assert page.shapes.by_id(ab.ID) is None
    assert _referencing(page, ab.ID) == []
    assert page.shapes.by_id(b.ID) is not None


def test_deleting_a_connector_leaves_the_shapes_it_joined_and_their_other_glue(vsdx_copy):
    """Fails if deleting a connector directly cascades into the shapes it joins (#105)."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page, (a, b, c), (ab, bc) = _three_connected(vis)

    ab.delete()

    assert page.shapes.by_id(ab.ID) is None
    assert _referencing(page, ab.ID) == []
    for shape in (a, b, c, bc):
        assert page.shapes.by_id(shape.ID) is not None
    assert {record.attrib["FromCell"] for record in _referencing(page, bc.ID)} == {"BeginX", "EndX"}


def test_every_shape_a_delete_takes_is_detached(vsdx_copy):
    """Fails if a connector removed by the cascade still answers through a Shape held before the delete (#105)."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    _page, (_, b, _), (ab, bc) = _three_connected(vis)

    b.delete()

    for gone in (b, ab, bc):
        assert not gone.is_attached
        with pytest.raises(InvalidOperationError, match="no longer in the document"):
            _ = gone.text


def test_a_shape_a_showif_hides_takes_its_connectors_and_records(vsdx_copy):
    """Fails if a template that renders a shape out leaves its connector and glue behind (#105).

    The shape leaves the page through the template, not through
    `Shape.delete`, and the connector glued to it survived with a record
    naming a shape no longer there.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page, (a, b, c), (ab, bc) = _three_connected(vis)
    a.text = "{% showif show_a %}A"

    vis.render({"show_a": False})

    page = vis.pages[0]
    ids = {shape.ID for shape in page.shapes}
    assert a.ID not in ids
    assert ab.ID not in ids
    assert _referencing(page, a.ID) == []
    assert _referencing(page, ab.ID) == []
    assert {b.ID, c.ID, bc.ID} <= ids
    assert len(_referencing(page, bc.ID)) == 2


def test_a_connector_a_showif_hides_takes_only_its_own_records(vsdx_copy):
    """Fails if a connector rendered out leaves its glue records naming it (#105)."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page, (a, b, _), (ab, bc) = _three_connected(vis)
    ab.text = "{% showif False %}"

    vis.render({})

    page = vis.pages[0]
    ids = {shape.ID for shape in page.shapes}
    assert ab.ID not in ids
    assert _referencing(page, ab.ID) == []
    assert {a.ID, b.ID, bc.ID} <= ids
    assert len(_referencing(page, bc.ID)) == 2
