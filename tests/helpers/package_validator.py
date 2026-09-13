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

import os
import posixpath
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

from helpers.opc import (
    CONTENT_TYPES_PART,
    DOC_REL_NS,
    MAIN_NS,
    MASTERS_PART,
    MASTERS_RELS_PART,
    PAGES_PART,
    PAGES_RELS_PART,
)

__all__ = ["Defect", "describe_defects", "validate_package"]


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
            defects.extend(_page_and_master_defects(archive, members))
            return tuple(defects)
    except Exception as error:
        # Deliberately every exception, not a list of the ones seen so far. The
        # list was `BadZipFile` and `OSError`, and `zipfile` also raises
        # `NotImplementedError` for a compression method it does not have and
        # `RuntimeError` for an encrypted member; the recursive walks below
        # raise `RecursionError` on a deeply nested group. The type is named in
        # the report so that a bug in this module still reads as one.
        return (
            Defect(
                "unreadable-package",
                os.path.basename(path),
                f"the archive could not be read: {type(error).__name__}: {error}",
            ),
        )


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
    except Exception as error:
        return Defect("unreadable-part", part, f"the part could not be read: {type(error).__name__}: {error}")


def describe_defects(defects: tuple[Defect, ...]) -> str:
    return "\n".join(f"  [{defect.kind}] {defect.where}: {defect.detail}" for defect in defects)


# --- pages and masters ------------------------------------------------------
#
# `pages.xml` and `masters.xml` are the same document twice over: a listing
# whose entries each carry an id, a sheet of cells, and a `<Rel>` naming the
# part that holds the contents. They are also produced by the same kind of
# code - an allocator handing out ids, and a writer handing out relationship
# ids - so they fail in the same ways, and the rules below are stated once over
# a listing and applied to both. The parts they name are the same type as each
# other too (`MasterContents` is `PageContents`), so those share their rules as
# well.
#
# Kinds here are built from the listing's noun and so do not appear in this
# file as literals: `unresolved-page` / `unresolved-master`,
# `duplicate-page-id` / `duplicate-master-id`, `reused-page-part` /
# `reused-master-part`.


@dataclass(frozen=True)
class _ListingSpec:
    """Where a listing lives, what its entries are called, and whether it is optional."""

    listing: str
    relationships: str
    tag: str
    noun: str
    required: bool


_PAGES = _ListingSpec(
    listing=PAGES_PART,
    relationships=PAGES_RELS_PART,
    tag="Page",
    noun="page",
    # a package with no pages is not a drawing; one with no masters is ordinary
    required=True,
)
_MASTERS = _ListingSpec(
    listing=MASTERS_PART,
    relationships=MASTERS_RELS_PART,
    tag="Master",
    noun="master",
    required=False,
)


@dataclass(frozen=True)
class _Entry:
    """A listing entry whose `<Rel>` resolved to a part that is in the archive."""

    spec: _ListingSpec
    identifier: str | None
    label: str
    part: str
    element: ET.Element


@dataclass(frozen=True)
class _Listing:
    """One parsed listing: the entries that resolved, and every id it takes.

    Ids come from every child element, not only from the entries that resolved
    to a part. A master whose part is missing still owns its id, so a shape
    naming it has not named a master nobody declared: that would be a second
    finding for one broken thing, and the first one is already reported.

    `read` is false when the listing is there but would not parse. Nothing is
    known about what it declares then, so a rule that asks whether an id was
    declared has to stand down rather than answer from an empty set.
    """

    read: bool = True
    entries: tuple[_Entry, ...] = ()
    declared_ids: frozenset[str] = frozenset()


def _page_and_master_defects(archive: zipfile.ZipFile, members: set[str]) -> list[Defect]:
    pages_defects, pages = _listing_defects(archive, members, _PAGES)
    masters_defects, masters = _listing_defects(archive, members, _MASTERS)
    defects = pages_defects + masters_defects

    # Keyed by part rather than by entry, because two entries may name one part
    # and the checks below are about the part. Reporting per entry would report
    # everything in a shared part twice, on top of the `reused-*-part` that
    # says what the actual problem is.
    contents: dict[str, ET.Element] = {}
    for entry in (*pages.entries, *masters.entries):
        if entry.part in contents:
            continue
        parsed = _parse(archive, entry.part)
        if isinstance(parsed, Defect):
            defects.append(parsed)
        else:
            contents[entry.part] = parsed

    for part, root in contents.items():
        defects.extend(_contents_defects(root, part))
    defects.extend(_master_reference_defects(contents, masters))
    for entry in (*pages.entries, *masters.entries):
        if entry.part in contents:
            defects.extend(_max_id_defects(contents[entry.part], entry))
    return defects


