"""The bundled donor packages are opened once per process, and never written (#104).

`create_shape` and `Connect.create` both copy out of the bundled media and
palette documents. Opening them per call re-parsed both packages on every
shape and connector (#65); holding them per document made every document
responsible for closing them, and the leak was the document that did not
(#242). Now each is opened once, closed to writes at once, and shared.
"""

import os
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

import pytest

from vsdxkit import _media
from vsdxkit.document import Document
from vsdxkit.glue import Routing
from vsdxkit.package import PackageStore
from vsdxkit.shape_kind import ShapeKind

BASE = "test8_simple_connector.vsdx"

DONORS = (_media.MEDIA, _media.PALETTE)


@pytest.fixture
def fresh_donors(monkeypatch):
    """A donor table of the test's own, so it loads its donors and no other test sees them."""
    monkeypatch.setattr(_media, "_donors", {})


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


def test_each_donor_is_opened_once_across_documents(vsdx_copy, monkeypatch, fresh_donors):
    """Fails if a donor is opened per call or per document, or if closing a document takes it away."""
    opens = count_package_opens(monkeypatch)
    path = vsdx_copy(BASE)

    vis = Document.open(path)
    page = vis.pages[0]
    shapes = [page.create_shape(ShapeKind.PROCESS, x=1.0 + i * 0.01, y=1.0, text=f"S{i}") for i in range(50)]
    for i in range(50):
        assert page.connect(shapes[i], shapes[(i + 1) % 50]) is not None
    vis.save(path)
    second = Document.open(vsdx_copy("test1.vsdx"))
    a = second.pages[0].create_shape(ShapeKind.DECISION, x=1.0, y=1.0, text="A")
    b = second.pages[0].create_shape(ShapeKind.DATABASE, x=2.0, y=1.0, text="B")
    second.pages[0].connect(a, b)

    for donor in DONORS:
        assert opens[donor] == 1, f"{donor} opened {opens[donor]} times, expected 1"

    # sharing one donor across every call must not corrupt what those calls
    # copy out of it: the saved package still reopens with every shape intact
    monkeypatch.undo()
    assert zipfile.ZipFile(path).testzip() is None
    reopened = Document.open(path)
    for i in range(50):
        assert reopened.pages[0].shapes.by_text(f"S{i}") is not None


def _donor_xml() -> dict[str, bytes]:
    """Every part of both donors as its store holds it, parsed parts serialised."""
    parts = {}
    for filename in DONORS:
        store = _media._donor(filename, Document.open)._package
        for name in store.names():
            parts[f"{filename}{name}"] = store.read_bytes(name)
    for filename in DONORS:
        for page in _media._donor(filename, Document.open).pages:
            parts[f"{filename}:{page.name}"] = ET.tostring(page.xml.getroot())
    return parts


def test_creation_leaves_the_donors_as_they_were(vsdx_copy, fresh_donors):
    """Fails if copying a shape or connector out of a donor writes anything back into it."""
    before = _donor_xml()
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    a = page.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0, text="A")
    b = page.create_shape(ShapeKind.START_END, x=3.0, y=1.0)
    page.connect(a, b, routing=Routing.CURVED)
    assert _donor_xml() == before


def test_provisioning_masters_reads_only_the_donors_master_parts(vsdx_copy, monkeypatch, fresh_donors):
    """Fails if copying the donor's masters reads any donor part outside `/visio/masters/`.

    Reading a part the donor has parsed serialises it, and the donor has parsed
    every page it holds -- all of it wasted on a copy that wants none of them.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    donor = _media._donor(_media.MEDIA, Document.open)
    read: list[str] = []
    original = PackageStore.read_bytes

    def spy(self, name):
        if self is donor._package:
            read.append(name)
        return original(self, name)

    monkeypatch.setattr(PackageStore, "read_bytes", spy)
    shapes = list(page.children)
    page.connect(shapes[0], shapes[1])
    assert read, "the donor's masters were not copied through its store; the test has gone stale"
    assert [name for name in read if not name.startswith("/visio/masters/")] == []


def test_provisioning_masters_copies_the_donors_master_parts_byte_for_byte(vsdx_copy):
    """Fails if a document with no masters gets anything but the donor's `/visio/masters/` parts, unchanged."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    assert not [n for n in vis._package.names() if n.startswith("/visio/masters/")]
    page = vis.pages[0]
    donor = _media._donor(_media.MEDIA, Document.open)
    shapes = list(page.children)
    page.connect(shapes[0], shapes[1])
    donor_masters = {n: donor._package.read_bytes(n) for n in donor._package.names() if n.startswith("/visio/masters/")}
    copied = {n: vis._package.read_bytes(n) for n in vis._package.names() if n.startswith("/visio/masters/")}
    # the copy is exact at the moment it is made; masters.xml and its rels may
    # be edited afterwards by the connector's own master registration, so
    # compare the master drawing parts, which nothing edits
    assert set(copied) == set(donor_masters)
    drawing = [n for n in donor_masters if re.fullmatch(r"master\d+\.xml", n.rsplit("/", 1)[-1])]
    assert drawing
    assert {n: copied.get(n) for n in drawing} == {n: donor_masters[n] for n in drawing}


def test_provisioning_masters_leaves_a_sibling_of_the_masters_folder_behind(vsdx_copy, fresh_donors):
    """Fails if the masters copy takes a donor part whose folder merely starts with `masters`.

    The copy selects parts by the part-name prefix `/visio/masters/`. Without
    its trailing slash that prefix also matches `/visio/masters-old/`, and the
    target would gain a part nothing refers to. The part is planted in the
    store directly, past the donor's closed guard, on a donor this test alone
    loads.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    _media._donor(_media.MEDIA, Document.open)._package.write_bytes("/visio/masters-old/x.xml", b"<x/>")
    shapes = list(page.children)
    page.connect(shapes[0], shapes[1])
    assert vis._package.part("/visio/masters-old/x.xml") is None
