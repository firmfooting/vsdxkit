"""Tests for findings from reviews of merged PRs (fix pass, September 2026)."""

import os
import struct
import zipfile

import pytest

import vsdx
from vsdx import PackageLimitError, VisioFile
from vsdx.vsdxdiff import VisioFileDiff

basedir = os.path.dirname(os.path.realpath(__file__))


def _make_vsdx(path: str, members: dict[str, bytes]) -> None:
    """Build a minimal archive; VisioFileDiff treats any zip as readable."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def _copy(name: str, tmp_path) -> str:
    source = os.path.join(basedir, name)
    destination = os.path.join(str(tmp_path), name)
    with open(source, "rb") as reader, open(destination, "wb") as writer:
        writer.write(reader.read())
    return destination


def test_eocd_preflight_rejects_declared_entry_overflow(tmp_path):
    """An EOCD declaring more entries than max_members is rejected before ZipFile runs."""
    path = _copy("test1.vsdx", tmp_path)
    limits = vsdx.PackageLimits(max_members=20)
    VisioFile._preflight_eocd(path, limits)  # real fixture declares 14 < 20: passes

    with open(path, "rb") as handle:
        payload = bytearray(handle.read())
    eocd = payload.rfind(b"PK\x05\x06")
    assert eocd != -1
    payload[eocd + 10 : eocd + 12] = struct.pack("<H", 50_000)
    lying = os.path.join(str(tmp_path), "lying.vsdx")
    with open(lying, "wb") as handle:
        handle.write(payload)

    with pytest.raises(PackageLimitError) as excinfo:
        VisioFile(lying, limits=limits)
    assert excinfo.value.reason == "member_count"


@pytest.mark.allow_invalid_package  # the package is padded past the cap on purpose
def test_diff_rejects_member_above_cap(tmp_path):
    """A member declaring more than the diff cap is refused, not inflated."""
    document = str(tmp_path / "big.vsdx")
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("visio/pages/pages.xml", b"<xml/>")

    # lie about the member's declared uncompressed size in the central directory
    with open(document, "rb") as reader:
        payload = bytearray(reader.read())
    cd = payload.find(b"PK\x01\x02")
    struct.pack_into("<I", payload, cd + 24, VisioFileDiff.MAX_MEMBER_BYTES + 1)
    over = os.path.join(str(tmp_path), "over.vsdx")
    with open(over, "wb") as handle:
        handle.write(payload)

    with pytest.raises(PackageLimitError) as excinfo:
        VisioFileDiff.extract_file_data(over)
    assert excinfo.value.reason == "member_size"


def test_zip64_low_count_with_real_directory_bounds_is_rejected(tmp_path):
    """ZIP64 EOCD with a falsified low count and real directory bounds is caught.

    Third-round review of #254: the preflight originally read only the ZIP64
    entry count and bounded its scan with the classic size/offset fields —
    which sit at 0xFFFFFFFF sentinels when ZIP64 is in play — so a low
    falsified count ended the walk before the real directory was examined.
    """
    path = _copy("test1.vsdx", tmp_path)
    with open(path, "rb") as handle:
        payload = bytearray(handle.read())
    eocd = payload.rfind(b"PK\x05\x06")
    real_cd_size = int.from_bytes(payload[eocd + 12 : eocd + 16], "little")
    real_cd_offset = int.from_bytes(payload[eocd + 16 : eocd + 20], "little")
    payload[eocd + 10 : eocd + 12] = struct.pack("<H", 0xFFFF)  # sentinel count
    payload[eocd + 12 : eocd + 16] = struct.pack("<I", 0xFFFFFFFF)  # sentinel size
    payload[eocd + 16 : eocd + 20] = struct.pack("<I", 0xFFFFFFFF)  # sentinel offset
    # ZIP64 EOCD inserted before the classic one: count lied low (5), real bounds
    zip64_eocd = struct.pack(
        "<IQHHIIQQQQ",
        0x06064B50,  # signature
        44,  # size of remainder of this record
        45,  # version made by
        45,  # version needed
        0,  # this disk
        0,  # directory start disk
        14,  # entries on this disk
        5,  # total entries: the lie
        real_cd_size,
        real_cd_offset,
    )
    payload = payload[:eocd] + zip64_eocd + payload[eocd:]
    lying = os.path.join(str(tmp_path), "zip64-low-count.vsdx")
    with open(lying, "wb") as handle:
        handle.write(payload)

    with pytest.raises(PackageLimitError) as excinfo:
        VisioFile(lying, limits=vsdx.PackageLimits(max_members=10))
    assert excinfo.value.reason == "member_count"


def test_low_declared_count_with_swollen_directory_is_rejected(tmp_path):
    """A low classic count cannot hide a directory holding more real entries."""
    path = str(tmp_path / "many.vsdx")
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(30):
            archive.writestr(f"part{index}.xml", b"<x/>")
    with open(path, "rb") as handle:
        payload = bytearray(handle.read())
    eocd = payload.rfind(b"PK\x05\x06")
    payload[eocd + 10 : eocd + 12] = struct.pack("<H", 3)  # declared count lied low

    with pytest.raises(PackageLimitError) as excinfo:
        VisioFile(path, limits=vsdx.PackageLimits(max_members=20))
    assert excinfo.value.reason == "member_count"


def test_zero_declared_count_with_nonempty_directory_is_rejected(tmp_path):
    """A declared zero count must not skip the walk while ZipFile parses by size.

    Fourth-round review of #255: the preflight returned early on a zero
    count, but ZipFile parses entries by central-directory size, restoring
    the memory-exhaustion path the preflight exists to prevent.
    """
    path = str(tmp_path / "zero.vsdx")
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(30):
            archive.writestr(f"part{index}.xml", b"<x/>")
    with open(path, "rb") as handle:
        payload = bytearray(handle.read())
    eocd = payload.rfind(b"PK\x05\x06")
    payload[eocd + 10 : eocd + 12] = struct.pack("<H", 0)  # declared count zero

    with pytest.raises(PackageLimitError) as excinfo:
        VisioFile(path, limits=vsdx.PackageLimits(max_members=20))
    assert excinfo.value.reason == "member_count"


def test_eocd_preflight_reads_zip64_entry_count(tmp_path):
    """A ZIP64 locator/EOCD replaces classic values even without a sentinel count."""
    path = _copy("test1.vsdx", tmp_path)
    with open(path, "rb") as handle:
        payload = bytearray(handle.read())
    eocd = payload.rfind(b"PK\x05\x06")
    real_cd_size = int.from_bytes(payload[eocd + 12 : eocd + 16], "little")
    real_cd_offset = int.from_bytes(payload[eocd + 16 : eocd + 20], "little")
    # real ZIP64 layout: ZIP64 EOCD, then locator pointing at it, then classic EOCD
    z64_eocd = struct.pack(
        "<IQHHIIQQQQ",
        0x06064B50,  # signature
        44,  # size of remainder of this record
        45,  # version made by
        45,  # version needed
        0,  # this disk
        0,  # directory start disk
        14,  # entries on this disk
        40000,  # total entries: the lie
        real_cd_size,
        real_cd_offset,
    )
    z64_offset = eocd  # ZIP64 EOCD placed at the classic EOCD's position
    locator = struct.pack("<IIQH", 0x07064B50, 0, z64_offset, 1)
    payload = payload[:eocd] + z64_eocd + locator + payload[eocd:]
    new_eocd = payload.rfind(b"PK\x05\x06")
    payload[new_eocd + 10 : new_eocd + 12] = struct.pack("<H", 0xFFFF)  # classic sentinel

    lying = os.path.join(str(tmp_path), "zip64-lying.vsdx")
    with open(lying, "wb") as handle:
        handle.write(payload)

    with pytest.raises(PackageLimitError) as excinfo:
        VisioFile(lying, limits=vsdx.PackageLimits(max_members=20))
    assert excinfo.value.reason == "member_count"
    assert "40000" in str(excinfo.value)


def test_get_type_hints_resolves_connect_to_class():
    """get_type_hints must resolve the quoted annotation to the real class."""
    import typing

    from vsdx.connectors import Connect
    from vsdx.shapes import Shape

    hints = typing.get_type_hints(Shape.connects.fget)
    assert hints["return"].__args__[0] is Connect


def test_diff_chunk_boundary_crlf_is_one_newline(tmp_path):
    """A CRLF pair split across the 1 MiB chunk boundary must not double-count."""

    document = str(tmp_path / "split.vsdx")
    other = str(tmp_path / "plain.vsdx")
    # pad so the CR is the final byte of chunk one and the LF opens chunk two
    padding = b" " * (VisioFileDiff._CHUNK - len(b"<xml>") - 1)
    payload = b"<xml>" + padding + b"\r\n</xml>"
    assert payload[VisioFileDiff._CHUNK - 1 : VisioFileDiff._CHUNK + 1] == b"\r\n"
    _make_vsdx(document, {"visio/document.xml": payload})
    _make_vsdx(other, {"visio/document.xml": b"<xml>" + padding + b"\n</xml>"})

    file_diff = VisioFileDiff(document, other)
    assert file_diff.diffs == {}
    # and the split line count matches a plain-LF document exactly
    assert file_diff.contents_a == file_diff.contents_b


def test_diff_incomplete_utf8_at_eof_is_binary(tmp_path):
    """A member ending in an incomplete multibyte sequence hashes as binary."""
    document = str(tmp_path / "truncated.vsdx")
    other = str(tmp_path / "truncated2.vsdx")
    # valid UTF-8 until a trailing lead byte with no continuation, which only
    # the final=True flush rejects
    _make_vsdx(document, {"custom/binary.dat": b"ok\xc3"})
    _make_vsdx(other, {"custom/binary.dat": b"ok\xc4"})

    file_diff = VisioFileDiff(document, other)
    assert "custom/binary.dat" in file_diff.diffs
    assert file_diff.contents_a["custom/binary.dat"][0].startswith("binary sha256:")
    assert file_diff.contents_a["custom/binary.dat"] != file_diff.contents_b["custom/binary.dat"]
