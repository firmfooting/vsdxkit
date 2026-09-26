"""Connector glue as data: the cells and records each of a connector's options writes.

Nothing here reads or changes a document. `vsdxkit._connectors` resolves each
end of a connector to an `EndGlue`, asks this module for the cells and records
that glue means, and writes them. Keeping the formulas out of the writer is
what lets create and retarget share them, and lets them be checked against
what Visio writes without a document to hand.

The formulas are Visio's own, from `tests/fixtures/com_reference`:
`_WALKGLUE`/`_XFTRIGGER` with `GlueType=2` for dynamic glue (s01, s02),
`PAR(PNT(...))` for point glue (s07) and the `ShapeRouteStyle` codes (s03).
The sheet references are written `SheetN!`; Visio writes `Sheet.N!` (#400).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias
from xml.etree.ElementTree import Element

from vsdxkit.glue import Routing

_CONNECT_TAG = "{http://schemas.microsoft.com/office/visio/2012/main}Connect"
"""The Visio namespace's ``Connect`` tag, for building a `<Connect>` element."""

_WALKGLUE_BEGIN = "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
"""The formula Visio writes on the ``BeginX``/``BeginY`` cells of a dynamically glued begin end."""
_WALKGLUE_END = "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"
"""The formula Visio writes on the ``EndX``/``EndY`` cells of a dynamically glued end end."""


_ROUTE_STYLE = {Routing.STRAIGHT: "16", Routing.RIGHT_ANGLE: "1", Routing.CURVED: "17"}
"""The `ShapeRouteStyle` code for each `Routing`, other than `Routing.DEFAULT`, which changes nothing."""


@dataclass(frozen=True)
class EndGlue:
    """One glued end: the shape it names, and its connection point or ``None`` for dynamic glue."""

    shape_id: str
    """The glued-to shape's page-scoped ID."""
    point: int | None
    """The connection point index the end is glued to, or ``None`` for dynamic glue."""


@dataclass(frozen=True)
class CellWrite:
    """A cell to set on the connector. ``None`` leaves that half of the cell as it is."""

    name: str
    """The cell's name, such as ``BeginX`` or ``GlueType``."""
    formula: str | None = None
    """The formula to write, or ``None`` to leave the cell's formula as it is."""
    value: str | None = None
    """The value to write, or ``None`` to leave the cell's value as it is."""


@dataclass(frozen=True)
class CellFreeze:
    """A cell whose formula goes and whose value stays, as a floating end's coordinates do."""

    name: str
    """The cell's name, one of ``BeginX``, ``BeginY``, ``EndX`` and ``EndY``."""


@dataclass(frozen=True)
class CellInherit:
    """A cell of the connector's own to remove, so that it takes its master's again."""

    name: str
    """The cell's name, such as ``BegTrigger`` on a floating end or ``GlueType`` without dynamic glue."""


CellChange: TypeAlias = CellWrite | CellFreeze | CellInherit
"""One change `_change_cell` applies to a connector's cell: write it, freeze it, or drop it to inherit."""


@dataclass(frozen=True)
class ConnectionRecord:
    """The attributes of one ``<Connect>`` element."""

    from_sheet: str
    """The connector's own shape ID: ``FromSheet``."""
    from_cell: str
    """Which of the connector's ends this record is: ``BeginX`` or ``EndX``, its ``FromCell``."""
    from_part: str
    """`from_cell`'s numeric code, Visio's own spelling of it: ``9`` for ``BeginX``, ``12`` for ``EndX``."""
    to_sheet: str
    """The glued-to shape's ID: ``ToSheet``."""
    to_cell: str
    """What is glued to: ``PinX`` for dynamic glue, or a ``Connections.Xn`` row: the record's ``ToCell``."""
    to_part: str
    """`to_cell`'s numeric code: ``3`` for ``PinX``, or ``100 + n`` for connection point row ``n``."""


def _coordinate_formula(end: EndGlue, *, begin: bool) -> str:
    """The formula for one coordinate cell (X or Y) of `end`, `begin` saying which end of the connector it is."""
    if end.point is None:
        return _WALKGLUE_BEGIN if begin else _WALKGLUE_END
    row = end.point + 1
    return f"PAR(PNT(Sheet{end.shape_id}!Connections.X{row},Sheet{end.shape_id}!Connections.Y{row}))"


