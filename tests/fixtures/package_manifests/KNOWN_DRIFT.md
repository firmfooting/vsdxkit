# Known re-serialisation drift

Open a fixture, save it without changing anything, and the archive that comes
back is not byte-identical to the one that went in. This file says what moves
and why.

The numbers come from running `tests/test_package_manifest.py` over all 29
packages under `tests/`, comparing each member of the source archive with the
same member of the saved one.

`test_a_round_trip_stays_within_the_known_drift` allows exactly the drift listed
here and nothing else, so a change that makes the library write different bytes
fails that test instead of passing quietly. Issue #89 (byte-preserving save) is
the work that empties this file; when it lands, the allowances come out of the
test and this file should say so.

## Reproducing it

```
uv run pytest tests/test_package_manifest.py -q
```

A failure names the first member that differs, says which of its records moved,
and prints a unified diff of the canonical XML. To see the drift itself, take an
entry out of `RESERIALISATION_DRIFT` or `UNUSED_NAMESPACE_DECLARATIONS` in that
module and run it again.

## What does not move

Across every fixture:

- **The member names, and their order in the archive.** Nothing is added,
  removed or moved.
- **Every non-XML member.** The images, `docProps/thumbnail.emf` and
  `visio/vbaProject.bin` come back byte for byte.
- **The XML parts `save_vsdx` does not write**: `_rels/.rels`,
  `docProps/core.xml`, `docProps/custom.xml`, `visio/masters/masters.xml`,
  `visio/masters/_rels/masters.xml.rels`, `visio/theme/theme1.xml`,
  `visio/validation.xml`, `visio/windows.xml`. These are copied out of the
  source archive untouched.
- **Attribute order inside an element.** ElementTree keeps the order it parsed,
  and no element in the corpus comes back rearranged.
- **The content type declared for `/visio/document.xml`**, which is what makes a
  package macro-enabled. `diagram_with_macro.vsdm` is still macro-enabled after
  a round trip.

## What does move

Every part `save_vsdx` writes goes back out through `ElementTree.write`, and
what it produces is not what Visio wrote. The save path adds nothing of its own:
each saved part is byte-identical to re-parsing the original and writing it
straight back through `vsdx.xmlio.xml_to_file`. Every difference below comes
from that one round trip through ElementTree.

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
| `visio/pages/pageN.xml` | declaration, namespaces, bytes | all but the two below |
| `page1.xml` in `fixtures/com_reference/s05_swimlanes_cfflow.vsdx` | declaration, bytes | 1 |
| `page1.xml` in `test5_master.vsdx` | declaration, namespaces, canonical, bytes | 1 |

In the middle column, *declaration* is the XML declaration, *namespaces* is the
set of prefixes the part binds, *canonical* means the XML itself changed and not
only its spelling, and *bytes* is everything else.

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

### The Lucidchart prefix rewrite

`test5_master.vsdx`'s `visio/pages/page1.xml` carries Lucidchart
`<lc:Property>` elements bound to `http://www.lucidchart.com`. That namespace is
not in `vsdx.xmlio.NAMESPACE_PREFIXES`, so `_fallback_prefix` invents a prefix
from the URI, and the part comes back as
`<xwwwlucidchartcom:Property xmlns:xwwwlucidchartcom="http://www.lucidchart.com">`
where Visio wrote `<lc:Property xmlns:lc="…">`. ElementTree also hoists the
declaration to the root rather than leaving it on the element that uses it.

Nothing is lost semantically: the elements resolve to the same expanded names
either way. It is recorded here because the canonical hash can see it, and
because it runs on the same machinery as issue #60. Consumers stricter than
Visio do read prefixes, and the library does not preserve the ones it was
handed. Any part carrying a vocabulary the library has no entry for will be
respelled this way.

#89's byte-preserving save removes it along with everything else here, so it
needs no fix of its own.

## What #89 has to do

Two things empty this file. A part the library did not modify has to go back out
exactly as it came in, which covers most of the table: `save_vsdx` currently
rewrites all of those parts on every save whether anything in them changed or
not. A part that was modified has to be re-serialised in Visio's own spelling:
the same declaration, the same quoting, the same empty-element form, the same
namespace declarations including the unused ones, and the prefixes the source
used.
