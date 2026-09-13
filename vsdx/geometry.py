from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element

import vsdx

from .logging_support import get_logger
from .xmlio import xml_value

logger = get_logger(__name__)

namespace = "{http://schemas.microsoft.com/office/visio/2012/main}"  # visio file name space


class Geometry:
    """The geometry of a shape: a Geometry section's cells and rows.

    A shape that has a master starts from the master's section and layers its
    own on top. Rows merge by index and then by cell name, so a row that
    overrides only X keeps the master's Y; a row carrying ``Del="1"`` removes
    the inherited row entirely. Section cells merge less carefully: they are a
    list, not a dict, so an instance cell is *appended* after the inherited one
    of the same name rather than replacing it.

    An inherited row is the master's :class:`GeometryRow` object, and its cells
    are the master's XML. Writing to one through :attr:`GeometryRow.x`, or
    through :meth:`move`, edits the master and so moves every other shape
    drawn from it. :meth:`set_move_to` and :meth:`set_line_to` avoid that by
    copying the row down onto the instance first.

    The merge also takes the master's :attr:`rows` dict by reference rather
    than copying it, so applying a ``Del`` row deletes it from the master
    Geometry's view too. That is harmless only because ``Shape.master_shape``
    rebuilds the master on every access, leaving the mutated object to be
    discarded; it would not survive the master being cached.
    """

    def __init__(self, xml: Element, shape: vsdx.Shape):
        # get shape master geometry, and append/overwrite with actual shape instance data

        self.xml = xml  # expect an Element of Section with attr N='Geometry'
        self.cells: list[GeometryCell] = []  # cells directly under Geometry section
        self.rows: dict[str, GeometryRow] = {}  # rows keyed by IX: type(T) + index(IX), each with named cells
        self.shape = shape

        if shape.master_shape and shape.master_shape.geometry:
            self.cells = shape.master_shape.geometry.cells

        for cell in self.xml.findall(f"{namespace}Cell"):
            self.cells.append(GeometryCell(parent=self, xml=cell))

        if shape.master_shape and shape.master_shape.geometry:
            self.rows = shape.master_shape.geometry.rows  # type: dict
        for row in self.xml.findall(f"{namespace}Row"):
            index = row.attrib.get("IX")
            if index is None:
                continue  # a row without IX cannot be addressed
            g_row = GeometryRow(geometry=self, xml=row, master_geometry_row=self.rows.get(index))
            self.rows[index] = g_row
            if g_row.del_bool:  # remove if master row over-ridden with a  deleted item
                del self.rows[index]

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

        An inherited row is shifted in the master's XML, which moves every
        other shape drawn from that master too.
        """
        for r in self.rows.values():  # type: GeometryRow
            logger.debug("r=%s %s", type(r), r)
            if str(r.row_type).lower() in ["moveto", "lineto"]:  # todo: include other absolute row types
                x = r.x
                y = r.y
                if x is not None:
                    r.x = x + x_delta
                if y is not None:
                    r.y = y + y_delta
                logger.debug("r=%s %s after move %s, %s", type(r), r, x_delta, y_delta)

    def set_move_to(self, x: float, y: float, move_to_index: int = 0) -> None:
        """Set the coordinates of one MoveTo row.

        ``move_to_index`` counts MoveTo rows in order, and is not a row IX.
        Nothing happens if the shape has no MoveTo row at that position.

        An inherited row is copied down onto this shape first, so the master is
        left alone; the copy carries the value but not the master cell's ``F``
        formula. A cell this shape already owns keeps its formula, and Visio
        re-evaluates that formula over the value written here.
        """
        move_tos = [r for r in self.rows.values() if str(r.row_type).lower() == "moveto"]
        # print(f"move_tos={move_tos}")
        if len(move_tos) > move_to_index:
            move_to = move_tos[move_to_index]  # type: GeometryRow
            if move_to.geometry.shape.master_page_ID != self.shape.master_page_ID:
                move_to = GeometryRow(geometry=self, xml=None, master_geometry_row=move_to, T="MoveTo", IX=move_to.index)
                logger.debug("set_move_to() created: %s", move_to)
            move_to.x = x
            move_to.y = y
            # print(f"move_to[{move_to_index}]={move_to.x},{move_to.y}")

    def set_line_to(self, x: float, y: float, line_to_index: int = 0) -> None:
        """Set the coordinates of one LineTo row.

        Behaves as :meth:`set_move_to` does, over LineTo rows.
        """
        line_tos = [r for r in self.rows.values() if str(r.row_type).lower() == "lineto"]
        # print(f"line_tos={line_tos}")
        if len(line_tos) > line_to_index:
            line_to = line_tos[line_to_index]  # type: GeometryRow
            if line_to.geometry.shape.master_page_ID != self.shape.master_page_ID:
                line_to = GeometryRow(geometry=self, xml=None, master_geometry_row=line_to, T="LineTo", IX=line_to.index)
                logger.debug("set_line_to() created: %s", line_to)
            line_to.x = x
            line_to.y = y
            # print(f"line_to[{line_to_index}]={line_to.x},{line_to.y}")

    def __repr__(self):
        s = f"Geometry: {self.cells} {[(r.row_type, r.index, r.x, r.y) for r in self.rows.values()]}"
        s += f"\nGeometry: {vsdx.pretty_print_element(self.xml)}"
        return s


class GeometryRow:
    """A row with type(T) and index(IX), each containing a list of Cells"""

    """See: https://docs.microsoft.com/en-us/office/client-developer/visio/row-element-geometry-sectionvisio-xml """

    def __init__(
        self,
        geometry: Geometry,
        xml: Element | None,
        master_geometry_row: GeometryRow | None,
        T: str | None = None,
        IX: str | int | None = None,
    ):
        self.geometry = geometry  # parent of this row
        self.xml = xml if type(xml) is Element else self.create_row_xml(T or "", str(IX))
        # Create a dictionary of each Cell element, indexed by name
        # a row's cells are keyed by name (unlike Geometry.cells, a list)
        self.cells: dict[str, GeometryCell] = dict(master_geometry_row.cells) if master_geometry_row else {}
        # add/overwrite cells values with master as basis id present
        for cell in self.xml.findall(f"{namespace}Cell"):
            g_cell = GeometryCell(parent=self, xml=cell)
            if g_cell.name is not None:
                self.cells[g_cell.name] = g_cell

    def create_row_xml(self, T: str, IX: str) -> Element:
        """Add a Row element for this row to the parent Geometry section.

        Placement is unreliable in two ways. The position is worked out over
        the section's Row elements alone but applied to all of its children,
        so a new row can land between the section's Cell elements, which the
        Visio schema does not allow. Indexes are also sorted as text, so IX 10
        lands ahead of IX 2, and row order is the order the path is drawn in.

        Both arguments have already been stringified by the caller, so
        ``IX=None`` arrives as the literal ``"None"`` and passes the
        emptiness check.
        """
        if not T or not IX:
            raise ValueError(f"cannot create a geometry row without T and IX (got T={T!r}, IX={IX!r})")
        # Create new row xml
        row = ET.fromstring(f'<Row xmlns="{namespace[1:-1]}" T="{T}" IX="{IX}" />')
        # get all indexes
        indexes = [x.attrib.get("IX") for x in self.geometry.xml.findall(f"{namespace}Row") if x.attrib.get("IX")]
        if IX in indexes:
            # todo: replace existing row with new one
            raise ValueError(f"geometry row IX={IX} already exists")
        indexes.append(IX)
        indexes.sort()
        self.geometry.xml.insert(indexes.index(IX), row)

        self.geometry.rows[IX] = self
        return row

    @property
    def row_type(self) -> str | None:
        return self.xml.attrib.get("T")

    @row_type.setter
    def row_type(self, value: str | int) -> None:
        self.xml.attrib["T"] = str(value)

    @property
    def index(self) -> str | None:
        """The row's IX attribute.

        :attr:`Geometry.rows` is keyed when the section is read, so setting
        this afterwards leaves the row filed under its old index.
        """
        return self.xml.attrib.get("IX")

    @index.setter
    def index(self, value: str | int) -> None:
        self.xml.attrib["IX"] = str(value)

    @property
    def x(self) -> float | None:
        """The row's X coordinate, or ``None`` if the row does not set one.

        Setting it adds the cell if the row lacks one. If this row is itself
        inherited from a master, the write lands in the master's XML; copy the
        row down first (as :meth:`Geometry.set_move_to` does) to avoid that.
        """
        x_cell = self.cells.get("X")
        return float(x_cell.value) if x_cell and x_cell.value else None

    @x.setter
    def x(self, value: float | str) -> None:
        cell_value = xml_value(value)
        x_cell = self.cells.get("X")  # type: GeometryCell
        if not x_cell or (
            type(x_cell.parent) is GeometryRow
            and x_cell.parent.geometry.shape.master_page_ID != self.geometry.shape.master_page_ID
        ):
            # create new cell if none exists, or if existing cell is from master shape
            x_cell = GeometryCell(parent=self, xml=None, name="X", value=cell_value)
            logger.debug("x_cell=%s", x_cell)
        x_cell.value = cell_value

    @property
    def y(self) -> float | None:
        """The row's Y coordinate. Behaves as :attr:`x` does."""
        y_cell = self.cells.get("Y")
        return float(y_cell.value) if y_cell and y_cell.value else None

    @y.setter
    def y(self, value: float | str) -> None:
        cell_value = xml_value(value)
        y_cell = self.cells.get("Y")
        if not y_cell or (
            type(y_cell.parent) is GeometryRow
            and y_cell.parent.geometry.shape.master_page_ID != self.geometry.shape.master_page_ID
        ):
            # create new cell if none exists, or if existing cell is from master shape
            y_cell = GeometryCell(parent=self, xml=None, name="Y", value=cell_value)
            logger.debug("y_cell=%s", y_cell)
        y_cell.value = cell_value

    @property
    def del_bool(self) -> str | None:
        """The Del attribute: whether a row inherited from a master is deleted.

        Assigning a falsy value removes the attribute, and raises ``KeyError``
        if it was not set to begin with.
        """
        return self.xml.attrib.get("Del")

    @del_bool.setter
    def del_bool(self, value: object) -> None:
        if value:
            self.xml.attrib["Del"] = "1"  # set to 1 if truthy
        else:
            del self.xml.attrib["Del"]  # remove attribute if falsy

    def __repr__(self):
        s = f"Row[{self.index}] del:{self.del_bool}: {self.row_type}={self.cells}"
        return s