def _trigger(glued: EndGlue | None, name: str) -> CellChange:
    """The change to `name` (``BegTrigger`` or ``EndTrigger``): inherit it floating, or fire on the glued shape's changes."""
    if glued is None:
        return CellInherit(name)
    return CellWrite(name, formula=f"_XFTRIGGER(Sheet{glued.shape_id}!EventXFMod)")


def _coordinate(glued: EndGlue | None, name: str, *, begin: bool) -> CellChange:
    """The change to coordinate cell `name`: freeze it floating, or write the formula that tracks the glued shape."""
    if glued is None:
        return CellFreeze(name)
    return CellWrite(name, formula=_coordinate_formula(glued, begin=begin))


def glue_cells(begin: EndGlue | None, end: EndGlue | None) -> tuple[CellChange, ...]:
    """Every cell that says how the connector's ends are glued, in the order Visio writes them.

    ``None`` is a floating end: its trigger goes and its coordinates keep their
    values without the formulas that tied them to a shape. The cells are the
    whole state, not a delta, so writing them over a connector glued some
    other way leaves nothing of the old glue behind.
    """
    triggers = (_trigger(begin, "BegTrigger"), _trigger(end, "EndTrigger"))
    coordinates = [
        _coordinate(glued, f"{prefix}{axis}", begin=is_begin)
        for prefix, glued, is_begin in (("Begin", begin, True), ("End", end, False))
        for axis in ("X", "Y")
    ]
    if _any_dynamic(begin, end):
        connector: tuple[CellChange, ...] = (CellWrite("GlueType", value="2"), CellWrite("ObjType", value="2"))
    else:
        connector = (CellInherit("GlueType"), CellInherit("ObjType"))
    # point glue before 1.0 wrote its begin trigger here; Visio has no such cell
    return (*triggers, *coordinates, *connector, CellInherit("BeginTrigger"))


def _any_dynamic(begin: EndGlue | None, end: EndGlue | None) -> bool:
    """Whether either end is glued dynamically, which makes the whole connector a dynamic one."""
    return any(glued is not None and glued.point is None for glued in (begin, end))


def routing_cells(routing: Routing, *, dynamic: bool) -> tuple[CellWrite, ...]:
    """Every cell that sets a connector's routing, so the routing replaces whatever the connector had.

    With :attr:`Routing.DEFAULT`, dynamic glue takes Visio's defaults (s01)
    and point glue the straight connector's (the bundled donor's own cells).
    """
    if dynamic:
        cells = {"ShapeRouteStyle": "0", "ConLineRouteExt": "0", "ConFixedCode": "6"}
    else:
        cells = {"ShapeRouteStyle": "16", "ConLineRouteExt": "1", "ConFixedCode": "6"}
    if routing is not Routing.DEFAULT:
        cells["ShapeRouteStyle"] = _ROUTE_STYLE[routing]
    if routing is Routing.CURVED:
        # Visio sets ConFixedCode itself when a connector is made curved (s03)
        cells["ConLineRouteExt"] = "2"
        cells["ConFixedCode"] = "0"
    return tuple(CellWrite(name, value=value) for name, value in cells.items())


def connection_records(connector_id: str, begin: EndGlue | None, end: EndGlue | None) -> tuple[ConnectionRecord, ...]:
    """The ``<Connect>`` records for each glued end: the end's first, as Visio writes them."""
    records = []
    for from_cell, from_part, glued in (("EndX", "12", end), ("BeginX", "9", begin)):
        if glued is None:
            continue
        if glued.point is None:
            to_cell, to_part = "PinX", "3"
        else:
            to_cell, to_part = f"Connections.X{glued.point + 1}", str(100 + glued.point)
        records.append(ConnectionRecord(connector_id, from_cell, from_part, glued.shape_id, to_cell, to_part))
    return tuple(records)


def record_element(record: ConnectionRecord) -> Element:
    """A ``<Connect>`` element holding the record."""
    return Element(
        _CONNECT_TAG,
        {
            "FromSheet": record.from_sheet,
            "FromCell": record.from_cell,
            "FromPart": record.from_part,
            "ToSheet": record.to_sheet,
            "ToCell": record.to_cell,
            "ToPart": record.to_part,
        },
    )
