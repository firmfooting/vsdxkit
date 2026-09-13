"""Tests for VisioFile.create_shape (extended palette API)."""

import zipfile

from vsdxkit import VisioFile

BASE = "test8_simple_connector.vsdx"


def test_create_shape_from_palette(vsdx_copy):
    path = vsdx_copy(BASE)
    with VisioFile(path) as vis:
        page = vis.pages[0]
        shape = vis.create_shape(page, "PALETTE_DECISION", 4.0, 6.0, w=1.5, h=1.0, text="Choose")
        assert shape is not None
        assert shape.text.strip() == "Choose"
        assert abs(shape.x - 4.0) < 0.001
        assert abs(shape.y - 6.0) < 0.001
        assert abs(shape.width - 1.5) < 0.001
        vis.save_vsdx(path)
    with VisioFile(path) as vis2:
        assert vis2.pages[0].find_shape_by_text("Choose") is not None


def test_create_shape_clears_sentinel_when_no_text(vsdx_copy):
    with VisioFile(vsdx_copy(BASE)) as vis:
        page = vis.pages[0]
        shape = vis.create_shape(page, "PALETTE_PROCESS", 6.0, 6.0)
        assert shape.text == ""
        assert page.find_shape_by_text("PALETTE_PROCESS") is None


def test_create_shape_unknown_palette_name(vsdx_copy):
    with VisioFile(vsdx_copy(BASE)) as vis:
        try:
            vis.create_shape(vis.pages[0], "PALETTE_NOPE", 1.0, 1.0)
            raise AssertionError("expected ValueError")
        except ValueError as e:
            assert "PALETTE_NOPE" in str(e)


def test_created_shape_package_valid(vsdx_copy):
    path = vsdx_copy(BASE)
    with VisioFile(path) as vis:
        page = vis.pages[0]
        vis.create_shape(page, "PALETTE_DATABASE", 3.0, 3.0, text="DB")
        vis.create_shape(page, "PALETTE_PARALLELOGRAM", 6.0, 3.0, text="IO")
        vis.save_vsdx(path)
    assert zipfile.ZipFile(path).testzip() is None
