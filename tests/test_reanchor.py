"""Tests for connector retargeting (re-anchor)."""

import os
import zipfile

import pytest

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.glue import ConnectorOptions, Glue, Routing
from vsdxkit.shape_kind import ShapeKind

BASE = "test8_simple_connector.vsdx"
# shapes 90, 97 and 102 have eight connection points of their own; 53 inherits four
S05 = os.path.join("fixtures", "com_reference", "s05_swimlanes_cfflow.vsdx")


def _records(page, connector):
    """The connector's records, by the end they glue: the shape and the cell each names."""
    return {c.from_rel: (c.to_id, c.to_rel) for c in page.connects if c.from_id == connector.ID}


def _state(page, connector):
    """Everything a refused retarget must leave alone."""
    cells = sorted((name, cell.formula, cell.value) for name, cell in connector.cells.items())
    records = sorted((c.from_id, c.from_rel, c.to_id, c.to_rel) for c in page.connects)
    return cells, records


def _drop_record(page, connector, end):
    (record,) = [c for c in page.connects if c.from_id == connector.ID and c.from_rel == end]
    page.xml.find(".//{http://schemas.microsoft.com/office/visio/2012/main}Connects").remove(record.xml)


def test_retarget_both_ends(vsdx_copy):
    path = vsdx_copy(BASE)
    vis = Document.open(path)
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect(a, b)
    # fresh shapes to retarget to
    c = page.create_shape(ShapeKind.PROCESS, x=7.0, y=6.0, text="Target C")
    d = page.create_shape(ShapeKind.PROCESS, x=7.0, y=3.0, text="Target D")

    connector.retarget(source=c, target=d)

    records = [rc for rc in page.connects if rc.from_id == str(connector.ID)]
    endpoints = {(rc.from_rel, rc.to_id) for rc in records}
    assert ("BeginX", str(c.ID)) in endpoints
    assert ("EndX", str(d.ID)) in endpoints
    # old records replaced, not duplicated
    assert len(records) == 2
    # triggers reference the new shapes
    assert f"Sheet{c.ID}!" in connector.cells["BegTrigger"].formula
    assert f"Sheet{d.ID}!" in connector.cells["EndTrigger"].formula
    vis.save(path)
    assert zipfile.ZipFile(path).testzip() is None


