# Writes Land Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** every value a user writes to a shape is the value Visio shows, a write to a master instance stays on the instance, and moving a shape moves the shape.

**Architecture:** one cell writer, `Shape._write_cell(name, *, v, f, keep_formula)`. A user's value write drops the cell's formula. A library write keeps it; the library's writes are the glue engine's and the formula cache's, and a 1-D shape's derived cells.
- `Cell` and `GeometryCell` gain a private `_set_value(value, *, keep_formula)`, and their public `value` setters are the user's form.
- A coordinate written to a glued end first frees that end, through a per-end `_float_end`.
- The glue engine places the ends it glues through a private `_place_ends(..., keep_glue=True)`, so the public `set_start_and_finish` can unglue.

**Tech Stack:** Python 3.10–3.14, `xml.etree.ElementTree`, pytest, uv, ruff, pyrefly strict, mypy.

**Spec:** `.hermes/plans/2026-09-27_writes-land-spec.md`. Read it with this plan; the spec wins where they differ.

## Global Constraints

- **Imports:** absolute only (ruff `ban-relative-imports = "all"`), no `__all__`, no re-exports. Follow dignified-python (dagster-io).
- **Private by default:** a new name is private (leading underscore on the name or its module) unless it is user API. The only new public behaviour is what the spec names.
- **Docstrings:** every definition in `src/vsdxkit`, private or public, has one (`tools/check_docstrings.py`). A constant or field is documented by a string on the line after it, never `#:`.
- **Errors:** a refused operation raises `vsdxkit.errors.InvalidOperationError`, with a message that names the shape and says what to do instead.
- **Detached shapes:** a write to a detached shape raises `InvalidOperationError` before it writes anything.
- **Test-first:** each behaviour gets a test that fails before the change, and fails for the reason given.
- **Gates, all green on every commit's PR head:**
  - `uv run --no-sync python -m pytest tests -q` on 3.14 and `uv run --python 3.10 --isolated python -m pytest tests -q`;
  - `uv run --no-sync ruff check src tests tools` and `uv run --no-sync ruff format --check src tests tools`;
  - `uv run --no-sync pyrefly check src/vsdxkit --min-severity warn`;
  - `uv run --no-sync python tools/check_public_annotations.py`, `tools/check_migration_guide.py` and `tools/check_docstrings.py`;
  - `uv run --no-sync sphinx-build -W --keep-going -b html docs docs/_build/html`.

  The controller also runs the sdist smoke, type completeness (100.0) and `tools/check_api_documented.py`.
- **Commits:** Conventional Commits. Every commit message ends with:
  ```
  Co-Authored-By: <the model that wrote it> <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_014SeJzNKgmmqyg4BHg7odRt
  ```
- **Shell rules in this worktree:**
  - one plain command per call: no `cd x && y`, no `;`, no shell variables, no heredocs;
  - write scripts and commit messages to files, then run or use them;
  - `git commit -F <file>`.
- **Fixtures:** in `tests/` and `tests/fixtures/com_reference/`. A test that saves works on a copy, through the `vsdx_copy` fixture or `tmp_path`.
- **Line numbers** below are on `main` at 3575873. Find each symbol by name if they have moved.

## Review Focus

1. **A connector the library glues stays glued.** `page.connect()` and `connector.retarget()` must still report `source` and `target` after 8a, even though the end setters now unglue. Pinned in Task 5.
2. **A section-cell write on a shape without that row is refused, not created.** It must not leave a stray top-level `<Cell N="Control/...">`, and a refused write writes nothing. Pinned in Task 3.
3. **An inherited property or row written through any setter leaves the master alone,** including `DataProperty.set_attribute` on a cell the instance does not have yet. That write must land, not return `False`. Pinned in Task 7.
4. **`set_start_and_finish` on a diagonal plain line keeps its `SQRT` width formula,** so Visio still draws it between its ends. Pinned in Task 5 (8a) and Task 11 (8c).
5. **A detached shape handed to `append_shape` or to `master_page_ID` is refused before anything moves.** Pinned in Task 9.

---

## PR 8a: one writer, and the value wins (#300, #319)

Branch `fix/writes-land-a-writer`, stacked on `fix/writes-land-spec`.

### Task 1: One helper puts a row in `IX` order

**Files:**
- Modify: `src/vsdxkit/_xmlio.py` (add two functions)
- Modify: `src/vsdxkit/geometry.py:63-65` (delete `_row_index_sort_key`) and `:312-343` (`GeometryRow._create_row_xml`)
- Modify: `src/vsdxkit/shapes.py:1487-1504` (`_create_character_color_cell`; delete `_insert_character_row`)
- Test: `tests/test_row_insertion.py` (new)

**Interfaces:**
- Produces:
  - `vsdxkit._xmlio.row_index_key(index: str) -> tuple[int, int, str]`
  - `vsdxkit._xmlio.insert_row_in_index_order(section: Element, row: Element) -> None`

- [ ] **Step 1: Write the failing tests**

```python
"""One helper puts a section row in IX order, for geometry and for text formatting alike (#319)."""

import xml.etree.ElementTree as ET

from vsdxkit import namespace
from vsdxkit._xmlio import insert_row_in_index_order
from vsdxkit.document import Document

NS = namespace[1:-1]


def _section(*children: str) -> ET.Element:
    return ET.fromstring(f'<Section xmlns="{NS}" N="Geometry">{"".join(children)}</Section>')


def _row(ix: str) -> ET.Element:
    return ET.fromstring(f'<Row xmlns="{NS}" IX="{ix}"/>')


def _layout(section: ET.Element) -> list[str]:
    return [child.get("IX") or child.get("N") or "" for child in section]


def test_a_row_goes_between_the_rows_either_side_of_its_index_as_numbers():
    """IX 10 sorts after IX 3: as text it would sort first and redraw the path in another order."""
    section = _section('<Cell N="NoFill" V="0"/>', '<Row IX="1"/>', '<Row IX="2"/>', '<Row IX="10"/>')

    insert_row_in_index_order(section, _row("3"))

    assert _layout(section) == ["NoFill", "1", "2", "3", "10"]


def test_a_first_row_goes_after_the_sections_cells():
    """A Section is Cell*, Trigger*, Row*: a row among the cells is a file Visio offers to repair."""
    section = _section('<Cell N="NoFill" V="0"/>', '<Cell N="NoLine" V="0"/>')

    insert_row_in_index_order(section, _row("1"))

    assert _layout(section) == ["NoFill", "NoLine", "1"]


def test_an_index_that_is_not_a_number_sorts_after_every_number():
    section = _section('<Row IX="x"/>')

    insert_row_in_index_order(section, _row("5"))

    assert _layout(section) == ["5", "x"]


def test_text_colour_on_a_shape_whose_character_section_has_a_non_numeric_index(vsdx_copy):
    """`_insert_character_row` did int(IX) on every sibling, so one odd index made text_color raise ValueError."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    shape = vis.pages[0].shapes.require_id("1")
    section = ET.SubElement(shape.xml, f"{namespace}Section", {"N": "Character"})
    ET.SubElement(ET.SubElement(section, f"{namespace}Row", {"IX": "a"}), f"{namespace}Cell", {"N": "Size", "V": "0.16"})

    shape.text_color = "#00ff00"

    assert [row.get("IX") for row in section.findall(f"{namespace}Row")] == ["0", "a"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --no-sync python -m pytest tests/test_row_insertion.py -q`
Expected:
- the three helper tests fail with `ImportError: cannot import name 'insert_row_in_index_order'`;
- the text-colour test fails with `ValueError: invalid literal for int() with base 10: 'a'`.

- [ ] **Step 3: Add the helpers to `src/vsdxkit/_xmlio.py`**

Import `namespace` from `vsdxkit` if the module does not already. The import-graph test allows `_xmlio` to import the package root's constants, as `geometry` does. If it refuses, take `namespace` as the module already spells it.

```python
def row_index_key(index: str) -> tuple[int, int, str]:
    """Order a section row's ``IX`` as a number, with an index that is not a whole number after every one that is."""
    return (0, int(index), "") if index.isdigit() else (1, 0, index)


def insert_row_in_index_order(section: Element, row: Element) -> None:
    """Put `row` among `section`'s rows in ``IX`` order, after the cells and triggers the schema puts ahead of every row.

    Row order is the order Visio reads a section in, so indexes compare as
    numbers: as text, IX 10 would go ahead of IX 2. An index that is not a
    whole number sorts after every one that is, rather than raising.
    """
    key = row_index_key(row.attrib.get("IX", ""))
    children = list(section)
    positions = [position for position, child in enumerate(children) if child.tag == f"{namespace}Row"]
    for position in positions:
        if row_index_key(children[position].attrib.get("IX", "")) > key:
            section.insert(position, row)
            return
    section.insert(positions[-1] + 1 if positions else len(children), row)
```

- [ ] **Step 4: Use the helper in both places**

In `geometry.py`:
- delete `_row_index_sort_key`;
- in `GeometryRow._create_row_xml`, replace everything from `children = list(self.geometry.xml)` to `self.geometry.xml.insert(first_row + indexes.index(IX), row)` with the block below;
- keep `self.geometry.rows[IX] = self` and `return row`;
- import `insert_row_in_index_order` from `vsdxkit._xmlio`;
- the docstring's second paragraph now says the helper places the row.

```python
        indexes = [child.attrib["IX"] for child in self.geometry.xml if child.tag == f"{namespace}Row" and child.attrib.get("IX")]
        if IX in indexes:
            # todo: replace existing row with new one
            raise InvalidOperationError(f"geometry row IX={IX} already exists")
        insert_row_in_index_order(self.geometry.xml, row)
```

In `shapes.py`:
- delete `_insert_character_row`;
- in `_create_character_color_cell`, replace `self._insert_character_row(section, row)` with `insert_row_in_index_order(section, row)`;
- add the import from `vsdxkit._xmlio`.

