# Phase 5B: ShapeKind and Page.create_shape (#111)

Part of the 1.0 API cutover (#108-#112). Stacked on #403 (`Document`).

## Goal

A page creates its own shapes from a typed kind or from a prototype shape.
Palette-name strings leave the public API.

## Public API

- `vsdxkit.shape_kind.ShapeKind(Enum)`: `PROCESS`, `DECISION`, `START_END`,
  `PARALLELOGRAM`, `DATABASE`, `RECTANGLE`, `CIRCLE`, `LINE`.
- `Page.create_shape(kind_or_prototype, *, x, y, width=None, height=None, text=None) -> Shape`
  - `ShapeKind`: copies the bundled shape for that kind; text defaults to "".
  - `Shape`: copies the prototype (with its text) onto this page. A prototype
    from another document raises `InvalidOperationError` before anything changes.
  - Anything else (including a palette-name string) raises `TypeError` naming
    the `ShapeKind` members.
- `Routing.DEFAULT` replaces `routing=None` in `ConnectorOptions`; `None` is
  refused with `TypeError`.

## Removed

- `Document.create_shape(page, "PALETTE_X", x, y, w, h, text)`.
- `media.copy_palette_shape`; the kind table (`media._KINDS`) maps each kind to
  its bundled document and sentinel, and `media.copy_kind(kind, page)` copies it.

## Unchanged

- Bytes written: the canonical sweep against main is identical, including a
  workload that creates PROCESS and DECISION shapes and connects them.

## Tests

`tests/test_create_shape.py`: each kind copies its bundled geometry; size and
text; prototype copy; cross-document prototype refused; string refused;
position keyword-only; created shapes save as a valid package;
`Document.create_shape` is gone. `tests/test_glue.py`: routing defaults to
`Routing.DEFAULT`; `"curved"` and `None` refused.

## Docs

README, `create_connect.rst`, `swimlanes.rst`, `classes.rst` (Page member,
ShapeKind autoclass), and a "A page creates its own shapes" section in
`migration-1.0.rst`.
