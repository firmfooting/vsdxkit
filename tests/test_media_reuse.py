"""The bundled donor packages are opened once per VisioFile, not per call.

`create_shape` and `Connect.create` both need the bundled media/palette
documents. Constructing a `Media` per call re-parsed both packages on every
shape and connector; these tests pin the shared, lazily created instance.
"""

import os
import re
import zipfile
from collections import Counter

import pytest

from vsdxkit.connectors import Connect
from vsdxkit.errors import VisioFileNotOpen
from vsdxkit.media import Media
from vsdxkit.package import PackageStore
from vsdxkit.vsdxfile import VisioFile

BASE = "test8_simple_connector.vsdx"

DONORS = ("media.vsdx", "palette_extended.vsdx")


def count_package_opens(monkeypatch) -> Counter:
    """Count ZipFile opens by file basename for the duration of a test."""
    opens: Counter = Counter()
    real_zipfile = zipfile.ZipFile

    class CountingZipFile(real_zipfile):
        def __init__(self, file, *args, **kwargs):
            if isinstance(file, (str, os.PathLike)):
                opens[os.path.basename(os.fspath(file))] += 1
            super().__init__(file, *args, **kwargs)

    monkeypatch.setattr(zipfile, "ZipFile", CountingZipFile)
    return opens


def test_bulk_creation_opens_each_donor_package_once(vsdx_copy, monkeypatch):
    opens = count_package_opens(monkeypatch)
    path = vsdx_copy(BASE)

    with VisioFile(path) as vis:
        page = vis.pages[0]
        shapes = [vis.create_shape(page, "PALETTE_PROCESS", 1.0 + i * 0.01, 1.0, text=f"S{i}") for i in range(50)]
        for i in range(50):
            connector = page.connect_shapes(shapes[i], shapes[(i + 1) % 50])
            assert connector is not None
        vis.save_vsdx(path)

    for donor in DONORS:
        assert opens[donor] == 1, f"{donor} opened {opens[donor]} times, expected 1"

    # sharing one donor across 100 calls must not corrupt what those calls
    # copy out of it: the saved package still reopens with every shape intact
    monkeypatch.undo()
    assert zipfile.ZipFile(path).testzip() is None
    with VisioFile(path) as reopened:
        reopened_page = reopened.pages[0]
        for i in range(50):
            assert reopened_page.find_shape_by_text(f"S{i}") is not None


def test_each_visiofile_gets_its_own_media(vsdx_copy, monkeypatch):
    """Caching is per document, so a second VisioFile still loads the donors."""
    opens = count_package_opens(monkeypatch)

    for _ in range(2):
        with VisioFile(vsdx_copy(BASE)) as vis:
            vis.create_shape(vis.pages[0], "PALETTE_PROCESS", 1.0, 1.0, text="A")

    assert opens["palette_extended.vsdx"] == 2


def test_close_vsdx_releases_the_shared_media(vsdx_copy):
    """close_vsdx closes the donors and drops the reference it cached."""
    vis = VisioFile(vsdx_copy(BASE))
    vis.create_shape(vis.pages[0], "PALETTE_PROCESS", 1.0, 1.0, text="A")
    cached = vis._media
    assert cached is not None

    vis.close_vsdx()

    assert vis._media is None
    assert cached._media_vsdx is None
    assert cached._palette_vsdx is None


def test_closed_document_refuses_to_rebuild_the_shared_media(vsdx_copy):
    """Rebuilding on demand was itself the leak (issue #242).

    This used to hand a closed document a fresh donor pair; `close_vsdx` had
    already released the pair it owned, so nothing left could close the new one.
    """
    vis = VisioFile(vsdx_copy(BASE))
    first = vis._shared_media()
    assert vis._shared_media() is first  # same instance while the file is open

    vis.close_vsdx()

    with pytest.raises(VisioFileNotOpen):
        vis._shared_media()
    assert vis._media is None


def test_a_closed_media_refuses_to_reopen_its_donors():
    """Same leak one layer down: Media used to reopen a donor after close()."""
    media = Media()
    assert media.palette.file_open

    media.close()

    with pytest.raises(VisioFileNotOpen):
        _ = media.media
    with pytest.raises(VisioFileNotOpen):
        _ = media.palette


def test_close_vsdx_is_idempotent(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    vis.create_shape(vis.pages[0], "PALETTE_PROCESS", 1.0, 1.0, text="A")
    vis.close_vsdx()
    vis.close_vsdx()
    assert vis.file_open is False
    assert vis._media is None


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
    assert set(copied) == set(donor_masters)
    drawing = [n for n in donor_masters if re.fullmatch(r"master\d+\.xml", n.rsplit("/", 1)[-1])]
    assert drawing
    assert {n: copied.get(n) for n in drawing} == {n: donor_masters[n] for n in drawing}


def test_provisioning_masters_leaves_a_sibling_of_the_masters_folder_behind(vsdx_copy):
    """Fails if the masters copy takes a donor part whose folder merely starts with `masters`.

    The copy selects parts by the part-name prefix `/visio/masters/`. Without
    its trailing slash that prefix also matches `/visio/masters-old/`, and the
    target would gain a part nothing refers to.
    """
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        donor = vis._shared_media().media
        donor._package.write_bytes("/visio/masters-old/x.xml", b"<x/>")
        shapes = page.child_shapes
        Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
        assert vis._package.part("/visio/masters-old/x.xml") is None
