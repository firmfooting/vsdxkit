"""Connector glue as engine actions: what to glue, on a page, and where.

`vsdxkit._glue` turns a glued end into cells and records; this module decides
what a connector's ends should be glued to. `_plan_connector`,
`_retarget_connector` and `_float_ends` are the entry points
`vsdxkit.pages.Page` and `vsdxkit.shapes.Connector` call, and the Protocols
above them (`_ConnectorPage`, `_EndShape`, `_ConnectorShape`) let the engine
name only what it reads and writes on a page or a shape, without importing
either module.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol, TypeAlias
from xml.etree.ElementTree import Element

from vsdxkit import namespace
from vsdxkit._glue import (
    CellChange,
    CellFreeze,
    CellInherit,
    CellWrite,
    EndGlue,
    connection_records,
    glue_cells,
    record_element,
    routing_cells,
)
from vsdxkit.errors import InvalidOperationError, MalformedPackageError
from vsdxkit.glue import ConnectorOptions, Glue


class _CellXml(Protocol):
    """A cell the engine edits in place: it drops the cell's formula, or the cell itself."""

    @property
    def xml(self) -> Element:
        """The cell's own ``<Cell>`` element, for `_change_cell` to edit or remove."""
        ...


class _ShapeLookup(Protocol):
    """The page's shapes, which the engine looks up by the ids its records name."""

    def by_id(self, shape_id: str) -> _EndShape | None:
        """The shape with this page-scoped ID, or None."""
        ...


class _ConnectorPage(Protocol):
    """What the engine needs from the page a connector is on.

    The page holds the ``Connect`` records and the shapes they name, and it
    sits above this module, so the engine names only what it reads and writes.
    """

    @property
    def name(self) -> str:
        """The page's name, for an error naming where an endpoint check failed."""
        ...

    @property
    def shapes(self) -> _ShapeLookup:
        """Every shape on the page, for the engine to look one up by ID."""
        ...

    def _connects(self) -> list[_Connect]:
        """Every ``<Connect>`` record on the page, in document order."""
        ...

    def _add_connect(self, element: Element) -> None:
        """Append a ``Connect`` record to the page."""
        ...

    def _remove_connect_records(self, connector_ids: Iterable[str | int]) -> None:
        """Remove Connect records leading from any of these connectors."""
        ...


class _EndShape(Protocol):
    """What the engine needs from a shape an end is glued to: its id, its connection points and its centre."""

    @property
    def ID(self) -> str | None:
        """This shape's page-scoped ID, as its element declares it."""
        ...

    @property
    def xml(self) -> Element:
        """The shape's own ``<Shape>`` element, which this object is a view onto."""
        ...

    @property
    def master_shape(self) -> _EndShape | None:
        """The shape on this shape's master that it instances, or None."""
        ...

    @property
    def center_x_y(self) -> tuple[float | None, float | None]:
        """A centre for the shape as ``(x, y)``, for the endpoints written while Visio has not yet recalculated."""
        ...


class _ConnectorShape(_EndShape, Protocol):
    """What the engine needs from a connector: its page, its end cells, and a way to write them."""

    @property
    def _page(self) -> _ConnectorPage:
        """The page this connector is on, for the engine to check endpoints and write records through."""
        ...

    @property
    def begin_x(self) -> float | None:
        """The x of the connector's begin point, for the fallback endpoint written when no shape is glued there."""
        ...

    @property
    def begin_y(self) -> float | None:
        """The y of the connector's begin point. Behaves as `begin_x` does."""
        ...

    @property
    def end_x(self) -> float | None:
        """The x of the connector's end point. Behaves as `begin_x` does."""
        ...

    @property
    def end_y(self) -> float | None:
        """The y of the connector's end point. Behaves as `begin_x` does."""
        ...

    def set_start_and_finish(
        self, start: tuple[float | None, float | None], finish: tuple[float | None, float | None]
    ) -> None:
        """Move the connector's endpoints to `start` and `finish`, so the file renders sensibly before Visio recalculates."""
        ...

    def get_or_create_cell(self, name: str, v: str | None = None, f: str | None = None) -> object:
        """Set or create the named cell, for the engine to write a glue cell without knowing it already exists."""
        ...

    def _cell(self, name: str) -> _CellXml | None:
        """This connector's own cell `name`, or ``None``, for the engine to drop a formula or remove a cell in place."""
        ...

    def _require_attached(self, operation: str) -> None:
        """Refuse `operation`, naming it, once the connector is detached."""
        ...


# One end of a connector as the engine plans it: the shape it glues to and
# its connection point, `None` for dynamic glue. A floating end is `None`.
_Glued: TypeAlias = tuple[_EndShape, int | None]
"""One glued end as the engine plans it: the shape and its connection point, or `None` for dynamic glue."""
_End: TypeAlias = _Glued | None
"""An end of a connector as the engine plans it: `_Glued`, or `None` for a floating end."""

