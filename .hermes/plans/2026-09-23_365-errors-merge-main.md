# Finish #365: error hierarchy on top of the #89 package stack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PR #365 (issue #96, the `VsdxError` hierarchy) mergeable on top of today's `main`, which now holds the #89 package stack (#370, #371 and #373). Bring the stack's new raise sites into the hierarchy, and fix #365's two open Codex findings.

**Architecture:**
- `main` is merged into `feat/errors-module` once, as a merge commit. The PR is squash-merged at the end, so its history does not matter, and a merge avoids force-pushing over the PR branch.
- The one real design collision is the error for malformed XML:
  - `main` has `PartParseError(ET.ParseError, ValueError)` in `package.py`, raised by `_promoted`. It keeps `except ET.ParseError` working and carries `position`/`code`.
  - #365 has `parse_part` raise `MalformedPackageError`, which deliberately does *not* inherit `ET.ParseError`, because it would not carry `position`.
  - They unify as `PartParseError(MalformedPackageError, ET.ParseError)` in `errors.py`, raised by `parse_part` itself. It carries `position` and `code`, so #365's objection no longer applies. Both old contracts hold: `except ET.ParseError` and `except VsdxError`/`MalformedPackageError`/`ValueError`.

**Tech Stack:** Python 3.10–3.14, `xml.etree.ElementTree`, `zipfile`, pytest, ruff, pyrefly.

**Spec:**
- Issue #96 (10A-D1).
- PR #365's body, which states the hierarchy, the compatibility rule and the remaining-`ValueError` rule.
- #371/#373's `PartParseError` contract.
- Codex comments 4001449826 and 4001449830 on #365.

## Global Constraints

