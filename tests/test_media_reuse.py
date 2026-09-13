"""The bundled donor packages are opened once per VisioFile, not per call.

`create_shape` and `Connect.create` both need the bundled media/palette
documents. Constructing a `Media` per call re-parsed both packages on every
shape and connector; these tests pin the shared, lazily created instance.
"""

import os
import zipfile
from collections import Counter

from vsdx import VisioFile

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


def test_shared_media_is_rebuilt_rather_than_handed_back_closed(vsdx_copy):
    """The closed instance is never returned again, so no caller sees it broken."""
    vis = VisioFile(vsdx_copy(BASE))
    first = vis._shared_media()
    assert vis._shared_media() is first  # same instance while the file is open

    vis.close_vsdx()

    second = vis._shared_media()
    assert second is not first
    assert second.palette.pages[0].find_shape_by_text("PALETTE_PROCESS") is not None
    vis.close_vsdx()


def test_close_vsdx_is_idempotent(vsdx_copy):
    vis = VisioFile(vsdx_copy(BASE))
    vis.create_shape(vis.pages[0], "PALETTE_PROCESS", 1.0, 1.0, text="A")
    vis.close_vsdx()
    vis.close_vsdx()
    assert vis.file_open is False
    assert vis._media is None
