"""Building a package to test against: a fixture with one thing changed, or an archive from nothing.

A test that breaks a fixture in one specific way is only testing that way while
the text it edits is still in the file. `str.replace` on text that has moved
substitutes nothing and raises nothing, so the test goes on passing, against a
package with no defect in it. Every substitution here asserts it found its mark
first, which is what the copies of this loop scattered through the suite mostly
did not.

Nothing here imports `vsdx`; see the package docstring.
"""

from __future__ import annotations

import copy
import pathlib
import struct
import zipfile
import zlib

__all__ = ["Edit", "append_member", "make_package", "rewritten", "understated"]

# What one member may have done to it. A `(old, new)` pair substitutes once and
# fails if `old` is not there; `bytes` replaces the member outright, for a part
# swapped for something the test generates; `None` drops it from the archive.
Edit = tuple[str, str] | tuple[bytes, bytes] | bytes | None


def rewritten(
    source: str,
    destination: str,
    edits: dict[str, Edit],
    *,
    added: dict[str, bytes] | None = None,
    renamed: dict[str, str] | None = None,
) -> str:
    """Copy the package at `source` to `destination`, changing what `edits` names.

    Members keep their order and their compression, so the result differs from
    the fixture only in what was asked for. `added` writes new members after the
    copied ones; `renamed` maps a member to the name it is written under, which
    is how a part name gains a character that has to be percent-encoded to be
    referred to.

    Every key of `edits` and `renamed` has to name a member of `source`. A key
    that does not is the same failure the substitution guard exists for - the
    part was renamed, the edit now applies to nothing, and the test goes on
    asserting against an unmodified package.
    """
    added = added or {}
    renamed = renamed or {}
    with zipfile.ZipFile(source) as original:
        unknown = sorted((set(edits) | set(renamed)) - set(original.namelist()))
        assert not unknown, f"{unknown} are not members of {source}; the fixture has changed"
        with zipfile.ZipFile(destination, "w") as rewrite:
            for entry in original.infolist():
                edit = edits.get(entry.filename)
                if entry.filename in edits and edit is None:
                    continue  # drop the member entirely
                data = original.read(entry.filename)
                if isinstance(edit, bytes):
                    data = edit
                elif edit is not None:
                    data = _substituted(data, edit, entry.filename)
                # A copy, because `writestr` rewrites the ZipInfo it is handed:
                # header offset, and flag bits from 0x6 to 0x800, which strips
                # the data-descriptor flag every member of these fixtures
                # carries. Hand it the source's own and the next read from that
                # archive raises `BadZipFile: Bad CRC-32`. Correct today only
                # because every member is read before any is written, and no
                # test can see that ordering become load-bearing, because the
                # corrupted handle never leaves this function.
                written = copy.copy(entry)
                written.filename = renamed.get(entry.filename, entry.filename)
                rewrite.writestr(written, data)
            for name, payload in added.items():
                rewrite.writestr(name, payload)
    return destination


def _substituted(data: bytes, edit: tuple[str, str] | tuple[bytes, bytes], member: str) -> bytes:
    """Substitute once, or fail saying the fixture has changed.

    Takes the pair as `str` or as `bytes`. Most of these edits read better
    against the XML as text, but a part holding a percent-encoded name or a
    non-UTF-8 byte is easier to state as bytes, and decoding it to make the edit
    then re-encoding is a second chance to change something nobody asked to
    change.
    """
    old, new = edit
    if isinstance(old, bytes):
        assert old in data, f"{old!r} not found in {member}; the fixture has changed"
        return data.replace(old, new, 1)  # type: ignore[arg-type]
    text = data.decode("utf-8")
    assert old in text, f"{old!r} not found in {member}; the fixture has changed"
    return text.replace(old, new, 1).encode("utf-8")  # type: ignore[arg-type]


def make_package(path: str, members: dict[str, bytes]) -> str:
    """Write an archive of exactly `members`, and nothing that makes it a document.

    For the tests that are about the zip container rather than about Visio: a
    differ comparing two binary members, a reader refusing an archive that
    declares more entries than it has. Mark those `allow_invalid_package`; the
    result is not a drawing, and the structural validator will say so.
    """
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return path


def append_member(path: str, name: str, data: bytes) -> str:
    with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, data)
    return path


# Offsets of the CRC and the uncompressed-size field inside each of the two
# headers that carry them. Patching by offset rather than by searching for the
# value: under ZIP_STORED the compressed and uncompressed sizes are equal, so a
# search finds the size four times and rewrites two fields nobody asked about.
_LOCAL_CRC, _LOCAL_SIZE = 14, 22
_CENTRAL_CRC, _CENTRAL_SIZE = 16, 24


def understated(path: str, member: str, payload: bytes, declared: int, *, consistent_crc: bool = False) -> str:
    """An archive of one member whose headers understate how much it holds.

    The whole point of the package size caps is that they are applied to sizes
    the central directory declares, and an archive is free to declare anything.
    What stops that being a hole is that `ZipFile` will not deliver more of a
    member than the member says it has: it truncates the output at `file_size`
    and then fails the CRC. This builds the archive that says so.

    `consistent_crc` also rewrites the CRC to match the truncated output, which
    is the stronger case: nothing raises, and the reader still gets exactly
    `declared` bytes.
    """
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, payload)
        local = archive.infolist()[0].header_offset

    raw = bytearray(pathlib.Path(path).read_bytes())
    central = raw.rfind(b"PK\x01\x02")
    assert central != -1, "the archive has no central directory record"
    assert raw[local : local + 4] == b"PK\x03\x04", "the local header is not where the index said it was"

    for base, crc_at, size_at in ((local, _LOCAL_CRC, _LOCAL_SIZE), (central, _CENTRAL_CRC, _CENTRAL_SIZE)):
        found = struct.unpack_from("<I", raw, base + size_at)[0]
        assert found == len(payload), f"expected the size {len(payload)} at offset {base + size_at}, found {found}"
        struct.pack_into("<I", raw, base + size_at, declared)
        if consistent_crc:
            found_crc = struct.unpack_from("<I", raw, base + crc_at)[0]
            assert found_crc == zlib.crc32(payload), f"expected the payload's CRC at offset {base + crc_at}"
            struct.pack_into("<I", raw, base + crc_at, zlib.crc32(payload[:declared]))

    pathlib.Path(path).write_bytes(bytes(raw))
    return path
