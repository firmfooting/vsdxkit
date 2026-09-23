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

from vsdxkit import VisioFile
from vsdxkit.package import PackageStore, XmlPart
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


def test_delitem_with_invalid_part_name_raises_key_error(view):
    """Deleting a key with an invalid part name must raise KeyError, not ValueError."""
    with pytest.raises(KeyError):
        del view[f"{DIRECTORY}/visio/../escape.xml"]


def test_mutations_through_returned_buffer_update_the_store(view, store):
    """Mutations to the returned buffer (seek, write, truncate) must update the store (backwards compatibility)."""
    key = f"{DIRECTORY}/visio/document.xml"
    buf = view[key]
    buf.seek(0)
    buf.write(b"<Changed/>")
    buf.truncate()
    assert store.read_bytes("/visio/document.xml") == b"<Changed/>"


def test_reading_returned_buffer_does_not_replace_promoted_part(view, store):
    """Reading a returned buffer must not replace a promoted XmlPart in the store."""
    tree = store.require_xml("/visio/pages/page1.xml")
    root = tree.getroot()
    assert root is not None
    original_part = store.part("/visio/pages/page1.xml")
    buf = view[f"{DIRECTORY}/visio/pages/page1.xml"]
    buf.read()
    assert store.part("/visio/pages/page1.xml") is original_part


def test_writelines_writes_through(view, store):
    """writelines on the returned buffer must write through to the store."""
    key = f"{DIRECTORY}/visio/document.xml"
    buf = view[key]
    buf.seek(0)
    buf.truncate()
    buf.writelines([b"<", b"New", b"/>"])
    assert store.read_bytes("/visio/document.xml") == b"<New/>"


def test_a_getbuffer_edit_reaches_the_store_on_sync(view, store):
    """Fails if getbuffer() stops registering the buffer, or sync() stops writing a changed one to the store."""
    buf = view[f"{DIRECTORY}/docProps/thumbnail.emf"]
    original = buf.getvalue()
    buf.getbuffer()[0] = original[0] ^ 0xFF
    assert store.read_bytes("/docProps/thumbnail.emf") == original
    view.sync()
    assert store.read_bytes("/docProps/thumbnail.emf") == bytes([original[0] ^ 0xFF]) + original[1:]


def test_a_getbuffer_edit_reaches_disk_through_save_vsdx(vsdx_copy, tmp_path):
    """Fails if VisioFile.save_vsdx stops calling zip_file_contents.sync() before it writes the package."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        buf = vis.zip_file_contents[f"{vis.directory}/docProps/thumbnail.emf"]
        original = buf.getvalue()
        buf.getbuffer()[0] = original[0] ^ 0xFF
        target = str(tmp_path / "saved.vsdx")
        vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert archive.read("docProps/thumbnail.emf") == bytes([original[0] ^ 0xFF]) + original[1:]


def test_an_exported_but_unedited_buffer_writes_nothing(view, store):
    """Fails if sync() writes an exported buffer whose bytes have not changed, replacing its promoted part."""
    store.require_xml("/visio/pages/page1.xml")
    promoted = store.part("/visio/pages/page1.xml")
    assert isinstance(promoted, XmlPart)
    buf = view[f"{DIRECTORY}/visio/pages/page1.xml"]
    bytes(buf.getbuffer())
    view.sync()
    assert store.part("/visio/pages/page1.xml") is promoted


def test_a_write_through_after_export_is_not_collected_again(view, store):
    """Fails if a write-through leaves the export baseline stale, so sync() rewrites bytes the store has moved past."""
    buf = view[f"{DIRECTORY}/visio/pages/page1.xml"]
    buf.getbuffer().release()
    buf.seek(0)
    buf.write(b"<Changed/>")
    buf.truncate()
    store.write_bytes("/visio/pages/page1.xml", b"<Later/>")
    view.sync()
    assert store.read_bytes("/visio/pages/page1.xml") == b"<Later/>"


def test_sync_does_not_bring_back_a_removed_part(view, store):
    """Fails if sync() writes an exported buffer's edit even after its part was removed from the package."""
    buf = view[f"{DIRECTORY}/docProps/thumbnail.emf"]
    buf.getbuffer()[0] = 0
    del view[f"{DIRECTORY}/docProps/thumbnail.emf"]
    view.sync()
    assert store.part("/docProps/thumbnail.emf") is None