class GeometryCell:
    """class to represent a Cell element, a name value pair. This may be a child of Geometry or of GeometryRow"""

    def __init__(
        self,
        parent: GeometryRow | Geometry,
        xml: Element | None,
        name: str | None = None,
        value: float | str | None = None,
    ):
        self.parent = parent
        self.parent_xml = parent.xml
        self.xml = xml if type(xml) is Element else self.create_cell_xml(name or "")
        if name:
            self.name = name
        if value is not None:
            self.value = value

    def create_cell_xml(self, name: str) -> Element:
        cell = ET.fromstring(f'<Cell xmlns="{namespace[1:-1]}"  />')
        self.parent_xml.append(cell)
        if isinstance(self.parent, GeometryRow):
            self.parent.cells[name] = self
        else:
            self.parent.cells.append(self)
        return cell

    @property
    def value(self) -> str | None:
        return self.xml.attrib.get("V")

    @value.setter
    def value(self, value: float | str) -> None:
        self.xml.attrib["V"] = xml_value(value)

    @property
    def formula(self) -> str | None:
        return self.xml.attrib.get("F")

    @formula.setter
    def formula(self, value: str) -> None:
        self.xml.attrib["F"] = xml_value(value)

    @property
    def name(self) -> str | None:
        return self.xml.attrib.get("N")

    @name.setter
    def name(self, value: str) -> None:
        self.xml.attrib["N"] = xml_value(value)

    @property
    def func(self) -> str | None:  # assume F stands for function, i.e. F="Width*0.5"
        return self.xml.attrib.get("F")

    def __repr__(self):
        s = f"{self.name}={self.value}"
        if self.func:
            s += f" func={self.func}"
        return s
