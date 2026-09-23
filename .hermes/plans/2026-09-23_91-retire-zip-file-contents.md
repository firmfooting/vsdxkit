# Retire `zip_file_contents` for part names (#91) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every part of an open document is named by its OPC part name, and the pre-store `zip_file_contents` view, `VisioFile.directory` and the helpers that served them are deleted.

**Architecture:** `PackageStore` (`src/vsdxkit/package.py`) already holds the document. Six places still reach it through `ZipFileContentsView` (`src/vsdxkit/zip_contents.py`), keyed by pseudo-paths `f"{directory}/visio/…"`, and every store call first strips a pseudo-path back to a part name. PR 1 (Tasks 1–2) moves every consumer onto the store and part names, leaving the view in place. PR 2 (Tasks 3–6) deletes the view and everything that only served it.

**Tech Stack:** Python 3.10–3.14, `xml.etree.ElementTree`, pytest, `uv`, ruff, pyrefly, `gh stack`.

**Spec:** `.hermes/plans/2026-09-23_91-retire-zip-file-contents-spec.md` (approved 2026-09-23)

## Global Constraints

- The file output must not change. Every fixture saves the same member bytes before and after (Task 6 checks this against a baseline taken before Task 1).
- `Page.filename` and `Page.rels_xml_filename` hold OPC part names such as `/visio/pages/page1.xml`: leading slash, no directory prefix (spec D1).
- No public replacement for raw part access. `PackageStore` stays private as `VisioFile._package` (spec D2).
- Do not edit `CHANGELOG.md` or any version string. release-please writes them from the squash commits (spec D3).
- Gates, all clean before every commit:
  - `uv run pytest tests -q`
  - `uv run ruff check src tests tools`
  - `uv run ruff format --check src tests tools`
  - `uv run pyrefly check src/vsdxkit --min-severity warn`
- Before the last commit of each PR, also run `uv run --python 3.10 --isolated python -m pytest tests -q`.
- Commit subjects are conventional commits. Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_014SeJzNKgmmqyg4BHg7odRt
  ```
- Worktree-isolated session: run plain, separate git commands from the worktree root. Never use `git -C`, and never use bare `git stash`.
- Comments and docstrings match the surrounding code's density and voice. They say why, in full sentences, and never "this used to…" history for its own sake.
- Test docstrings follow the repo idiom: `"""Fails if <the behaviour breaks>."""`, then a short why.

## Review Focus

1. **A package stored under a directory whose own path contains `visio/pages/`.** `Page._ensure_page_master_rel` builds the rels name with `self.filename.replace("visio/pages/", "visio/pages/_rels/")`. On a pseudo-path that rewrites the directory too. On a part name it must yield `/visio/pages/_rels/pageN.xml.rels`. Test in Task 2.
2. **A relationship `Target` that is not a plain file name** (`../x.xml`, `a/../../x.xml`). It must still fail the open with `MalformedPackageError`, exactly as before. Joining now starts at `/visio/pages/` instead of a pseudo-path, so the `_checked` call is what must still see and reject it. Test in Task 2.
3. **`insert_shape(..., page_path)`** must accept `page.filename` (the new part name) and reject any other page's name. Test in Task 2.
4. **Importing the connector master into a document that already has masters.** `_ensure_masters_for_shape` copies it from the bundled donor, which is another document with the same part names. The imported part must be the donor's master, byte for byte. The target's own part at that name must not be read or overwritten. Test in Task 2.
5. **Connecting shapes on a document with no masters.** The target gets exactly the donor's `/visio/masters/` parts, byte for byte. No donor page is read or serialised, and no sibling folder whose name merely starts with `masters` is copied. Test in Task 1.

---

## Setup (controller, before Task 1)

- [ ] **Record the output baseline.** Write this script to the scratchpad as `output_probe.py`. It is not committed. Run it on the current HEAD, before any task lands:

```python
"""Save every fixture after a fixed workload; record each member's bytes digest (read-only probe for #91)."""

import glob
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

from vsdxkit import VisioFile

ROOT, OUT = sys.argv[1], sys.argv[2]


def workload(vis):
    """Public calls that reach every consumer #91 moves: add, copy, connect, rename, remove."""
    steps = []
    for label, step in (
        ("add_page", lambda: vis.add_page("Probe added")),
        ("copy_page", lambda: vis.copy_page(vis.pages[0], name="Probe copy")),
        ("shapes", lambda: (
            vis.create_shape(vis.pages[0], "PALETTE_PROCESS", 2.0, 2.0, text="A"),
            vis.create_shape(vis.pages[0], "PALETTE_DECISION", 6.0, 2.0, text="B"),
        )),
        ("connect", lambda: vis.pages[0].connect_shapes(*steps_shapes[-1])),
        ("rename", lambda: setattr(vis.pages[0], "name", "Probe renamed")),
        ("remove", lambda: vis.remove_page_by_index(len(vis.pages) - 1)),
    ):
        try:
            result = step()
            if label == "shapes":
                steps_shapes.append(result)
            steps.append((label, "ok"))
        except Exception as error:  # noqa: BLE001 -- recorded, compared, not hidden
            steps.append((label, type(error).__name__))
    return steps


def members(path):
    with zipfile.ZipFile(path) as archive:
        return {i.filename: hashlib.sha256(archive.read(i)).hexdigest() for i in archive.infolist() if not i.is_dir()}