def _listing_defects(archive: zipfile.ZipFile, members: set[str], spec: _ListingSpec) -> tuple[list[Defect], _Listing]:
    """Every entry resolves to a part of its own, and no two entries share an id.

    An entry whose `<Rel>` resolves to nothing, two entries resolving to one
    part, two entries claiming one id. None stops the package opening, and the
    last two lose a page or a master outright.
    """
    if spec.listing not in members:
        if not spec.required:
            return [], _Listing()
        return [Defect("missing-part", spec.listing, "the package declares no pages at all")], _Listing()

    parsed = _parse(archive, spec.listing)
    if isinstance(parsed, Defect):
        return [parsed], _Listing(read=False)

    relationships = _relationships(archive, spec.relationships, members)
    defects: list[Defect] = []
    entries: list[_Entry] = []
    declared_ids: set[str] = set()
    named_by: dict[str, str] = {}
    for element in parsed:
        identifier = element.attrib.get("ID")
        key = _id_key(identifier)
        if key is not None:
            if key in declared_ids:
                defects.append(
                    Defect(
                        f"duplicate-{spec.noun}-id",
                        spec.listing,
                        f"{spec.noun} id {identifier} is declared more than once. Ids are unique within "
                        f"the listing, and anything naming this one reaches whichever entry the reader "
                        f"happened to keep.",
                    )
                )
            declared_ids.add(key)
        if element.tag != f"{MAIN_NS}{spec.tag}":
            # `masters.xml` also carries `<MasterShortcut>`, which stands for a
            # master held in another document: it takes an id in this package
            # but has no part in it, so the rules about parts do not apply.
            continue
        label = element.attrib.get("Name") or element.attrib.get("NameU") or identifier or "?"
        rel = element.find(f"{MAIN_NS}Rel")
        target = None if rel is None else relationships.get(rel.attrib.get(f"{DOC_REL_NS}id", ""))
        if target is None or target not in members:
            defects.append(
                Defect(
                    f"unresolved-{spec.noun}",
                    spec.listing,
                    f"{spec.noun} {label!r} names a part that the relationships do not resolve to anything in the archive",
                )
            )
            continue
        if target in named_by:
            defects.append(
                Defect(
                    f"reused-{spec.noun}-part",
                    spec.listing,
                    f"{spec.noun} {label!r} and {spec.noun} {named_by[target]!r} both resolve to "
                    f"{target}. An entry owns its contents part, so an edit to either of these shows "
                    f"up in both.",
                )
            )
        else:
            named_by[target] = label
        entries.append(_Entry(spec, identifier, label, target, element))
    return defects, _Listing(True, tuple(entries), frozenset(declared_ids))


def _contents_defects(contents: ET.Element, part: str) -> list[Defect]:
    """Ids used twice, and glue with no endpoint, in one page or master part.

    `MasterContents` and `PageContents` are the same type, carrying the same
    `Shapes` and `Connects`, so a master goes wrong here the ways a page does.

    Glue is checked from both ends. A `Connect` record and the `Sheet.N!`
    references in the connector's endpoint formulas name the same shape, and a
    writer that maintains one and not the other leaves the other pointing at a
    shape that has moved. Watching the record alone is how #328 went undetected.
    """
    shapes = _shape_ids(contents.find(f"{MAIN_NS}Shapes"))
    defects: list[Defect] = []

    seen: set[int] = set()
    for shape_id in shapes:
        if shape_id in seen:
            defects.append(
                Defect(
                    "duplicate-shape-id",
                    part,
                    f"shape {shape_id} is declared more than once. Ids are unique within the part; "
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
                    "but no such shape is in this part. Visio rebinds glue like this silently.",
                )
            )

    for owner, cell, named in _sheet_references(contents.find(f"{_MAIN_NS}Shapes")):
        if named not in seen:
            defects.append(
                Defect(
                    "stale-sheet-reference",
                    part,
                    f"shape {owner} names Sheet.{named}! in its {cell} formula, but no such shape is "
                    "in this part. A formula is the other place a shape id is written: a connector's "
                    "endpoint and a container's membership are both held this way, so what the "
                    "records say and what the sheet does can come apart.",
                )
            )
    return defects


