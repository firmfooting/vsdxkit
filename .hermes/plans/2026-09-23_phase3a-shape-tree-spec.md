# Phase 3A: one traversal, in `vsdxkit.shape_tree` (#98)

**Status:** Implementing. Stacked on Phase 2 (#388).
**Plan:** `2026-09-12_simplification-usability-refactor.md`, Phase 3.
**Issue:** #98 (10B-A1). This is the first slice of the v1.0.0-beta milestone.

## Problem

The shape tree is walked in eleven places, each with its own recursion:

- `Shape.child_shapes`, `_all_shapes` and `get_max_id` each recurse by hand;
- the eleven `Shape.find_*` filter `all_shapes`, one call each;
- the twelve `Page.find_*` loop over the synthetic `<Shapes>` wrapper and call those;
- `Page._set_max_ids` walks a third way.

Connector detection is also written twice, and the two copies disagree:

- `Container.members` checks for `"BeginX" in shape.cells`, the shape's own
  cells only;
- `Page.delete_shape` checks `cell_value("BeginX") is not None`, which also
  reads the master.

## Decisions

**D1. `vsdxkit.shape_tree` holds pure functions over `Element`, and imports no wrapper.**

```python
def iter_children(element: Element) -> Iterator[Element]
def iter_edges(element: Element) -> Iterator[tuple[Element, Element]]  # (parent, child), depth first, parents first
def iter_descendants(element: Element) -> Iterator[Element]
def is_connector_element(element: Element, master: Element | None = None) -> bool
```

- **What `iter_children` accepts.** It takes a page or master contents root, a
  `Shape`, or a `Shapes` element. In every case it yields the `Shape` elements
  in the `Shapes` element that `element` is or holds.
  - It follows the schema: only a group holds `Shapes`. That is also what the
    wrappers checked, as `Type == "Group"`.
  - Across all 268 shapes in the fixtures, the two tests never disagree.
  - The `Shapes` form exists only for the synthetic wrapper, which #103 deletes.
- **`iter_edges` is the one recursion.** `iter_descendants` is built on it.
  Wrappers use the parent it reports to give each wrapper its parent: a
  sub-shape inherits its group's `Master`, so the parent chain carries meaning.
- **`is_connector_element` means 1-D.** A shape is 1-D if it has the 1-D
  Endpoints cells (`BeginX`), either itself or on the master shape it inherits
  from. No `Type` value marks a 1-D shape. This is Visio's `OneD`, and a test
  checks it against `one_d` for every shape in the COM manifest.

**D2. The wrappers route through it, and keep their behaviour.**

- `Shape.child_shapes`, `all_shapes`, `get_max_id` and every `Shape.find_*` go
  through `shape_tree`.
- `Page.child_shapes`, `all_shapes`, `_set_max_ids` and every `Page.find_*` go
  through `shape_tree`. They start from the page's `Shapes` element, so each
  top-level shape keeps today's parent, the synthetic wrapper. Templating reads
  `shape.parent.xml` as the `Shapes` element.
- Order is document order, depth first, parents before children, as
  `_all_shapes` produced.
- The public finders keep their names and results. #100 replaces them with
  `ShapeCollection`, and #103 deletes them.
- `Page.shapes` (deprecated) and the synthetic wrapper stay until #103.

**D3. One connector predicate.** `Container.members` and `Page.delete_shape`
both call `is_connector_element`, passing the master shape's element. `members`
therefore also excludes a connector whose `BeginX` comes only from its master.
Every connector Visio writes carries `BeginX` locally, so no fixture output
changes.

## Tests

- Unit tests over hand-built trees:
  - children of a page, a group, a non-group, and a `Shapes` element;
  - order;
  - `is_connector_element` with a local `BeginX`, an inherited one, and none.
- A generative property, seeded and deterministic, with no new dependency: over
  random trees, `descendants(x)` is each child followed by that child's
  descendants, and `iter_edges` names each element's true parent.
- The same property over every page and master of every fixture.
- COM agreement: for every shape in
  `tests/fixtures/com_reference/manifest.json`, `is_connector_element` equals
  `one_d == -1`.
- The existing finder, container, delete and templating suites pass unchanged.
  The canonical sweep of the probe workload must come out identical to #388.

## Out of scope

- `find_by_id`, which #98 lists. Every lookup by ID today needs a wrapper with
  its parent chain, so the function would have no caller. It lands with #100,
  where `ShapeCollection.by_id` uses it.
- #99 and #100 (collections);
- #101 (identity);
- #102 (cache policy);
- #103 (deleting the finders and the synthetic wrapper).
