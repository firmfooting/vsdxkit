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


@pytest.mark.allow_invalid_package
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
