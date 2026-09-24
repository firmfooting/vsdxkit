"""Tests for connector retargeting (re-anchor)."""

import os
import zipfile

import pytest

from vsdxkit.errors import InvalidOperationError
from vsdxkit.glue import ConnectorOptions, Glue
from vsdxkit.vsdxfile import VisioFile

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
    vis = VisioFile(path)
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect_shapes(a, b)
    # fresh shapes to retarget to
    c = vis.create_shape(page, "PALETTE_PROCESS", 7.0, 6.0, text="Target C")
    d = vis.create_shape(page, "PALETTE_PROCESS", 7.0, 3.0, text="Target D")

    page.reanchor_connector(connector, from_shape=c, to_shape=d)

    records = [rc for rc in page.connects if rc.from_id == str(connector.ID)]
    endpoints = {(rc.from_rel, rc.to_id) for rc in records}
    assert ("BeginX", str(c.ID)) in endpoints
    assert ("EndX", str(d.ID)) in endpoints
    # old records replaced, not duplicated
    assert len(records) == 2
    # triggers reference the new shapes
    assert f"Sheet{c.ID}!" in connector.cells["BegTrigger"].formula
    assert f"Sheet{d.ID}!" in connector.cells["EndTrigger"].formula
    vis.save_vsdx(path)
    assert zipfile.ZipFile(path).testzip() is None


