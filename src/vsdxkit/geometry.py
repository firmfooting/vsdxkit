"""A shape's geometry: the Geometry section that holds the path Visio draws it along.

:class:`Geometry` is the section, merged with the master's; a
:class:`GeometryRow` is one row of the path, such as a ``MoveTo`` or a
``LineTo``; and a :class:`GeometryCell` is one named cell, of the section or
of a row. Reach them through :attr:`vsdxkit.shapes.Shape.geometry`, never by
constructing one: each is a view onto an element of the shape's XML.
"""

from __future__ import annotations

import copy
import sys
import xml.etree.ElementTree as ET
from logging import Logger
from typing import Protocol
from xml.etree.ElementTree import Element

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from vsdxkit import namespace
from vsdxkit._inheritance import InheritedRow
from vsdxkit._logging_support import get_logger
from vsdxkit._shape_part import AttachedShape, ShapePart
from vsdxkit._xmlio import insert_row_in_index_order, make_cell_element, pretty_print_element, to_float, xml_value
from vsdxkit.errors import InvalidOperationError

_logger: Logger = get_logger(__name__)
"""This module's logger, under the ``vsdxkit`` hierarchy the library never configures a handler for."""


class _GeometryOwner(Protocol):
    """What a Geometry reads from the shape it belongs to."""

    @property
    def x(self) -> float | None:
        """The x of the shape's pin, in inches, which `Geometry.start_pos` answers for a path that opens with ``RelMoveTo``."""
        ...

    @property
    def y(self) -> float | None:
        """The y of the shape's pin, in inches, which `Geometry.start_pos` answers with `x`."""
        ...

    @property
    def geometry(self) -> Geometry | None:
        """The shape's Geometry, or None: read off the master shape, it is what an instance's Geometry merges its own section onto."""
        ...

    @property
    def master_shape(self) -> _GeometryOwner | None:
        """The shape on this shape's master that it instances, or None: a new `Geometry` starts from that shape's geometry."""
        ...

    def _require_attached(self, operation: str) -> None:
        """Raise `InvalidOperationError`, naming `operation`, once the shape is detached: every write to its geometry asks first."""
        ...


