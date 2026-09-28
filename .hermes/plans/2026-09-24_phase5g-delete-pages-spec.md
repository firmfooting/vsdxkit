# Phase 5G: `Shape.delete`, and pages change through the collection (#112, part 3 of 5)

Part of the 1.0 API cutover (#108-#112). Stacked on #410 (the traversal
names). Authority:
`.hermes/plans/2026-09-12_simplification-usability-refactor.md`, "Names
removed in 1.0" (`Shape.remove` and `Page.delete_shape` → `Shape.delete`) and
Collection semantics (`PageCollection` is where pages change).

\#112 now lands as five PRs:

1. #409: the guide check.
2. #410: the traversal names.
3. **This one.**
4. 5H: the connection records become internal (`Connect`, `Page.connects`,
   `Shape.connects`).
5. 5I: README, quickstart and `classes.rst` for 1.0. This closes #112.

## `Shape.delete()`

It replaces `Page.delete_shape(shape)` and the deprecated `Shape.remove()`.
It deletes the shape from its own page through the one deletion
(`Page._delete`), taking every connector glued to it or to a group member,
and every record naming them.

- A shape carries its page, so "a shape from another page" can no longer be
  passed. The `NotFoundError` for it is gone. The ID-collision hazard it
  guarded is now a positive test: deleting page 1's shape 1 leaves page 3's
  shape 1.
- A detached shape, including one already deleted, raises
  `InvalidOperationError` through `_require_attached`.

## Pages

| Removed from `Document` | Use |
| --- | --- |
| `get_page(n)` | `pages[n]` (`IndexError`, not `None`) |
| `get_page_by_name(name)` | `pages.by_name(name)` / `require_name(name)` |
| `get_page_names()` | `[page.name for page in pages]` |
| `add_page(name)` | `pages.create(name)` |
| `add_page_at(index, name)` | `pages.create(name, index=index)` |
| `copy_page(page, index=, name=)` | `pages.copy(page, name=, index=)` |
| `remove_page_by_index(i)` | `pages.delete(pages[i])` |
| `remove_page_by_name(name)` | `pages.delete(pages.require_name(name))` |

`_add_page_at`, `_copy_page` and `_remove_page_by_index` stay as the private
implementation `PageCollection` calls through its `PageLifecycle` protocol.
The Jinja renderer deletes a hidden page with `self.pages.delete(page)`, and
the mixin's host stub for `remove_page_by_index` goes.

`PagePosition` becomes `_PagePosition`: no public call takes one any more.
The guide maps each position to an index.

## Tests

- The cascade and error tests go through `Shape.delete`.
- The "same state through both APIs" test goes, because there is one API.
- The positions test uses indexes. The refusal of a relative position
  without a reference page can no longer be reached from the collection, so
  its test goes.
- `remove_page_by_name`'s no-match row goes: `require_name` refuses it, and
  the collection tests cover that.
