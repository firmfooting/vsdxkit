# Phase 3D: a `Shape` is its element (#101)

**Status:** Implementing. Stacked on Phase 3C (#393).
**Plan:** `2026-09-12_simplification-usability-refactor.md`, Phase 3, and "Detached-wrapper semantics".
**Issue:** #101 (10B-A4).

## Problem

`Shape.__hash__` was `hash((ID, page.name, vis.filename))`, and `__eq__` compared those hashes. All three can change, so the old identity broke in three ways:
- **Rename.** A page rename silently dropped every shape on it out of the sets and dicts that held it. A renumber or a save-as did the same.
- **Two documents.** Two opens of one file had equal shapes.
- **Deleted shapes.** A deleted shape went on answering reads and accepting writes, which changed nothing a save could reach.

## Decisions

**D1. Identity is the element.** `a == b` iff both are `Shape`s and `a.xml is b.xml`, whatever their class. `hash` is `id(xml)`: the wrapper holds the element, so the id is stable and unique for the wrapper's life.
- **No separate document token.** The plan asks for "document token plus element identity". An element object is in at most one document, so its identity already carries the document's. Nothing moves elements between documents: `Shape.copy` deep-copies.
- **Cost if that is wrong.** If elements ever do move between documents, a token can be added without changing any API.

**D2. `Shape.is_attached`.** A shape is attached while its page is attached (`Page._attached()`: the store's part at the page's name is that page's own tree) and the element is in that tree.
- **Fast path.** The wrapper's parent chain is checked first, link by link. Each wrapper remembers its slot in its container: it is seeded by the walk that minted it, and verified before it is trusted. A chain that holds is proof, and a repeated check costs one comparison per level.
- **Fallback.** A chain that breaks is not proof of detachment: another wrapper may have moved the element into a group. Only then is the page tree walked.
- **Cost.** Measured on a generated page, reading `x`, `y`, `width`, `height` and `text` of every shape:

  | Page size | Unguarded | Guarded | Ratio |
  |---|---|---|---|
  | ~100 shapes | 1.1 ms | 1.4 ms | 1.32× |
  | ~1,000 shapes | 12.2 ms | 14.4 ms | 1.18× |
  | ~3,000 shapes | 38.9 ms | 48.6 ms | 1.25× |

  A naive page walk per check was 110× at 1,000 shapes.

**D3. A detached shape refuses reads and writes with `InvalidOperationError`.**
- **Reads:** `text`, `cell_value` and `cell_formula` (and so `x`, `y`, `width`, `height` and the rest), `data_properties`, `geometry`, `child_shapes` and `all_shapes` (and so `children` and `descendants`).
- **Writes:** every mutator through `Shape._require_open`. `Cell`, `DataProperty` and `Geometry` now guard through their shape rather than straight through the document.
- **Still readable:** `ID`, `xml`, `page`, `parent`, `is_attached`, `repr` and `hash`, so a detached shape can be named in a message and stays in its sets.

**D4. `add_swimlane` stays atomic without writing an unplaced lane.** Whether the label can be written is checked on the lane being cloned, which the clone matches row for row, before anything is created. The clone is then placed and written through an attached wrapper. #330's guarantee holds: a refused label leaves the document unchanged.

## Breaking

- Shapes from two documents are never equal. Before, two opens of one file compared equal.
- Reading or writing a shape after it is deleted raises.

## Tests

`tests/test_shape_identity.py`:
- two wrappers of one shape are equal and hash alike;
- equality ignores the wrapper's class;
- the hash survives a page rename, a renumber and a save;
- `is_attached` either side of a delete, including a deleted group's members and a shape on a deleted page;
- a moved shape is attached through every wrapper;
- a detached shape refuses reads and writes, including writes through a `Cell`;
- a detached shape keeps its ID, `repr` and hash.

`test_shape_equality` becomes `test_shapes_of_two_documents_are_never_equal`.