class Geometry(ShapePart):
    """The geometry of a shape: a Geometry section's cells and rows.

    A shape that has a master starts from the master's section and layers its
    own on top. Rows merge by index and then by cell name, so a row that
    overrides only X keeps the master's Y; a row carrying a ``Del`` attribute
    of any value removes the inherited row entirely, ``Del="0"`` included,
    though Visio reads that as keeping the row. Section cells merge less carefully: they are a
    list, not a dict, so an instance cell is *appended* after the inherited one
    of the same name rather than replacing it.

    An inherited row reads the master's cells but is marked
    :attr:`GeometryRow.inherited`. The first write to it,
    through :attr:`GeometryRow.x`, :meth:`move`, :meth:`set_move_to`,
    :meth:`set_line_to` or one of its cells' setters, materialises an
    override row on this shape and leaves the master alone. A write to a
    section cell this shape inherits gives this shape's section a cell of
    its own, in the same way.

    The merge copies the master's :attr:`cells` list and :attr:`rows` dict
    rather than taking them by reference, so an instance applying a ``Del``
    row, or gaining a row of its own, does not change what the master
    Geometry sees. That holds however long the master object lives. Each
    inherited :class:`GeometryCell` is this shape's view of the master's
    element: it reads the master's value until a setter writes it, and the
    write lands on a cell of this shape's own.
    """

    xml: Element
    """The shape's own ``<Section N="Geometry">`` element, where a row this shape writes goes."""
    cells: list[GeometryCell]
    """The cells directly under the section, in no row: the master's first, then this shape's, so one name can appear twice."""
    rows: dict[str, GeometryRow]
    """The path's rows, keyed by their ``IX`` attribute as a string.

    The master's rows come first, marked :attr:`GeometryRow.inherited`, and
    this shape's own replace them by index. A row of this shape's that
    carries a ``Del`` attribute of any value is left out, with the master's
    row at its index; a row without an ``IX`` is not read.
    """
    shape: _GeometryOwner
    """The :class:`~vsdxkit.shapes.Shape` the section belongs to.

    It is typed with a private protocol naming only what the geometry reads
    from the shape, because :mod:`vsdxkit.shapes` imports this module.
    """

    def __init__(self, xml: Element, shape: _GeometryOwner):
        """Read `xml`, one of `shape`'s Geometry sections, merged over its master's; `Shape.geometry` makes these."""
        # get shape master geometry, and append/overwrite with actual shape instance data

        self.xml = xml  # expect an Element of Section with attr N='Geometry'
        self.cells: list[GeometryCell] = []  # cells directly under Geometry section
        self.rows: dict[str, GeometryRow] = {}  # rows keyed by IX: type(T) + index(IX), each with named cells
        self.shape = shape

        # the master is resolved once per Shape and held there; ask for it
        # once here too, so a shape whose master this is the only reader of
        # still pays the walk of the master page a single time
        master_shape = shape.master_shape
        master_geometry = master_shape.geometry if master_shape else None

        if master_geometry is not None:
            # copy the list rather than alias it, so what this instance merges,
            # deletes or adds stays out of the master Geometry's view; each
            # cell is seen from this section, so a write to it lands here
            self.cells = [cell._seen_from(self) for cell in master_geometry.cells]

        for cell in self.xml.findall(f"{namespace}Cell"):
            self.cells.append(GeometryCell(parent=self, xml=cell))

        if master_geometry is not None:
            self.rows = {index: row._inherited_by(self) for index, row in master_geometry.rows.items()}
        for row in self.xml.findall(f"{namespace}Row"):
            index = row.attrib.get("IX")
            if index is None:
                continue  # a row without IX cannot be addressed
            g_row = GeometryRow(geometry=self, xml=row, master_geometry_row=self.rows.get(index))
            self.rows[index] = g_row
            if g_row.del_bool:  # remove if master row over-ridden with a  deleted item
                del self.rows[index]

    @property
    @override
    def _shape(self) -> AttachedShape:
        """The shape the detached-shape guard asks, so a write to a deleted shape's geometry is refused."""
        # the shape, not its document: a write to a deleted shape's geometry is
        # refused, as a write to the shape itself is
        return self.shape

    def start_pos(self) -> tuple[float | None, float | None] | None:
        """The start of the path, from the first MoveTo or RelMoveTo row.

        The two row types answer in different coordinate systems. MoveTo gives
        the row's own X/Y, relative to the shape. RelMoveTo ignores the row's
        offset altogether and gives the shape's PinX/PinY, measured from the
        page or from the enclosing group. Check the row type before relying on
        the result. Returns ``None`` if the shape has neither row.
        """
        for row in self.rows.values():  # type: GeometryRow
            if str(row.row_type).lower() == "moveto":
                return row.x, row.y
            if str(row.row_type).lower() == "relmoveto":
                # todo: find actual x,y based on shape width/height and relmoveto x,y
                return self.shape.x, self.shape.y
        return None

    def move(self, x_delta: float, y_delta: float) -> None:
        """Shift the rows that hold absolute coordinates.

        Only MoveTo and LineTo rows are shifted; relative rows are offsets
        from the previous point and stay as they are. A coordinate the row
        does not define is left undefined rather than treated as zero.

        An inherited row is read from the master and written to a copy on this
        shape, so no other shape drawn from that master moves with it. A cell
        this shape already owns loses its formula, as typing a number into
        the ShapeSheet does in Visio, so the value is the one Visio shows.
        """
        self._move(x_delta, y_delta, keep_formula=False)

    def _move(self, x_delta: float, y_delta: float, *, keep_formula: bool) -> None:
        """As :meth:`move`, with `keep_formula` passed to each coordinate write."""
        # a shape with no absolute rows writes nothing, so leaving this to the
        # row setters would make the refusal depend on the shape
        self._require_attached("Geometry.move()")
        for r in self.rows.values():  # type: GeometryRow
            _logger.debug("r=%s %s", type(r), r)
            if str(r.row_type).lower() in ["moveto", "lineto"]:  # todo: include other absolute row types
                x = r.x
                y = r.y
                if x is not None:
                    r._write_coordinate("X", x + x_delta, keep_formula=keep_formula)
                if y is not None:
                    r._write_coordinate("Y", y + y_delta, keep_formula=keep_formula)
                _logger.debug("r=%s %s after move %s, %s", type(r), r, x_delta, y_delta)

    def set_move_to(self, x: float, y: float, move_to_index: int = 0) -> None:
        """Set the coordinates of one MoveTo row.

        ``move_to_index`` counts MoveTo rows in order, and is not a row IX.
        Nothing happens if the shape has no MoveTo row at that position.

        An inherited row is copied down onto this shape first, so the master is
        left alone. The copied cell, like a cell this shape already owns,
        loses its ``F`` formula, as typing a number into the ShapeSheet does
        in Visio, so the value is the one Visio shows; its other attributes,
        such as its unit, are kept.
        """
        self._set_point("moveto", "Geometry.set_move_to()", x, y, move_to_index, keep_formula=False)

    def set_line_to(self, x: float, y: float, line_to_index: int = 0) -> None:
        """Set the coordinates of one LineTo row.

        Behaves as :meth:`set_move_to` does, over LineTo rows.
        """
        self._set_point("lineto", "Geometry.set_line_to()", x, y, line_to_index, keep_formula=False)

    def _set_point(self, row_type: str, operation: str, x: float, y: float, position: int, *, keep_formula: bool) -> None:
        """Write `x` and `y` to the `position`-th row of `row_type` (lower case), if the shape has one; `operation` names the call for a refusal."""
        self._require_attached(operation)
        rows = [row for row in self.rows.values() if str(row.row_type).lower() == row_type]
        if len(rows) > position:
            rows[position]._write_coordinate("X", x, keep_formula=keep_formula)
            rows[position]._write_coordinate("Y", y, keep_formula=keep_formula)

    def __repr__(self) -> str:
        """Shows the section's cells, each row's type, index and coordinates, and then the section's XML, pretty-printed."""
        s = f"Geometry: {self.cells} {[(r.row_type, r.index, r.x, r.y) for r in self.rows.values()]}"
        s += f"\nGeometry: {pretty_print_element(self.xml)}"
        return s


