# #89 Byte-Preserving Atomic Save — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `PackageStore` the one authoritative copy of an open package, so
a save writes every member exactly once through a single atomic writer:
untouched parts go out as the bytes they arrived as, and changed parts are
serialised once.

**Architecture:** `PackageStore` (landed in #355) gains `remove` and `save`.
`VisioFile` opens a `PackageStore` and reads every XML part through `read_xml`,
so the trees it mutates *are* the store's trees. `zip_file_contents` becomes a
transitional `MutableMapping` view over the store (#91 deletes it). The
re-serialise-everything block in `save_vsdx` goes, along with the eager
`masters.xml` writes. Wholesale tree replacements (`page.xml = …`,
`vis.app_xml = …`) write through to the store.

**Tech Stack:** Python ≥3.10, `xml.etree.ElementTree`, `zipfile`, pytest, ruff,
pyrefly (strict), uv.

**Spec:** issue #89 (scope + acceptance criteria),
`.hermes/plans/2026-09-12_simplification-usability-refactor.md` §"Authoritative
package representation" and §"Phase 1 — PackageStore". Read #360's resolution
and the #89 comment first. Removing the unconditional rewrites unmasks any part
serialised outside `xmlio`, and #364 fixed the two known ones.

## Global Constraints

- Every tree becomes archive bytes through `xmlio.serialise_part` and nowhere
  else (#360/#364).
- `PackageStore` names are OPC part names (`/visio/document.xml`). They are
  never repaired: a name without the leading slash raises `ValueError`.
- An explicit save target does not rebind the source: `store.source` and
  `VisioFile.filename` are unchanged by `save(target)`.
- The save is atomic: a same-directory temporary file, then `os.replace`, and
  the source's mode is kept (existing `test_save_destinations.py` must pass
  unmodified, including the `zipfile.ZipFile.writestr` monkeypatch test, so
  members are written with `writestr`).
- The public API is unchanged: `zip_file_contents` keeps working as a mapping of
  `f"{vis.directory}/{member}"` → `io.BytesIO` until #91.
- Gate before every commit: `uv run --no-sync python -m pytest tests -q`, `uv
  run --no-sync ruff check src tests tools`, `uv run --no-sync ruff format
  --check src tests tools`, `uv run --no-sync pyrefly check src/vsdxkit
  --min-severity warn --output-format min-text`.
- House style: docstrings say *why*, in full sentences, the way `package.py`
  does. Tests carry a docstring saying which production change would make them
  fail. Conventional-commit subjects (`feat:`, `fix:`, `refactor:`, `test:`).
- **Check Codex's inline comments before merging any PR in this stack:** `gh api
  repos/firmfooting/vsdxkit/pulls/<n>/comments`, and confirm the review ran on
  the head commit.

## Decisions made here (flag in review if you disagree)

1. **Members are written `ZIP_DEFLATED`.** Today's writer uses `zipfile`'s
   default, `ZIP_STORED`. Every fixture arrives deflated (307/307 members), and
   saving `test1.vsdx` grows it from 15 KB to 59 KB. Byte preservation is about
   member *bytes*, and this only changes the container. Task 2 pins it.
2. **Page objects keep their `_xml` reference** instead of looking the tree up
   in the store on every access. A caller who still holds a removed `Page` keeps
   a working, detached tree, and the setter writes through only while the page's
   own part is still in the package.
3. **`#366` folds in here** (`masters.xml.rels` becomes a tree). **`#367` does
   not:** `_bootstrap_masters` still has its test, and deciding whether it is
   redundant is separate.

## Review Focus

1. **A caller replaces a part wholesale** (`page.xml = tree` as Jinja rendering
   does, or `vis.app_xml = tree`). Once `save_vsdx` stops rewriting, only the
   write-through setters get that onto disk. → Task 5 tests.
2. **A caller still holding a removed `Page`** sets `page.xml`. It must not put
   an orphan part back into the package. → Task 5 test.
3. **Two saves with a mutation in between.** The second save must carry the
   second mutation, because comparing against a baseline must not "use up" the
   change. → Task 7 test.
4. **Save-as then save in place.** The second save must write to the original
   source, not to the save-as target. → Task 2 (store) and Task 7 (`VisioFile`)
   tests.
5. **A failure mid-write.** The target keeps its old bytes, and no `.tmp` file
   is left in the directory. → Task 2 test.

## Stack layout (`gh stack`, based on `main`)

| PR | Branch | Tasks | Closes |
| --- | --- | --- | --- |
| 1 | `feat/89-package-store-save` | 1–2 | — |
| 2 | `refactor/89-visiofile-reads-through-store` | 3–4 | — |
| 3 | `feat/89-byte-preserving-save` | 5–7 | #89, #366 |

```bash
gh stack init feat/89-package-store-save          # from an up-to-date main
# ... Tasks 1-2, commits ...
gh stack add refactor/89-visiofile-reads-through-store
# ... Tasks 3-4 ...
gh stack add feat/89-byte-preserving-save
# ... Tasks 5-7 ...
gh stack submit --auto --open                     # then `gh pr edit <n> --title … --body-file …` per PR
```

PR 2 is a pure refactor: behaviour is identical and the suite passes unchanged.
PR 3 is the behavioural change, so it's the one to review hardest.

---

### Task 1: `PackageStore.remove`

**Files:**

- Modify: `src/vsdxkit/package.py` (class `PackageStore`, after `write_xml`)
- Test: `tests/test_package_store.py`

**Interfaces:**

- Produces: `PackageStore.remove(name: str) -> None`. Raises `ValueError` for a
  name that is not a part name, and `KeyError(name)` for an absent part.

- [ ] **Step 1: Write the failing tests** (append to the "part names"/write
      section of `tests/test_package_store.py`, and add `remove` to the existing
      parametrised name-check test):

```python
# in test_every_way_into_the_store_checks_the_name's parametrize list, add:
        lambda store, name: store.remove(name),
```

```python
def test_remove_takes_the_part_out_of_the_package(store: PackageStore):
    """A removed page must not be written; the save writes what `names` lists."""
    store.remove(PAGE_PART)
    assert PAGE_PART not in store.names()
    assert store.read_bytes(PAGE_PART) is None


def test_a_part_written_after_removal_goes_on_the_end(store: PackageStore):
    """Removal forgets the position too; only a write *over* a part keeps its place."""
    store.remove(PAGE_PART)
    store.write_bytes(PAGE_PART, b"<PageContents/>")
    assert store.names()[-1] == PAGE_PART


def test_removing_an_absent_part_is_a_key_error(store: PackageStore):
    """KeyError, so a `MutableMapping` built on this gets `pop(key, default)` for free."""
    with pytest.raises(KeyError):
        store.remove("/visio/pages/page99.xml")
```

- [ ] **Step 2: Run to verify failure**
Run: `uv run --no-sync python -m pytest tests/test_package_store.py -q -k
"remove or checks_the_name"` Expected: FAIL with `AttributeError: 'PackageStore'
object has no attribute 'remove'`

- [ ] **Step 3: Implement**

```python
    def remove(self, name: str) -> None:
        """Take a part out of the package, or raise KeyError if it is not in it.

        A KeyError rather than a quiet no-op: the callers are removing a page
        or a relationship part they believe is there, and one that is not is a
        package the caller has misread.
        """
        checked = _checked(name)
        if checked not in self._parts:
            raise KeyError(name)
        del self._parts[checked]
```

- [ ] **Step 4: Run to verify pass.** Same command. Expected: PASS.
- [ ] **Step 5: Commit** — `feat: let the package store remove a part`

---

### Task 2: `PackageStore.save` — the single archive writer

**Files:**

- Modify: `src/vsdxkit/package.py` (imports: `contextlib`, `shutil`, `tempfile`;
  new method `save` on `PackageStore`)
- Test: `tests/test_package_store_save.py` (new)

**Interfaces:**

- Consumes: `PackageStore.names()`, `PackageStore.read_bytes()`, `PackageStore.source`.
- Produces: `PackageStore.save(target: str | os.PathLike[str] | None = None) ->
  Path`, which returns the absolute path it wrote. With `target=None` it writes
  over `self.source`. It never changes `self.source`.

- [ ] **Step 1: Write the failing tests** in `tests/test_package_store_save.py`:

```python
"""What `PackageStore.save` promises: one writer, every member once, atomically.

The expected side of each comparison is read with `zipfile` straight from the
fixture, never through the store (see test_package_store.py's docstring).
"""

from __future__ import annotations

import os
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from vsdxkit.package import PackageStore

BASEDIR = os.path.dirname(os.path.realpath(__file__))
PAGE_PART = "/visio/pages/page1.xml"


def _members(path: str | os.PathLike[str]) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        return [(info.filename, archive.read(info)) for info in archive.infolist() if not info.is_dir()]


@pytest.fixture
def source(tmp_path) -> Path:
    copy = tmp_path / "source.vsdx"
    shutil.copy(os.path.join(BASEDIR, "test1.vsdx"), copy)
    return copy


def test_an_untouched_store_saves_every_member_as_it_arrived(source, tmp_path):
    """Names, order and bytes. Fails if save re-serialises, reorders or drops a member."""
    target = tmp_path / "out.vsdx"
    PackageStore.open(source).save(target)
    assert _members(target) == _members(source)


def test_promoting_parts_without_changing_them_changes_nothing(source, tmp_path):
    """The whole point of the baseline: a parsed-but-untouched part writes its original bytes."""
    store = PackageStore.open(source)
    for name in store.names():
        if name.endswith((".xml", ".rels")):
            store.read_xml(name)
    target = tmp_path / "out.vsdx"
    store.save(target)
    assert _members(target) == _members(source)


def test_a_changed_part_is_the_only_member_that_changes(source, tmp_path):
    store = PackageStore.open(source)
    root = store.require_xml(PAGE_PART).getroot()
    assert root is not None
    root.set("VsdxkitMarker", "1")
    target = tmp_path / "out.vsdx"
    store.save(target)
    before, after = dict(_members(source)), dict(_members(target))
    assert list(after) == list(before)
    assert [name for name in before if before[name] != after[name]] == [PAGE_PART[1:]]


def test_every_member_is_written_exactly_once(source, tmp_path):
    """A duplicated member name is a corrupt package that some readers accept silently."""
    target = tmp_path / "out.vsdx"
    PackageStore.open(source).save(target)
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
    assert len(names) == len(set(names))


def test_members_are_deflated(source, tmp_path):
    """Visio writes deflated members; the old writer's ZIP_STORED quadrupled file size."""
    target = tmp_path / "out.vsdx"
    PackageStore.open(source).save(target)
    with zipfile.ZipFile(target) as archive:
        assert {info.compress_type for info in archive.infolist()} == {zipfile.ZIP_DEFLATED}


def test_save_with_no_target_writes_over_the_source(source):
    store = PackageStore.open(source)
    store.write_xml("/visio/extra.xml", ET.ElementTree(ET.Element("Extra")))
    assert store.save() == source.resolve()
    assert "visio/extra.xml" in dict(_members(source))


def test_save_as_does_not_rebind_the_source(source, tmp_path):
    """A later `save()` still writes to where the package was opened from."""
    store = PackageStore.open(source)
    elsewhere = tmp_path / "elsewhere.vsdx"
    store.save(elsewhere)
    store.write_xml("/visio/extra.xml", ET.ElementTree(ET.Element("Extra")))
    store.save()
    assert store.source == source
    assert "visio/extra.xml" in dict(_members(source))
    assert "visio/extra.xml" not in dict(_members(elsewhere))


def test_a_removed_part_is_not_written(source, tmp_path):
    store = PackageStore.open(source)
    store.remove(PAGE_PART)
    target = tmp_path / "out.vsdx"
    store.save(target)
    assert PAGE_PART[1:] not in dict(_members(target))


def test_save_creates_missing_parent_directories(source, tmp_path):
    target = tmp_path / "a" / "b" / "out.vsdx"
    PackageStore.open(source).save(target)
    assert target.exists()


def test_a_failed_write_leaves_the_target_and_no_temporary_file(source, monkeypatch):
    original = source.read_bytes()
    store = PackageStore.open(source)

    def fail(*_args, **_kwargs):
        raise RuntimeError("injected write failure")

    monkeypatch.setattr(zipfile.ZipFile, "writestr", fail)
    with pytest.raises(RuntimeError, match="injected write failure"):
        store.save()
    assert source.read_bytes() == original
    assert sorted(p.name for p in source.parent.iterdir()) == [source.name]


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not meaningful on Windows")
def test_a_new_target_takes_the_source_mode(source, tmp_path):
    source.chmod(0o640)
    target = tmp_path / "out.vsdx"
    PackageStore.open(source).save(target)
    assert target.stat().st_mode & 0o777 == 0o640
```

- [ ] **Step 2: Run to verify failure**
Run: `uv run --no-sync python -m pytest tests/test_package_store_save.py -q`
Expected: FAIL, `AttributeError: 'PackageStore' object has no attribute 'save'`

- [ ] **Step 3: Implement** (in `PackageStore`, after `remove`; add `import
      contextlib, shutil, tempfile` at the top of `package.py`):

```python
    def save(self, target: str | os.PathLike[str] | None = None) -> Path:
        """Write the package to `target`, or back over the source, and say where.

        The only archive writer. Every part goes out once, in `names()` order,
        as `read_bytes` gives it -- which is the original bytes for any part
        nothing changed, promoted or not. The archive is built beside the
        target and moved over it, so a failure part-way leaves the target as
        it was; the temporary file takes the target's mode, or the source's
        when the target is new.

        Saving elsewhere does not make elsewhere the source. A later `save()`
        with no target still writes where the package was opened from.
        """
        destination = Path(os.path.abspath(self.source if target is None else target))
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in self.names():
                    data = self.read_bytes(name)
                    assert data is not None  # names() lists only parts that are present
                    archive.writestr(name[1:], data)
            mode_source = destination if destination.exists() else Path(os.path.abspath(self.source))
            if mode_source.exists():
                shutil.copymode(mode_source, temporary)
            os.replace(temporary, destination)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)
        return destination
```

Note: `test_save_with_no_target_writes_over_the_source` compares against
`source.resolve()`. If `tmp_path` involves a symlink and `abspath` differs from
`resolve`, compare `os.path.abspath(source)` instead. Don't change the method to
`resolve()`, which would follow a symlinked target and replace the link's
destination instead of the link.

- [ ] **Step 4: Run to verify pass**, then the full gate (Global Constraints).
- [ ] **Step 5: Commit**: `feat: save the package store through one atomic
      archive writer`
- [ ] **Step 6: Open PR 1** (`gh stack submit --auto --open`, then edit
      title/body). The body names the ZIP_DEFLATED decision and says nothing
      calls `save` yet.

---

### Task 3: the transitional `zip_file_contents` view

**Files:**

- Create: `src/vsdxkit/zip_contents.py`
- Modify: `src/vsdxkit/xmlio.py` (widen `file_to_xml`, `xml_to_file`,
  `require_xml_tree`, `require_root` to take `Mapping` / `MutableMapping` rather
  than `dict`)
- Test: `tests/test_zip_contents_view.py` (new)

**Interfaces:**

- Consumes: `PackageStore.names/part/read_bytes/write_bytes/remove`.
- Produces:
  - `part_name_for_path(directory: str, path: str) -> str | None`:
    `f"{directory}/visio/x.xml"` → `"/visio/x.xml"`, or None when `path` is not
    under `directory`.
  - `class ZipFileContentsView(MutableMapping[str, io.BytesIO])` with
    `__init__(self, store: PackageStore, directory: str)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_zip_contents_view.py`:

```python
"""`zip_file_contents` as a view over the package store, until #91 deletes it.

The view must keep every existing caller working while holding nothing
itself: a write through it is a write to the store, and a read is what the
store would save.
"""

from __future__ import annotations

import io
import os
import xml.etree.ElementTree as ET
import zipfile

import pytest

from vsdxkit.package import PackageStore
from vsdxkit.zip_contents import ZipFileContentsView, part_name_for_path

BASEDIR = os.path.dirname(os.path.realpath(__file__))
DIRECTORY = "/somewhere/test1"


@pytest.fixture
def store() -> PackageStore:
    return PackageStore.open(os.path.join(BASEDIR, "test1.vsdx"))


@pytest.fixture
def view(store) -> ZipFileContentsView:
    return ZipFileContentsView(store, DIRECTORY)


def test_part_name_for_path_strips_exactly_the_directory():
    assert part_name_for_path(DIRECTORY, f"{DIRECTORY}/visio/document.xml") == "/visio/document.xml"
    assert part_name_for_path(DIRECTORY, "/elsewhere/visio/document.xml") is None
    assert part_name_for_path(DIRECTORY, f"{DIRECTORY}x/visio/document.xml") is None


def test_keys_are_the_old_pseudo_paths_in_archive_order(view, store):
    with zipfile.ZipFile(os.path.join(BASEDIR, "test1.vsdx")) as archive:
        expected = [f"{DIRECTORY}/{name}" for name in archive.namelist() if not name.endswith("/")]
    assert list(view) == expected
    assert len(view) == len(store.names())


def test_a_read_is_what_the_store_would_save(view, store):
    tree = store.require_xml("/visio/pages/page1.xml")
    root = tree.getroot()
    assert root is not None
    root.set("VsdxkitMarker", "1")
    assert b"VsdxkitMarker" in view[f"{DIRECTORY}/visio/pages/page1.xml"].getvalue()


def test_a_write_is_a_write_to_the_store(view, store):
    view[f"{DIRECTORY}/visio/new.xml"] = io.BytesIO(b"<New/>")
    assert store.read_bytes("/visio/new.xml") == b"<New/>"


def test_membership_does_not_serialise_and_tolerates_foreign_keys(view):
    assert f"{DIRECTORY}/visio/document.xml" in view
    assert "/elsewhere/visio/document.xml" not in view
    assert f"{DIRECTORY}/visio/../escape.xml" not in view
    assert 42 not in view


def test_pop_and_clear_remove_from_the_store(view, store):
    view.pop(f"{DIRECTORY}/visio/pages/page1.xml")
    assert store.part("/visio/pages/page1.xml") is None
    assert view.pop(f"{DIRECTORY}/visio/pages/page1.xml", None) is None
    view.clear()
    assert store.names() == ()


def test_a_key_outside_the_directory_is_refused_on_write(view):
    with pytest.raises(ValueError):
        view["/elsewhere/visio/new.xml"] = io.BytesIO(b"<New/>")


def test_a_missing_key_is_a_key_error(view):
    with pytest.raises(KeyError):
        view[f"{DIRECTORY}/visio/missing.xml"]
    with pytest.raises(KeyError):
        view["/elsewhere/visio/document.xml"]
```

- [ ] **Step 2: Run to verify failure.** Expected: `ModuleNotFoundError: No
      module named 'vsdxkit.zip_contents'`

- [ ] **Step 3: Implement** `src/vsdxkit/zip_contents.py`:

```python
"""`VisioFile.zip_file_contents`, kept working over the package store until #91.

The old mapping held the package itself, keyed by a filesystem path no file was
ever at. The store holds it now, by part name, so this is only a translation:
it holds nothing, and every read and write lands in the store. A second copy
here would be a second writer, which is what #89 exists to remove.
"""

from __future__ import annotations

import io
from collections.abc import Iterator, MutableMapping

from .package import PackageStore


def part_name_for_path(directory: str, path: str) -> str | None:
    """The part name the old pseudo-path spells, or None if it is not under `directory`."""
    prefix = directory + "/"
    if not path.startswith(prefix):
        return None
    return "/" + path[len(prefix) :]


class ZipFileContentsView(MutableMapping[str, io.BytesIO]):
    """The store, addressed by `f"{directory}/{member}"` and valued as `BytesIO`."""

    def __init__(self, store: PackageStore, directory: str) -> None:
        self._store = store
        self._directory = directory

    def _name(self, key: object) -> str | None:
        return part_name_for_path(self._directory, key) if isinstance(key, str) else None

    def __getitem__(self, key: str) -> io.BytesIO:
        name = self._name(key)
        try:
            data = None if name is None else self._store.read_bytes(name)
        except ValueError:  # not a part name, so not a part
            data = None
        if data is None:
            raise KeyError(key)
        return io.BytesIO(data)

    def __setitem__(self, key: str, value: io.BytesIO) -> None:
        name = self._name(key)
        if name is None:
            raise ValueError(f"{key!r} is not under the package directory {self._directory!r}")
        self._store.write_bytes(name, value.getvalue())

    def __delitem__(self, key: str) -> None:
        name = self._name(key)
        if name is None:
            raise KeyError(key)
        self._store.remove(name)

    def __contains__(self, key: object) -> bool:
        # asked of the store's index rather than through __getitem__, which
        # would serialise a promoted part to answer a yes/no question
        name = self._name(key)
        if name is None:
            return False
        try:
            return self._store.part(name) is not None
        except ValueError:
            return False

    def __iter__(self) -> Iterator[str]:
        # names() is a snapshot, so deleting while iterating is safe
        return (f"{self._directory}{name}" for name in self._store.names())

    def __len__(self) -> int:
        return len(self._store.names())
```

In `xmlio.py`, change the annotations only: `file_to_xml(filename: str,
zip_file_contents: Mapping[str, io.BytesIO])`, `require_xml_tree(...,
zip_file_contents: Mapping[...])`, `require_root(..., Mapping[...])`, and
`xml_to_file(..., zip_file_contents: MutableMapping[str, io.BytesIO])`,
importing from `collections.abc`.

- [ ] **Step 4: Run to verify pass**, then the full gate.
- [ ] **Step 5: Commit** — `refactor: add a zip_file_contents view over the
      package store`

---

### Task 4: `VisioFile` opens a `PackageStore` and reads its trees through it

This task is behaviour-identical: `save_vsdx` keeps its rewrites, and only the
storage underneath changes. The whole suite must pass **without editing any
existing test**.

**Files:**

- Modify: `src/vsdxkit/vsdxfile.py`: `__init__` (drop `self.zip_file_contents =
  {}`), `_load_zip_file_contents_to_memory`, `_save_zip_file_contents_to_disk`
  (delete; `save_vsdx` calls the store), `load_pages`, `load_master_pages`,
  `remove_page_by_index`, `save_vsdx`'s empty check. Add helpers `_part_name`,
  `_read_part_xml`, `_require_part_xml`.
- Modify: `src/vsdxkit/masters.py`: the mixin annotation `zip_file_contents:
  MutableMapping[str, io.BytesIO]`, declare `_package: PackageStore` and
  `_read_part_xml`, and use `_read_part_xml` at the rels read (line ~91) and the
  new-master read (line ~147).
- Test: `tests/test_visiofile_package_store.py` (new)

**Interfaces:**

- Consumes: Task 1–3 APIs.
- Produces (on `VisioFile`):
  - `self._package: PackageStore`
  - `self.zip_file_contents: ZipFileContentsView`
  - `_part_name(self, path: str) -> str`: the pseudo-path to the part name.
    Raises `ValueError` if the path is not under `self.directory`.
  - `_read_part_xml(self, path: str) -> ET.ElementTree[ET.Element] | None`: the
    store's own (promoted) tree.
  - `_require_part_xml(self, path: str, description: str) -> ET.ElementTree[ET.Element]`

- [ ] **Step 1: Write the failing tests** in `tests/test_visiofile_package_store.py`:

```python
"""`VisioFile` over `PackageStore`: the trees it edits are the store's trees."""

from __future__ import annotations

from vsdxkit import VisioFile
from vsdxkit.package import XmlPart


def test_the_page_tree_is_the_stores_tree(vsdx_copy):
    """Fails if the loader parses its own copy instead of promoting the store's part."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        held = vis._package.part(vis._part_name(page.filename))
        assert isinstance(held, XmlPart) and held.tree is page.xml


def test_the_document_parts_are_the_stores_trees(vsdx_copy):
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        for name, tree in [
            ("/visio/pages/pages.xml", vis.pages_xml),
            ("/visio/pages/_rels/pages.xml.rels", vis.pages_xml_rels),
            ("/[Content_Types].xml", vis.content_types_xml),
            ("/docProps/app.xml", vis.app_xml),
            ("/visio/document.xml", vis.document_xml),
            ("/visio/_rels/document.xml.rels", vis.document_xml_rels),
        ]:
            held = vis._package.part(name)
            assert isinstance(held, XmlPart) and held.tree is tree, name
        masters = vis._package.part("/visio/masters/masters.xml")
        assert isinstance(masters, XmlPart) and masters.tree.getroot() is vis.masters_xml


def test_zip_file_contents_is_a_view_of_the_store(vsdx_copy):
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        assert list(vis.zip_file_contents) == [f"{vis.directory}{name}" for name in vis._package.names()]
```

- [ ] **Step 2: Run to verify failure.** Expected: `AttributeError: 'VisioFile'
      object has no attribute '_package'`.

- [ ] **Step 3: Implement.** Key edits:

```python
# imports
from .package import PackageLimitError, PackageLimits, PackageStore, read_archive_members  # noqa: F401
from .zip_contents import ZipFileContentsView, part_name_for_path

    def _load_zip_file_contents_to_memory(self) -> None:
        """Open the package as a `PackageStore`, the one copy of it held from now on.

        `zip_file_contents` survives as a view over the store, keyed the old
        way, until #91 retires it.
        """
        self._package = PackageStore.open(self.filename, limits=self.limits)
        self.zip_file_contents = ZipFileContentsView(self._package, self.directory)

    def _part_name(self, path: str) -> str:
        """The OPC part name for one of this document's `{directory}/...` paths."""
        name = part_name_for_path(self.directory, path)
        if name is None:
            raise ValueError(f"{path!r} is not a part of this document")
        return name

    def _read_part_xml(self, path: str) -> ET.ElementTree[ET.Element] | None:
        """The store's own tree for a part, promoting it -- never a private copy."""
        return self._package.read_xml(self._part_name(path))

    def _require_part_xml(self, path: str, description: str) -> ET.ElementTree[ET.Element]:
        tree = self._read_part_xml(path)
        if tree is None:
            raise ValueError(f"expected XML part not found: {description} ({path})")
        return tree
```

Then, in `load_pages` / `load_master_pages`, replace every `file_to_xml(p,
self.zip_file_contents)` with `self._read_part_xml(p)`, every
`require_xml_tree(p, self.zip_file_contents, d)` with `self._require_part_xml(p,
d)`, and every `require_root(p, self.zip_file_contents, d)` with
`require_element(self._require_part_xml(p, d).getroot(), d)`. In `load_pages`,
`rels` and `self.pages_xml_rels` must now be **one** tree, and likewise `pages`
and `self.pages_xml`, so read each once and take `.getroot()`.

In `remove_page_by_index`, use `self._package.remove(self._part_name(...))` for
the page part, and for its rels part when `page.rels_xml_filename` names a
present part.

In `save_vsdx`: `if not self._package.names(): raise ValueError("cannot save an
empty package")`. The rewrites stay for now, and the final line becomes
`self._package.save(target)`. Delete `_save_zip_file_contents_to_disk`, then
`grep -rn _save_zip_file_contents_to_disk src tests` must be empty. Remove the
`tempfile`, `shutil`, `contextlib` and `zipfile` imports if they're now unused
(ruff will say).

`save_vsdx` must resolve `target` before `self._package.save(target)` exactly as
today, so a refused extension still leaves everything untouched.

- [ ] **Step 4: Run the new tests and then the full gate.** Every existing test
      must pass unmodified. If one fails, the refactor changed behaviour: fix
      the code, not the test. The one expected difference is output compression
      (Task 2); a test asserting file size or `ZIP_STORED` would be updated
      here, with the reason in the commit message.
- [ ] **Step 5: Commit** — `refactor: hold an open document in a PackageStore`
- [ ] **Step 6: `gh stack add refactor/89-visiofile-reads-through-store` must
      already have been run before Step 1**, then open PR 2 (title as the commit
      subject). The body says it's behaviour-identical apart from deflate, and
      that `save_vsdx` still rewrites every part.

---

### Task 5: replacing a part's tree writes through to the store

**Files:**

- Modify: `src/vsdxkit/vsdxfile.py`: turn `pages_xml`, `pages_xml_rels`,
  `content_types_xml`, `app_xml`, `document_xml`, `document_xml_rels`,
  `masters_xml` into properties backed by the store; add `_set_part_xml`; remove
  their `= None` initialisation in `__init__` and the assignments in
  `load_pages`/`load_master_pages` (the getters read the store).
- Modify: `src/vsdxkit/pages.py`: the `Page.xml` setter writes through, and
  `Page.rels_xml` becomes a property (backing `_rels_xml`) whose setter writes
  through.
- Modify: `src/vsdxkit/masters.py`, `src/vsdxkit/templating.py`: change mixin
  attribute declarations to property stubs if pyrefly requires it.
- Test: `tests/test_visiofile_package_store.py` (extend)

**Interfaces:**

- Produces:
  - `VisioFile._set_part_xml(self, name: str, tree: ET.ElementTree[ET.Element] |
    None) -> None`: writes `tree` to part `name` unless the store already holds
    that very tree object. `None` removes the part if present.
  - Constants in `vsdxfile.py`: `_PAGES_PART = "/visio/pages/pages.xml"`,
    `_PAGES_RELS_PART = "/visio/pages/_rels/pages.xml.rels"`,
    `_CONTENT_TYPES_PART = "/[Content_Types].xml"`, `_APP_PART =
    "/docProps/app.xml"`, `_DOCUMENT_PART = "/visio/document.xml"`,
    `_DOCUMENT_RELS_PART = "/visio/_rels/document.xml.rels"`, `_MASTERS_PART =
    "/visio/masters/masters.xml"`.
  - `Page._attached(self) -> bool`: True while the page's own part is in its
    document's package.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_visiofile_package_store.py`):

```python
import xml.etree.ElementTree as ET

from vsdxkit.xmlio import serialise_part


def test_assigning_a_document_part_replaces_it_in_the_store(vsdx_copy):
    """`vis.app_xml = tree` has to reach disk once save stops rewriting (Review Focus 1)."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        replacement = ET.ElementTree(ET.fromstring(serialise_part(vis.app_xml)))
        root = replacement.getroot()
        assert root is not None
        root.set("VsdxkitMarker", "1")
        vis.app_xml = replacement
        assert vis.app_xml is replacement
        assert b"VsdxkitMarker" in (vis._package.read_bytes("/docProps/app.xml") or b"")


def test_assigning_page_xml_replaces_the_page_part(vsdx_copy):
    """What Jinja rendering does to every page it renders (Review Focus 1)."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        replacement = ET.ElementTree(ET.fromstring(serialise_part(page.xml)))
        replacement.getroot().set("VsdxkitMarker", "1")
        page.xml = replacement
        assert b"VsdxkitMarker" in (vis._package.read_bytes(vis._part_name(page.filename)) or b"")


def test_a_removed_page_does_not_write_its_part_back(vsdx_copy):
    """A caller still holding a removed Page must not resurrect an orphan part (Review Focus 2)."""
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[1]
        name = vis._part_name(page.filename)
        vis.remove_page_by_index(1)
        page.xml = ET.ElementTree(ET.Element("PageContents"))
        assert vis._package.part(name) is None


def test_reassigning_the_same_tree_keeps_the_promotion_baseline(vsdx_copy):
    """Identity is not a change: the part must still save as its original bytes."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        before = vis._package.part("/docProps/app.xml")
        vis.app_xml = vis.app_xml
        assert vis._package.part("/docProps/app.xml") is before
```

- [ ] **Step 2: Run to verify failure.** Expected: the first two fail on the
      marker assertion, and the "removed page" test passes already or fails on
      `_attached`. That's fine, since it pins a guard the setter is about to
      need.

- [ ] **Step 3: Implement.**

```python
    def _set_part_xml(self, name: str, tree: ET.ElementTree[ET.Element] | None) -> None:
        """Make `tree` the part called `name`, or take the part out for None.

        Handing back the tree the store already holds is not a change, and
        writing it would throw away the baseline that lets an untouched part
        save as the bytes it arrived as.
        """
        held = self._package.part(name)
        if tree is None:
            if held is not None:
                self._package.remove(name)
            return
        if isinstance(held, XmlPart) and held.tree is tree:
            return
        self._package.write_xml(name, tree)

    @property
    def app_xml(self) -> ET.ElementTree[ET.Element] | None:
        return self._package.read_xml(_APP_PART)

    @app_xml.setter
    def app_xml(self, tree: ET.ElementTree[ET.Element] | None) -> None:
        self._set_part_xml(_APP_PART, tree)

    # ... identical pairs for pages_xml, pages_xml_rels, content_types_xml,
    # document_xml, document_xml_rels (write them all out; no loop/metaprogramming)

    @property
    def masters_xml(self) -> ET.Element | None:
        """The `<Masters>` root, read from the store so it can never be a stale copy."""
        tree = self._package.read_xml(_MASTERS_PART)
        return None if tree is None else tree.getroot()

    @masters_xml.setter
    def masters_xml(self, root: ET.Element | None) -> None:
        current = self._package.read_xml(_MASTERS_PART)
        if root is not None and current is not None and current.getroot() is root:
            return
        self._set_part_xml(_MASTERS_PART, None if root is None else ET.ElementTree(root))
```

`_pages_filename()` must equal `f"{self.directory}{_PAGES_PART}"`, so keep it
and have `load_pages` use the constant's pseudo-path through it. `XmlPart` is
imported from `.package`.

In `pages.py`:

```python
    def _attached(self) -> bool:
        """Whether this page's own part is still in its document's package."""
        return self.vis._package.part(self.vis._part_name(self.filename)) is not None

    @xml.setter
    def xml(self, value: ET.ElementTree[ET.Element]) -> None:
        self.vis._require_open("Setting Page.xml")
        attached = self._attached()
        self._xml = value
        if attached:
            self.vis._set_part_xml(self.vis._part_name(self.filename), value)

    @property
    def rels_xml(self) -> ET.ElementTree[ET.Element] | None:
        return self._rels_xml

    @rels_xml.setter
    def rels_xml(self, value: ET.ElementTree[ET.Element] | None) -> None:
        self._rels_xml = value
        if value is not None and self.rels_xml_filename is not None and self._attached():
            self.vis._set_part_xml(self.vis._part_name(self.rels_xml_filename), value)
```

In `Page.__init__`, set `self._rels_xml = None` in place of `self.rels_xml =
None`. The constructor must **not** write to the store: every caller either
passes the store's own tree (load, master import) or writes the part itself
first (`_create_page`, Task 6).

- [ ] **Step 4: Run to verify pass**, then the full gate.
- [ ] **Step 5: Commit**: `feat: write a replaced part tree through to the
      package store`

---

### Task 6: every mutation lands in the store without a save-time rewrite

**Files:**

- Modify: `src/vsdxkit/vsdxfile.py`, `_create_page`: write the new page part
  before constructing `Page`, and set `rels_xml_filename` *before* `rels_xml`
  for a copied page.
- Modify: `src/vsdxkit/masters.py`: `_ensure_masters_for_shape` and `_bootstrap_masters`.
- Modify: `src/vsdxkit/pages.py`, `_ensure_page_master_rel`: drop the trailing `xml_to_file`.
- Test: `tests/test_visiofile_package_store.py` (extend)

- [ ] **Step 1: Write the failing tests:**

```python
from vsdxkit.package import XmlPart


def test_an_added_page_is_in_the_store_before_any_save(vsdx_copy):
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.add_page("Added")
        held = vis._package.part(vis._part_name(page.filename))
        assert isinstance(held, XmlPart) and held.tree is page.xml


def test_a_copied_page_brings_its_rels_part_into_the_store(vsdx_copy):
    with VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        source = next(p for p in vis.pages if p.rels_xml is not None)
        copy = vis.copy_page(source)
        assert copy.rels_xml_filename is not None
        held = vis._package.part(vis._part_name(copy.rels_xml_filename))
        assert isinstance(held, XmlPart) and held.tree is copy.rels_xml


def test_importing_a_master_keeps_masters_parts_as_the_stores_trees(vsdx_copy):
    """#366 and the eager-write removal: masters.xml(.rels) are trees in the store, not bytes."""
    with VisioFile(vsdx_copy("test3_house.vsdx")) as vis:
        page = vis.pages[0]
        page.connect_shapes(page.find_shape_by_id("1"), page.find_shape_by_id("5"))
        masters = vis._package.part("/visio/masters/masters.xml")
        rels = vis._package.part("/visio/masters/_rels/masters.xml.rels")
        assert isinstance(masters, XmlPart) and masters.tree.getroot() is vis.masters_xml
        assert isinstance(rels, XmlPart)


def test_bootstrapping_masters_writes_trees(vsdx_copy):
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        vis._bootstrap_masters()
        assert isinstance(vis._package.part("/visio/masters/masters.xml"), XmlPart)
        assert isinstance(vis._package.part("/visio/masters/_rels/masters.xml.rels"), XmlPart)
```

(`VisioFile.copy_page(page, *, index=PagePosition.AFTER, name=None) -> Page` is
the public copy API, and it passes `source_page` into `_create_page`.)

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement.**

`_create_page`: after building `new_page_xml`, call
`self._package.write_xml(self._part_name(new_page_path), new_page_xml)`
**before** `Page(...)`. For a copied page, set `new_page.rels_xml_filename`
first, then `new_page.rels_xml =
ET.ElementTree(copy.deepcopy(source_rels_root))`, whose setter writes it because
the page part is already present.

`masters.py`, `_ensure_masters_for_shape`:

```python
        master_rels_path = f"{self._masters_folder}/_rels/masters.xml.rels"
        rels_tree = self._read_part_xml(master_rels_path)
        if rels_tree is None:
            rels_tree = ET.ElementTree(
                ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
            )
            self._package.write_xml(self._part_name(master_rels_path), rels_tree)
        rels_root = rels_tree.getroot()
        ...
        self._package.write_bytes(
            self._part_name(part_path), src_vis._package.read_bytes(src_vis._part_name(source_master_page.filename)) or b""
        )
        ...
        self.masters_xml.append(new_master_element)
        # (both xml_to_file calls deleted: the trees are the store's)
        ...
        master_page_xml = self._require_part_xml(part_path, "imported master part")
```

The `or b""` is only there to satisfy the type. The earlier
`source_master_page.filename not in src_vis.zip_file_contents` check guarantees
presence, so switch that check to
`src_vis._package.part(src_vis._part_name(...)) is None` as well.

`_bootstrap_masters`:

```python
        self._package.write_xml(self._part_name(f"{self._masters_folder}/masters.xml"), ET.ElementTree(masters_root))
        self._package.write_xml(
            self._part_name(f"{self._masters_folder}/_rels/masters.xml.rels"),
            ET.ElementTree(
                ET.fromstring('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>')
            ),
        )
```

(Remove `self.masters_xml = masters_root`: the property reads it back. Remove
the `io` import if it's unused.)

`pages.py`, `_ensure_page_master_rel`: delete the final `if
self.rels_xml_filename: xml_to_file(...)` block and its comment. Creating the
rels part goes through the `rels_xml` setter, since `rels_xml_filename` is
assigned on the line before, which writes it into the store. Update the
docstring: "the filename is registered so save_vsdx persists it" becomes
"assigning it writes it into the package".

- [ ] **Step 4: Run to verify pass**, then the full gate.
- [ ] **Step 5: Commit**: `fix: keep masters.xml and its rels as trees in the
      package store` (the body says it closes #366).

---

### Task 7: `save_vsdx` stops re-serialising and delegates to the store

**Files:**

- Modify: `src/vsdxkit/vsdxfile.py`, `save_vsdx`: delete every `xml_to_file` rewrite.
- Modify: `tests/test_namespaces.py`: update docstrings that describe save
  "re-serialising every page". The assertions stay.
- Test: `tests/test_byte_preserving_save.py` (new)

- [ ] **Step 1: Write the failing tests** in `tests/test_byte_preserving_save.py`:

```python
"""#89's acceptance: a save changes exactly the members that changed.

Expected sides are read with `zipfile` from the fixture, never through vsdxkit.
"""

from __future__ import annotations

import glob
import os
import zipfile
from datetime import datetime

import pytest

import vsdxkit

BASEDIR = os.path.dirname(os.path.realpath(__file__))
FIXTURES = sorted(os.path.basename(p) for p in glob.glob(os.path.join(BASEDIR, "*.vsd[xm]")))


def _members(path) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(path) as archive:
        return [(i.filename, archive.read(i)) for i in archive.infolist() if not i.is_dir()]


@pytest.mark.parametrize("fixture", FIXTURES)
def test_open_and_save_is_byte_identical(fixture, vsdx_copy, tmp_path):
    source = vsdx_copy(fixture)
    target = tmp_path / f"out{os.path.splitext(fixture)[1]}"
    with vsdxkit.VisioFile(source) as vis:
        for page in vis.pages:  # read every shape, promoting nothing new but walking the trees
            _ = [shape.text for shape in page.all_shapes]
        vis.save_vsdx(str(target))
    assert _members(target) == _members(source)


def test_one_edit_changes_one_member(vsdx_copy, tmp_path):
    source = vsdx_copy("test8_simple_connector.vsdx")
    target = tmp_path / "out.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        shape = vis.pages[0].find_shape_by_text("Shape A")
        assert shape is not None
        shape.text = "Renamed A"
        page_member = vis._part_name(vis.pages[0].filename)[1:]
        vis.save_vsdx(str(target))
    before, after = dict(_members(source)), dict(_members(target))
    assert list(after) == list(before)
    assert [name for name in before if before[name] != after[name]] == [page_member]


def test_a_second_save_carries_a_second_edit(vsdx_copy, tmp_path):
    """Review Focus 3: comparing against the baseline must not use the change up."""
    source = vsdx_copy("test8_simple_connector.vsdx")
    first, second = tmp_path / "first.vsdx", tmp_path / "second.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        shape = vis.pages[0].find_shape_by_text("Shape A")
        assert shape is not None
        shape.text = "Once"
        vis.save_vsdx(str(first))
        shape.text = "Twice"
        vis.save_vsdx(str(second))
    with vsdxkit.VisioFile(str(second)) as vis:
        assert vis.pages[0].find_shape_by_text("Twice") is not None


def test_save_as_then_save_writes_the_original(vsdx_copy, tmp_path):
    """Review Focus 4, through VisioFile."""
    source = vsdx_copy("test8_simple_connector.vsdx")
    elsewhere = tmp_path / "elsewhere.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        vis.save_vsdx(str(elsewhere))
        shape = vis.pages[0].find_shape_by_text("Shape A")
        assert shape is not None
        shape.text = "In place"
        vis.save_vsdx()
    with vsdxkit.VisioFile(source) as vis:
        assert vis.pages[0].find_shape_by_text("In place") is not None
    with vsdxkit.VisioFile(str(elsewhere)) as vis:
        assert vis.pages[0].find_shape_by_text("In place") is None


def test_a_rendered_template_reaches_disk(vsdx_copy, tmp_path):
    """Jinja replaces each page's tree wholesale; nothing rewrites it at save any more."""
    source = vsdx_copy("test_jinja.vsdx")
    target = tmp_path / "rendered.vsdx"
    with vsdxkit.VisioFile(source) as vis:
        vis.jinja_render_vsdx(context={"date": datetime(2026, 9, 23), "scenario": "VsdxkitRendered", "x": 2, "y": 2})
        vis.save_vsdx(str(target))
    with zipfile.ZipFile(target) as archive:
        pages = b"".join(archive.read(n) for n in archive.namelist() if n.startswith("visio/pages/page"))
    assert b"VsdxkitRendered" in pages
```

(`Page.all_shapes` is a property. `test_jinja.vsdx` expects the context keys
`date`, `scenario`, `x`, `y`; see `tests/test_jinja.py:15`.)

- [ ] **Step 2: Run to verify failure.** `test_open_and_save_is_byte_identical`
      should fail for most fixtures, because the rewrites re-serialise pages,
      content types and so on. `test_one_edit_changes_one_member` fails for the
      same reason.

- [ ] **Step 3: Implement.** `save_vsdx` becomes:

```python
        self._require_open("VisioFile.save_vsdx()")
        if not self._package.names():
            raise ValueError("cannot save an empty package")

        # resolve the destination first, so a refused extension writes nothing
        target = self._in_place_filename() if new_filename is None else self._destination_filename(new_filename)

        # every change is already in the store -- the trees this document edits
        # are the store's own -- so saving is writing it, once, member by member
        self._package.save(target)
```

Then remove any now-unused imports (`xml_to_file`, `require_tree`) that ruff reports.

- [ ] **Step 4: Run the new tests, then the full gate.** Treat any existing-test
      failure as a mutation site Task 6 missed. The symptom is a change that no
      longer reaches disk. Find the site with `grep -rn "ET.ElementTree(\|=
      ET.ElementTree\|xml_to_file\|zip_file_contents\[" src/vsdxkit` and route
      it through the store; don't weaken the test.
      `tests/test_interop_libreoffice.py` is skipped without LibreOffice; CI
      runs it.
- [ ] **Step 5: Mutation check.** Temporarily make `XmlPart.current_bytes`
      always return `serialise_part(self.tree)`, and confirm
      `test_open_and_save_is_byte_identical` fails. Then temporarily delete the
      `Page.xml` setter's write-through, and confirm
      `test_a_rendered_template_reaches_disk` fails. Revert both.
- [ ] **Step 6: Commit** — `feat!: save only what changed, byte for byte` if any
      public behaviour a caller could see changes (unchanged members keep their
      original spelling, and the container is deflated); otherwise `feat:`. The
      body says it closes #89.
- [ ] **Step 7: Open PR 3.** In the body, give the before/after for `test1.vsdx`
      (size, and the members that changed on a no-op save). Link #91 as now
      unblocked, and #367 as untouched.
