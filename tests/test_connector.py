"""Connector: the 1-D shape, its ends, and the graph queries over them (#109)."""

import copy
import os
import xml.etree.ElementTree as ET

import pytest
from helpers.connect_records import page_records

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError, PackageError
from vsdxkit.glue import ConnectorOptions, Glue, Routing
from vsdxkit.pages import Page
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.shapes import Connector, Shape

BASE = "test8_simple_connector.vsdx"
# two master-instance connectors among shapes A, B and C
WIRED = "test4_connectors.vsdx"
# shapes 90, 97 and 102 have eight connection points of their own; 53 inherits four
S05 = os.path.join("fixtures", "com_reference", "s05_swimlanes_cfflow.vsdx")
NS = "{http://schemas.microsoft.com/office/visio/2012/main}"


def _page(vsdx_copy, name=BASE):
    return Document.open(vsdx_copy(name)).pages[0]


def _ends(page):
    a = page.shapes.require_text("Shape A")
    b = page.shapes.require_text("Shape B")
    return a, b


def _drop_record(page, connector, end):
    (record,) = [c for c in page_records(page) if c.from_id == connector.ID and c.from_rel == end]
    page.xml.find(f".//{NS}Connects").remove(record.xml)


def _state(page, connector):
    cells = sorted((name, cell.formula, cell.value) for name, cell in connector.cells.items())
    records = sorted((c.from_id, c.from_rel, c.to_id, c.to_rel) for c in page_records(page))
    return cells, records


def test_a_walk_wraps_exactly_the_one_d_shapes_as_connectors(vsdx_copy):
    page = _page(vsdx_copy)
    for shape in page.shapes:
        assert isinstance(shape, Connector) == ("BeginX" in shape.cells), shape


def test_a_master_instance_is_a_connector_by_its_master(vsdx_copy):
    """Fails if the 1-D test reads only the shape's own cells, not the master's it inherits."""
    page = _page(vsdx_copy, WIRED)
    connector = page.connectors[0]
    assert connector.master_shape is not None
    assert connector.master_shape.xml.find(f'{NS}Cell[@N="BeginX"]') is not None
    own = connector.xml.find(f'{NS}Cell[@N="BeginX"]')
    connector.xml.remove(own)

    assert page.connectors[0] == connector


def test_a_shape_and_a_connector_over_one_element_are_equal(vsdx_copy):
    page = _page(vsdx_copy, WIRED)
    connector = page.connectors[0]
    plain = Shape(connector.xml, connector.parent, page)
    assert plain == connector
    assert hash(plain) == hash(connector)


def test_connect_returns_a_connector_glued_at_both_ends(vsdx_copy):
    page = _page(vsdx_copy)
    a, b = _ends(page)

    connector = page.connect(a, b)

    assert isinstance(connector, Connector)
    assert (connector.source, connector.target) == (a, b)
    assert connector in page.connectors


def test_connect_takes_glue_and_routing_as_keywords(vsdx_copy):
    page = _page(vsdx_copy, S05)
    source, target = page.shapes.require_id("90"), page.shapes.require_id("97")

    connector = page.connect(source, target, glue=Glue.POINT, routing=Routing.CURVED, from_point=1, to_point=2)

    records = {c.from_rel: (c.to_id, c.to_rel) for c in page_records(page) if c.from_id == connector.ID}
    assert records == {"BeginX": ("90", "Connections.X2"), "EndX": ("97", "Connections.X3")}
    assert connector.cells["ShapeRouteStyle"].value == "17"


@pytest.mark.parametrize("routing", [Routing.DEFAULT, Routing.CURVED])
def test_a_new_connector_carries_no_sentinel_text(vsdx_copy, routing):
    """Fails if a connector keeps the text it was found by in the bundled document, which Visio shows as its label."""
    page = _page(vsdx_copy)
    a, b = _ends(page)
    assert page.connect(a, b, routing=routing).text == ""


def test_connect_imports_the_line_style_its_master_names_once(vsdx_copy):
    """Fails if the connector's line style is not imported, so it names a StyleSheet the file lacks, or is imported again on each connect."""
    path = vsdx_copy("test1.vsdx")
    vis = Document.open(path)
    before = [style.attrib["ID"] for style in vis._style_sheets()]
    page = vis.pages[0]
    a, b = list(page.children)[:2]

    style_id = page.connect(a, b).master_shape.line_style_id
    page.connect(b, a)
    vis.save()

    assert style_id is not None and style_id not in before
    after = [style.attrib["ID"] for style in Document.open(path)._style_sheets()]
    assert after.count(style_id) == 1
    assert len(after) == len(before) + 1


