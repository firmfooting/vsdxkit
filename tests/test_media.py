"""The bundled donors, and the shapes found in them by sentinel text (#104, #310)."""

from pathlib import Path

import pytest

from vsdxkit import media
from vsdxkit.errors import NotFoundError
from vsdxkit.vsdxfile import VisioFile

MEDIA_DIR = Path(__file__).resolve().parents[1] / "src" / "vsdxkit" / "media"


@pytest.fixture
def fresh_donors(monkeypatch):
    """A donor table of the test's own, so it loads its donors and no other test sees them."""
    monkeypatch.setattr(media, "_donors", {})


def test_bundled_media_path_is_absolute_and_cwd_independent(tmp_path, monkeypatch, fresh_donors):
    monkeypatch.chdir(tmp_path)
    path = Path(media.media_path(media.MEDIA))
    assert path.is_absolute()
    assert path.is_file()
    assert media._donor(media.MEDIA).pages  # loads from here, not from the working directory


def test_media_curved_connector_returns_curved():
    """Regression: the curved connector was the straight one."""
    curved = media._sentinel(media.MEDIA, media.CURVED_CONNECTOR)
    straight = media._sentinel(media.MEDIA, media.STRAIGHT_CONNECTOR)
    assert curved.ID != straight.ID
    vis = VisioFile(str(MEDIA_DIR / "media.vsdx"))
    assert curved.ID == vis.pages[0].shapes.require_text("CURVED_CONNECTOR").ID


def test_a_truncated_palette_name_is_refused(vsdx_copy):
    """Fails if a palette name is matched as a substring, so "PALETTE_PRO" builds a process shape (#310)."""
    vis = VisioFile(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    before = [shape.ID for shape in page.shapes]

    with pytest.raises(NotFoundError, match=r"no shape named 'PALETTE_PRO'; it has .*PALETTE_PROCESS"):
        vis.create_shape(page, "PALETTE_PRO", 1.0, 1.0)

    assert [shape.ID for shape in page.shapes] == before


def test_what_the_module_hands_out_is_a_copy(vsdx_copy):
    """Fails if a caller is given a donor's own elements, which it could edit past the closed guard."""
    donor = media._donor(media.PALETTE)
    donor_elements = set(donor.pages[0].xml.getroot().iter())
    vis = VisioFile(vsdx_copy("test1.vsdx"))
    shape = media.copy_palette_shape("PALETTE_PROCESS", vis.pages[0])
    connector = media.copy_connector(vis.pages[0])
    assert not donor_elements & set(shape.xml.iter())
    assert shape.page is vis.pages[0] and connector.page is vis.pages[0]
    style_id = next(iter(media._donor(media.MEDIA)._style_sheets())).attrib["ID"]
    assert media.media_style(style_id) is not media._donor(media.MEDIA)._get_style_by_id(style_id)


def test_each_donor_loads_once_across_threads(monkeypatch):
    """Fails if threads creating their first shapes at once each open and parse the same donor."""
    import threading

    monkeypatch.setattr(media, "_donors", {})
    opened: list[str] = []
    real_visiofile = media.VisioFile

    def recording(path):
        opened.append(path)
        return real_visiofile(path)

    monkeypatch.setattr(media, "VisioFile", recording)
    start = threading.Barrier(8)

    def load():
        start.wait()
        media._donor(media.PALETTE)

    threads = [threading.Thread(target=load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(opened) == 1
