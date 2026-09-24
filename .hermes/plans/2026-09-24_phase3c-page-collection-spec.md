# Phase 3C: `PageCollection` (#99)

**Status:** Implementing. Stacked on Phase 3B (#392).
**Plan:** `2026-09-12_simplification-usability-refactor.md`, Phase 3, "Collection semantics / Pages".
**Issue:** #99 (10B-A2).

## Problem

`VisioFile.pages` is a plain `list` that the document mutates in place. Any caller can `append`, `del` or reorder it without the package changing to match. Page operations are spread across eight document methods:
- `get_page` and `get_page_by_name`;
- `add_page` and `add_page_at`;
- `copy_page`;
- `remove_page_by_index` and `remove_page_by_name`;
- `get_page_names`.

Each takes its own form of position. In `add_page_at`, a negative int silently means something other than Python's "from the end": `-1` inserts before the last page.

## Decisions

**D1. `vsdxkit.pages.PageCollection(Sequence[Page])`.** `VisioFile.pages` returns one, over the document's private `_pages` list, so it is live.
- **Sequence.** `len`, iteration, `in`, `index`, and indexing (negative indexes too) behave as on a tuple. A slice returns a tuple.
- **Lookup.** `by_name` returns the page or `None`. `require_name` raises `NotFoundError` on a miss. Two pages with one name raise `PackageError`, since Visio keeps page names unique.
- **`create(name=None, index=None)`.** It appends by default. Otherwise `index` must lie in `0..len(pages)`; any other int, negative included, raises `InvalidOperationError` before anything changes. A name already in use gets a numeric suffix, which is today's `_get_new_page_name`.
- **`copy(page, name=None, index=None)`.** The copy goes straight after `page` unless `index` is given. A page not in this document raises `InvalidOperationError`, because cross-document page copy is outside 1.0.
- **`delete(page)`.** Removes the page, its part, its relationships and its title. A page not in this document raises `InvalidOperationError`, instead of deleting whichever local page sits at its index.

**D2. No upward import.** `pages.py` declares a `PageLifecycle` Protocol containing `add_page_at`, `copy_page` and `remove_page_by_index`. `VisioFile` satisfies it structurally. The collection drives today's page lifecycle; Phase 5 moves that lifecycle behind the collection and removes the document's list-like methods.

**D3. The document's list is private.** Internal mutations go through `_pages`. Nothing outside `vsdxfile.py` assigned `pages`, and every existing read (indexing, iteration, `index`, `in`) is a `Sequence` operation, so no caller changes. `JinjaTemplatingMixin` declares `pages` as a property returning `PageCollection`.

## Tests

`tests/test_page_collection.py`:
- sequence behaviour;
- lookup by name;
- the duplicate-name `PackageError`;
- `create` at the end, at the front and at `len`;
- the refused indexes -1, -2, 4 and 99, each leaving the document unchanged;
- `copy` after its original and at an index;
- a refused cross-document copy;
- `delete`, and a refused foreign page;
- liveness.

Each save goes through the autouse validator.

## Out of scope

The document's old page methods stay until the Phase 5 cutover. There is no migration guide yet (100-A5); the "Find pages and shapes" guide documents the collection.
