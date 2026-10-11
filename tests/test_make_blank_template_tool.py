"""`tools/make_blank_template.py --empty-page` removes its temporary directory, also when it fails (#474)."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "tests" / "fixtures" / "com_reference" / "s01_autoconnect_right.vsdx"


def _tool():
    spec = importlib.util.spec_from_file_location("make_blank_template", ROOT / "tools" / "make_blank_template.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_empty_page_leaves_no_temporary_directory(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    assert _tool().main([str(RAW), str(tmp_path / "out.vsdx"), "--empty-page"]) == 0
    assert list(scratch.iterdir()) == []


def test_empty_page_failure_leaves_no_temporary_directory(tmp_path, monkeypatch):
    from vsdxkit.document import Document

    def boom(self, *args, **kwargs):
        raise RuntimeError("save failed")

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    monkeypatch.setattr(Document, "save", boom)
    with pytest.raises(RuntimeError):
        _tool().main([str(RAW), str(tmp_path / "out.vsdx"), "--empty-page"])
    assert list(scratch.iterdir()) == []


def test_plain_run_creates_no_temporary_directory(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("a run without --empty-page needs no temporary directory")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", boom)
    monkeypatch.setattr(tempfile, "mkdtemp", boom)
    assert _tool().main([str(RAW), str(tmp_path / "out.vsdx")]) == 0