def test_a_one_line_getbuffer_edit_reaches_disk(vsdx_copy, tmp_path):
    """Fails if the view holds exported buffers weakly, so a temporary buffer's edit dies before save."""
    target = str(tmp_path / "saved.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        key = f"{vis.directory}/docProps/thumbnail.emf"
        first = vis.zip_file_contents[key].getvalue()[0]
        vis.zip_file_contents[key].getbuffer()[0] = first ^ 0xFF
        vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert archive.read("docProps/thumbnail.emf")[0] == first ^ 0xFF


def test_a_buffer_stays_registered_after_sync(view, store):
    """Fails if sync() unregisters a buffer, so an edit through a memoryview still held is lost at the next save."""
    buf = view[f"{DIRECTORY}/docProps/thumbnail.emf"]
    memory = buf.getbuffer()
    memory[0] = 1
    view.sync()
    memory[0] = 2
    view.sync()
    assert store.read_bytes("/docProps/thumbnail.emf")[:1] == b"\x02"


def test_repeated_exports_register_a_buffer_once(view):
    """Fails if getbuffer() registers the same buffer on every call, growing the registry without bound."""
    buf = view[f"{DIRECTORY}/docProps/thumbnail.emf"]
    for _ in range(3):
        buf.getbuffer().release()
    assert len(view._exports) == 1


def test_sync_skips_and_drops_a_closed_buffer(view, store):
    """Fails if sync() reads a closed buffer (ValueError) or keeps it registered."""
    original = store.read_bytes("/docProps/thumbnail.emf")
    buf = view[f"{DIRECTORY}/docProps/thumbnail.emf"]
    buf.getbuffer().release()
    buf.close()
    view.sync()
    assert store.read_bytes("/docProps/thumbnail.emf") == original
    assert view._exports == {}


def test_two_reads_of_a_member_share_one_buffer_so_both_edits_land(view, store):
    """Fails if __getitem__ returns a fresh snapshot per read, so the second buffer's write-through restores byte 0."""
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    original = store.read_bytes("/docProps/thumbnail.emf")
    assert original is not None
    a = view[key]
    b = view[key]
    assert a is b
    a.seek(0)
    a.write(bytes([original[0] ^ 0xFF]))
    b.seek(1)
    b.write(bytes([original[1] ^ 0xFF]))
    expected = bytes([original[0] ^ 0xFF, original[1] ^ 0xFF]) + original[2:]
    assert store.read_bytes("/docProps/thumbnail.emf") == expected


def test_a_read_after_a_write_through_is_the_same_buffer(view, store):
    """Fails if a write-through does not re-point the cache at the part it wrote, so the next read snapshots afresh."""
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    a = view[key]
    a.seek(0)
    a.write(b"\x00")
    assert view[key] is a


def test_two_reads_then_two_edits_reach_disk(vsdx_copy, tmp_path):
    """Fails if VisioFile.zip_file_contents hands out one snapshot per read, so an interleaved edit is lost at save."""
    target = str(tmp_path / "saved.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        key = f"{vis.directory}/docProps/thumbnail.emf"
        a = vis.zip_file_contents[key]
        b = vis.zip_file_contents[key]
        original = a.getvalue()
        a.seek(0)
        a.write(bytes([original[0] ^ 0xFF]))
        b.seek(1)
        b.write(bytes([original[1] ^ 0xFF]))
        vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert archive.read("docProps/thumbnail.emf")[:2] == bytes([original[0] ^ 0xFF, original[1] ^ 0xFF])


def test_a_store_write_between_reads_invalidates_the_cached_buffer(view, store):
    """Fails if the view returns its cached buffer without checking the store still holds the part it was made from."""
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    a = view[key]
    store.write_bytes("/docProps/thumbnail.emf", b"replaced")
    b = view[key]
    assert b is not a
    assert b.getvalue() == b"replaced"


def test_setitem_and_delitem_drop_the_cached_buffer(view, store):
    """Fails if __setitem__ or __delitem__ leave a cached buffer behind that a later read could hand out."""
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    a = view[key]
    view[key] = io.BytesIO(b"set")
    b = view[key]
    assert b is not a
    assert b.getvalue() == b"set"
    del view[key]
    assert view._live == {}


def test_a_closed_cached_buffer_is_not_handed_out_again(view):
    """Fails if the cache returns a buffer the caller closed, which can no longer be read."""
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    a = view[key]
    a.close()
    b = view[key]
    assert b is not a
    assert not b.closed


def test_a_promoted_part_is_read_as_a_fresh_snapshot(view, store):
    """Fails if an XML part's buffer is cached, so a read after a tree edit returns bytes the tree has moved past."""
    tree = store.require_xml("/visio/pages/page1.xml")
    key = f"{DIRECTORY}/visio/pages/page1.xml"
    a = view[key]
    root = tree.getroot()
    assert root is not None
    root.set("VsdxkitMarker", "1")
    b = view[key]
    assert b is not a
    assert b"VsdxkitMarker" in b.getvalue()


def test_a_cached_exported_buffer_is_still_collected_by_sync(view, store):
    """Fails if caching bypasses the export registry, so a memoryview edit on a re-read buffer never reaches the store."""
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    view[key]
    memory = view[key].getbuffer()
    memory[0] = 7
    view.sync()
    assert store.read_bytes("/docProps/thumbnail.emf")[:1] == b"\x07"
    assert view[key].getbuffer()[0] == 7
