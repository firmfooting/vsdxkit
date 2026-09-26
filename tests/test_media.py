"""The bundled donors, and the shapes found in them by sentinel text (#104, #310)."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from vsdxkit import _media, namespace
from vsdxkit.document import Document
from vsdxkit.errors import NotFoundError
from vsdxkit.shape_kind import ShapeKind

MEDIA_DIR = Path(__file__).resolve().parents[1] / "src" / "vsdxkit" / "_bundled"


@pytest.fixture
def fresh_donors(monkeypatch):
    """A donor table of the test's own, so it loads its donors and no other test sees them."""
    monkeypatch.setattr(_media, "_donors", {})


def test_bundled_media_path_is_absolute_and_cwd_independent(tmp_path, monkeypatch, fresh_donors):
    monkeypatch.chdir(tmp_path)
    path = Path(_media.media_path(_media.MEDIA))
    assert path.is_absolute()
    assert path.is_file()
    assert _media._donor(_media.MEDIA, Document.open).pages  # loads from here, not from the working directory


def test_media_curved_connector_returns_curved():
    """Regression: the curved connector was the straight one."""
    curved = _media._sentinel(_media.MEDIA, _media.CURVED_CONNECTOR, Document.open)
    straight = _media._sentinel(_media.MEDIA, _media.STRAIGHT_CONNECTOR, Document.open)
    assert curved.ID != straight.ID
    vis = Document.open(str(MEDIA_DIR / "media.vsdx"))
    assert curved.ID == vis.pages[0].shapes.require_text("CURVED_CONNECTOR").ID


def test_a_truncated_sentinel_is_refused():
    """Fails if a sentinel is matched as a substring, so "PALETTE_PRO" finds the process shape (#310)."""
    with pytest.raises(NotFoundError, match=r"no shape named 'PALETTE_PRO'; it has .*PALETTE_PROCESS"):
        _media._sentinel(_media.PALETTE, "PALETTE_PRO", Document.open)


def test_what_the_library_creates_from_a_donor_is_a_copy(vsdx_copy):
    """Fails if a created shape, connector or style is a donor's own element, which a caller could edit past the closed guard.

    `media` hands its donor shapes out uncopied, to the library alone:
    `Page.create_shape`, `Document._copy_connector` and `_style_copy` copy them.
    """
    donor = _media._donor(_media.PALETTE, Document.open)
    donor_elements = set(donor.pages[0].xml.getroot().iter())
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shape = page.create_shape(ShapeKind.PROCESS, x=1.0, y=1.0)
    connector = vis._copy_connector(page)
    assert not donor_elements & set(shape.xml.iter())
    assert shape.page is page and connector.page is page
    donor_connector = _media._connector_shape(Document.open)
    assert not set(donor_connector.xml.iter()) & set(connector.xml.iter())
    # the same cells and sections: only the ID and the sentinel text differ
    text = f"{namespace}Text"
    assert [ET.tostring(child) for child in connector.xml if child.tag != text] == [
        ET.tostring(child) for child in donor_connector.xml if child.tag != text
    ]
    media_donor = _media._donor(_media.MEDIA, Document.open)
    style_id = next(iter(media_donor._style_sheets())).attrib["ID"]
    assert _media._style_copy(style_id, Document.open) is not media_donor._get_style_by_id(style_id)


def test_each_donor_loads_once_across_threads(monkeypatch):
    """Fails if threads creating their first shapes at once each open and parse the same donor."""
    import threading

    monkeypatch.setattr(_media, "_donors", {})
    opened: list[str] = []

    def recording(path):
        opened.append(path)
        return Document.open(path)

    start = threading.Barrier(8)

    def load():
        start.wait()
        _media._donor(_media.PALETTE, recording)

    threads = [threading.Thread(target=load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(opened) == 1