class GeometryRow(InheritedRow, ShapePart):
    """One row of the path a Geometry section draws, such as a ``MoveTo`` or a ``LineTo``, holding its cells by name.

    Reach a row through :attr:`Geometry.rows`, rather than constructing one.
    See: https://docs.microsoft.com/en-us/office/client-developer/visio/row-element-geometry-sectionvisio-xml
    """

    geometry: Geometry
    """The :class:`Geometry` the row is in: for a row inherited from a master, the instance's, not the master's."""
    xml: Element
    """The row's ``<Row>`` element: for an inherited row, the master's, until :meth:`make_local`, a write through :attr:`x` or :attr:`y`, or a write to one of its :attr:`cells`, gives this shape a row of its own."""
    cells: dict[str, GeometryCell]
    """The row's cells by name, such as ``X`` and ``Y``: the master row's, with this row's own over them.

    An inherited cell reads the master's element until a setter, on the row
    or on the cell, writes it, and the write lands on a cell of this
    shape's own.
    """

    def __init__(
        self,
        geometry: Geometry,
        xml: Element | None,
        master_geometry_row: GeometryRow | None,
        T: str | None = None,
        IX: str | int | None = None,
    ):
        """Read `xml`, a row of `geometry`'s section, over `master_geometry_row`'s cells; without `xml`, add a row of type `T` at index `IX`.

        Adding one raises `ValueError` without a `T`, and `InvalidOperationError`
        where the section already has a row at `IX` or the shape is detached.
        An `IX` of None is not refused: it is written as the text ``None``.
        """
        self.geometry = geometry  # parent of this row
        self.xml = xml if type(xml) is Element else self._create_row_xml(T or "", str(IX))
        # Create a dictionary of each Cell element, indexed by name
        # a row's cells are keyed by name (unlike Geometry.cells, a list)
        self.cells: dict[str, GeometryCell] = (
            {name: cell._seen_from(self) for name, cell in master_geometry_row.cells.items()} if master_geometry_row else {}
        )
        # add/overwrite cells values with master as basis id present
        for cell in self.xml.findall(f"{namespace}Cell"):
            g_cell = GeometryCell(parent=self, xml=cell)
            if g_cell.name is not None:
                self.cells[g_cell.name] = g_cell

    @property
    @override
    def _shape(self) -> AttachedShape:
        """The shape the detached-shape guard asks: the one whose Geometry the row is in."""
        return self.geometry._shape

    def _inherited_by(self, geometry: Geometry) -> GeometryRow:
        """This row as an instance's Geometry sees it, marked inherited.

        The copy reads the master's Row element and the master's cells; the
        first write to it, or to one of its cells, calls :meth:`make_local`,
        which gives the instance a Row of its own to hold the change.
        """
        row = copy.copy(self)
        row.geometry = geometry
        row.cells = {name: cell._seen_from(row) for name, cell in self.cells.items()}
        row.inherited = True
        return row

    @override
    def _materialise(self) -> None:
        """Add this row to the instance's Geometry section, in place.

        The object keeps its identity, because :attr:`Geometry.rows` already
        holds it and :meth:`Geometry.move` may be iterating over it. Only the
        XML changes, from the master's Row element to a new, empty one on the
        instance. The cells stay the master's until a setter replaces one, so
        a coordinate the caller does not write is still inherited.
        """
        # make_local() is public and reaches here directly, not only through
        # the guarded x/y setters, and this is the only materialisation path
        self._require_attached("materialising an inherited geometry row")
        row_type, index = self.row_type, self.index
        self.xml = self._create_row_xml(row_type or "", str(index))
        _logger.debug("materialised inherited row on the instance: %s", self)

    def _create_row_xml(self, T: str, IX: str) -> Element:
        """Add a Row element for this row to the parent Geometry section.

        `insert_row_in_index_order` places the row: after the Cell and Trigger
        children the Visio schema requires them all to follow, and in index
        order among the section's existing rows.

        Both arguments have already been stringified by the caller, so
        ``IX=None`` arrives as the literal ``"None"`` and passes the
        emptiness check.
        """
        self._require_attached("creating a geometry row")
        if not T or not IX:
            raise ValueError(f"cannot create a geometry row without T and IX (got T={T!r}, IX={IX!r})")
        # Create new row xml
        row = ET.fromstring(f'<Row xmlns="{namespace[1:-1]}" T="{T}" IX="{IX}" />')
        indexes = [
            child.attrib["IX"] for child in self.geometry.xml if child.tag == f"{namespace}Row" and child.attrib.get("IX")
        ]
        if IX in indexes:
            # todo: replace existing row with new one
            raise InvalidOperationError(f"geometry row IX={IX} already exists")
        insert_row_in_index_order(self.geometry.xml, row)

        self.geometry.rows[IX] = self
        return row

    @property
    def row_type(self) -> str | None:
        """The row's type, its ``T`` attribute, such as ``MoveTo``, ``LineTo`` or ``RelMoveTo``; ``None`` for a row without one.

        Setting it writes ``str(value)`` to :attr:`xml` as it stands, so on an
        inherited row it changes the master's row. A write to a detached
        shape's row raises :class:`~vsdxkit.errors.InvalidOperationError`.
        """
        return self.xml.attrib.get("T")

    @row_type.setter
    def row_type(self, value: str | int) -> None:
        self._require_attached("writing a geometry row's type")
        self.xml.attrib["T"] = str(value)

    @property
    def index(self) -> str | None:
        """The row's IX attribute.

        :attr:`Geometry.rows` is keyed when the section is read, so setting
        this afterwards leaves the row filed under its old index. Setting it
        writes ``str(value)`` to :attr:`xml` as it stands, so on an inherited
        row it changes the master's row. A write to a detached shape's row
        raises :class:`~vsdxkit.errors.InvalidOperationError`.
        """
        return self.xml.attrib.get("IX")

    @index.setter
    def index(self, value: str | int) -> None:
        self._require_attached("writing a geometry row's index")
        self.xml.attrib["IX"] = str(value)

    @property
    def x(self) -> float | None:
        """The row's X coordinate, or ``None`` if the row does not set one.

        Setting it adds the cell if the row lacks one. A row or cell inherited
        from a master is copied onto this shape first, so the master keeps the
        coordinate every other instance reads.
        """
        x_cell = self.cells.get("X")
        return to_float(x_cell.value, "X") if x_cell and x_cell.value else None

    @x.setter
    def x(self, value: float | str) -> None:
        self._write_coordinate("X", value, keep_formula=False)

    @property
    def y(self) -> float | None:
        """The row's Y coordinate. Behaves as :attr:`x` does."""
        y_cell = self.cells.get("Y")
        return to_float(y_cell.value, "Y") if y_cell and y_cell.value else None

    @y.setter
    def y(self, value: float | str) -> None:
        self._write_coordinate("Y", value, keep_formula=False)

    def _write_coordinate(self, name: str, value: float | str, *, keep_formula: bool) -> None:
        """Write coordinate cell `name` (``X`` or ``Y``), copying an inherited row down first; `keep_formula` as :meth:`GeometryCell._set_value` takes it."""
        # ahead of make_local(): a refused write must not leave an empty
        # override row behind on the shape
        self._require_attached(f"writing a geometry row's {name} coordinate")
        cell_value = xml_value(value)  # ahead of any write: None raises TypeError and leaves no cell behind
        cell = self.cells.get(name)
        if cell is None:
            self.make_local()  # an inherited row gets one of its own before it is written
            cell = GeometryCell(parent=self, xml=None, name=name)
        else:
            cell._make_local()  # the row, and then a cell that is still the master's
        cell._set_value(cell_value, keep_formula=keep_formula)

    @property
    def del_bool(self) -> str | None:
        """The Del attribute: whether a row inherited from a master is deleted.

        Assigning a falsy value removes the attribute, and raises ``KeyError``
        if it was not set to begin with. Setting it writes to :attr:`xml` as
        it stands, so on an inherited row it changes the master's row. A
        write to a detached shape's row raises
        :class:`~vsdxkit.errors.InvalidOperationError`.
        """
        return self.xml.attrib.get("Del")

    @del_bool.setter
    def del_bool(self, value: object) -> None:
        self._require_attached("writing a geometry row's Del flag")
        if value:
            self.xml.attrib["Del"] = "1"  # set to 1 if truthy
        else:
            del self.xml.attrib["Del"]  # remove attribute if falsy

    def __repr__(self) -> str:
        """Shows the row's index, its ``Del`` attribute, its type and its cells."""
        s = f"Row[{self.index}] del:{self.del_bool}: {self.row_type}={self.cells}"
        return s