def _max_id_defects(contents: ET.Element, entry: _Entry) -> list[Defect]:
    """A sheet whose MaxID is below an id the part already uses.

    Reported against the listing rather than the part, because that is where
    the cell is.
    """
    declared = _declared_max_id(entry.element)
    shapes = _shape_ids(contents.find(f"{MAIN_NS}Shapes"))
    if declared is None or not shapes or declared >= max(shapes):
        return []
    return [
        Defect(
            "max-id-too-low",
            entry.spec.listing,
            f"the {entry.spec.noun} sheet declares MaxID {declared} but carries shape {max(shapes)}. "
            "The next id allocated from it would collide with a shape that already exists.",
        )
    ]


def _master_reference_defects(contents: dict[str, ET.Element], masters: _Listing) -> list[Defect]:
    """Shapes naming a master, or a shape inside one, that the package has not got.

    A listing that would not parse is not evidence that nothing was declared,
    so the rule stands down: answering from an empty set would report every
    instance in the package for one part nobody can read.
    """
    if not masters.read:
        return []
    shapes_by_master = {
        _id_key(entry.identifier): frozenset(_shape_ids(contents[entry.part].find(f"{MAIN_NS}Shapes")))
        for entry in masters.entries
        if entry.identifier is not None and entry.part in contents
    }
    defects: list[Defect] = []
    for part, root in contents.items():
        defects.extend(
            _shape_reference_defects(root.find(f"{MAIN_NS}Shapes"), None, part, masters.declared_ids, shapes_by_master)
        )
    return defects


def _shape_reference_defects(
    container: ET.Element | None,
    inherited: str | None,
    part: str,
    declared: frozenset[str],
    shapes_by_master: dict[str | None, frozenset[int]],
) -> list[Defect]:
    """Check `Master` and `MasterShape` on every shape below `container`.

    `Master` names a master in this package. `MasterShape` names a shape inside
    whichever master the instance came from, which is the nearest `Master` at or
    above the shape - so it is carried down the tree rather than looked up.
    """
    if container is None:
        return []
    defects: list[Defect] = []
    for shape in container.findall(f"{MAIN_NS}Shape"):
        named = shape.attrib.get("Master")
        master = _id_key(named) if named is not None else inherited
        if named is not None and master not in declared:
            defects.append(
                Defect(
                    "undeclared-master",
                    part,
                    f"shape {shape.attrib.get('ID', '?')} is an instance of master {named}, which this "
                    "package does not declare. Visio drops an instance like this on open without an "
                    "error, so the file opens with the shape missing.",
                )
            )
        member = _as_int(shape.attrib.get("MasterShape"))
        # Resolvable only against a master that was read, and only where the
        # shape does not carry `Master` itself: neither this corpus nor the
        # schema settles which of the two a shape carrying both resolves
        # against, and a rule that guesses fires on files nobody has a reason
        # to think are wrong. A `MasterShape` with no master above it at all is
        # skipped for the same reason.
        resolvable = named is None and member is not None and master in shapes_by_master
        if resolvable and member not in shapes_by_master[master]:
            defects.append(
                Defect(
                    "undeclared-master-shape",
                    part,
                    f"shape {shape.attrib.get('ID', '?')} inherits from shape {member} of master "
                    f"{master}, which has no shape with that id.",
                )
            )
        defects.extend(_shape_reference_defects(shape.find(f"{MAIN_NS}Shapes"), master, part, declared, shapes_by_master))
    return defects


def _declared_max_id(sheet_holder: ET.Element) -> int | None:
    """Return the entry's MaxID, if its sheet declares one.

    Optional, and no fixture in this repository carries it - Visio writes it on
    some documents and not others, and this library tracks the high-water mark
    in memory instead. Checked when present rather than required, because a
    package that states the number wrongly is worse than one that stays quiet:
    the wrong number is the one an allocator would trust.
    """
    sheet = sheet_holder.find(f"{MAIN_NS}PageSheet")
    if sheet is None:
        return None
    for cell in sheet.findall(f"{MAIN_NS}Cell"):
        if cell.attrib.get("N") == "MaxID":
            try:
                return int(float(cell.attrib.get("V", "")))
            except ValueError:
                return None
    return None


def _as_int(raw: str | None) -> int | None:
    """Read an id attribute as a number, or None if it is not one.

    `int()`, not `str.isdigit()`: '²'.isdigit() is True and int('²')
    raises. A non-numeric id is the schema's business, not any rule's here.
    """
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _id_key(raw: str | None) -> str | None:
    """Fold an id to the value it names, so that '06' and '6' are one master.

    Ids are `xsd:unsignedInt`, whose lexical space admits leading zeros and a
    leading plus, so two spellings can be one id. Visio does not write them
    that way, but a package reported for a difference no reader would see is a
    package whose report gets switched off.
    """
    value = _as_int(raw)
    return raw if value is None else str(value)