- [ ] **Step 5: Run the new tests and the geometry and text tests**

Run: `uv run --no-sync python -m pytest tests/test_row_insertion.py tests/test_geometry.py tests/test_optional_element_setters.py -q`
Expected: all pass.

- [ ] **Step 6: Run the full suite and the lint gates**

Run each gate in Global Constraints.
Expected: all green.

- [ ] **Step 7: Commit**

Stage `src/vsdxkit/_xmlio.py`, `src/vsdxkit/geometry.py`, `src/vsdxkit/shapes.py` and `tests/test_row_insertion.py`. Commit with the message `refactor: one helper puts a section row in IX order (#319)`.

### Task 2: A value written to a cell replaces its formula; the library's own writes keep it

**Files:**
- Modify: `src/vsdxkit/shapes.py`:
  - `Cell.value` setter (`:479-482`) and its docstring (`:470-477`);
  - `_refresh_formula_values` (`:1917`);
  - `set_start_and_finish`'s text-pin writes (`:1888-1889`);
  - `move` (`:1707-1708`).
- Modify: `src/vsdxkit/geometry.py`:
  - `GeometryCell.value` (`:495-509`);
  - `GeometryRow.x`/`y` (`:388-418`);
  - `Geometry.move`, `set_move_to` and `set_line_to` (`:172-224`).
- Test: `tests/test_value_wins.py` (new)

**Interfaces:**
- Produces:
  - `Cell._set_value(self, value: float | str, *, keep_formula: bool) -> None`
  - `GeometryCell._set_value(self, value: float | str, *, keep_formula: bool) -> None`
  - `GeometryRow._write_coordinate(self, name: str, value: float | str, *, keep_formula: bool) -> None`, where `name` is `"X"` or `"Y"`
  - `Geometry._move(self, x_delta: float, y_delta: float, *, keep_formula: bool) -> None`
  - `Geometry._set_point(self, row_type: str, operation: str, x: float, y: float, position: int, *, keep_formula: bool) -> None`, where `row_type` is lower-case, `"moveto"` or `"lineto"`

- [ ] **Step 1: Write the failing tests**

```python
"""A value written to a cell is the value Visio shows (#300, #319).

Visio recalculates a cell's formula on open and discards the value beside
it, so a write that leaves the formula in place does not land. Writing a
value replaces the formula, as typing a number into the ShapeSheet does.
The library's own writes, which store the value a formula gives, keep it.
"""

import pytest

from vsdxkit.document import Document


def _conn_a(vsdx_copy):
    """test9's 'Conn A': a master instance whose own Width is GUARD(EndX-BeginX), with its own LineTo row 2."""
    return Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Conn A")


def test_a_cell_value_write_drops_the_formula(vsdx_copy):
    connector = _conn_a(vsdx_copy)
    width = connector.cells["Width"]
    assert width.formula == "GUARD(EndX-BeginX)"

    width.value = 2.5

    assert (width.value, width.formula) == ("2.5", None)


def test_a_geometry_cell_value_write_drops_the_formula(vsdx_copy):
    row = _conn_a(vsdx_copy).geometry.rows["2"]
    cell = row.cells["X"]
    cell.formula = "Width*1"

    cell.value = 1.5

    assert (cell.value, cell.formula) == ("1.5", None)


def test_a_geometry_row_coordinate_write_drops_the_formula(vsdx_copy):
    row = _conn_a(vsdx_copy).geometry.rows["2"]
    row.cells["X"].formula = "Width*1"

    row.x = 1.5

    assert (row.cells["X"].value, row.cells["X"].formula) == ("1.5", None)


def test_set_line_to_drops_the_formula(vsdx_copy):
    geometry = _conn_a(vsdx_copy).geometry
    geometry.rows["2"].cells["X"].formula = "Width*1"

    geometry.set_line_to(1.5, 0.0)

    assert geometry.rows["2"].cells["X"].formula is None


def test_the_formula_cache_keeps_the_formula_it_evaluates(vsdx_copy):
    """`_refresh_formula_values` writes the value a formula gives; dropping the formula would freeze it."""
    connector = _conn_a(vsdx_copy)
    expected = connector.end_x - connector.begin_x

    connector._refresh_formula_values()

    assert connector.cells["Width"].formula == "GUARD(EndX-BeginX)"
    assert float(connector.cells["Width"].value) == pytest.approx(expected)
```

- [ ] **Step 2: Run them and watch the first four fail**

Run: `uv run --no-sync python -m pytest tests/test_value_wins.py -q`
Expected:
- the first four fail, with each formula still present (`assert ('2.5', 'GUARD(EndX-BeginX)') == ('2.5', None)` and the like);
- `test_the_formula_cache_keeps_the_formula_it_evaluates` passes. It is the guard that the next step must keep green.

- [ ] **Step 3: Give `Cell` and `GeometryCell` the two forms of a value write**

In `shapes.py`, `Cell`:

```python
    @value.setter
    def value(self, value: float | str) -> None:
        self._set_value(value, keep_formula=False)

    def _set_value(self, value: float | str, *, keep_formula: bool) -> None:
        """Write `value` to ``V``, and without `keep_formula` remove ``F``, as typing a number into the ShapeSheet cell does in Visio.

        The library keeps the formula where the value it writes is the one the
        formula gives: the formula cache, the glue engine, and a 1-D shape's
        cells derived from its ends.
        """
        self._require_attached(f"writing the value of cell {self.name!r}")
        text = xml_value(value)
        self.xml.attrib["V"] = text
        if not keep_formula:
            self.xml.attrib.pop("F", None)
```

The `value` docstring's second paragraph becomes: "Setting it writes ``str(value)`` to ``V`` and removes the formula, as typing a number into the ShapeSheet cell does in Visio, so the value is the one Visio shows. ``None`` raises :class:`TypeError`, and a write to a detached shape's cell raises :class:`~vsdxkit.errors.InvalidOperationError`."

In `geometry.py`, do the same for `GeometryCell`, with its own `_require_attached` message. Its docstring keeps the sentence saying that, on a cell inherited from a master, the write goes to the master's cell; Task 8 changes the cache refresh, not this setter.

- [ ] **Step 4: Route the row and section writes through one private form each**

In `geometry.py`, `GeometryRow`: the `x` setter becomes `self._write_coordinate("X", value, keep_formula=False)`, and `y` likewise. Add:

```python
    def _write_coordinate(self, name: str, value: float | str, *, keep_formula: bool) -> None:
        """Write coordinate cell `name` (``X`` or ``Y``), copying an inherited row down first; `keep_formula` as :meth:`GeometryCell._set_value` takes it."""
        # ahead of make_local(): a refused write must not leave an empty
        # override row behind on the shape
        self._require_attached(f"writing a geometry row's {name} coordinate")
        self.make_local()  # an inherited row gets one of its own before it is written
        cell_value = xml_value(value)
        cell = self.cells.get(name)
        if cell is None or cell.parent is not self:
            # create new cell if none exists, or if the existing one is the master's
            cell = GeometryCell(parent=self, xml=None, name=name, value=cell_value)
        cell._set_value(cell_value, keep_formula=keep_formula)
```

`Geometry`:
- `move(x_delta, y_delta)` becomes `self._move(x_delta, y_delta, keep_formula=False)`.
- `_move` holds today's body, with `r.x = x + x_delta` becoming `r._write_coordinate("X", x + x_delta, keep_formula=keep_formula)`, and Y likewise. It keeps `self._require_attached("Geometry.move()")`.
- `set_move_to` becomes `self._set_point("moveto", "Geometry.set_move_to()", x, y, move_to_index, keep_formula=False)`, and `set_line_to` likewise with `"lineto"` and `"Geometry.set_line_to()"`.

Add:

```python
    def _set_point(self, row_type: str, operation: str, x: float, y: float, position: int, *, keep_formula: bool) -> None:
        """Write `x` and `y` to the `position`-th row of `row_type` (lower case), if the shape has one; `operation` names the call for a refusal."""
        self._require_attached(operation)
        rows = [row for row in self.rows.values() if str(row.row_type).lower() == row_type]
        if len(rows) > position:
            rows[position]._write_coordinate("X", x, keep_formula=keep_formula)
            rows[position]._write_coordinate("Y", y, keep_formula=keep_formula)
```

The `set_move_to` docstring's last two sentences become: "A cell this shape already owns loses its formula, as typing a number into the ShapeSheet does in Visio, so the value is the one Visio shows."

- [ ] **Step 5: Mark the library's own value writes**

In `shapes.py`:
- `_refresh_formula_values`: `c.value = v` becomes `c._set_value(v, keep_formula=True)`.
- `set_start_and_finish`: `txt_pin_x.value = text_x` and `txt_pin_y.value = text_y` become `_set_value(..., keep_formula=True)`. The geometry calls become `self.geometry._set_point("moveto", "Shape.set_start_and_finish()", 0.0, 0.0, 0, keep_formula=True)` and `self.geometry._set_point("lineto", "Shape.set_start_and_finish()", width, height, 0, keep_formula=True)`.
- `move`: `self.geometry.move(x_delta, y_delta)` becomes `self.geometry._move(x_delta, y_delta, keep_formula=True)`. Task 10 removes this call.

- [ ] **Step 6: Run the tests**

Run: `uv run --no-sync python -m pytest tests/test_value_wins.py tests/test_geometry.py tests/test_page.py tests/test_shape.py -q`
Expected: `test_value_wins.py` all pass.

If `tests/test_page.py::test_copy_and_move_line` fails, that is the case Task 5 rewrites. It hand-writes a line's width and relies on the formula surviving to correct it. Leave it red only if it fails for that reason, and note it in the report. Nothing else may fail.

- [ ] **Step 7: Commit**

Commit with the message `fix!: a value written to a cell replaces its formula; the library's own writes keep it (#300)`.

### Task 3: One writer for every named cell

