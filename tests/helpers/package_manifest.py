"""A description of what a .vsdx package contains, at the level the format cares about.

A `.vsdx` is a zip of XML parts, and two archives can hold the same document
while sharing not one byte: the serialiser picks the quoting, the empty-element
spelling and the order of otherwise-equal attributes. Comparing the bytes alone
calls every such archive different. Comparing the parsed trees alone calls two
archives the same when one has lost its XML declaration or renamed a namespace
prefix, which is the difference between a file Visio opens and a file libvisio
rejects (issue #60).

A `PackageManifest` records both, per member, so a comparison can say which of
the two happened:

* the member names, in archive order, and whether each part is XML or bytes;
* a SHA-256 of the raw bytes, for every member;
* for XML parts, a SHA-256 of the canonical form, the XML declaration exactly as
  written, and every namespace prefix the part binds;
* the content type declared for `/visio/document.xml`, which is what makes a
  package macro-enabled. The `.vsdm` extension is a consequence of that, not the
  cause, and a manifest of a renamed file must still say so.

`assert_manifest_equal` compares two manifests and, for the first member that
differs, says which of those records moved and prints a unified diff of the
canonical XML.

Nothing here imports `vsdx`. An oracle that shared the library's parser would
share its blind spots, so archives are opened with `zipfile` and parts with
`xml.etree.ElementTree` directly. That also keeps the manifest usable on a
package this library did not write.
"""

from __future__ import annotations

import codecs
import difflib
import fnmatch
import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

__all__ = [
    "CANONICALIZE_OPTIONS",
    "CHANGE_KINDS",
    "DRAWING_CONTENT_TYPE",
    "MACRO_ENABLED_CONTENT_TYPE",
    "MAIN_DOCUMENT_PART",
    "PackageManifest",
    "PartManifest",
    "XmlDeclaration",
    "assert_manifest_equal",
    "manifest_differences",
    "member_matches",
]

# Options passed to `ET.canonicalize` for every XML part. Each is a decision
# about what counts as "the same part", so `test_canonicalisation_options_are_pinned`
# asserts this exact mapping: changing it changes what the whole suite lets
# through, and that should cost an edit to the test as well as to the code.
#
# with_comments    ElementTree's parser discards comments, so a save that
#                  dropped one would otherwise be invisible here.
# strip_text       Visio writes `xml:space="preserve"` on the parts that carry
#                  shape text. Whitespace in those parts is content.
# rewrite_prefixes the point of issue #60: a part that arrives under `ns0:`
#                  instead of its own default namespace is rejected by libvisio
#                  and draw.io. Rewriting prefixes to a canonical sequence would
#                  hide exactly that regression.
CANONICALIZE_OPTIONS: Mapping[str, bool] = MappingProxyType(
    {
        "with_comments": True,
        "strip_text": False,
        "rewrite_prefixes": False,
    }
)

# Members compared as XML. Every part of a Visio package is one of these two
# extensions or a binary: an image, the EMF thumbnail, or `vbaProject.bin`.
XML_SUFFIXES = (".xml", ".rels")

MAIN_DOCUMENT_PART = "/visio/document.xml"
CONTENT_TYPES_PART = "[Content_Types].xml"
CONTENT_TYPES_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"
MACRO_ENABLED_CONTENT_TYPE = "application/vnd.ms-visio.drawing.macroEnabled.main+xml"
DRAWING_CONTENT_TYPE = "application/vnd.ms-visio.drawing.main+xml"

# The kinds of difference `assert_manifest_equal` reports, and the names
# `allowed_changes` accepts. Ordered from "not the same package" down to "the
# same XML, spelled differently".
#
# There is deliberately no "kind" change: a part is XML or binary according to
# its member name alone, and two manifests are only ever compared member by
# member, so the two sides always agree. A kind that could be listed here but
# never raised would make `allowed_changes={"*": ("kind",)}` validate and then
# waive nothing.
ADDED = "added"
REMOVED = "removed"
ORDER = "order"
DECLARATION = "declaration"
NAMESPACES = "namespaces"
CANONICAL = "canonical"
BYTES = "bytes"
CHANGE_KINDS = (ADDED, REMOVED, ORDER, DECLARATION, NAMESPACES, CANONICAL, BYTES)

