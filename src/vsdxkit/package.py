"""The package as a map from OPC part name to part value.

A `.vsdx` is an OPC package: a zip whose members are *parts*, addressed by a
part name that begins with a slash -- `/visio/document.xml`, `/_rels/.rels`,
`/[Content_Types].xml`. The archive spells the same thing without the slash,
and this library spells it a third way again, as an absolute filesystem path
under a directory that never existed on disk. Three spellings of one name are
three chances to look a part up and not find it.

`PackageStore` holds one spelling. A name that is not an OPC part name is
refused rather than repaired: a name without its leading slash is the archive's
spelling and belongs to the reader, a name with a backslash in it would
normalise onto some other part, and a `..` segment addresses something outside
the package. Each of those is a caller confusing two naming schemes, and the
useful thing to do with it is say so.

Parts are held as the bytes they arrived as. A part becomes a tree only when
something asks for its tree, and at that moment the store records the canonical
hash of the tree it just parsed. That baseline is what lets `read_bytes` answer
the question a byte-preserving save has to ask of every part: did anything
actually change? If the live tree still canonicalises to the baseline the part
reads back as the bytes it arrived as, spelling and all; if it does not, it
reads back as a fresh serialisation. Parsing a part and writing it straight
back is not the identity -- ElementTree rewrites the XML declaration, requotes
attributes and drops namespace declarations the part does not use -- so
"unchanged" has to mean unchanged, not re-serialised the same way.

The baseline is taken from the tree rather than from the original bytes on
purpose. A parse loses things a serialisation cannot put back, so a baseline
read off the bytes would call an untouched part changed and re-serialise it,
which is the one thing this is here to avoid.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .xmlio import parse_part, serialise_part

__all__ = [
    "BytesPart",
    "PackageLimitError",
    "PackageLimits",
    "PackageStore",
    "PartValue",
    "XmlPart",
    "canonical_hash",
    "read_archive_members",
]


# --------------------------------------------------------------------------
# load limits
# --------------------------------------------------------------------------


class PackageLimitError(OSError):
    """A package violated a load limit: size, member count, ratio, names or duplicates.

    ``reason`` is a stable slug (``member_size``, ``total_size``,
    ``member_count``, ``compression_ratio``, ``duplicate_member``,
    ``member_name``, ``limits_file``) so callers can branch by failure mode.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class PackageLimits:
    """Conservative caps applied while loading a package from disk.

    The defaults suit documents from unknown sources: a hostile or accidental
    archive is rejected well before it can exhaust process memory. Even at the
    caps the loader materialises at most ``max_total_uncompressed`` bytes
    (256 MiB by default); callers loading larger trusted documents should raise
    the caps explicitly via ``VisioFile(filename, limits=PackageLimits(...))``
    or a JSON file passed as ``limits_path`` with the same keys.
    """

    max_members: int = 512
    max_member_size: int = 64 * 1024 * 1024
    max_total_uncompressed: int = 256 * 1024 * 1024
    max_ratio: float = 100.0

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.max_ratio)):
            raise ValueError("max_ratio must be a finite number")
        for field_name in ("max_members", "max_member_size", "max_total_uncompressed"):
            value = getattr(self, field_name)
            if not math.isfinite(float(value)):
                raise ValueError(f"{field_name} must be a finite number")
            if value < 1:
                raise ValueError(f"{field_name} must be at least 1")
        if self.max_ratio < 1.0:
            raise ValueError("max_ratio must be at least 1.0")

    @classmethod
    def from_json_file(cls, path: str) -> PackageLimits:
        """Load limits from a JSON object; unusable files are PackageLimitError, not surprises."""
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as error:  # ValueError covers json.JSONDecodeError
            raise PackageLimitError("limits_file", f"unable to read limits file {path}: {error}") from error
        if not isinstance(payload, dict):
            raise PackageLimitError("limits_file", f"limits file {path} must contain a JSON object")
        known = {"max_members", "max_member_size", "max_total_uncompressed", "max_ratio"}
        unknown = sorted(set(payload) - known)
        if unknown:
            raise PackageLimitError("limits_file", f"unknown limit keys in {path}: {', '.join(unknown)}")
        try:
            return cls(**payload)
        except (TypeError, ValueError) as error:
            raise PackageLimitError("limits_file", f"invalid limits in {path}: {error}") from error


