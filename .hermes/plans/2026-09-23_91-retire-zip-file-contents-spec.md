# Address every part by its part name, and delete `zip_file_contents` (#91): design

**Status:** draft for review, 2026-09-23 **Issue:** #91 (roadmap `10A-B4`, P0,
v1.0.0-alpha) **Related:** #89 (the `PackageStore`, merged
as #370/#371/#373), #377 (deferred; no longer blocks this), #94
(`MasterCatalog`, next),
`.hermes/plans/2026-09-12_simplification-usability-refactor.md` Phase 1

## Problem

Since #89, `PackageStore` holds the open document, addressed by OPC part name
(`/visio/pages/page1.xml`). Everything above it still speaks the pre-store
dialect:

- **Pseudo-paths.** `VisioFile.directory` is the source path minus its extension
  (`/home/me/drawing`). Every part the document names is spelled
  `f"{directory}/visio/…"`, a filesystem path where no file has ever been.
  `Page.filename`, `Page.rels_xml_filename` and `VisioFile._masters_folder` hold
  these paths. Every store call first strips them back to a part name through
  `_part_name(path)` → `part_name_for_path`.
- **A translation layer.** `zip_file_contents` is a `ZipFileContentsView`
  (`zip_contents.py`, 444 lines). It re-creates the old `dict[str, BytesIO]`
  over the store, with write-through buffers, per-name generation counters,
  held-back unparseable bytes, `getbuffer()` export tracking and a `sync()` that
  `save_vsdx` must call first. It exists only so that old callers keep working.
  `PackageStore.write_bytes_keeping_tree` exists only to serve it.
- **Dead helpers.** `xmlio.file_to_xml`, `xml_to_file`, `require_xml_tree` and
  `require_root` take the old mapping. None of them has a caller in `src/`,
  except `file_to_xml`'s re-export from `vsdxfile.py`, which is kept for an
  import in `pages.py` that no longer exists.

The plan says Phase 1 deletes `zip_file_contents` outright, and the
simplification plan's rule is "no other class opens a ZIP or strips source
prefixes". Until this lands, every new feature has to choose between two ways of
naming a part, and #94 (`MasterCatalog`) would inherit the pseudo-paths.

## What uses it today

| Consumer | What it does | Becomes |
| --- | --- | --- |
| `vsdxfile.py` load (`_pages_filename`, `load_pages`, `load_master_pages`, `_read_part_xml` of the four document parts) | builds `{directory}/…` paths and strips them again | part-name constants |
| `vsdxfile.py:447, 598` | `path in zip_file_contents` | `store.part(name) is not None` |
| `vsdxfile.py:662` (`_unused_page_part_name`), `masters.py:112` (next master number) | iterate the view's keys | iterate `store.names()` |
| `vsdxfile.py:1575` | `zip_file_contents.sync()` before save | deleted |
| `connectors.py:119–123` | copy the donor's `visio/masters/*` into a document with no masters | `store.read_bytes` → `store.write_bytes`, part name to part name |
| `masters.py` (`_masters_folder`, `_part_name`, `_read_part_xml`) | mixin protocol in pseudo-paths | protocol in part names |
| `Page.filename`, `Page.rels_xml_filename` | pseudo-paths, stripped at every use | part names |

`vsdxdiff.py` opens archives with `zipfile` to diff two files on disk. It never
touches an open document, and it stays as it is.

## Decisions

### D1. `Page.filename` and `Page.rels_xml_filename` hold part names

Today they hold `/home/me/drawing/visio/pages/page1.xml`. They will hold `/visio/pages/page1.xml`.

- These are the names the store, the relationship parts and
  `[Content_Types].xml` all use. Nothing else in the document spells a part the
  old way.
- Both attributes are public by spelling but undocumented: they are not in
  `docs/classes.rst`'s member list, the README or the changelog. The only thing
  a caller could have done with the old value is index `zip_file_contents`,
  which this change deletes.
- Keeping the attribute names and changing their values follows the plan's "no
  public entity rename in this PR". 1.0's renames come later (#112).
