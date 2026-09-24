from __future__ import annotations

import re
from typing import TYPE_CHECKING, TypeAlias
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

if TYPE_CHECKING:
    from vsdxkit.pages import Page
    from vsdxkit.shapes import Shape

    # One end of a connector as the engine plans it: the shape it glues to and
    # its connection point, `None` for dynamic glue. A floating end is `None`.
    _End: TypeAlias = "tuple[Shape, int | None] | None"

namespace = "{http://schemas.microsoft.com/office/visio/2012/main}"

# a Connect record's ToPart for connection point row n is 100 + n, and its ToCell Connections.X{n + 1}
_FIRST_CONNECTION_POINT_PART = 100
_CONNECTION_CELL = re.compile(r"Connections\.X(\d+)")


def _options(route: str | None, from_cp: int, to_cp: int, options: ConnectorOptions | None) -> ConnectorOptions | None:
    """The one place the connector methods' arguments become options; `None` means keep what is there."""
    if options is not None:
        if route is not None or from_cp or to_cp:
            raise ValueError("pass a route or options, not both")
        return options
    if route is not None:
        return ConnectorOptions.from_route(route, from_cp, to_cp)
    if from_cp or to_cp:
        raise ValueError("from_cp and to_cp choose connection points, so they need a route")
    return None


def _connection_rows(shape: Shape) -> frozenset[int]:
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


def _id(shape: Shape) -> str:
    """The shape's id, which glue cannot name a shape without."""
    shape_id = shape.ID
    if shape_id is None:
        raise MalformedPackageError("a Shape element has no ID attribute, so nothing can be glued to it")
    return shape_id


def _check_endpoint(page: Page, shape: Shape, connector: Shape | None) -> None:
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


def _record_point(connect: Connect) -> int | None:
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


