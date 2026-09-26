"""`Document.filename` is read-only, and a plain save goes back to the file opened (#116)."""

import os
from pathlib import Path

import pytest

from vsdxkit.document import Document
from vsdxkit.shapes import Shape


def _edit(document: Document, text: str) -> None:
    shape = document.pages[0].shapes.by_text("Shape A")
    assert isinstance(shape, Shape)
    shape.text = text


def test_a_plain_save_writes_back_over_the_file_opened(vsdx_copy):
    """Fails if `save()` with no target stops going to the source, or returns another path."""
    source = vsdx_copy("test8_simple_connector.vsdx")
    document = Document.open(source)
    _edit(document, "In place")

    written = document.save()

    assert written == Path(os.path.abspath(source))
    assert document.filename == source
    reopened = Document.open(source)
    assert reopened.pages[0].shapes.by_text("In place") is not None


def test_assigning_filename_is_refused_and_redirects_nothing(vsdx_copy, tmp_path):
    """Fails if `document.filename = ...` is accepted, or if it still steers the next plain save.

    0.x code set `filename` to point a later `save()` somewhere else. That is
    `save(target)` now, and the assignment raises rather than being ignored.
    """
    source = vsdx_copy("test8_simple_connector.vsdx")
    other = tmp_path / "other.vsdx"
    document = Document.open(source)
    _edit(document, "Stays home")

    with pytest.raises(AttributeError):
        document.filename = str(other)  # type: ignore[misc]

    assert document.filename == source
    document.save()
    assert not other.exists()
    assert Document.open(source).pages[0].shapes.by_text("Stays home") is not None


def test_save_target_is_how_to_write_elsewhere(vsdx_copy, tmp_path):
    """Fails if a named target stops leaving the source untouched."""
    source = vsdx_copy("test8_simple_connector.vsdx")
    with open(source, "rb") as handle:
        original = handle.read()
    document = Document.open(source)
    _edit(document, "Elsewhere")

    written = document.save(tmp_path / "elsewhere.vsdx")

    assert written == tmp_path / "elsewhere.vsdx"
    assert Document.open(str(written)).pages[0].shapes.by_text("Elsewhere") is not None
    with open(source, "rb") as handle:
        assert handle.read() == original