def test_retarget_one_end_keeps_other(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect_shapes(a, b)
    c = vis.create_shape(page, "PALETTE_PROCESS", 7.0, 6.0, text="Target C")

    page.reanchor_connector(connector, to_shape=c)  # keep begin at A

    records = [rc for rc in page.connects if rc.from_id == str(connector.ID)]
    endpoints = {(rc.from_rel, rc.to_id) for rc in records}
    assert ("BeginX", str(a.ID)) in endpoints  # kept
    assert ("EndX", str(c.ID)) in endpoints  # moved


def test_retarget_a_connector_glued_at_neither_end_glues_the_end_named(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect_shapes(a, b)
    page.remove_connect_records([connector.ID])
    begin = (connector.begin_x, connector.begin_y)

    page.reanchor_connector(connector, to_shape=b)

    assert _records(page, connector) == {"EndX": (b.ID, "PinX")}
    assert (connector.begin_x, connector.begin_y) == begin


def test_remove_connect_records_normalises_integer_ids(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    assert a is not None and b is not None
    connector = page.connect_shapes(a, b)
    connector_id = str(connector.ID)

    assert any(record.from_id == connector_id for record in page.connects)
    page.remove_connect_records([int(connector_id)])
    assert all(record.from_id != connector_id for record in page.connects)


def test_moving_one_end_of_a_point_glued_connector_keeps_point_glue(vsdx_copy):
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect_shapes(source, target, route="point", from_cp=1, to_cp=2)

    page.reanchor_connector(connector, to_shape=other)

    assert _records(page, connector) == {"BeginX": ("90", "Connections.X2"), "EndX": ("102", "Connections.X3")}
    assert connector.cells["EndX"].formula == "PAR(PNT(Sheet102!Connections.X3,Sheet102!Connections.Y3))"
    assert connector.cells["EndTrigger"].formula == "_XFTRIGGER(Sheet102!EventXFMod)"


def test_a_retained_point_the_new_shape_lacks_is_refused(vsdx_copy):
    """The end keeps point 8; shape 53 has four. It must not fall back to dynamic glue."""
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, decision = (page.shapes.by_id(i) for i in ("90", "97", "53"))
    connector = page.connect_shapes(source, target, route="point", to_cp=7)
    before = _state(page, connector)

    with pytest.raises(InvalidOperationError, match="connection point"):
        page.reanchor_connector(connector, to_shape=decision)

    assert _state(page, connector) == before


def test_a_floating_end_being_replaced_gets_dynamic_glue(vsdx_copy):
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect_shapes(source, target, route="point", from_cp=1, to_cp=2)
    _drop_record(page, connector, "EndX")

    page.reanchor_connector(connector, to_shape=other)

    assert _records(page, connector) == {"BeginX": ("90", "Connections.X2"), "EndX": ("102", "PinX")}
    assert connector.cells["EndX"].formula == "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"


def test_moving_the_glued_end_leaves_a_floating_end_floating(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect_shapes(a, b)
    c = vis.create_shape(page, "PALETTE_PROCESS", 7.0, 6.0, text="Target C")
    _drop_record(page, connector, "BeginX")
    begin = (connector.begin_x, connector.begin_y)

    page.reanchor_connector(connector, to_shape=c)

    assert _records(page, connector) == {"EndX": (c.ID, "PinX")}
    assert (connector.begin_x, connector.begin_y) == begin


def test_retarget_keeps_the_routing(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect_shapes(a, b, route="curved")
    c = vis.create_shape(page, "PALETTE_PROCESS", 7.0, 6.0, text="Target C")

    page.reanchor_connector(connector, to_shape=c)

    assert connector.cells["ShapeRouteStyle"].value == "17"
    assert connector.cells["ConLineRouteExt"].value == "2"


def test_options_replace_the_glue_of_both_ends(vsdx_copy):
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect_shapes(source, target, route="point", from_cp=1, to_cp=2)

    page.reanchor_connector(connector, to_shape=other, options=ConnectorOptions())

    assert _records(page, connector) == {"BeginX": ("90", "PinX"), "EndX": ("102", "PinX")}
    assert connector.cells["ShapeRouteStyle"].value == "0"


def _own_cell(connector, name):
    """The connector's own cell `name`, or None where it inherits it."""
    return connector.xml.find(f'{{http://schemas.microsoft.com/office/visio/2012/main}}Cell[@N="{name}"]')


def test_options_to_point_glue_replace_dynamic_routing_and_glue_cells(vsdx_copy):
    """Codex on #401: a dynamic connector moved to point glue kept ShapeRouteStyle=0 and GlueType=2."""
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    dynamic = page.connect_shapes(source, target)
    point = page.connect_shapes(source, target, route="point")

    page.reanchor_connector(dynamic, to_shape=other, options=ConnectorOptions(glue=Glue.POINT))
    page.reanchor_connector(point, to_shape=other)

    for name in ("ShapeRouteStyle", "ConLineRouteExt", "ConFixedCode"):
        assert dynamic.cells[name].value == point.cells[name].value, name
    assert _own_cell(dynamic, "GlueType") is None
    assert _own_cell(dynamic, "ObjType") is None


def test_options_uncurve_a_curved_point_connector(vsdx_copy):
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target = page.shapes.by_id("90"), page.shapes.by_id("97")
    connector = page.connect_shapes(source, target, route="point|curved")

    page.reanchor_connector(connector, to_shape=target, route="point|straight")

    values = {name: connector.cells[name].value for name in ("ShapeRouteStyle", "ConLineRouteExt", "ConFixedCode")}
    assert values == {"ShapeRouteStyle": "16", "ConLineRouteExt": "1", "ConFixedCode": "6"}


def test_a_kept_floating_end_loses_its_old_glue(vsdx_copy):
    """Codex on #401: a floating begin kept `PAR(PNT(Sheet90!...))`, so Visio would glue it back to 90."""
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect_shapes(source, target, route="point", from_cp=1, to_cp=2)
    _drop_record(page, connector, "BeginX")
    begin = (connector.begin_x, connector.begin_y)

    page.reanchor_connector(connector, to_shape=other)

    assert connector.cells["BeginX"].formula is None
    assert connector.cells["BeginY"].formula is None
    assert _own_cell(connector, "BegTrigger") is None
    assert (connector.begin_x, connector.begin_y) == begin
    assert not any("Sheet90!" in (cell.formula or "") for cell in connector.cells.values())


def test_retarget_removes_the_begintrigger_earlier_releases_wrote(vsdx_copy):
    """Codex on #401: point glue before #106 wrote a `BeginTrigger` cell, which Visio does not have."""
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect_shapes(source, target, route="point")
    connector.get_or_create_cell("BeginTrigger", f="_XFTRIGGER(Sheet90!EventXFMod)")

    page.reanchor_connector(connector, to_shape=other)

    assert _own_cell(connector, "BeginTrigger") is None


def test_a_record_without_toparts_keeps_its_point_glue(vsdx_copy):
    """Codex on #401: `ToPart` is optional, and `ToCell` alone still names the point."""
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect_shapes(source, target, route="point", from_cp=1, to_cp=2)
    for record in page.connects:
        if record.from_id == connector.ID:
            del record.xml.attrib["ToPart"]

    page.reanchor_connector(connector, to_shape=other)

    assert _records(page, connector) == {"BeginX": ("90", "Connections.X2"), "EndX": ("102", "Connections.X3")}


def test_a_route_still_replaces_the_glue_of_both_ends(vsdx_copy):
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    source, target, other = (page.shapes.by_id(i) for i in ("90", "97", "102"))
    connector = page.connect_shapes(source, target)

    page.reanchor_connector(connector, to_shape=other, route="point", to_cp=4)

    assert _records(page, connector) == {"BeginX": ("90", "Connections.X1"), "EndX": ("102", "Connections.X5")}


def test_options_and_a_route_together_are_refused(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect_shapes(a, b)
    with pytest.raises(ValueError, match="route or options"):
        page.reanchor_connector(connector, to_shape=b, route="dynamic", options=ConnectorOptions())


def _refused(page, connector, **endpoints):
    before = _state(page, connector)
    with pytest.raises(InvalidOperationError) as excinfo:
        page.reanchor_connector(connector, **endpoints)
    assert _state(page, connector) == before
    return str(excinfo.value)


def test_retarget_with_no_endpoint_is_refused(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    connector = page.connect_shapes(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))
    assert "at least one endpoint" in _refused(page, connector)


def test_a_connector_cannot_be_its_own_endpoint(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    connector = page.connect_shapes(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))
    assert "itself" in _refused(page, connector, to_shape=connector)


def test_an_endpoint_on_another_page_is_refused(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    connector = page.connect_shapes(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))
    elsewhere = vis.create_shape(vis.add_page("Elsewhere"), "PALETTE_PROCESS", 1.0, 1.0, text="Elsewhere")
    assert "not on page" in _refused(page, connector, to_shape=elsewhere)


def test_a_connector_on_another_page_is_refused(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    other = vis.add_page("Elsewhere")
    start = vis.create_shape(other, "PALETTE_PROCESS", 1.0, 1.0, text="Start")
    finish = vis.create_shape(other, "PALETTE_PROCESS", 4.0, 1.0, text="Finish")
    connector = other.connect_shapes(start, finish)
    before = _state(other, connector)
    with pytest.raises(InvalidOperationError, match="not on page"):
        page.reanchor_connector(connector, to_shape=a)
    assert _state(other, connector) == before


def test_a_deleted_endpoint_is_refused(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    connector = page.connect_shapes(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))
    gone = vis.create_shape(page, "PALETTE_PROCESS", 7.0, 6.0, text="Gone")
    page.delete_shape(gone)
    assert "not on page" in _refused(page, connector, to_shape=gone)


def test_connecting_to_a_shape_on_another_page_is_refused(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    elsewhere = vis.create_shape(vis.add_page("Elsewhere"), "PALETTE_PROCESS", 1.0, 1.0, text="Elsewhere")
    shapes_before = len(page.shapes)
    with pytest.raises(InvalidOperationError, match="not on page"):
        page.connect_shapes(a, elsewhere)
    assert len(page.shapes) == shapes_before


def test_a_connector_visio_glued_to_points_keeps_them(vsdx_copy):
    """Visio glued connector 59 from point 3 of shape 54 to point 3 of shape 53; both inherit their points."""
    vis = VisioFile(vsdx_copy(S05))
    page = vis.pages[0]
    connector, start = page.shapes.by_id("59"), page.shapes.by_id("52")

    page.reanchor_connector(connector, to_shape=start)

    assert _records(page, connector) == {"BeginX": ("54", "Connections.X3"), "EndX": ("52", "Connections.X3")}


def test_connection_points_without_a_route_are_refused(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    page = vis.pages[0]
    a = page.shapes.by_text("Shape A")
    b = page.shapes.by_text("Shape B")
    connector = page.connect_shapes(a, b)
    with pytest.raises(ValueError, match="need a route"):
        page.reanchor_connector(connector, to_shape=b, to_cp=2)
