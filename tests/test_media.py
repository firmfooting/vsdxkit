"""The bundled donors, and the shapes found in them by sentinel text (#104, #310)."""

from pathlib import Path

import pytest

from vsdxkit import media
from vsdxkit.errors import NotFoundError, VisioFileNotOpen
from vsdxkit.vsdxfile import VisioFile

MEDIA_DIR = Path(__file__).resolve().parents[1] / "src" / "vsdxkit" / "media"


@pytest.fixture
def fresh_donors():
    """An empty donor cache for the test, and another after it, so no test sees a donor another loaded."""
    media.donor.cache_clear()
    yield
    media.donor.cache_clear()


def test_bundled_media_path_is_absolute_and_cwd_independent(tmp_path, monkeypatch, fresh_donors):
    monkeypatch.chdir(tmp_path)
    path = Path(media.media_path(media.MEDIA))
    assert path.is_absolute()
    assert path.is_file()
    assert media.connector_shape() is not None  # loads from here, not from the working directory


def test_media_curved_connector_returns_curved():
    """Regression: the curved connector was the straight one."""
    curved = media.connector_shape(curved=True)
    straight = media.connector_shape()
    assert curved.ID != straight.ID
    with VisioFile(str(MEDIA_DIR / "media.vsdx")) as vis:
        assert curved.ID == vis.pages[0].shapes.require_text("CURVED_CONNECTOR").ID


def test_a_truncated_palette_name_is_refused(vsdx_copy):
    """Fails if a palette name is matched as a substring, so "PALETTE_PRO" builds a process shape (#310)."""
    with VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        before = [shape.ID for shape in page.shapes]

        with pytest.raises(NotFoundError, match=r"no shape named 'PALETTE_PRO'; it has .*PALETTE_PROCESS"):
            vis.create_shape(page, "PALETTE_PRO", 1.0, 1.0)

        assert [shape.ID for shape in page.shapes] == before


def test_a_donor_refuses_writes():
    """Fails if a donor can be edited, which would change every shape copied from it afterwards."""
    process = media.palette_shape("PALETTE_PROCESS")
    with pytest.raises(VisioFileNotOpen):
        process.text = "edited"
    with pytest.raises(VisioFileNotOpen):
        media.connector_shape().x = 5.0