def test_connect_takes_no_positional_options(vsdx_copy):
    page = _page(vsdx_copy)
    a, b = _ends(page)
    with pytest.raises(TypeError):
        page.connect(a, b, Glue.POINT)  # type: ignore[misc]


def test_a_floating_end_is_none_and_the_connector_is_still_listed(vsdx_copy):
    page = _page(vsdx_copy)
    a, b = _ends(page)
    connector = page.connect(a, b)
    _drop_record(page, connector, "BeginX")

    assert connector.source is None
    assert connector.target == b
    assert connector in page.connectors
    assert connector not in a.connectors
    assert connector in b.connectors


def test_a_fully_floating_connector_is_listed_with_no_incidence(vsdx_copy):
    page = _page(vsdx_copy)
    a, b = _ends(page)
    connector = page.connect(a, b)
    _drop_record(page, connector, "BeginX")
    _drop_record(page, connector, "EndX")

    assert (connector.source, connector.target) == (None, None)
    assert connector in page.connectors
    assert connector not in b.connectors
    assert a not in b.connected_shapes


def test_connected_shapes_are_the_other_ends_once_each(vsdx_copy):
    page = _page(vsdx_copy)
    a, b = _ends(page)
    c = page.create_shape(ShapeKind.PROCESS, x=7.0, y=6.0, text="C")
    first = page.connect(a, b)
    second = page.connect(a, b)
    third = page.connect(c, a)

    assert set(a.connectors) >= {first, second, third}
    assert a.connected_shapes.count(b) == 1
    assert c in a.connected_shapes
    assert a not in a.connected_shapes
    assert isinstance(a.connectors, tuple)
    assert isinstance(a.connected_shapes, tuple)
    assert isinstance(page.connectors, tuple)


def test_a_record_that_glues_no_end_is_not_incidence(vsdx_copy):
    """Fails if a Connect record from a connector's other cells counts as one of its ends being glued."""
    page = _page(vsdx_copy)
    a, b = _ends(page)
    c = page.create_shape(ShapeKind.PROCESS, x=7.0, y=6.0, text="C")
    connector = page.connect(a, b)
    record = ET.SubElement(page.xml.find(f".//{NS}Connects"), f"{NS}Connect")
    record.attrib.update({"FromSheet": connector.ID, "FromCell": "Controls.Row_1", "ToSheet": c.ID, "ToCell": "PinX"})

    assert connector not in c.connectors
    assert c.connected_shapes == ()
    assert c not in a.connected_shapes


def test_a_master_edited_into_a_line_makes_its_instances_connectors(vsdx_copy):
    """Fails if whether a master is 1-D is remembered past an edit to its cells."""
    page = _page(vsdx_copy, WIRED)
    connectors = page.connectors
    assert connectors
    master = connectors[0].master_shape
    for connector in connectors:
        connector.xml.remove(connector.xml.find(f'{NS}Cell[@N="BeginX"]'))
    # 1-D now only by the master, which this walk asks about
    assert page.connectors == connectors

    master.xml.remove(master.xml.find(f'{NS}Cell[@N="BeginX"]'))

    assert page.connectors == ()


def test_a_master_whose_shape_is_replaced_is_read_anew(vsdx_copy):
    """Fails if the master shape an instance inherits from is remembered past its replacement."""
    page = _page(vsdx_copy, WIRED)
    connectors = page.connectors
    master = connectors[0].master_shape
    for connector in connectors:
        connector.xml.remove(connector.xml.find(f'{NS}Cell[@N="BeginX"]'))
    assert page.connectors == connectors
    holder = master.page.xml.getroot().find(f"{NS}Shapes")
    replacement = copy.deepcopy(master.xml)
    replacement.remove(replacement.find(f'{NS}Cell[@N="BeginX"]'))
    holder.remove(master.xml)
    holder.insert(0, replacement)

    assert page.connectors == ()


def test_a_floating_end_is_not_a_shape_without_an_id(vsdx_copy):
    """Fails if an absent end is looked up and resolves to a malformed shape that has no ID."""
    page = _page(vsdx_copy)
    a, b = _ends(page)
    connector = page.connect(a, b)
    _drop_record(page, connector, "BeginX")
    shapes = page.xml.getroot().find(f"{NS}Shapes")
    for _ in range(2):
        nameless = copy.deepcopy(a.xml)
        del nameless.attrib["ID"]
        shapes.append(nameless)

    assert b.connected_shapes == ()
    assert b.connectors == (connector,)


