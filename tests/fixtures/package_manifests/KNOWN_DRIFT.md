# Known re-serialisation drift

Until #89, opening a fixture and saving it without changing anything gave back
an archive that was not byte-identical to the one that went in. This file
records what moved and why.

**A no-op save no longer moves anything.** Since #89 a save writes every part
it did not change as the bytes it arrived as, so
`test_a_round_trip_changes_nothing` in `tests/test_package_manifest.py` allows
no drift at all, over all 29 packages. What follows still describes what
happens to a part the library *does* change: it goes out through the same
serialiser, and picks up the same spelling differences listed below.

The numbers come from running `tests/test_package_manifest.py` over all 29
packages under `tests/` before #89, comparing each member of the source
archive with the same member of the saved one.

## What did not move

Across every fixture:

- **The member names, and their order in the archive.** Nothing is added,
  removed or moved.
- **Every non-XML member.** The images, `docProps/thumbnail.emf` and
  `visio/vbaProject.bin` come back byte for byte.
- **The XML parts `save_vsdx` did not write**: `_rels/.rels`,
  `docProps/core.xml`, `docProps/custom.xml`, `visio/masters/masters.xml`,
  `visio/masters/_rels/masters.xml.rels`, `visio/theme/theme1.xml`,
  `visio/validation.xml`, `visio/windows.xml`. These were copied out of the
  source archive untouched.
- **Attribute order inside an element.** ElementTree keeps the order it parsed,
  and no element in the corpus comes back rearranged.
- **The XML itself.** Every part of an unchanged package comes back
  canonically equal to the one that went in, third-party vocabularies
  included: the prefix a document chose is the prefix it is written back
  with (#282). What moves below is spelling.
- **The content type declared for `/visio/document.xml`**, which is what makes a
  package macro-enabled. `diagram_with_macro.vsdm` is still macro-enabled after
  a round trip.

## What did move

Every part `save_vsdx` wrote went back out through `ElementTree.write`, and
what it produces is not what Visio wrote. The save path adds nothing of its own:
each saved part is byte-identical to re-parsing the original and writing it
straight back through `vsdxkit.xmlio.serialise_part`. Every difference below
comes from that one round trip through ElementTree.

| Part | What changes | Fixtures |
| --- | --- | --- |
| `[Content_Types].xml` | declaration, bytes | 29 of 29 |
| `docProps/app.xml` | declaration, bytes | 28 of the 28 that have it |
| `visio/_rels/document.xml.rels` | declaration, bytes | 29 of 29 |
| `visio/pages/pages.xml` | declaration, bytes | 29 of 29 |
| `visio/pages/_rels/pages.xml.rels` | declaration, bytes | 29 of 29 |
| `visio/pages/_rels/pageN.xml.rels` | declaration, bytes | all that have them |
| `visio/document.xml` | declaration, namespaces, bytes | 29 of 29 |
| `visio/masters/masterN.xml` | declaration, namespaces, bytes | all 15 that have them |
| `visio/pages/pageN.xml` | declaration, namespaces, bytes | all but the one below |
| `page1.xml` in `fixtures/com_reference/s05_swimlanes_cfflow.vsdx` | declaration, bytes | 1 |

In the middle column, *declaration* is the XML declaration, *namespaces* is the
set of prefixes the part binds, and *bytes* is everything else.

### The causes

1. **The declaration is rewritten.** Visio writes
   `<?xml version='1.0' encoding='utf-8' ?>` on the drawing parts and
   `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` on the package
   parts. Both come back as `<?xml version='1.0' encoding='UTF-8'?>`, so
   `standalone="yes"` is dropped and the encoding changes case.
   `visio/masters/masters.xml` has no declaration at all in any fixture, and
   since nothing rewrites that part, it still has none afterwards.
2. **The newline after the declaration goes.** Visio writes `?>\r\n<PageContents`;
   ElementTree writes `?><PageContents`.
3. **Attribute values are requoted.** Visio writes `N='PinX'` in the drawing
   parts; ElementTree writes `N="PinX"`.
4. **Empty elements gain a space.** `<Cell N="PinX" V="1.25"/>` comes back as
   `<Cell N="PinX" V="1.25" />`.
5. **CRLF inside element text becomes LF.** `<Text>Master Shape A\r\n</Text>`
   comes back as `<Text>Master Shape A\n</Text>`. Every XML parser is required
   to fold CRLF to LF before the application sees it, so by the spec the two are
   the same document. The bytes still differ, and Visio wrote the CRLF.
6. **Namespace declarations the part does not use are dropped.** Visio puts
   `xmlns:r="…/officeDocument/2006/relationships"` on the root of
   `document.xml`, every `masterN.xml` and every `pageN.xml`, whether or not the
   part references a relationship; ElementTree emits only the prefixes in use.
   One page in the corpus does use it: `page1.xml` in
   `s05_swimlanes_cfflow.vsdx`, which carries a `ForeignData` image reference.
   It keeps its `xmlns:r`, which is why that fixture is the exception in the
   table.
7. **Namespace declarations are hoisted to the root.** `test5_master.vsdx`
   declares `xmlns:lc="http://www.lucidchart.com"` on each of the 28
   `<lc:Property>` elements that use it; ElementTree declares it once, on
   `<PageContents>`. The prefix is the one Lucidchart chose and the part is
   canonically unchanged, so the hoisting costs bytes and nothing else; that
   part's `namespaces` record moves for cause 6, like every other page.

## What #89 did, and what is left

Two things empty this file. The first is done: a part the library did not
modify goes back out exactly as it came in, which covers the whole table for a
no-op save.

The second is not: a part that *was* modified still goes out in ElementTree's
spelling, with every cause above applying to it. Matching Visio's own spelling
there -- the same declaration, the same quoting, the same empty-element form,
and the same namespace declarations, including the unused ones, on the
elements that declared them -- is separate work. Until it lands, a part edited
in one session keeps that spelling in every later save, even once a later
session undoes the edit; `test_deleting_a_copy_made_before_the_last_save_restores_the_package`
in `tests/test_metamorphic.py` allows exactly that and nothing more.
