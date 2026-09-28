# Writes land: one cell writer, the value wins, writes stay on the instance

Pre-1.0 package, on `main` at 3575873.
Issues #300, #319, #273, #435, #432, #434, #438, #430 and #301, and one bug the
triage found.

Authority:

- the maintainer's request of 2026-09-27: "Pick up the next set of fixes for us
  to package and address together prior to 1.0 release";
- the maintainer's choice of this set, "writes land", from the triage below;
- the maintainer's three decisions of the same day, recorded below.

## Goal

After this package, every write a user makes lands where Visio reads it:

- **A value written to a cell is the value Visio shows.** No formula, the
  shape's own or one copied down from its master, recalculates over it on open.
- **A write to an instance stays on the instance.** It never edits the master,
  and so never edits every other shape drawn from that master.
- **Moving a shape moves the shape.** Its outline stays on it, and a 1-D shape's
  two ends and its text move together.
- **A deleted shape stays deleted,** and every write to it is refused.

## Where things stand (main at 3575873)

Two read-only triages re-checked each issue against `main` and reproduced it.
Their notes are in the session scratchpad: `triage-a/findings.md` and
`triage-b/findings.md`.

**The formula a write keeps (#300, #319).**

- **`Shape._write_cell` (`shapes.py:1298`) writes `V` and never touches `F`.** A
  cell the shape lacks is deep-copied from the master, formula included
  (`:1324-1330`). Reproduced:
  - `line_color`, `fill_color` and `text_color` keep
    `THEMEGUARD(...)`/`THEMEVAL()` (test12 shapes 1 and 5, test3 shape 7, s05
    shape 35);
  - `begin_x` keeps `_WALKGLUE(...)` and `width` keeps `GUARD(EndX-BeginX)`
    (test4 shape 6).

  Visio recalculates `F` on open, so the value written is discarded. The library
  reads the new value back, so nothing looks wrong.
- **The rule is documented as intended.** `Cell.value` (`shapes.py:473`),
  `GeometryCell.value` (`geometry.py:499`) and the `line_weight`, `line_color`
  and `x` docstrings (`shapes.py:1403`, `:1420`, `:1587`) say the formula is
  kept. Most other setters' docstrings refer back to `x`'s.
  `test_text_color_updates_the_existing_cell_in_place`
  (`tests/test_optional_element_setters.py:93`) pins the stale `F` and points
  at #300.
- **There are three writers, not one:**
  - `_write_cell`;
  - `get_or_create_cell` (`shapes.py:1716`), which is public and named in
    `docs/migration-1.0.rst:958`. It creates a cell with no `F`, and its comment
    says #319 folds it in;
  - `text_color`'s setter, which writes `V` straight onto the Character `Color`
    cell (`shapes.py:1561`).
- **A name holding `/`**, such as `Control/TextPosition/X`, that the shape lacks
  becomes a top-level `<Cell N="Control/TextPosition/X">`, which is not a
  ShapeSheet cell. `set_start_and_finish` writes four of these
  (`shapes.py:1890-1893`).
- **`pages._drop_formula` (`pages.py:89`)** exists to undo `_write_cell`'s kept
  formula for `create_shape`.
- **Two helpers insert a row in `IX` order:** `Shape._insert_character_row`
  (`shapes.py:1497`), which does `int(IX)` on every sibling, and the row
  insertion in `GeometryRow._create_row_xml` (`geometry.py:312`).
- **The glue engine's `CellWrite` documents `None` as "leave that half of the
  cell as it is"** (`_glue.py:47-55`). The engine writes through
  `get_or_create_cell` (`_connectors.py:375`), declared on the `_ConnectorShape`
  protocol (`_connectors.py:140`).

**Writes that reach the master (#273, #435, #432).**

- `GeometryRow.row_type`, `index` and `del_bool` (`geometry.py:355-438`) write
  `self.xml` as it stands. Their docstrings say so. On an inherited row that is
  the master's row (test9 Conn A). `del_bool = False` on a row with no `Del`
  raises `KeyError`.
- `DataProperty.set_attribute` (`shapes.py:694`) writes the master's cell on an
  inherited property (test3 shape 7).
- `Shape._refresh_formula_values` (`shapes.py:1896`) writes the cached value of
  every formula cell it can evaluate. That includes the master's geometry cells
  an instance inherits. It runs from every `connect()` and `retarget()`, from
  `set_start_and_finish`, and from `create_shape(width=...)`.
- `DataProperty.label`, `value_type`, `prompt` and `sort_key` are read once, in
  `__init__` (`shapes.py:545-587`). Even `set_attribute("Label", ...)` leaves
  `label` stale.
- A property with no value matches a search for the string `"None"` (`shapes.py:2313`).

**Deleted shapes (#434, #438).**

- The `master_page_ID` setter (`shapes.py:958`) has no guard. `is_attached`'s
  docstring (`shapes.py:841`) names it as the one unguarded write.
- `append_shape` (`shapes.py:2024`) checks only that the group is attached. A
  shape deleted from the same page takes the "new to the page" branch, is
  renumbered, and is attached again (test10). The docstring (`:2036-2038`)
  describes this as intended.

**Moving (#430, #301, and a new bug).**

- `Shape.move` (`shapes.py:1697`) shifts the geometry's `MoveTo`/`LineTo` rows
  as well as the pin. Those rows are in the shape's own coordinates, so the
  outline is drawn offset from the shape.
  - In the sweep, 23 of 94 top-level fixture shapes end up with a shifted
    absolute row that has no formula.
  - On a master instance, `Geometry.move` copies the master's row down without
    its `F`.
  - A 1-D shape's end point is not moved.
  - `render` calls `move` on every loop copy (`templating.py:129`).
  - `tests/test_geometry.py:276-302` pins the current behaviour.
- **`set_start_and_finish` (`shapes.py:1850`):**
  - It does nothing, silently, on a 2-D shape (`:1858`).
  - A 1-D shape not named exactly "Dynamic connector" gets its text pin from
    `center_x_y`, which is in the parent's coordinates. On test5_master shape 5,
    a Lucidchart line, `TxtPinX` becomes 12.0 where it should be about 2.5. This
    is the new bug.
  - #301's other claim, that text is left behind on a line with no `TxtPinX`, is
    unverified: Visio's default text pin is local to the shape. It is out of
    scope, pending the Visio check.

## Decisions

### The maintainer's decisions (2026-09-27)

1. **The value wins, as in Visio.** A value written to a cell replaces the
   cell's formula with the constant, as typing a number into a ShapeSheet cell
   does in Visio. That covers `GUARD(...)` and `THEMEGUARD(...)`. Only the
   library's own formula-cache writes keep `F`. `set_cell_formula` stays the way
   to set a formula.
2. **A coordinate written to a glued connector end unglues that end first,** as
   dragging a glued end away does in Visio. The end's `Connect` record, trigger
   and glue formulas go, and the coordinate lands. The other end is untouched.
3. **The Visio check gates the merge.** The PRs carry `needs-visio`. The package
   ships the files and the `tools/visio_verify.py` commands. Nothing merges
   until the maintainer has run them on Windows and they agree.

### Rulings made from those decisions

These rulings are mine, not the maintainer's. Each follows from a decision, and
each is listed here so it can be overturned.

- **Two kinds of write, one writer.**
  - A *user's* value write removes `F`:
    - the setters;
    - `set_cell_value` and `get_or_create_cell(name, v=...)` without `f`;
    - `Cell.value`;
    - `GeometryCell.value`;
    - `text_color`.
  - A *library* write keeps `F`: the glue engine's `CellWrite`, and the
    formula-cache refresh. It goes through a private path that says so.

  `Cell.value` and `GeometryCell.value` are public, so they follow the user's
  rule: `shape.cells["PinX"].value = 3` lands as `shape.x = 3` does. The cache
  refresh stops writing through them.
- **One writer.** `Shape._write_cell(name, *, v=None, f=None,
  keep_formula=False)` is the only function that creates or updates a shape's
  named cell.
  - `v` without `f` removes `F` unless `keep_formula` is true.
  - `f` sets `F`, and sets `V` too when `v` is given.
  - `set_cell_value`, `set_cell_formula` and `get_or_create_cell` each become
    one line over it. `get_or_create_cell` stays public and returns the `Cell`.
  - The `_ConnectorShape` protocol trades `get_or_create_cell` for
    `_write_cell`. `_change_cell` calls it with `keep_formula=True`, so glue
    writes keep `CellWrite`'s documented "`None` leaves that half".
- **A name holding `/` goes to its section row.**
  - Found on the shape, it is written in place, under the same rule.
  - Not found, the write raises `InvalidOperationError` naming the section and
    row. No top-level `/` cell is ever created.
  - Materialising an inherited section row other than geometry and Shape Data is
    out of scope.
  - `set_start_and_finish` writes the `Control/TextPosition` cells only when the
    shape has that row of its own.
- **`text_color` goes through the same rule.** Its setter removes the `Color`
  cell's `F`. `_create_character_color_cell` and the geometry row insertion
  share one helper that puts a row in `IX` order. The helper reads a non-numeric
  `IX` as the end of the section, as `_create_row_xml` does, rather than
  raising.
- **`pages._drop_formula` is deleted.** `create_shape`'s pin and size writes
  drop the formula through the rule. `_detach` keeps its own removal of a
  formula naming a shape the copy has left behind. That is a library write: it
  removes a formula without writing a value.
- **Ungluing one end** is `_float_end(connector, end)` in `_connectors.py`, the
  per-end half of `_float_ends`. `_float_ends` becomes two calls to it.
  - The `begin_x`, `begin_y`, `end_x` and `end_y` setters call it before writing
    when their end has a `Connect` record.
  - `move` and `set_start_and_finish` write through those setters, so they
    unglue too. Moving a whole glued connector frees both ends, as dragging its
    body does in Visio.
- **A 1-D shape's ends are the user's write; its pin, width and height are derived.**
  - In Visio a 1-D shape's `PinX`, `PinY`, `Width`, `Height` and `Angle` are
    formulas of its ends, such as `(BeginX+EndX)/2`, `SQRT(...)` and
    `GUARD(EndX-BeginX)`. `_place_one_d`'s docstring already says Visio would
    put back any of them written directly.
  - So where `move` and `set_start_and_finish` write those cells on a 1-D shape,
    they are library writes: `keep_formula=True`, followed by the cache refresh.
    This is what keeps the line following its ends. It preserves today's values
    on every cell that has a formula.
  - A cell with no formula is written as it is today.
  - A user writing `connector.x` or `connector.width` directly still gets the
    value-wins rule, as in Visio's ShapeSheet.
- **The cache refresh skips cells the shape only inherits.** A cell whose
  element is not in this shape's tree belongs to the master, and Visio
  recomputes it for the instance on open. Writing it edited the master (#273,
  part 3).
- **`GeometryRow.row_type`, `index` and `del_bool`, and
  `DataProperty.set_attribute`, call `make_local()` first,** as the `x` and `y`
  setters already do.
  - `del_bool = False` on a row with no `Del` is a no-op, not a `KeyError`.
  - `index`'s write also refiles the row under its new key in `Geometry.rows`.
- **`DataProperty`'s four fields become properties** that read the row, or the
  master's row of the same name, each time.
- **`append_shape` refuses a detached shape,** so `delete()` is one-way.
  - The "built by hand" route the docstring mentions is not public: `Shape` is
    reached through a document, never constructed.
  - A test that builds a shape by hand to append moves to `copy()`.
- **`move` never touches the geometry rows.**
  - On a 2-D shape it moves the pin, under the value-wins rule, as dragging a
    shape in Visio replaces a pin formula. A pin the shape lacks is still taken
    as 0 and written.
  - On a 1-D shape it moves both ends through their setters, which unglues a
    glued end, then refreshes the derived cells.
- **A 1-D shape's text pin is set in its own coordinates,** at half the width
  and height the shape has once its derived cells are refreshed, for every 1-D
  shape (by `_is_one_d`). The refresh therefore runs before the text pin and the
  geometry are written.
  - A plain line, meaning a 1-D shape not named "Dynamic connector" and with no
    `Width`, `Height` or `Angle` formula (Visio's own lines carry `SQRT` and
    `ATAN2`, its connectors `GUARD` spans; a Lucidchart line carries none), is
    turned to run from start to finish, as Visio draws one: its width is its
    length, `hypot(dx, dy)`, its height 0, its angle `atan2(dy, dx)`, and its
    pin the midpoint of its ends. Every other 1-D shape is written its spans as
    before (a dynamic connector's height is its y span, a plain line's 0), and
    its formulas, once refreshed, give the size it is drawn with. (Amended after
    the PR review of #455: a diagonal line's text pin had been set from `dx`,
    not its length.)
  - `set_start_and_finish` on a 2-D shape raises `InvalidOperationError`, rather
    than doing nothing.

### The migration guide and the docs

- **Every behaviour change gets a guide entry:**
  - the value-wins rule, with `Cell.value` and `GeometryCell.value` named;
  - ungluing on a coordinate write;
  - `append_shape` refusing a deleted shape;
  - `move` not moving geometry rows, and moving a 1-D end;
  - `set_start_and_finish` refusing a 2-D shape;
  - `set_cell_value` with a `/` name refusing an absent row.
- Each docstring that promises the old rule changes to the new one:
  `Cell.value`, `GeometryCell.value`, `x` and the setters that refer to it,
  `line_weight`, `line_color`, `begin_x`, `move`, `append_shape`, `is_attached`,
  the `GeometryRow` setters and `DataProperty`'s fields.

## The Visio check

A script, `tools/writes_land_cases.py`, writes one `.vsdx` per case to a folder
it is given. Beside each case it writes the untouched fixture as
`<stem>.before.vsdx`. That pair is the before and after: two files side by side,
not two shapes on one page. The script records what each case expects in two
files in the same folder: `EXPECTED.txt`, one line per case for a person to
read, and `expected.json`, the same expectations as data for the check to judge.

1. `line_color`, `fill_color` and `text_color` set on a master instance with
   `THEMEGUARD`/`THEMEVAL` (s05 shape 37, the title bar; its container, shape
   35, draws nothing, so a picture of it could not show the write). Visio must
   show the written colour.
   - 1b. `text_color` written over a Character colour formula (test12 shape 2).
2. `x` and `width` set on a shape whose cells hold `GUARD(...)`. Visio must keep
   the written values.
   - 2b. A Shape Data value written over the property's own formula (s05 shape
     54). Visio must show the written value.
   - 2c. A geometry cell written on an instance whose row is its master's (test9
     Conn A). Visio must show the written value on that instance, and the
     master's value on a copy of it.
3. `begin_x` set on a connector glued at both ends (test4). Visio must show that
   end free at the written x, and the other end still glued.
   - 3b. A property an instance inherits, written on that instance (test3 shape
     7). Visio must show the written value on it, and the master's value on a
     copy of it.
4. `move` on a master instance with `MoveTo`/`LineTo` rows (test9). Visio must
   draw the outline on the shape.
5. `set_start_and_finish` on the Lucidchart line (test5_master shape 5). Visio
   must place the text on the line.
   - 5b. The same line placed on a diagonal, from (1, 7) to (4, 11). Visio must
     show it 5 in long with its text at its middle.
6. `set_start_and_finish` to a diagonal on a connector, and on a plain line
   whose `Width` is `SQRT(...)`. Visio must draw each between the two points
   given, with its pin and width still following its ends.

The PR body gives the commands:

- `python tools/writes_land_cases.py out/`
- `python tools/writes_land_cases.py check out/`

`check` asks Visio for each written cell twice: as it opens the file, and after
`Cell.Trigger()` makes it recalculate. A stale formula wins only when the cell
recalculates, so the second reading is the one that catches it. It also reads
each glued end's `Connect` records. It judges only the cases `expected.json`
names, and never sends a `.before` file to Visio. `visio_verify check` is not
the gate: it compares the package with what Visio opened, before anything
recalculates, so it could not fail on these bugs.

A clean `check`, and the maintainer's look at cases 1, 3 and 4 beside their
`.before` files, gate the merge.

`tools/visio_shots.py run --against main` takes the pictures for that look. It
has Visio export each case's page, and the `.before` file and `main`'s build of
the case beside it, as PNG and SVG, on open and after the checked cells
recalculate. It compares the SVGs shape by shape and records the run under
`.hermes/visio-shots/`. A case drawn differently after recalculating was stale
on open (#461).

## What must not change

- **The save sweep (28 fixtures) against `main`:** every difference is one this
  spec names. The workload's connect step writes through the glue engine, which
  keeps its formulas. The expectation is 28 of 28 `same`, and any difference is
  explained in the PR.
- **The render sweep (10 cases) against `main`:** loop copies no longer shift
  their geometry rows (8c), which the loop cases show. Every other case is
  `same`.
- **Coverage** stays at or above `fail_under`. Type completeness stays at 100.0%.
- Every gate stays green: the import graph, pyrefly strict, mypy, ruff, the
  annotations, the guide, the docstrings, `sphinx -W`, the API-reference gate,
  and the sdist and wheel smokes.

## Delivery: a spec PR, then three stacked PRs on main

1. **8a, one writer, and the value wins (#300, #319):**
   - `_write_cell` with `keep_formula`, and the three writers folded into it;
   - `Cell.value`, `GeometryCell.value` and `text_color` under the rule;
   - `/` names routed to their row or refused;
   - one `IX`-order row helper;
   - `_drop_formula` deleted;
   - `_float_end`, and the four end setters ungluing;
   - `move`'s and `set_start_and_finish`'s writes of a 1-D shape's derived cells
     made library writes, so 8a changes neither's output on its own;
   - `test_text_color_updates_the_existing_cell_in_place` inverted;
   - the Visio-check script;
   - the guide entries and docstrings for this part.
2. **8b, writes stay on the instance (#273, #435, #432, #434, #438):**
   `make_local` on the three row setters and `set_attribute`; the cache refresh
   skipping inherited cells; `DataProperty`'s live fields; the `"None"` match;
   the `master_page_ID` guard; `append_shape` refusing a detached shape.
3. **8c, moving a shape moves the shape (#430, #301, the text-pin bug):**
   `move`; the 1-D text pin in local coordinates; `set_start_and_finish`
   refusing a 2-D shape; the render-sweep expectations for loop copies.

Each PR is test-first. It gets per-task reviews, a spec-alignment review, both
sweeps, the gates, and CI on its pushed head. A final whole-branch review
follows 8c. The Codex and firmfooting-reviewer inline comments on each head are
read and answered before the merge is asked for.

## Out of scope

- #301's "text left behind with no `TxtPinX`", pending the Visio check.
- #436: `center_x_y` for a line, `bounds` under rotation, and `relative_bounds`
  through nested groups. This package does not use `center_x_y` for a 1-D text
  pin any more.
- Materialising an inherited section row other than geometry and Shape Data.
- The connector-reference group (#400, #313, #334), the pages-and-masters group
  (#448, #361, #440, #390, #439, #433, #431), #317 and #337. Each is its own
  package.