_DECLARATION_RE = re.compile(r"\A(?P<declaration><\?xml[^>]*\?>)")
_PSEUDO_ATTRIBUTE_RE = re.compile(r"(\w+)\s*=\s*(['\"])(.*?)\2")

# A part may be UTF-16 even though Visio writes UTF-8, and XML requires such a
# part to open with a byte order mark. Reading the declaration as raw bytes
# would record "no declaration" for one, which is the wrong answer to give
# about the very field this helper exists to watch. UTF-32 is absent because
# expat rejects it outright, so such a part never reaches this function.
_BYTE_ORDER_MARKS = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
# Long enough for any declaration, short enough that decoding it is free.
_DECLARATION_WINDOW = 512


@dataclass(frozen=True)
class XmlDeclaration:
    """An XML part's declaration, as written rather than as interpreted.

    The text is kept verbatim because every part of it has been seen to move:
    Visio writes `encoding='utf-8'` in the drawing parts and
    `encoding="UTF-8" standalone="yes"` in the package parts, and ElementTree
    writes back neither. The parsed fields exist so a failure message can name
    what moved instead of showing two similar-looking strings.
    """

    text: str | None
    version: str | None
    encoding: str | None
    standalone: str | None
    byte_order_mark: bool

    @classmethod
    def read(cls, data: bytes) -> XmlDeclaration:
        # the mark is read first and separately: a part may carry one and no
        # declaration, and the mark is also what says how to decode the rest
        mark, charset = b"", "utf-8"
        for candidate, candidate_charset in _BYTE_ORDER_MARKS:
            if data.startswith(candidate):
                mark, charset = candidate, candidate_charset
                break
        head = data[len(mark) : len(mark) + _DECLARATION_WINDOW].decode(charset, errors="replace")
        match = _DECLARATION_RE.match(head)
        if match is None:
            return cls(text=None, version=None, encoding=None, standalone=None, byte_order_mark=bool(mark))
        text = match.group("declaration")
        pseudo_attributes = {name: value for name, _, value in _PSEUDO_ATTRIBUTE_RE.findall(text)}
        return cls(
            text=text,
            version=pseudo_attributes.get("version"),
            encoding=pseudo_attributes.get("encoding"),
            standalone=pseudo_attributes.get("standalone"),
            byte_order_mark=bool(mark),
        )

    def describe(self) -> str:
        if self.text is None:
            return "(no XML declaration)"
        return f"{'<BOM>' if self.byte_order_mark else ''}{self.text}"


@dataclass(frozen=True)
class PartManifest:
    """One member of the archive.

    `canonical_text` is carried so a failed comparison can print a diff rather
    than two hashes. It is excluded from equality: parts with the same canonical
    hash have the same canonical text, and a manifest rebuilt without the text
    must still compare equal to one that has it.
    """

    name: str
    kind: str  # "xml" or "binary"
    byte_sha256: str
    declaration: XmlDeclaration | None = None
    namespaces: tuple[tuple[str, str], ...] = ()
    root_tag: str | None = None
    canonical_sha256: str | None = None
    canonical_text: str | None = field(default=None, compare=False, repr=False)

    @property
    def is_xml(self) -> bool:
        return self.kind == "xml"