class Connect:
    """Connect class to represent a connection between two `Shape` objects"""

    def __init__(self, xml: Element | None = None, page: Page | None = None):
        if page is None:
            raise ValueError("Connect requires the page containing the connection")
        if xml is None:
            raise ValueError("Connect requires the connection's XML element")
        if type(xml) is not Element or xml.tag != f"{namespace}Connect":
            raise ValueError(f"Connect requires a {namespace}Connect element, got {xml.tag!r}")
        # Not an argument check like the three above: these attributes come from
        # the package, and `page.connects` builds a Connect per element in it.
        missing = [name for name in ("FromSheet", "ToSheet") if name not in xml.attrib]
        if missing:
            raise MalformedPackageError(f"Connect element is missing required attribute(s): {', '.join(missing)}")
        self.xml = xml
        self.page = page

    # Read from the element on each access, not copied in. `_remap_connect_records`
    # rewrites these very attributes when a shape is renumbered, so a Connect
    # built before the renumber would otherwise keep naming the vacated id - the
    # same second-store drift that #320 fixed on Shape.

    @property
    def from_id(self) -> str:
        """The connector shape this record leads from."""
        return self.xml.attrib["FromSheet"]

    @property
    def to_id(self) -> str:
        """The shape this record's connector terminates at."""
        return self.xml.attrib["ToSheet"]

    @property
    def from_rel(self) -> str | None:
        """Which end of the connector is glued: ``BeginX``, ``EndX``, or absent."""
        return self.xml.attrib.get("FromCell")

    @property
    def to_rel(self) -> str | None:
        """What the connector is glued to: ``PinX``, a ``Connections.Xn`` row, or absent."""
        return self.xml.attrib.get("ToCell")

    @staticmethod
    def create(
        page: Page | None = None,
        from_shape: Shape | None = None,
        to_shape: Shape | None = None,
        route: str | None = None,
        from_cp: int = 0,
        to_cp: int = 0,
        *,
        options: ConnectorOptions | None = None,
    ) -> Shape:
        """Create a connector glued from ``from_shape`` to ``to_shape``.

        ``options`` says how it is glued and routed, and defaults to dynamic
        glue with Visio's routing. ``route`` is the older spelling of the same
        thing: 'dynamic' (shape glue) or 'point' (connection-point glue, with
        ``from_cp``/``to_cp`` the 0-based point on each shape), optionally
        joined with one of 'straight', 'rightangle' or 'curved', as in
        'point|curved'. Pass one or the other.

        Everything is checked before anything is written: both shapes are on
        ``page``, and each connection point exists.

        :returns: the new connector
        :rtype: Shape
        """
        if page is None:
            raise ValueError("Connect.create() requires a page")
        if from_shape is None or to_shape is None:
            raise ValueError("Connect.create() requires both from_shape and to_shape")
        chosen = _options(route, from_cp, to_cp, options) or ConnectorOptions()
        begin = (from_shape, chosen.end_point(begin=True))
        end = (to_shape, chosen.end_point(begin=False))
        for shape in (from_shape, to_shape):
            _check_endpoint(page, shape, None)
        for glued in (begin, end):
            _check_point(glued)

        # vsdxkit.media opens its donors as Documents, which import this
        # module, so importing it at module level would be a cycle
        from vsdxkit import media

        # the copy imports the connector's master, whether or not this
        # document has masters yet, and relates the page to it (#375)
        connector_shape = media.copy_connector(page)
        connector_shape.text = ""  # clear text used to find shape

        # copy style used by new connector shape
        master_shape = connector_shape.master_shape
        line_style_id = master_shape.line_style_id if master_shape is not None else None
        if line_style_id is not None and not isinstance(page.vis._get_style_by_id(line_style_id), Element):
            # assume same if is ok, todo: use names for match and increment IDs
            media_style = media.media_style(line_style_id)
            if media_style is not None:
                page.vis._style_sheets().append(media_style)  # a copy of the donor's

        Connect._write(connector_shape, begin, end, routing_cells(chosen.routing, dynamic=chosen.glue is Glue.DYNAMIC))
        # initial endpoints so the file renders sensibly even before Visio recalculates
        connector_shape.set_start_and_finish(from_shape.center_x_y, to_shape.center_x_y)
        return connector_shape

    @staticmethod
    def _write(
        connector_shape: Shape,
        begin: _End,
        end: _End,
        routing: tuple[CellWrite, ...],
    ) -> None:
        """Glue the connector's ends as planned: its cells, then its records in place of the ones it had."""
        connector_id = _id(connector_shape)
        begin_glue, end_glue = _end_glue(begin), _end_glue(end)
        for change in (*glue_cells(begin_glue, end_glue), *routing):
            Connect._change_cell(connector_shape, change)
        page = connector_shape.page
        page.remove_connect_records({connector_id})
        for record in connection_records(connector_id, begin_glue, end_glue):
            page.add_connect(Connect(xml=record_element(record), page=page))

    @staticmethod
    def _change_cell(connector_shape: Shape, change: CellChange) -> None:
        if isinstance(change, CellWrite):
            connector_shape.get_or_create_cell(change.name, v=change.value, f=change.formula)
            return
        # the two below edit the element: a Cell cannot drop a formula, and
        # nothing removes one of a shape's cells
        connector_shape._require_attached(f"writing shape cell {change.name!r}")
        cell = connector_shape._cell(change.name)
        if cell is None:
            return
        if isinstance(change, CellFreeze):
            cell.xml.attrib.pop("F", None)
        elif isinstance(change, CellInherit):
            connector_shape.xml.remove(cell.xml)

    @staticmethod
    def _current_ends(page: Page, connector_shape: Shape) -> tuple[_End, _End]:
        """Each end as the connector's records have it glued; `None` for an end no record names a shape for."""
        ends: dict[str, tuple[Shape, int | None]] = {}
        for connect in page.connects:
            if connect.from_id != connector_shape.ID or connect.from_rel not in ("BeginX", "EndX"):
                continue
            shape = page.shapes.by_id(connect.to_id)
            if shape is None:
                continue
            ends[connect.from_rel] = (shape, _record_point(connect))
        return ends.get("BeginX"), ends.get("EndX")

    @staticmethod
    def retarget(
        page: Page,
        connector_shape: Shape,
        from_shape: Shape | None = None,
        to_shape: Shape | None = None,
        route: str | None = None,
        from_cp: int = 0,
        to_cp: int = 0,
        *,
        options: ConnectorOptions | None = None,
    ) -> Shape:
        """Glue one or both ends of an existing connector to other shapes.

        With no ``options`` (and no ``route``) the connector keeps its glue and
        routing: a moved end keeps the connection point it had, and one that
        was floating or glued dynamically is glued dynamically. A connection
        point the new shape does not have is refused, never dropped for
        dynamic glue. ``options``, or ``route`` as in :meth:`create`, replace
        the glue and routing of both ends. An end not named stays where it is,
        floating if it was.

        Everything is checked before anything is written.

        :returns: the connector
        """
        if from_shape is None and to_shape is None:
            raise InvalidOperationError("retargeting a connector needs at least one endpoint")
        chosen = _options(route, from_cp, to_cp, options)
        _check_endpoint(page, connector_shape, None)
        for shape in (from_shape, to_shape):
            if shape is not None:
                _check_endpoint(page, shape, connector_shape)
        current_begin, current_end = Connect._current_ends(page, connector_shape)
        begin = Connect._next_end(current_begin, from_shape, chosen, begin=True)
        end = Connect._next_end(current_end, to_shape, chosen, begin=False)
        for glued in (begin, end):
            _check_point(glued)

        routing = () if chosen is None else routing_cells(chosen.routing, dynamic=chosen.glue is Glue.DYNAMIC)
        Connect._write(connector_shape, begin, end, routing)
        start = begin[0].center_x_y if begin else (connector_shape.begin_x, connector_shape.begin_y)
        finish = end[0].center_x_y if end else (connector_shape.end_x, connector_shape.end_y)
        connector_shape.set_start_and_finish(start, finish)
        return connector_shape

    @staticmethod
    def _next_end(
        current: _End,
        replacement: Shape | None,
        options: ConnectorOptions | None,
        *,
        begin: bool,
    ) -> _End:
        """Where one end goes: the shape named, or the one it has, glued as `options` say or as it was."""
        shape = replacement if replacement is not None else (current[0] if current else None)
        if shape is None:
            return None
        if options is not None:
            return shape, options.end_point(begin=begin)
        return shape, current[1] if current else None

    @property
    def shape_id(self) -> str | None:
        # ref to the shape where the connector terminates - convenience property
        return self.to_id

    @property
    def shape(self) -> Shape | None:
        return self.page.shapes.by_id(self.shape_id) if self.shape_id else None

    @property
    def connector_shape_id(self) -> str | None:
        # ref to the connector shape - convenience property
        return self.from_id

    @property
    def connector_shape(self) -> Shape | None:
        return self.page.shapes.by_id(self.connector_shape_id) if self.connector_shape_id else None

    def __repr__(self):
        return f"Connect: from={self.from_id} to={self.to_id} connector_id={self.connector_shape_id} shape_id={self.shape_id}"


def _float_ends(connector: Shape) -> None:
    """Leave both of a 1-D shape's ends unglued: the cells a floating end has, and no records.

    A copy of a glued connector keeps glue formulas naming the shapes the
    original is glued to, but none of its records, and Visio would pull it
    back to them.
    """
    Connect._write(connector, None, None, ())
