"""Regression tests for save_vsdx destination and repeat-save handling."""

import os
import zipfile
from pathlib import Path

import pytest

from vsdxkit import VisioFile

BASE = "test8_simple_connector.vsdx"


def test_save_vsdx_no_filename_saves_in_place(vsdx_copy):
    src = vsdx_copy(BASE)
    with VisioFile(src) as vis:
        shape = vis.pages[0].find_shape_by_text("Shape A")
        assert shape is not None
        shape.text = "Renamed A"
        vis.save_vsdx()
    with VisioFile(src) as vis:
        assert vis.pages[0].find_shape_by_text("Renamed A") is not None


def test_save_vsdx_appends_vsdx_suffix(vsdx_copy):
    src = vsdx_copy(BASE)
    out = str(src)[:-5] + "_out"
    with VisioFile(src) as vis:
        vis.save_vsdx(out)

    assert os.path.exists(out + ".vsdx")
    with VisioFile(out + ".vsdx") as vis:
        assert len(vis.pages) == 1


def test_save_vsdx_accepts_uppercase_suffix(vsdx_copy):
    src = vsdx_copy(BASE)
    destination = Path(src).with_name("UPPER.VSDX")

    with VisioFile(src) as vis:
        vis.save_vsdx(str(destination))

    assert destination.exists()
    assert not Path(f"{destination}.vsdx").exists()


def test_save_vsdx_creates_nested_parent_directories(vsdx_copy, tmp_path):
    src = vsdx_copy(BASE)
    destination = tmp_path / "nested" / "deeper" / "saved.vsdx"

    with VisioFile(src) as vis:
        vis.save_vsdx(str(destination))

    with VisioFile(str(destination)) as vis:
        assert len(vis.pages) == 1


def test_save_vsdx_refuses_an_empty_package(vsdx_copy, tmp_path):
    src = vsdx_copy(BASE)
    destination = tmp_path / "empty.vsdx"

    with VisioFile(src) as vis:
        vis.zip_file_contents.clear()
        with pytest.raises(ValueError, match="empty package"):
            vis.save_vsdx(str(destination))

    assert not destination.exists()


def test_save_vsdx_twice_preserves_unmodified_parts(vsdx_copy):
    src = vsdx_copy(BASE)
    with zipfile.ZipFile(src) as archive:
        root_rels = archive.read("_rels/.rels")

    with VisioFile(src) as vis:
        vis.save_vsdx()
        vis.save_vsdx()

    with zipfile.ZipFile(src) as archive:
        assert archive.read("_rels/.rels") == root_rels
    with VisioFile(src) as vis:
        assert len(vis.pages) == 1


def test_failed_in_place_save_keeps_original_bytes(vsdx_copy, monkeypatch):
    src = vsdx_copy(BASE)
    original = Path(src).read_bytes()

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("injected ZIP write failure")

    with VisioFile(src) as vis:
        monkeypatch.setattr(zipfile.ZipFile, "writestr", fail_write)
        with pytest.raises(RuntimeError, match="injected ZIP write failure"):
            vis.save_vsdx()

    assert Path(src).read_bytes() == original


def test_two_named_saves_keep_archive_paths_relative(vsdx_copy):
    src = vsdx_copy(BASE)
    first = str(Path(src).with_name("first.vsdx"))
    second = str(Path(src).with_name("second.vsdx"))
    with zipfile.ZipFile(src) as archive:
        source_names = set(archive.namelist())

    with VisioFile(src) as vis:
        vis.save_vsdx(first)
        vis.save_vsdx(second)

    with zipfile.ZipFile(second) as archive:
        assert set(archive.namelist()) == source_names
    with VisioFile(second) as vis:
        assert len(vis.pages) == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not meaningful on Windows")
def test_new_named_save_preserves_source_mode(vsdx_copy):
    src = Path(vsdx_copy(BASE))
    src.chmod(0o640)
    destination = src.with_name("mode-copy.vsdx")

    with VisioFile(str(src)) as vis:
        vis.save_vsdx(str(destination))

    assert destination.stat().st_mode & 0o777 == 0o640


MACRO_BASE = "diagram_with_macro.vsdm"


def _vba_bytes(path) -> bytes:
    with zipfile.ZipFile(str(path)) as archive:
        return archive.read("visio/vbaProject.bin")


def test_macro_package_saves_to_vsdm(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    destination = Path(src).with_name("out.vsdm")

    with VisioFile(src) as vis:
        vis.save_vsdx(str(destination))

    assert destination.exists()
    assert _vba_bytes(destination) == _vba_bytes(src)


def test_macro_package_refuses_a_vsdx_destination(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    destination = Path(src).with_name("out.vsdx")

    with VisioFile(src) as vis:
        with pytest.raises(ValueError, match="macro-enabled"):
            vis.save_vsdx(str(destination))

    assert not destination.exists()


def test_drawing_package_refuses_a_vsdm_destination(vsdx_copy):
    src = vsdx_copy(BASE)
    destination = Path(src).with_name("out.vsdm")

    with VisioFile(src) as vis:
        with pytest.raises(ValueError, match="macro-enabled"):
            vis.save_vsdx(str(destination))

    assert not destination.exists()


def test_macro_package_gets_the_vsdm_suffix_when_none_is_given(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    destination = Path(src).with_name("suffixless")

    with VisioFile(src) as vis:
        vis.save_vsdx(str(destination))

    assert destination.with_suffix(".vsdm").exists()
    assert not destination.with_suffix(".vsdx").exists()


def test_macro_package_accepts_an_uppercase_vsdm_suffix(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    destination = Path(src).with_name("UPPER.VSDM")

    with VisioFile(src) as vis:
        vis.save_vsdx(str(destination))

    assert destination.exists()


def test_macro_package_saves_in_place(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    original = _vba_bytes(src)

    with VisioFile(src) as vis:
        vis.save_vsdx()

    assert Path(src).exists()
    assert _vba_bytes(src) == original


def test_in_place_save_refuses_a_mismatched_source_name(vsdx_copy):
    """A renamed .vsdm must not be written back out under its .vsdx name.

    `save_vsdx()` with no argument is the commonest call, and skipping the
    check there would let exactly the package this fix is about reach disk.
    """
    src = Path(vsdx_copy(MACRO_BASE))
    renamed = src.with_name("renamed.vsdx")
    src.rename(renamed)
    before = renamed.read_bytes()

    with VisioFile(str(renamed)) as vis:
        with pytest.raises(ValueError, match="macro-enabled"):
            vis.save_vsdx()

    assert renamed.read_bytes() == before