class GeometryCell(ShapePart):
    """One cell of a Geometry section or one of its rows: a name and a value, such as ``X`` or ``Y``.

    Reach a cell through :attr:`Geometry.cells` or :attr:`GeometryRow.cells`,
    rather than constructing one.
    """

    parent: GeometryRow | Geometry
    """The :class:`GeometryRow` or :class:`Geometry` the cell is in: for a cell inherited from a master, the instance's, which a write goes to."""
    _parent_xml: Element
    """The parent's element the cell's ``<Cell>`` was last put in: where a new cell is appended, or an inherited cell copied down."""
    xml: Element
    """The ``<Cell>`` element this reads and writes: for a cell inherited from a master, the master's, until a setter gives this shape one of its own."""

    def __init__(
        self,
        parent: GeometryRow | Geometry,
        xml: Element | None,
        name: str | None = None,
        value: float | str | None = None,
    ):
        """Wrap `xml`, a cell of `parent`, or without it add a cell named `name` to `parent`; then write `name` and `value` where given."""
        self.parent = parent
        self._parent_xml = parent.xml
        self.xml = xml if type(xml) is Element else self._create_cell_xml(name or "")
        if name:
            self.name = name
        if value is not None:
            self.value = value

    @property
    @override
    def _shape(self) -> AttachedShape:
        """The shape the detached-shape guard asks: the one the cell's parent belongs to."""
        return self.parent._shape

    def _create_cell_xml(self, name: str) -> Element:
        """Append a ``<Cell>`` named `name` to the parent's element, file this cell in the parent's `cells`, and return the element."""
        # also the first write of GeometryCell.__init__, so constructing a cell
        # on a detached shape refuses before it appends anything
        self._require_attached("creating a geometry cell")
        if isinstance(self.parent, GeometryRow):
            # a cell added to an inherited row goes on the instance's own row
            self.parent.make_local()
            self._parent_xml = self.parent.xml
        cell = make_cell_element(name)
        self._parent_xml.append(cell)
        if isinstance(self.parent, GeometryRow):
            self.parent.cells[name] = self
        else:
            self.parent.cells.append(self)
        return cell

    def _seen_from(self, parent: GeometryRow | Geometry) -> GeometryCell:
        """This cell as `parent`, an instance's row or section, sees it: the same element, but written through `parent`."""
        cell = copy.copy(self)
        cell.parent = parent
        return cell

    def _make_local(self) -> None:
        """Give the cell to this shape if it is still the master's, so a write to it leaves the master alone.

        A cell of an inherited row calls the row's :meth:`GeometryRow.make_local`
        first. A cell whose element is not among its parent's own is then given
        one of its own there: the instance's cell of that name where the
        parent already has one, which only a section can, or else a copy of
        the master's cell, whole, with its unit and its formula. The write
        that follows applies its own rule to the copy: a value write drops
        the formula, and a library write that keeps it leaves it. Visio
        matches the two by name, and the master's cell, with every other
        instance, is left as it was.
        """
        parent = self.parent
        if isinstance(parent, GeometryRow):
            parent.make_local()
        home = parent.xml
        own_cells = home.findall(f"{namespace}Cell")
        if any(own is self.xml for own in own_cells):
            return
        name = self.name or ""
        own = next((cell for cell in own_cells if cell.attrib.get("N") == name), None)
        if own is None:
            own = copy.deepcopy(self.xml)
            # a section is Cell*, Trigger*, Row*, so a section cell goes after
            # the section's last cell rather than after its rows
            home.insert(list(home).index(own_cells[-1]) + 1 if own_cells else 0, own)
        self.xml = own
        self._parent_xml = home

    @property
    def value(self) -> str | None:
        """The cell's value, its ``V`` attribute, as the text the file holds; ``None`` when it has none.

        Setting it writes ``str(value)`` to ``V`` and removes the formula, as
        typing a number into the ShapeSheet cell does in Visio, so the value
        is the one Visio shows. A cell this shape inherits from its master
        is copied onto this shape first, with its row where the row is
        inherited too, and the write lands on the copy: the master keeps
        its cell, value and formula, and so does every other shape drawn
        from it. ``None`` raises :class:`TypeError`, and a write to a
        detached shape's cell raises
        :class:`~vsdxkit.errors.InvalidOperationError`.
        """
        return self.xml.attrib.get("V")

    @value.setter
    def value(self, value: float | str) -> None:
        # ahead of _make_local(): a refused write must not leave an empty
        # override row behind on the shape
        self._require_attached(f"writing the value of geometry cell {self.name!r}")
        text = xml_value(value)
        self._make_local()
        self._set_value(text, keep_formula=False)

    def _set_value(self, value: float | str, *, keep_formula: bool) -> None:
        """Write `value` to ``V`` of the element as it stands, and without `keep_formula` remove ``F``, as :meth:`vsdxkit.shapes.Cell._set_value` does."""
        self._require_attached(f"writing the value of geometry cell {self.name!r}")
        text = xml_value(value)
        self.xml.attrib["V"] = text
        if not keep_formula:
            self.xml.attrib.pop("F", None)

    @property
    def formula(self) -> str | None:
        """The cell's formula, its ``F`` attribute, or ``None`` when it has none.

        Setting it writes the text to ``F`` and leaves the value as it was:
        nothing here evaluates the formula. A cell this shape inherits is
        copied onto this shape first, as :attr:`value` copies it. It refuses
        what :attr:`value` refuses.
        """
        return self.xml.attrib.get("F")

    @formula.setter
    def formula(self, value: str) -> None:
        self._require_attached(f"writing the formula of geometry cell {self.name!r}")
        text = xml_value(value)
        self._make_local()
        self.xml.attrib["F"] = text

    @property
    def name(self) -> str | None:
        """The cell's name, its ``N`` attribute, such as ``X``; ``None`` for a cell without one.

        Setting it writes the text to ``N`` and refuses what :attr:`value`
        refuses. A cell this shape inherits is copied onto this shape first,
        as :attr:`value` copies it, so the master's cell keeps its name. A
        row's :attr:`GeometryRow.cells` keeps the cell under the name it had
        when it was filed.
        """
        return self.xml.attrib.get("N")

    @name.setter
    def name(self, value: str) -> None:
        self._require_attached("writing a geometry cell's name")
        text = xml_value(value)
        self._make_local()
        self.xml.attrib["N"] = text

    def __repr__(self) -> str:
        """Shows the cell as ``name=value``, and its formula where it has one."""
        s = f"{self.name}={self.value}"
        if self.formula:
            s += f" formula={self.formula}"
        return s
