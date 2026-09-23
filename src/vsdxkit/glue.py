"""Connector glue as data: the options a connector is glued with, and what they write.

Nothing here reads or changes a document. `vsdxkit.connectors` resolves each
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
from enum import Enum
from xml.etree.ElementTree import Element

from vsdxkit.errors import InvalidOperationError

_CONNECT_TAG = "{http://schemas.microsoft.com/office/visio/2012/main}Connect"

_WALKGLUE_BEGIN = "_WALKGLUE(BegTrigger,EndTrigger,WalkPreference)"
_WALKGLUE_END = "_WALKGLUE(EndTrigger,BegTrigger,WalkPreference)"


class Glue(Enum):
    """How a connector's ends attach to the shapes they name."""

    DYNAMIC = "dynamic"
    """Shape glue: the end walks round the shape to the nearest side."""

    POINT = "point"
    """Glue to one row of the shape's ``Connection`` section."""


class Routing(Enum):
    """The path a connector takes between its ends."""

    STRAIGHT = "straight"
    RIGHT_ANGLE = "rightangle"
    CURVED = "curved"


_ROUTE_STYLE = {Routing.STRAIGHT: "16", Routing.RIGHT_ANGLE: "1", Routing.CURVED: "17"}


@dataclass(frozen=True)
class ConnectorOptions:
    """How a connector is glued and routed.

    ``from_point`` and ``to_point`` are 0-based rows of each shape's
    ``Connection`` section, and are read only when ``glue`` is
    :attr:`Glue.POINT`. ``routing`` of ``None`` is Visio's own: dynamic glue
    reroutes at right angles, and point glue keeps the connector straight.
    """

    glue: Glue = Glue.DYNAMIC
    routing: Routing | None = None
    from_point: int = 0
    to_point: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.glue, Glue):
            raise TypeError(f"glue must be a Glue, not {self.glue!r}")
        if self.routing is not None and not isinstance(self.routing, Routing):
            raise TypeError(f"routing must be a Routing or None, not {self.routing!r}")
        for point in (self.from_point, self.to_point):
            if type(point) is not int or point < 0:
                raise InvalidOperationError(f"a connection point is a 0-based row index, not {point!r}")

    @classmethod
    def from_route(cls, route: str, from_point: int = 0, to_point: int = 0) -> ConnectorOptions:
        """Read the ``route`` string the connector methods have always taken.

        ``route`` joins tokens with ``|``: ``dynamic`` or ``point`` for the
        glue, and at most one of ``straight``, ``rightangle`` and ``curved``.
        """
        parts: list[str] = route.split("|") if route else []
        unknown = set(parts) - {"dynamic", "point", *(routing.value for routing in Routing)}
        if unknown:
            raise ValueError(f"unknown connector route part(s): {', '.join(sorted(unknown))}")
        routings = [Routing(part) for part in parts if part not in ("dynamic", "point")]
        if len(routings) > 1:
            raise ValueError("connector route may specify only one routing behaviour")
        return cls(
            glue=Glue.POINT if "point" in parts else Glue.DYNAMIC,
            routing=routings[0] if routings else None,
            from_point=from_point,
            to_point=to_point,
        )

    def end_point(self, *, begin: bool) -> int | None:
        """The connection point one end glues to, or ``None`` for dynamic glue."""
        if self.glue is Glue.DYNAMIC:
            return None
        return self.from_point if begin else self.to_point


@dataclass(frozen=True)
class EndGlue:
    """One glued end: the shape it names, and its connection point or ``None`` for dynamic glue."""

    shape_id: str
    point: int | None


@dataclass(frozen=True)
class CellWrite:
    """A cell to set on the connector. ``None`` leaves that half of the cell as it is."""

    name: str
    formula: str | None = None
    value: str | None = None


@dataclass(frozen=True)
class ConnectionRecord:
    """The attributes of one ``<Connect>`` element."""

    from_sheet: str
    from_cell: str
    from_part: str
    to_sheet: str
    to_cell: str
    to_part: str


def _coordinate_formula(end: EndGlue, *, begin: bool) -> str:
    if end.point is None:
        return _WALKGLUE_BEGIN if begin else _WALKGLUE_END
    row = end.point + 1
    return f"PAR(PNT(Sheet{end.shape_id}!Connections.X{row},Sheet{end.shape_id}!Connections.Y{row}))"


def glue_cells(begin: EndGlue | None, end: EndGlue | None) -> tuple[CellWrite, ...]:
    """The cells gluing the connector's ends, in the order Visio writes them. ``None`` is a floating end."""
    ends = [(prefix, glued, is_begin) for prefix, glued, is_begin in (("Begin", begin, True), ("End", end, False)) if glued]
    triggers = [
        CellWrite("BegTrigger" if is_begin else "EndTrigger", formula=f"_XFTRIGGER(Sheet{glued.shape_id}!EventXFMod)")
        for _prefix, glued, is_begin in ends
    ]
    coordinates = [
        CellWrite(f"{prefix}{axis}", formula=_coordinate_formula(glued, begin=is_begin))
        for prefix, glued, is_begin in ends
        for axis in ("X", "Y")
    ]
    connector = [CellWrite("GlueType", value="2"), CellWrite("ObjType", value="2")] if _any_dynamic(begin, end) else []
    return (*triggers, *coordinates, *connector)


def _any_dynamic(begin: EndGlue | None, end: EndGlue | None) -> bool:
    return any(glued is not None and glued.point is None for glued in (begin, end))


def routing_cells(routing: Routing | None, *, dynamic: bool) -> tuple[CellWrite, ...]:
    """The cells setting a connector's routing.

    Dynamic glue sets Visio's defaults first; point glue leaves the straight
    connector it was copied from as it is.
    """
    cells = {"ShapeRouteStyle": "0", "ConLineRouteExt": "0", "ConFixedCode": "6"} if dynamic else {}
    if routing is not None:
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
