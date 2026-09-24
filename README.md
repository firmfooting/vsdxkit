# vsdxkit

[![CI](https://github.com/firmfooting/vsdxkit/actions/workflows/ci.yml/badge.svg)](https://github.com/firmfooting/vsdxkit/actions/workflows/ci.yml)
[![Python 3.10–3.14](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue.svg)](https://www.python.org/)
[![BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-firmfooting.github.io-blue.svg)](https://firmfooting.github.io/vsdxkit/)

Create, edit and analyse Microsoft Visio `.vsdx` files with Python. Visio is not required at runtime.

> **The 1.0 API.** This README describes the 1.0 API, which `main` carries. Code written for 0.x will not run unchanged: [Migrating to 1.0](docs/migration-1.0.rst) gives the replacement for every 0.x name 1.0 removes. Pin `vsdxkit<1` to stay on the 0.x names.

The distribution and the import package are both named **`vsdxkit`**. Import each name from the module that defines it, for example `from vsdxkit.document import Document`; the package root re-exports nothing.

vsdxkit adds shape creation, Visio-faithful connectors, connector retargeting, cross-functional flowchart swimlanes, stricter package handling, current Python tooling and typed public APIs. It began as a fork of [`dave-howard/vsdx`](https://github.com/dave-howard/vsdx) and is now developed as its own project; see [Provenance and licence](#provenance-and-licence).

## What it does

- Opens, queries and edits existing `.vsdx` files without Microsoft Visio.
- Finds shapes by ID, text or Shape Data, on a page or inside a group.
- Creates common flowchart shapes, or copies a shape already on the page.
- Creates dynamic or connection-point glue with straight, right-angle or curved routing.
- Retargets either end of an existing connector.
- Reads and extends Visio cross-functional flowchart swimlanes.
- Copies shapes and pages while rewriting package-local IDs and importing masters.
- Renders data into Visio templates with Jinja.
- Saves to a new file or safely replaces the source file in place.

The implementation edits the XML parts inside the Open Packaging Convention archive. It does not drive the Visio user interface. Generated files are checked against Microsoft Visio through COM before a change that Visio could silently repair is considered done, and what Visio reported is recorded so CI can replay it without Visio. The COM check itself is manual; no workflow runs Visio. See [When a change needs Visio](CONTRIBUTING.md#when-a-change-needs-visio).

## Installation

**As of 2026-09-13 there is no release on PyPI.** The first release was
withdrawn after a security defect was found in it and cannot be republished, so
`pip install vsdxkit` finds no versions until the next one lands. The
[PyPI project page](https://pypi.org/project/vsdxkit/) shows the current state.

Install from GitHub in the meantime:

```bash
python -m pip install "vsdxkit @ git+https://github.com/firmfooting/vsdxkit.git"
```

That tracks `main`, so pin a commit if you need a reproducible install. Once
there is a release on the index, install it with `pip install vsdxkit`.

For development:

```bash
git clone https://github.com/firmfooting/vsdxkit.git
cd vsdxkit
uv sync --locked
```

Python 3.10–3.14 is supported on Linux, Windows and macOS. Add `--group docs` to
that sync if you also want to build the documentation; Sphinx needs Python 3.12
or later.

## Open, edit and save

Opening reads the whole package into memory and holds no file, so there is nothing to close. Saving is explicit.

```python
from vsdxkit.document import Document

vis = Document.open("diagram.vsdx")
page = vis.pages[0]
shape = page.shapes.by_text("Shape to remove")

if shape is not None:
    shape.text = "Renamed shape"

vis.save("edited.vsdx")
```

Call `save()` without a filename to replace the source file in place:

```python
vis = Document.open("diagram.vsdx")
vis.pages[0].name = "Current state"
vis.save()
```

A save writes every part you did not change exactly as it arrived. A part you did change is written as equivalent XML, but not in Visio's own spelling: the XML declaration, attribute quotes, empty-element form and namespace declarations can differ, and a CRLF inside text becomes LF. Visio and LibreOffice open both.

## Find shapes

`page.shapes` is every shape on the page, inside groups too; `page.children` is only the page's top-level shapes, and a group's `children` and `descendants` are its own. Each is a collection: iterate it, or look shapes up in it. A lookup says how many shapes it expects: `require_*` wants exactly one and raises `NotFoundError` for none, `by_*` wants at most one and returns `None` for none, and `matching_*` returns every match. Two matches for a text or property lookup that wanted one raise `InvalidOperationError` instead of picking one. IDs are unique on a valid page, so two shapes sharing one make a lookup by ID raise `PackageError`: the page is malformed.

```python
vis = Document.open("diagram.vsdx")
page = vis.pages[0]

shape = page.shapes.require_text("Shape to remove")
missing = page.shapes.by_id("9999")
networked = page.shapes.matching_property("Network Name")
wide = [s for s in page.shapes if (s.width or 0) > 2]

assert missing is None and networked
```

Any other test is a comprehension over a collection.

## Create shapes and connectors

Shape coordinates are in Visio page units, normally inches. `x` and `y` identify the shape centre.

```python
from vsdxkit.document import Document
from vsdxkit.glue import Routing
from vsdxkit.shape_kind import ShapeKind

vis = Document.open("diagram.vsdx")
page = vis.pages[0]

start = page.create_shape(ShapeKind.START_END, x=2.0, y=6.0, text="Start")
work = page.create_shape(ShapeKind.PROCESS, x=6.0, y=6.0, text="Do the thing")
decision = page.create_shape(ShapeKind.DECISION, x=10.0, y=6.0, text="OK?")

page.connect(start, work)
page.connect(work, decision, routing=Routing.RIGHT_ANGLE)
vis.save("flow.vsdx")
```

`ShapeKind` names the built-in shapes: `PROCESS`, `DECISION`, `START_END`, `PARALLELOGRAM`, `DATABASE`, `RECTANGLE`, `CIRCLE` and `LINE`. Pass a shape from the same document instead of a kind to place a copy of it, text included; `width`, `height` and `text` are optional either way.

`page.connect(source, target)` returns a `Connector`, a shape whose `source` and `target` are the shapes its ends are glued to. Two keywords say how:

| Keyword | Values |
|---|---|
| `glue` | `Glue.DYNAMIC` (the default) walks each end round its shape to the nearest side. `Glue.POINT` glues the ends to the zero-based connection points `from_point` and `to_point`. |
| `routing` | `Routing.DEFAULT` (Visio's own), `Routing.STRAIGHT`, `Routing.RIGHT_ANGLE` or `Routing.CURVED`. |

`page.connectors` lists every connector on the page, and `shape.connectors` and `shape.connected_shapes` the ones glued to a shape and the shapes at their other ends.

## Retarget a connector

Name only the end that should move; the other stays where it is. The connector keeps its glue and routing unless you pass `options`.

```python
vis = Document.open("flow.vsdx")
page = vis.pages[0]
store = page.create_shape(ShapeKind.DATABASE, x=10.0, y=2.0, text="Store")

connector = page.connectors[0]
connector.retarget(target=store)

vis.save("retargeted.vsdx")
```

`shape.delete()` also removes the connectors glued to the shape, and a group's members with it.

## Work with swimlanes

Swimlane operations need a page that already holds a Visio cross-functional flowchart (CFF). `page.swimlanes` is that diagram, or `None` on a page without one; `page.require_swimlanes()` raises `NotFoundError` instead. `add_lane()` copies the top lane above it and grows the CFF container to match.

```python
vis = Document.open("cross-functional-flow.vsdx")
page = vis.pages[0]
diagram = page.require_swimlanes()

review_lane = diagram.add_lane("Review")
check = page.create_shape(ShapeKind.PROCESS, x=6.0, y=2.0, text="Check")
diagram.move_to_lane(check, review_lane)

assert diagram.lane_for(check) == review_lane
vis.save("with-review-lane.vsdx")
```

Visio CFF membership is geometric. Shapes are associated with the lane whose vertical band contains their centre; there is no separate membership field to write.

## Render a Jinja template

Jinja expressions can be stored in shape text and rendered into a new file:

```python
vis = Document.open("template.vsdx")
vis.render(
    context={"project": "Ward refurbishment", "owner": "Facilities"}
)
vis.save("rendered.vsdx")
```

The package also supports its existing group-shape loop and `showif` conventions. See `docs/templating.rst` and the `tests/test_jinja*.py` cases for the exact template structure.

## Limits

- The library starts from an existing `.vsdx`; it does not create a complete Visio document package from nothing.
- `.vsdm` files can be read and saved, but only back to a `.vsdm` destination. The package kind is decided by the content type of `visio/document.xml`, not by the filename, so `save()` refuses a `.vsdx` destination for a macro-enabled package and a `.vsdm` destination for one that is not — either would produce a file whose extension and `[Content_Types].xml` disagree, which Visio reports as corrupt. Stripping macros to convert a `.vsdm` into a `.vsdx` is not supported. A destination with no extension, or with an unrelated one, gets the matching Visio extension appended.
- Swimlane creation works on existing Visio CFF diagrams. It does not convert an ordinary page into a CFF diagram.
- Visio may recalculate layout when a generated file opens. The library writes the glue and route cells but does not reproduce Visio's entire layout engine.
- Loading enforces package expansion limits before any archive member is read: at most 512 members, 64 MiB per member, 256 MiB total uncompressed, and a 100:1 compression ratio, plus rejection of duplicate and path-unsafe member names. A hostile or accidental archive is refused with `vsdxkit.errors.PackageLimitError` instead of exhausting process memory. The defaults suit documents from unknown sources; trusted callers can relax the caps with `Document.open(filename, limits=PackageLimits(...))` or `limits_path="vsdxkit.limits.json"` (same keys, JSON object).

## Development and verification

```bash
uv run --no-sync python -m pytest tests -q
uv run --no-sync ruff check src tests tools
uv run --no-sync ruff format --check src tests tools
uv run --no-sync pyrefly check src/vsdxkit --min-severity warn --output-format min-text
uv run --no-sync sphinx-build -W --keep-going -b html docs docs/_build/html
uv run --no-sync python -m build
```

The package is held at pyrefly's `strict` preset. CI tests Python 3.10–3.14 on Linux and Windows, and 3.10 and 3.14 on macOS. Changes that Visio could silently repair also run through `tools/visio_verify.py`, which opens the file in an invisible Microsoft Visio instance and diffs what Visio reports against what the package declares. That step is manual, on a maintainer's Windows machine; GitHub's runners have no Visio. What Visio said is recorded under `tests/fixtures/visio_observations/`, and CI replays those recordings against the fixtures on every run.

## Documentation

The Sphinx source is in [`docs/`](docs/). Build it locally with:

```bash
uv sync --locked --group docs
uv run --no-sync python -m sphinx -W --keep-going -b html docs docs/_build/html
```

Sphinx is pinned in the `docs` dependency group, which requires Python 3.12 or
later. The library itself still supports 3.10, so run the docs build on a 3.12+
interpreter.

## Provenance and licence

vsdxkit descends from [`dave-howard/vsdx`](https://github.com/dave-howard/vsdx), originally written by Dave Howard and released under the BSD 3-Clause licence. That work is the foundation this library is built on, and its copyright notice is retained in [`LICENSE`](LICENSE) alongside our own.

vsdxkit is now developed independently: it is not a downstream of that project and does not track it. The import package is `vsdxkit`, not `vsdx`, and the licence remains BSD 3-Clause.
