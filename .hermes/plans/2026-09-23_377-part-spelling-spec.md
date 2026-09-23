# Write an edited part in the spelling it arrived in (#377): design

**Status:** deferred, 2026-09-23. Not to be built until one of the reopen conditions in [Decision](#decision-deferred) holds.
**Issue:** #377 (P3; no longer blocks #91)
**Related:** #89 (byte-preserving save, merged), #360/#364 (`serialise_part` is the only writer), #282 (a part keeps its declared prefixes), `tests/fixtures/package_manifests/KNOWN_DRIFT.md`

## Problem

Since #89, saving a document writes every part the library did not change as the bytes it arrived as. A part the library *did* change is serialised by `ElementTree.write`, which spells XML differently from Visio:

1. **The declaration is rewritten.**
   - Visio writes `<?xml version='1.0' encoding='utf-8' ?>` on its own parts.
   - It writes `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` on package parts.
   - Both come back as `<?xml version='1.0' encoding='UTF-8'?>`.
2. **The CRLF after the declaration is dropped.**
3. **Attributes are double-quoted.** Visio single-quotes the attributes of its own parts.
4. **Empty elements get a space:** `<a />`, not `<a/>`.
5. **CRLF in text becomes LF.**
6. **`'` in text is written raw.** Visio writes `&apos;`.
7. **Unused namespace declarations are dropped.** Visio declares `xmlns:r` on the root of every page, master and `document.xml`.
8. **Namespace declarations are hoisted to the root.**

What goes wrong as a result:

- **Noisy diffs.** Change one cell on one page, and that page's archive member differs from the original across most of its bytes, not just the cell. Tools and people who diff packages, review saved documents or store them in version control see the whole part rewritten.
- **Sticky spelling.** Once a part has been edited and saved, it keeps ElementTree's spelling for good. A later session that undoes the edit cannot get back to what Visio wrote. `tests/test_metamorphic.py` has to allow for this, and `KNOWN_DRIFT.md` documents it.
- **Blocks #91 as written.** #91's acceptance criteria require `KNOWN_DRIFT.md` to be empty and deleted.
- **The roadmap principle** "File-format fidelity is the contract" (`.hermes/plans/2026-09-13_three-year-roadmap.md`).

### What is *not* known to be a problem

- **There is no evidence that Visio rejects or repairs ElementTree's spelling.** Every release before #89 rewrote every part in that spelling. No issue in this repo or in upstream `dave-howard/vsdx` reports Visio refusing it.
- **The interoperability failure fixed earlier had a different cause.** The known failure in LibreOffice and draw.io (upstream #90, #35) came from `ns0:` prefixes, and #60/#282/#360 fixed it. It was not caused by quoting, declarations or empty-element form.
- **All the spelling differences are XML-equivalent.** Every difference listed above is equivalent under the XML spec. The one semantic difference is the dropped unused `xmlns:r`, and it only matters to a consumer that looks up prefixes by name inside attribute values; none is known.

## Corpus facts

These come from a survey of all XML parts in the 29 packages under `tests/`.

| | Package parts (rels, `[Content_Types]`, docProps) | Visio parts (pages, masters, document, windows, …) |
|---|---|---|
| Declaration | `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` | `<?xml version='1.0' encoding='utf-8' ?>` |
| After the declaration | CRLF | CRLF |
| Attribute quote | `"` | `'`; `"` for a value that contains `'` |
| Empty element | `<a/>` | `<a/>` |
| Escapes | `&amp; &lt; &gt;` | `&amp; &lt; &gt;` in attributes, with `"` raw inside `'`-quoted values; `&apos;` for every `'` in text, with `"` raw |
| CRLF in text | none seen | 58 of 118 drawing parts |
| `xmlns` below the root | none | one page (Lucidchart `lc:` on each `lc:Property`), and `theme1.xml` |

`test5_master.vsdx` has no producer name in `app.xml`. Its parts use LF after the declaration and double quotes throughout, and its `masters.xml` has no declaration at all. The design has to handle a producer that is not Visio, per part.

## Goals

- **G1.** Serialising a part's tree unchanged reproduces its original bytes exactly, for every XML part of every package in the corpus. Any exception is named, with its reason, in the test's exception list, which starts empty.
- **G2.** An edit changes the bytes of the elements it changed and nothing else in the part.
- **G3.** A part built from nothing (a new page, rels part or master) is spelled the way Visio spells a part of that kind.
- **G4.** `serialise_part` stays the only writer. Byte preservation and canonical hashing are unchanged. No new runtime dependency.
- **G5.** `KNOWN_DRIFT.md` is deleted, and `test_metamorphic.py`'s cross-session spelling allowance is removed.

## Non-goals

- Reproducing quirks outside the rules above, such as whitespace inside tags or the order of attributes in `'` versus `"`.
- Attribute order: ElementTree already keeps the parsed order.
- Anything in #91.
- Changing the canonical-hash baseline.

## Design

### 1. Capture: `PartSpelling`, recorded by `parse_part`

`parse_part` already has the raw bytes and the `start-ns` events. It will record a frozen `PartSpelling` against the root element, replacing `_declared_prefixes`, which is keyed and held weakly the same way:

- `declaration: bytes | None`: the declaration exactly as written, or `None` when there is none.
- `after_declaration: bytes`: `b"\r\n"`, `b"\n"` or `b""`.
- `quote: str`: the part's default attribute quote, taken from its first attribute.
- `text_newline: str`: `"\r\n"` if any text or tail in the part held a CRLF, otherwise `"\n"`.
- `namespace_declarations: Mapping[Element, tuple[tuple[str, str], ...]]`: the `(prefix, uri)` pairs each element declared, in document order, unused ones included. `start-ns` events arrive just before the `start` event of the element that declares them.

### 2. Write: a small element writer in `xmlio`

`serialise_part` stops calling `ElementTree.write`. It walks the tree itself:

- **Declaration.** Write `spelling.declaration`, then `after_declaration`.
- **Tags.** Use the prefix map from today's `_prefixes_for`.
- **Namespace declarations.**
  - Each element re-emits the declarations it recorded, in their original order.
  - A namespace used by the tree but declared by no recorded element (one introduced by an edit) is declared on the root, after the root's recorded declarations.
  - The `xml` namespace is never declared.
- **Attributes.** Keep the parsed order. Use `spelling.quote`, unless the value contains that quote and not the other, in which case use the other quote. Escape `&`, `<`, `>` and the chosen quote.
- **Text and tails.**
  - Escape `&`, `<` and `>`.
  - In a Visio-part spelling, also write `'` as `&apos;`. Whether `&apos;` is always written, or tracked per part, is settled by G1's corpus test.
  - Write `\n` as `spelling.text_newline`.
- **Empty elements.** An element with no text and no children is written `<tag .../>`.

### 3. Defaults for parts built from nothing

A tree with no recorded spelling takes one of two module constants:

- `VISIO_PART_SPELLING` if its root is in the Visio main namespace (`http://schemas.microsoft.com/office/visio/2012/main`).
- `PACKAGE_PART_SPELLING` otherwise.

Both values come from the corpus table above.

### 4. Where it plugs in

- `serialise_part(tree)` keeps its signature.
- `PackageStore`, the `zip_file_contents` view and `write_bytes_keeping_tree` are unchanged, because they already go through `parse_part` and `serialise_part`.
- A tree rebuilt from another with `adopt_prefixes` also adopts the source's spelling. The #282 hook becomes "adopt spelling".

## Testing

- **G1.** Parametrise over every XML member of every package under `tests/`, and assert `serialise_part(parse_part(data)) == data`. The exception list starts empty.
- **G2.** For each fixture, change one cell's `V` on page 1, save, and assert that the byte diff of that member against the original is confined to that attribute's value.
- **G3.** A new page from `add_page`, a new page-rels part and an imported master's rels part are each spelled with the default for their kind.
- **G5.**
  - `test_package_manifest.py` stays green, and it will be.
  - The spelling allowance in `test_metamorphic.py` goes. `test_deleting_a_copy_made_before_the_last_save_restores_the_package` asserts full byte equality with the original.
  - `KNOWN_DRIFT.md` is deleted.
- **Escaping.** Unit tests cover each rule in section 2, plus the per-attribute quote fallback.
- **needs-visio.** The COM oracle opens every fixture after a one-cell edit, with no repair prompt. This runs on the maintainer's Windows machine.

## Risks

- **Other producers' parts.** A part from a producer other than Visio may not round-trip. G1's exception list surfaces this, and nothing silently changes.
- **Performance.** A Python-level writer is slower than the C-accelerated `ElementTree.write`. It runs only for changed parts. Measure a 1,000-shape page before and after.
- **Scope creep.** "Spelling" can grow without limit. The rules above are the whole contract, and G1's corpus test is what defines "done".

## Decision: deferred

An adversarial review on 2026-09-23 asked whether this needs to exist. It found no consumer that minds ElementTree's spelling, and the maintainer deferred the work.

### Why

- **Visio accepts ElementTree's spelling.** The COM oracle recordings of 2026-09-14 (#297, #315) were made before #89, when every part was rewritten. All 21 opened, with matching pages, shapes and glue. The harness sets `AlertResponse=7` and answers dialogs itself, so a repair prompt would not have been recorded.
- **LibreOffice accepts it.** The CI import job passed on fully rewritten output before #89.
- **Every release up to 0.8.0 wrote it**, and no issue here or upstream blames it. The known interoperability failures were `ns0:` prefixes, fixed by #60, #282 and #360.
- **Dropping unused `xmlns:r` breaks nothing known.** 162 of the corpus's 414 XML parts declare a prefix they do not use, and none of them uses a prefix inside an attribute value or text.
- **Noisy diffs are not a real cost.** A Visio page part is one line after its declaration, so a line diff shows the whole part either way. After a one-cell edit, 85–94% of the part's bytes already match.
- **#91's `KNOWN_DRIFT.md` criterion predates #89.** The simplification plan and epic #22 ask for a byte-identical no-op save. #89 delivers that, and `test_a_round_trip_changes_nothing` enforces it.

Building it looks feasible, at 3–5 days plus a Visio session. A throwaway writer of about 120 lines reproduced all 414 corpus parts once two rules missing from this spec were added. The cost is a hand-written writer for every edited part, while the same milestone has bugs users actually hit (#331, #313, #317, #319).

### Reopen when

- a consumer (Visio, LibreOffice, draw.io, a validator or a user's tooling) is shown to reject or repair a part in ElementTree's spelling, or
- #293's Visio evidence shows Visio treats the spelling differently, or
- a user asks for edited parts to diff cleanly against the original.

### Defects to fix first if this is reopened

1. **Empty-element form differs by part.** `docProps/core.xml`, `app.xml` and `custom.xml` write `<a></a>` in 84 parts, and `app.xml` is edited whenever a page is added, renamed or removed. The corpus table above is wrong about this, and `PartSpelling` has no field for it. A part already saved as `<a />` must not be respelled a third way.
2. **Attributes can come before namespace declarations.** `windows.xml` does this in all 29 fixtures, so the interleaving has to be recorded, not just the declarations.
3. **Encoding.** Copying a non-UTF-8 declaration onto UTF-8 output corrupts text (`café` became `cafÃ©` in a probe). Write the recorded declaration only when it says UTF-8, or encode to match it.
4. **CRLF.** Mapping every `\n` to `\r\n` turns text a caller set as `"a\r\nb"` into `a\r\r\nb`, which reads back with an extra line. CRLF detection also needs the raw bytes, because the parser has already folded them.
5. **Rebuilt trees lose recorded declarations.** Declarations keyed by element identity do not survive templating, `copy_page` or `deepcopy`, so a templated page still loses `xmlns:r`.
6. **Comments and processing instructions** are not handled.
7. **Namespaced attributes** cannot use a default (unprefixed) namespace.
8. **The `&apos;` rule is undefined.** Record it per part or derive it from the corpus; do not leave it to the test.
9. **`PartSpelling` keeps deleted elements alive** if it maps elements strongly.
10. **Performance is not a risk.** `ElementTree.write` is pure Python. The prototype took 38 ms against 45 ms for `ElementTree.write` on a 1,000-shape page.
11. **G1 tests a path that never reaches disk**, since an unchanged part is written as its original bytes. G2 is the real definition of done, and it should cover `app.xml`, a templated page and the Lucidchart page.
12. **"No repair prompt" cannot be observed** while the oracle answers dialogs itself. The needs-visio criterion needs a harness change or different wording.

The smallest useful piece, if one is wanted without the rest: keep the recorded declaration and the newline after it when the declared encoding is UTF-8. That is about 15 lines.
