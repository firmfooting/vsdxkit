# Vsdxkit 1.0 simplification and usability refactor

**Status:** Reviewed design v2, in phased implementation
**Date:** 2026-09-12
**Tracked in:** [v1.0.0-alpha](https://github.com/firmfooting/vsdxkit/milestone/2) and the milestones after it
**Target release:** 1.0.0
**Compatibility position:** Python API breakage is accepted. File-format behaviour is not.

> **Corrected 2026-09-13.** This header used to gate the work on "PR #3". That
> number is from before the project moved repositories and resolves to nothing
> here; issue #3 today is an unrelated defect. The phases below are tracked as
> milestones and issues, and those are authoritative for what is done. The
> design itself is unchanged.

## Decision

Replace the inherited upstream Python API with one coherent object model. Remove old names rather than carrying compatibility wrappers or a multi-release deprecation period.

The refactor may rename or remove classes, methods, arguments and imports. It must preserve:

- valid `.vsdx` and `.vsdm` OPC packages;
- Visio formulas, relationships, master references and shape IDs;
- explicit save semantics;
- deterministic round trips;
- files opening in Microsoft Visio without repair.

No release of the package is installable from PyPI: the name is registered, and 0.7.0 was withdrawn after a security defect. There is nothing published for downstream code to pin, so this is the point to remove accidental boundaries rather than make them permanent.

## Current evidence

| Surface | Current shape | Structural problem |
|---|---:|---|
| `VisioFile` | 1,061 lines, 59 methods | Document facade, package store, XML-part registry, page/master catalogue, metadata, ID allocation, copying and saving coexist |
| `Page` | 520 lines, 53 methods | Metadata, relationship mutation, traversal, connector graph operations, deletion and CFF conveniences coexist |
| `Shape` | 986 lines, 93 methods, 40 properties | XML view, traversal, caches, finders, formatting, copy/delete and graph access coexist |
| `Connect` | Record wrapper plus static factory and retarget service | `Connect.create()` returns a `Shape`; the class has two meanings |
| `MastersImportMixin` | Stateful document mutation through host stubs | Inheritance splits a file rather than modelling an is-a relationship |
| `JinjaTemplatingMixin` | Stateless transformation through host stubs | A function is disguised as inheritance |
| Shape traversal | `Page` creates a synthetic `Shape` for `<Shapes>` | Page and Shape repeat finder logic and expose an XML-container accident |
| Package representation | Absolute pseudo-paths mapped to mutable `BytesIO` cursors | Every consumer knows the source prefix; repeat-save and save-as have already exposed the coupling |

Known boundary defects to turn into ratchets before moving code:

1. `Shape.__hash__` uses mutable page name and filename.
2. Fresh wrappers over one element can hold disagreeing caches.
3. `Shape.remove()` bypasses connector and connection-record cleanup.
4. `VisioFileNotOpen` inherits `BaseException`.
5. Internal modules import `vsdx` to resolve cycles.
6. `Media` opens bundled documents during construction.
7. A deleted shape or cascade-deleted connector remains usable as a detached wrapper.

## Class-management position

Use classes for entities, owned collections and resources with state. Use functions for transformations. Do not add generic manager or service layers.

### Public classes

| Class | State and responsibility |
|---|---|
| `Document` | In-memory document model, metadata, pages, render and save facade |
| `PageCollection` | Ordered pages belonging to one document; lookup, create, copy and delete |
| `Page` | One page's metadata and page-local commands |
| `ShapeCollection` | A specifically scoped set of shapes with shared traversal and queries |
| `Shape` | A generic Visio shape entity: cells, text, geometry, style and deletion |
| `Connector(Shape)` | A 1-D shape with endpoints, glue/routing and retargeting |
| `Cell`, `DataProperty`, geometry views | Typed live views over one XML entity |
| `SwimlaneDiagram` | One CFF container shape, its lanes and geometric membership |

`Connector` is a real subtype because every connector is a Visio shape and retains shape properties. `Shape` is therefore generic, not defined as 2-D. One private predicate, `is_connector_element()`, controls wrapper construction everywhere.

### Internal stateful classes

| Class | State and responsibility |
|---|---|
| `PackageStore` | Source path, OPC-relative parts, path safety and atomic archive writes |
| `MasterCatalog` | The one master index, import, deduplication and master-specific relationships |
| `ConnectionRecord` | One Visio `<Connect>` element; data only, no factory or orchestration |

`PackageStore` and `MasterCatalog` are justified by owned state and invariants. They are not public managers.

### Functions, not classes

Use module functions for:

- XML parse, canonicalise, serialise, coercion and required-element checks;
- shape-tree traversal and predicates;
- relationship find, allocate, append-if-absent and remove;
- connector formula and connection-record construction;
- Jinja transformation;
- package-manifest comparison.

Do not add `DocumentManager`, `PageManager`, `ShapeManager`, `ConnectorManager`, `TemplateManager` or a generic repository layer. Do not use mixins to split implementation files. Do not turn live XML views into dataclasses. A frozen value object is justified only for immutable validated input such as connector options.

## Ownership and dependency rules

```text
Document / Page / Shape / Connector / collections
                       ↓
        narrow domain operation functions
                       ↓
        PackageStore / MasterCatalog / XML primitives
                       ↓
             zipfile / ElementTree
```

Rules:

- internal modules do not `import vsdx`;
- lower layers never import public facades at runtime;
- type-only edges use `TYPE_CHECKING`;
- no class reaches through two owners such as `shape.page.document._package`;
- every wrapper receives a direct immutable document identity token;
- mutations call the owner-boundary operation rather than editing another entity's private XML;
- each XML part has one authoritative representation at a time;
- every relationship kind uses the same allocation and deduplication helpers.

## Authoritative package representation

`PackageStore` owns a mapping of OPC-relative names to one authoritative value per part:

```python
PartValue = bytes | XmlPart

@dataclass
class XmlPart:
    tree: ElementTree
    original_bytes: bytes
    original_canonical_hash: str
```

Opening a package loads immutable bytes. Requesting XML promotes that part to one live `XmlPart`; its tree becomes authoritative. The retained original bytes are a byte-preservation snapshot, not a second writer. On save, compare the tree's canonical hash with the promotion baseline. If unchanged, write the original bytes exactly. If changed, serialise the live tree once. `write_bytes()` or `write_xml()` replaces the prior value. Every archive member is written exactly once.

This preserves untouched XML byte-for-byte even when a read path parsed it. It also avoids unreliable manual dirty flags while raw XML remains accessible. A test must prove that opening, promoting several parts and saving without mutation preserves the entire archive byte-for-byte.

This removes competing writers: the live tree is authoritative after promotion, while the original bytes are used only when canonical comparison proves no semantic mutation. XML parsing and serialisation remain pure functions.

```python
class PackageStore:
    @classmethod
    def open(cls, source: StrPath) -> PackageStore: ...
    def names(self) -> tuple[str, ...]: ...
    def read_bytes(self, name: str) -> bytes: ...
    def write_bytes(self, name: str, content: bytes) -> None: ...
    def read_xml(self, name: str) -> ElementTree | None: ...
    def require_xml(self, name: str) -> ElementTree: ...
    def write_xml(self, name: str, tree: ElementTree) -> None: ...
    def save(self, target: StrPath | None = None) -> Path: ...
```

`PackageStore` alone owns the resolved source path. `Document.save(target=None) -> Path` forwards to it. An explicit target does not rebind the opened source: a later `save()` still writes to the original path.

Package kind comes from `[Content_Types].xml`, not the source suffix. Saving a macro-enabled package to `.vsdx`, or a macro-free package to `.vsdm`, raises `InvalidOperationError`; 1.0 does not attempt macro conversion. A target with the matching package-family suffix preserves the source content types and VBA parts exactly unless a documented mutation changes them.

Absolute member names, `..` traversal and separator-normalisation collisions fail on open and write.

## Target public API

```python
from vsdx import Document, Glue, Routing, ShapeKind

document = Document.open("process.vsdx")
page = document.pages.require_name("Current state")

source = page.shapes.require_text("Start")
review = page.create_shape(
    ShapeKind.PROCESS,
    x=6.0,
    y=3.0,
    text="Review",
)

connector = page.connect(
    source,
    review,
    glue=Glue.POINT,
    routing=Routing.CURVED,
    from_point=0,
    to_point=2,
)

connector.retarget(target=page.shapes.require_text("Archive"))

if page.swimlanes is not None:
    page.swimlanes.add_lane("Review")

review.delete()
document.render({"owner": "Operations"})
output = document.save()
```

There is no `close()` method or context-manager state. The ZIP is closed before `Document.open()` returns. Only `save()` writes; garbage collection releases the in-memory model.

### Names removed in 1.0

- `VisioFile` → `Document`
- `save_vsdx` → `save`
- `jinja_render_vsdx` → `render`
- `Connect` → internal `ConnectionRecord` plus public `Connector`
- `Connect.create` and `Page.connect_shapes` → `Page.connect`
- `Page.reanchor_connector` → `Connector.retarget`
- `Shape.remove` and `Page.delete_shape` → `Shape.delete`
- `VisioFile.create_shape(page, ...)` → `Page.create_shape(...)`
- `Container` and `Page.get_container` → `SwimlaneDiagram`, `Page.swimlanes` and `Page.require_swimlanes`
- `VisioFileNotOpen` and closed-state checks are deleted

No old export or alias remains after the public cutover.

## Collection semantics

### Pages

`PageCollection` supports:

- `len(document.pages)`, iteration and integer indexing;
- `by_name(name) -> Page | None`;
- `require_name(name) -> Page`;
- `create(name=None, index=None) -> Page`;
- `copy(page, name=None, index=None) -> Page` for pages owned by the same document only;
- `delete(page) -> None`.

Cross-document page copying is outside 1.0 and raises `InvalidOperationError`.

### Shapes

Every `ShapeCollection` has a fixed scope. Iteration and finders search the same members.

- `Page.children`: direct top-level shapes.
- `Page.shapes`: all shapes recursively, including connectors.
- `Shape.children`: direct nested shapes.
- `Shape.descendants`: all nested shapes recursively.

A collection supports:

- iteration and length;
- `by_id()` / `require_id()`;
- `by_text()` / `require_text()`;
- `matching_text()`;
- `by_property()` / `require_property()`;
- `matching_property()`.

`by_id()` and `require_id()` expect Visio's page-unique ID. A duplicate ID raises `PackageError` because the document is structurally invalid. `by_text()` and `by_property()` require a unique match: they return `None` on no match and raise `InvalidOperationError` on multiple matches. Their `require_*` forms raise `NotFoundError` on no match and the same `InvalidOperationError` on multiple matches. `matching_*` always returns every match as an immutable tuple. Duplicate-text and duplicate-property cases are cutover acceptance tests.

There is no generic selector mini-language and no separate `walk()` whose scope can disagree with iteration.

## Connector and graph semantics

- `Page.connect(...) -> Connector` is the only creation entry.
- `Page.connectors -> tuple[Connector, ...]` contains every recursive 1-D connector in `Page.shapes`, including fully floating and half-glued connectors.
- `Connector.source` and `Connector.target` return `Shape | None`; `None` means that end is not glued.
- `Shape.connectors -> tuple[Connector, ...]` contains every connector, at any nesting depth, with at least one connection record referencing that shape.
- `Shape.connected_shapes -> tuple[Shape, ...]` returns the non-`None` opposite endpoints from `Shape.connectors`; fully floating connectors have no incidence.
- connector query tuples are deliberately graph results, not `ShapeCollection`, and do not carry text/property finders.
- one `is_connector_element()` predicate creates `Connector` wrappers from 1-D XML.
- wrapper equality and hash ignore wrapper subclass; `Shape(element) == Connector(element)` when the document token and XML element are the same.

`Connector.retarget()` has the explicit shape:

```python
def retarget(
    self,
    *,
    source: Shape | None = None,
    target: Shape | None = None,
    options: ConnectorOptions | None = None,
) -> None: ...
```

At least one endpoint is required; omitting both raises `InvalidOperationError`. When `options` is omitted, glue, routing and existing per-end connection-point indexes are preserved. The replacement endpoint is validated against the retained point before any mutation. If the endpoint being replaced was floating and has no point index to retain, that end uses dynamic glue. An invalid retained point raises `InvalidOperationError`; it never silently falls back to dynamic glue. Supplying `options` replaces the complete glue/routing specification for both ends.

Phase 0 includes a connector with one floating end and pins its enumeration, `None` endpoint, retarget, point handling and cascade-delete behaviour.

Deleting a connector directly removes its connection records without recursion. Deleting a 2-D shape cascade-deletes incident connectors through the same internal delete operation.

## Shape creation and custom shapes

`Page.create_shape()` accepts either:

- a built-in `ShapeKind`; or
- a prototype `Shape` from the same document.

The built-in sentinel map remains private. A prototype gives users an escape hatch for custom masters without exposing `MasterCatalog` as public API. Cross-document prototypes are outside 1.0 and raise `InvalidOperationError`.

Moving or copying a shape into a group is outside 1.0 unless Phase 0 proves an existing supported public workflow. Do not leave it implied.

## Swimlane semantics

`SwimlaneDiagram` is a typed view bound to one CFF container element. It uses the shared shape-tree traversal and geometric predicates; it does not implement a second walker.

- `Page.swimlanes -> SwimlaneDiagram | None` raises only on ambiguity, never on absence.
- `Page.require_swimlanes() -> SwimlaneDiagram` raises `NotFoundError` when absent and the same ambiguity error as the property.
- `SwimlaneDiagram.lanes -> tuple[Shape, ...]` enumerates lanes in visual order.
- `SwimlaneDiagram.shapes_in(lane) -> tuple[Shape, ...]` returns geometric members through shared predicates.
- `SwimlaneDiagram.lane_for(shape) -> Shape | None` returns the one containing lane and raises `InvalidOperationError` if malformed overlap makes membership ambiguous.
- `SwimlaneDiagram.add_lane(label) -> Shape` creates and returns a lane.
- zero CFF containers returns `None` from the property;
- one returns the view;
- multiple containers raise `InvalidOperationError` because the page is ambiguous.

1.0 edits an existing CFF diagram. Creating a complete CFF container on a plain page is outside scope. Lane creation routes shape/master/relationship changes through the same internal operations as other shape creation.

## Detached-wrapper semantics

`Shape`, `Connector`, `Cell`, page and collection wrappers are live views only while their XML remains attached to the owning document.

- each wrapper exposes `is_attached`;
- reading or mutating a detached wrapper raises `InvalidOperationError`;
- deleting a shape detaches the shape and every cascade-deleted connector;
- wrappers retain stable hash/equality after detachment so existing sets and dictionaries are not corrupted;
- a wrapper does not become equal to a newly inserted element that reuses an old Visio ID.

Use document identity plus XML element identity, not filename, page name, text, mutable ID or wrapper subclass.

## Errors

Add `vsdx/errors.py`:

```text
VsdxError(Exception)
├── PackageError
├── MissingPartError
├── NotFoundError
└── InvalidOperationError
```

Errors name the part, page, shape or operation. Nothing derives directly from `BaseException`.

## Behaviour-oracle architecture

The format oracle must survive the API rewrite without being rewritten by it.

Phase 0 creates two layers:

1. **API-coupled drivers** open, mutate and save documents.
2. **API-independent assertions** inspect generated packages and COM-observed facts.

The public cutover may replace a driver. It must not alter the corresponding assertion data or assertion implementation in the same PR. A test-only legacy/new driver adapter is allowed; it is not a production compatibility wrapper.

Package comparison is two-tier:

- exact member order and names;
- byte-identical non-XML members;
- XML members compared using `xml.etree.ElementTree.canonicalize()` with `with_comments=False`, `strip_text=False` and `rewrite_prefixes=False`;
- a separate raw-byte assertion records, per XML part, whether an XML declaration exists and its declared encoding and standalone value.

The canonicaliser's remaining QName-aware sets are empty. These options are part of the contract and version-pinned in the manifest helper tests. “Normal XML serialisation differences” is not an acceptance criterion. Every allowed difference must be represented by this rule or explicitly reviewed.

COM assertions consume generated files, not Python objects. They pin page/shape counts, connector endpoints, point formulas, routing values, masters, relationship targets, deletion results and CFF lane labels.

## Delivery strategy

Work serially from fresh branches off current `origin/main`. Each PR leaves `main` executable. Breaking changes begin before the rename cut, so `docs/migration-1.0.rst` starts with the first breaking PR and is updated in every later one.

Package-store and characterisation work are serial. Later work may be developed in parallel only where files and ownership are disjoint, but lands serially after rebase and full verification.

## Phase 0 — freeze file and Visio behaviour

Create:

- `tests/helpers/document_driver.py` — replaceable API-coupled driver;
- `tests/helpers/package_manifest.py` — API-independent package assertions;
- `tests/test_package_manifest.py`;
- `tests/test_visio_behaviour_contract.py`;
- `tests/fixtures/package_manifests/*.json`;
- an executable README workflow test;
- `docs/migration-1.0.rst`.

Pin:

- exact archive order and member names;
- canonical XML hashes, raw XML declaration metadata and non-XML byte hashes;
- save, repeated-save and save-as semantics, including no save-as rebinding, unchanged promoted parts, and refusal of `.vsdx`/`.vsdm` package-kind mismatches;
- object destruction without `save()` writes nothing;
- connector create and retarget formulas, records, point retention, invalid-point refusal, and a half-glued connector with one floating end;
- master import/deduplication;
- safe shape and direct connector deletion;
- CFF lane creation and membership;
- template output;
- COM read-back for every structural mutation.

Add strict xfail ratchets for:

- mutable wrapper hash;
- raw `Shape.remove()` leaving graph residue;
- detached-wrapper access;
- runtime package-root imports.

**Acceptance:** production behaviour unchanged; assertion layer independent of old API; canonicalisation rule and fixture provenance documented.

## Phase 1 — `PackageStore`

Replace absolute pseudo-paths and `BytesIO` cursors with the authoritative part mapping described above.

Rules:

- OPC-relative names only;
- one authoritative `PartValue` per member;
- one live tree plus an immutable byte-preservation snapshot per promoted XML part;
- untouched promoted XML writes its original bytes; changed XML is serialised once at save;
- one archive writer;
- atomic same-directory replacement and source-mode preservation;
- save-as does not rebind source;
- package kind comes from `[Content_Types].xml`; mismatched `.vsdx`/`.vsdm` targets fail rather than convert;
- path traversal and normalisation collisions fail closed;
- `Document` contains no `zipfile`, `tempfile` or `os.replace` logic.

Delete `zip_file_contents` outright. Add every removed use to the migration guide.

**Acceptance:** Phase 0 manifests and COM oracles pass; opening, promoting and saving without mutation is byte-identical; package-kind mismatch tests fail before writing; no other class opens a ZIP or strips source prefixes.

**Risk:** high format risk. No public entity rename in this PR.

## Phase 2 — master ownership and relationship base

Create the internal `MasterCatalog` and commit to it as the sole master-state owner.

It owns:

- the master index;
- master lookup;
- import and deduplication;
- master-part registration;
- master-specific relationship updates.

Extract pure relationship helpers for find, allocate ID, append-if-absent and remove. Document, page and master relationships use them.

Remove `MastersImportMixin` in this phase. `Document` holds one private catalogue and does not expose a second master index.

**Acceptance:** one master index; one relationship-ID allocator; import/dedup fixtures and COM checks pass; no mixin host stubs or casts remain for master operations.

## Phase 3 — scoped collections, traversal and identity

Add `PageCollection`, `ShapeCollection` and pure functions in `vsdx/shape_tree.py`.

Implement the exact scopes defined above. Remove:

- synthetic `Shape` wrappers for `<Shapes>`;
- duplicate finder and traversal implementations;
- list-like page operations on the document class;
- recursive methods implemented independently on wrappers.

One wrapper factory uses `is_connector_element()`. Equality and hash use document token plus XML element identity and ignore wrapper subtype. Wrappers hold their document token directly; no two-owner reach-through is required.

Default to computed cells, properties and child views. Retain a cache only after a benchmark proves it. If a cache survives, one document mutation counter invalidates it — no local ad hoc cache.

Run the full COM oracle in this phase because traversal decides where mutations land.

**Acceptance:** iteration and finders share scope; one traversal implementation; subtype-independent identity; stable set membership after rename/save; writes visible through old and newly acquired wrappers.

## Phase 4 — one mutation implementation per operation

Consolidate internals before the public rename.

### Creation and media

One internal operation performs built-in/prototype validation, package-resource loading, master handling, copy, ID allocation and insertion. Loading bundled media has no constructor side effect and no persistent `Document` cache.

### Deletion and attachment

One internal operation removes shape XML, incident connector shapes, connection records and empty relationship/container elements. `_remove_element_only` is private. During this phase, `Shape.remove()` calls the safe operation and the xfail turns green; this is a deliberate behaviour break before the name is removed.

The operation marks every removed wrapper detached. Direct connector deletion is an explicit test case.

### Connectors

Pure functions build formulas and records. `ConnectionRecord` holds data only. Validation completes before mutation. Create and retarget use one `ConnectorOptions` parser and one glue/formula/record builder.

**Acceptance:** one implementation each for create, delete, connect, retarget and relationship allocation; invalid input leaves no mutation; all Phase 0 assertions and COM oracles pass.

**Risk:** high. Split into 4A creation/deletion and 4B connectors if the production diff exceeds about 500 lines.

## Phase 5 — public 1.0 cutover

Rename and reshape in one deliberate public-API PR:

- `VisioFile` → `Document`;
- `Connect` → internal `ConnectionRecord` and public `Connector`;
- `Container` → `SwimlaneDiagram`;
- add page/shape collections and the exact target API;
- delete context-manager, close-state and `VisioFileNotOpen`;
- remove all old exports and methods.

Update the API-coupled driver, all tests, README, Sphinx API pages and migration guide. Do not change Phase 0 assertion data or assertion implementation in this PR.

**Acceptance:** no old public names in `vsdx.__all__`, tests or primary docs; every removed documented call has one migration entry; graph-query and detached-wrapper APIs are covered.

**Risk:** high Python breakage, low file-format risk.

## Phase 6 — templating and dependency direction

Replace `JinjaTemplatingMixin` with:

```python
def render_document(document: Document, context: Mapping[str, object]) -> None: ...
```

`Document.render()` calls it. There is no renderer class.

Remove all runtime `import vsdx` statements from internal modules. Add an import-graph test that fails on package-root imports or new cycles.

**Acceptance:** `Document` has no mixin bases; dependency arrows point down; Jinja fixtures and COM checks pass.

## Phase 7 — cleanup

After ownership is stable:

- move `Cell` and `DataProperty` only if doing so removes a real cycle;
- move cohesive text/ShapeSheet helpers to pure modules where useful;
- delete dead methods and TODO-marked unused paths;
- untrack committed `.venv` and generated `*.egg-info` trees;
- remove the `deprecation` dependency;
- remove transitional test drivers no longer needed;
- ensure only the 1.0 API appears in primary docs.

Do not split a class to meet a line-count target. File size is evidence, not the goal.

## Phase 8 — release 1.0

- build wheel and sdist;
- install the wheel into clean Python 3.10–3.14 environments;
- execute the README workflow from the installed wheel;
- run package manifests and every COM oracle;
- publish the complete migration guide;
- release through release-please: merging the release PR tags the version, publishes to PyPI with attestations and creates the GitHub release in one run (see "Releases" in `CONTRIBUTING.md`).

## PR sequence

1. **Behaviour contract** — independent assertions, manifests, canonicalisation and COM characterisation.
2. **Package store** — one authoritative part representation and one atomic writer.
3. **Master catalogue** — explicit master ownership and shared relationship primitives.
4. **Collections** — scoped traversal, wrapper classification, identity and cache policy.
5. **Mutation A** — creation, media, deletion and attachment state.
6. **Mutation B** — connectors and graph records, if split is needed.
7. **Public cutover** — clean 1.0 entities, collections, graph queries and errors.
8. **Composition** — remove templating mixin and root-import cycles.
9. **Cleanup** — dead code, generated trees and dependency reduction.
10. **Release** — 1.0 docs, wheel/sdist, PyPI and GitHub release.

Each PR starts from current `origin/main`, lands serially, and is independently executable. A later branch is not reported green until rebased onto its merged predecessor and rerun.

## Gates for every PR

```bash
python -m pytest tests -q
ruff check vsdx tests tools
ruff format --check vsdx tests tools
pyrefly check vsdx --min-severity warn --output-format min-text
sphinx-build -W --keep-going -b html docs docs/_build/html
actionlint .github/workflows/*.yml
uvx zizmor .github/workflows
python -m build
```

Additionally:

- Python 3.10–3.14 for package representation, collections and public-model PRs;
- Microsoft Visio COM for package, master, collection/traversal, connector, deletion, copy and CFF changes;
- exact/canonical manifest comparison on every phase;
- independent read-only adversarial review on every high-risk PR;
- exact pushed-head verification after review;
- no automatic GitHub reviewer requests.

## DRY rejection tests

The refactor is incomplete while any of these remain:

- two archive writers or two authoritative representations for one part;
- two shape-tree walkers or connector predicates;
- two master indexes;
- two relationship-ID allocators;
- two route/options parsers;
- two connector record builders;
- raw shape deletion outside `_remove_element_only`;
- mixin host stubs;
- runtime `import vsdx` inside package modules;
- a class whose methods only forward without owning state, identity or a collection;
- a collection method whose validity depends on an undisclosed owner type.

## Definition of done

- The README common path uses only the target 1.0 API.
- `Document` is an in-memory facade, not a package implementation or lifecycle guard.
- `PackageStore` owns source identity and one authoritative representation per part.
- `MasterCatalog` is the sole master-state owner.
- Page and shape collections have explicit, consistent scopes and one traversal engine.
- `Connector` is the public 1-D shape; records are internal.
- Connector graph queries, endpoint retention and refusal semantics are explicit.
- Wrapper identity is class-independent and stable; detached wrappers fail visibly.
- Existing CFF diagrams have one typed, non-duplicated domain view.
- One safe deletion path and one atomic save path remain.
- Mixins and package-root cycles are gone.
- No old API aliases remain.
- The migration guide contains every removed documented call from the first breaking PR onward.
- Python 3.10–3.14, static gates, package builds, installed-wheel workflow, package manifests and relevant COM oracles are green.

## Review record

Three independent bounded reviews returned `REVISE`; their findings were accepted and folded into this version.

### Delivery and oracle review

Resolved:

- split API-coupled drivers from API-independent assertion data and code;
- replaced “normal XML serialisation” with exact members, binary hashes and documented canonical XML hashes;
- added COM to collection/traversal changes;
- added unsafe removal to Phase 0 xfail ratchets;
- started migration documentation at the first breaking phase;
- moved the master-ownership decision ahead of relationship work;
- made wrapper equality subtype-independent;
- assigned media construction cleanup to mutation work.

### Class ownership and DRY review

Resolved:

- defined one `PartValue` authority rather than parallel byte/tree stores;
- restated `Shape` as generic and made connector classification single-source;
- committed to `MasterCatalog` before public cutover;
- bound `SwimlaneDiagram` to one container and shared traversal;
- made `PackageStore`, not `Document`, own source identity;
- enumerated collection methods and cross-document refusal;
- gave wrappers a direct document token.

### Python usability review

Resolved:

- made collection scope explicit and consistent between iteration and lookup;
- added public connector enumeration, endpoints and adjacency queries;
- specified complete retarget and connection-point retention behaviour;
- specified `Document.save()` return and non-rebinding semantics;
- defined detached-wrapper failures;
- added optional and required swimlane accessors;
- allowed prototype-based custom shape creation.

### Final verification

A bounded verification of the reconciled v2 returned `APPROVE` with no blockers. Its remaining contract notes were also folded in:

- floating and half-glued connector endpoints are `None`, remain enumerable and have pinned incidence and retarget semantics;
- each `by_*`, `require_*` and `matching_*` method now has explicit multiplicity behaviour;
- connector query scope is recursive and separate from text/property finder collections;
- XML canonicalisation options and raw declaration metadata are fixed;
- promoted but unchanged XML reuses original bytes;
- swimlane absence, ambiguity, lane order and membership are explicit;
- `.vsdx`/`.vsdm` package-kind mismatch is refused rather than converted;
- endpoint-free `retarget()` raises `InvalidOperationError`.

## Assumptions

- Breaking Python changes are accepted and should remove, not relocate, accidental complexity.
- File-format compatibility and Visio fidelity remain non-negotiable.
- The pure Python implementation remains the runtime; COM is an oracle only.
- Performance is not currently a bottleneck. Cache complexity needs benchmark evidence.
- Universal low-risk fixes can still be offered upstream separately; the 1.0 object model belongs to the fork.
