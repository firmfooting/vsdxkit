# Phase 4A: one creation operation, donors loaded once per process (#104)

**Status:** Implementing. Stacked on Phase 3F (#397).
**Plan:** `2026-09-12_simplification-usability-refactor.md`, Phase 4 "Creation and media".
**Issue:** #104 (10B-B1). It also closes #310.

## Problem

- **Three creation paths, three sets of steps:**
  - `VisioFile.create_shape` found a palette shape and called `copy_shape` on its element directly.
  - `Connect.create` called `Shape.copy` on a media shape.
  - `Shape.copy` resolved and imported masters, copied the element, rewrote master references, related the page to each master, and built the wrapper.
  The palette path skipped the master steps. That was safe only because palette shapes happen to be masterless.
- **The bundled donors were a per-document cache.**
  - `VisioFile._media` held a `Media` that opened `media.vsdx` and `palette_extended.vsdx` on first use.
  - `close_vsdx` had to close it, and #242 was the leak when it did not.
  - The plan asks for "no persistent `Document` cache" and #104 for the palette "parsed once per process".
- **`create_shape` matched the palette name as a substring (#310).** `"PALETTE_PRO"` created a process shape.
- **`Shape.copy()` with no page mislabelled a group member's copy.** The copy always lands at the page's top level, yet the returned wrapper claimed the source's group as parent. The copy also never named the master it had inherited from that group, so it kept a `MasterShape` pointing into nothing.

## Decisions

**D1. `vsdxkit.media` is a set of functions over donors loaded once per process.**
- **Loading:** `_donor(filename)` is `functools.cache`d. It opens the bundled package and closes it at once.
- **Why closing works:** a closed `VisioFile` still reads, and copying from it works, but every guarded write raises `VisioFileNotOpen`. So no caller can change what the next creation copies.
- **Nothing to release:** the package is read into memory with no handle held, so documents have nothing to close. `VisioFile._media`, `_shared_media` and the `Media` class go.
- **Lookups:**
  - `palette_shape(name)` and `media_shape(sentinel)` match the sentinel text exactly. An unknown name raises `NotFoundError` listing the names there are, which closes #310.
  - `connector_shape(curved=False)` answers the straight or curved connector.
  - `media_style(style_id)` answers the media document's StyleSheet.
- **Ruling: no `ShapeKind` yet.** No public `ShapeKind` enum is added here. Phase 5 names the public creation API; the sentinel map stays private.

**D2. `Shape.copy` is the one creation operation.**
- **The steps:** validate, resolve and import masters through the catalog, copy the element, allocate IDs, insert at the page's top level, relate the page to its masters, and wrap.
- **Callers:**
  - `create_shape` calls `palette_shape(name).copy(page)`, then sets position, size and text.
  - `Connect.create` calls `connector_shape().copy(page)`.
- **Below it:** `copy_shape` and `insert_shape` stay as the element-level allocation and insert primitives that `Shape.copy` uses.

**D3. A copy's parent is the page it lands on, and it names the master it inherited, whatever page is given.**
- **Parent:** `Shape.copy()` with no page now returns a wrapper whose parent is the page, where the element is.
- **Master:** a group member names the group's master on its copy whenever it inherits one, not only when a page is passed.

**D4. Cross-document prototypes are unchanged.** `Shape.copy` onto another document keeps working: #331's master import depends on it, and the donors are other documents. The plan's "cross-document prototypes raise" is for the public `Page.create_shape(prototype)` that Phase 5 adds.

## Tests

- **`tests/test_media_reuse.py`, rewritten:**
  - creating 50 shapes and 50 connectors across two documents opens each donor once in the process;
  - closing a document leaves nothing open;
  - a donor refuses writes, and creations leave it unchanged.
- **`tests/test_media.py`:** the bundled path is absolute; the curved connector is the curved one; an unknown or truncated palette name is refused (#310).
- **`tests/test_mutation_after_close.py`:** a closed document refuses `create_shape` and `connect_shapes` before any donor is loaded.
- **`tests/test_shape.py`:** a copy of a master instance's member made with no page names the master and has the page as its parent.
- **The master-provisioning tests** use the process donor, cleared around the test that writes a sibling part into it.
