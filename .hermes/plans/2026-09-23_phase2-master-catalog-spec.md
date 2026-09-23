# Phase 2: `MasterCatalog` owns master state

**Status:** in implementation. The maintainer said to "keep driving for the next major phase" and not to stop at each gate.
**Date:** 2026-09-23
**Issues:** #93 (C2), #94 (C3), #375, #331, #357, #367. #95 (C4) comes next, in its own PR.
**Design:** `.hermes/plans/2026-09-12_simplification-usability-refactor.md`, Phase 2, as amended on 2026-09-23 (no re-exports; `Protocol` seams; public annotations resolve at runtime).
**Stacked on:** #384 (dependency inversion).

## Problem

Master state has five owners and two bootstraps.

- `MastersImportMixin` is bolted onto `VisioFile`. It declares `_package`, `master_pages`, `master_index` and `masters_xml` as host attributes and stubs the host's methods, and it builds a `Page` with `cast("VisioFile", self)`.
- `VisioFile.load_master_pages()` appends to `master_pages` and `master_index` without clearing them, so a second call lists every master twice (#375).
- `Connect.create` has its own bootstrap for a document with no masters (#375). It copies every donor master part, hardcodes `master1.xml` and `rId1`, and reloads the masters through the method that isn't idempotent.
- `Shape.copy` into another document never imports the master, so Visio drops the copy on open (#331).
- `Page._ensure_page_master_rel` is handed a relationship id from `masters.xml.rels`, a different id space from the page's own rels part, and guards on `Target` only (#357).
- `_bootstrap_masters` is reachable only by calling it directly (#367).

## Decisions

**D1. `MasterCatalog` lives in `vsdxkit.masters` and is the sole owner of master state.**

```python
MasterPageFactory = Callable[[PartTree, str, str, str, str], Page]  # tree, part name, name, id, rel id

class MasterCatalog:
    def __init__(self, store: PackageStore, make_page: MasterPageFactory) -> None
    def load(self) -> None                       # idempotent: rebuilds from the store
    @property
    def pages(self) -> list[Page]                # a copy, in masters.xml order
    def by_id(self, master_id: str) -> Page | None
    def by_name(self, name: str) -> Page | None  # NameU, falling back to Name
    def element_by_id(self, master_id: str) -> Element | None
    def bootstrap(self) -> None                  # the one bootstrap; a no-op once masters exist
    def import_masters(self, source: MasterCatalog, master_ids: Iterable[str]) -> dict[str, Page]
```

- **No upward import.** `masters` never imports `vsdxkit.vsdxfile`: the document hands the catalog a factory for master pages. This is dependency inversion under the amended rules, so every public annotation on the catalog resolves at runtime.
- **What `import_masters` does.**
  - **Dedup.** It deduplicates by name (`NameU`, else `Name`), which is Visio's MatchByName. A master with neither name matches nothing and is always imported. Two masters of one name in the same batch are imported once.
  - **Atomic.** It reads every source part before changing anything, so one unreadable master leaves the target as it was.
  - **Writes.** It bootstraps if needed. It writes each part under the first unused `masterN.xml`, not `len + 1`, which collides after a gap. It allocates the master ID, allocates the relationship through `relationships.append_if_absent`, registers the content types and the document relationship, and records the new page.
  - **Result.** It is keyed by the source's master ID. An ID the source cannot resolve is left out.
- **No logging in `masters`.** The per-master debug dump stays in the document, behind its own `debug` flag.

**D2. `VisioFile` holds one private catalog, and the mixin is deleted (#94).**

- `self._masters` is built in `open_vsdx_file`.
- `master_pages` and `master_index` become read-only properties over the catalog. The public API stays until Phase 5, and nothing assigns to them.
- `get_master_page_by_id` and `load_master_pages` go through the catalog.
- `_ensure_masters_for_shape` and `_bootstrap_masters` are deleted: they are private, so this breaks them rather than shims them.
- `VisioFile` keeps one base class, `JinjaTemplatingMixin`, which Phase 6 removes. No `cast("VisioFile", self)` remains.

**D3. One import operation on the document: `VisioFile._masters_for(master_ids, source) -> dict[str, Page]`.**

- It requires an open document.
- From the same document, it only resolves the IDs.
- From another document, it imports through the catalog and lists each newly added master's name in `app.xml`'s TitlesOfParts.
  - Today only `Connect.create` does that, and it uses the connector shape's name. What TitlesOfParts means is the master's own name (`NameU`, else `Name`). That name choice is not yet checked against Visio.
  - The TitlesOfParts section is resolved before anything changes.
  - A document without `app.xml` has no titles to keep in step, so the listing is skipped and the operation goes ahead (#385).

**D4. `Connect.create` has one path (#375).** Import the connector master, copy the shape, repoint `master_page_ID`, and relate the page to the master. The masterless branch goes, with its hardcoded `master1.xml`/`rId1` and its wholesale copy of donor masters.

*Deliberate output change:* a masterless document that gains a connector now gets exactly one master part, not every master the donor holds. The output probe is re-baselined, and the diff is reviewed to confirm it is only this.

**D5. `Shape.copy` resolves masters before it copies (#331).**

- **Resolve.** Every `Master` reference in the copied subtree is resolved through `_masters_for`. From another document, the master is imported, deduplicated by name. The copy is rewritten to use the resolved IDs.
- **Page relationships.** Every master the destination page now uses gets a page relationship. That includes a copy to another page of the same document, as Visio writes it.
- **Sub-shapes.** A sub-shape of a master instance names no `Master`: it inherits its group's. Copied onto a page, it leaves that group. So the root of the copy names the inherited master, or its `MasterShape` would reach into nothing. This is not yet checked against Visio.
- **Unresolvable masters.** A `Master` the source cannot resolve is stripped, along with its `MasterShape`, but only on a cross-document copy. There it would name a master the target package does not declare. Within one document, it is left as it was.

**D6. Page master relationship ids are allocated, not handed in (#357).** The signature becomes `Page._ensure_page_master_rel(master_part_name)`. It uses `relationships.append_if_absent`, which finds an existing relationship by type and target or allocates a free id in the page's own rels part.

**D7. #367 is closed with a test that goes through public operations.** Copy a master instance into a document with no masters part, save, and reopen. The bootstrapped `masters.xml` must carry exactly the imported master. The part is store-backed now, so the bootstrap's output survives. The two tests that call `_bootstrap_masters` directly move to `MasterCatalog.bootstrap`.

## Out of scope

- #95: page lifecycle through the relationship helpers, and unused page part names. It's the next PR in the stack.
- COM checks on `test3_house` and `s07_point_glue_masters`: no Visio in this environment. The structural validator, which every saved package in the suite runs through, stands in, and the issue records the gap.
- `Page.is_master_page` and `_pagesheet_xml` still read `vis.masters_xml`. They move when Phase 3 replaces the page's back-reference.

## Acceptance

- One master index, and one bootstrap. `load` is idempotent (a second call leaves `master_pages` unchanged).
- Importing the same master twice yields one part, one `Master` element and one relationship.
- Copying a master instance across documents and saving passes the validator, and the shape survives a reopen.
- A page rels part that already holds `rId1` gets a fresh id for its master relationship.
- `masters.py` doesn't import `vsdxfile`, `VisioFile` has one base class, and no `cast("VisioFile"...)` remains.
- The annotation ratchet gains no entries, and `test_imports` passes.
- Gates: pytest on 3.14 and 3.10; ruff; pyrefly strict; the mypy fixture; Sphinx `-W`; and the output probe. The canonical sweep of the probe workload over every fixture came out identical except in two reviewed places. `test5_master` now completes its connector, where it used to fail halfway because the file has no app.xml (#385). `test6` gets a page relationship id allocated from its own rels part (#357).