def _shape_ids(container: ET.Element | None) -> list[int]:
    """Every shape id in the part, descending into groups.

    Group members carry part-scoped ids like any other shape, so a member that
    collides with a top-level shape is the same defect as two siblings sharing
    one. Walking only the top level would miss exactly that.
    """
    if container is None:
        return []
    found: list[int] = []
    for shape in container.findall(f"{MAIN_NS}Shape"):
        shape_id = _as_int(shape.attrib.get("ID"))
        if shape_id is not None:
            found.append(shape_id)
        found.extend(_shape_ids(shape.find(f"{MAIN_NS}Shapes")))
    return found


def _glue_endpoints(contents: ET.Element) -> list[tuple[str, int]]:
    """Every shape a Connect record names, with the end it names it as."""
    container = contents.find(f"{MAIN_NS}Connects")
    if container is None:
        return []
    endpoints = []
    for connect in container.findall(f"{MAIN_NS}Connect"):
        for attribute, role in (("FromSheet", "source"), ("ToSheet", "target")):
            endpoint = _as_int(connect.attrib.get(attribute))
            if endpoint is not None:
                endpoints.append((role, endpoint))
    return endpoints


# A ShapeSheet formula addresses another shape on the same page as `Sheet.5!Cell`
# or `Sheet5!Cell`, at the start of the formula or nested inside a function call.
# The lookbehind drops the sheet of a cross-page reference - the `Sheet.5!` in
# `Pages[Page-2]!Sheet.5!Width` belongs to the page named in front of it and
# cannot be resolved against this one.
_SHEET_REFERENCE = re.compile(r"(?<!!)\bSheet\.?(\d+)!")


def _own_cells(shape: ET.Element) -> list[ET.Element]:
    """The cells this shape declares, not the ones its sub-shapes declare.

    Cells sit at several depths - directly under the shape, and inside the rows
    of a `Section` - so this descends, stopping at the `Shapes` container that
    holds the shape's children. A sub-shape's cells are found when the walk
    reaches that shape, and are reported under its id.
    """
    found: list[ET.Element] = []
    for child in shape:
        if child.tag == f"{_MAIN_NS}Shapes":
            continue
        if child.tag == f"{_MAIN_NS}Cell":
            found.append(child)
        else:
            found.extend(_own_cells(child))
    return found


def _sheet_references(container: ET.Element | None) -> list[tuple[str, str, int]]:
    """Every sheet a formula names, as (the shape holding it, the cell, the id).

    A formula naming one sheet twice - which is how Visio writes a glue point,
    `PAR(PNT(Sheet.2!Connections.X1,Sheet.2!Connections.Y1))` - yields it once.
    That is one thing to fix, and reporting it per occurrence would report the
    one fix twice.
    """
    if container is None:
        return []
    found: list[tuple[str, str, int]] = []
    for shape in container.findall(f"{_MAIN_NS}Shape"):
        owner = shape.attrib.get("ID", "?")
        for cell in _own_cells(shape):
            formula = cell.attrib.get("F")
            if not formula or "Sheet" not in formula:
                continue
            for named in dict.fromkeys(_SHEET_REFERENCE.findall(formula)):
                found.append((owner, cell.attrib.get("N", "?"), int(named)))
        found.extend(_sheet_references(shape.find(f"{_MAIN_NS}Shapes")))
    return found


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
    if CONTENT_TYPES_PART not in members:
        return [Defect("missing-part", CONTENT_TYPES_PART, "the package has no content types part")]

    parsed = _parse(archive, CONTENT_TYPES_PART)
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
        if member == CONTENT_TYPES_PART or member.endswith("/"):
            continue
        extension = _extension(member)
        if _normalise_part(member) in overrides or extension in defaults:
            continue
        defects.append(
            Defect(
                "undeclared-content-type",
                CONTENT_TYPES_PART,
                f"{member} has no content type: no Override names it and no Default covers "
                f"{'.' + extension if extension else 'a part with no extension'}",
            )
        )
    normalised_members = {_normalise_part(member) for member in members}
    for normalised, declared in sorted(overrides.items()):
        if normalised not in normalised_members:
            defects.append(
                Defect("missing-part", CONTENT_TYPES_PART, f"an Override declares {declared}, which is not in the package")
            )
    return defects
