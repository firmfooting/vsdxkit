# Phase 3F: no synthetic `<Shapes>` wrapper, and each finder once (#103)

**Status:** Implementing. Stacked on Phase 3E (#396). **Plan:**
`2026-09-12_simplification-usability-refactor.md`, Phase 3: "Remove synthetic
`Shape` wrappers for `<Shapes>`; duplicate finder and traversal
implementations". **Issue:** #103 (10B-A6).

## Problem

- **The page's `<Shapes>` element was held as a `Shape`.** `Page._shapes` built
  one, and every walk of a page started from it:
  - `Page.child_shapes` and `Page.all_shapes` read it;
  - every Page finder forwarded to it;
  - top-level shapes took it as their `parent`.
- **Code had to know about the accident:**
  - `is_attached` carried a branch for it;
  - `append_shape` accepted it as a container;
  - templating read `shape.parent.xml` to find where a loop statement goes.
- **Every finder was written twice.** Page and Shape each had eleven. The
  collections (#100) made a twelfth way to look up a shape.
- **`VisioFile.get_sub_shapes`** was dead code.

## Decisions

**D1. A page's top-level shapes have the Page as their parent.**

- **One wrapping.** `Page.child_shapes`/`all_shapes` and
  `Shape.child_shapes`/`all_shapes` wrap a walk in one place:
  `shapes._wrap_children` and `shapes._wrap_descendants`. Each takes the element
  walked, the parent wrapper and the page.
- **Private helpers.** They are annotated with `Page`, which `vsdxkit.shapes`
  can import only for type checking. Public names would add entries to the
  runtime annotation ratchet, which only shrinks.
- **`_set_max_ids`** reads the IDs straight off the page's descendants.

**D2. `Shape._container()` is where a shape sits:** the `<Shapes>` element of
its parent, which is the page's contents root or the group.

- **`is_attached`** walks the parent chain through it, so the special case is gone.
- **Templating** puts a `{% for %}` or `{% showif %}` opener into the
  container's text, and the closer onto the shape's tail. That is the same
  element for a top-level shape and a group member alike.
- **A latent bug fixed.** The old code used `shape.parent.xml`. For a group
  member that is the group's own `<Shape>` element, so the loop opened before
  the group's cells and closed inside its `<Shapes>`, and the rendered page
  failed to parse (`ParseError: mismatched tag`).
  `tests/test_jinja_nested_loop.py` pins it.

**D3. `append_shape` accepts groups only.**

- **Why:** with no Shape wrapping a `<Shapes>` element, a page-level append has
  no receiver.
- **The replacement:** `VisioFile.copy_shape(element, page)` renumbers and
  appends to the page's `<Shapes>`.
- **Tests:** two tests that pinned the wrapper itself are deleted:
  - `test_append_shape_to_the_page_shapes_container`;
  - `test_get_page_shapes`, which counted `Page._shapes`.

**D4. Every finder has one implementation, in `vsdxkit/retired_finders.py`.**

- **The shims.** The 11 Page and 11 Shape finders, plus
  `Page.find_shapes_with_same_master`, are two-line shims. Each warns and
  forwards with the collection it searched: `page.shapes` or
  `shape.descendants`.
- **Behaviour kept until 1.0.0:**
  - the `find_shape_*` forms answer the first match;
  - text is matched as a substring;
  - property values are compared as text.
- **Phase 5 deletes the module.**
- **No import back.** `vsdxkit.shapes` imports this module, so it cannot import
  `Shape` back. It declares two Protocols, `SearchedShape` and `Searched`, for
  what it reads (the seam pattern from Phase 2), so its signatures resolve at
  runtime.
- **Warnings.** Each one names the replacement, and points at the caller's line
  (`stacklevel=3`). They are plain `warnings.warn`, not the version-gated
  `deprecation` decorator, which would stay silent until `__version__` reached
  1.0.0.
- **`Page._find_shapes_by_id`** is gone. Templating filters `page.shapes` by ID,
  since a loop's copies share one.

**D5. Internal callers use the collections.**

- **ID lookups** use `by_id`. They are in connectors, `connected_shapes`,
  `get_connectors_between`, master sub-shape resolution and `create_shape`.
  - **Ruling:** a duplicate ID on the page now raises `PackageError` there,
    where the first match was silently taken. The plan rules a duplicate ID
    structurally invalid.
  - **Cost if wrong:** revert a call site to a comprehension.
- **Text lookups keep their substring semantics** through explicit
  comprehensions. They are the media sentinel, the palette name and
  `get_connectors_between`'s text arguments, whose callers pass fragments.

**D6. `VisioFile.get_sub_shapes` warns** and keeps its body until 1.0.0. Nothing
in the library calls it.

## Tests

- **`tests/test_retired_finders.py`:** every shim warns with the replacement
  named and returns what it did, including first match, substring and
  descendants-only scope. The warning points at the caller.
- **`tests/test_jinja_nested_loop.py`:** a loop on a group's first member, and
  on a page's first shape.
- **The suite runs through the collections:** 0 finder DeprecationWarnings, down
  from 686.

## Not run here

The COM oracle needs Windows Visio; its tests skip on this runner. The
canonical-output sweep over every fixture stands in for "traversal decides where
mutations land".
