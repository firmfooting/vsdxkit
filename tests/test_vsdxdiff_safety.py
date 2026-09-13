"""VisioFileDiff must not delete beside the source and must not hide binary changes."""

import os

import pytest
from helpers.broken_package import make_package

from vsdx.vsdxdiff import VisioFileDiff

# Every package here is a two-member archive built to exercise the differ's
# byte comparison. There is no document in them to have structural defects.
pytestmark = pytest.mark.allow_invalid_package

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def test_same_stem_directory_is_untouched(tmp_path):
    """Comparing sample.vsdx must not delete a pre-existing sample/ directory."""
    document = str(tmp_path / "sample.vsdx")
    other = str(tmp_path / "other.vsdx")
    make_package(document, {"[Content_Types].xml": b"<Types/>"})
    make_package(other, {"[Content_Types].xml": b"<Types/>"})

    keep = tmp_path / "sample"
    keep.mkdir()
    (keep / "keep.txt").write_text("precious user data", encoding="utf-8")

    VisioFileDiff(document, other)

    assert keep.is_dir(), "same-stem directory was deleted"
    assert (keep / "keep.txt").read_text(encoding="utf-8") == "precious user data"


def test_different_binary_members_are_reported_as_changed(tmp_path):
    """Two different undecodable members must surface as a change, not compare equal."""
    document = str(tmp_path / "one.vsdx")
    other = str(tmp_path / "two.vsdx")
    make_package(document, {"custom/binary.dat": b"\xff\xfe\x00one"})
    make_package(other, {"custom/binary.dat": b"\xff\xfe\x00two"})

    file_diff = VisioFileDiff(document, other)
    assert "custom/binary.dat" in file_diff.diffs, "changed binary member not reported"


def test_equal_text_members_with_different_line_endings_do_not_report_change(tmp_path):
    """CRLF-vs-LF packaging differences are not content changes (universal newlines)."""
    document = str(tmp_path / "crlf.vsdx")
    other = str(tmp_path / "lf.vsdx")
    make_package(document, {"visio/document.xml": b"<xml>\r\n  <page/>\r\n</xml>\r\n"})
    make_package(other, {"visio/document.xml": b"<xml>\n  <page/>\n</xml>\n"})

    file_diff = VisioFileDiff(document, other)
    assert file_diff.diffs == {}


def test_equal_binary_members_do_not_report_change(tmp_path):
    document = str(tmp_path / "one.vsdx")
    other = str(tmp_path / "two.vsdx")
    payload = os.urandom(64)
    make_package(document, {"custom/binary.dat": payload})
    make_package(other, {"custom/binary.dat": payload})

    file_diff = VisioFileDiff(document, other)
    assert file_diff.compare_members() is True