- **Rejected:** keep the pseudo-path as a computed compatibility value. That
  would keep `directory` alive for a string nothing can use.

### D2. No public replacement for raw part access

`zip_file_contents` was the only way to read or write a part's raw bytes. It
goes without a public successor.

- The plan says `PackageStore` is "not a public manager". A raw-bytes door is
  what let callers bypass the object model and break the invariants #89 exists
  for.
- No issue, test or doc shows a user reading parts through it. A caller who
  needs raw bytes can open the saved file with `zipfile`, as `vsdxdiff` does.
- The breaking-change note says this plainly. If a real need turns up, a
  read-only accessor is a small, additive follow-up.

### D3. Removals are recorded in the changelog, not a migration guide

\#347 closed #87 by deciding against `docs/migration-1.0.rst`. Releases go
through release-please, as in every firmfooting product. `publish.yml` runs it
as the firmfooting-bot app, it keeps the release PR (currently #349, 0.9.0) up
to date, and it writes `CHANGELOG.md` from the conventional commits on `main`.
Both PRs are squash-merged, so each one's title (`refactor!: …`) and its body's
`BREAKING CHANGE:` footer become the changelog entry. That footer lists every
removed name and what to use instead. Nothing edits `CHANGELOG.md` or the
version by hand.

### D4. `KNOWN_DRIFT.md` becomes a short note in the README

Its first half is about no-op saves, which #89 fixed and
`test_a_round_trip_changes_nothing` enforces. Its second half is still true: a
part the library changes is written by ElementTree, which spells XML differently
from Visio (#377, deferred). That half moves to a few lines under the README's
"Open, edit and save", for example:

> A save writes every part you did not change exactly as it arrived. A part you
> did change is written in equivalent XML, not in Visio's own spelling: the XML
> declaration, attribute quotes, empty-element form and namespace declarations
> can differ, and a CRLF in text becomes LF. Visio and LibreOffice open both.

The file and both references to it in `tests/test_package_manifest.py` go.

## Design

1. **One module derives every part name** (added at plan review, 2026-09-23, for
   extensibility to any part a shape refers to). `src/vsdxkit/partnames.py`
   holds:
   - the fixed part names as constants;
   - `relationships_part_name(part)`: `/a/b.xml` → `/a/_rels/b.xml.rels`;
   - `target_part_name(source, target)`: a relationship Target joined onto its
     source part's folder, exactly as the library joins it today.

   Pages, masters and page relationships, and any part added later (images,
   embedded objects, data recordsets), are named by these rules rather than by
   folder strings of their own. `vsdxfile.py`'s private constants and
   `_page_relationship_path` go. OPC-conformant resolution of `..`, `.`,
   absolute and percent-encoded Targets is #378, a change to `target_part_name`
   alone.
2. **`VisioFile`:**
   - `_read_part_xml(name)` and `_part_name` go. Callers use `self._package.read_xml(name)`.
   - Nothing in `src/` except the view itself reads `directory` or
     `zip_file_contents` any more.
3. **`Page`:** `filename` and `rels_xml_filename` hold part names. `_holds`,
   `_attached`, `_rels_attached` and the `xml`/`rels_xml` setters drop their
   `_part_name(...)` wrapping.
4. **`MastersImportMixin`:** the protocol's `_masters_folder` becomes the
   part-name prefix `/visio/masters`, and `_part_name`/`_read_part_xml` leave
   the protocol. The master-numbering scan reads `store.names()`.
5. **Connectors:** copying the donor's masters goes store to store, `read_bytes`
   to `write_bytes`. `read_bytes` gives each part's current bytes: the original
   ones for any master the donor parsed but did not change. The prefix test
   matches `"/visio/masters/"` with its trailing slash, so no sibling that
   merely starts with the same letters is copied.
6. **Deleted:**
   - `VisioFile.directory` and `VisioFile.zip_file_contents`;
   - `_load_zip_file_contents_to_memory`, whose store-opening line moves into `open_vsdx_file`;
   - the `sync()` call in `save_vsdx`;
   - `zip_contents.py` in full;
   - `PackageStore.write_bytes_keeping_tree`;
   - `xmlio.file_to_xml`, `xml_to_file`, `require_xml_tree` and `require_root`;
   - the `file_to_xml` re-export in `vsdxfile.py` and its stale comment;
   - docstrings and comments that describe the view or the old idiom
     (`package.py:572–590`, `masters.py:205`, `pages.py:263/290`,
     `xmlio.py:228`).
7. **Simplify `Page._attached()` and `_rels_attached()`.** Both accept an absent
   part or a `BytesPart` today, and the view is the only thing that can produce
   either behind a live page, by writing unparseable bytes or deleting the
   member. A page's own part is promoted when the page loads, so once the view
   is gone:
   - `_attached()` reduces to `_holds(filename, self._xml)`.
   - `_rels_attached()` keeps "no rels part yet", which is how a page's first
     relationship part is created, and drops the `BytesPart` case.

   The existing tests keep pinning that a removed page's assignment writes
   nothing and does not overwrite the page that took its name. If the plan finds
   another route to a `BytesPart` or absent page part, that branch stays and a
   test names the route.

## Testing

- **Deleted:** `tests/test_zip_contents_view.py` (55 tests), which pins only the
  view's own mechanics. The same goes for tests elsewhere that exist only for
  `write_bytes_keeping_tree`, `file_to_xml`, `xml_to_file` or
  `require_xml_tree`, each named in the plan.
- **Migrated:** every other test that reads or writes through the view. That's
  about 40 uses across 12 files (`test_visiofile_package_store`,
  `test_byte_preserving_save`, `test_visiofile`, `test_namespaces`,
  `test_media_reuse`, `test_connector_atomicity`, …). Each asserts the same
  thing through `vis._package` with a part name, or through the saved archive.
  An assertion is not weakened on the way. Where a test used the view to
  *inject* a malformed part, it writes the bytes with
  `vis._package.write_bytes`.
- **New:**
  - `Page.filename` and `rels_xml_filename` are part names, for a loaded page,
    an added page and a copied page.
  - `VisioFile` has no `directory` or `zip_file_contents` attribute.
  - A connector on a document with no masters copies exactly the donor's
    `/visio/masters/` parts, byte for byte.
- **Unchanged and still green:**
  - the package manifests, including `test_a_round_trip_changes_nothing`;
  - the metamorphic suite;
  - the LibreOffice job;
  - the full suite on Python 3.10 and on 3.14.
- **Acceptance greps:** `grep -rn
  "zip_file_contents\|\.directory\b\|part_name_for_path\|file_to_xml\|xml_to_file"
  src` is empty.
- **needs-visio:** the COM oracle recordings are unaffected, because file output
  is unchanged. The plan confirms this with a manifest-identical save of every
  fixture before and after, not a new Windows run.

## Delivery

Two stacked PRs (`gh stack`), each leaving `main` green:

1. **`refactor!: name every part by its part name`**: steps 1–5. Every consumer
   in `src/` moves to part names, and so does every test that combines
   `page.filename` with the view. The view and `directory` stay, still keyed the
   old way, so nothing public is deleted yet. Breaking only in `Page.filename`
   and `rels_xml_filename`.
2. **`refactor!: delete zip_file_contents and the helpers that served it`**:
   steps 6 and 7 (step 7 only holds once the view is gone), the test deletions,
   D4, and the `BREAKING CHANGE:` footer listing each removed name.

Breaking changes land in the changelog under 0.9's section, with no API rename.

## Risks

- **Output drift.** A consumer moved from the view to the store could write
  where it used to read, or promote a part it used to leave as bytes. Promotion
  alone never changes output, because an unchanged promoted part is still
  written as its original bytes. The manifest-identical check over every fixture
  is the guard.
- **Hidden consumers in tests.** Some tests use the view to build a scenario,
  not to assert one. Migrating them by hand risks weakening the assertion. The
  review checks each migrated test against its original.
- **Third-party breakage.** Anyone who read `zip_file_contents` loses that, per
  D2. The package has two releases, both from 2026-09-13, and no known
  downstream user of the attribute.
