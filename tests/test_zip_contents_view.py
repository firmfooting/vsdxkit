"""`zip_file_contents` as a view over the package store, until #91 deletes it.

The view must keep every existing caller working while holding nothing
itself: a write through it is a write to the store, and a read is what the
store would save.
"""

from __future__ import annotations

import io
import os
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
    """part_name_for_path must convert pseudo-paths to part names only when under the directory."""
    assert part_name_for_path(DIRECTORY, f"{DIRECTORY}/visio/document.xml") == "/visio/document.xml"
    assert part_name_for_path(DIRECTORY, "/elsewhere/visio/document.xml") is None
    assert part_name_for_path(DIRECTORY, f"{DIRECTORY}x/visio/document.xml") is None


def test_keys_are_the_old_pseudo_paths_in_archive_order(view, store):
    """The view's iteration order must match the archive's order and map part names to pseudo-paths."""
    with zipfile.ZipFile(os.path.join(BASEDIR, "test1.vsdx")) as archive:
        expected = [f"{DIRECTORY}/{name}" for name in archive.namelist() if not name.endswith("/")]
    assert list(view) == expected
    assert len(view) == len(store.names())


def test_a_read_is_what_the_store_would_save(view, store):
    """A read through the view reflects the current state of the store (mutation via store affects read)."""
    tree = store.require_xml("/visio/pages/page1.xml")
    root = tree.getroot()
    assert root is not None
    root.set("VsdxkitMarker", "1")
    assert b"VsdxkitMarker" in view[f"{DIRECTORY}/visio/pages/page1.xml"].getvalue()


def test_a_write_is_a_write_to_the_store(view, store):
    """A write through the view adds or updates a part in the store."""
    view[f"{DIRECTORY}/visio/new.xml"] = io.BytesIO(b"<New/>")
    assert store.read_bytes("/visio/new.xml") == b"<New/>"


def test_membership_does_not_serialise_and_tolerates_foreign_keys(view):
    """Checking membership (in operator) must not read or serialize parts, and must tolerate invalid keys."""
    assert f"{DIRECTORY}/visio/document.xml" in view
    assert "/elsewhere/visio/document.xml" not in view
    assert f"{DIRECTORY}/visio/../escape.xml" not in view
    assert 42 not in view


def test_pop_and_clear_remove_from_the_store(view, store):
    """pop() and clear() must remove parts from the store."""
    view.pop(f"{DIRECTORY}/visio/pages/page1.xml")
    assert store.part("/visio/pages/page1.xml") is None
    assert view.pop(f"{DIRECTORY}/visio/pages/page1.xml", None) is None
    view.clear()
    assert store.names() == ()


def test_a_key_outside_the_directory_is_refused_on_write(view):
    """Writing a key outside the configured directory must raise ValueError."""
    with pytest.raises(ValueError):
        view["/elsewhere/visio/new.xml"] = io.BytesIO(b"<New/>")


def test_a_missing_key_is_a_key_error(view):
    """Reading a missing key, whether in or out of the directory, must raise KeyError."""
    with pytest.raises(KeyError):
        view[f"{DIRECTORY}/visio/missing.xml"]
    with pytest.raises(KeyError):
        view["/elsewhere/visio/document.xml"]