@dataclass(frozen=True)
class PackageManifest:
    """Every member of one archive, in the order the archive lists them."""

    parts: tuple[PartManifest, ...]
    main_part_content_type: str
    label: str = field(default="", compare=False)

    @classmethod
    def from_bytes(cls, data: bytes, label: str = "") -> PackageManifest:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return cls.from_archive(archive, label=label)

    @classmethod
    def from_path(cls, path: str) -> PackageManifest:
        with zipfile.ZipFile(path) as archive:
            return cls.from_archive(archive, label=str(path))

    @classmethod
    def from_archive(cls, archive: zipfile.ZipFile, label: str = "") -> PackageManifest:
        members = [(name, archive.read(name)) for name in archive.namelist()]
        parts = tuple(_part_manifest(name, data) for name, data in members)
        content_type = next((_main_part_content_type(data) for name, data in members if name == CONTENT_TYPES_PART), "")
        return cls(parts=parts, main_part_content_type=content_type, label=label)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(part.name for part in self.parts)

    def by_name(self) -> dict[str, PartManifest]:
        return {part.name: part for part in self.parts}

    @property
    def is_macro_enabled(self) -> bool:
        """Whether the package declares the macro-enabled main part.

        Read from `[Content_Types].xml`, never from the file extension: a
        macro-enabled package saved under a `.vsdx` name is still macro-enabled,
        and the manifest has to say so for that mismatch to be visible.
        """
        return self.main_part_content_type == MACRO_ENABLED_CONTENT_TYPE


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _part_manifest(name: str, data: bytes) -> PartManifest:
    byte_sha256 = _sha256(data)
    if not name.endswith(XML_SUFFIXES):
        return PartManifest(name=name, kind="binary", byte_sha256=byte_sha256)
    try:
        canonical = ET.canonicalize(xml_data=data, **CANONICALIZE_OPTIONS)
        root_tag, namespaces = _structure(data)
    except ET.ParseError as error:
        raise ValueError(f"package member {name!r} is not well-formed XML: {error}") from error
    return PartManifest(
        name=name,
        kind="xml",
        byte_sha256=byte_sha256,
        declaration=XmlDeclaration.read(data),
        namespaces=namespaces,
        root_tag=root_tag,
        canonical_sha256=_sha256(canonical.encode("utf-8")),
        canonical_text=canonical,
    )


def _structure(data: bytes) -> tuple[str | None, tuple[tuple[str, str], ...]]:
    """The root tag, and every (prefix, uri) the part binds, in document order.

    Prefixes are collected from the whole part rather than from the root
    element. A Visio drawing can carry a third-party vocabulary on a descendant
    -- Lucidchart's `lc:Property` is in the test corpus -- and that prefix is as
    much part of the file's spelling as the root's own.
    """
    root_tag: str | None = None
    namespaces: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for event, payload in ET.iterparse(io.BytesIO(data), events=("start-ns", "start")):
        if event == "start-ns":
            binding = (payload[0], payload[1])
            if binding not in seen:
                seen.add(binding)
                namespaces.append(binding)
        elif root_tag is None:
            root_tag = payload.tag
    return root_tag, tuple(namespaces)


def _main_part_content_type(content_types: bytes) -> str:
    """The content type `[Content_Types].xml` declares for the main document part."""
    root = ET.fromstring(content_types)
    for override in root.findall(f"{{{CONTENT_TYPES_NAMESPACE}}}Override"):
        if override.get("PartName") == MAIN_DOCUMENT_PART:
            return override.get("ContentType", "")
    return ""


def _part_changes(expected: PartManifest, actual: PartManifest) -> tuple[str, ...]:
    """Which records moved between two manifests of the same member.

    Ordered from the most to the least meaningful, so the first entry is the one
    worth reading: a canonical difference means the XML changed, while a
    bytes-only difference means only its spelling did.
    """
    changes: list[str] = []
    if expected.is_xml and actual.is_xml:
        if expected.declaration != actual.declaration:
            changes.append(DECLARATION)
        if expected.namespaces != actual.namespaces:
            changes.append(NAMESPACES)
        if expected.canonical_sha256 != actual.canonical_sha256:
            changes.append(CANONICAL)
    if expected.byte_sha256 != actual.byte_sha256:
        changes.append(BYTES)
    return tuple(changes)


