# Phase 3E: computed by default, and one counter for the cache that stays (#102)

**Status:** Implementing. Stacked on Phase 3D (#395).
**Plan:** `2026-09-12_simplification-usability-refactor.md`, Phase 3.
**Issue:** #102 (10B-A5).

## Problem

Since #101, two Shape objects for one shape are equal. Four reads were held per
object, so a write through one object was not read through the other:

- **`Shape.cells`.** A snapshot of the cells, taken in `__init__`. A cell added
  through another object, or straight into the XML, was invisible, and a removed
  one was still answered.
- **`Shape.data_properties`.** Keyed on the identity of the Property rows. An
  in-place relabel stayed keyed under the old label, and an edit to the master
  was never picked up.
- **`Page.background`.** Held after the first read.
- **`Shape.master_shape`.** Keyed on the reference and the master element's
  children. A shape that looked for a master before the document had it kept
  `None` after it arrived.

## Measurements

`tools/bench_shape_reads.py` times seven workloads on s05 page 1 and on the same
page grown to 1,034 shapes. Base is Phase 3D (273dd87). Both were run
interleaved, five rounds each, taking the best per workload.

| 1,034 shapes | Base | Computed | Ratio |
| --- | --- | --- | --- |
| walk (`all_shapes`, IDs) | 9.41 ms | 1.69 ms | 0.18× |
| geometry (`x`, `y`, `width`, `height`, `text`) | 39.15 ms | 21.03 ms | 0.54× |
| the same, read 10× per Shape object | 69.62 ms | 124.87 ms | 1.79× |
| cells | 9.75 ms | 12.00 ms | 1.23× |
| properties | 42.61 ms | 15.44 ms | 0.36× |
| properties, read 10× per Shape object | 58.95 ms | 95.43 ms | 1.62× |
| background × 1,000 | 0.02 ms | 0.86 ms | 43× |

On s05 alone (47 shapes), most ratios are the same. The exceptions:

| s05, 47 shapes | Ratio |
| --- | --- |
| geometry, read 10× | 1.88× |
| properties, read 10× | 1.75× |
| cells | 1.55× |

**`master_shape`, resolved on every read.** Also measured:

- reading a page's coordinates 10× went to 174 ms (2.2×);
- reading its properties 10× went to 140 ms (2.2×).

## Decisions

**D1. `Shape.cells` is computed.** It is a property that builds a fresh dict
from the XML, keyed as before: `Name`, `Geometry/{T}/{N}` and `Control/{row
N}/{N}`. It raises on a detached shape.

- **Internal lookups** go through `Shape._cell(name)`. A plain name scans the
  top-level cells alone; a section name goes through the same generator `cells`
  uses.
- **Writers** no longer register the cells they create: the next read finds them
  in the XML.
- **Construction cost.** Building a Shape no longer parses its cells, which is
  why a walk costs a fifth of what it did.

**D2. `Shape.data_properties` is computed.** Building each `DataProperty` now
reads its row's cells in one pass rather than four `Cell[@N=…]` searches. That
brought a first read to a third of the cached version's cost.

**D3. `Page.background` is computed.** `_page_xml` now indexes the Page children
directly: the `Page[n]` positional path made ElementPath build a parent map of
pages.xml on every call.

- **Ruling:** computed, although the ratio is 43×.
- **Why:** the gate exists to catch reads a caller would notice. One read is 0.9
  µs, cheaper than reading one cell. A held bool that goes stale when pages.xml
  is edited costs more than it saves.
- **Cost if wrong:** re-add it keyed on the counter in D4.

**D4. `Shape.master_shape` stays memoised, and the catalog's counter lets it
go.** Resolving on every read failed the gate at 2.2×.

- **The key** is the shape's `Master` and `MasterShape` attributes, read live,
  plus `MasterCatalog.revision`. The revision counts every `load` and every
  master added.
- **Kept:** `tuple(master.xml)` stays in the key. The master's cells and
  properties are read live through the Shape held, but that Shape locates its
  Geometry section when it is built, so a section added to, removed from or
  swapped on the master must rebuild it. The first cut dropped it, and Codex
  caught the stale Geometry on #396. The repeated-read numbers above are
  measured with it in the key.
- **Ruling: why not a document-wide counter.** One bumped in `_require_open` has
  two faults:
  - it would drop every memo on every cell write;
  - its bump precedes the write it guards, so a memo filled during that write
    would be stamped current.
  The catalog is the only place masters change (Phase 2), so its counter is exact.
  - **Cost if wrong:** move the counter to the document.

**D5. `Shape.geometry` is unchanged.** It is a merged view that writes to the
XML, not a read cache, and the issue does not name it.

- **Where it stands:** a Shape object builds it once. Another object's first
  read sees every write made through it.
- **Limitation:** an object that has already built its Geometry does not see a
  later write made through another object.

## Breaking

- `Shape.cells` is read-only and new on each read. Assigning into the dict no
  longer changes what the shape reads, and two reads are two dicts.
- `Shape.cells` on a detached shape raises `InvalidOperationError`, as the other
  reads do (#101).

## Tests

`tests/test_cache_policy.py` has six tests, each failing on the base or on the
first cut:

- a cell added through one Shape object is read through another;
- a cell removed from the XML is gone;
- a property relabelled in place is keyed under its new label, through both objects;
- `Page.background` follows pages.xml;
- a master added after a shape missed it is resolved;
- a Geometry section swapped on an already-resolved master is the one merged.

Also: `test_the_section_is_located_when_the_shape_is_built` now asserts that
`cells` is live, and the #101 detached-read test covers `cells`.
