# Phase 5F: the 0.x traversal names go (#112, part 2 of 4)

Part of the 1.0 API cutover (#108-#112). Stacked on #409 (the checked
migration guide). Authority:
`.hermes/plans/2026-09-12_simplification-usability-refactor.md`, Phase 5
("remove all old exports and methods") and Collection semantics ("there is no
... separate `walk()` whose scope can disagree with iteration").

#112 lands as four PRs:

1. #409: the guide check.
2. **This one:** the traversal names.
3. 5G: `Shape.delete`, the connection records made internal, and the
   `Document` page methods that `PageCollection` replaces.
4. 5H: README, quickstart and `classes.rst` for 1.0. This closes #112.

## Removed

| 0.x | 1.0 |
|---|---|
| `Page.child_shapes`, `Page.sub_shapes()` | `Page.children` |
| `Page.all_shapes` | `Page.shapes` |
| `Shape.child_shapes`, `Shape.sub_shapes()` | `Shape.children` |
| `Shape.all_shapes` | `Shape.descendants` |
| the 11 `Page.find_*` and `Page.find_shapes_with_same_master` | `page.shapes` lookups or a comprehension |
| the 11 `Shape.find_*` and `Shape.find_shapes_by_master` | `shape.descendants` lookups or a comprehension |
| `Page.set_name`, `Page.page_name` | `Page.name` |
| `Document.get_sub_shapes` | `Shape.children` |

`vsdxkit.retired_finders` and its tests are deleted. With the deprecated
aliases gone, nothing uses the `deprecation` package, so it leaves the
dependencies.

## Inside the library

`Page` and `Shape` each gain `_children()` and `_descendants()`, private
lists that build the collections and serve the library's own walks. A
collection is not indexable (the plan gives it iteration and length), so a
test that indexed the old lists takes `list(...)`, or `next(iter(...))` for
the first shape.

## Docs

The guide gains the traversal entries and the finder table, with each 0.x
finder named on its owner. `find_shape.rst`'s "Earlier finders" section
points to the guide, and `classes.rst` drops the removed members.

## Not in this PR

The element-level helpers on `Document` (`copy_shape`, `insert_shape`,
`renumber_shape_ids` and the others) have no 1.0 replacement. They are Phase
7's "delete dead methods", not a rename.