def manifest_differences(expected: PackageManifest, actual: PackageManifest) -> dict[str, tuple[str, ...]]:
    """Every difference between two manifests, keyed by member name.

    Members added or removed are reported under their own name; a member that
    moved within the archive is reported as `order`. The mapping follows
    `expected`'s member order, with added members last, so `next(iter(...))`
    gives the first differing member.
    """
    expected_parts = expected.by_name()
    actual_parts = actual.by_name()

    # `position >= len(actual_order)` only when one side repeats a member name,
    # which a hand-built archive can do; report that as a reorder rather than
    # raising IndexError out of a comparison helper.
    common = [name for name in expected.names if name in actual_parts]
    actual_order = [name for name in actual.names if name in expected_parts]
    reordered = {
        name for position, name in enumerate(common) if position >= len(actual_order) or actual_order[position] != name
    }

    differences: dict[str, tuple[str, ...]] = {}
    for name in expected.names:
        changes: list[str] = []
        if name not in actual_parts:
            changes.append(REMOVED)
        else:
            if name in reordered:
                changes.append(ORDER)
            changes.extend(_part_changes(expected_parts[name], actual_parts[name]))
        if changes:
            differences[name] = tuple(changes)
    for name in actual.names:
        if name not in expected_parts:
            differences[name] = (ADDED,)
    return differences


def member_matches(name: str, pattern: str) -> bool:
    """Whether a member name is covered by a pattern.

    A name always matches itself before fnmatch gets a look, because the part
    every package has is called `[Content_Types].xml` and fnmatch reads those
    brackets as a character class. Writing the name out would otherwise match
    every one-character name and nothing else.
    """
    return name == pattern or fnmatch.fnmatchcase(name, pattern)


def _allowed_for(name: str, allowed_changes: Mapping[str, Iterable[str]]) -> frozenset[str]:
    """The change kinds allowed for one member: the union over matching patterns."""
    allowed: set[str] = set()
    for pattern, kinds in allowed_changes.items():
        if member_matches(name, pattern):
            allowed.update(kinds)
    return frozenset(allowed)


def _normalise_allowed(allowed_changes: Mapping[str, Iterable[str]] | Iterable[str] | None) -> Mapping[str, Iterable[str]]:
    if allowed_changes is None:
        return {}
    if isinstance(allowed_changes, str):
        # a bare string is iterable, so it would otherwise be read one letter at
        # a time and rejected as five unknown change kinds
        raise ValueError(f"allowed_changes takes a collection of change kinds; pass ({allowed_changes!r},) or a mapping")
    table = allowed_changes if isinstance(allowed_changes, Mapping) else {"*": list(allowed_changes)}
    unknown = {kind for kinds in table.values() for kind in kinds} - set(CHANGE_KINDS)
    if unknown:
        raise ValueError(f"unknown change kind(s) {sorted(unknown)}; expected some of {list(CHANGE_KINDS)}")
    return table


def _diff_lines(canonical: str) -> list[str]:
    """Canonical XML is one long line; break it before every tag.

    Without this, a diff of two drawing parts is two 200KB lines, one removed
    and one added, which tells the reader nothing.
    """
    return [piece for piece in re.split(r"(?=<)", canonical) if piece]


def _canonical_diff(expected: PartManifest, actual: PartManifest, max_lines: int) -> list[str]:
    if expected.canonical_text is None or actual.canonical_text is None:
        return ["  (canonical XML was not retained in one of the manifests, so no diff is available)"]
    diff = difflib.unified_diff(
        _diff_lines(expected.canonical_text),
        _diff_lines(actual.canonical_text),
        fromfile="expected",
        tofile="actual",
        lineterm="",
        n=2,
    )
    lines = [f"  {line}" for line in diff]
    if not lines:
        return ["  (the canonical XML is identical; the difference is in how it is spelled)"]
    if len(lines) > max_lines:
        lines = [*lines[:max_lines], f"  ... {len(lines) - max_lines} further diff lines suppressed"]
    return lines


def _format_namespaces(namespaces: Sequence[tuple[str, str]]) -> str:
    if not namespaces:
        return "(none)"
    return ", ".join(f"{prefix or '(default)'}={uri}" for prefix, uri in namespaces)


