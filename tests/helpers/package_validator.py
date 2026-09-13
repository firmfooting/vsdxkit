"""Structural defects a .vsdx has on its own terms, found without opening Visio.

Every rule here is decided by the file itself, so none of it needs an oracle, a
recording, or an expectation about a particular document. That is what makes the
rules worth applying everywhere: they hold for a file nobody has looked at.

They are not all equally normative. Duplicate ids, glue with no endpoint and an
unreachable page are unambiguous. A relationship or content type override naming
a part that is absent is not forbidden in as many words by OPC, and a real file
in this corpus ships that way and opens - but consumers do fail on it, and the
failures are obscure, so it is reported and excused by name where it is known.

The motivating case is a package that declares the same shape id twice. Visio
opens it, keeps one of the two, discards the other, reports no error and saves
again without complaint - so the only way to observe the loss through Visio is
to compare Visio's view against the package's own claim, on Windows, with a
licence. But the duplicate is plainly visible in `page1.xml`. Spending an oracle
on a question the file already answers means the answer only arrives when
somebody remembers to ask.

So: Visio is for questions only Visio can answer. Everything below is a question
the format answers, and it is answered on every platform in milliseconds.

Nothing here imports `vsdx`: a validator sharing the library's parser would
inherit the assumptions it is supposed to be checking.
"""

from __future__ import annotations

import contextlib
import os
import posixpath
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

__all__ = ["Defect", "describe_defects", "validate_package"]

_MAIN_NS = "{http://schemas.microsoft.com/office/visio/2012/main}"
_DOC_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_CONTENT_TYPES = "[Content_Types].xml"


@dataclass(frozen=True)
class Defect:
    """One thing wrong with the package, and where to look for it."""

    kind: str
    where: str
    detail: str