- **Hierarchy (unchanged):** `VsdxError` ⊃ `InvalidOperationError(ValueError)` ⊃ `VisioFileNotOpen`; `NotFoundError(ValueError)` ⊃ `MissingPartError`; `PackageError` ⊃ `MalformedPackageError(ValueError)`, `PackageLimitError(OSError)`. The one addition is `PartParseError(MalformedPackageError, ET.ParseError)`.
- **Compatibility rule (from #365):** a class raised at a site that previously raised a builtin keeps that builtin as a base. Remaining plain `ValueError`s are argument checks only.
- **Import paths:** `vsdxkit.package.PartParseError`, `vsdxkit.package.PackageLimitError`, `vsdxkit.vsdxfile.PackageLimitError` and `vsdxkit.vsdxfile.VisioFileNotOpen` must keep resolving to the same class objects as `vsdxkit.errors.*` and `vsdxkit.*`.
- **Gate before every commit:** `uv run --no-sync python -m pytest tests -q`, `uv run --no-sync ruff check src tests tools`, `uv run --no-sync ruff format --check src tests tools`, `uv run --no-sync pyrefly check src/vsdxkit --min-severity warn --output-format min-text`. Before pushing, also run `uv run --no-sync python tools/check_public_annotations.py` and `uv run --no-sync sphinx-build -W --keep-going -b html docs /tmp/claude-1000/-home-shaunes-dev-firmfooting-vsdxkit/2d63fae9-cc29-434a-b868-44ee3b5c8f66/scratchpad/docs-out`.
- **House style:** docstrings say *why*, in full sentences. Every test has a docstring naming the production change that would make it fail. Conventional-commit subjects.
- **No force-push to `feat/errors-module`:** integrate `main` by merge.
- **Out of scope:**
  - #362's deprecation shim: the re-exports stay as plain aliases.
  - Hardening every `attrib[...]` read.
  - Dropping `OSError` from `PackageLimitError`.

## Review Focus

1. **`except ET.ParseError`:** code written against 0.8/#371 opens a malformed page. It must still catch the error, and still read `.position`. This is pinned in Task 1.
2. **Undecodable encoding through `zip_file_contents`:** bytes declaring an encoding nothing can decode, written through `zip_file_contents` into a parsed part mid-edit, must be held back like any unparseable write, not escape `buf.write()` as a raw `LookupError`. On `main` today, `write_bytes_keeping_tree` catches only `ET.ParseError`. This is pinned in Task 1.
3. **`MemoryError` while reading a member:** it must propagate as `MemoryError`, not become `MalformedPackageError`. This is pinned in Task 3.
4. **Multi-byte encodings:** a part declaring an encoding expat rejects as multi-byte must open as `MalformedPackageError`, not a bare `ValueError`. This is pinned in Task 3.
5. **Refused `None` assignment:** `VisioFile.app_xml = None` / `Page.xml = None` must be an `InvalidOperationError` that is still a `ValueError`, so `except ValueError` code from #373 keeps working. This is pinned in Task 2.

---

### Task 1: Merge `main`, and unify the malformed-XML error

**Files:**
- Modify: `src/vsdxkit/errors.py` (add `PartParseError`, add it to `__all__`)
- Modify: `src/vsdxkit/xmlio.py` (`parse_part` raises `PartParseError` for `ET.ParseError`)
- Modify: `src/vsdxkit/package.py` (drop main's local `PartParseError` class and `_promoted`'s try/except; re-export `PartParseError` from `.errors`; `write_bytes_keeping_tree` catches `MalformedPackageError`)
- Modify: `src/vsdxkit/__init__.py` (export `PartParseError`)
- Modify: `docs/classes.rst` (add `PartParseError` to the Errors section)
- Conflicts expected in `src/vsdxkit/package.py`, `src/vsdxkit/pages.py` and `src/vsdxkit/vsdxfile.py`
- Test: `tests/test_errors.py`, `tests/test_visiofile_package_store.py`, `tests/test_zip_contents_view.py`

**Interfaces:**
- Produces: `vsdxkit.errors.PartParseError(MalformedPackageError, ET.ParseError)`. Instances carry `position: tuple[int, int]` and `code: int` copied from the parser's error, and a message naming the part: `"package part {name} is not well-formed XML: {error}"`.
- Produces: `xmlio.parse_part(data: bytes, name: str = "") -> ET.ElementTree[ET.Element]` (#365's signature). It raises `PartParseError` for well-formedness, and `MalformedPackageError` for an undecodable encoding or a missing root.

- [ ] **Step 1: Merge**

```bash
git fetch origin main
git merge origin/main
```

Resolve the conflicts. The rules:
- Keep every behaviour from `main`: store-backed properties, write-through, `_attached` identity, generation-bound buffers, the `set_name` delegation, `None` refusals.
- Keep every raise-site type from #365.
- Where #365 routed a required-attribute read through `xmlio.require_attribute`, keep that routing on main's code.
- `_promoted` becomes:

```python
def _promoted(name: str, part: BytesPart) -> XmlPart:
    tree = parse_part(part.data, name)
    return XmlPart(tree=tree, original_bytes=part.data, original_canonical_hash=canonical_hash(tree), promoted_from=part)
```

- [ ] **Step 2: Add `PartParseError` to `errors.py`, after `MalformedPackageError`**

```python
class PartParseError(MalformedPackageError, ET.ParseError):
    """A part that is not well-formed XML, named, and catchable as every error it has been.

    Before the package store a malformed part reached the caller as the bare
    `ET.ParseError` the parser raised; 0.9 callers catch it as `ValueError`,
    and the hierarchy's callers as `MalformedPackageError` or `VsdxError`.
    A caller should not have to know which release it runs against to catch a
    broken package, so this is all of them. It carries the parser's
    `position` and `code`, which say where in the part it broke.
    """
```

Add `import xml.etree.ElementTree as ET` to `errors.py` and `"PartParseError"` to `__all__`. In `package.py`, delete main's local `PartParseError` class and import it instead: `from .errors import MalformedPackageError, MissingPartError, PackageLimitError, PartParseError`. Keep `"PartParseError"` in `package.__all__`. Add `PartParseError` to `vsdxkit/__init__.py` imports and `__all__`, next to `MalformedPackageError`.

- [ ] **Step 3: `parse_part` raises it**

In `xmlio.parse_part`, replace the `except ET.ParseError` handler:

```python
    except ET.ParseError as error:
        raised = PartParseError(f"{subject} is not well-formed XML: {error}")
        # ParseError sets these on the instance rather than taking them in its
        # constructor, so they are copied the same way
        raised.position = error.position
        raised.code = error.code
        raise raised from error
```

- [ ] **Step 4: Widen the catch in `write_bytes_keeping_tree`**

In `PackageStore.write_bytes_keeping_tree` (main's `package.py`, around line 579), change `except ET.ParseError:` to `except MalformedPackageError:`. Then an undecodable encoding is treated like any other unparseable write: held back, or stored as a `BytesPart`. Check every other `except ET.ParseError` in `src/` and change it the same way: `git grep -n "except ET.ParseError" src`.

- [ ] **Step 5: Tests (write them before Steps 2–4 if the merge leaves the old behaviour in place)**

Add to `tests/test_errors.py`:

```python
def test_part_parse_error_is_every_error_a_malformed_part_has_been():
    """Fails if PartParseError drops any base a caller may already catch a malformed part by."""
    import xml.etree.ElementTree as ET

    from vsdxkit import errors

    for base in (errors.MalformedPackageError, errors.PackageError, errors.VsdxError, ET.ParseError, ValueError):
        assert issubclass(errors.PartParseError, base)


def test_part_parse_error_is_the_same_class_on_every_import_path():
    """Fails if package.py keeps its own PartParseError instead of re-exporting the errors module's."""
    import vsdxkit
    from vsdxkit import errors, package

    assert package.PartParseError is errors.PartParseError is vsdxkit.PartParseError
```

The existing `test_visiofile_package_store.py::test_a_malformed_part_is_both_a_parse_error_and_a_value_error`, or whatever main named it, must pass unmodified. Extend it, or add a sibling that opens the same malformed package and asserts it is caught by `except vsdxkit.VsdxError`, with `position` set.

Add to `tests/test_zip_contents_view.py`:

```python
def test_bytes_declaring_an_undecodable_encoding_are_held_back_like_unparseable_bytes(view, store):
    """Fails if write_bytes_keeping_tree catches only ET.ParseError, so a LookupError-shaped failure escapes buf.write()."""
    tree = store.require_xml(PAGE1)
    buf = view[f"{DIRECTORY}{PAGE1}"]
    buf.seek(0)
    buf.write(b'<?xml version="1.0" encoding="x-no-such-codec"?><a/>')
    held = store.part(PAGE1)
    assert isinstance(held, XmlPart) and held.tree is tree
```

Use the module's existing fixtures and constants (`view`, `store`, `PAGE1`, `DIRECTORY`, `XmlPart`). Read the file's head for the exact names.

- [ ] **Step 6: Docs.** In `docs/classes.rst`, add `.. autoclass:: vsdxkit.errors.PartParseError` to the Errors section, with one sentence: it is also an `xml.etree.ElementTree.ParseError`.

- [ ] **Step 7: Gate, then commit the merge.** Use `git commit` with the merge message `Merge main (the #89 package stack) into feat/errors-module`. Put the unification and the tests in a follow-up commit with the subject `fix: raise one PartParseError for a malformed part, in the hierarchy and still a ParseError`, if they are not part of the conflict resolution itself.

### Task 2: Bring the stack's new raise sites into the hierarchy

**Files:**
- Modify: `src/vsdxkit/vsdxfile.py` (`_require_part_xml`, `_set_document_part_xml`)
- Modify: `src/vsdxkit/pages.py` (`Page.xml` setter's `None` refusal)
- Modify: `src/vsdxkit/masters.py` ("source master part … could not be read")
- Modify: `src/vsdxkit/package.py` (`PackageStore.require_xml`, if the merge left it raising `ValueError`)
- Test: `tests/test_errors.py`

**Interfaces:**
- Consumes: `vsdxkit.errors.MissingPartError`, `InvalidOperationError` (both are `ValueError`s).

The mapping (a ruling; every one of these previously raised `ValueError`, so the new class keeps `ValueError` as a base):

| Site | New type | Why |
|---|---|---|
| `VisioFile._require_part_xml` "expected XML part not found" | `MissingPartError` | a part the document must contain is absent |
| `PackageStore.require_xml` "expected XML part not found" | `MissingPartError` | same |
| `masters.py` "source master part … could not be read, though the package lists it" | `MissingPartError` | the donor lists a part it does not hold |
| `VisioFile._set_document_part_xml` refusing `None` | `InvalidOperationError` | the document cannot do the removal asked of it in a consistent state |
| `Page.xml` setter refusing `None` | `InvalidOperationError` | same |

Left as `ValueError`, because they are argument checks:
- `VisioFile._part_name` ("… is not a part of this document")
- `ZipFileContentsView`'s "not under the package directory"
- `_checked`'s OPC name syntax
- `PackageStore.save`'s "zipfile would transform member name"

Left as builtins by design:
- `KeyError` from `PackageStore.remove` and from the `MutableMapping` view, which is the mapping protocol.
- `OSError` for a temp file replaced during save, which is an operating-system condition.

- [ ] **Step 1: Failing tests** in `tests/test_errors.py`, one per row:

```python
def test_refusing_none_for_a_document_part_is_an_invalid_operation(vsdx_copy):
    """Fails if VisioFile's document-part setters refuse None with a plain ValueError."""
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        with pytest.raises(vsdxkit.InvalidOperationError):
            vis.app_xml = None


def test_refusing_none_for_a_page_part_is_an_invalid_operation(vsdx_copy):
    """Fails if Page.xml refuses None with a plain ValueError."""
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        with pytest.raises(vsdxkit.InvalidOperationError):
            vis.pages[0].xml = None


def test_a_required_part_the_store_lacks_is_a_missing_part():
    """Fails if PackageStore.require_xml reports an absent part with a plain ValueError."""
    from vsdxkit.package import PackageStore

    store = PackageStore.open(os.path.join(BASEDIR, "test1.vsdx"))
    with pytest.raises(vsdxkit.MissingPartError):
        store.require_xml("/visio/no-such-part.xml")


def test_a_source_master_listed_but_unreadable_is_a_missing_part(vsdx_copy, monkeypatch):
    """Fails if master import reports a listed-but-unreadable donor part with a plain ValueError."""
    with vsdxkit.VisioFile(vsdx_copy("test4_connectors.vsdx")) as source, vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as target:
        shape = next(shape for shape in source.pages[0].all_shapes if shape.xml.attrib.get("Master"))
        monkeypatch.setattr(source._package, "read_bytes", lambda name: None)
        with pytest.raises(vsdxkit.MissingPartError, match="could not be read"):
            target._ensure_masters_for_shape(shape)
```

If `tests/test_errors.py` has no `BASEDIR`, define it the way `tests/test_package_store.py` does: `BASEDIR = os.path.dirname(os.path.realpath(__file__))`. The existing `pytest.raises(ValueError, match="could not be read")` in `tests/test_master_import_opc.py` stays unmodified; it is the compatibility evidence.

- [ ] **Step 2: Run them.** Expect FAIL: a plain `ValueError` is raised.
- [ ] **Step 3: Change the five raise sites** and import from `.errors`. Update each `:raises:` docstring line that names `ValueError` for these sites.
- [ ] **Step 4: Gate.** `test_errors.py`'s test asserting that argument checks stay plain builtins must still pass.
- [ ] **Step 5: Commit** `fix!: raise the hierarchy's errors from the package stack's new refusals`, with a `BREAKING CHANGE:` footer. There is none for callers: every new type is still a `ValueError`. The footer is there to record that the types changed.

### Task 3: #365's two open Codex findings

**Files:**
- Modify: `src/vsdxkit/package.py` (`_member_bytes`)
- Modify: `src/vsdxkit/xmlio.py` (`parse_part`)
- Test: `tests/test_errors.py`

- [ ] **Step 1: Failing test: `MemoryError` escapes the member decoder** (Codex 4001449826)

```python
def test_memory_exhausted_while_reading_a_member_is_not_blamed_on_the_package(monkeypatch, tmp_path):
    """Fails if _member_bytes' broad handler turns MemoryError into MalformedPackageError."""
    from vsdxkit import package

    def exhausted(*args, **kwargs):
        raise MemoryError

    monkeypatch.setattr(package, "_read_bounded", exhausted)
    with pytest.raises(MemoryError):
        package.PackageStore.open(os.path.join(BASEDIR, "test1.vsdx"))
```

- [ ] **Step 2: Failing test: a multi-byte encoding the parser refuses** (Codex 4001449830)
  - First reproduce what `ET.iterparse` raises for a part whose declaration names a codec expat treats as multi-byte and refuses. Try `encoding="UTF-7"`, `"UTF-32"` and `"UTF-16"` with matching and with plain-ASCII bodies. Record the exact `ValueError` message in the test docstring.
  - Then write the test with the reproduced bytes as a module constant. For example, if UTF-32 reproduces it:

```python
REFUSED_MULTIBYTE_PART = '<?xml version="1.0" encoding="UTF-32"?><a/>'.encode("utf-32")


def test_a_part_in_a_multibyte_encoding_the_parser_refuses_is_malformed():
    """Fails if parse_part lets expat's "multi-byte encodings are not supported" ValueError escape untranslated."""
    from vsdxkit import xmlio

    with pytest.raises(vsdxkit.MalformedPackageError, match="encoding"):
        xmlio.parse_part(REFUSED_MULTIBYTE_PART, "/visio/pages/page1.xml")
```

  - Also assert that `VisioFile(...)` on a copy of `test1.vsdx`, with `visio/pages/page1.xml` replaced by those bytes, raises `MalformedPackageError`. Rewrite the archive the way the existing malformed-XML test in `tests/test_errors.py` does. Find it with `git grep -n "is not well-formed" tests/test_errors.py`, and reuse its helper.

- [ ] **Step 3: Run both.** Expect FAIL (`MalformedPackageError` raised; bare `ValueError` escapes).

- [ ] **Step 4: Implement**

In `_member_bytes`, before `except Exception`:

```python
    except MemoryError:
        # the process ran out, not the package: blaming the archive would let an
        # `except VsdxError` caller carry on under memory pressure
        raise
```

In `parse_part`, after the `LookupError` handler:

```python
    except ValueError as error:
        # expat refuses some encodings it recognises -- multi-byte ones it cannot
        # stream -- with a ValueError rather than LookupError. Nothing in the loop
        # body raises ValueError, so this catches the parser and only the parser.
        raise MalformedPackageError(f"{subject} declares an encoding the parser does not support: {error}") from error
```

`PartParseError` and `MalformedPackageError` are `ValueError` subclasses, but they are raised *outside* the `try`, so this handler cannot swallow them. Keep them outside.

- [ ] **Step 5: Gate. Commit** `fix: let MemoryError escape, and report a refused multi-byte encoding as MalformedPackageError`.

### Task 4 (controller): PR hygiene

- Update #365's body:
  - The hierarchy gains `PartParseError`.
  - Delete the `ET.ParseError` breaking footer line for well-formedness; that break no longer happens.
  - Record the migrated stack sites and the new counts from `git grep -c "raise ValueError" src`.
  - Update the gate numbers.
- Push. Reply to Codex 4001449826 and 4001449830. Watch CI and Codex.