def _check_member_names(names: list[str]) -> None:
    """Reject duplicate and path-like unsafe member names before any state is materialised."""
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise PackageLimitError("duplicate_member", f"duplicate package member: {name}")
        seen.add(name)
        unsafe = (
            name.startswith("/")
            or name.startswith("\\")
            or ":" in name
            or "\\" in name
            or any(part == ".." for part in name.split("/"))
        )
        if unsafe:
            raise PackageLimitError("member_name", f"unsafe package member name: {name!r}")


class _MemberReader(Protocol):
    """Minimal structural type for a readable archive member stream."""

    def read(self, size: int = -1, /) -> bytes: ...


def _read_bounded(reader: _MemberReader, declared_size: int, name: str, limits: PackageLimits) -> bytes:
    """Stream a member through a byte counter so over-delivery cannot bypass the per-member cap."""
    chunks: list[bytes] = []
    received = 0
    while True:
        chunk = reader.read(1024 * 1024)
        if not chunk:
            break
        received += len(chunk)
        if received > limits.max_member_size:
            raise PackageLimitError(
                "member_size",
                f"package member '{name}' delivered {received} bytes (declared {declared_size});"
                f" max_member_size={limits.max_member_size}",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _preflight_eocd(path: str, limits: PackageLimits) -> None:
    """Validate the central directory before ZipFile parses it.

    Issue #20 review: the ``ZipFile`` constructor reads the whole central
    directory and builds a ``ZipInfo`` per entry before any of our checks
    run, so a crafted archive with millions of tiny entries costs memory
    proportional to its entry count first.

    Every EOCD/Z64 field is attacker-controlled and ``ZipFile`` reserves
    the right to reinterpret them, so this preflight derives the
    central-directory start the same way ``ZipFile`` does — from the EOCD
    locator's own file position minus the declared directory size — and
    then walks the real records (headers only, no payload) until one
    fails to parse, the declared directory is exhausted, or the member
    cap is exceeded. A falsified count, offset, or ZIP64 sentinel cannot
    hide entries from the walk.
    """
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        window = min(size, 65536 + 22)  # EOCD comment is at most 64 KiB
        handle.seek(size - window)
        tail = handle.read()
    signature = b"PK\x05\x06"
    position = tail.rfind(signature)
    if position == -1:
        return  # not a zip / truncated: ZipFile will raise its own error
    eocd_file_position = size - window + position  # absolute offset of the EOCD record
    declared_entries = int.from_bytes(tail[position + 10 : position + 12], "little")
    cd_size = int.from_bytes(tail[position + 12 : position + 16], "little")
    # note: the classic cd_offset field is deliberately not read — the
    # walk derives its start from the EOCD's own file position, matching
    # zipfile's concat adjustment, so a falsified offset cannot misdirect
    # the scan away from the records ZipFile will parse.

    # Detect ZIP64 by its locator (PK\x06\x07), exactly as zipfile does:
    # the locator may exist regardless of the classic count, and when the
    # ZIP64 EOCD is found it replaces all classic values.
    locator = tail.rfind(b"PK\x06\x07")
    if locator != -1:
        z64_offset = int.from_bytes(tail[locator + 8 : locator + 16], "little")
        z64_tail_position = z64_offset - (size - window)
        if 0 <= z64_tail_position <= len(tail) - 56 and tail[z64_tail_position : z64_tail_position + 4] == b"PK\x06\x06":
            z64 = z64_tail_position
            z64_count_this_disk = int.from_bytes(tail[z64 + 24 : z64 + 32], "little")
            z64_total = int.from_bytes(tail[z64 + 32 : z64 + 40], "little")
            z64_cd_size = int.from_bytes(tail[z64 + 40 : z64 + 48], "little")
            z64_cd_offset = int.from_bytes(tail[z64 + 48 : z64 + 56], "little")
            if z64_count_this_disk != 0xFFFF and z64_total != 0xFFFF:
                declared_entries = z64_total
            if z64_cd_size != 0xFFFFFFFF and z64_cd_offset != 0xFFFFFFFF:
                cd_size = z64_cd_size  # the walk derives its start from cd_size + EOCD position

    if declared_entries > limits.max_members:
        raise PackageLimitError(
            "member_count",
            f"package declares {declared_entries} entries in its central directory; max_members={limits.max_members}",
        )
    if cd_size == 0 or cd_size > size:
        return
    # Derive the effective directory start the way zipfile's
    # _EndRecData does: concat-adjust from the EOCD's own location.
    effective_start = max(eocd_file_position - cd_size, 0)
    # Walk the real central-directory records: each header is at least 46
    # bytes and carries its own name/extra/comment lengths. The declared
    # count is never trusted — including a declared zero, which must not
    # skip the walk while ZipFile would still parse entries by size — so
    # records are visited until one fails to parse, the declared
    # directory is exhausted, or the member cap is exceeded.
    walked = 0
    with open(path, "rb") as handle:
        handle.seek(effective_start)
        while walked < declared_entries or declared_entries == 0:
            header = handle.read(46)
            if len(header) < 46 or header[:4] != b"PK\x01\x02":
                break  # malformed/short directory: ZipFile will judge it
            name_len = int.from_bytes(header[28:30], "little")
            extra_len = int.from_bytes(header[30:32], "little")
            comment_len = int.from_bytes(header[32:34], "little")
            record_len = 46 + name_len + extra_len + comment_len
            if record_len > 46 + 3 * 65535:  # impossible per spec: corrupt
                break
            if handle.seek(record_len - 46, 1) > size:
                break
            walked += 1
            if walked > limits.max_members:
                break  # cap already exceeded; no need to count further
    if walked > limits.max_members:
        raise PackageLimitError(
            "member_count",
            f"package central directory holds at least {walked} entries; max_members={limits.max_members}",
        )


def read_archive_members(path: str | os.PathLike[str], limits: PackageLimits) -> list[tuple[str, bytes]]:
    """Every file member of a zip archive, in archive order, within `limits`.

    The end-of-central-directory entry count is checked before ``ZipFile``
    parses the central directory, and ZipInfo metadata is checked against
    ``limits`` before any member body is read.

    ``max_total_uncompressed`` is applied to the sizes the central directory
    declares, which the archive chooses. That bounds what is materialised only
    because ``ZipFile`` will not hand back more of a member than the member
    claims to hold: it truncates the output at ``file_size`` and fails the CRC,
    so a declaration that lies can only make the loader read *less*. That is a
    dependency on CPython rather than on anything here, and
    ``test_a_member_cannot_deliver_more_bytes_than_it_declares`` is what holds
    it. ``_read_bounded`` is the second line, for a reader that is not
    ``ZipFile``.

    Directory entries are not parts and are dropped, but they are counted
    against ``max_members`` first: an archive can be padded with them just as
    cheaply as with files.
    """
    source = os.fspath(path)
    _preflight_eocd(source, limits)
    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        if len(infos) > limits.max_members:
            raise PackageLimitError(
                "member_count",
                f"package has {len(infos)} entries (including directories); max_members={limits.max_members}",
            )
        _check_member_names([info.filename for info in infos])
        file_infos = [info for info in infos if info.filename and not info.filename.endswith("/")]
        declared_total = 0
        for info in file_infos:
            declared_total += info.file_size
            if info.file_size > limits.max_member_size:
                raise PackageLimitError(
                    "member_size",
                    f"package member '{info.filename}' declares {info.file_size} bytes;"
                    f" max_member_size={limits.max_member_size}",
                )
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > limits.max_ratio:
                raise PackageLimitError(
                    "compression_ratio",
                    f"package member '{info.filename}' has compression ratio {ratio:.1f}; max_ratio={limits.max_ratio}",
                )
        if declared_total > limits.max_total_uncompressed:
            raise PackageLimitError(
                "total_size",
                f"package declares {declared_total} uncompressed bytes;"
                f" max_total_uncompressed={limits.max_total_uncompressed}",
            )
        members: list[tuple[str, bytes]] = []
        for info in file_infos:
            with archive.open(info, "r") as member_reader:
                members.append((info.filename, _read_bounded(member_reader, info.file_size, info.filename, limits)))
    return members


# --------------------------------------------------------------------------
# part names
# --------------------------------------------------------------------------

# A segment of a part name may not be empty, and `.` and `..` are the relative
# forms a part name never has: ECMA-376 Part 2 requires a part name to be a
# sequence of non-empty segments and forbids both dot segments outright.
#
# Nothing here splits a segment on its final period. OPC's notion of an
# extension is "everything after the last period", which makes `.rels` a
# segment with an extension and no stem -- `posixpath.splitext` reads it as a
# dotfile with no extension, and any rule built on that reads the relationship
# part every package has as malformed.
_REJECTED_SEGMENTS = frozenset({"", ".", ".."})


def _checked(name: str) -> str:
    """The part name, or a ValueError saying which rule it broke.

    Names are never repaired. A caller that hands over `visio/document.xml` has
    an archive member name and expects the part it addresses; silently
    prefixing a slash would make the two spellings interchangeable here and
    incompatible everywhere else.
    """
    if not name.startswith("/"):
        raise ValueError(f"{name!r} is not an OPC part name: a part name begins with '/'")
    if name.endswith("/"):
        raise ValueError(f"{name!r} is not an OPC part name: a part name does not end with '/'")
    if "\\" in name or ":" in name:
        raise ValueError(f"{name!r} is not an OPC part name: a part name cannot contain '\\' or ':'")
    for segment in name[1:].split("/"):
        if segment in _REJECTED_SEGMENTS:
            raise ValueError(f"{name!r} is not an OPC part name: {segment!r} is not a usable segment")
    return name


def _part_name_for_member(member: str) -> str:
    """The part name an archive member holds: the same string, made absolute.

    Checked against the same rules every read is checked against, and reported
    as the load-limit failure it is. `_check_member_names` runs first and
    cheaply, over every entry in the central directory, but it only looks for
    names that escape the archive; a member called `visio/./document.xml` stays
    inside it and still has no part name, and a store that held one would list
    a part that `read_bytes` then refused.
    """
    try:
        return _checked(f"/{member}")
    except ValueError as error:
        raise PackageLimitError("member_name", f"unsafe package member name: {member!r} ({error})") from error


# --------------------------------------------------------------------------
# part values
# --------------------------------------------------------------------------


def _canonical_hash_of(data: bytes) -> str:
    """A hash of what a part means, whatever spelling it arrived in.

    Each option is a decision about what counts as the same part. Comments are
    kept because a caller can build one that ElementTree's own parser never
    would; text is not stripped because Visio marks the parts carrying shape
    text `xml:space="preserve"`, and whitespace in those is content; prefixes
    are not rewritten because a part that arrives under one prefix and leaves
    under another is a part libvisio rejects (#60).

    The hash is taken over re-parsed bytes, so it inherits XML's own input
    normalisation: setting an element's text to `a\r\nb` where it was `a\nb`
    hashes the same, because no parser can tell those apart on the way back in.
    Such a change is unrepresentable in the format rather than lost by this.
    """
    canonical = ET.canonicalize(xml_data=data, with_comments=True, strip_text=False, rewrite_prefixes=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_hash(tree: ET.ElementTree[ET.Element]) -> str:
    """The canonical hash of the bytes this tree would be written as.

    Comparable with `XmlPart.original_canonical_hash`, which is this same
    function applied to the tree the moment it was parsed, and that comparison
    is the only thing it is for. It is not a hash of the tree in the abstract:
    it goes through `serialise_part`, so the prefixes that part declared are
    part of what it hashes.
    """
    return _canonical_hash_of(serialise_part(tree))


@dataclass(frozen=True)
class BytesPart:
    """A part nothing has asked the XML of: the bytes it arrived as."""

    data: bytes

    def current_bytes(self) -> bytes:
        return self.data


@dataclass(frozen=True)
class XmlPart:
    """A part that has been parsed. The tree is authoritative from then on.

    `original_bytes` and `original_canonical_hash` are the promotion baseline:
    the bytes the part arrived as, and what the tree parsed out of them meant
    before anything touched it. Both are None for a part written as a tree,
    which has no earlier bytes to preserve and is therefore always serialised.
    """

    tree: ET.ElementTree[ET.Element]
    original_bytes: bytes | None
    original_canonical_hash: str | None

    def current_bytes(self) -> bytes:
        data = serialise_part(self.tree)
        if self.original_bytes is not None and _canonical_hash_of(data) == self.original_canonical_hash:
            return self.original_bytes
        return data


PartValue = BytesPart | XmlPart


def _promoted(name: str, data: bytes) -> XmlPart:
    try:
        tree = parse_part(data)
    except ET.ParseError as error:
        raise ValueError(f"package part {name} is not well-formed XML: {error}") from error
    return XmlPart(tree=tree, original_bytes=data, original_canonical_hash=canonical_hash(tree))


# --------------------------------------------------------------------------
# the store
# --------------------------------------------------------------------------


class PackageStore:
    """The parts of one package, in archive order, addressed by part name."""

    def __init__(self, source: Path) -> None:
        # The one copy of where this package came from. It is only knowable at
        # open, and #89's `save(target=None)` writes back over it.
        self.source = source
        self._parts: dict[str, PartValue] = {}

    @classmethod
    def open(cls, source: str | os.PathLike[str], *, limits: PackageLimits | None = None) -> PackageStore:
        """Read a package off disk. Nothing is parsed as XML here."""
        path = Path(source)
        store = cls(path)
        for member, data in read_archive_members(path, limits if limits is not None else PackageLimits()):
            store._parts[_part_name_for_member(member)] = BytesPart(data)
        return store

    def names(self) -> tuple[str, ...]:
        """Every part name, in the order the archive listed them.

        A part written for the first time goes on the end; a part written over
        keeps the place it had, so the order a package arrived in survives any
        number of writes to it.
        """
        return tuple(self._parts)

    def part(self, name: str) -> PartValue | None:
        """The part as it is held right now, without promoting it.

        The promotion baseline made visible. `read_bytes` is what consumes it
        in anger -- it is the whole of the write-original-or-serialise decision
        -- so this is here for the caller that needs to see whether a part has
        been parsed at all, and what it arrived as.
        """
        return self._parts.get(_checked(name))

    def read_bytes(self, name: str) -> bytes | None:
        """The bytes this part would be written as now, or None if it is absent."""
        value = self._parts.get(_checked(name))
        return None if value is None else value.current_bytes()

    def write_bytes(self, name: str, data: bytes) -> None:
        """Replace a part with these bytes, discarding any tree it had."""
        self._parts[_checked(name)] = BytesPart(data)

    def read_xml(self, name: str) -> ET.ElementTree[ET.Element] | None:
        """This part's tree, promoting it on first ask, or None if it is absent."""
        checked = _checked(name)
        value = self._parts.get(checked)
        if value is None:
            return None
        if isinstance(value, XmlPart):
            return value.tree
        promoted = _promoted(checked, value.data)
        self._parts[checked] = promoted
        return promoted.tree

    def require_xml(self, name: str) -> ET.ElementTree[ET.Element]:
        """This part's tree, or a ValueError naming the part that is not there."""
        tree = self.read_xml(name)
        if tree is None:
            raise ValueError(f"expected XML part not found: {name}")
        return tree

    def write_xml(self, name: str, tree: ET.ElementTree[ET.Element]) -> None:
        """Replace a part with this tree.

        A part written this way has no promotion baseline, so it is serialised
        rather than copied: a caller that went to the trouble of writing a tree
        is telling the store the part changed.
        """
        self._parts[_checked(name)] = XmlPart(tree=tree, original_bytes=None, original_canonical_hash=None)
