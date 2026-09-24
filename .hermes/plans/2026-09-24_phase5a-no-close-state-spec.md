# Phase 5A-1: a document has no close state (#108, part 1)

Phase 5 of the 1.0 simplification plan is the public cutover, #108–#112. #108 (`Document` facade, no close state) is split in two stacked PRs:

- **5A-1 (this):** delete the close state.
- **5A-2:** `Document` replaces `VisioFile`.

## Why

`PackageStore.open` reads every member into memory and holds no file handle (Phase 1). "Closing" a `VisioFile` releases nothing. All it does is flip `file_open`, after which some 85 guards refuse writes with `VisioFileNotOpen`. Reads, copies and saves still work. The state exists only to be checked, and every mutator has had to remember to check it (#242, #329).

The plan deletes it: "delete context-manager, close-state and `VisioFileNotOpen`" (Phase 5). #108 names `__enter__`/`__exit__`, `close_vsdx`, `file_open` and `VisioFileNotOpen`.

## Design

- **`VisioFile`:** `__enter__`, `__exit__`, `close_vsdx`, `file_open` and `_require_open` are deleted, along with every `self._require_open(...)`, `page.vis._require_open(...)` and `dst_page.vis._require_open(...)` call in src.
- **`vsdxkit.errors.VisioFileNotOpen`** is deleted.
- **The part guard asks one question: is the shape still in the document?** A write through a deleted shape, or through one of its parts, still raises `InvalidOperationError` (#101).
  - `vsdxkit/document_part.py` becomes `vsdxkit/shape_part.py`.
  - `GuardedDocument` becomes `AttachedShape(Protocol)` with `_require_attached(operation)`.
  - `DocumentPart` becomes `ShapePart`, with `_shape`.
  - `_require_open` on parts becomes `_require_attached`.
  - `Shape` stops being a part. It keeps its own `_require_attached`, and its `_require_open` calls become `_require_attached`.
- **Guards that asked only about the close state go:**
  - `Container` stops being a part, and its three guards go.
  - The templating mixin's guard goes.
  - `GeometryOwner._require_open` becomes `_require_attached`.
- **`vsdxkit.media`:** donors are no longer closed after loading. Nothing reaches a donor anyway: only copies leave the module (#104).

## Breaking

- `with VisioFile(path) as vis:` raises `TypeError` (`AttributeError` on Python 3.10). Write `vis = VisioFile(path)`.
- `close_vsdx()`, `file_open` and `VisioFileNotOpen` are gone. There is nothing to close.

`docs/migration-1.0.rst` is started here, with one entry per removed member. #112 completes it.

## Tests

- **Rewritten by an AST script:** every `with VisioFile(...) as name[, VisioFile(...) as other]:` becomes one assignment per item, and its body is dedented. Each rewritten file must compile, and the suite must pass.
- **Deleted:** `tests/test_visiofile_not_open.py` and `tests/test_mutation_after_close.py`, since the behaviour is gone. So are the close cases in `test_errors.py`, `test_media.py`, `test_media_reuse.py`, `test_master_catalog.py`, `test_byte_preserving_save.py` and `test_package_limits.py`.
- **New:**
  - `with VisioFile(...)` raises `TypeError`, pinning that the context manager is gone;
  - `vsdxkit.errors` has no `VisioFileNotOpen`;
  - the detached-shape guards still refuse through `Cell`, `DataProperty` and geometry. The existing Phase 3 identity tests cover this.

## Verification

- the gates script;
- the canonical sweep against main, byte-identical;
- the wheel smoke test.
