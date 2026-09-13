"""Malformed numeric ShapeSheet values must not silently become zero."""

import os

import pytest

import vsdx

FIXTURES = os.path.dirname(os.path.realpath(__file__))
namespace = "{http://schemas.microsoft.com/office/visio/2012/main}"


@pytest.fixture
def malformed_pinx_path(vsdx_copy, tmp_path):
    """A copy of test1.vsdx whose first shape has a malformed PinX value."""
    path = vsdx_copy("test1.vsdx")
    with vsdx.VisioFile(path) as vis:
        shape = vis.pages[0].all_shapes[0]
        shape.set_cell_value("PinX", "not-a-number")
        out = str(tmp_path / "malformed.vsdx")
        vis.save_vsdx(out)
    return out


@pytest.fixture
def absent_pinx_path(vsdx_copy, tmp_path):
    """A copy of test1.vsdx whose first shape has no PinX cell at all."""
    path = vsdx_copy("test1.vsdx")
    with vsdx.VisioFile(path) as vis:
        shape = vis.pages[0].all_shapes[0]
        cell = shape.xml.find(f"{namespace}Cell[@N='PinX']")
        assert cell is not None
        shape.xml.remove(cell)
        out = str(tmp_path / "absent.vsdx")
        vis.save_vsdx(out)
    return out


def test_malformed_geometry_value_raises_with_cell_and_raw_value(malformed_pinx_path):
    with vsdx.VisioFile(malformed_pinx_path) as vis:
        shape = vis.pages[0].all_shapes[0]
        with pytest.raises(ValueError, match=r"PinX.*not-a-number"):
            _ = shape.x


def test_malformed_value_raises_from_bounds(malformed_pinx_path):
    with vsdx.VisioFile(malformed_pinx_path) as vis:
        shape = vis.pages[0].all_shapes[0]
        with pytest.raises(ValueError, match="PinX"):
            _ = shape.bounds


def test_absent_value_remains_none(absent_pinx_path):
    with vsdx.VisioFile(absent_pinx_path) as vis:
        shape = vis.pages[0].all_shapes[0]
        assert shape.x is None  # absent is distinct from malformed and from 0.0


def test_page_dimension_rejects_malformed_value(vsdx_copy):
    path = vsdx_copy("test1.vsdx")
    with vsdx.VisioFile(path) as vis:
        page = vis.pages[0]
        with pytest.raises(ValueError):
            page._pagesheet_cell("PageWidth").attrib["V"] = "wide"
            _ = page.width
