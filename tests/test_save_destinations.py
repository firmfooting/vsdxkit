"""Regression tests for save destination and repeat-save handling."""

import os
import zipfile
from pathlib import Path

import pytest

from vsdxkit.document import Document

BASE = "test8_simple_connector.vsdx"


def test_save_vsdx_no_filename_saves_in_place(vsdx_copy):
    src = vsdx_copy(BASE)
    vis = Document.open(src)
    shape = vis.pages[0].shapes.by_text("Shape A")
    assert shape is not None
    shape.text = "Renamed A"
    vis.save()
    vis = Document.open(src)
    assert vis.pages[0].shapes.by_text("Renamed A") is not None


def test_save_vsdx_appends_vsdx_suffix(vsdx_copy):
    src = vsdx_copy(BASE)
    out = str(src)[:-5] + "_out"
    vis = Document.open(src)
    vis.save(out)

    assert os.path.exists(out + ".vsdx")
    vis = Document.open(out + ".vsdx")
    assert len(vis.pages) == 1


def test_save_vsdx_accepts_uppercase_suffix(vsdx_copy):
    src = vsdx_copy(BASE)
    destination = Path(src).with_name("UPPER.VSDX")

    vis = Document.open(src)
    vis.save(str(destination))

    assert destination.exists()
    assert not Path(f"{destination}.vsdx").exists()


def test_save_vsdx_creates_nested_parent_directories(vsdx_copy, tmp_path):
    src = vsdx_copy(BASE)
    destination = tmp_path / "nested" / "deeper" / "saved.vsdx"

    vis = Document.open(src)
    vis.save(str(destination))

    vis = Document.open(str(destination))
    assert len(vis.pages) == 1


def test_save_vsdx_refuses_an_empty_package(vsdx_copy, tmp_path):
    src = vsdx_copy(BASE)
    destination = tmp_path / "empty.vsdx"

    vis = Document.open(src)
    for name in vis._package.names():
        vis._package.remove(name)
    with pytest.raises(ValueError, match="empty package"):
        vis.save(str(destination))

    assert not destination.exists()


def test_save_vsdx_twice_preserves_unmodified_parts(vsdx_copy):
    src = vsdx_copy(BASE)
    with zipfile.ZipFile(src) as archive:
        root_rels = archive.read("_rels/.rels")

    vis = Document.open(src)
    vis.save()
    vis.save()

    with zipfile.ZipFile(src) as archive:
        assert archive.read("_rels/.rels") == root_rels
    vis = Document.open(src)
    assert len(vis.pages) == 1


def test_failed_in_place_save_keeps_original_bytes(vsdx_copy, monkeypatch):
    src = vsdx_copy(BASE)
    original = Path(src).read_bytes()

    def fail_write(*_args, **_kwargs):
        raise RuntimeError("injected ZIP write failure")

    vis = Document.open(src)
    monkeypatch.setattr(zipfile.ZipFile, "writestr", fail_write)
    with pytest.raises(RuntimeError, match="injected ZIP write failure"):
        vis.save()

    assert Path(src).read_bytes() == original


def test_two_named_saves_keep_archive_paths_relative(vsdx_copy):
    src = vsdx_copy(BASE)
    first = str(Path(src).with_name("first.vsdx"))
    second = str(Path(src).with_name("second.vsdx"))
    with zipfile.ZipFile(src) as archive:
        source_names = set(archive.namelist())

    vis = Document.open(src)
    vis.save(first)
    vis.save(second)

    with zipfile.ZipFile(second) as archive:
        assert set(archive.namelist()) == source_names
    vis = Document.open(second)
    assert len(vis.pages) == 1


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not meaningful on Windows")
def test_new_named_save_preserves_source_mode(vsdx_copy):
    src = Path(vsdx_copy(BASE))
    src.chmod(0o640)
    destination = src.with_name("mode-copy.vsdx")

    vis = Document.open(str(src))
    vis.save(str(destination))

    assert destination.stat().st_mode & 0o777 == 0o640


MACRO_BASE = "diagram_with_macro.vsdm"


def _vba_bytes(path) -> bytes:
    with zipfile.ZipFile(str(path)) as archive:
        return archive.read("visio/vbaProject.bin")


def test_macro_package_saves_to_vsdm(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    destination = Path(src).with_name("out.vsdm")

    vis = Document.open(src)
    vis.save(str(destination))

    assert destination.exists()
    assert _vba_bytes(destination) == _vba_bytes(src)


def test_macro_package_refuses_a_vsdx_destination(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    destination = Path(src).with_name("out.vsdx")

    vis = Document.open(src)
    with pytest.raises(ValueError, match="macro-enabled"):
        vis.save(str(destination))

    assert not destination.exists()


def test_drawing_package_refuses_a_vsdm_destination(vsdx_copy):
    src = vsdx_copy(BASE)
    destination = Path(src).with_name("out.vsdm")

    vis = Document.open(src)
    with pytest.raises(ValueError, match="macro-enabled"):
        vis.save(str(destination))

    assert not destination.exists()


def test_macro_package_gets_the_vsdm_suffix_when_none_is_given(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    destination = Path(src).with_name("suffixless")

    vis = Document.open(src)
    vis.save(str(destination))

    assert destination.with_suffix(".vsdm").exists()
    assert not destination.with_suffix(".vsdx").exists()


def test_macro_package_accepts_an_uppercase_vsdm_suffix(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    destination = Path(src).with_name("UPPER.VSDM")

    vis = Document.open(src)
    vis.save(str(destination))

    assert destination.exists()


def test_macro_package_saves_in_place(vsdx_copy):
    src = vsdx_copy(MACRO_BASE)
    original = _vba_bytes(src)

    vis = Document.open(src)
    vis.save()

    assert Path(src).exists()
    assert _vba_bytes(src) == original


def test_in_place_save_refuses_a_mismatched_source_name(vsdx_copy):
    """A renamed .vsdm must not be written back out under its .vsdx name.

    `save()` with no argument is the commonest call, and skipping the
    check there would let exactly the package this fix is about reach disk.
    """
    src = Path(vsdx_copy(MACRO_BASE))
    renamed = src.with_name("renamed.vsdx")
    src.rename(renamed)
    before = renamed.read_bytes()

    vis = Document.open(str(renamed))
    with pytest.raises(ValueError, match="macro-enabled"):
        vis.save()

    assert renamed.read_bytes() == before