def run():
    result = {}
    for source in sorted(glob.glob(os.path.join(ROOT, "tests", "**", "*.vs[dm]x"), recursive=True)):
        rel = os.path.relpath(source, ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            copy = os.path.join(tmp, os.path.basename(source))
            shutil.copy(source, copy)
            global steps_shapes
            steps_shapes = []
            try:
                with VisioFile(copy) as vis:
                    steps = workload(vis)
                    out = os.path.join(tmp, "out" + os.path.splitext(source)[1])
                    vis.save_vsdx(out)
                result[rel] = {"steps": steps, "members": members(out)}
            except Exception as error:  # noqa: BLE001
                result[rel] = {"error": type(error).__name__}
    return result


first, second = run(), run()
# members that differ between two runs of the same code are nondeterministic
# (generated GUIDs); they are reported, not compared
for rel, entry in first.items():
    other = second.get(rel, {})
    if "members" in entry and "members" in other:
        entry["unstable"] = sorted(n for n in entry["members"] if entry["members"][n] != other["members"].get(n))
json.dump(first, open(OUT, "w"), indent=1, sort_keys=True)
print(f"{len(first)} packages -> {OUT}")
```

Run: `uv run python <scratchpad>/output_probe.py . <scratchpad>/91-baseline.json`
Expected: prints the package count. Every fixture has an entry.

- [ ] **Start the ledger** at the SDD workspace, per the skill.

---

## PR 1: `refactor!: name every part by its part name`

Branch: `refactor/91-retire-zip-file-contents`. It already carries the #377 and #91 spec commits.

### Task 1: Read and write the store, not the view, everywhere in `src/`

**Files:**
- Modify: `src/vsdxkit/connectors.py:114-124`
- Modify: `src/vsdxkit/masters.py:31-36` (mixin attribute declarations), `masters.py:109-114` (next master number)
- Modify: `src/vsdxkit/vsdxfile.py:447` (`load_pages`), `vsdxfile.py:598` (`remove_page_by_index`), `vsdxfile.py:643-667` (`_unused_page_part_name`)
- Test: `tests/test_media_reuse.py:126-149`, `tests/test_master_import_opc.py:255`, `tests/test_connector_atomicity.py:22-26`, `tests/test_add_page_at_positions.py:14-19`

**Interfaces:**
- Consumes: `PackageStore.names() -> tuple[str, ...]`, `part(name) -> PartValue | None`, `read_bytes(name) -> bytes | None` and `write_bytes(name, data) -> None`, from `package.py`.
- Produces: no `src/` module other than `vsdxfile.py`'s `_load_zip_file_contents_to_memory`, its `save_vsdx` `sync()` call and `zip_contents.py` itself mentions `zip_file_contents`. Task 3 deletes those three.

- [ ] **Step 1: Write the failing test for the donor copy (Review Focus 5).** Replace `test_provisioning_masters_reads_only_the_donors_master_parts` in `tests/test_media_reuse.py`, and drop its `ZipFileContentsView` import:

```python
from vsdxkit.package import PackageStore


def test_provisioning_masters_reads_only_the_donors_master_parts(vsdx_copy, monkeypatch):
    """Fails if copying the donor's masters reads any donor part outside `/visio/masters/`.

    Reading a part the donor has parsed serialises it, and the donor has parsed
    every page it holds -- all of it wasted on a copy that wants none of them.
    """
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        donor = vis._shared_media().media
        read: list[str] = []
        original = PackageStore.read_bytes

        def spy(self, name):
            if self is donor._package:
                read.append(name)
            return original(self, name)

        monkeypatch.setattr(PackageStore, "read_bytes", spy)
        shapes = page.child_shapes
        Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
    assert read, "the donor's masters were not copied through its store; the test has gone stale"
    assert [name for name in read if not name.startswith("/visio/masters/")] == []


def test_provisioning_masters_copies_the_donors_master_parts_byte_for_byte(vsdx_copy):
    """Fails if a document with no masters gets anything but the donor's `/visio/masters/` parts, unchanged."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        assert not [n for n in vis._package.names() if n.startswith("/visio/masters/")]
        page = vis.pages[0]
        donor = vis._shared_media().media
        shapes = page.child_shapes
        Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
        donor_masters = {n: donor._package.read_bytes(n) for n in donor._package.names() if n.startswith("/visio/masters/")}
        copied = {n: vis._package.read_bytes(n) for n in vis._package.names() if n.startswith("/visio/masters/")}
    # the copy is exact at the moment it is made; masters.xml and its rels may
    # be edited afterwards by the connector's own master registration, so
    # compare the master drawing parts, which nothing edits
    drawing = [n for n in donor_masters if n.rsplit("/", 1)[-1].startswith("master") and n.rsplit("/", 1)[-1] != "masters.xml"]
    assert drawing
    assert {n: copied.get(n) for n in drawing} == {n: donor_masters[n] for n in drawing}
```

- [ ] **Step 2: Run it and watch it fail.**
Run: `uv run pytest tests/test_media_reuse.py -q -k provisioning`
Expected: `test_provisioning_masters_reads_only_the_donors_master_parts` FAILS with the stale-test assertion, because the copy still goes through the view. The byte-for-byte test may already pass. That's fine: it pins behaviour that must survive the change.

- [ ] **Step 3: Move the donor copy onto the stores.** In `connectors.py`, replace the `donor_contents` loop:

```python
            if not masters_rel_present:
                # document has no masters at all: copy the donor's masters
                # parts, part name for part name. `read_bytes` gives a part the
                # donor has parsed but not changed as the bytes it arrived as,
                # and only the masters are read -- the donor has parsed every
                # page it holds, and reading one would serialise it for nothing
                donor_store = media.media._package
                for name in donor_store.names():
                    if name.startswith(_MASTERS_PREFIX):
                        data = donor_store.read_bytes(name)
                        assert data is not None  # names() lists only parts the store holds
                        page.vis._package.write_bytes(name, data)
                page.vis.load_master_pages()  # load copied master page files into VisioFile object
```

Add at module level in `connectors.py`, next to its other constants:

```python
# the folder a package keeps its masters in, as a part-name prefix; the
# trailing slash keeps a sibling such as /visio/masters-old/ out of a copy
_MASTERS_PREFIX = "/visio/masters/"
```

- [ ] **Step 4: Move the other four consumers onto the store.**

`vsdxfile.py`, `load_pages`:

```python
            if self._package.part(self._part_name(page_rels_path)) is not None:
```

`vsdxfile.py`, `remove_page_by_index`:

```python
                if page.rels_xml_filename and self._package.part(self._part_name(page.rels_xml_filename)) is not None:
```

`vsdxfile.py`, `_unused_page_part_name`: the body after the docstring becomes

```python
        taken = set(self._package.names())
        rels_root = self._part_root(self.pages_xml_rels, "pages.xml.rels")
        taken.update(f"/visio/pages/{rel.attrib['Target']}" for rel in rels_root)
        counter = 1
        while f"/visio/pages/page{counter}.xml" in taken or f"/visio/pages/_rels/page{counter}.xml.rels" in taken:
            counter += 1
        return f"page{counter}.xml"
```

`masters.py`, the next-master-number scan:

```python
        prefix = "/visio/masters/master"
        existing_numbers = [
            int(name[len(prefix) : -4])
            for name in self._package.names()
            if name.startswith(prefix) and name.endswith(".xml") and name[len(prefix) : -4].isdigit()
        ]
```

`masters.py`, `MastersImportMixin`: delete the `zip_file_contents: MutableMapping[str, io.BytesIO]` declaration. Also delete the `io` and `MutableMapping` imports if nothing else in the file uses them.

- [ ] **Step 5: Move the tests that read the package through the view onto the store.** They assert package state, not the view:
  - `tests/test_master_import_opc.py:255`: `assert vis._package.part(vis._part_name(master_page.filename)) is not None`.
  - `tests/test_connector_atomicity.py:22-26`: iterate `document._package.names()` and keep both filters. Names now start with `/`, and `"/masters/" in name` and `endswith("page1.xml.rels")` still hold.
  - `tests/test_add_page_at_positions.py:_pages_rels_root`: `return visio_file._package.require_xml("/visio/pages/_rels/pages.xml.rels").getroot()`, then delete the `io` import if it's unused.

- [ ] **Step 6: Run the gates.** Run all four gates from Global Constraints.
Expected: all green. Then run `grep -n "zip_file_contents" src/vsdxkit/*.py`. It should list only `vsdxfile.py`'s attribute declaration, `_load_zip_file_contents_to_memory`, the `save_vsdx` sync, docstrings and comments, and `zip_contents.py`.

- [ ] **Step 7: Commit.**

```bash
git add src/vsdxkit/connectors.py src/vsdxkit/masters.py src/vsdxkit/vsdxfile.py tests/test_media_reuse.py tests/test_master_import_opc.py tests/test_connector_atomicity.py tests/test_add_page_at_positions.py
git commit -m "refactor: read and write the package store, not zip_file_contents (#91)" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_014SeJzNKgmmqyg4BHg7odRt"
```

### Task 2: Name every part by its part name

**Files:**
- Modify: `src/vsdxkit/vsdxfile.py` (the load, create, remove and relationship-check paths: lines 248-285, 399-470, 474-520, 590-603, 1010-1060)
- Modify: `src/vsdxkit/pages.py:238-310` (setters, `_holds`, `_attached`, `_rels_attached`), `pages.py:401-404` (`_ensure_page_master_rel`)
- Modify: `src/vsdxkit/masters.py` (protocol lines 40-46, 85-91, 115-133, 172, 208-209)
- Modify: `src/vsdxkit/connectors.py:154`
- Test: create `tests/test_part_names.py`. Migrate `tests/test_byte_preserving_save.py`, `tests/test_visiofile_package_store.py`, `tests/test_visiofile.py:453`, `tests/test_master_import_opc.py:255` (from Task 1) and `tests/test_media_reuse.py`.

**Interfaces:**
- Consumes: Task 1's store-only consumers.
- Produces, for Tasks 3–5:
  - `Page.filename: str` and `Page.rels_xml_filename: str | None` are part names.
  - `VisioFile._masters_folder == "/visio/masters"`.
  - `VisioFile._require_part_xml(name: str, description: str)`.
  - `VisioFile._check_relationship_target(name: str, subject: str, target: str)`.
  - `VisioFile._part_name`, `VisioFile._read_part_xml` and `_pages_filename` no longer exist.
  - `MastersImportMixin`'s protocol no longer declares `_part_name`, `_read_part_xml` or `directory`.
  - `VisioFile.directory` and `zip_file_contents` still exist, and are read only by `_load_zip_file_contents_to_memory`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_part_names.py`:

```python
"""Pages and masters are named by their OPC part names (#91).

The names used to be pseudo-paths under the source file's path minus its
extension, a directory no file was ever in, and every use stripped them back
to part names. A part name is what the store, the relationship parts and
[Content_Types].xml all say.
"""

import os
import shutil
import xml.etree.ElementTree as ET
import zipfile

import pytest

from vsdxkit import Connect, VisioFile
from vsdxkit.errors import MalformedPackageError
from vsdxkit.shapes import find_or_create_shapes_tag

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def test_loaded_pages_and_masters_are_named_by_part_name(vsdx_copy):
    """Fails if a loaded page or master is named by anything but its part name."""
    with VisioFile(vsdx_copy("test2.vsdx")) as vis:
        assert vis.pages[0].filename == "/visio/pages/page1.xml"
        assert all(page.filename.startswith("/visio/pages/page") for page in vis.pages)
        assert vis.master_pages, "the fixture has changed: it should carry masters"
        assert all(master.filename.startswith("/visio/masters/master") for master in vis.master_pages)
        with_rels = [page for page in vis.pages if page.rels_xml_filename is not None]
        assert all(page.rels_xml_filename.startswith("/visio/pages/_rels/") for page in with_rels)


def test_added_and_copied_pages_are_named_by_part_name(vsdx_copy):
    """Fails if a page the library creates is named by anything but its part name."""
    with VisioFile(vsdx_copy("test2.vsdx")) as vis:
        added = vis.add_page("Added")
        copied = vis.copy_page(vis.pages[0], name="Copied")
        for page in (added, copied):
            assert page.filename.startswith("/visio/pages/page")
            assert vis._package.part(page.filename) is not None
        if copied.rels_xml_filename is not None:
            assert copied.rels_xml_filename == f"/visio/pages/_rels/{copied.filename.rsplit('/', 1)[-1]}.rels"


def test_a_document_has_no_directory_prefix_in_any_page_name(vsdx_copy):
    """Fails if the source path leaks into a page's name."""
    path = vsdx_copy("test2.vsdx")
    with VisioFile(path) as vis:
        stem = os.path.splitext(os.path.abspath(path))[0]
        assert not any(stem in page.filename for page in (*vis.pages, *vis.master_pages))


def test_a_page_rels_created_under_a_visio_pages_directory_lands_in_the_package(tmp_path):
    """Fails if the page-rels name is built by rewriting a path that contains `visio/pages/` twice.

    `_ensure_page_master_rel` derives the rels part from the page's name. With
    a pseudo-path, a source file kept under a directory called visio/pages had
    that directory rewritten too.
    """
    home = tmp_path / "visio" / "pages"
    home.mkdir(parents=True)
    path = home / "test1.vsdx"
    shutil.copy(os.path.join(FIXTURES, "test1.vsdx"), path)
    out = tmp_path / "out.vsdx"
    with VisioFile(str(path)) as vis:
        page = vis.pages[0]
        shapes = page.child_shapes
        page.connect_shapes(shapes[0], shapes[1])
        assert page.rels_xml_filename == "/visio/pages/_rels/page1.xml.rels"
        vis.save_vsdx(str(out))
    with zipfile.ZipFile(out) as archive:
        assert "visio/pages/_rels/page1.xml.rels" in archive.namelist()


@pytest.mark.parametrize("target", ["../page1.xml", "a/../../page1.xml"])
def test_a_page_target_outside_the_pages_folder_still_fails_the_open(tmp_path, target):
    """Fails if joining a relationship Target onto a part name lets a traversal through."""
    source = os.path.join(FIXTURES, "test1.vsdx")
    crafted = tmp_path / "crafted.vsdx"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(crafted, "w") as rewritten:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == "visio/pages/_rels/pages.xml.rels":
                root = ET.fromstring(data)
                root[0].set("Target", target)
                data = ET.tostring(root)
            rewritten.writestr(entry, data)
    with pytest.raises(MalformedPackageError):
        VisioFile(str(crafted))


def test_insert_shape_takes_the_pages_part_name(vsdx_copy):
    """Fails if `insert_shape` refuses the name `Page.filename` now holds, or accepts another page's."""
    with VisioFile(vsdx_copy("test2.vsdx")) as vis:
        assert len(vis.pages) > 1, "the fixture has changed: it should have more than one page"
        page, other = vis.pages[0], vis.pages[1]
        shapes = find_or_create_shapes_tag(page.xml.getroot())
        source = page.child_shapes[0].xml
        vis.insert_shape(ET.fromstring(ET.tostring(source)), shapes, page, page.filename)
        with pytest.raises(ValueError):
            vis.insert_shape(ET.fromstring(ET.tostring(source)), shapes, page, other.filename)


def test_the_connector_master_is_imported_from_the_donor_not_the_target(vsdx_copy):
    """Fails if importing a master reads the target document's part of the same name.

    The bundled donor and the target now name their parts identically; only
    the store a name is looked up in says whose part it is. `test3_house.vsdx`
    ships exactly one master, which puts `Connect.create()` on the import
    branch (see tests/test_master_import_opc.py).
    """
    with VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        target_before = {n: vis._package.read_bytes(n) for n in vis._package.names() if n.startswith("/visio/masters/master")}
        page = vis.pages[0]
        shapes = page.child_shapes
        Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
        donor = vis._shared_media().media
        connector_master = donor.get_master_page_by_id(vis._shared_media().straight_connector.master_page_ID)
        assert connector_master is not None
        imported = vis.master_index[connector_master.name]
        assert imported.filename not in target_before, "the import wrote over one of the target's own masters"
        assert vis._package.read_bytes(imported.filename) == donor._package.read_bytes(connector_master.filename)
        for name, data in target_before.items():
            assert vis._package.read_bytes(name) == data
```

If `test3_house.vsdx` has fewer than two child shapes on page 1, or `straight_connector.master_page_ID` doesn't name a donor master, read `tests/test_master_import_opc.py`'s `imported_master` fixture and take the connector-master lookup it uses. Say which in the report.

- [ ] **Step 2: Run them and watch them fail.**
Run: `uv run pytest tests/test_part_names.py -q`
Expected:
- The name assertions FAIL, because the names still carry the directory prefix.
- The traversal test passes already: it pins behaviour that must survive.
- `test_a_page_rels_created_under_a_visio_pages_directory_lands_in_the_package` FAILS. This is Review Focus 1.

- [ ] **Step 3: Switch `vsdxfile.py` to part names.**

  - Add `_PAGES_FOLDER = "/visio/pages/"`, `_PAGES_RELS_FOLDER = "/visio/pages/_rels/"` and `_MASTERS_FOLDER = "/visio/masters"` beside `_PAGES_PART` (line 92).
  - Delete `_part_name`, `_read_part_xml` and `_pages_filename`.
  - `_masters_folder` returns `_MASTERS_FOLDER`.
  - `_check_relationship_target(self, name, subject, target)` calls `_checked(name)` directly, keeping its `except ValueError` translation.
  - `_require_part_xml(self, name, description)` calls `self._package.read_xml(name)`.
  - `load_pages`:
    - `rel_dir = _PAGES_RELS_FOLDER` and `page_dir = _PAGES_FOLDER`;
    - `rel_filename = _PAGES_RELS_PART`, with `pages_filename = _PAGES_PART`;
    - `page_rels_path` in `self._package.part(page_rels_path)`;
    - `new_page._rels_xml = self._package.read_xml(page_rels_path)`;
    - the four promotions read `self._package.read_xml(_CONTENT_TYPES_PART)`, and likewise for `_APP_PART`, `_DOCUMENT_PART` and `_DOCUMENT_RELS_PART`.
  - `load_master_pages`: `master_rel_path = f"{_MASTERS_FOLDER}/_rels/masters.xml.rels"`, `self._package.read_xml(master_rel_path)`, and `master_path = f"{_MASTERS_FOLDER}/{master_target}"`.
  - `remove_page_by_index`: drop the `_part_name(...)` wrappers. The content-types override stays `f"/visio/pages/{os.path.basename(page.filename)}"`, which is now simply `page.filename`, so use that.
  - `_create_page`: `page_dir = _PAGES_FOLDER`, and drop the "better concatenation" TODOs; `self._package.write_xml(new_page_path, new_page_xml)`; `rel_dir = _PAGES_RELS_FOLDER`.
  - `_unused_page_part_name` (from Task 1): use `_PAGES_FOLDER` and `_PAGES_RELS_FOLDER` in place of the literals.

- [ ] **Step 4: Switch `pages.py`, `masters.py` and `connectors.py` to part names.**
  - `pages.py`:
    - drop every `self.vis._part_name(...)` wrapper, since the attribute is the name;
    - `_ensure_page_master_rel` builds `rels_filename = f"/visio/pages/_rels/{posixpath.basename(self.filename)}.rels"`, importing `posixpath`.
  - `masters.py`:
    - delete `directory`, `_read_part_xml` and `_part_name` from the protocol block;
    - `src_vis._package.part(source_master_page.filename)` and `source_part_name = source_master_page.filename`;
    - `self._package.read_xml(master_rels_path)`;
    - `self._package.write_xml(master_rels_path, rels_tree)`;
    - `self._package.write_bytes(part_path, master_bytes)`;
    - `self._package.read_xml(part_path)`;
    - in `_bootstrap_masters`, drop the `_part_name` wrappers;
    - update the comment at line 205 so it no longer names `xml_to_file`: "written as trees, not bytes literals (#366)".
  - `connectors.py:154`: `master_part = master_page.filename.removeprefix(page.vis._masters_folder + "/")`.

- [ ] **Step 5: Migrate the tests that built or stripped pseudo-paths.** Each keeps its assertion, only spelling the name differently:
  - `vis._part_name(X)` → `X`, wherever `X` is a page's `filename` or `rels_xml_filename`, in `tests/test_byte_preserving_save.py` and `tests/test_visiofile_package_store.py`.
  - `vis._part_name(X)[1:]` → `X[1:]`: the archive member name is the part name without its slash.
  - `X.removeprefix(f"{vis.directory}/")` → `X[1:]`, in `test_byte_preserving_save.py:274,297` and `test_visiofile.py:453`.
  - `vis._part_name(f"{vis.directory}/visio/pages/_rels/{candidate}.rels")` → `f"/visio/pages/_rels/{candidate}.rels"` (`test_visiofile_package_store.py:262`).
  - `tests/test_master_import_opc.py:255` → `vis._package.part(master_page.filename) is not None`.
  - Tests that still index the view with a page name (`vis.zip_file_contents[page.filename]`, `del vis.zip_file_contents[page.rels_xml_filename]`) index `f"{vis.directory}{page.filename}"` for now. Task 3 deletes every one of them along with the view. Don't rewrite them further.
  - `tests/test_visiofile_package_store.py:369`: `f"{vis.directory}/visio/masters/masters.xml"` stays for now. Task 3 moves it to `vis._package.write_bytes`.

- [ ] **Step 6: Run the gates.** Run all four gates from Global Constraints.
Expected: all green, including every test in `tests/test_part_names.py`. `grep -n "_part_name(\|_read_part_xml\|_pages_filename\|self\.directory" src/vsdxkit/*.py` lists only `_load_zip_file_contents_to_memory` and `zip_contents.py`.

- [ ] **Step 7: Run the Python 3.10 suite** (last task of PR 1).
Run: `uv run --python 3.10 --isolated python -m pytest tests -q`
Expected: all pass.

- [ ] **Step 8: Commit.**

```bash
git add src/vsdxkit tests
git commit -m "refactor!: name every part by its part name (#91)" -m "BREAKING CHANGE: Page.filename and Page.rels_xml_filename hold OPC part names such as /visio/pages/page1.xml instead of a path under the source file's name. insert_shape's page_path takes the same part name." -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_014SeJzNKgmmqyg4BHg7odRt"
```


---

## PR 2: `refactor!: delete zip_file_contents and the helpers that served it`

Branch: `refactor/91-delete-zip-file-contents`, stacked on PR 1 with `gh stack`.

### Task 3: Delete the view, `directory` and `write_bytes_keeping_tree`

**Files:**
- Delete: `src/vsdxkit/zip_contents.py`, `tests/test_zip_contents_view.py`
- Modify: `src/vsdxkit/vsdxfile.py`:
  - imports (line 28);
  - `__init__` (lines 173, 182-188);
  - `_load_zip_file_contents_to_memory` (lines 237-245), folded into `open_vsdx_file`;
  - `save_vsdx` (lines 1572-1576).
- Modify: `src/vsdxkit/package.py`: delete `write_bytes_keeping_tree` (lines 567-618).
- Modify tests: `tests/test_visiofile_package_store.py`, `tests/test_byte_preserving_save.py`, `tests/test_visiofile.py`, `tests/test_namespaces.py`, `tests/test_errors.py:879`, `tests/test_save_destinations.py:63`, `tests/test_package_store_save.py:364-372`, and any `tests/test_package_store.py` tests of `write_bytes_keeping_tree`.

**Interfaces:**
- Consumes: Task 2's state, where only `_load_zip_file_contents_to_memory` reads `directory` or `zip_file_contents`.
- Produces: `VisioFile` has no `directory` or `zip_file_contents` attribute. `PackageStore` has no `write_bytes_keeping_tree`.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_part_names.py`:

```python
def test_a_document_has_no_zip_file_contents_or_directory(vsdx_copy):
    """Fails if the pre-store view or its pseudo-path root is still on `VisioFile` (#91)."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        assert not hasattr(vis, "zip_file_contents")
        assert not hasattr(vis, "directory")
```

Run: `uv run pytest tests/test_part_names.py -q -k no_zip`. Expected: FAIL.

- [ ] **Step 2: Delete the source.**
  - `git rm src/vsdxkit/zip_contents.py`.
  - In `vsdxfile.py`:
    - delete the `from .zip_contents import …` line;
    - delete `self.directory = …`;
    - delete the `self.zip_file_contents` declaration and its comment;
    - in `open_vsdx_file`, replace `self._load_zip_file_contents_to_memory()` with the two lines that open the store and record `_opened_filename`;
    - delete `_load_zip_file_contents_to_memory`;
    - in `save_vsdx`, delete the `sync` comment and call.
  - Delete the `io` and `MutableMapping` imports if they are unused afterwards.
  - In `package.py`, delete `write_bytes_keeping_tree`, and delete any import that becomes unused (`MalformedPackageError`, `parse_part`) only if nothing else in the file uses it.

- [ ] **Step 3: Delete the tests whose subject is the view or `write_bytes_keeping_tree`.**
  - `git rm tests/test_zip_contents_view.py`.
  - In `tests/test_visiofile_package_store.py`, delete:
    - `test_zip_file_contents_is_a_view_of_the_store`
    - `test_writing_a_page_back_through_the_view_keeps_the_tree_attached`
    - `test_different_xml_written_through_the_view_reaches_the_page_and_disk`
    - `test_truncating_a_read_buffer_of_a_parsed_page_keeps_the_tree_attached`
  - In `tests/test_byte_preserving_save.py`, delete:
    - `test_a_tree_assigned_after_a_pages_bytes_were_flushed_is_saved`
    - `test_a_rels_tree_assigned_after_the_view_deleted_the_part_is_saved`
    - `test_none_assigned_to_rels_after_the_view_wrote_bytes_over_them_removes_the_part`
    - `test_a_tree_assigned_after_the_view_deleted_a_pages_part_is_saved`
  - Every test in `tests/test_package_store.py` (and elsewhere) that calls `write_bytes_keeping_tree`. Find them with `grep -rn write_bytes_keeping_tree tests`.

  Before deleting each one, read it. If it asserts something about the document other than the view's own mechanics, keep that assertion by moving it to the store, list it in the report, and delete only the view part.

- [ ] **Step 4: Migrate the tests that use the view as a tool.**
  - `tests/test_errors.py:879` and `tests/test_save_destinations.py:63` empty the package: `for name in vis._package.names(): vis._package.remove(name)`.
  - `tests/test_visiofile_package_store.py:369` (`test_assigning_masters_xml_over_a_malformed_part_does_not_parse_it`): `vis._package.write_bytes("/visio/masters/masters.xml", b"<Masters")`, then drop the `io` import if unused. Update its docstring's "bytes written through `zip_file_contents`" to "bytes that are not XML".
  - `tests/test_namespaces.py:309-337, 356, 396-398`:
    - `vis.zip_file_contents.items()` → `((name, vis._package.read_bytes(name)) for name in vis._package.names())`;
    - `.getvalue()` goes away, since `read_bytes` returns bytes;
    - `vis.zip_file_contents[f"{vis.directory}/visio/pages/_rels/page1.xml.rels"].getvalue()` → `vis._package.read_bytes("/visio/pages/_rels/page1.xml.rels")`;
    - `vis.zip_file_contents[f"{vis._masters_folder}/masters.xml"]` → `vis._package.read_bytes("/visio/masters/masters.xml")`;
    - update the docstring at line 309 to "Read from the package store rather than from a saved file".
  - `tests/test_visiofile.py:618` `test_load_zip_file_contents` → rename it to `test_every_xml_part_of_an_opened_document_parses`. Iterate `vis._package.names()`, and for each name ending `.xml` or `.rels`, assert `vis._package.read_xml(name) is not None`. Keep whatever else it asserts. Drop the `file_to_xml` import only if Task 4 hasn't run yet and nothing else uses it.
  - `tests/test_package_store_save.py:364-372`: keep the test and reword the docstring. The NUL check guards every writer, and it no longer mentions the view.
  - `tests/test_byte_preserving_save.py` and `tests/test_visiofile_package_store.py`: any remaining `vis.directory` or `vis.zip_file_contents` from Task 2's interim spelling.

- [ ] **Step 5: Fix docstrings and comments that describe the view.** `grep -rn "zip_file_contents\|write_bytes_keeping_tree\|ZipFileContentsView\|_WriteThroughBuffer" src tests`. Rewrite each hit so it describes the code as it now is, or delete it where it only explained the view: `package.py`'s docstrings, `pages.py:_attached`'s docstring and `_rels_attached`'s comment. Task 5 rewrites `_attached` and `_rels_attached`, so a one-line holding edit there is enough.

- [ ] **Step 6: Run the gates.** Run all four gates.
Expected: all green, and `grep -rn "zip_file_contents\|\.directory\b\|part_name_for_path\|ZipFileContentsView\|write_bytes_keeping_tree" src tests` returns nothing. `tests/test_part_names.py`'s docstring and the no-attribute test are the only exceptions.

- [ ] **Step 7: Commit.**

```bash
git add -A src tests
git commit -m "refactor!: delete zip_file_contents and VisioFile.directory (#91)" -m "BREAKING CHANGE: VisioFile.zip_file_contents and VisioFile.directory are removed. Work on the document through its object model; to read raw part bytes, open the saved file with zipfile." -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_014SeJzNKgmmqyg4BHg7odRt"
```

### Task 4: Delete `xmlio`'s mapping helpers

**Files:**
- Modify: `src/vsdxkit/xmlio.py`:
  - delete `file_to_xml` (290-294), `xml_to_file` (320-322), `require_xml_tree` (339-346) and `require_root` (349-351);
  - fix the `parse_part` docstring (228) and the `serialise_part` docstring (300-302);
  - delete the `Mapping`, `MutableMapping` and `io` imports if they are unused.
- Modify: `src/vsdxkit/vsdxfile.py:53-62`: delete the `file_to_xml` re-export and its comment.
- Modify tests: `tests/test_namespaces.py:125-206`, `tests/test_visiofile.py:13`, `tests/test_errors.py:246-253`, and the docstrings at `test_errors.py:320,369`.

**Interfaces:**
- Consumes: `xmlio.parse_part(data: bytes, name: str = "")` and `xmlio.serialise_part(tree) -> bytes`, both unchanged.
- Produces: `xmlio` has none of the four names, and `vsdxkit.vsdxfile` has no `file_to_xml`.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_part_names.py`:

```python
@pytest.mark.parametrize("name", ["file_to_xml", "xml_to_file", "require_xml_tree", "require_root"])
def test_xmlio_has_no_helpers_over_the_old_mapping(name):
    """Fails if a helper that took the pre-store `{path: BytesIO}` mapping is still in `xmlio` (#91)."""
    import vsdxkit.vsdxfile
    import vsdxkit.xmlio

    assert not hasattr(vsdxkit.xmlio, name)
    assert not hasattr(vsdxkit.vsdxfile, name)
```

Run: `uv run pytest tests/test_part_names.py -q -k xmlio_has_no`. Expected: FAIL.

- [ ] **Step 2: Move the namespace tests onto `parse_part` and `serialise_part`.** In `tests/test_namespaces.py`:

```python
def _round_trip_part(source: str) -> str:
    """Parse a part the way the library does, then write it straight back out."""
    return xmlio.serialise_part(xmlio.parse_part(source.encode("utf-8"))).decode("utf-8")
```

At lines 174-179 and 206, apply the same replacement: `xmlio.file_to_xml(...)` → `xmlio.parse_part(data)`, and `xml_to_file(tree, "part.xml", contents)` followed by `contents["part.xml"].getvalue()` → `xmlio.serialise_part(tree)`. Each test's assertions stay unchanged. Update the docstring at line 275 so it says `parse_part`.

- [ ] **Step 3: Delete the helpers and move their other tests.**
  - Delete the four functions from `xmlio.py`, and the re-export block from `vsdxfile.py`.
  - In `parse_part`'s docstring, say the one route in is `PackageStore`'s promotion.
  - In `serialise_part`'s docstring, say it is the one writer of a part's bytes.
  - `tests/test_errors.py:246` `test_require_xml_tree_raises_missing_part_error` → rename it to `test_requiring_an_absent_part_raises_missing_part_error`. It asserts `PackageStore.require_xml("/visio/absent.xml")` raises `MissingPartError`, on a store opened from `test1.vsdx`. If `tests/test_package_store.py` already has exactly that test, delete this one instead and say so in the report.
  - Update the docstrings at `test_errors.py:320` and `369`, which name `file_to_xml` and `require_xml_tree`, so they name the store's promotion and `require_xml`.
  - `tests/test_visiofile.py:13`: delete the import.

- [ ] **Step 4: Run the gates.** Run all four gates. Expected: green. `grep -rn "file_to_xml\|xml_to_file\|require_xml_tree\|require_root" src tests` returns only `test_part_names.py`.

- [ ] **Step 5: Commit.**

```bash
git add -A src tests
git commit -m "refactor!: delete xmlio's helpers over the old part mapping (#91)" -m "BREAKING CHANGE: vsdxkit.xmlio.file_to_xml, xml_to_file, require_xml_tree and require_root are removed, and so is vsdxkit.vsdxfile.file_to_xml. parse_part(bytes) and serialise_part(tree) do the same work on bytes." -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_014SeJzNKgmmqyg4BHg7odRt"
```

### Task 5: Simplify `Page._attached` and `_rels_attached`

**Files:**
- Modify: `src/vsdxkit/pages.py:252-296`
- Test: `tests/test_visiofile_package_store.py`, `tests/test_byte_preserving_save.py` (existing tests), and `tests/test_part_names.py`

**Interfaces:**
- Consumes: Task 3's state. Nothing can write a page's part as bytes, or delete it, behind a live page.
- Produces: `_attached() -> bool` is `self._holds(self.filename, self._xml)`. `_rels_attached()` accepts a missing rels part, or its own tree, and nothing else.

- [ ] **Step 1: Look for any other route to a `BytesPart` or missing part under a live page.** Grep for `write_bytes(` and `remove(` in `src/`. For each call, decide whether its name can be a live page's part or a live page's rels part. Put the list, with a verdict per call, in the report.

  If a route exists, keep the branch it needs. Add a test that reaches it through public API and name the route in the docstring, then skip Step 3's change for that branch.

- [ ] **Step 2: Write the tests that pin what must keep working.** Append to `tests/test_part_names.py`:

```python
def test_a_removed_pages_xml_assignment_writes_nothing(vsdx_copy):
    """Fails if a page removed from the document can still write its part."""
    with VisioFile(vsdx_copy("test2.vsdx")) as vis:
        removed = vis.pages[-1]
        name = removed.filename
        vis.remove_page_by_index(len(vis.pages) - 1)
        removed.xml = ET.ElementTree(ET.fromstring(ET.tostring(removed.xml.getroot())))
        assert vis._package.part(name) is None


def test_a_page_with_no_rels_part_gets_one_on_assignment(vsdx_copy):
    """Fails if a live page with no relationship part cannot be given one."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        assert page.rels_xml is None, "the fixture has changed: page 1 should have no rels part"
        page.rels_xml_filename = f"/visio/pages/_rels/{page.filename.rsplit('/', 1)[-1]}.rels"
        page.rels_xml = ET.ElementTree(
            ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
        )
        assert vis._package.part(page.rels_xml_filename) is not None
```

Run: `uv run pytest tests/test_part_names.py -q -k "removed_pages_xml or no_rels_part"`
Expected: PASS. These pin behaviour that must survive Step 3, so they pass before it. Run them again after it.

- [ ] **Step 3: Simplify.** In `pages.py`:

```python
    def _attached(self) -> bool:
        """Whether an assignment to `xml` may write this page's part.

        A caller may keep holding a `Page` after it has been removed from the
        document (`VisioFile.remove_page_by_index`); a later assignment to its
        `xml` must not resurrect the part it was removed from. Nor may it
        write over the part of the page added after it: removal frees the part
        name, and the next page takes it. So this asks whether the part at the
        page's name is this page's own tree, not merely whether there is one.
        """
        return self._holds(self.filename, self._xml)

    def _rels_attached(self) -> bool:
        """Whether an assignment to `rels_xml` may write this page's relationship part.

        Only while the page itself is attached, and only over the relationship
        part the page holds -- or where the package holds none yet, which is
        how one is first created. A removed page's rels name is freed along
        with its page's, and the page that takes the name must not be given
        the removed page's relationships.
        """
        if self.rels_xml_filename is None or not self._attached():
            return False
        held = self.vis._package.part(self.rels_xml_filename)
        if held is None:
            return True
        return isinstance(held, XmlPart) and held.tree is self._rels_xml
```

Delete the `BytesPart` import from `pages.py` if it's unused afterwards.

- [ ] **Step 4: Run the gates.** Run all four gates. Expected: green, including `test_a_removed_page_does_not_write_its_part_back`, `test_a_removed_page_does_not_clobber_a_page_that_reuses_its_part_name`, `test_clearing_a_pages_rels_takes_its_part_out_of_the_package` and the two new tests.

- [ ] **Step 5: Commit.**

```bash
git add src/vsdxkit/pages.py tests/test_part_names.py
git commit -m "refactor: a page is attached exactly when the store holds its tree (#91)" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_014SeJzNKgmmqyg4BHg7odRt"
```

### Task 6: Move `KNOWN_DRIFT.md` into the README, and check the output is unchanged

**Files:**
- Delete: `tests/fixtures/package_manifests/KNOWN_DRIFT.md`
- Modify: `README.md`, "Open, edit and save" (after the in-place save example, around line 81); `tests/test_package_manifest.py:12` and `:429`, the two references to it.

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: the finished branch.

- [ ] **Step 1: Add the README note.** After the paragraph and code block that show `vis.save_vsdx()` saving in place, add:

```markdown
A save writes every part you did not change exactly as it arrived. A part you did change is written as equivalent XML, but not in Visio's own spelling: the XML declaration, attribute quotes, empty-element form and namespace declarations can differ, and a CRLF inside text becomes LF. Visio and LibreOffice open both.
```

- [ ] **Step 2: Delete `KNOWN_DRIFT.md` and its references.** `git rm tests/fixtures/package_manifests/KNOWN_DRIFT.md`. At `tests/test_package_manifest.py:12` and `:429`, rewrite the sentences that point at it. Line 12 describes what the manifest test allows, and line 429 what a no-op save preserves. Say it directly, and point at the README note where the edited-part spelling matters. Then `grep -rn KNOWN_DRIFT . --include=*.py --include=*.md --include=*.rst`. The only hits allowed are under `.hermes/plans/`.

- [ ] **Step 3: Check the file output is unchanged.**
Run: `uv run python <scratchpad>/output_probe.py . <scratchpad>/91-after.json`, then compare with this script:

```python
import json, sys
before, after = (json.load(open(p)) for p in sys.argv[1:3])
bad = []
for rel in sorted(set(before) | set(after)):
    b, a = before.get(rel), after.get(rel)
    if b is None or a is None or b.get("error") != a.get("error") or b.get("steps") != a.get("steps"):
        bad.append((rel, "outcome", b and (b.get("error"), b.get("steps")), a and (a.get("error"), a.get("steps"))))
        continue
    if "members" not in b:
        continue
    unstable = set(b.get("unstable", []))
    if list(b["members"]) != list(a["members"]):
        bad.append((rel, "member list", list(b["members"]), list(a["members"])))
    for name, digest in b["members"].items():
        if name not in unstable and a["members"].get(name) != digest:
            bad.append((rel, "bytes", name))
print("\n".join(map(str, bad)) or "identical")
sys.exit(1 if bad else 0)
```

Expected: `identical`. Any difference is a finding: investigate it, don't explain it away. Report the unstable members.

- [ ] **Step 4: Run the acceptance greps.**
Run: `grep -rn "zip_file_contents\|\.directory\b\|part_name_for_path\|file_to_xml\|xml_to_file" src`
Expected: no output.

- [ ] **Step 5: Run every gate, plus Python 3.10.** Run the four gates and `uv run --python 3.10 --isolated python -m pytest tests -q`. Expected: all green.

- [ ] **Step 6: Commit.**

```bash
git add -A README.md tests
git commit -m "docs: say how a save spells an edited part, and retire KNOWN_DRIFT.md (#91)" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>" -m "Claude-Session: https://claude.ai/code/session_014SeJzNKgmmqyg4BHg7odRt"
```

---

## Finishing (controller)

- Split the stack.
  - PR 1 is `refactor/91-retire-zip-file-contents`, up to and including Task 2's commit.
  - PR 2 is `refactor/91-delete-zip-file-contents`, with Tasks 3–6.
  - Create PR 2's branch at Task 2's commit before dispatching Task 3.
- Open both PRs with `gh stack`.
  - PR titles: `refactor!: name every part by its part name` and `refactor!: delete zip_file_contents and the helpers that served it`.
  - Each body ends with its `BREAKING CHANGE:` paragraph, which is what release-please reads from the squash commit, then the attribution lines.
  - PR 1's body says `Part of #91`, and PR 2's says `Closes #91`.
- Watch CI and Codex on each head commit, and answer every inline comment before asking the user to merge. Merging needs the user's explicit approval. Never merge #349.
