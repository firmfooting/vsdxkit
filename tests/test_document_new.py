"""Document.new(): a blank drawing from the template shipped in the package, with nothing of the machine that made the template."""

import os
import stat
import sys
import zipfile
from pathlib import Path

import pytest
from helpers.package_validator import validate_package

from vsdxkit import _media
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError, PackageLimitError
from vsdxkit.package import PackageLimits
from vsdxkit.shape_kind import ShapeKind


def test_a_new_document_is_one_empty_page_named_as_asked():
    document = Document.new(page_name="Overview")
    assert [page.name for page in document.pages] == ["Overview"]
    assert len(document.pages[0].shapes) == 0


def test_the_default_page_name_is_page_1():
    assert Document.new().pages[0].name == "Page-1"


def test_a_new_document_has_no_file_to_save_over():
    with pytest.raises(InvalidOperationError, match="pass target"):
        Document.new().save()


def test_a_saved_new_document_is_a_valid_package_that_opens_again(tmp_path):
    path = Document.new(page_name="Blank").save(tmp_path / "blank.vsdx")
    assert validate_package(str(path)) == ()
    assert [page.name for page in Document.open(path).pages] == ["Blank"]


def test_shapes_and_connectors_can_be_added_to_a_new_document(tmp_path):
    document = Document.new()
    page = document.pages[0]
    a = page.create_shape(ShapeKind.PROCESS, x=2.0, y=2.0, text="A")
    b = page.create_shape(ShapeKind.DECISION, x=5.0, y=2.0, text="B")
    page.connect(a, b)
    path = document.save(tmp_path / "two.vsdx")
    assert validate_package(str(path)) == ()
    assert len(Document.open(path).pages[0].connectors) == 1


def test_two_new_documents_share_nothing():
    first, second = Document.new(), Document.new()
    first.pages[0].create_shape(ShapeKind.PROCESS, x=1.0, y=1.0, text="only in the first")
    assert len(second.pages[0].shapes) == 0
    assert len(Document.new().pages[0].shapes) == 0


def test_the_template_carries_nothing_of_the_machine_that_saved_it():
    """Fails if a user name, a machine path, an address or a rendering of the page is left in the shipped template."""
    template = Path(_media.media_path(_media.BLANK))
    with zipfile.ZipFile(template) as archive:
        names = archive.namelist()
        assert "docProps/thumbnail.emf" not in names and "docProps/custom.xml" not in names
        for name in names:
            data = archive.read(name)
            for marker in (b"\\Users\\", b"C:\\", b"@", "\\Users\\".encode("utf-16-le"), "C:\\".encode("utf-16-le")):
                assert marker not in data, f"{name} contains {marker!r}"
        core = archive.read("docProps/core.xml").decode("utf-8")
    assert "<dc:creator></dc:creator>" in core
    assert "<cp:lastModifiedBy>" not in core or "<cp:lastModifiedBy></cp:lastModifiedBy>" in core
    assert core.count("2000-01-01T00:00:00Z") == core.count("</dcterms:") + core.count("</cp:lastPrinted>")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_a_new_document_saved_to_a_new_path_gets_the_mode_the_umask_allows(tmp_path):
    old = os.umask(0o022)
    try:
        path = Document.new().save(tmp_path / "blank.vsdx")
    finally:
        os.umask(old)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_saving_a_new_document_never_touches_the_process_umask(tmp_path, monkeypatch):
    def refuse(_mask):
        raise AssertionError("os.umask is process-wide state and must not be called")

    monkeypatch.setattr(os, "umask", refuse)
    path = Document.new().save(tmp_path / "blank.vsdx")
    assert path.exists()


def test_a_new_document_is_held_to_the_limits_it_was_given():
    with pytest.raises(PackageLimitError):
        Document.new(limits=PackageLimits(max_member_size=16))
