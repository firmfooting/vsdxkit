# vsdxkit three-year roadmap (September 2026 – August 2029)

**Status:** design, tracked in the GitHub project "vsdxkit roadmap 2026–2029" (milestones, epics and tickets)
**Date:** 2026-09-13
**Base:** `main` at `67098c0` (v0.6.3 plus the 2026-09 hardening PRs)
**Companion:** `.hermes/plans/2026-09-12_simplification-usability-refactor.md` (the approved 1.0 object-model plan, executed as the first four milestones here)

## Vision

vsdxkit is the reference open-source toolkit for Visio files: create, edit, inspect, validate, render and convert `.vsdx` (and stencils and templates) from Python, the command line and AI agents, on any operating system, without Microsoft Visio.

The Visio file format has not changed since Visio 2013. Microsoft offers no cross-platform programmatic surface for it (the JavaScript API exists only for classic SharePoint embedding; there is no Graph/REST/Python API) and has been retiring adjacent automation (Visio Web Access 2023, Data Visualizer add-in 2026, Power Automate export 2026). `.vsdx` nevertheless remains the enterprise interchange format. File-level tooling is therefore the only automation path, and the field is thin: upstream `vsdx` is low-cadence, `libvisio-ng` is GPL and read-only, Aspose is proprietary, and every Visio MCP server built in 2025–26 needs Windows plus COM.

## Evidence base

Three inputs shaped the plan:

