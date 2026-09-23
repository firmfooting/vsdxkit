# Phase 3B: `ShapeCollection`, scoped and explicit about multiplicity (#100)

**Status:** Implementing, on `main` after #391.
**Plan:** `2026-09-12_simplification-usability-refactor.md`, Phase 3, "Collection semantics / Shapes".
**Issue:** #100 (10B-A3).

## Problem

There are 23 finders (`Page.find_*` and `Shape.find_*`), and they disagree with one another in three ways:
- **On multiplicity.** `find_shape_by_text` returns the first substring match. Two shapes reading "Review" silently give whichever comes first in document order.
- **On scope.** The page's finders search every shape, but `child_shapes` does not.
- **On what "not found" means.** Every miss is `None`, so a caller cannot tell "no such shape" from "a document with two of them".

## Decisions

**D1. `ShapeCollection` is a live, fixed-scope view, defined in `vsdxkit.shapes` beside `Shape`.**

`Shape.children` returns one and a collection returns `Shape`s, so the two share a module. Nothing needs a `Protocol` to break a cycle, and every annotation resolves.

```python
class ShapeCollection:
    def __iter__(self) -> Iterator[Shape]
    def __len__(self) -> int
    def by_id(self, shape_id: str) -> Shape | None          # duplicate ID -> PackageError
    def require_id(self, shape_id: str) -> Shape            # none -> NotFoundError
    def by_text(self, text: str) -> Shape | None            # several -> InvalidOperationError
    def require_text(self, text: str) -> Shape              # none -> NotFoundError; several -> InvalidOperationError
    def matching_text(self, text: str) -> tuple[Shape, ...]
    def by_property(self, label: str, value: str | None = None) -> Shape | None
    def require_property(self, label: str, value: str | None = None) -> Shape
    def matching_property(self, label: str, value: str | None = None) -> tuple[Shape, ...]
```

- **Live.** Every call walks the scope again, through `shape_tree`, so a shape added or removed after the collection was taken is seen. There is no cache (#102 decides cache policy).
- **Iteration.** Iteration and every finder read the same members: there is one member function per collection.
- **Text.** Matching is by equality with `Shape.text`, which is the shape's own text or else its master's, without Visio's terminating newline. `require_text("Start")` means the shape that reads "Start", not one that mentions it. Substring and regex searches are comprehensions over the collection, e.g. `[s for s in page.shapes if "Review" in s.text]`. The old `find_*` methods keep their substring behaviour until #103 deletes them.
- **Property.** `label` is the Shape Data label, as `data_properties` keys it, including rows inherited from the master. With `value`, it matches when `str(property.value) == value`. Without `value`, it matches any shape that has the property.
- **ID.** A duplicate ID in one scope makes the page structurally invalid, so it raises `PackageError`, naming the IDs' holders. `by_id` needs every match to detect a duplicate, so it filters the walk; `find_by_id` stays unwritten (#98).
- **Errors.** Every error names the scope, e.g. `page 'Page-1'` or `shape 5 on page 'Page-1'`, and the text, property or ID asked for. A multiple-match error also lists the matching shapes' IDs.

**D2. Four scopes, as the plan defines them.**

| Property | Members |
|---|---|
| `Page.children` | direct top-level shapes |
| `Page.shapes` | every shape on the page, recursively, connectors included |
| `Shape.children` | direct members of a group; empty otherwise |
| `Shape.descendants` | every shape inside, recursively |

**D3. `Page.shapes` changes meaning (breaking).** It was deprecated in 0.5.0, marked "removed in 1.0.0", and returned a one-element list holding the synthetic `<Shapes>` wrapper. It now returns the recursive `ShapeCollection`. The one test that read it moves to `Page.shapes` as a collection. The PR is `feat!` with a `BREAKING CHANGE` footer.

**D4. The old finders stay, unchanged.** `child_shapes`, `all_shapes` and the 23 `find_*` methods keep their names and results. #103 deletes them, after #101 gives wrappers identity. The docs' "Find pages and shapes" guide leads with the collections and keeps a short section on the old methods.

## Tests

- **Scopes:** each of the four scopes yields exactly what `child_shapes` or `all_shapes` does, on every fixture page; `Page.shapes` includes connectors; a non-group shape's `children` is empty.
- **Live:** a shape copied onto the page after the collection is taken is found by it.
- **Multiplicity:** the duplicate-text and duplicate-property cases the plan asks for, both built on a fixture by copying a shape.
  - `by_text` and `require_text` raise `InvalidOperationError` and name both IDs.
  - `matching_text` returns both.
  - `require_*` on a miss raises `NotFoundError`.
  - `by_*` on a miss returns `None`.
- **Exactness:** `by_text("Shape")` does not find a shape reading "Shape Text".
- **Duplicate ID:** `by_id` raises `PackageError`.
- **Return types:** `matching_*` returns a tuple.
- **Annotations:** the annotation ratchet gains no entries, and the type fixture exercises the new API under mypy.

## Out of scope

- #99 (`PageCollection`);
- #101 (identity: `==`, `hash`, `in`, `is_attached`);
- #102 (cache policy);
- #103 (deleting the old finders and the synthetic wrapper).
