"""`vsdxkit.glue` builds connector glue as data, with no document to hand.

The formulas pinned here are the ones Visio writes, from
`tests/fixtures/com_reference`: `_WALKGLUE`/`_XFTRIGGER`/`GlueType=2` from s01
and s02, the routing codes from s03, and point glue from s07.
"""

import pytest

from vsdxkit.errors import InvalidOperationError
from vsdxkit.glue import (
    CellFreeze,
    CellInherit,
    CellWrite,
    ConnectionRecord,
    ConnectorOptions,
    EndGlue,
    Glue,
    Routing,
    connection_records,
    glue_cells,
    record_element,
    routing_cells,
)

WALKGLUE_BEGIN = "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
WALKGLUE_END = "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"


@pytest.mark.parametrize(
    ("route", "glue", "routing"),
    [
        ("", Glue.DYNAMIC, Routing.DEFAULT),
        ("dynamic", Glue.DYNAMIC, Routing.DEFAULT),
        ("point", Glue.POINT, Routing.DEFAULT),
        ("straight", Glue.DYNAMIC, Routing.STRAIGHT),
        ("rightangle", Glue.DYNAMIC, Routing.RIGHT_ANGLE),
        ("curved", Glue.DYNAMIC, Routing.CURVED),
        ("point|curved", Glue.POINT, Routing.CURVED),
        ("dynamic|straight", Glue.DYNAMIC, Routing.STRAIGHT),
    ],
)
def test_from_route_reads_every_legacy_token(route, glue, routing):
    options = ConnectorOptions.from_route(route)
    assert (options.glue, options.routing) == (glue, routing)


def test_from_route_carries_the_point_indexes():
    options = ConnectorOptions.from_route("point", from_point=1, to_point=2)
    assert (options.from_point, options.to_point) == (1, 2)


def test_from_route_refuses_an_unknown_token():
    with pytest.raises(ValueError, match="unknown connector route part"):
        ConnectorOptions.from_route("diagonal")


def test_from_route_refuses_two_routings():
    with pytest.raises(ValueError, match="only one routing"):
        ConnectorOptions.from_route("straight|curved")


@pytest.mark.parametrize("point", [-1, 1.0, "0", True])
def test_options_refuse_a_point_that_is_not_a_row_index(point):
    with pytest.raises(InvalidOperationError, match="connection point"):
        ConnectorOptions(glue=Glue.POINT, from_point=point)


def test_options_refuse_a_glue_that_is_not_a_glue():
    with pytest.raises(TypeError, match="Glue"):
        ConnectorOptions(glue="point")  # type: ignore[arg-type]


@pytest.mark.parametrize("routing", ["curved", None])
def test_options_refuse_a_routing_that_is_not_a_routing(routing):
    """A route string, or the 0.x `None` for Visio's routing, is refused naming the members to use."""
    with pytest.raises(TypeError, match=r"Routing\.DEFAULT, Routing\.STRAIGHT, Routing\.RIGHT_ANGLE, Routing\.CURVED"):
        ConnectorOptions(routing=routing)  # type: ignore[arg-type]


def test_options_default_to_visio_routing():
    assert ConnectorOptions().routing is Routing.DEFAULT


def test_options_are_frozen():
    options = ConnectorOptions()
    with pytest.raises(AttributeError):
        options.glue = Glue.POINT  # type: ignore[misc]


def test_options_name_the_glue_each_end_gets():
    assert ConnectorOptions().end_point(begin=True) is None
    point = ConnectorOptions(glue=Glue.POINT, from_point=1, to_point=2)
    assert point.end_point(begin=True) == 1
    assert point.end_point(begin=False) == 2


def test_dynamic_glue_at_both_ends_is_what_visio_writes():
    cells = glue_cells(EndGlue("5", None), EndGlue("6", None))
    assert cells == (
        CellWrite("BegTrigger", formula="_XFTRIGGER(Sheet5!EventXFMod)"),
        CellWrite("EndTrigger", formula="_XFTRIGGER(Sheet6!EventXFMod)"),
        CellWrite("BeginX", formula=WALKGLUE_BEGIN),
        CellWrite("BeginY", formula=WALKGLUE_BEGIN),
        CellWrite("EndX", formula=WALKGLUE_END),
        CellWrite("EndY", formula=WALKGLUE_END),
        CellWrite("GlueType", value="2"),
        CellWrite("ObjType", value="2"),
        CellInherit("BeginTrigger"),
    )


