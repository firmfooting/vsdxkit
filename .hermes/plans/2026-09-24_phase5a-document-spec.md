# Phase 5A-2: `Document` replaces `VisioFile` (#108, part 2)

Stacked on 5A-1 (#402, no close state). This closes #108.

## Design

- **Module and class:** `vsdxkit/vsdxfile.py` moves to `vsdxkit/document.py`, and `VisioFile` becomes `Document`. There is no alias and no re-export.
- **`Document.open(source, *, limits=None, limits_path=None) -> Document`** is the one way to open a file.
  - `source` and `limits_path` take a `str` or an `os.PathLike`.
  - The suffix check (`TypeError` for anything but `.vsdx`/`.vsdm`) and `PackageStore.open` run in `open`. The ZIP is read and closed before it returns.
  - `__init__(package, filename)` wraps a package already read. It is for `open`, not for callers.
  - `open_vsdx_file` goes. It re-read the file into a live document, which is what `open` does.
- **`Document.save(target=None) -> Path`** replaces `save_vsdx(new_filename=None)`. It returns the absolute path `PackageStore.save` wrote. The destination rules are unchanged: the kind check, the appended suffix, an in-place save to the absolute source, and a reassigned `filename` redirecting the save.
- **`Document.render(context)`** replaces `jinja_render_vsdx(context)`. It is still the templating mixin's method until Phase 6 (#113).
- **No `debug=`:**
  - The debug dumps are gated on `logger.isEnabledFor(logging.DEBUG)`, so configuring the `vsdxkit` logger turns them on. Logging configuration is the caller's job.
  - `logging_support.attach_debug_stream_handler` and its handler class go.
- **`Document.debug` and `Document.limits` go.** The limits are applied at open and not kept.

Everything else on the class keeps its name until the later Phase 5 issues: `add_page`, `create_shape`, `get_page_by_name`, `vis` on `Page`, and so on. So does `vsdxkit.vsdxdiff.VisioFileDiff`, which is not the document class.

## Tests and docs

- A regex script rewrites tests, tools, README and the guides:
  - `VisioFile(` becomes `Document.open(`;
  - the module path, `save_vsdx` and `jinja_render_vsdx` are renamed.
- `tests/test_visiofile.py` becomes `tests/test_document.py`.
- **New tests:**
  - `open` takes a `Path`;
  - `save` returns the absolute path, in place and to a target;
  - a bare name gets the kind's suffix;
  - the 0.x names are gone, including `vsdxkit.vsdxfile` and `debug=`.
- **`docs/migration-1.0.rst`** gets an entry for every removed name.

## Verification

- the gates script;
- the canonical sweep against main, byte-identical;
- the wheel smoke test.
