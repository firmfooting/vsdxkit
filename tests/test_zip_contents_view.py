"""`zip_file_contents` as a view over the package store, until #91 deletes it.

The view must keep every existing caller working while holding nothing
itself: a write through it is a write to the store, and a read is what the
store would save.
"""

from __future__ import annotations

import copy
import io
import os
import xml.etree.ElementTree as ET
import zipfile

import pytest

from vsdxkit import VisioFile
from vsdxkit.package import PackageStore, XmlPart
from vsdxkit.xmlio import serialise_part
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


def test_a_write_to_a_parsed_part_keeps_the_baseline_it_arrived_with(view, store):
    """Fails if a view write to a parsed part replaces the part, so its arrival bytes stop being what an unchanged save writes.

    Two writes: one that changes the page, then one that puts back what it
    meant on arrival, in ElementTree's spelling rather than the file's. The
    part is unchanged in meaning after both, so it must read back as the bytes
    it arrived as, which is only possible if neither write threw away the
    baseline the store took when the page was parsed.
    """
    name = "/visio/pages/page1.xml"
    key = f"{DIRECTORY}{name}"
    original = store.read_bytes(name)
    tree = store.require_xml(name)
    respelled = serialise_part(tree)
    assert respelled != original  # the test needs two spellings of one meaning
    changed = copy.deepcopy(tree.getroot())
    changed.set("VsdxkitMarker", "1")
    view[key] = io.BytesIO(serialise_part(ET.ElementTree(changed)))
    assert b"VsdxkitMarker" in store.read_bytes(name)
    view[key] = io.BytesIO(respelled)
    assert store.read_bytes(name) == original


def test_a_write_through_a_buffer_whose_member_was_deleted_leaves_it_deleted(view, store):
    """Fails if a buffer writes through without checking the store still holds the part it was made from.

    The old dict dropped its BytesIO on `del`, so a write to that BytesIO went
    nowhere; writing it to the store brings the member back.
    """
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    buf = view[key]
    del view[key]
    buf.seek(0)
    buf.write(b"resurrected")
    buf.truncate()
    assert store.part("/docProps/thumbnail.emf") is None
    assert buf.getvalue() == b"resurrected"  # still an ordinary BytesIO


def test_a_write_through_a_deleted_parsed_members_snapshot_leaves_it_deleted(view, store):
    """Fails if a snapshot of a parsed part writes through after the part was removed from the store."""
    name = "/visio/pages/page2.xml"
    store.require_xml(name)
    buf = view[f"{DIRECTORY}{name}"]
    del view[f"{DIRECTORY}{name}"]
    buf.seek(0)
    buf.write(b"<Resurrected/>")
    buf.truncate()
    assert store.part(name) is None