def test_point_glue_at_both_ends_writes_the_begin_trigger_to_begtrigger():
    cells = glue_cells(EndGlue("5", 0), EndGlue("6", 2))
    begin_point = "PAR(PNT(Sheet5!Connections.X1,Sheet5!Connections.Y1))"
    end_point = "PAR(PNT(Sheet6!Connections.X3,Sheet6!Connections.Y3))"
    assert cells == (
        CellWrite("BegTrigger", formula="_XFTRIGGER(Sheet5!EventXFMod)"),
        CellWrite("EndTrigger", formula="_XFTRIGGER(Sheet6!EventXFMod)"),
        CellWrite("BeginX", formula=begin_point),
        CellWrite("BeginY", formula=begin_point),
        CellWrite("EndX", formula=end_point),
        CellWrite("EndY", formula=end_point),
        CellInherit("GlueType"),
        CellInherit("ObjType"),
        CellInherit("BeginTrigger"),
    )


def test_mixed_glue_writes_each_end_its_own_way():
    cells = {cell.name: cell for cell in glue_cells(EndGlue("5", 0), EndGlue("6", None))}
    assert cells["BeginX"].formula == "PAR(PNT(Sheet5!Connections.X1,Sheet5!Connections.Y1))"
    assert cells["EndX"].formula == WALKGLUE_END
    assert cells["GlueType"].value == "2"


def test_a_floating_end_stays_where_it_is():
    """Its glue formulas go, its coordinates stay: nothing recalculates it back onto a shape."""
    cells = glue_cells(None, EndGlue("6", None))
    assert cells[0] == CellInherit("BegTrigger")
    assert CellFreeze("BeginX") in cells
    assert CellFreeze("BeginY") in cells
    assert CellWrite("EndTrigger", formula="_XFTRIGGER(Sheet6!EventXFMod)") in cells


def test_dynamic_routing_starts_from_visio_defaults():
    assert routing_cells(Routing.DEFAULT, dynamic=True) == (
        CellWrite("ShapeRouteStyle", value="0"),
        CellWrite("ConLineRouteExt", value="0"),
        CellWrite("ConFixedCode", value="6"),
    )


def test_point_routing_is_the_straight_connector():
    """Every routing cell is written, so options replace what a connector had rather than add to it."""
    assert routing_cells(Routing.DEFAULT, dynamic=False) == (
        CellWrite("ShapeRouteStyle", value="16"),
        CellWrite("ConLineRouteExt", value="1"),
        CellWrite("ConFixedCode", value="6"),
    )


@pytest.mark.parametrize(
    ("routing", "style", "extension", "fixed"),
    [(Routing.STRAIGHT, "16", "0", "6"), (Routing.RIGHT_ANGLE, "1", "0", "6"), (Routing.CURVED, "17", "2", "0")],
)
def test_routing_sets_the_s03_codes(routing, style, extension, fixed):
    """Visio itself set `ConFixedCode=0` when s03's generator made a connector curved."""
    cells = {cell.name: cell.value for cell in routing_cells(routing, dynamic=True)}
    assert cells == {"ShapeRouteStyle": style, "ConLineRouteExt": extension, "ConFixedCode": fixed}


def test_curved_point_routing_sets_what_curving_sets():
    cells = {cell.name: cell.value for cell in routing_cells(Routing.CURVED, dynamic=False)}
    assert cells == {"ShapeRouteStyle": "17", "ConLineRouteExt": "2", "ConFixedCode": "0"}


@pytest.mark.parametrize(("routing", "style"), [(Routing.STRAIGHT, "16"), (Routing.RIGHT_ANGLE, "1")])
def test_uncurved_point_routing_undoes_a_curve(routing, style):
    cells = {cell.name: cell.value for cell in routing_cells(routing, dynamic=False)}
    assert cells == {"ShapeRouteStyle": style, "ConLineRouteExt": "1", "ConFixedCode": "6"}


def test_records_are_the_end_then_the_begin():
    records = connection_records("9", EndGlue("5", None), EndGlue("6", 1))
    assert records == (
        ConnectionRecord("9", "EndX", "12", "6", "Connections.X2", "101"),
        ConnectionRecord("9", "BeginX", "9", "5", "PinX", "3"),
    )


def test_a_floating_end_gets_no_record():
    assert connection_records("9", None, EndGlue("6", None)) == (ConnectionRecord("9", "EndX", "12", "6", "PinX", "3"),)


def test_a_record_becomes_a_connect_element():
    element = record_element(ConnectionRecord("9", "BeginX", "9", "5", "PinX", "3"))
    assert element.tag == "{http://schemas.microsoft.com/office/visio/2012/main}Connect"
    assert list(element.attrib.items()) == [
        ("FromSheet", "9"),
        ("FromCell", "BeginX"),
        ("FromPart", "9"),
        ("ToSheet", "5"),
        ("ToCell", "PinX"),
        ("ToPart", "3"),
    ]
