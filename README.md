<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/firmfooting/branding/main/lockups/vsdxkit_dark.svg">
  <img alt="vsdxkit, by firmfooting" src="https://raw.githubusercontent.com/firmfooting/branding/main/lockups/vsdxkit.svg" height="56">
</picture>

Create, edit and analyse Microsoft Visio `.vsdx` files with Python, with no Visio needed at runtime.

[![CI](https://github.com/firmfooting/vsdxkit/actions/workflows/ci.yml/badge.svg)](https://github.com/firmfooting/vsdxkit/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/vsdxkit?color=2A6B64)](https://pypi.org/project/vsdxkit/) [![Python 3.10–3.14](https://img.shields.io/badge/python-3.10%E2%80%933.14-2A6B64.svg)](https://www.python.org/) [![Licence: BSD-3-Clause](https://img.shields.io/badge/licence-BSD--3--Clause-2A6B64.svg)](https://github.com/firmfooting/vsdxkit/blob/main/LICENSE) [![Docs](https://img.shields.io/badge/docs-firmfooting.github.io-2A6B64.svg)](https://firmfooting.github.io/vsdxkit/)

vsdxkit adds shape creation, Visio-faithful connectors, connector retargeting, cross-functional flowchart swimlanes, stricter package handling, current Python tooling and typed public APIs. It began as a fork of [`dave-howard/vsdx`](https://github.com/dave-howard/vsdx) and is now developed as its own project; see [Provenance and licence](#provenance-and-licence).

> **The 1.0 API.** This README describes the 1.0 API, which `main` carries and which is not yet released. Code written for 0.x will not run unchanged: [Migrating to 1.0](https://firmfooting.github.io/vsdxkit/migration-1.0.html) gives the replacement for every 0.x name 1.0 removes. [Install](#install) says which install gives you which API.

The distribution and the import package are both named **`vsdxkit`**. Import each name from the module that defines it, for example `from vsdxkit.document import Document`; the package root re-exports nothing.

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

The implementation edits the XML parts inside the Open Packaging Convention archive. It does not drive the Visio user interface. Generated files are checked against Microsoft Visio through COM before a change that Visio could silently repair is considered done, and what Visio reported is recorded so CI can replay it without Visio. The COM check itself is manual; no workflow runs Visio. See [When a change needs Visio](https://github.com/firmfooting/vsdxkit/blob/main/CONTRIBUTING.md#when-a-change-needs-visio).

## Install

Python 3.10–3.14 is supported on Linux, Windows and macOS.

**The 1.0 API is on `main`.** It is not on PyPI yet. Install it from GitHub:

```bash
python -m pip install "vsdxkit @ git+https://github.com/firmfooting/vsdxkit.git"
```

That tracks `main`, so pin a commit if you need a reproducible install. Until 1.0 is released, an install from `main` reports its version as 0.8.0, because the version is only bumped when a release is cut.

**The 0.x API is on PyPI.** `pip install vsdxkit` installs 0.8.0, the latest release, published on 2026-09-13. It has the 0.x names: it imports as `vsdx`, and its document class is `VisioFile`. The examples below do not run on it. Pin `vsdxkit<1` to stay on the 0.x names once 1.0 is released, and read [Migrating to 1.0](https://firmfooting.github.io/vsdxkit/migration-1.0.html) when you move.

0.7.0 was withdrawn from PyPI because its Jinja rendering could run code from a crafted document. 0.7.1 and later render templates in Jinja's sandbox. The [changelog](https://github.com/firmfooting/vsdxkit/blob/main/CHANGELOG.md) has the details.

## Quickstart

### Open, edit and save

Opening reads the whole package into memory and holds no file, so there is nothing to close. Saving is explicit.

```python
from vsdxkit.document import Document

document = Document.open("diagram.vsdx")
page = document.pages[0]
shape = page.shapes.by_text("Shape to remove")

if shape is not None:
    shape.text = "Renamed shape"

document.save("edited.vsdx")
```

Call `save()` without a filename to replace the source file in place:

```python
document = Document.open("diagram.vsdx")
document.pages[0].name = "Current state"
document.save()
```

A save writes every part you did not change exactly as it arrived. A part you did change is written as equivalent XML, but not in Visio's own spelling: the XML declaration, attribute quotes, empty-element form and namespace declarations can differ, and a CRLF inside text becomes LF. Visio and LibreOffice open both.

### Find shapes

`page.shapes` is every shape on the page, inside groups too; `page.children` is only the page's top-level shapes. A `require_*` lookup wants exactly one match and raises `NotFoundError` for none, a `by_*` lookup returns `None` for none, and a `matching_*` lookup returns every match. Any other test is a comprehension over a collection.

```python
document = Document.open("diagram.vsdx")
page = document.pages[0]

shape = page.shapes.require_text("Shape to remove")
missing = page.shapes.by_id("9999")
networked = page.shapes.matching_property("Network Name")
wide = [s for s in page.shapes if (s.width or 0) > 2]

assert missing is None and networked
```

[Find pages and shapes](https://firmfooting.github.io/vsdxkit/find_shape.html) covers pages, the scopes a lookup can search, what happens when several shapes match, and shape identity.

### Create shapes and connectors

Coordinates are Visio page units, normally inches, and `x` and `y` identify the shape centre. `page.connect(source, target)` returns a `Connector`.

```python
from vsdxkit.document import Document
from vsdxkit.glue import Routing
from vsdxkit.shape_kind import ShapeKind

document = Document.open("diagram.vsdx")
page = document.pages[0]

start = page.create_shape(ShapeKind.START_END, x=2.0, y=6.0, text="Start")
work = page.create_shape(ShapeKind.PROCESS, x=6.0, y=6.0, text="Do the thing")
decision = page.create_shape(ShapeKind.DECISION, x=10.0, y=6.0, text="OK?")

page.connect(start, work)
page.connect(work, decision, routing=Routing.RIGHT_ANGLE)
document.save("flow.vsdx")
```

[Create shapes and connectors](https://firmfooting.github.io/vsdxkit/create_connect.html) lists the shape kinds and covers copying a shape, glue to connection points, routing, and finding connectors.

### Retarget a connector

Name only the end that should move; the other stays where it is. The connector keeps its glue and routing unless you pass `options`.

```python
document = Document.open("flow.vsdx")
page = document.pages[0]
store = page.create_shape(ShapeKind.DATABASE, x=10.0, y=2.0, text="Store")

connector = page.connectors[0]
connector.retarget(target=store)

document.save("retargeted.vsdx")
```

`shape.delete()` also removes the connectors glued to the shape, and a group's members with it. [Retarget a connector](https://firmfooting.github.io/vsdxkit/create_connect.html#retarget-a-connector) covers connection points and `options`.

### Work with swimlanes

Swimlane operations need a page that already holds a Visio cross-functional flowchart (CFF). `add_lane()` copies the top lane above it and grows the CFF container to match.

```python
document = Document.open("cross-functional-flow.vsdx")
page = document.pages[0]
diagram = page.require_swimlanes()

review_lane = diagram.add_lane("Review")
check = page.create_shape(ShapeKind.PROCESS, x=6.0, y=2.0, text="Check")
diagram.move_to_lane(check, review_lane)

assert diagram.lane_for(check) == review_lane
document.save("with-review-lane.vsdx")
```

Lane membership is geometric: a shape is in the lane whose band contains its centre, and there is no separate membership field to write. [Cross-functional flowchart swimlanes](https://firmfooting.github.io/vsdxkit/swimlanes.html) has the rest.

### Render a Jinja template

Jinja expressions stored in shape text are rendered into a new file:

```python
document = Document.open("template.vsdx")
document.render(
    context={"project": "Ward refurbishment", "owner": "Facilities"}
)
document.save("rendered.vsdx")
```

Rendering runs in Jinja's sandboxed environment. [Jinja templates](https://firmfooting.github.io/vsdxkit/templating.html) covers the group-shape loop and `showif` conventions, self assignments, and what the sandbox does not protect against.

## Documentation

The full documentation is at <https://firmfooting.github.io/vsdxkit/>.

| To | Read |
|---|---|
| Install, open a document and save it | [Quick start](https://firmfooting.github.io/vsdxkit/quickstart.html) |
| Select, add, copy and delete pages, and find shapes | [Find pages and shapes](https://firmfooting.github.io/vsdxkit/find_shape.html) |
| Create, connect, retarget and delete shapes | [Create shapes and connectors](https://firmfooting.github.io/vsdxkit/create_connect.html) |
| Extend a cross-functional flowchart | [Cross-functional flowchart swimlanes](https://firmfooting.github.io/vsdxkit/swimlanes.html) |
| Fill a Visio template with data | [Jinja templates](https://firmfooting.github.io/vsdxkit/templating.html) |
| Look up a class or an error | [API reference](https://firmfooting.github.io/vsdxkit/classes.html) |
| Move code from 0.x to 1.0 | [Migrating to 1.0](https://firmfooting.github.io/vsdxkit/migration-1.0.html) |

## Limits

- The library starts from an existing `.vsdx`; it does not create a complete Visio document package from nothing.
- `.vsdm` files can be read and saved, but only back to a `.vsdm` destination. The package kind is decided by the content type of `visio/document.xml`, not by the filename. So `save()` refuses a `.vsdx` destination for a macro-enabled package, and a `.vsdm` destination for one that is not. Either would produce a file whose extension and `[Content_Types].xml` disagree, which Visio reports as corrupt. Stripping macros to convert a `.vsdm` into a `.vsdx` is not supported. A destination with no extension, or with an unrelated one, gets the matching Visio extension appended.
- Swimlane creation works on existing Visio CFF diagrams. It does not convert an ordinary page into a CFF diagram.
- Visio may recalculate layout when a generated file opens. The library writes the glue and route cells but does not reproduce Visio's entire layout engine.
- Loading enforces package expansion limits before any archive member is read: at most 512 members, 64 MiB per member, 256 MiB total uncompressed, and a 100:1 compression ratio, plus rejection of duplicate and path-unsafe member names. A hostile or accidental archive is refused with `vsdxkit.errors.PackageLimitError` instead of exhausting process memory. The defaults suit documents from unknown sources; trusted callers can relax the caps with `Document.open(filename, limits=PackageLimits(...))` or `limits_path="vsdxkit.limits.json"` (same keys, JSON object).

## Contributing

Contributions are welcome. [CONTRIBUTING.md](https://github.com/firmfooting/vsdxkit/blob/main/CONTRIBUTING.md) covers the development environment, the checks to run before a pull request, the documentation build, when a change needs Visio, and how releases are cut. Report vulnerabilities privately, as [SECURITY.md](https://github.com/firmfooting/vsdxkit/blob/main/SECURITY.md) describes.

## Provenance and licence

vsdxkit descends from [`dave-howard/vsdx`](https://github.com/dave-howard/vsdx), originally written by Dave Howard and released under the BSD 3-Clause licence. That work is the foundation this library is built on, and its copyright notice is retained in [`LICENSE`](https://github.com/firmfooting/vsdxkit/blob/main/LICENSE) alongside our own.

vsdxkit is now developed independently: it is not a downstream of that project and does not track it. The import package is `vsdxkit`, not `vsdx`, and the licence remains BSD 3-Clause.

---

<sub>Part of <a href="https://github.com/firmfooting">firmfooting</a>: safe, plain tooling for M365 and SharePoint operators. Not affiliated with or endorsed by Microsoft. Visio is a trademark of Microsoft.</sub>