def validate_package(path: str) -> tuple[Defect, ...]:
    """Return every structural defect in the package at `path`, in no set order.

    An archive that cannot be read, or a part that will not parse, is reported
    as a defect rather than raised. This runs at test teardown, where an
    exception surfaces as a traceback pointing into conftest with no mention of
    the marker that would have silenced it - and a package whose XML is
    malformed is exactly what the report is for.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            members = set(names)
            defects: list[Defect] = list(_duplicate_member_defects(names))
            defects.extend(_content_type_defects(archive, members))
            defects.extend(_relationship_defects(archive, members))
            defects.extend(_page_defects(archive, members))
            return tuple(defects)
    except (zipfile.BadZipFile, OSError) as error:
        return (Defect("unreadable-package", os.path.basename(path), f"the archive could not be read: {error}"),)


def _duplicate_member_defects(names: list[str]) -> list[Defect]:
    """A part named twice in one archive.

    `zipfile` reads the last entry and silently ignores the first, and
    `ZipFile.writestr` will emit a duplicate name with only a warning - so a
    writer can produce this, and every reader disagrees about which copy counts.
    A set of member names would hide it, which is why the raw list is walked.
    """
    seen: set[str] = set()
    repeated: list[str] = []
    for name in names:
        if name in seen and name not in repeated:
            repeated.append(name)
        seen.add(name)
    return [Defect("duplicate-member", name, "the archive contains this part more than once") for name in repeated]


def _parse(archive: zipfile.ZipFile, part: str) -> ET.Element | Defect:
    try:
        return ET.fromstring(archive.read(part))
    except ET.ParseError as error:
        return Defect("unreadable-part", part, f"the XML will not parse: {error}")
    except (KeyError, zipfile.BadZipFile, OSError) as error:
        return Defect("unreadable-part", part, f"the part could not be read: {error}")


def describe_defects(defects: tuple[Defect, ...]) -> str:
    return "\n".join(f"  [{defect.kind}] {defect.where}: {defect.detail}" for defect in defects)


# --- pages ------------------------------------------------------------------


def _page_defects(archive: zipfile.ZipFile, members: set[str]) -> list[Defect]:
    defects: list[Defect] = []
    pages_xml = "visio/pages/pages.xml"
    if pages_xml not in members:
        return [Defect("missing-part", pages_xml, "the package declares no pages at all")]

    relationships = _relationships(archive, "visio/pages/_rels/pages.xml.rels", members)
    listing = _parse(archive, pages_xml)
    if isinstance(listing, Defect):
        return [listing]
    for page in listing:
        name = page.attrib.get("Name") or page.attrib.get("NameU") or page.attrib.get("ID", "?")
        rel = page.find(f"{_MAIN_NS}Rel")
        target = None if rel is None else relationships.get(rel.attrib.get(f"{_DOC_REL_NS}id", ""))
        if target is None or target not in members:
            defects.append(
                Defect(
                    "unresolved-page",
                    pages_xml,
                    f"page {name!r} names a part that the relationships do not resolve to anything in the archive",
                )
            )
            continue
        defects.extend(_page_content_defects(archive, target, page))
    return defects


def _page_content_defects(archive: zipfile.ZipFile, part: str, page: ET.Element) -> list[Defect]:
    contents = _parse(archive, part)
    if isinstance(contents, Defect):
        return [contents]
    shapes = _shape_ids(contents.find(f"{_MAIN_NS}Shapes"))
    defects: list[Defect] = []

    seen: set[int] = set()
    for shape_id in shapes:
        if shape_id in seen:
            defects.append(
                Defect(
                    "duplicate-shape-id",
                    part,
                    f"shape {shape_id} is declared more than once. Ids are page-scoped and unique; "
                    "Visio keeps one and drops the rest without an error.",
                )
            )
        seen.add(shape_id)

    for role, shape_id in _glue_endpoints(contents):
        if shape_id not in seen:
            defects.append(
                Defect(
                    "dangling-glue",
                    part,
                    f"a Connect record names shape {shape_id} as its {role}, "
                    "but no such shape is on this page. Visio rebinds glue like this silently.",
                )
            )

    declared = _declared_max_id(page)
    if declared is not None and shapes and declared < max(shapes):
        defects.append(
            Defect(
                "max-id-too-low",
                # the cell is in pages.xml, not in the page part the shapes are in
                "visio/pages/pages.xml",
                f"the page sheet declares MaxID {declared} but carries shape {max(shapes)}. "
                "The next id allocated from it would collide with a shape that already exists.",
            )
        )
    return defects


def _declared_max_id(page: ET.Element) -> int | None:
    """Return the page sheet's MaxID, if it declares one.

    Optional, and no fixture in this repository carries it - Visio writes it on
    some documents and not others, and this library tracks the high-water mark
    in memory instead. Checked when present rather than required, because a
    package that states the number wrongly is worse than one that stays quiet:
    the wrong number is the one an allocator would trust.
    """
    sheet = page.find(f"{_MAIN_NS}PageSheet")
    if sheet is None:
        return None
    for cell in sheet.findall(f"{_MAIN_NS}Cell"):
        if cell.attrib.get("N") == "MaxID":
            try:
                return int(float(cell.attrib.get("V", "")))
            except ValueError:
                return None
    return None


def _shape_ids(container: ET.Element | None) -> list[int]:
    """Every shape id on the page, descending into groups.

    Group members carry page-scoped ids like any other shape, so a member that
    collides with a top-level shape is the same defect as two siblings sharing
    one. Walking only the top level would miss exactly that.
    """
    if container is None:
        return []
    found: list[int] = []
    for shape in container.findall(f"{_MAIN_NS}Shape"):
        # int(), not isdigit(): '\u00b2'.isdigit() is True and int('\u00b2') raises.
        raw = shape.attrib.get("ID")
        if raw is not None:
            # a non-numeric id is the schema's business, not this rule's
            with contextlib.suppress(ValueError):
                found.append(int(raw))
        found.extend(_shape_ids(shape.find(f"{_MAIN_NS}Shapes")))
    return found


def _glue_endpoints(contents: ET.Element) -> list[tuple[str, int]]:
    """Every shape a Connect record names, with the end it names it as."""
    container = contents.find(f"{_MAIN_NS}Connects")
    if container is None:
        return []
    endpoints = []
    for connect in container.findall(f"{_MAIN_NS}Connect"):
        for attribute, role in (("FromSheet", "source"), ("ToSheet", "target")):
            try:
                endpoints.append((role, int(connect.attrib.get(attribute, ""))))
            except ValueError:
                continue
    return endpoints


# --- package ----------------------------------------------------------------


def _relationship_defects(archive: zipfile.ZipFile, members: set[str]) -> list[Defect]:
    defects: list[Defect] = []
    for member in sorted(members):
        if not member.endswith(".rels"):
            continue
        parsed = _parse(archive, member)
        if isinstance(parsed, Defect):
            defects.append(parsed)
            continue
        for identifier, target, external in _relationship_entries(archive, member):
            if external:
                continue  # an external target is a URL, not a part in this archive
            if target not in members:
                defects.append(
                    Defect(
                        "missing-part",
                        member,
                        f"relationship {identifier} points at {target}, which is not in the package",
                    )
                )
    return defects


def _relationship_entries(archive: zipfile.ZipFile, rels_part: str) -> list[tuple[str, str, bool]]:
    base = rels_part.rsplit("/_rels/", 1)[0] if "/_rels/" in rels_part else ""
    entries = []
    parsed = _parse(archive, rels_part)
    if isinstance(parsed, Defect):
        return []  # reported once, by the caller that walks every .rels part
    for relationship in parsed:
        target = relationship.attrib.get("Target", "")
        identifier = relationship.attrib.get("Id", "")
        if not target or not identifier:
            continue
        external = relationship.attrib.get("TargetMode") == "External"
        entries.append((identifier, _resolve(base, target), external))
    return entries


def _relationships(archive: zipfile.ZipFile, rels_part: str, members: set[str]) -> dict[str, str]:
    if rels_part not in members:
        return {}
    return {identifier: target for identifier, target, external in _relationship_entries(archive, rels_part) if not external}


def _resolve(base: str, target: str) -> str:
    """Resolve a relationship target to a package-absolute member name.

    A `Target` is a URI reference and a zip member name is not, so a part whose
    name holds a space or a non-ASCII character arrives percent-encoded here and
    has to be decoded before it will match anything. Embedded images and OLE
    parts are where this usually shows up. Any fragment is not part of the name.

    Targets are relative to the part's own directory and may walk upwards with
    `../`, which `posixpath.normpath` handles; a leading `/` is already absolute
    and only needs its slash removing.
    """
    target = urllib.parse.unquote(target.split("#", 1)[0])
    if target.startswith("/"):
        return target[1:]
    return posixpath.normpath(posixpath.join(base, target)) if base else posixpath.normpath(target)


def _normalise_part(part: str) -> str:
    """Fold a part name for comparison: no leading slash, ASCII case-insensitive."""
    return part.lstrip("/").lower()


def _extension(member: str) -> str:
    """The OPC extension of a part name: everything after its final period.

    Not `posixpath.splitext`, which reads `_rels/.rels` as a name with no
    extension at all and so reports every package in existence as missing a
    content type for it. OPC has no notion of a dotfile.
    """
    return member.rpartition("/")[2].rpartition(".")[2].lower() if "." in member.rpartition("/")[2] else ""


def _content_type_defects(archive: zipfile.ZipFile, members: set[str]) -> list[Defect]:
    if _CONTENT_TYPES not in members:
        return [Defect("missing-part", _CONTENT_TYPES, "the package has no content types part")]

    parsed = _parse(archive, _CONTENT_TYPES)
    if isinstance(parsed, Defect):
        return [parsed]
    defaults: set[str] = set()
    overrides: dict[str, str] = {}
    for entry in parsed:
        if entry.tag.endswith("Default"):
            defaults.add(entry.attrib.get("Extension", "").lower())
        elif entry.tag.endswith("Override"):
            # OPC compares part names case-insensitively (ECMA-376 Part 2), so a
            # package whose Override says /visio/Pages/Page1.xml for a member
            # written visio/pages/page1.xml is valid and must not be reported.
            overrides[_normalise_part(entry.attrib.get("PartName", ""))] = entry.attrib.get("PartName", "")

    defects: list[Defect] = []
    for member in sorted(members):
        if member == _CONTENT_TYPES or member.endswith("/"):
            continue
        extension = _extension(member)
        if _normalise_part(member) in overrides or extension in defaults:
            continue
        defects.append(
            Defect(
                "undeclared-content-type",
                _CONTENT_TYPES,
                f"{member} has no content type: no Override names it and no Default covers "
                f"{'.' + extension if extension else 'a part with no extension'}",
            )
        )
    normalised_members = {_normalise_part(member) for member in members}
    for normalised, declared in sorted(overrides.items()):
        if normalised not in normalised_members:
            defects.append(
                Defect("missing-part", _CONTENT_TYPES, f"an Override declares {declared}, which is not in the package")
            )
    return defects