1. **Codebase audit** (2026-09-13) of the 14 modules / 4,413 lines / 450 tests. Findings that drive Year 1: the package is held as absolute pseudo-path `BytesIO` cursors and every XML part is rewritten on save; masters are written outside `save`; `Shape` has 86 public members with 11 finders duplicated on `Page` with divergent scope; `ET.register_namespace` is called four times with different URIs so serialised parts carry `ns0:` prefixes (the likely cause of upstream #90 "files don't open in LibreOffice/draw.io"); `update_ids` misses the dot-less `Sheet5!` references the connector engine writes; nothing can construct a document from nothing (three helpers fail on an empty package); no rendering; no text-run, hyperlink, image, layer, theme or stencil support; performance is wrapper churn (6 ms per `find_shape_by_id` on a 47-shape page).
2. **Upstream demand** (dave-howard/vsdx, 105 stars, 37 open issues): create from scratch (#70, #54), SVG/PDF export (#28, #36), hyperlinks (#74), images (#75), copy between files (#41), connectors and page size (#37), glue (#46), multiple geometries (#69), big-file load time (#67), text breaking fields (#88, #92), empty shape data (#79), interoperability (#90, #35), and #22 "review the API for 1.0" open since 2021.
3. **Ecosystem research** (2026-09-12): draw.io removed VSDX export in 26.1.0 (Feb 2025) and nothing free replaced it (users self-host old forks or pay a converter); a 2026 cluster of AI-skill repositories each hand-roll a VSDX writer to reuse vendor stencils; no diagrams-as-code DSL has a Visio backend; the "complete library" bar is set by OfficeIMO.Visio (.NET) and vsdx-go (formula evaluator, router, renderer, validator); Python expectations for a 1.0 in 2026 are Trusted Publishing with attestations, a written version policy, free-threading tests and benchmarks; Python 3.10 EOL Oct 2026, 3.11 Oct 2027, 3.12 Oct 2028; 3.15 final 2026-10-01, 3.16 2027-10-06.

## Principles

- **File-format fidelity is the contract.** Package manifests (canonical XML plus byte hashes) and the Visio COM oracle gate every structural change. Python API may break at majors; file behaviour never regresses.
- **Pure Python at runtime; Visio only as an oracle.** Tests pass with no Visio installed. `needs-visio` work closes only after the COM harness passes on Windows.
- **One implementation per operation.** No second archive writer, walker, master index, relationship allocator or connector builder. The 1.0 plan's DRY rejection list applies to all later work.
- **Measure before caching.** Performance work starts with a benchmark suite; caches are invalidated by one document mutation counter.
- **Ship early, version honestly.** 0.7 goes to PyPI under the legacy API with an explicit "1.0 will rename" notice; pre-releases (a1, b1) precede 1.0; semver, deprecation and Python-version policies are published at 1.0.
- **Fork-forward for capability, small PRs upstream for universal bugs.** Community fixes stuck in upstream's queue are ported with attribution.

## Horizons

| Horizon | Period | Theme | Headline outcomes |
|---|---|---|---|
| Year 1 | Sep 2026 – Aug 2027 | Foundation | PyPI + release automation; 1.0 object model (Document, collections, Connector, SwimlaneDiagram, PackageStore, MasterCatalog, errors); documents from nothing; structural validator |
| Year 2 | Sep 2027 – Aug 2028 | Fidelity and breadth | Text runs and fields; complete Shape Data; hyperlinks; stencils (.vssx); all geometry row types and a path builder; groups, containers, CFF creation; images; layers; themes and effective styles; performance; headless SVG renderer; Python 3.12+ |
| Year 3 | Sep 2028 – Aug 2029 | Ecosystem | CLI; draw.io bridge; JSON model; XSD validation; diagrams-as-code builder; layout and routing; DOT/Mermaid bridges; MCP server; SVG import; stencil/template authoring; macros; plugins; LTS |

## Milestones

Roughly one release per quarter. Dates are milestone due dates in GitHub.

| Milestone | Due | Exit criterion |
|---|---|---|
| v0.7.0 — Hardening and first PyPI release | 2026-10-31 | Open integrity issues closed; output opens in LibreOffice/draw.io; tests hermetic; Trusted Publishing + tag-triggered release + RTD live; 0.x API-change notice |
| v1.0.0-alpha — Behaviour oracle, PackageStore, MasterCatalog | 2027-01-31 | 1.0 plan Phases 0–2: manifests + COM oracle; byte-preserving saves; one master index; error hierarchy; a1 on PyPI |
| v1.0.0-beta — Collections, identity and single mutation paths | 2027-03-31 | Phases 3–4: scoped collections, one traversal, stable identity, one create/delete/connect/retarget path; b1 on PyPI |
| v1.0.0 — Public API cutover | 2027-05-31 | Phases 5–8: Document/Connector/SwimlaneDiagram model, templating function, no root-import cycles, cleanup, policies, migration guide, 1.0 on PyPI |
| v1.1.0 — Documents from nothing | 2027-08-31 | `Document.new()`, bytes/file-like I/O, cross-document copy, page setup and background pages, document properties, structural validator; Python floor 3.11 |
| v1.2.0 — Text and Shape Data fidelity | 2027-11-30 | Rich text model, field-preserving writes, field refresh, full Property/User sections, hyperlinks; MCP spike |
| v1.3.0 — Stencils, geometry and groups | 2028-02-29 | .vssx/.vstx open, drop external masters, bundled stencil catalogue, all geometry rows, path builder, connection points, transforms, groups, containers, CFF creation |
| v1.4.0 — Media, layers, themes and effective styles | 2028-05-31 | Images in/out, layers, themes parsed, StyleSheet chain resolution (`shape.effective`), comments |
| v2.0.0 — Performance, headless SVG rendering, Python 3.12+ | 2028-08-31 | Benchmarks and indexes; formula evaluator; SVG renderer with PNG/PDF extra and visual regression vs Visio; free-threading tests |
| v2.1.0 — CLI, draw.io bridge and JSON model | 2028-11-30 | `vsdxkit` CLI; .drawio import/export; interoperability CI corpus; versioned JSON model; XSD validation |
| v2.2.0 — Diagrams as code and layout | 2029-02-28 | Builder API; grid/tree/layered/swimlane layouts; orthogonal routing; DOT and Mermaid import, export to both |
| v2.3.0 — Agents and SVG import | 2029-05-31 | `vsdxkit-mcp` with PNG preview; SVG → editable shapes |
| v3.0.0 — Authoring, macros and long-term support | 2029-08-31 | Write .vssx/.vstx; .vsdm with VBA preserved; data graphics/linking/validation rules read; plugin entry points; LTS policy; Python floor 3.13 |

## Epics per milestone

### v0.7.0 — Hardening and first PyPI release
- **E-070-A Close the fork's open integrity defects** — the eight open issues (#7, #8, #9, #13, #15, #16, #17, #18) plus six new fixes: default-namespace serialisation, `Sheet.N` remap, `.vsdm` save-as kind mismatch, side-effect-free `DataProperty.value`, `Shape.remove()` cascade, one `Media` load per document.
- **E-070-B Release engineering** — PyPI Trusted Publishing, tag-triggered release with PEP 740 attestations and GitHub Release assets, release checklist, Read the Docs, 0.x API notice, macOS + 3.15 in CI, coverage ratchet, cut 0.7.0.
- **E-070-C Test hermeticity and fixture hygiene** — no writes under `tests/`, Geometry tests, unskip diff tests, COM corpus documentation.
- **E-070-D Upstream reconciliation** — port community PRs #84–#89 with attribution, offer universal fixes upstream, quarterly sync procedure.

### v1.0.0-alpha — Behaviour oracle, PackageStore, MasterCatalog
- **E-10A-A Phase 0** — manifest helper and canonical-XML rule, API-coupled driver, contract scenarios, COM oracle with JSON expectations, executable README test, strict xfail ratchets, migration guide skeleton.
- **E-10A-B Phase 1 PackageStore** — OPC-relative parts with promotion, byte-preserving atomic save, package kind from content types, delete `zip_file_contents`.
- **E-10A-C Phase 2 MasterCatalog** — relationship helpers, catalog, remove the mixin, page lifecycle on the helpers.
- **E-10A-D Error hierarchy** — `vsdx/errors.py`.
- 10A-R1 publish 1.0.0a1.

### v1.0.0-beta — Collections, identity and single mutation paths
- **E-10B-A Phase 3** — `shape_tree.py`, `PageCollection`, `ShapeCollection` with multiplicity semantics, identity and `is_attached`, cache policy, remove synthetic wrapper and duplicate finders.
- **E-10B-B Phase 4** — single creation operation, single deletion with detachment, connector engine with `ConnectorOptions`.
- 10B-R1 publish 1.0.0b1.

### v1.0.0 — Public API cutover
- **E-100-A Phase 5** — `Document`, `Connector`, `SwimlaneDiagram`, enums and `Page.create_shape`, remove old exports and finish the migration guide.
- **E-100-B Phase 6** — `render_document()`, no runtime root imports with an import-graph test.
- **E-100-C Phase 7** — drop `deprecation`, delete dead statics, type-completeness gate.
- **E-100-D Phase 8** — policies page, installed-wheel + COM verification, publish and announce.

### v1.1.0 — Documents from nothing
- **E-110-A Create a document without a source file** — blank donor, `Document.new()`, bytes/file-like I/O, guide.
- **E-110-B Copy shapes and pages between documents** — StyleSheet import by name, cross-document copy.
- **E-110-C Page setup, background pages and document properties** — `Page.setup`, layout-and-routing settings, background pages, core/custom properties with `app.xml`/`windows.xml` consistency.
- **E-110-D Package validator** — OPC structural checks, repair-risk lint, `save(validate=True)`.
- 110-E1 drop Python 3.10; 110-R1 publish.

### v1.2.0 — Text and Shape Data fidelity
- **E-120-A Rich text model** — design spike, read runs/fields, field-preserving writes, field refresh from Shape Data, text block cells.
- **E-120-B Shape Data completeness** — full Property rows, typed values, tabular export/import.
- **E-120-C User cells and hyperlinks**.
- 120-S1 MCP server spike; 120-R1 publish.

### v1.3.0 — Stencils, geometry and groups
- **E-130-A Stencils and templates** — open .vssx/.vstx, drop external masters, bundled stencil catalogue, `Document.new(template=)`.
- **E-130-B Geometry completeness and a path builder** — all row types, multiple sections, builder, connection points, transforms.
- **E-130-C Groups, generic containers and CFF creation** — group/ungroup, containers and lists, CFF on a plain page with vertical orientation and phases, callouts.
- 130-R1 publish.

### v1.4.0 — Media, layers, themes and effective styles
- **E-140-A Images and foreign data** — read, insert/replace, thumbnail policy.
- **E-140-B Layers** — read, create/assign/flags.
- **E-140-C Themes and effective style resolution** — theme parsing, StyleSheet chain and `shape.effective`, apply theme/quick style.
- **E-140-D Comments**.
- 140-R1 publish.

### v2.0.0 — Performance, headless SVG rendering, Python 3.12+
- **E-200-A Performance** — benchmark suite and large fixtures, lazy loading, ID/incidence indexes, master wrapper cache, lxml spike.
- **E-200-B SVG renderer** — architecture spike, formula evaluator, path builder, styles, text, page/document API with PNG/PDF extra, visual regression vs Visio.
- **E-200-C Platform** — drop 3.11, free-threaded job and thread-safety contract, add 3.16.
- 200-R1 publish.

### v2.1.0 — CLI, draw.io bridge and JSON model
- **E-210-A CLI** — skeleton, inspect, render/validate, semantic diff (replaces `VisioFileDiff`), template/convert, docs and completion.
- **E-210-B draw.io bridge** — mxGraph mapping spike, import, export, interoperability CI corpus (LibreOffice headless, draw.io).
- **E-210-C Versioned JSON document model**.
- **E-210-D XSD schema validation**.
- 210-R1 publish.

### v2.2.0 — Diagrams as code and layout
- **E-220-A Declarative builder API** — model and compiler, shape-kind catalogue, tutorial.
- **E-220-B Layout primitives and routing** — grid/align/auto-size, tree, layered DAG, orthogonal routing with explicit geometry, swimlane-aware layout.
- **E-220-C DOT and Mermaid** — import both, export both.
- 220-R1 publish.

### v2.3.0 — Agents and SVG import
- **E-230-A MCP server** — package/transports/tools, safety, docs.
- **E-230-B SVG import** — parser to path builder, CLI and matplotlib recipe.
- 230-R1 publish 2.3.0 and `vsdxkit-mcp` 0.1.

### v3.0.0 — Authoring, macros and long-term support
- **E-300-A Authoring and macros** — write .vssx, write .vstx, .vsdm with VBA preserved and `strip_macros()`.
- **E-300-B Advanced features read-first** — data graphics and data linking, validation rules and Solutions XML.
- **E-300-C Platform, plugins, LTS** — Python 3.13 floor and 3.17, entry-point plugins, LTS policy and 2.x branch.
- 300-R1 publish.

## Decisions and rationale

**Publish 0.7 to PyPI before the 1.0 rename.** The 1.0 plan reasoned that not being on PyPI made this the moment to break freely. That remains true for the API; but a three-year roadmap needs a distribution channel from day one, 0.x already signals instability under semver, and release machinery should fail on a low-stakes release rather than on 1.0. Mitigation: README/PyPI/RTD notice, pre-releases before 1.0, complete migration guide.

**Execute the 1.0 plan as four milestones, unchanged in substance.** Phases 0–2, 3–4, 5–8 map to alpha, beta, final. The plan's DRY rejection list and definition of done are inherited verbatim. Two small additions: the namespace-serialisation and `Sheet.N` remap fixes land in 0.7 so Phase 0 freezes correct behaviour, and page lifecycle moves onto the relationship helpers in Phase 2.

**Pull stencils and geometry ahead of media and themes.** Original ordering had media/layers/themes at 1.3. Research showed vendor-stencil reuse and custom geometry are both the most-demanded creation capabilities and hard prerequisites for the renderer and every import bridge, so 1.3 is stencils/geometry/groups and 1.4 is media/layers/themes (themes being the last prerequisite for rendering in 2.0).

**Rendering is the Year 2 capstone, not a Year 3 feature.** Headless SVG/PNG is the second-strongest demand signal and the enabler for agent workflows (an agent must be able to look at what it drew). It needs effective-style resolution (1.4), geometry completeness (1.3) and a formula evaluator (2.0); therefore 2.0.

**draw.io bridge in 2.1 rather than 2.3.** draw.io's removal of VSDX export is the loudest single ecosystem signal; the bridge depends on the path builder (1.3), text (1.2) and stencil masters (1.3) and so is the first Year 3 deliverable.

**MCP server at 2.3, with a spike at 1.2.** The server needs the JSON model (2.1) and renderer (2.0) to be useful, but an early throwaway prototype tells us which API affordances agents need before the 2.x surface hardens.

**Python-version policy.** Floor is the oldest non-EOL CPython at the time of a minor release: 3.10 dropped at 1.1 (after its Oct 2026 EOL and after 1.0 ships on the plan's declared 3.10–3.14 range), 3.11 dropped at 2.0, 3.12 dropped at 3.0. New CPython (3.15 Oct 2026, 3.16 Oct 2027, 3.17 Oct 2028) enters CI within one release of final. Free-threaded builds are tested from 2.0.

**GPL code is not reused.** `libvisio-ng` (GPL-3) is a reference for expected rendering behaviour only; no code or fixtures are copied. Bundled stencils are saved from Visio with provenance notes and a redistribution check.

**Year 3 is decomposed to the level defensible today.** Each Year 3 epic is re-decomposed when its milestone becomes the next one up; the tickets present are the ones with clear scope now.

## Non-goals (unchanged from the 1.0 plan, plus two)

- Renaming the `vsdx` import namespace.
- Re-implementing Visio's full layout engine; 2.2 provides readable placement and routing, not Visio parity.
- Driving Visio through COM at runtime; COM is an oracle only.
- Binary `.vsd` (Visio 2003–2010) read or write. libvisio and Aspose cover it; the OLE format is a separate project.
- A hosted service or GUI.

## Risks

| Risk | Mitigation |
|---|---|
| The 1.0 refactor stalls mid-way and leaves two representations live | Phases are serial PRs each leaving `main` executable; the Phase 0 oracle is API-independent so any phase can be reverted without losing tests |
| COM verification becomes a bottleneck (one Windows machine with Visio) | `needs-visio` label makes the dependency explicit; batch COM runs per milestone; grow the COM fixture corpus so most changes are covered by manifests alone |
| Renderer fidelity expectations exceed what pure Python can deliver | 2.0 scope is written down (no gradients/effects/text-on-path); visual regression uses per-fixture tolerances; PNG/PDF via optional extras |
| Bundled stencil redistribution | Provenance and licence check is a ticket (130-A3); fall back to shipping only shapes drawn by the project |
| Single-maintainer velocity | Quarterly milestones with P0/P1/P2 tiers; P2/P3 slip without blocking a release; `good first issue` tickets seeded in every milestone |

## Working the board

- Every issue has a `[KEY]` prefix; epics are `E-…`. Pick a ticket whose *Blocked by* list is empty or closed in the earliest open milestone.
- Priority, Size and Horizon are project fields; kind, area and flags are labels.
- Release tickets (`…-R1`) close a milestone; they are blocked by every epic in it.
- Re-decompose an epic (add sub-issues) when its milestone becomes the next one up.
- Keep this document and the project README in sync when the plan changes; record why.
