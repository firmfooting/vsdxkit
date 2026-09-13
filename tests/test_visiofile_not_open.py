"""VisioFileNotOpen must be catchable with normal exception handling."""

import os

import pytest

import vsdxkit


def test_save_after_close_raises_catchable_exception(vsdx_copy, tmp_path):
    path = vsdx_copy("test1.vsdx")
    with open(path, "rb") as handle:
        original_bytes = handle.read()
    visio = vsdxkit.VisioFile(path)
    visio.close_vsdx()
    destination = os.path.join(str(tmp_path), "ignored.vsdx")
    # the regression is precisely that a plain `except Exception` handler matches
    with pytest.raises(Exception) as excinfo:
        visio.save_vsdx(destination)
    assert isinstance(excinfo.value, vsdxkit.VisioFileNotOpen)
    assert not os.path.exists(destination)  # nothing was written
    with open(path, "rb") as handle:
        assert handle.read() == original_bytes  # source untouched


def test_not_open_is_exported_and_derives_from_exception():
    assert issubclass(vsdxkit.VisioFileNotOpen, Exception)
