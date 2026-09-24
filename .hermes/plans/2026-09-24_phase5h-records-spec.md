# Phase 5H: the connection records are internal (#112, part 4 of 5)

Part of the 1.0 API cutover (#108-#112). Stacked on #411 (`Shape.delete`).
Authority: `.hermes/plans/2026-09-12_simplification-usability-refactor.md`,
"Connectors": `Connect` splits into an internal record and the public
`Connector(Shape)`, and the record stops reaching up to a page.

## What goes

| Removed | Use |
|---|---|
| `vsdxkit.connectors.Connect` | `Connector`, `connector.source`, `connector.target` |
| `Page.connects`, `Page.get_connects()` | `page.connectors` |
| `Shape.connects` | `shape.connectors`, `shape.connected_shapes` |
| `Page.add_connect(connect)` | `page.connect(a, b)` |
| `Page.remove_connect_records(ids)` | `connector.retarget(...)`, `shape.delete()` |

The record the engine reads becomes `vsdxkit.connectors._Connect`: a read
view over one `<Connect>` element, with `from_id`, `to_id`, `from_rel` and
`to_rel` read from the element on each access (#320). It holds no page and
no shape, so the three `UNRESOLVED` annotation entries for `Connect` go.

- `Page._connects()` returns the page's records; `Page._add_connect(element)`
  appends one; `Page._remove_connect_records` keeps its behaviour.
- A record without `FromSheet` or `ToSheet` still raises
  `MalformedPackageError`, now from the graph queries that read it
  (`shape.connectors`, `connector.source`, `connector.target`).
  `FromCell` and `ToCell` stay optional.

## Tests

Tests that check what a connection, retarget, copy or delete leaves in the
package read the records straight from the page XML, through
`tests/helpers/connect_records.py` (`page_records`, `records_naming`,
`unglue`). The helper does not import vsdxkit, so it cannot pass because the
library agrees with itself.

- `test_connect_constructor.py` becomes `test_connect_records_malformed.py`:
  a malformed record raises through the public queries, and a record without
  an optional attribute is read.
- The #320 tests use `shape.connectors`: a renumbered shape still finds its
  connectors, and a connector held across the renumber resolves to the new
  ID.
- The tests of `remove_connect_records` itself go with the public method.
  The one that needed an unglued connector uses `unglue`.
- The mypy fixture types `Connector` and `shape.connectors`.

## Docs

- The migration guide gains "The `<Connect>` records are internal", naming
  every removed member; the guide check drives the list.
- `classes.rst` drops `Connect` and `connects`.

The README and index notice still name `ConnectionRecord`; 5I rewrites them.