def _report(
    expected: PackageManifest,
    actual: PackageManifest,
    unexpected: Mapping[str, tuple[str, ...]],
    allowed_changes: Mapping[str, Iterable[str]],
    max_diff_lines: int,
) -> str:
    """The failure message: the first unexpected member, in full, then a tally."""
    name = next(iter(unexpected))
    changes = unexpected[name]
    expected_part = expected.by_name().get(name)
    actual_part = actual.by_name().get(name)

    lines = [
        f"package manifest mismatch at member {name!r}",
        f"  expected: {expected.label or '<expected>'}",
        f"  actual:   {actual.label or '<actual>'}",
        f"  unexpected changes: {', '.join(changes)}",
    ]
    allowed_here = sorted(_allowed_for(name, allowed_changes))
    if allowed_here:
        lines.append(f"  changes allowed here: {', '.join(allowed_here)}")

    if expected_part is None or actual_part is None:
        lines.append("  the member is present in only one of the two packages")
        lines.append(f"  expected members: {list(expected.names)}")
        lines.append(f"  actual members:   {list(actual.names)}")
    else:
        if ORDER in changes:
            lines.append(f"  position in the archive: {expected.names.index(name)} -> {actual.names.index(name)}")
        if DECLARATION in changes and expected_part.declaration and actual_part.declaration:
            lines.append(f"  declaration: {expected_part.declaration.describe()}")
            lines.append(f"           ->  {actual_part.declaration.describe()}")
        if NAMESPACES in changes:
            lines.append(f"  namespace prefixes: {_format_namespaces(expected_part.namespaces)}")
            lines.append(f"                  ->  {_format_namespaces(actual_part.namespaces)}")
        if BYTES in changes:
            lines.append(f"  bytes sha256: {expected_part.byte_sha256[:16]} -> {actual_part.byte_sha256[:16]}")
        if expected_part.is_xml and actual_part.is_xml:
            lines.append("  canonical XML diff:")
            lines.extend(_canonical_diff(expected_part, actual_part, max_diff_lines))

    # counted over `unexpected`, not `differences`: in the round-trip freeze
    # every rewritten part is in `differences` with its drift waived, and
    # naming those here would bury one real regression in eight red herrings
    others = [other for other in unexpected if other != name]
    if others:
        shown = ", ".join(repr(other) for other in others[:5])
        suffix = f", and {len(others) - 5} more" if len(others) > 5 else ""
        lines.append(f"  {len(others)} further member(s) also differ: {shown}{suffix}")
    return "\n".join(lines)


def assert_manifest_equal(
    expected: PackageManifest,
    actual: PackageManifest,
    allowed_changes: Mapping[str, Iterable[str]] | Iterable[str] | None = None,
    max_diff_lines: int = 60,
) -> None:
    """Fail unless `actual` matches `expected`, ignoring the changes allowed.

    `allowed_changes` is either a set of change kinds allowed for every member,
    or a mapping from an fnmatch pattern over member names to the kinds allowed
    for the members it matches; a member's allowance is the union over every
    pattern that matches it. The kinds are the names in `CHANGE_KINDS`, and an
    unrecognised one raises `ValueError` rather than quietly allowing nothing.

    The failure names the first member that differs in `expected`'s order, says
    which records moved, and prints a unified diff of the canonical XML.
    """
    table = _normalise_allowed(allowed_changes)

    if expected.main_part_content_type != actual.main_part_content_type:
        raise AssertionError(
            f"package kind changed: the content type declared for {MAIN_DOCUMENT_PART} went from "
            f"{expected.main_part_content_type!r} to {actual.main_part_content_type!r}"
        )

    differences = manifest_differences(expected, actual)
    unexpected = {
        name: tuple(change for change in changes if change not in _allowed_for(name, table))
        for name, changes in differences.items()
    }
    unexpected = {name: changes for name, changes in unexpected.items() if changes}
    if unexpected:
        raise AssertionError(_report(expected, actual, unexpected, table, max_diff_lines))