**Files:**
- Modify: `src/vsdxkit/shapes.py`:
  - `_write_cell` (`:1298-1341`), `set_cell_value` and `set_cell_formula` (`:1343-1349`);
  - `get_or_create_cell` (`:1716-1750`, to the end of the method);
  - `set_start_and_finish`'s derived-cell and `Control` writes (`:1863-1893`);
  - `move` (`:1709-1714`).
- Modify: `src/vsdxkit/_connectors.py`: the `_ConnectorShape.get_or_create_cell` protocol member (`:140-142`) and `_change_cell` (`:375`).
- Modify: `src/vsdxkit/pages.py`: `_drop_formula` (`:89-97`, delete), `_detach` (`:130`) and `create_shape` (`:901-911`).
- Modify: `src/vsdxkit/swimlanes.py` (`:261`, `:268-269`, `:302`).
- Modify: `tests/test_page.py`, `test_copy_and_move_line` (`:641-646`).
- Test: `tests/test_cell_writer_primitive.py` (extend)

**Interfaces:**
- Consumes: `Cell._set_value(value, *, keep_formula)` (Task 2).
- Produces:
  - `Shape._write_cell(self, name: str, *, v: str | None = None, f: str | None = None, keep_formula: bool = False) -> None`
  - `Shape.get_or_create_cell(self, name: str, v: str | None = None, f: str | None = None) -> Cell` (unchanged signature)
  - the `_ConnectorShape._write_cell` protocol member, with the same signature as `Shape._write_cell`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cell_writer_primitive.py`)

```python
from vsdxkit.errors import InvalidOperationError

S05 = "fixtures/com_reference/s05_swimlanes_cfflow.vsdx"


def test_a_colour_set_on_a_master_instance_is_not_overridden_by_the_masters_formula(vsdx_copy):
    """#300: shape 35 inherits LineColor from a master whose cell is a THEMEVAL formula; Visio drew the theme colour."""
    shape = Document.open(vsdx_copy(S05)).pages[0].shapes.by_id("35")
    assert shape.cell_formula("LineColor").startswith("IF(LUM(THEMEVAL())")

    shape.line_color = "#ff0000"

    assert (shape.cells["LineColor"].value, shape.cells["LineColor"].formula) == ("#ff0000", None)


def test_a_colour_whose_own_cell_says_inherit_takes_the_value(vsdx_copy):
    """Shape 35's own FillForegnd is F="Inh", which Visio reads as take the master's formula."""
    shape = Document.open(vsdx_copy(S05)).pages[0].shapes.by_id("35")
    assert shape.cells["FillForegnd"].formula == "Inh"

    shape.fill_color = "#00ff00"

    assert shape.cells["FillForegnd"].formula is None


def test_get_or_create_cell_is_the_same_writer(vsdx_copy):
    """#319: get_or_create_cell created a bare cell while set_cell_value copied the master's formula down."""
    shape = Document.open(vsdx_copy(S05)).pages[0].shapes.by_id("35")

    cell = shape.get_or_create_cell("LineColor", v="#123456")

    assert (cell.value, cell.formula) == ("#123456", None)
    assert cell.xml is shape.xml.find(f'{namespace}Cell[@N="LineColor"]')


def test_a_section_cell_the_shape_lacks_is_refused_not_created_at_the_top(shape):
    """#319: a name holding '/' became a top-level <Cell N="Control/TextPosition/X">, which is no ShapeSheet cell."""
    cells_before = [element.get("N") for element in shape.xml.findall(f"{namespace}Cell")]

    with pytest.raises(InvalidOperationError, match="Control"):
        shape.set_cell_value("Control/TextPosition/X", 1.0)

    assert [element.get("N") for element in shape.xml.findall(f"{namespace}Cell")] == cells_before


def test_a_section_cell_the_shape_has_is_written_in_its_row(vsdx_copy):
    """test5_master shape 5 has its own Control row TextPosition, whose DynX is the formula TextPosition."""
    shape = Document.open(vsdx_copy("test5_master.vsdx")).pages[0].shapes.by_id("5")

    shape.set_cell_value("Control/TextPosition/DynX", 2.0)

    cell = shape.cells["Control/TextPosition/DynX"]
    assert (cell.value, cell.formula) == ("2.0", None)
    assert shape.xml.find(f'{namespace}Cell[@N="Control/TextPosition/DynX"]') is None