def test_a_duplicate_id_makes_the_graph_refuse(vsdx_copy):
    """Fails if the endpoint index picks one of two shapes sharing an ID rather than reporting the invalid page."""
    page = _page(vsdx_copy)
    a, b = _ends(page)
    page.connect(a, b)
    twin = copy.deepcopy(b.xml)
    page.xml.getroot().find(f"{NS}Shapes").append(twin)

    with pytest.raises(PackageError, match=f"ID {b.ID}"):
        a.connected_shapes  # noqa: B018


@pytest.mark.parametrize("query", ["connectors", "connected_shapes", "source", "target"])
def test_a_detached_shape_refuses_graph_queries(vsdx_copy, query):
    """Fails if a shape on a deleted page still reports that page's connectors as live."""
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages.create("Doomed")
    start = page.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0, text="Start")
    finish = page.create_shape(ShapeKind.PROCESS, x=4.0, y=1.0, text="Finish")
    connector = page.connect(start, finish)
    vis.pages.delete(page)

    subject = connector if query in ("source", "target") else start
    with pytest.raises(InvalidOperationError):
        getattr(subject, query)


def test_retarget_moves_the_named_end_and_keeps_the_other(vsdx_copy):
    page = _page(vsdx_copy)
    a, b = _ends(page)
    connector = page.connect(a, b)
    c = page.create_shape(ShapeKind.PROCESS, x=7.0, y=6.0, text="C")

    assert connector.retarget(target=c) is None

    assert (connector.source, connector.target) == (a, c)


def test_retarget_keeps_the_connection_point_without_options(vsdx_copy):
    page = _page(vsdx_copy, S05)
    source, target, other = (page.shapes.require_id(i) for i in ("90", "97", "102"))
    connector = page.connect(source, target, glue=Glue.POINT, from_point=1, to_point=2)

    connector.retarget(target=other)

    records = {c.from_rel: (c.to_id, c.to_rel) for c in page_records(page) if c.from_id == connector.ID}
    assert records == {"BeginX": ("90", "Connections.X2"), "EndX": ("102", "Connections.X3")}


def test_retarget_with_options_replaces_the_glue(vsdx_copy):
    page = _page(vsdx_copy, S05)
    source, target = page.shapes.require_id("90"), page.shapes.require_id("97")
    connector = page.connect(source, target, glue=Glue.POINT, from_point=1, to_point=2)

    connector.retarget(source=source, options=ConnectorOptions())

    records = {c.from_rel: (c.to_id, c.to_rel) for c in page_records(page) if c.from_id == connector.ID}
    assert records == {"BeginX": ("90", "PinX"), "EndX": ("97", "PinX")}


def test_retarget_without_an_endpoint_is_refused(vsdx_copy):
    page = _page(vsdx_copy)
    a, b = _ends(page)
    connector = page.connect(a, b)
    before = _state(page, connector)

    with pytest.raises(InvalidOperationError, match="at least one endpoint"):
        connector.retarget(options=ConnectorOptions(routing=Routing.CURVED))

    assert _state(page, connector) == before


def test_retarget_to_a_missing_point_is_refused_before_writing(vsdx_copy):
    page = _page(vsdx_copy, S05)
    source, target = page.shapes.require_id("90"), page.shapes.require_id("97")
    four_points = page.shapes.require_id("53")
    connector = page.connect(source, target, glue=Glue.POINT, from_point=1, to_point=7)
    before = _state(page, connector)

    with pytest.raises(InvalidOperationError, match="connection point"):
        connector.retarget(target=four_points)

    assert _state(page, connector) == before


def test_retarget_takes_keywords_only(vsdx_copy):
    page = _page(vsdx_copy)
    a, b = _ends(page)
    connector = page.connect(a, b)
    with pytest.raises(TypeError):
        connector.retarget(a)  # type: ignore[misc]


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        (Page, "connect_shapes"),
        (Page, "reanchor_connector"),
        (Page, "get_connectors_between"),
        (ConnectorOptions, "from_route"),
    ],
)
def test_the_0x_connector_calls_are_gone(owner, name):
    assert not hasattr(owner, name)


def test_the_connection_record_class_is_gone():
    from vsdxkit import connectors

    assert not hasattr(connectors, "Connect")
