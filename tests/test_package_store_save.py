"""What `PackageStore.save` promises: one writer, every member once, atomically.

The expected side of each comparison is read with `zipfile` straight from the
fixture, never through the store (see test_package_store.py's docstring).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from vsdxkit.package import PackageLimitError, PackageLimits, PackageStore

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
    """Fails if changed parts are not re-serialised or unchanged parts are modified."""
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
    """Fails if the default `save()` does not write back over the original source."""
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


@pytest.mark.allow_invalid_package
def test_a_removed_part_is_not_written(source, tmp_path):
    """Fails if a removed part is still written to the archive."""
    store = PackageStore.open(source)
    store.remove(PAGE_PART)
    target = tmp_path / "out.vsdx"
    store.save(target)
    assert PAGE_PART[1:] not in dict(_members(target))


def test_save_creates_missing_parent_directories(source, tmp_path):
    """Fails if parent directories are not created before saving."""
    target = tmp_path / "a" / "b" / "out.vsdx"
    PackageStore.open(source).save(target)
    assert target.exists()


def test_a_failed_write_leaves_the_target_and_no_temporary_file(source, monkeypatch):
    """Fails if temporary files are not cleaned up when a write fails."""
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
    """Fails if file mode is not preserved from the source."""
    source.chmod(0o640)
    target = tmp_path / "out.vsdx"
    PackageStore.open(source).save(target)
    assert target.stat().st_mode & 0o777 == 0o640


def test_save_uses_absolute_source_path_to_avoid_cwd_changes(source, tmp_path, monkeypatch):
    """Fails if save() computes source path at save time instead of open time.

    A caller who opens with a relative path and then changes working directory
    should still save back to the original location, not somewhere else.
    """
    monkeypatch.chdir(tmp_path)
    # Open with a relative path
    store = PackageStore.open("source.vsdx")
    # Create a subdirectory and change into it
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    monkeypatch.chdir(subdir)
    # Add a new part
    store.write_xml("/visio/extra.xml", ET.ElementTree(ET.Element("Extra")))
    # Save with no target should write to the original location
    store.save()
    # Assert the original source was updated
    assert "visio/extra.xml" in dict(_members(tmp_path / "source.vsdx"))
    # Assert no source.vsdx was created in the subdirectory
    assert not (subdir / "source.vsdx").exists()


@pytest.mark.allow_invalid_package
def test_members_exceeding_compression_ratio_are_stored_uncompressed(source, tmp_path):
    """Fails if members exceeding the compression ratio limit are not stored uncompressed.

    Forcing ZIP_DEFLATED on all members can produce members whose compression
    ratio exceeds the limit, causing the package to be rejected when reopened.
    """
    # Build a package with a highly compressible member that would exceed the ratio if deflated
    store = PackageStore.open(source)
    # Create a member that is highly compressible but would have a bad ratio if deflated
    big_xml = b"<Big>" + b"<a/>" * 150_000 + b"</Big>"
    store.write_bytes("/visio/big.xml", big_xml)
    target = tmp_path / "out.vsdx"
    store.save(target)
    # Assert that the new package can be opened with default limits
    reopened = PackageStore.open(target)
    assert reopened is not None
    # Assert that visio/big.xml is stored uncompressed (because it's highly compressible)
    with zipfile.ZipFile(target) as archive:
        big_info = next((info for info in archive.infolist() if info.filename == "visio/big.xml"), None)
        assert big_info is not None
        assert big_info.compress_type == zipfile.ZIP_STORED
        # Assert all other members are deflated
        for info in archive.infolist():
            if info.filename != "visio/big.xml" and not info.is_dir():
                assert info.compress_type == zipfile.ZIP_DEFLATED


@pytest.mark.skipif(os.name == "nt", reason="symlink-based test is not meaningful on Windows")
def test_save_detects_symlink_race_on_temp_file(source, tmp_path, monkeypatch):
    """Fails if save() does not detect a symlink being swapped in on the temp file.

    Closing the mkstemp descriptor and reopening the path allows a race where
    someone with directory write access can swap in a symlink. The fix is to
    write through the descriptor and check that the path still points to the
    file we wrote.
    """
    import vsdxkit.package as package_module

    original_mkstemp = tempfile.mkstemp
    victim_file = tmp_path / "victim"
    victim_file.write_bytes(b"original victim content")

    def mkstemp_with_symlink_race(*args, **kwargs):
        fd, path = original_mkstemp(*args, **kwargs)
        # Unlink the temp file and replace it with a symlink to the victim
        os.unlink(path)
        os.symlink(victim_file, path)
        return fd, path

    monkeypatch.setattr(package_module, "tempfile", type("Module", (), {"mkstemp": staticmethod(mkstemp_with_symlink_race)})())

    store = PackageStore.open(source)
    store.write_xml("/visio/extra.xml", ET.ElementTree(ET.Element("Extra")))
    target = tmp_path / "out.vsdx"

    # save() should detect the race and raise OSError
    with pytest.raises(OSError, match="was replaced while the package was being written"):
        store.save(target)

    # Victim should still have original content
    assert victim_file.read_bytes() == b"original victim content"
    # Target should not exist (because save failed before replace)
    assert not target.exists()


def test_save_rejects_package_exceeding_member_count_limit(source, tmp_path):
    """Fails if save() allows packages to exceed the member count limit.

    A caller can add parts after opening, and save() should reject the package
    if it would exceed the limits the store was opened with.
    """
    store = PackageStore.open(source)
    current_count = len(store.names())
    # Open with a limit that allows the current package but not one more part
    store_limited = PackageStore.open(source, limits=PackageLimits(max_members=current_count))
    # Add a part to exceed the limit
    store_limited.write_xml("/visio/extra.xml", ET.ElementTree(ET.Element("Extra")))
    target = tmp_path / "out.vsdx"
    # save() should reject this and raise PackageLimitError
    with pytest.raises(PackageLimitError) as exc_info:
        store_limited.save(target)
    assert exc_info.value.reason == "member_count"
    # The wording mirrors read_archive_members; fails if save() words the same limit differently.
    assert f"package has {current_count + 1} entries (including directories)" in str(exc_info.value)
    # Target should not have been created
    assert not target.exists()


def test_save_rejects_package_exceeding_member_size_limit(source, tmp_path):
    """Fails if save() allows packages to exceed the member size limit.

    A caller can grow a part after opening, and save() should reject the
    package if any member exceeds the limits the store was opened with.
    """
    store = PackageStore.open(source)
    # Find the maximum size of any existing part
    max_existing = max(len(store.read_bytes(name)) for name in store.names())
    # Open with a limit that allows the current package
    member_limit = max_existing + 1000
    store_limited = PackageStore.open(source, limits=PackageLimits(max_member_size=member_limit))
    # Write a part that exceeds this limit
    store_limited.write_bytes("/visio/big.xml", b"x" * (member_limit + 1))
    target = tmp_path / "out.vsdx"
    # save() should reject this and raise PackageLimitError
    with pytest.raises(PackageLimitError) as exc_info:
        store_limited.save(target)
    assert exc_info.value.reason == "member_size"
    # The wording mirrors read_archive_members; fails if save() words the same limit differently.
    assert f"package member 'visio/big.xml' declares {member_limit + 1} bytes" in str(exc_info.value)
    # Target should not have been created
    assert not target.exists()


def test_save_rejects_package_exceeding_total_size_limit(source, tmp_path):
    """Fails if save() allows packages to exceed the total uncompressed size limit.

    A caller can add large parts after opening, and save() should reject the
    package if the total uncompressed size exceeds the limits the store was opened with.
    """
    store = PackageStore.open(source)
    total = sum(len(store.read_bytes(name)) for name in store.names())
    # Open with a small limit that only allows the current package
    small_limit = total + 1
    store_limited = PackageStore.open(source, limits=PackageLimits(max_total_uncompressed=small_limit))
    # Add a part that makes the total exceed the limit
    store_limited.write_bytes("/visio/extra.xml", b"x" * 1000)
    target = tmp_path / "out.vsdx"
    # save() should reject this and raise PackageLimitError
    with pytest.raises(PackageLimitError) as exc_info:
        store_limited.save(target)
    assert exc_info.value.reason == "total_size"
    # Target should not have been created
    assert not target.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not meaningful on Windows")
def test_save_mode_uses_fchmod_when_available(source, tmp_path, monkeypatch):
    """Fails if mode copying is not done via fchmod on platforms that support it.

    When the descriptor is still open, mode changes via fchmod are atomic with
    respect to the file. Using the path-based copymode after closing exposes a
    race where a symlink can be swapped in and get the file's permissions.
    """
    if not hasattr(os, "fchmod"):
        pytest.skip("This platform does not have os.fchmod")

    # Track whether copymode was called on the path (it shouldn't be if fchmod exists)
    copymode_called = []
    original_copymode = shutil.copymode

    def copymode_wrapper(*args, **kwargs):
        copymode_called.append(args)
        return original_copymode(*args, **kwargs)

    monkeypatch.setattr(shutil, "copymode", copymode_wrapper)

    source.chmod(0o640)
    store = PackageStore.open(source)
    store.write_xml("/visio/extra.xml", ET.ElementTree(ET.Element("Extra")))
    target = tmp_path / "out.vsdx"
    store.save(target)

    # On platforms with fchmod, copymode should not have been called
    assert len(copymode_called) == 0, f"copymode was called {len(copymode_called)} times when fchmod is available"
    # The mode should still have been preserved
    assert target.stat().st_mode & 0o777 == 0o640


def test_save_rejects_nul_in_part_name(source):
    """Fails if save() allows NUL characters in part names at write time.

    NUL characters are rejected at _checked time, which is when any part name
    is validated. This test verifies the rejection happens when writing bytes
    (not just when writing XML).
    """
    store = PackageStore.open(source)
    # Attempt to write a part with NUL in the name
    with pytest.raises(ValueError, match="cannot contain"):
        store.write_bytes("/visio/bad\x00.xml", b"data")


def test_save_closes_the_temporary_file_before_renaming_it(source, tmp_path, monkeypatch):
    """Fails if `os.replace` runs while the writer still holds the temporary file open.

    Windows will not rename a file that has an open handle (`mkstemp` does not
    grant delete sharing), so a rename inside the `with os.fdopen(...)` block
    fails every save there. Linux does not care, so the test cannot wait for
    the rename to fail: it records every file object `os.fdopen` hands the
    writer and, at the moment `os.replace` is called on the temporary file,
    asserts each one is closed. Where `/proc/self/fd` exists it also checks
    that no descriptor in the process still points at the temporary file,
    which catches a writer that stops going through `os.fdopen`.
    """
    opened = []
    original_fdopen = os.fdopen
    original_replace = os.replace
    checked = []

    def recording_fdopen(*args, **kwargs):
        handle = original_fdopen(*args, **kwargs)
        opened.append(handle)
        return handle

    def checking_replace(src, dst, *args, **kwargs):
        if os.path.basename(os.fspath(src)).startswith(".out.vsdx."):
            assert opened, "the writer did not open the temporary file through os.fdopen"
            assert all(handle.closed for handle in opened), "os.replace ran with the temporary file still open"
            if os.path.isdir("/proc/self/fd"):
                temporary = os.path.realpath(src)
                for entry in os.listdir("/proc/self/fd"):
                    with contextlib.suppress(OSError):
                        assert os.readlink(f"/proc/self/fd/{entry}") != temporary, "a descriptor still holds the file"
            checked.append(src)
        return original_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "fdopen", recording_fdopen)
    monkeypatch.setattr(os, "replace", checking_replace)
    target = tmp_path / "out.vsdx"
    PackageStore.open(source).save(target)
    assert checked, "save() never renamed its temporary file"
    assert _members(target) == _members(source)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not meaningful on Windows")
def test_a_new_target_takes_the_source_mode_without_fchmod(source, tmp_path, monkeypatch):
    """Fails if the no-`fchmod` path reads the mode after the rename, or skips applying it.

    Windows before Python 3.13 has no `os.fchmod`, so the mode goes on by path.
    If the mode source is chosen after `os.replace`, the destination always
    exists by then and the new file's own `mkstemp` mode (0o600) is copied
    onto itself, so a new target loses the source's 0o640.
    """
    monkeypatch.delattr(os, "fchmod", raising=False)
    source.chmod(0o640)
    target = tmp_path / "out.vsdx"
    PackageStore.open(source).save(target)
    assert target.stat().st_mode & 0o777 == 0o640
