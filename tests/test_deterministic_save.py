"""A deterministic save writes the same bytes whatever the clock, the platform, the zlib build or the hash seed."""

import hashlib
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from vsdxkit.document import Document
from vsdxkit.shape_kind import ShapeKind

HERE = Path(__file__).resolve().parent


def _document() -> Document:
    document = Document.new()
    document.pages[0].create_shape(ShapeKind.PROCESS, x=2.0, y=3.0, text="Step")
    return document


def test_zipfile_stamps_the_clock_and_the_host_on_a_member_given_by_name(monkeypatch):
    """The stdlib behaviour the deterministic writer exists to avoid (spec section 11, item 7)."""
    stamps = []
    for moment in (1_000_000_000, 1_500_000_000):
        monkeypatch.setattr(zipfile.time, "localtime", lambda _t=None, moment=moment: time.gmtime(moment))
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("a.xml", b"<a/>")
        stamps.append((buffer.getvalue(), archive.infolist()[0].create_system))
    assert stamps[0][0] != stamps[1][0], "the date_time of a str-named member follows time.localtime"
    assert stamps[0][1] == (0 if sys.platform == "win32" else 3), "create_system follows the platform"


def test_a_deterministic_save_does_not_follow_the_clock(tmp_path, monkeypatch):
    first = _document().save(tmp_path / "a.vsdx", deterministic=True).read_bytes()
    monkeypatch.setattr(zipfile.time, "localtime", lambda _t=None: time.gmtime(1_900_000_000))
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1234567890")
    second = _document().save(tmp_path / "b.vsdx", deterministic=True).read_bytes()
    assert first == second


def test_every_member_has_the_same_fixed_form(tmp_path):
    path = _document().save(tmp_path / "a.vsdx", deterministic=True)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
    names = [i.filename for i in infos]
    assert names[0] == "[Content_Types].xml"
    assert names[1:] == sorted(names[1:])
    for info in infos:
        assert (info.date_time, info.create_system, info.external_attr, info.flag_bits) == (
            (1980, 1, 1, 0, 0, 0),
            3,
            0o600 << 16,
            0,
        )
        assert (info.compress_type, info.extra, info.comment) == (zipfile.ZIP_STORED, b"", b"")


def test_a_deterministic_save_reads_back_as_the_same_document(tmp_path):
    path = _document().save(tmp_path / "a.vsdx", deterministic=True)
    reread = Document.open(path)
    assert [s.text for s in reread.pages[0].shapes] == ["Step"]


def test_the_default_save_is_still_the_compressed_archive(tmp_path):
    path = _document().save(tmp_path / "a.vsdx")
    with zipfile.ZipFile(path) as archive:
        assert zipfile.ZIP_DEFLATED in {i.compress_type for i in archive.infolist()}


def test_the_bytes_do_not_depend_on_the_hash_seed(tmp_path):
    code = (
        "import hashlib, sys\n"
        "from vsdxkit.document import Document\n"
        "from vsdxkit.shape_kind import ShapeKind\n"
        "d = Document.new()\n"
        "d.pages[0].create_shape(ShapeKind.PROCESS, x=2.0, y=3.0, text='Step')\n"
        "print(hashlib.sha256(d.save(sys.argv[1], deterministic=True).read_bytes()).hexdigest())\n"
    )
    paths = os.pathsep.join([str(HERE.parent / "src")])
    digests = {
        subprocess.run(
            [sys.executable, "-c", code, str(tmp_path / f"{seed}.vsdx")],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": paths},
            check=True,
        ).stdout
        for seed in ("0", "1", "2", "random")
    }
    assert len(digests) == 1


def test_a_new_document_with_no_target_has_nowhere_to_save(tmp_path):
    from vsdxkit.errors import InvalidOperationError

    with pytest.raises(InvalidOperationError, match="pass target"):
        Document.new().save()


GOLDEN = HERE / "fixtures" / "deterministic_save.sha256"
"""The digest of the document above, written once and read by every platform in the CI matrix (spec section 4.11)."""


def test_the_bytes_equal_the_digest_every_platform_is_held_to(tmp_path):
    """Linux, Windows and macOS each save the same document and compare with the one committed digest."""
    digest = hashlib.sha256(_document().save(tmp_path / "a.vsdx", deterministic=True).read_bytes()).hexdigest()
    assert digest == GOLDEN.read_text(encoding="utf-8").strip(), (
        "a platform that disagrees is a determinism defect; rewrite the digest only when the template or writer changed on purpose"
    )