# a Connect record's ToPart for connection point row n is 100 + n, and its ToCell Connections.X{n + 1}
_FIRST_CONNECTION_POINT_PART = 100
"""The `ToPart` a Connect record gives connection point row 0; row n's `ToPart` is this plus n."""
_CONNECTION_CELL = re.compile(r"Connections\.X(\d+)")
"""Matches a Connect record's `ToCell` naming a connection point row, such as `Connections.X3`."""


def _connection_rows(shape: _EndShape) -> frozenset[int]:
    """The rows of the shape's ``Connection`` section, its master's included.

    An instance inherits every row its master has and overrides or deletes
    them by ``IX``, so a flowchart shape that holds no section of its own
    still has its master's four points.
    """
    master = shape.master_shape
    rows: set[int] = set()
    for element in (master.xml if master is not None else None, shape.xml):
        if element is None:
            continue
        section = element.find(f"{namespace}Section[@N='Connection']")
        if section is None:
            continue
        if section.attrib.get("Del") == "1":
            rows.clear()
            continue
        for position, row in enumerate(section.findall(f"{namespace}Row")):
            index = int(row.attrib.get("IX", position))
            if row.attrib.get("Del") == "1":
                rows.discard(index)
            else:
                rows.add(index)
    return frozenset(rows)


def _id(shape: _EndShape) -> str:
    """The shape's id, which glue cannot name a shape without."""
    shape_id = shape.ID
    if shape_id is None:
        raise MalformedPackageError("a Shape element has no ID attribute, so nothing can be glued to it")
    return shape_id


def _check_endpoint(page: _ConnectorPage, shape: _EndShape, connector: _ConnectorShape | None) -> None:
    """Refuse gluing `connector` to itself, or to a shape not on `page`."""
    if connector is not None and shape == connector:
        raise InvalidOperationError(f"connector shape ID {connector.ID} cannot be glued to itself")
    if page.shapes.by_id(_id(shape)) != shape:
        raise InvalidOperationError(f"shape ID {shape.ID} is not on page {page.name!r}")


def _check_point(end: _End) -> None:
    """Refuse gluing to a connection point index the glued shape does not have."""
    if end is None or end[1] is None:
        return
    shape, point = end
    rows = _connection_rows(shape)
    if point not in rows:
        raise InvalidOperationError(
            f"Shape ID {shape.ID} has {len(rows)} connection point(s); cannot glue to connection point index {point}"
        )


def _record_point(connect: _Connect) -> int | None:
    """The connection point a record glues to, or ``None`` for dynamic glue.

    ``ToPart`` is 100 plus the point's row. It is optional, and without it
    ``ToCell`` still names the row, as ``Connections.X3``.
    """
    part = connect.xml.attrib.get("ToPart", "")
    if part.isdigit():
        return int(part) - _FIRST_CONNECTION_POINT_PART if int(part) >= _FIRST_CONNECTION_POINT_PART else None
    named = _CONNECTION_CELL.fullmatch(connect.to_rel or "")
    return int(named.group(1)) - 1 if named else None


def _end_glue(end: _End) -> EndGlue | None:
    """`end` as the data `vsdxkit._glue` works from, or ``None`` for a floating end."""
    return None if end is None else EndGlue(_id(end[0]), end[1])


class _Connect:
    """A read view over one ``<Connect>`` element of a page: which end of which connector is glued to what.

    Internal: the public graph is :class:`vsdxkit.shapes.Connector` and its
    queries. Every attribute is read from the element on each access, because
    renumbering a shape rewrites these very attributes, and a copy made before
    it would keep naming the vacated ID (#320).
    """

    def __init__(self, xml: Element) -> None:
        """Wrap `xml`, one page's ``<Connect>`` element.

        :raises MalformedPackageError: if `xml` lacks ``FromSheet`` or ``ToSheet``
        """
        # the attributes come from the package, so a record without them is a
        # malformed package rather than a bad argument
        missing = [name for name in ("FromSheet", "ToSheet") if name not in xml.attrib]
        if missing:
            raise MalformedPackageError(f"Connect element is missing required attribute(s): {', '.join(missing)}")
        self.xml = xml

    def __repr__(self) -> str:
        """Shows which shape is glued from which of which connector's ends to what."""
        return f"<Connect from={self.from_id} {self.from_rel} to={self.to_id} {self.to_rel}>"

    @property
    def from_id(self) -> str:
        """The connector shape this record leads from."""
        return self.xml.attrib["FromSheet"]

    @property
    def to_id(self) -> str:
        """The shape this record's connector is glued to."""
        return self.xml.attrib["ToSheet"]

    @property
    def from_rel(self) -> str | None:
        """Which end of the connector is glued: ``BeginX``, ``EndX``, or absent."""
        return self.xml.attrib.get("FromCell")

    @property
    def to_rel(self) -> str | None:
        """What the connector is glued to: ``PinX``, a ``Connections.Xn`` row, or absent."""
        return self.xml.attrib.get("ToCell")


