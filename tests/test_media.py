from pathlib import Path

from vsdx import VisioFile

MEDIA_DIR = Path(__file__).resolve().parents[1] / "vsdx" / "media"


def test_bundled_media_path_is_absolute_and_cwd_independent(tmp_path, monkeypatch):
    from vsdx import Media

    monkeypatch.chdir(tmp_path)
    media = Media()
    try:
        assert Path(media.media.filename).is_absolute()
        assert Path(media.media.filename).is_file()
    finally:
        media.close()


def test_media_curved_connector_returns_curved():
    """Regression: Media.curved_connector returned the straight connector."""
    from vsdx import Media

    media = Media()
    try:
        curved = media.curved_connector
        straight = media.straight_connector
        assert curved is not None and straight is not None
        assert curved.ID != straight.ID
        with VisioFile(str(MEDIA_DIR / "media.vsdx")) as vis:
            page = vis.pages[0]
            expected_curved = page.find_shape_by_text("CURVED_CONNECTOR")
            assert expected_curved is not None
            assert curved.ID == expected_curved.ID
    finally:
        media.close()