def test_retarget_one_end_keeps_other(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect(a, b)
    c = page.create_shape(ShapeKind.PROCESS, x=7.0, y=6.0, text="Target C")

    connector.retarget(target=c)  # keep begin at A

    records = [rc for rc in page.connects if rc.from_id == str(connector.ID)]
    endpoints = {(rc.from_rel, rc.to_id) for rc in records}
    assert ("BeginX", str(a.ID)) in endpoints  # kept
    assert ("EndX", str(c.ID)) in endpoints  # moved


def test_retarget_a_connector_glued_at_neither_end_glues_the_end_named(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect(a, b)
    page.remove_connect_records([connector.ID])
    begin = (connector.begin_x, connector.begin_y)

    connector.retarget(target=b)

    assert _records(page, connector) == {"EndX": (b.ID, "PinX")}
    assert (connector.begin_x, connector.begin_y) == begin


def test_remove_connect_records_normalises_integer_ids(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    assert a is not None and b is not None
    connector = page.connect(a, b)
    connector_id = str(connector.ID)

    assert any(record.from_id == connector_id for record in page.connects)
    page.remove_connect_records([int(connector_id)])
    assert all(record.from_id != connector_id for record in page.connects)


def test_moving_one_end_of_a_point_glued_connector_keeps_point_glue(vsdx_copy):
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect(source, target, glue=Glue.POINT, from_point=1, to_point=2)

    connector.retarget(target=other)

    assert _records(page, connector) == {"BeginX": ("90", "Connections.X2"), "EndX": ("102", "Connections.X3")}
    assert connector.cells["EndX"].formula == "PAR(PNT(Sheet102!Connections.X3,Sheet102!Connections.Y3))"
    assert connector.cells["EndTrigger"].formula == "_XFTRIGGER(Sheet102!EventXFMod)"


def test_a_retained_point_the_new_shape_lacks_is_refused(vsdx_copy):
    """The end keeps point 8; shape 53 has four. It must not fall back to dynamic glue."""
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, decision = (page.shapes.by_id(i) for i in ("90", "97", "53"))
    connector = page.connect(source, target, glue=Glue.POINT, to_point=7)
    before = _state(page, connector)

    with pytest.raises(InvalidOperationError, match="connection point"):
        connector.retarget(target=decision)

    assert _state(page, connector) == before


def test_a_floating_end_being_replaced_gets_dynamic_glue(vsdx_copy):
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect(source, target, glue=Glue.POINT, from_point=1, to_point=2)
    _drop_record(page, connector, "EndX")

    connector.retarget(target=other)

    assert _records(page, connector) == {"BeginX": ("90", "Connections.X2"), "EndX": ("102", "PinX")}
    assert connector.cells["EndX"].formula == "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"


def test_moving_the_glued_end_leaves_a_floating_end_floating(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect(a, b)
    c = page.create_shape(ShapeKind.PROCESS, x=7.0, y=6.0, text="Target C")
    _drop_record(page, connector, "BeginX")
    begin = (connector.begin_x, connector.begin_y)

    connector.retarget(target=c)

    assert _records(page, connector) == {"EndX": (c.ID, "PinX")}
    assert (connector.begin_x, connector.begin_y) == begin


def test_retarget_keeps_the_routing(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect(a, b, routing=Routing.CURVED)
    c = page.create_shape(ShapeKind.PROCESS, x=7.0, y=6.0, text="Target C")

    connector.retarget(target=c)

    assert connector.cells["ShapeRouteStyle"].value == "17"
    assert connector.cells["ConLineRouteExt"].value == "2"


def test_options_replace_the_glue_of_both_ends(vsdx_copy):
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect(source, target, glue=Glue.POINT, from_point=1, to_point=2)

    connector.retarget(target=other, options=ConnectorOptions())

    assert _records(page, connector) == {"BeginX": ("90", "PinX"), "EndX": ("102", "PinX")}
    assert connector.cells["ShapeRouteStyle"].value == "0"


def _own_cell(connector, name):
    """The connector's own cell `name`, or None where it inherits it."""
    return connector.xml.find(f'{{http://schemas.microsoft.com/office/visio/2012/main}}Cell[@N="{name}"]')


def test_options_to_point_glue_replace_dynamic_routing_and_glue_cells(vsdx_copy):
    """Codex on #401: a dynamic connector moved to point glue kept ShapeRouteStyle=0 and GlueType=2."""
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    dynamic = page.connect(source, target)
    point = page.connect(source, target, glue=Glue.POINT)

    dynamic.retarget(target=other, options=ConnectorOptions(glue=Glue.POINT))
    point.retarget(target=other)

    for name in ("ShapeRouteStyle", "ConLineRouteExt", "ConFixedCode"):
        assert dynamic.cells[name].value == point.cells[name].value, name
    assert _own_cell(dynamic, "GlueType") is None
    assert _own_cell(dynamic, "ObjType") is None


def test_options_uncurve_a_curved_point_connector(vsdx_copy):
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target = page.shapes.by_id("90"), page.shapes.by_id("97")
    connector = page.connect(source, target, glue=Glue.POINT, routing=Routing.CURVED)

    connector.retarget(target=target, options=ConnectorOptions(glue=Glue.POINT, routing=Routing.STRAIGHT))

    values = {name: connector.cells[name].value for name in ("ShapeRouteStyle", "ConLineRouteExt", "ConFixedCode")}
    assert values == {"ShapeRouteStyle": "16", "ConLineRouteExt": "1", "ConFixedCode": "6"}


def test_a_kept_floating_end_loses_its_old_glue(vsdx_copy):
    """Codex on #401: a floating begin kept `PAR(PNT(Sheet90!...))`, so Visio would glue it back to 90."""
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect(source, target, glue=Glue.POINT, from_point=1, to_point=2)
    _drop_record(page, connector, "BeginX")
    begin = (connector.begin_x, connector.begin_y)

    connector.retarget(target=other)

    assert connector.cells["BeginX"].formula is None
    assert connector.cells["BeginY"].formula is None
    assert _own_cell(connector, "BegTrigger") is None
    assert (connector.begin_x, connector.begin_y) == begin
    assert not any("Sheet90!" in (cell.formula or "") for cell in connector.cells.values())


def test_retarget_removes_the_begintrigger_earlier_releases_wrote(vsdx_copy):
    """Codex on #401: point glue before #106 wrote a `BeginTrigger` cell, which Visio does not have."""
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect(source, target, glue=Glue.POINT)
    connector.get_or_create_cell("BeginTrigger", f="_XFTRIGGER(Sheet90!EventXFMod)")

    connector.retarget(target=other)

    assert _own_cell(connector, "BeginTrigger") is None


def test_a_record_without_toparts_keeps_its_point_glue(vsdx_copy):
    """Codex on #401: `ToPart` is optional, and `ToCell` alone still names the point."""
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect(source, target, glue=Glue.POINT, from_point=1, to_point=2)
    for record in page.connects:
        if record.from_id == connector.ID:
            del record.xml.attrib["ToPart"]

    connector.retarget(target=other)

    assert _records(page, connector) == {"BeginX": ("90", "Connections.X2"), "EndX": ("102", "Connections.X3")}


def test_a_route_still_replaces_the_glue_of_both_ends(vsdx_copy):
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect(source, target)

    connector.retarget(target=other, options=ConnectorOptions(glue=Glue.POINT, to_point=4))

    assert _records(page, connector) == {"BeginX": ("90", "Connections.X1"), "EndX": ("102", "Connections.X5")}


def _refused(page, connector, **endpoints):
    before = _state(page, connector)
    with pytest.raises(InvalidOperationError) as excinfo:
        connector.retarget(**endpoints)
    assert _state(page, connector) == before
    return str(excinfo.value)


def test_retarget_with_no_endpoint_is_refused(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    connector = page.connect(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))
    assert "at least one endpoint" in _refused(page, connector)


def test_a_connector_cannot_be_its_own_endpoint(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    connector = page.connect(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))
    assert "itself" in _refused(page, connector, target=connector)


def test_an_endpoint_on_another_page_is_refused(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    connector = page.connect(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))
    elsewhere = vis.add_page("Elsewhere").create_shape(ShapeKind.PROCESS, x=1.0, y=1.0, text="Elsewhere")
    assert "not on page" in _refused(page, connector, target=elsewhere)


def test_a_connector_on_another_page_is_refused(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    other = vis.add_page("Elsewhere")
    start = other.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0, text="Start")
    finish = other.create_shape(ShapeKind.PROCESS, x=4.0, y=1.0, text="Finish")
    connector = other.connect(start, finish)
    before = _state(other, connector)
    with pytest.raises(InvalidOperationError, match="not on page"):
        connector.retarget(target=a)
    assert _state(other, connector) == before


def test_a_deleted_endpoint_is_refused(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    connector = page.connect(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))
    gone = page.create_shape(ShapeKind.PROCESS, x=7.0, y=6.0, text="Gone")
    page.delete_shape(gone)
    assert "not on page" in _refused(page, connector, target=gone)


def test_connecting_to_a_shape_on_another_page_is_refused(vsdx_copy):
    vis = Document.open(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    elsewhere = vis.add_page("Elsewhere").create_shape(ShapeKind.PROCESS, x=1.0, y=1.0, text="Elsewhere")
    shapes_before = len(page.shapes)
    with pytest.raises(InvalidOperationError, match="not on page"):
        page.connect(a, elsewhere)
    assert len(page.shapes) == shapes_before


def test_a_connector_visio_glued_to_points_keeps_them(vsdx_copy):
    """Visio glued connector 59 from point 3 of shape 54 to point 3 of shape 53; both inherit their points."""
    vis = Document.open(vsdx_copy(S05))
    page = vis.pages[0]
    connector, start = page.shapes.by_id("59"), page.shapes.by_id("52")

    connector.retarget(target=start)

    assert _records(page, connector) == {"BeginX": ("54", "Connections.X3"), "EndX": ("52", "Connections.X3")}