def _plan_connector(
    page: _ConnectorPage, source: _EndShape, target: _EndShape, options: ConnectorOptions
) -> tuple[_Glued, _Glued]:
    """The two ends of a new connector on `page`, glued from `source` to `target` as `options` say.

    Everything is checked before anything is written: both shapes are on
    `page`, and each connection point exists.
    """
    begin = (source, options.end_point(begin=True))
    end = (target, options.end_point(begin=False))
    for shape in (source, target):
        _check_endpoint(page, shape, None)
    for glued in (begin, end):
        _check_point(glued)
    return begin, end


def _glue_connector(connector: _ConnectorShape, begin: _End, end: _End, options: ConnectorOptions | None) -> None:
    """Glue the connector's ends as planned, by :func:`_plan_connector` or :func:`_retarget_connector`.

    Without `options`, no routing cell is written. An end planned as `None`
    stays where it is.
    """
    routing = () if options is None else routing_cells(options.routing, dynamic=options.glue is Glue.DYNAMIC)
    _write(connector, begin, end, routing)
    # endpoints so the file renders sensibly even before Visio recalculates
    start = begin[0].center_x_y if begin else (connector.begin_x, connector.begin_y)
    finish = end[0].center_x_y if end else (connector.end_x, connector.end_y)
    connector.set_start_and_finish(start, finish)


def _retarget_connector(
    connector: _ConnectorShape, source: _EndShape | None, target: _EndShape | None, options: ConnectorOptions | None
) -> None:
    """Glue one or both ends of `connector` to other shapes; see :meth:`vsdxkit.shapes.Connector.retarget`."""
    if source is None and target is None:
        raise InvalidOperationError("retargeting a connector needs at least one endpoint")
    page = connector._page
    _check_endpoint(page, connector, None)
    for shape in (source, target):
        if shape is not None:
            _check_endpoint(page, shape, connector)
    current_begin, current_end = _glued_ends(connector)
    begin = _next_end(current_begin, source, options, begin=True)
    end = _next_end(current_end, target, options, begin=False)
    for glued in (begin, end):
        _check_point(glued)
    _glue_connector(connector, begin, end, options)


def _glued_ends(connector: _ConnectorShape) -> tuple[_End, _End]:
    """Each end as the connector's records have it glued; `None` for an end no record names a shape on the page for."""
    page = connector._page
    ends: dict[str, tuple[_EndShape, int | None]] = {}
    for connect in page._connects():
        if connect.from_id != connector.ID or connect.from_rel not in ("BeginX", "EndX"):
            continue
        shape = page.shapes.by_id(connect.to_id)
        if shape is None:
            continue
        ends[connect.from_rel] = (shape, _record_point(connect))
    return ends.get("BeginX"), ends.get("EndX")


def _next_end(current: _End, replacement: _EndShape | None, options: ConnectorOptions | None, *, begin: bool) -> _End:
    """Where one end goes: the shape named, or the one it has, glued as `options` say or as it was."""
    shape = replacement if replacement is not None else (current[0] if current else None)
    if shape is None:
        return None
    if options is not None:
        return shape, options.end_point(begin=begin)
    return shape, current[1] if current else None


def _write(connector: _ConnectorShape, begin: _End, end: _End, routing: tuple[CellWrite, ...]) -> None:
    """Glue the connector's ends as planned: its cells, then its records in place of the ones it had."""
    connector_id = _id(connector)
    begin_glue, end_glue = _end_glue(begin), _end_glue(end)
    for change in (*glue_cells(begin_glue, end_glue), *routing):
        _change_cell(connector, change)
    page = connector._page
    page._remove_connect_records({connector_id})
    for record in connection_records(connector_id, begin_glue, end_glue):
        page._add_connect(record_element(record))


def _change_cell(connector: _ConnectorShape, change: CellChange) -> None:
    """Apply one `CellChange`: write a cell, drop its formula, or drop the cell so it inherits the master's again."""
    if isinstance(change, CellWrite):
        connector.get_or_create_cell(change.name, v=change.value, f=change.formula)
        return
    # the two below edit the element: a Cell cannot drop a formula, and
    # nothing removes one of a shape's cells
    connector._require_attached(f"writing shape cell {change.name!r}")
    cell = connector._cell(change.name)
    if cell is None:
        return
    if isinstance(change, CellFreeze):
        cell.xml.attrib.pop("F", None)
    elif isinstance(change, CellInherit):
        connector.xml.remove(cell.xml)


# what kind of connector a shape is, which floating its ends does not change:
# a masterless connector has no master to take them back from
_CONNECTOR_KIND_CELLS = frozenset({"GlueType", "ObjType"})
"""The cells `_float_ends` leaves alone: a connector's kind, not part of what glue it has."""


def _float_ends(connector: _ConnectorShape) -> None:
    """Leave both of a 1-D shape's ends unglued: the cells a floating end has, and no records.

    A copy of a glued connector keeps glue formulas naming the shapes the
    original is glued to, but none of its records, and Visio would pull it
    back to them.
    """
    for change in glue_cells(None, None):
        if change.name not in _CONNECTOR_KIND_CELLS:
            _change_cell(connector, change)
    connector._page._remove_connect_records({_id(connector)})