def test_a_deleted_member_stays_absent_from_disk_after_a_late_write(vsdx_copy, tmp_path):
    """Fails if a buffer taken before `del zip_file_contents[key]` can still write the member back before save."""
    target = str(tmp_path / "saved.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        # a member of the test's own, so deleting it leaves nothing pointing at it
        key = f"{vis.directory}/visio/scratch.bin"
        vis.zip_file_contents[key] = io.BytesIO(b"scratch")
        buf = vis.zip_file_contents[key]
        del vis.zip_file_contents[key]
        buf.seek(0)
        buf.write(b"resurrected")
        vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert "visio/scratch.bin" not in archive.namelist()


def test_a_write_through_a_buffer_whose_member_was_reassigned_keeps_the_new_value(view, store):
    """Fails if a buffer read before `view[key] = new` writes its own bytes over `new`."""
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    buf = view[key]
    view[key] = io.BytesIO(b"new")
    buf.seek(0)
    buf.write(b"stale")
    assert store.read_bytes("/docProps/thumbnail.emf") == b"new"


def test_a_store_write_detaches_a_buffer_read_before_it(view, store):
    """Fails if a buffer keeps writing through after a store write replaced the part it was made from."""
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    buf = view[key]
    store.write_bytes("/docProps/thumbnail.emf", b"later")
    buf.seek(0)
    buf.write(b"stale")
    assert store.read_bytes("/docProps/thumbnail.emf") == b"later"


def test_a_new_tree_detaches_a_snapshot_taken_of_the_old_one(view, store):
    """Fails if a parsed part's snapshot writes through after `write_xml` gave the part a different tree."""
    name = "/visio/pages/page2.xml"
    store.require_xml(name)
    buf = view[f"{DIRECTORY}{name}"]
    replacement = ET.ElementTree(ET.Element("Replacement"))
    store.write_xml(name, replacement)
    buf.seek(0)
    buf.write(b"<Stale/>")
    buf.truncate()
    held = store.part(name)
    assert isinstance(held, XmlPart)
    assert held.tree is replacement
    assert held.tree.getroot().tag == "Replacement"


def test_a_detached_buffer_stays_detached(view, store):
    """Fails if a detached buffer re-attaches when its own write lands on a store that no longer holds its part.

    Once `del` has run, the buffer's first write must not bring the member
    back as a fresh part the buffer then treats as its own.
    """
    key = f"{DIRECTORY}/docProps/thumbnail.emf"
    buf = view[key]
    del view[key]
    buf.write(b"one")
    buf.write(b"two")
    assert store.part("/docProps/thumbnail.emf") is None


def test_an_exported_buffer_detached_by_reassignment_is_not_synced_at_save(vsdx_copy, tmp_path):
    """Fails if sync() writes an exported buffer's memoryview edit after its member was reassigned."""
    target = str(tmp_path / "saved.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        key = f"{vis.directory}/docProps/thumbnail.emf"
        memory = vis.zip_file_contents[key].getbuffer()
        vis.zip_file_contents[key] = io.BytesIO(b"new")
        memory[0] = 0
        vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert archive.read("docProps/thumbnail.emf") == b"new"


def test_promotion_does_not_detach_a_buffer(view, store):
    """Fails if parsing a part counts as replacing it, so a buffer read before the parse stops writing through.

    Promotion changes how the store holds a part, not what it holds; the old
    dict had no such step, and a buffer taken from it kept changing the
    package however often something else read the member as XML.
    """
    name = "/visio/pages/page2.xml"
    buf = view[f"{DIRECTORY}{name}"]
    tree = store.require_xml(name)
    # longer than the part, so the one write replaces all of it and parses
    rewritten = b"<Rewritten Padding='" + b"x" * len(buf.getvalue()) + b"'/>"
    buf.seek(0)
    buf.write(rewritten)
    held = store.part(name)
    assert isinstance(held, XmlPart)
    assert held.tree is tree
    assert tree.getroot().tag == "Rewritten"


PAGE1 = "/visio/pages/page1.xml"
MARKER = b"VsdxkitMarker='1'"


def _shorter_replacement(original: bytes) -> bytes:
    """The same page with one attribute added, and shorter than `original`.

    Shorter because the partial-rewrite idiom only leaves unparseable bytes
    behind when the new XML does not cover the old: dropping the XML
    declaration pays for the attribute. The idiom's intermediate state --
    the replacement followed by the old tail -- is checked not to parse, since
    a test of what happens to those bytes means nothing if they do.
    """
    declaration, _, rest = original.partition(b"\r\n")
    assert declaration.startswith(b"<?xml")
    replacement = rest.replace(b"<PageContents ", b"<PageContents " + MARKER + b" ", 1)
    assert len(replacement) < len(original)
    with pytest.raises(ET.ParseError):
        ET.fromstring(replacement + original[len(replacement) :])
    return replacement


def _partial_rewrite(buf: io.BytesIO, replacement: bytes) -> None:
    buf.seek(0)
    buf.write(replacement)
    buf.truncate()


def _canonical(data: bytes) -> str:
    return ET.canonicalize(xml_data=data, with_comments=True, strip_text=False)


def test_a_partial_rewrite_keeps_the_parsed_tree(view, store):
    """Fails if a buffer's write-through of bytes that do not parse replaces a parsed part with those bytes.

    Between its `write()` and its `truncate()` the idiom holds the new XML
    followed by the old tail. Writing that as the part would detach the tree
    the document edits, and the `truncate()` would then put valid XML into a
    part that is only bytes.
    """
    tree = store.require_xml(PAGE1)
    part = store.part(PAGE1)
    buf = view[f"{DIRECTORY}{PAGE1}"]
    _partial_rewrite(buf, _shorter_replacement(buf.getvalue()))
    assert store.part(PAGE1) is part
    root = tree.getroot()
    assert root is not None
    assert root.get("VsdxkitMarker") == "1"


def test_a_partial_rewrite_and_a_later_object_model_edit_both_reach_disk(vsdx_copy, tmp_path):
    """Fails if the partial-rewrite idiom detaches the page's tree, so either the rewrite or the later edit is lost."""
    target = str(tmp_path / "saved.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        buf = vis.zip_file_contents[page.filename]
        _partial_rewrite(buf, _shorter_replacement(buf.getvalue()))
        shape = page.find_shape_by_id("1")
        assert shape is not None
        shape.text = "Edited after the rewrite"
        vis.save_vsdx(target)
    with VisioFile(target) as saved:
        page = saved.pages[0]
        assert page.xml.getroot().get("VsdxkitMarker") == "1"
        shape = page.find_shape_by_id("1")
        assert shape is not None
        assert shape.text == "Edited after the rewrite"


def test_a_partial_rewrite_alone_reaches_disk(vsdx_copy, tmp_path):
    """Fails if the partial-rewrite idiom leaves the page's old tree in the package for the save to write."""
    target = str(tmp_path / "saved.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        buf = vis.zip_file_contents[f"{vis.directory}{PAGE1}"]
        replacement = _shorter_replacement(buf.getvalue())
        _partial_rewrite(buf, replacement)
        vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert _canonical(archive.read(PAGE1[1:])) == _canonical(replacement)


def test_bytes_that_do_not_parse_are_held_until_sync(view, store):
    """Fails if sync() does not write a buffer still holding bytes that do not parse, or if nothing holds that buffer.

    The write is made through a buffer nobody keeps, so only the view's own
    reference can carry its bytes to the sync.
    """
    store.require_xml(PAGE1)
    key = f"{DIRECTORY}{PAGE1}"
    original = view[key].getvalue()
    view[key].write(b"not xml")
    assert isinstance(store.part(PAGE1), XmlPart)
    view.sync()
    assert store.read_bytes(PAGE1) == b"not xml" + original[len(b"not xml") :]


def test_bytes_that_do_not_parse_are_written_when_the_buffer_is_closed(view, store):
    """Fails if close() drops a buffer still holding bytes that do not parse, so a `with` block's last write is lost."""
    store.require_xml(PAGE1)
    with view[f"{DIRECTORY}{PAGE1}"] as buf:
        buf.seek(0)
        buf.write(b"not xml")
        buf.truncate()
    assert store.read_bytes(PAGE1) == b"not xml"


def test_a_pending_buffer_detached_before_sync_is_not_written(view, store):
    """Fails if sync() writes a buffer's unparseable bytes after its member was deleted."""
    store.require_xml(PAGE1)
    key = f"{DIRECTORY}{PAGE1}"
    view[key].write(b"not xml")
    del view[key]
    view.sync()
    assert store.part(PAGE1) is None


def test_a_later_parseable_write_clears_the_pending_bytes(view, store):
    """Fails if a buffer that went on to write XML that parses is still written at sync as the bytes before it."""
    tree = store.require_xml(PAGE1)
    buf = view[f"{DIRECTORY}{PAGE1}"]
    _partial_rewrite(buf, _shorter_replacement(buf.getvalue()))
    root = tree.getroot()
    assert root is not None
    root.set("EditedAfter", "1")
    view.sync()
    held = store.part(PAGE1)
    assert isinstance(held, XmlPart)
    assert held.tree is tree
    assert tree.getroot() is root, "sync wrote the held-back bytes over the tree after a later write parsed"
    assert root.get("EditedAfter") == "1"


@pytest.mark.allow_invalid_package("unreadable-part")
def test_unparseable_bytes_left_in_a_buffer_reach_disk_as_they_are(vsdx_copy, tmp_path):
    """Fails if bytes that do not parse, still in a page's buffer at save, are dropped or written over by the page's tree.

    Deliberately writes a broken page, which is the point: the caller's
    final bytes are what the package holds, as they were before the store.
    """
    target = str(tmp_path / "saved.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        buf = vis.zip_file_contents[f"{vis.directory}{PAGE1}"]
        buf.seek(0)
        buf.write(b"not xml")
        expected = buf.getvalue()
        vis.save_vsdx(target)
    with zipfile.ZipFile(target) as archive:
        assert archive.read(PAGE1[1:]) == expected


@pytest.mark.allow_invalid_package("unreadable-part")
def test_unparseable_bytes_flushed_at_one_save_survive_the_next(vsdx_copy, tmp_path):
    """Fails if a second save writes the page's old tree over the bytes the first save's sync put in its place."""
    first = str(tmp_path / "first.vsdx")
    second = str(tmp_path / "second.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        buf = vis.zip_file_contents[f"{vis.directory}{PAGE1}"]
        buf.seek(0)
        buf.write(b"not xml")
        expected = buf.getvalue()
        vis.save_vsdx(first)
        vis.save_vsdx(second)
    with zipfile.ZipFile(second) as archive:
        assert archive.read(PAGE1[1:]) == expected


def test_copy_is_a_plain_dict_detached_from_the_store(view, store):
    """Fails if the view has no copy(), which the old dict had, or if the copy it returns writes to the store."""
    names = store.names()
    snapshot = view.copy()
    assert type(snapshot) is dict
    assert list(snapshot) == list(view)
    del snapshot[f"{DIRECTORY}/docProps/thumbnail.emf"]
    snapshot[f"{DIRECTORY}/visio/new.xml"] = io.BytesIO(b"<New/>")
    snapshot.clear()
    assert store.names() == names


def _page1_with_marker(store: PackageStore) -> bytes:
    """Page 1 as new XML: the parsed tree with one attribute added, serialised."""
    changed = copy.deepcopy(store.require_xml(PAGE1).getroot())
    changed.set("VsdxkitMarker", "1")
    return serialise_part(ET.ElementTree(changed))


def test_assigning_new_xml_to_a_parsed_member_detaches_an_older_buffer(view, store):
    """Fails if `view[key] = new_xml` on a parsed part leaves a buffer read before it bound, so it writes over new_xml.

    The assignment lands in the part's tree and keeps the part object, so
    only the view's generation for the name can tell the old buffer that
    its member was rebound, as a rebound dict value would have been.
    """
    key = f"{DIRECTORY}{PAGE1}"
    tree = store.require_xml(PAGE1)
    old = view[key]
    stale = old.getvalue()
    new_xml = _page1_with_marker(store)
    view[key] = io.BytesIO(new_xml)
    old.seek(0)
    old.write(stale)
    root = tree.getroot()
    assert root is not None
    assert root.get("VsdxkitMarker") == "1"
    assert old.getvalue() == stale  # still an ordinary BytesIO


def test_assigning_new_xml_to_a_parsed_page_survives_an_older_buffers_write_at_save(vsdx_copy, tmp_path):
    """Fails if a buffer read before `zip_file_contents[page] = new_xml` can write the old page back before save."""
    target = str(tmp_path / "saved.vsdx")
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        old = vis.zip_file_contents[page.filename]
        stale = old.getvalue()
        vis.zip_file_contents[page.filename] = io.BytesIO(_page1_with_marker(vis._package))
        old.seek(0)
        old.write(stale)
        vis.save_vsdx(target)
    with VisioFile(target) as saved:
        assert saved.pages[0].xml.getroot().get("VsdxkitMarker") == "1"


def test_an_exported_snapshot_is_not_synced_after_its_parsed_member_is_rebound(view, store):
    """Fails if sync() writes an exported snapshot's memoryview edit after `view[key] = new_xml` on its parsed part."""
    key = f"{DIRECTORY}{PAGE1}"
    tree = store.require_xml(PAGE1)
    memory = view[key].getbuffer()
    new_xml = _page1_with_marker(store)
    view[key] = io.BytesIO(new_xml)
    memory[0:1] = b"#"
    view.sync()
    part = store.part(PAGE1)
    assert isinstance(part, XmlPart)
    assert part.tree is tree
    root = tree.getroot()
    assert root is not None
    assert root.get("VsdxkitMarker") == "1"


def test_held_back_bytes_are_not_settled_after_their_parsed_member_is_rebound(view, store):
    """Fails if sync() settles a buffer's unparseable bytes after `view[key] = new_xml` rebound its parsed part."""
    key = f"{DIRECTORY}{PAGE1}"
    tree = store.require_xml(PAGE1)
    view[key].write(b"not xml")
    view[key] = io.BytesIO(_page1_with_marker(store))
    view.sync()
    part = store.part(PAGE1)
    assert isinstance(part, XmlPart)
    assert part.tree is tree


def test_two_snapshots_of_a_parsed_part_both_write_and_the_last_wins(view, store):
    """Fails if one snapshot's own write-through detaches another snapshot of the same parsed part.

    Pins the documented limitation rather than a goal: neither snapshot
    rebinds the member, so both stay bound, and each write lands in the
    tree in turn. The dict gave both holders one buffer; the view gives
    each its own copy, so the second writer's bytes are what the part holds.
    """
    key = f"{DIRECTORY}{PAGE1}"
    tree = store.require_xml(PAGE1)
    first = view[key]
    second = view[key]
    assert first is not second
    first.seek(0)
    first.write(b"<First/>")
    first.truncate()
    second.seek(0)
    second.write(b"<Second/>")
    second.truncate()
    root = tree.getroot()
    assert root is not None
    assert root.tag == "Second"