def test_the_glue_engine_keeps_the_formulas_it_writes(vsdx_copy):
    """The engine's CellWrite leaves the half it does not name as it is, so glue stays formula-driven."""
    page = Document.open(vsdx_copy("test8_simple_connector.vsdx")).pages[0]
    connector = page.connect(page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B"))

    assert connector.cells["BeginX"].formula is not None
    assert connector.cells["EndX"].formula is not None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --no-sync python -m pytest tests/test_cell_writer_primitive.py -q`
Expected:
- the colour tests fail with the formula still present;
- the section test fails with `DID NOT RAISE`;
- `test_a_section_cell_the_shape_has_is_written_in_its_row` fails on its formula (`('2.0', 'TextPosition')`);
- `test_get_or_create_cell_is_the_same_writer` passes today, because both paths happen to drop F on a bare cell. Keep it as a guard;
- `test_the_glue_engine_keeps_the_formulas_it_writes` passes. It is a guard.

- [ ] **Step 3: Write the one writer**

Replace `_write_cell`, and add `_new_cell_element`:

```python
    def _write_cell(self, name: str, *, v: str | None = None, f: str | None = None, keep_formula: bool = False) -> None:
        """Set cell `name`'s value or formula: the one function that creates or updates a shape's named cell.

        A value written without a formula replaces the cell's formula, as
        typing a number into the ShapeSheet does in Visio, unless
        `keep_formula` says the value is the one the formula gives: the glue
        engine's writes, the formula cache, and a 1-D shape's cells derived
        from its ends. A formula given is written, and a value beside it keeps
        it.

        A top-level cell the shape lacks is created, as a copy of the master's
        where the master has one, so its unit and other attributes carry over.
        A name holding ``/`` is a cell of a section row, such as
        ``Control/TextPosition/X``; it is written only where the shape has that
        cell of its own.

        :raises InvalidOperationError: if the shape is detached, or `name` is a
            section cell the shape does not have
        """
        # nearly every coordinate, size and colour setter arrives here, so one
        # guard covers them all; the message describes the write because which
        # setter the caller used is not knowable from here (issue #329)
        self._require_attached(f"writing shape cell {name!r}")
        cell = self._cell(name)
        if cell is None:
            if "/" in name:
                section, _, rest = name.partition("/")
                raise InvalidOperationError(
                    f"shape ID {self.ID} has no {section} cell {rest!r} of its own to write; "
                    "a cell in a section row is written only where the shape has that row and cell"
                )
            cell = Cell(xml=self._new_cell_element(name), shape=self)
        if f is not None:
            cell.formula = f
        if v is not None:
            cell._set_value(v, keep_formula=keep_formula or f is not None)

    def _new_cell_element(self, name: str) -> Element:
        """A new top-level cell `name` among the shape's cells: a copy of its master's, formula and all, where the master has one."""
        master = self.master_shape
        master_cell = None if master is None else master.xml.find(f'{namespace}Cell[@N="{name}"]')
        if master_cell is not None:
            _logger.debug("creating cell from: %s", ET.tostring(master_cell))
        element = make_cell_element(name) if master_cell is None else ET.fromstring(ET.tostring(master_cell))
        # schema order: a shape's cells come before its Text and Sections
        cells = self.xml.findall(f"{namespace}Cell")
        self.xml.insert(list(self.xml).index(cells[-1]) + 1 if cells else 0, element)
        return element
```

`set_cell_value` and `set_cell_formula` stay one-liners over it. Their docstrings say that a value replaces the formula, and that a section cell the shape lacks is refused.

`get_or_create_cell` becomes the lines below. Its docstring keeps the `:param:` lines, and says that a value without a formula replaces the cell's formula.

```python
        self._write_cell(name, v=v, f=f)
        cell = self._cell(name)
        if cell is None:  # _write_cell wrote it or raised; this satisfies the type checker
            raise InvalidOperationError(f"shape ID {self.ID} has no cell {name!r} after writing it")
        return cell
```

- [ ] **Step 4: Move the engine and the other library writers onto it**

- **`_connectors.py`:**
  - The `_ConnectorShape` protocol member `get_or_create_cell` becomes `def _write_cell(self, name: str, *, v: str | None = None, f: str | None = None, keep_formula: bool = False) -> None:`, with docstring "Set or create the named cell; the engine passes `keep_formula`, so a half of the cell it does not name stays as it is."
  - `_change_cell`'s write becomes `connector._write_cell(change.name, v=change.value, f=change.formula, keep_formula=True)`.
- **`swimlanes.py`:** each `get_or_create_cell(NAME, v=VALUE)` becomes `_write_cell(NAME, v=VALUE, keep_formula=True)`. Swimlane layout is #337's package, and this package does not change what it writes.
- **`pages.py`:**
  - Delete `_drop_formula`.
  - In `_detach`, the call becomes `cell.xml.attrib.pop("F", None)`, where `cell` is the `shape._cell(name)` already in hand. That is a library write: it removes a formula naming a shape the copy left behind.
  - In `create_shape`, `shape.get_or_create_cell("PinX", v=str(x))` and `PinY` already drop the formula through the rule, so delete the two `_drop_formula` calls after them. `shape.width = width` and `shape.height = height` go through the setters, which now drop it, so delete their `_drop_formula` calls too.
- **`shapes.py`, `set_start_and_finish`:**
  - Each of `self.x`, `self.y`, `self.width` and `self.height` becomes `self._write_cell("PinX", v=xml_value(start_x), keep_formula=True)`, and likewise for `PinY`, `Width` and `Height`. On a 1-D shape these are derived from its ends (spec ruling).
  - Keep the end writes as they are for now; Task 5 changes them.
  - Replace the four `Control/TextPosition` writes with the loop below. Real files name the dynamic cells `DynX` and `DynY`. `XDyn` and `YDyn` exist nowhere, and were always created as stray top-level cells.

    ```python
                    for cell_name, value in (("X", text_x), ("Y", text_y), ("DynX", text_x), ("DynY", text_y)):
                        if self._cell(f"Control/TextPosition/{cell_name}") is not None:
                            self._write_cell(f"Control/TextPosition/{cell_name}", v=xml_value(value), keep_formula=True)
    ```
- **`shapes.py`, `move`:** each coordinate write becomes a library write, so 8a does not change what `move` writes, and Task 10 gives `move` its new rules. For example, `self.begin_x = self.begin_x + x_delta` becomes `self._write_cell("BeginX", v=xml_value(begin_x + x_delta), keep_formula=True)`, and likewise `PinX`, `BeginY` and `PinY`. Read each value once, into a local.

- [ ] **Step 5: Rewrite `test_copy_and_move_line`'s body to use `set_start_and_finish`**

In `tests/test_page.py`, `test_copy_and_move_line`:
- Replace everything from `cp1.begin_x, cp1.begin_y = start` to the end of the formula re-evaluation loop with `cp1.set_start_and_finish(start, finish)`. Keep the lines before it, the save, and every assertion.
- Delete the `is_connector` line only if nothing after the save reads it. The assertions do, so keep it.
- Update the docstring. The test hand-wrote the derived cells and relied on their formulas surviving; `set_start_and_finish` is how a 1-D shape is placed by its ends, and it keeps them.

- [ ] **Step 6: Run the tests and the full suite**

Run: `uv run --no-sync python -m pytest tests/test_cell_writer_primitive.py tests/test_page.py tests/test_swimlanes.py tests/test_connector_engine.py tests/test_create_shape.py -q`
Expected: all pass.

Then run every gate in Global Constraints. The import-graph test must stay green: `pages` no longer imports anything new.

- [ ] **Step 7: Commit**

Commit with the message `fix!: one writer for every named cell; a section cell the shape lacks is refused (#319)`.

### Task 4: `text_color` lands, and the pinned stale formula is inverted

**Files:**
- Modify: `src/vsdxkit/shapes.py` (the `text_color` setter, `:1550-1561`)
- Modify: `tests/test_optional_element_setters.py:93-107`

- [ ] **Step 1: Invert the pinned test**

In `test_text_color_updates_the_existing_cell_in_place`:
- replace the last comment and assertion with the lines below;
- the docstring gains: "Its formula goes, so the colour is the one Visio shows (#300)."

```python
    # the formula that produced the old colour goes, as typing a colour into
    # the ShapeSheet does in Visio; left in place, Visio recomputes over the
    # write (#300)
    assert colour_cells(shape)[0].attrib.get("F") is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run --no-sync python -m pytest tests/test_optional_element_setters.py -q -k existing_cell_in_place`
Expected: FAIL, `assert 'THEMEGUARD(RGB(255,0,0))' is None`.

- [ ] **Step 3: Drop the formula in the setter**

The setter's last line, `cell.attrib["V"] = text`, becomes the two lines below. The getter's docstring gains a paragraph: "Setting it writes the colour and removes the cell's formula, as :attr:`line_color` does."

```python
        cell.attrib["V"] = text
        cell.attrib.pop("F", None)  # the value is the one Visio shows (#300)
```

- [ ] **Step 4: Run the file**

Run: `uv run --no-sync python -m pytest tests/test_optional_element_setters.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

Commit with the message `fix: text_color replaces the colour's formula, as line_color does (#300)`.

### Task 5: A coordinate written to a glued end frees that end; the engine's own placement keeps its glue

**Files:**
- Modify: `src/vsdxkit/_connectors.py`:
  - add `_float_end`, and rewrite `_float_ends` (`:395-405`);
  - the `_ConnectorPage._remove_connect_records` protocol member (`:77-79`);
  - the `_ConnectorShape.set_start_and_finish` protocol member (`:134-138`);
  - `_glue_connector` (`:312-314`).
- Modify: `src/vsdxkit/pages.py`: `Page._remove_connect_records` (`:957-975`).
- Modify: `src/vsdxkit/shapes.py`:
  - the `begin_x`, `begin_y`, `end_x` and `end_y` setters and their docstrings (`:1640-1695`);
  - `set_start_and_finish` (`:1850-1894`), split into itself and `_place_ends`;
  - the import from `vsdxkit._connectors`.
- Test: `tests/test_glued_end_writes.py` (new)

**Interfaces:**
- Consumes: `Shape._write_cell(..., keep_formula=...)` (Task 3), and `Geometry._set_point` (Task 2).
- Produces:
  - `vsdxkit._connectors._float_end(connector: _ConnectorShape, *, begin: bool) -> None`
  - `Page._remove_connect_records(self, connector_ids, *, match: str = "from", from_cell: str | None = None) -> None`
  - `Shape._place_ends(self, start: tuple[float | None, float | None], finish: tuple[float | None, float | None], *, keep_glue: bool) -> None`
  - the `_ConnectorShape._place_ends` protocol member, with the same signature.

- [ ] **Step 1: Write the failing tests**

```python
"""A coordinate written to a glued connector end frees that end, as dragging it away does in Visio.

The value wins over the glue formula. A Connect record left naming the end
would have Visio pull it back on open, so the record and the end's trigger go
with the formula, and only that end's.
"""

import pytest

from vsdxkit.document import Document


@pytest.fixture
def glued(vsdx_copy):
    """test4 page 1: connector 6, its begin glued to shape 1 and its end to shape 2."""
    page = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0]
    connector = page.shapes.by_id("6")
    assert (connector.source.ID, connector.target.ID) == ("1", "2")
    return connector


def _records(connector) -> set[tuple[str, str | None]]:
    return {(record.from_id, record.from_rel) for record in connector._page._connects() if record.from_id == connector.ID}


def test_writing_begin_x_frees_the_begin_and_keeps_the_end_glued(glued):
    glued.begin_x = 1.0

    assert glued.source is None
    assert glued.target is not None and glued.target.ID == "2"
    assert _records(glued) == {("6", "EndX")}
    assert (glued.cells["BeginX"].value, glued.cells["BeginX"].formula) == ("1.0", None)
    assert glued.cells["EndX"].formula is not None
    assert "BegTrigger" not in glued.cells


def test_writing_end_y_frees_the_end(glued):
    glued.end_y = 3.0

    assert glued.source is not None
    assert glued.target is None
    assert _records(glued) == {("6", "BeginX")}


def test_set_start_and_finish_frees_both_ends(glued):
    glued.set_start_and_finish((1.0, 1.0), (2.0, 2.0))

    assert (glued.source, glued.target) == (None, None)
    assert _records(glued) == set()


def test_connect_still_glues_both_ends(vsdx_copy):
    """The engine places the ends it glues through `_place_ends`, which keeps its glue."""
    page = Document.open(vsdx_copy("test8_simple_connector.vsdx")).pages[0]
    source, target = page.shapes.by_text("Shape A"), page.shapes.by_text("Shape B")

    connector = page.connect(source, target)

    assert (connector.source, connector.target) == (source, target)


def test_retarget_still_glues(glued):
    page = glued._page
    other = page.shapes.by_id("5")

    glued.retarget(target=other)

    assert (glued.source.ID, glued.target.ID) == ("1", "5")


def test_a_diagonal_plain_line_keeps_its_length_formula(vsdx_copy):
    """test9 'Line A' is a plain line: its Width is a formula of its ends, which set_start_and_finish keeps."""
    line = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Line A")
    width_formula = line.cell_formula("Width")

    line.set_start_and_finish((2.0, 7.0), (3.0, 8.0))

    assert line.cell_formula("Width") == width_formula
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --no-sync python -m pytest tests/test_glued_end_writes.py -q`
Expected:
- the first three fail: the ends stay glued, and `source` is still shape 1;
- `test_connect_still_glues_both_ends`, `test_retarget_still_glues` and `test_a_diagonal_plain_line_keeps_its_length_formula` pass. They are guards for Steps 3–5.

- [ ] **Step 3: Remove one end's records, and float one end**

In `pages.py`, `_remove_connect_records` gains `from_cell: str | None = None`. When it is given, only records whose `FromCell` equals it are removed. The docstring says so, and the loop condition gains `and (from_cell is None or connect.attrib.get("FromCell") == from_cell)`. Mirror the keyword on the `_ConnectorPage` protocol member in `_connectors.py`.

In `_connectors.py`:

```python
_END_CELLS = {True: frozenset({"BegTrigger", "BeginX", "BeginY"}), False: frozenset({"EndTrigger", "EndX", "EndY"})}
"""The cells that say how one end is glued, by whether it is the begin end: its trigger and its two coordinates."""


def _float_end(connector: _ConnectorShape, *, begin: bool) -> None:
    """Leave one end of a 1-D shape unglued: its trigger inherits, its coordinates keep their values without their formulas, and its record goes.

    The other end, and the cells that say what kind of connector it is, are
    left as they are, as dragging one end away in Visio leaves them.
    """
    for change in glue_cells(None, None):
        if change.name in _END_CELLS[begin]:
            _change_cell(connector, change)
    connector._page._remove_connect_records({_id(connector)}, from_cell="BeginX" if begin else "EndX")


def _float_ends(connector: _ConnectorShape) -> None:
    """Leave both of a 1-D shape's ends unglued: the cells a floating end has, and no records.

    A copy of a glued connector keeps glue formulas naming the shapes the
    original is glued to, but none of its records, and Visio would pull it
    back to them.
    """
    _float_end(connector, begin=True)
    _float_end(connector, begin=False)
    # point glue before 1.0 wrote its begin trigger here; Visio has no such cell
    _change_cell(connector, CellInherit("BeginTrigger"))
    connector._page._remove_connect_records({_id(connector)})
```

- [ ] **Step 4: The end setters free a glued end first**

In `shapes.py`, import `_float_end` from `vsdxkit._connectors` beside `_glued_ends`. Each of the four setters becomes a call to one helper:

```python
    @begin_x.setter
    def begin_x(self, value: float | str) -> None:
        self._write_end("BeginX", value)

    def _write_end(self, name: str, value: float | str) -> None:
        """Write end coordinate `name`, freeing that end first if it is glued, as dragging a glued end away does in Visio."""
        self._require_attached(f"writing shape cell {name!r}")
        begin = name.startswith("Begin")
        end_cell = "BeginX" if begin else "EndX"
        if any(record.from_id == self.ID and record.from_rel == end_cell for record in self._page._connects()):
            _float_end(self, begin=begin)
        self.set_cell_value(name, _coordinate_value(value))
```

Two docstrings change:
- `begin_x`'s "Setting it writes the cell's value, as :attr:`x` does; the glue is left as it was." becomes: "Setting it writes the cell's value, as :attr:`x` does. A glued begin end is freed first: its ``Connect`` record, trigger and glue formulas go, as dragging the end away does in Visio. The other end stays glued."
- The other three say "as :attr:`begin_x` does, for its end".

If pyrefly rejects `Shape` as a `_ConnectorShape` at the `_float_end(self, ...)` call, check which protocol member it names, and add that member. `_glue_connector` already passes `Connector` objects as `_ConnectorShape`. Do not cast.

- [ ] **Step 5: Split `set_start_and_finish` into the user's form and the engine's**

```python
    def set_start_and_finish(
        self, start: tuple[float | None, float | None], finish: tuple[float | None, float | None]
    ) -> None:
        """Place a line or connector by its two ends, and draw it between them.

        Writing an end frees it if it is glued, as dragging it away does in
        Visio; :meth:`Connector.retarget` glues an end to another shape. The
        pin, width and height follow the ends: where they are formulas of the
        ends, the formulas stay, and their values are refreshed.

        :raises InvalidOperationError: if the shape is detached, or a coordinate is ``None``
        """
        # nothing at all is written on a shape with no BeginX, so leaving this
        # to the coordinate setters below would make the refusal depend on the
        # shape it was asked of
        self._require_attached("Shape.set_start_and_finish()")
        self._place_ends(start, finish, keep_glue=False)

    def _place_ends(
        self, start: tuple[float | None, float | None], finish: tuple[float | None, float | None], *, keep_glue: bool
    ) -> None:
        """Place a 1-D shape by its ends: the body of :meth:`set_start_and_finish`.

        The glue engine calls it with `keep_glue`, to put the ends it has just
        glued where they render before Visio recalculates, leaving their glue
        formulas and records in place. Without it, the end setters write the
        ends, and free a glued one.
        """
```

The body is today's body from `if self.begin_x is not None:` down, with the Task 3 changes, and one more. The line `self.begin_x, self.begin_y = start_x, start_y` and the one for the end become:

```python
            if keep_glue:
                for name, value in (("BeginX", start_x), ("BeginY", start_y), ("EndX", finish_x), ("EndY", finish_y)):
                    self._write_cell(name, v=xml_value(value), keep_formula=True)
            else:
                self.begin_x, self.begin_y = start_x, start_y
                self.end_x, self.end_y = finish_x, finish_y
```

In `_connectors.py`:
- the `_ConnectorShape` protocol member `set_start_and_finish` becomes `_place_ends`, with the same signature and docstring "Place the connector's ends; the engine passes `keep_glue`, so the glue it has just written stays";
- `_glue_connector`'s last line becomes `connector._place_ends(start, finish, keep_glue=True)`.

- [ ] **Step 6: Run the new tests, the connector suites and the full suite**

Run: `uv run --no-sync python -m pytest tests/test_glued_end_writes.py tests/test_connector_engine.py tests/test_connector.py tests/test_reanchor.py tests/test_connector_atomicity.py tests/test_create_shape.py -q`
Expected: all pass.

Then run every gate in Global Constraints. `tests/test_shape_coordinates.py::test_connector_coordinates_reject_none_before_mutation` must still pass: the `None` check comes before any write.

- [ ] **Step 7: Commit**

Commit with the message `fix!: a coordinate written to a glued end frees that end; the engine's own placement keeps its glue (#300)`.

### Task 6: The Visio-check script, the guide and the docstrings for 8a

**Files:**
- Create: `tools/writes_land_cases.py`
- Create: `tests/test_writes_land_cases_tool.py`
- Modify: `docs/migration-1.0.rst` (a new section)
- Modify: the docstrings of `x`, `line_weight`, `line_color` and `fill_color`, and of every setter whose docstring says "keeps a formula the cell has" or "as :attr:`x` does" (`grep -n "formula the cell has\|leaves the formula" src/vsdxkit`)

**Interfaces:**
- Produces:
  - `tools/writes_land_cases.py` with `main(argv: list[str] | None = None) -> int` and `CASES: tuple[Callable[[Path], str], ...]`. Each case writes one `.vsdx` into the folder and returns one line saying what Visio must show.
  - Task 11 appends cases 4–6.

- [ ] **Step 1: Write the failing tool test**

```python
"""The writes-land Visio-check cases build, and each file opens again."""

import importlib.util
import sys
from pathlib import Path

from vsdxkit.document import Document

TOOL = Path(__file__).resolve().parent.parent / "tools" / "writes_land_cases.py"


def _tool():
    spec = importlib.util.spec_from_file_location("writes_land_cases", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules["writes_land_cases"] = module
    spec.loader.exec_module(module)
    return module


def test_every_case_writes_a_file_that_opens(tmp_path):
    tool = _tool()

    assert tool.main([str(tmp_path)]) == 0

    files = sorted(tmp_path.glob("*.vsdx"))
    assert len(files) == len(tool.CASES)
    for path in files:
        Document.open(path)
    expected = (tmp_path / "EXPECTED.txt").read_text(encoding="utf-8").splitlines()
    assert len(expected) == len(tool.CASES)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run --no-sync python -m pytest tests/test_writes_land_cases_tool.py -q`
Expected: FAIL, because the tool file does not exist.

- [ ] **Step 3: Write the tool**

The spec said each case records what it expects in the file's `Title`. There is no public writer for core properties, so the expectations go in `EXPECTED.txt` beside the files. This plan amends the spec there.

```python
"""Write the files the Visio harness checks the writes-land package against (#300, #319, #430).

Usage: python tools/writes_land_cases.py <out-dir>

Each case is one ``.vsdx`` in <out-dir>, and ``EXPECTED.txt`` there says, one
line per case, what Visio must show. On Windows with desktop Visio, run
``python tools/visio_verify.py check <out-dir>/<case>.vsdx`` for each file, and
open the ones whose line names something to look at. The package is not
merged until every check agrees (CONTRIBUTING, "When a change needs Visio").
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from vsdxkit.document import Document

_TESTS = Path(__file__).resolve().parent.parent / "tests"
"""The fixtures the cases start from."""


def _copy(fixture: str, out: Path, case: str) -> tuple[Document, Path]:
    """`fixture` copied into `out` as `case`.vsdx, and opened."""
    target = out / f"{case}.vsdx"
    shutil.copy(_TESTS / fixture, target)
    return Document.open(target), target


def colours(out: Path) -> str:
    """Case 1: colours set on a master instance whose master's cells are theme formulas."""
    document, path = _copy("fixtures/com_reference/s05_swimlanes_cfflow.vsdx", out, "01_colours")
    shape = document.pages[0].shapes.require_id("35")
    shape.line_color = "#FF0000"
    shape.fill_color = "#00FF00"
    shape.text_color = "#0000FF"
    document.save(path)
    return "01_colours: shape 35 has a red line, a green fill and blue text"


def guarded(out: Path) -> str:
    """Case 2: a position and a size written over GUARD formulas."""
    document, path = _copy("test1.vsdx", out, "02_guarded")
    shape = document.pages[0].shapes.require_id("1")
    shape.set_cell_formula("Width", "GUARD(1)")
    shape.set_cell_formula("PinX", "GUARD(1)")
    shape.width = 2.5
    shape.x = 3.0
    document.save(path)
    return "02_guarded: shape 1 is 2.5 in wide with its pin at x = 3.0 in"


def glued_end(out: Path) -> str:
    """Case 3: one end of a connector glued at both ends, written to."""
    document, path = _copy("test4_connectors.vsdx", out, "03_glued_end")
    connector = document.pages[0].shapes.require_id("6")
    connector.begin_x = (connector.begin_x or 0.0) - 1.0
    document.save(path)
    return "03_glued_end: connector 6's begin is free, 1 in left of where it was; its end is still glued to shape 2"


CASES: tuple[Callable[[Path], str], ...] = (colours, guarded, glued_end)
"""Every case, in the order its file is numbered."""


def main(argv: list[str] | None = None) -> int:
    """Write every case into the folder named by the one argument; 2 for a usage error."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    lines = [case(out) for case in CASES]
    (out / "EXPECTED.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

If `shapes.require_id` or `Document.save(path)` is spelled differently, use the spelling the tests use (`grep -n "require_id\|\.save(" tests/test_shape.py`).

- [ ] **Step 4: Run the tool test**

Run: `uv run --no-sync python -m pytest tests/test_writes_land_cases_tool.py -q`
Expected: PASS.

- [ ] **Step 5: The migration guide and the docstrings**

Add a section to `docs/migration-1.0.rst`, after "A connector is a shape" and before "The ``<Connect>`` records are internal". Use the guide's own form: a heading underlined with `-`, then definition-list entries.

```rst
A value written is the value Visio shows
----------------------------------------

Setting a cell's value, through a setter such as ``shape.line_color`` or ``shape.x``, ``shape.set_cell_value``, ``shape.get_or_create_cell(name, v=...)``, ``cell.value`` or a geometry cell's ``value``
   Replaces the cell's formula, as typing a number into the ShapeSheet does
   in Visio, including a ``GUARD`` or theme formula and one the shape inherits
   from its master. 0.8 kept the formula, and Visio recalculated it over the
   value on open, so a colour or position written to a themed or guarded
   shape did not show. ``shape.set_cell_formula`` sets a formula.

``shape.text_color``
   Replaces the colour cell's formula, as the other colour setters do.

``shape.set_cell_value("Control/TextPosition/X", ...)`` and other names holding ``/``
   Write the cell in its section row where the shape has it, and raise
   :class:`vsdxkit.errors.InvalidOperationError` where it does not. 0.8
   created a top-level cell of that name, which is no ShapeSheet cell.

Writing an end of a glued connector: ``begin_x``, ``begin_y``, ``end_x``, ``end_y``, ``set_start_and_finish``
   Frees that end first: its ``Connect`` record, trigger and glue formulas
   go, and ``connector.source`` or ``connector.target`` reads ``None``, as
   dragging a glued end away does in Visio. The other end stays glued.
   ``connector.retarget`` glues an end to another shape. 0.8 wrote the
   coordinate beside the glue, and Visio pulled the end back on open.
```

Then change each docstring that promises the old rule. `x`'s "and keeps a formula the cell has" becomes "and replaces a formula the cell has, as typing a number into the ShapeSheet does in Visio". Do the same in `line_weight`, `line_color`, `fill_color` and each setter that says it. `grep -rn "formula the cell has\|leaves the formula" src/vsdxkit` must print nothing afterwards.

- [ ] **Step 6: The full gates, and the sweeps (controller)**

Run every gate in Global Constraints. The controller then runs the save sweep and the render sweep against `main`.
- **Expected save sweep:** 28 of 28 `same`, except connect cases that lose stray top-level `Control/TextPosition/XDyn`/`YDyn` cells, or gain `DynX`/`DynY` values. Each such difference is named in the PR.
- **Expected render sweep:** 10 of 10 `same`.

- [ ] **Step 7: Commit**

Commit with the message `docs: the value-wins rule in the guide and the docstrings; the Visio-check cases (#300, #319)`.

---

## PR 8b: writes stay on the instance (#273, #435, #432, #434, #438)

Branch `fix/writes-land-b-instance`, stacked on `fix/writes-land-a-writer`.

### Task 7: The row setters and `set_attribute` copy an inherited row down first

**Files:**
- Modify: `src/vsdxkit/geometry.py`: `GeometryRow.row_type`, `index` and `del_bool`, and their docstrings (`:345-438`)
- Modify: `src/vsdxkit/shapes.py`: `DataProperty.set_attribute` (`:694-701`)
- Test: `tests/test_inherited_writes.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
"""A write to an instance never edits its master (#273).

test9's 'Conn A' inherits MoveTo row 1 from its master, and test3's shape 7
inherits its ShapeClass property. A write to either must give the instance a
row of its own and leave the master's row, which every other instance reads,
as it was.
"""

import pytest

from vsdxkit import namespace
from vsdxkit.document import Document


@pytest.fixture
def conn_a(vsdx_copy):
    connector = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Conn A")
    assert connector.geometry.rows["1"].inherited
    return connector


def _master_row(connector, ix: str):
    section = connector.master_shape.xml.find(f'{namespace}Section[@N="Geometry"]')
    return next(row for row in section.findall(f"{namespace}Row") if row.get("IX") == ix)


def test_row_type_on_an_inherited_row_leaves_the_master_alone(conn_a):
    row = conn_a.geometry.rows["1"]

    row.row_type = "LineTo"

    assert _master_row(conn_a, "1").get("T") == "MoveTo"
    assert row.xml is not _master_row(conn_a, "1")
    assert row.xml.get("T") == "LineTo"


def test_del_bool_on_an_inherited_row_leaves_the_master_alone(conn_a):
    row = conn_a.geometry.rows["1"]

    row.del_bool = True

    assert _master_row(conn_a, "1").get("Del") is None
    assert row.xml.get("Del") == "1"


def test_clearing_del_bool_where_there_is_none_is_a_no_op(conn_a):
    row = conn_a.geometry.rows["2"]
    assert row.del_bool is None

    row.del_bool = False

    assert row.del_bool is None


def test_index_on_an_inherited_row_leaves_the_master_alone_and_refiles_the_row(conn_a):
    geometry = conn_a.geometry
    row = geometry.rows["1"]

    row.index = 7

    assert _master_row(conn_a, "1").get("IX") == "1"
    assert geometry.rows["7"] is row
    assert row.xml.get("IX") == "7"


def test_set_attribute_on_an_inherited_property_writes_the_instance_and_lands(vsdx_copy):
    """It wrote the master's cell; with make_local alone it would find no cell on the new row and return False."""
    shape = Document.open(vsdx_copy("test3_house.vsdx")).pages[0].shapes.by_id("7")
    prop = shape.data_properties["ShapeClass"]
    assert prop.inherited
    master_value = prop.xml.find(f'{namespace}Cell[@N="Value"]')

    assert prop.set_attribute("Value", "V", "Changed") is True

    assert master_value.get("V") == "Location"
    assert shape.data_properties["ShapeClass"].value == "Changed"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --no-sync python -m pytest tests/test_inherited_writes.py -q`
Expected:
- the row tests fail with the master's row changed (`assert 'LineTo' == 'MoveTo'` and the like);
- the `del_bool` no-op test fails with `KeyError: 'Del'`;
- the `set_attribute` test fails with `assert 'Changed' == 'Location'`.

- [ ] **Step 3: Copy the row down, then write**

In `geometry.py`:

```python
    @row_type.setter
    def row_type(self, value: str | int) -> None:
        self._require_attached("writing a geometry row's type")
        self.make_local()
        self.xml.attrib["T"] = str(value)

    @index.setter
    def index(self, value: str | int) -> None:
        self._require_attached("writing a geometry row's index")
        self.make_local()
        old = self.xml.attrib.get("IX")
        self.xml.attrib["IX"] = str(value)
        if old is not None and self.geometry.rows.get(old) is self:
            del self.geometry.rows[old]
        self.geometry.rows[str(value)] = self

    @del_bool.setter
    def del_bool(self, value: object) -> None:
        self._require_attached("writing a geometry row's Del flag")
        self.make_local()
        if value:
            self.xml.attrib["Del"] = "1"
        else:
            self.xml.attrib.pop("Del", None)
```

The three docstrings change:
- "so on an inherited row it changes the master's row" becomes "on a row inherited from a master, the row is copied onto this shape first, and the master keeps its own";
- `index`'s sentence about staying filed under its old key goes, because the row is refiled;
- `del_bool`'s `KeyError` sentence goes.

In `shapes.py`, `DataProperty.set_attribute`:

```python
    def set_attribute(self, name: str, attrib: str, value: str) -> bool:
        """Set attribute `attrib` of cell `name` of this property's row; ``False`` where neither the row nor its master's has that cell.

        A property inherited from a master is given a row of its own first,
        carrying a copy of the master's cell, so the master is left as it was.
        """
        self._require_attached("DataProperty.set_attribute()")
        element = self._get_element(name)
        if element is None:
            return False
        if self.inherited:
            self.make_local()
            own = self._get_element(name)
            if own is None:
                own = copy.deepcopy(element)
                self.xml.append(own)
            element = own
        element.attrib[attrib] = value
        return True
```

- [ ] **Step 4: Run the tests and the geometry and property suites**

Run: `uv run --no-sync python -m pytest tests/test_inherited_writes.py tests/test_geometry.py tests/test_data_property_reads.py tests/test_shape.py -q`
Expected: all pass. A test that asserted the master changed, or that `KeyError` is raised, is asserting #273's bug: invert it, and say so in the report.

- [ ] **Step 5: Commit**

Commit with the message `fix: a row's type, index and Del flag, and a property's attributes, are written on the instance (#273)`.

### Task 8: The formula cache skips cells the shape only inherits

**Files:**
- Modify: `src/vsdxkit/shapes.py`: `_refresh_formula_values` (`:1896-1917`)
- Test: `tests/test_inherited_writes.py` (append)

- [ ] **Step 1: Write the failing test** (append)

test9's master row 1 `X` is `{N: X, V: 0}` with no formula; the test gives it `Width*1`, a formula `vsdxkit._formulae` evaluates.

```python
def test_the_formula_cache_leaves_an_inherited_geometry_cell_alone(vsdx_copy):
    """#273 part 3: the refresh wrote the value it computed into the master's cell, which every other instance reads."""
    connector = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Conn A")
    master_x = _master_row(connector, "1").find(f'{namespace}Cell[@N="X"]')
    master_x.set("F", "Width*1")
    master_x.set("V", "0")

    connector._refresh_formula_values()

    assert master_x.get("V") == "0"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run --no-sync python -m pytest tests/test_inherited_writes.py -q -k formula_cache`
Expected: FAIL, with `assert '3.543307044802283' == '0'` or the connector's width.

- [ ] **Step 3: Skip what the shape does not own**

In `_refresh_formula_values`:
- after building `cells`, add `own = set(self.xml.iter(f"{namespace}Cell"))`;
- the loop's first line becomes `if c.xml not in own: continue`, with the comment `# a cell only inherited is the master's; Visio recomputes it for this instance on open`;
- the docstring gains: "A cell the shape only inherits is left alone: it is the master's, and Visio recomputes it for this shape on open."

- [ ] **Step 4: Run the test and the full suite**

Run: `uv run --no-sync python -m pytest tests/test_inherited_writes.py tests/test_page.py tests/test_connector_engine.py -q`, then every gate.
Expected: all pass.

- [ ] **Step 5: Commit**

Commit with the message `fix: the formula cache leaves a cell the shape only inherits to its master (#273)`.

### Task 9: `DataProperty` reads its row each time; a property with no value matches nothing

**Files:**
- Modify: `src/vsdxkit/shapes.py`:
  - `DataProperty`'s class attributes and `__init__` (`:527-587`);
  - `_has_property` (`:2306-2313`).
- Test: `tests/test_data_property_reads.py` (append)

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_a_label_set_through_set_attribute_is_read_back(vsdx_copy):
    """#435: label was read once, in __init__, so the class's own set_attribute left it stale."""
    shape = Document.open(vsdx_copy("test1.vsdx")).pages[0].shapes.require_id("1")
    prop = shape.data_properties["my_property_label"]

    prop.set_attribute("Label", "V", "renamed")

    assert prop.label == "renamed"


def test_a_property_with_no_value_does_not_match_the_text_none(vsdx_copy):
    """#432: a property with no value read as the text "None", so it matched a search for that string."""
    page = Document.open(vsdx_copy("test1.vsdx")).pages[0]
    shape = page.shapes.require_id("1")
    prop = shape.data_properties["my_property_label"]
    prop.xml.remove(prop.xml.find(f'{namespace}Cell[@N="Value"]'))
    assert shape.data_properties["my_property_label"].value is None

    assert page.shapes.matching_property("my_property_label", "None") == ()
```

Add `from vsdxkit import namespace` and `from vsdxkit.document import Document` to the file's imports if they are not there.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --no-sync python -m pytest tests/test_data_property_reads.py -q`
Expected:
- the label test fails with `assert 'my_property_label' == 'renamed'`;
- the `None` test fails with a one-shape tuple.

- [ ] **Step 3: Four live properties**

Remove the class-level annotations and docstrings for `value_type`, `label`, `prompt` and `sort_key`, and every line of `__init__` that sets them. `__init__` keeps `self.shape`, `self.xml` and `self.name`. Add:

```python
    @property
    def label(self) -> str | None:
        """The label Visio shows the property under, which :attr:`Shape.data_properties` keys by; ``None`` where there is none.

        It is read from the row on every access, as are :attr:`value_type`,
        :attr:`prompt` and :attr:`sort_key`. A row with no ``Label`` cell, which
        is how an override of a master's property is written, takes all four
        from the master's property of the same name, and gives ``None`` where
        the master has none.
        """
        return self._field("Label")

    @property
    def value_type(self) -> str | None:
        """The ``Type`` cell's value, as Visio numbers property types (``"0"`` text, ``"2"`` number, ``"5"`` date, and so on); ``None`` where there is none."""
        return self._field("Type")

    @property
    def prompt(self) -> str | None:
        """The ``Prompt`` cell's value, the description Visio gives the property; ``None`` where there is none."""
        return self._field("Prompt")

    @property
    def sort_key(self) -> str | None:
        """The ``SortKey`` cell's value, which orders the properties in Visio's Shape Data window; ``None`` where there is none."""
        return self._field("SortKey")

    def _field(self, cell: str) -> str | None:
        """Cell `cell`'s value from this row, or from the master's property of the same name where this row is an override with no ``Label``."""
        if self.xml.find(f'{namespace}Cell[@N="Label"]') is None:
            master = self._master_property()
            return None if master is None else master._field(cell)
        element = self.xml.find(f'{namespace}Cell[@N="{cell}"]')
        return None if element is None else element.attrib.get("V")

    def _master_property(self) -> DataProperty | None:
        """The property of this one's name on the master shape, or ``None``."""
        master_shape = self.shape.master_shape
        if master_shape is None:
            return None
        return next((prop for prop in master_shape.data_properties.values() if prop.name == self.name), None)
```

In `_has_property`:
- the last line becomes `return found is not None and (value is None or found.value == value)`;
- the docstring's second paragraph becomes "A property with no value matches no `value`."

- [ ] **Step 4: Run the property and finder suites, and the full gates**

Run: `uv run --no-sync python -m pytest tests/test_data_property_reads.py tests/test_shape.py tests/test_shape_collection.py -q`, then every gate.
Expected: all pass. The docstring gate must still count every definition.

- [ ] **Step 5: Commit**

Commit with the message `fix: a property's label, type, prompt and sort key read the row each time; no value matches no text (#435, #432)`.

### Task 10: A deleted shape stays deleted

**Files:**
- Modify: `src/vsdxkit/shapes.py`:
  - the `master_page_ID` setter (`:957-967`);
  - the `is_attached` docstring (`:839-842`);
  - `append_shape` and its docstring (`:2024-2089`).
- Modify: `docs/migration-1.0.rst`, the new section from Task 6
- Test: `tests/test_shape_identity.py` (append)

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_a_deleted_shape_refuses_master_page_ID(vsdx_copy):
    """#434: the one write the detached-shape guard forgot."""
    shape = Document.open(vsdx_copy("test3_house.vsdx")).pages[0].shapes.by_id("7")
    master = shape.xml.get("Master")
    shape.delete()

    with pytest.raises(InvalidOperationError):
        shape.master_page_ID = "99"

    assert shape.xml.get("Master") == master


def test_append_shape_refuses_a_deleted_shape(vsdx_copy):
    """#438: a shape deleted from the same page took the 'new to the page' branch and was attached again."""
    page = Document.open(vsdx_copy("test10_nested_shapes.vsdx")).pages[0]
    group = page.shapes.require_id("7")
    victim = page.shapes.require_id("8")
    victim.delete()

    with pytest.raises(InvalidOperationError, match="deleted"):
        group.append_shape(victim)

    assert not victim.is_attached
    assert all(child.ID != "8" for child in group.children)
```

Add `import pytest`, `from vsdxkit.document import Document` and `from vsdxkit.errors import InvalidOperationError` if the file lacks them.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --no-sync python -m pytest tests/test_shape_identity.py -q`
Expected: both FAIL with `DID NOT RAISE`.

- [ ] **Step 3: Guard both writes**

`master_page_ID`'s setter first calls `self._require_attached("writing a shape's master_page_ID")`. Its docstring gains ":raises InvalidOperationError: if the shape is detached". `is_attached`'s docstring loses ", as does every write but one: the ``master_page_ID`` setter is not guarded, and writes to the detached element" and ends ", as does every write."

In `append_shape`, directly after `self._require_attached("Shape.append_shape()")`:

```python
        if not append_shape.is_attached:
            raise InvalidOperationError(
                f"shape ID={append_shape.ID} was deleted, or is on a removed page, so it cannot be placed; "
                "a deleted shape stays deleted"
            )
```

The docstring's sentence "A shape whose element is not on the page, such as one built by hand or one deleted from this page, is placed, with IDs the page is not using." goes. The `:raises:` line gains "if ``append_shape`` is detached".

Run `uv run --no-sync python -m pytest tests/test_shape.py tests/test_back_references.py tests/test_shape_id_single_store.py tests/test_errors.py -q`. A test that appends a shape built by hand (`Shape(xml=...)`) now fails. Change it to append a `copy()` of a shape on the page. `Shape` is reached through a document, never constructed (spec ruling). Name each change in the report.

- [ ] **Step 4: The guide**

Add to the section Task 6 made:

```rst
``group.append_shape(deleted_shape)``
   Raises :class:`vsdxkit.errors.InvalidOperationError`. 0.8 placed a shape
   deleted from the same page back inside the group, without the ``Connect``
   records its deletion removed.

``shape.master_page_ID = ...`` on a deleted shape
   Raises :class:`vsdxkit.errors.InvalidOperationError`, as every other write
   to a deleted shape does.

Writes to a geometry row's ``row_type``, ``index`` or ``del_bool``, and ``DataProperty.set_attribute``
   On a row or property the shape inherits from its master, copy it onto the
   shape first, as the ``x`` and ``y`` setters and ``DataProperty.value``
   already did. 0.8 wrote the master's row, and with it every instance's.
```

- [ ] **Step 5: The full gates, and the sweeps (controller)**

Every gate. The save and render sweeps against 8a's head: 28 of 28 and 10 of 10 `same`.

- [ ] **Step 6: Commit**

Commit with the message `fix!: a deleted shape refuses master_page_ID and append_shape, so delete is one-way (#434, #438)`.

---

## PR 8c: moving a shape moves the shape (#430, #301, the 1-D text pin)

Branch `fix/writes-land-c-move`, stacked on `fix/writes-land-b-instance`.

### Task 11: `move` moves the pin or the ends, never the geometry

**Files:**
- Modify: `src/vsdxkit/shapes.py`: `move` (`:1697-1714`)
- Modify: `tests/test_geometry.py:283` and `:302`: `connector.move(` becomes `connector.geometry.move(`. Those tests are about `Geometry.move`'s copy-down.
- Test: `tests/test_move.py` (new)

- [ ] **Step 1: Point the geometry tests at `Geometry.move`, and write the failing tests**

Make the two `test_geometry.py` edits. Their docstrings already name `Geometry.move()`. Then:

```python
"""Moving a shape moves the shape (#430).

The geometry's rows are in the shape's own coordinates, so they stay put when
the shape moves. A 2-D shape moves by its pin; a 1-D shape by its two ends,
from which its pin, width and angle follow.
"""

import pytest

from vsdxkit import namespace
from vsdxkit.document import Document


def _rows(shape) -> list[dict[str, str]]:
    section = shape.xml.find(f'{namespace}Section[@N="Geometry"]')
    if section is None:
        return []
    return [{cell.get("N"): cell.get("V") for cell in row.findall(f"{namespace}Cell")} for row in section.findall(f"{namespace}Row")]


def test_a_2d_shape_moves_by_its_pin_and_its_outline_stays_on_it(vsdx_copy):
    page = Document.open(vsdx_copy("test1.vsdx")).pages[0]
    shape = next(s for s in page.shapes if s.begin_x is None and s.geometry is not None and _rows(s))
    rows, x, y = _rows(shape), shape.x, shape.y

    shape.move(1.0, 2.0)

    assert (shape.x, shape.y) == pytest.approx((x + 1.0, y + 2.0))
    assert _rows(shape) == rows


def test_a_moved_pin_loses_a_formula_it_had(vsdx_copy):
    """As dragging a shape does in Visio: the pin written is the pin shown."""
    shape = Document.open(vsdx_copy("test1.vsdx")).pages[0].shapes.require_id("1")
    shape.set_cell_formula("PinX", "GUARD(1)")

    shape.move(1.0, 0.0)

    assert shape.cells["PinX"].formula is None


def test_a_1d_shape_moves_both_ends_and_keeps_its_geometry(vsdx_copy):
    """#430: move shifted the begin and the geometry rows and left the end behind."""
    connector = Document.open(vsdx_copy("test9_rect_and_line.vsdx")).pages[0].shapes.by_text("Conn A")
    begin, end, rows = (connector.begin_x, connector.begin_y), (connector.end_x, connector.end_y), _rows(connector)

    connector.move(1.0, 2.0)

    assert (connector.begin_x, connector.begin_y) == pytest.approx((begin[0] + 1.0, begin[1] + 2.0))
    assert (connector.end_x, connector.end_y) == pytest.approx((end[0] + 1.0, end[1] + 2.0))
    assert _rows(connector) == rows
    assert (connector.x, connector.y) == pytest.approx(((begin[0] + end[0]) / 2 + 1.0, (begin[1] + end[1]) / 2 + 2.0))


def test_moving_a_glued_connector_frees_both_ends(vsdx_copy):
    """As dragging a glued connector's body does in Visio."""
    connector = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0].shapes.by_id("6")

    connector.move(0.5, 0.5)

    assert (connector.source, connector.target) == (None, None)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --no-sync python -m pytest tests/test_move.py -q`
Expected:
- the outline test and the 1-D test fail on the rows, and on the end not moving;
- the pin-formula test fails with `'GUARD(1)'`;
- the glued test fails because the ends stay glued.

- [ ] **Step 3: The new `move`**

```python
    def move(self, x_delta: float, y_delta: float) -> None:
        """Move the shape by ``x_delta`` and ``y_delta`` inches.

        A 2-D shape moves by its pin, and the value written replaces a
        formula the pin had, as dragging the shape does in Visio. A pin the
        shape lacks is taken as 0, and written. A 1-D shape moves by its two
        ends, which frees an end that was glued; its pin, width and angle are
        formulas of its ends, and follow them. The geometry is in the shape's
        own coordinates, so it is not touched.

        :raises InvalidOperationError: if the shape is detached
        """
        begin_x, begin_y, end_x, end_y = self.begin_x, self.begin_y, self.end_x, self.end_y
        if begin_x is None or begin_y is None or end_x is None or end_y is None:
            self.x = (self.x or 0.0) + x_delta
            self.y = (self.y or 0.0) + y_delta
            return
        self.begin_x, self.begin_y = begin_x + x_delta, begin_y + y_delta
        self.end_x, self.end_y = end_x + x_delta, end_y + y_delta
        # derived from the ends: written as the library writes them, so a
        # formula stays and the refresh below gives it the new ends' value
        self._write_cell("PinX", v=xml_value((self.x or 0.0) + x_delta), keep_formula=True)
        self._write_cell("PinY", v=xml_value((self.y or 0.0) + y_delta), keep_formula=True)
        self._refresh_formula_values()
```

- [ ] **Step 4: Run the move tests, the geometry, shape and templating suites, and the full gates**

Run: `uv run --no-sync python -m pytest tests/test_move.py tests/test_geometry.py tests/test_shape.py tests/test_jinja.py tests/test_jinja_nested_loop.py tests/test_render_document.py -q`, then every gate.
Expected: all pass. A templating test that asserts a loop copy's geometry rows were shifted is asserting #430's bug: invert it, and say so in the report.

- [ ] **Step 5: Commit**

Commit with the message `fix!: move shifts the pin, or a 1-D shape's two ends, and never the geometry (#430)`.

### Task 12: A 1-D shape's text pin is local; `set_start_and_finish` refuses a 2-D shape; Visio cases 4–6

**Files:**
- Modify: `src/vsdxkit/shapes.py`: `_place_ends` (from Task 5)
- Modify: `tools/writes_land_cases.py` (three cases)
- Modify: `docs/migration-1.0.rst`, the section from Task 6
- Test: `tests/test_glued_end_writes.py` (append)

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_a_plain_lines_text_pin_is_in_its_own_coordinates(vsdx_copy):
    """test5_master shape 5 is a Lucidchart line, not named 'Dynamic connector': its text pin was set in the page's coordinates."""
    line = Document.open(vsdx_copy("test5_master.vsdx")).pages[0].shapes.by_id("5")

    line.set_start_and_finish((1.0, 7.5), (3.0, 7.5))

    assert float(line.cells["TxtPinX"].value) == pytest.approx(1.0)
    assert float(line.cells["TxtPinY"].value) == pytest.approx(0.0)
    assert float(line.cells["Control/TextPosition/X"].value) == pytest.approx(1.0)


def test_set_start_and_finish_refuses_a_2d_shape(vsdx_copy):
    """#301: it did nothing, silently, on a shape with no ends."""
    shape = Document.open(vsdx_copy("test1.vsdx")).pages[0].shapes.require_id("1")
    before = shape.x

    with pytest.raises(InvalidOperationError, match="2-D"):
        shape.set_start_and_finish((1.0, 1.0), (2.0, 2.0))

    assert shape.x == before
```

Add `from vsdxkit.errors import InvalidOperationError` to the file's imports.

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run --no-sync python -m pytest tests/test_glued_end_writes.py -q -k "text_pin or 2d"`
Expected:
- the text-pin test fails with the page-coordinate value (about 2.0), not 1.0;
- the 2-D test fails with `DID NOT RAISE`.

- [ ] **Step 3: The text pin and the refusal**

In `_place_ends`:
- the `if self.begin_x is not None:` block's condition is inverted into an early refusal:

  ```python
          if self.begin_x is None:
              raise InvalidOperationError(
                  f"shape ID {self.ID} is 2-D, so it has no start and finish; move it with move(), or x and y"
              )
  ```

  The body below it is dedented one level.
- The text-pin branch becomes `text_x, text_y = width / 2, height / 2` for every 1-D shape. The `center_x_y` branch and its `InvalidOperationError` go.
- The `is_connector` line stays, because it still chooses the height. Its comment becomes: "a dynamic connector's height is its y span; a plain line's is 0, its slope carried by its geometry".
- `set_start_and_finish`'s docstring `:raises:` gains "or it is a 2-D shape".

- [ ] **Step 4: Visio cases 4–6**

Append to `tools/writes_land_cases.py`, and extend `CASES` to hold all six:

```python
def moved_instance(out: Path) -> str:
    """Case 4: a master instance with MoveTo and LineTo rows, moved."""
    document, path = _copy("test9_rect_and_line.vsdx", out, "04_moved_instance")
    document.pages[0].shapes.by_text("Conn A").move(1.0, 1.0)
    document.save(path)
    return "04_moved_instance: 'Conn A' is drawn between its two ends, 1 in right of and 1 in above where it was"


def plain_line_text(out: Path) -> str:
    """Case 5: a plain line placed by its ends; its text must sit on it."""
    document, path = _copy("test5_master.vsdx", out, "05_plain_line_text")
    document.pages[0].shapes.require_id("5").set_start_and_finish((1.0, 7.0), (3.0, 7.0))
    document.save(path)
    return "05_plain_line_text: shape 5 runs from (1, 7) to (3, 7) with its text at its middle"


def diagonals(out: Path) -> str:
    """Case 6: a connector and a plain line placed on a diagonal."""
    document, path = _copy("test9_rect_and_line.vsdx", out, "06_diagonals")
    page = document.pages[0]
    page.shapes.by_text("Conn A").set_start_and_finish((1.0, 1.0), (3.0, 2.0))
    page.shapes.by_text("Line A").set_start_and_finish((4.0, 1.0), (5.0, 3.0))
    document.save(path)
    return "06_diagonals: 'Conn A' runs from (1, 1) to (3, 2) and 'Line A' from (4, 1) to (5, 3), each drawn between its ends"
```

- [ ] **Step 5: The guide**

Add to the section:

```rst
``shape.move(dx, dy)``
   Moves a 2-D shape's pin, replacing a formula it had, and a 1-D shape's two
   ends, freeing a glued end. It never shifts the geometry's rows, which are
   in the shape's own coordinates. 0.8 shifted them, drawing the outline off
   the shape, and left a 1-D shape's end behind.

``shape.set_start_and_finish`` on a 2-D shape
   Raises :class:`vsdxkit.errors.InvalidOperationError`. 0.8 did nothing.
   On a 1-D shape, the text pin is set in the shape's own coordinates, at its
   middle, whatever the shape is called.
```

- [ ] **Step 6: Run the tests, the tool test and the full gates; the sweeps (controller)**

Run: `uv run --no-sync python -m pytest tests/test_glued_end_writes.py tests/test_writes_land_cases_tool.py tests/test_page.py -q`, then every gate.
Expected: all pass.

The controller runs the sweeps against 8b's head:
- **Save sweep:** 28 of 28 `same`, unless the workload moves a shape; each difference is named.
- **Render sweep:** the loop cases differ only in the loop copies. Their geometry rows are no longer shifted, and a moved 2-D copy's pin loses its formula. Every other case is `same`. The PR names each difference.

- [ ] **Step 7: Commit**

Commit with the message `fix!: a 1-D shape's text pin is in its own coordinates, and set_start_and_finish refuses a 2-D shape (#301)`.

---

## After 8c (controller)

1. Push the spec branch and the three PR branches.
2. Open the stack with `gh stack`: the spec PR, then 8a, 8b and 8c.
3. Put `needs-visio` on 8a, 8b and 8c.
4. Each PR body gives `python tools/writes_land_cases.py out/`, then `python tools/visio_verify.py check out/<case>.vsdx` for each of the six files, with `EXPECTED.txt`.
5. Watch CI on each pushed head, and read each head's inline comments.
6. Ask the maintainer for the Visio run. Nothing merges until every case agrees, and until the maintainer says go.
