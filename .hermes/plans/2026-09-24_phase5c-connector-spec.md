# Phase 5C: `Connector(Shape)`, `Page.connect` and graph queries (#109)

Part of the 1.0 API cutover (#108-#112). Stacked on #405 (`ShapeKind`).
Authority: `.hermes/plans/2026-09-12_simplification-usability-refactor.md`,
"Connector and graph semantics".

## Public API

- `vsdxkit.shapes.Connector(Shape)`: the 1-D shape. It lives in `vsdxkit.shapes`
  because `shapes` already imports `connectors` at load time and every
  wrapper is made there; the glue engine stays in `vsdxkit.connectors`.
  - `source -> Shape | None`, `target -> Shape | None`: the shape each end's
    `Connect` record names; `None` for a floating end.
  - `retarget(*, source=None, target=None, options=None) -> None`.
    Omitting both endpoints raises `InvalidOperationError`. Without `options`
    glue, routing and each end's connection point are kept; a replaced end
    that was floating is glued dynamically; a retained point the new shape
    lacks raises `InvalidOperationError` before anything is written.
    `options` replaces the glue and routing of both ends.
- `Page.connect(source, target, *, glue=Glue.DYNAMIC, routing=Routing.DEFAULT,
  from_point=0, to_point=0) -> Connector`: the only way to create one.
- `Page.connectors -> tuple[Connector, ...]`: every 1-D shape in `Page.shapes`,
  glued or not.
- `Shape.connectors -> tuple[Connector, ...]`: every connector on the page with
  a `Connect` record naming this shape.
- `Shape.connected_shapes -> tuple[Shape, ...]`: the other glued end of each of
  those, without repeats, in connector order. A floating end contributes nothing.

## Wrapper factory

One function, `shapes._wrap(xml, parent, page) -> Shape`, builds every wrapper a
walk, a copy or a lane lookup returns, and makes a `Connector` exactly when the
shape is 1-D: it has its own `BeginX`, or the master shape it inherits from
does. `MasterCatalog.is_one_d(master id, master shape id)` looks the master
shape up and reads its cells on every call, so a master edited or replaced in
place is seen at once; only the id-to-master index is held, per catalog
revision. Equality and hash stay element identity, so `Shape(e) == Connector(e)`.

Cost, best of 20 walks of a 1503-shape page: main 3.8 ms, this branch 9.9 ms.
The cell test is a plain loop over the element's children; an ElementPath
attribute predicate made it 12.9 ms. Holding the master's element (7.9 ms) or
its answer (6.1 ms) went stale when a master was replaced or edited.

`Shape.connectors` and `connected_shapes` read the page's records once and walk
its shapes once, whatever the number of connectors. Only a record from `BeginX`
or `EndX` counts as a glued end, and an ID two shapes share raises
`PackageError`, as `ShapeCollection.by_id` does.

## Removed

- `Page.connect_shapes`, `Page.reanchor_connector`, `Page.get_connectors_between`.
- `Connect.create`, `Connect.retarget` (the engine is `connectors.create` and
  `connectors.retarget`, private to the library).
- `route=`, `from_cp=`, `to_cp=` everywhere, and `ConnectorOptions.from_route`.
- `Shape.connected_shapes`' old meaning (the connector shapes on this shape's
  records) is replaced by the one above.

## Kept for #112

`Connect`, `Page.connects` and `Shape.connects` stay as read-only record views;
their removal belongs with the export pruning.

## Tests

- `test_connector.py` (new):
  - wrappers are `Connector` exactly for 1-D shapes, including a master instance
    whose only `BeginX` is on its master;
  - `Shape(e) == Connector(e)`;
  - `source`/`target`, including a floating end;
  - `Page.connectors` includes a floating connector;
  - `Shape.connectors`/`connected_shapes`;
  - `connect` keywords;
  - `retarget` keeps or replaces glue, and refuses empty and invalid-point calls
    without writing anything;
  - the removed names are gone.
- Call sites are migrated by an AST rewrite that turns each literal `route` into
  the equivalent keywords.

## Docs

- README, `create_connect.rst`, `classes.rst`.
- Migration guide section "A connector is a shape", giving a before and after
  for every removed call.
