from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol, TypeAlias
from xml.etree.ElementTree import Element

from vsdxkit.errors import InvalidOperationError, MalformedPackageError
from vsdxkit.glue import (
    CellChange,
    CellFreeze,
    CellInherit,
    CellWrite,
    ConnectorOptions,
    EndGlue,
    Glue,
    connection_records,
    glue_cells,
    record_element,
    routing_cells,
)


class _CellXml(Protocol):
    """A cell the engine edits in place: it drops the cell's formula, or the cell itself."""

    @property
    def xml(self) -> Element: ...


class _ShapeLookup(Protocol):
    """The page's shapes, which the engine looks up by the ids its records name."""

    def by_id(self, shape_id: str) -> _EndShape | None: ...


class _ConnectorPage(Protocol):
    """What the engine needs from the page a connector is on.

    The page holds the ``Connect`` records and the shapes they name, and it
    sits above this module, so the engine names only what it reads and writes.
    """

    @property
    def name(self) -> str: ...

    @property
    def shapes(self) -> _ShapeLookup: ...

    def _connects(self) -> list[_Connect]: ...

    def _add_connect(self, element: Element) -> None: ...

    def _remove_connect_records(self, connector_ids: Iterable[str | int]) -> None: ...


class _EndShape(Protocol):
    """What the engine needs from a shape an end is glued to: its id, its connection points and its centre."""

    @property
    def ID(self) -> str | None: ...

    @property
    def xml(self) -> Element: ...

    @property
    def master_shape(self) -> _EndShape | None: ...

    @property
    def center_x_y(self) -> tuple[float | None, float | None]: ...


class _ConnectorShape(_EndShape, Protocol):
    """What the engine needs from a connector: its page, its end cells, and a way to write them."""

    @property
    def _page(self) -> _ConnectorPage: ...

    @property
    def begin_x(self) -> float | None: ...

    @property
    def begin_y(self) -> float | None: ...

    @property
    def end_x(self) -> float | None: ...

    @property
    def end_y(self) -> float | None: ...

    def set_start_and_finish(
        self, start: tuple[float | None, float | None], finish: tuple[float | None, float | None]
    ) -> None: ...

    def get_or_create_cell(self, name: str, v: str | None = None, f: str | None = None) -> object: ...

    def _cell(self, name: str) -> _CellXml | None: ...

    def _require_attached(self, operation: str) -> None: ...


# One end of a connector as the engine plans it: the shape it glues to and
# its connection point, `None` for dynamic glue. A floating end is `None`.
_Glued: TypeAlias = tuple[_EndShape, int | None]
_End: TypeAlias = _Glued | None

namespace = "{http://schemas.microsoft.com/office/visio/2012/main}"

# a Connect record's ToPart for connection point row n is 100 + n, and its ToCell Connections.X{n + 1}
_FIRST_CONNECTION_POINT_PART = 100
_CONNECTION_CELL = re.compile(r"Connections\.X(\d+)")


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
    if connector is not None and shape == connector:
        raise InvalidOperationError(f"connector shape ID {connector.ID} cannot be glued to itself")
    if page.shapes.by_id(_id(shape)) != shape:
        raise InvalidOperationError(f"shape ID {shape.ID} is not on page {page.name!r}")


def _check_point(end: _End) -> None:
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
    return None if end is None else EndGlue(_id(end[0]), end[1])


class _Connect:
    """A read view over one ``<Connect>`` element of a page: which end of which connector is glued to what.

    Internal: the public graph is :class:`vsdxkit.shapes.Connector` and its
    queries. Every attribute is read from the element on each access, because
    renumbering a shape rewrites these very attributes, and a copy made before
    it would keep naming the vacated ID (#320).
    """

    def __init__(self, xml: Element) -> None:
        # the attributes come from the package, so a record without them is a
        # malformed package rather than a bad argument
        missing = [name for name in ("FromSheet", "ToSheet") if name not in xml.attrib]
        if missing:
            raise MalformedPackageError(f"Connect element is missing required attribute(s): {', '.join(missing)}")
        self.xml = xml

    def __repr__(self) -> str:
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


def _glue_connector(connector: _ConnectorShape, begin: _Glued, end: _Glued, options: ConnectorOptions) -> None:
    """Glue a new connector's ends as :func:`_plan_connector` planned them."""
    _write(connector, begin, end, routing_cells(options.routing, dynamic=options.glue is Glue.DYNAMIC))
    # initial endpoints so the file renders sensibly even before Visio recalculates
    connector.set_start_and_finish(begin[0].center_x_y, end[0].center_x_y)


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

    routing = () if options is None else routing_cells(options.routing, dynamic=options.glue is Glue.DYNAMIC)
    _write(connector, begin, end, routing)
    start = begin[0].center_x_y if begin else (connector.begin_x, connector.begin_y)
    finish = end[0].center_x_y if end else (connector.end_x, connector.end_y)
    connector.set_start_and_finish(start, finish)


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
