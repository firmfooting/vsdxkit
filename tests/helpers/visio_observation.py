"""What a viewer reports about a .vsdx, in a form two viewers can be diffed in.

The library's own tests can only say that vsdxkit wrote what vsdxkit meant to
write. Whether Visio agrees is a separate question, and the interesting answers
are the quiet ones: a package declaring four shapes that Visio opens as three,
reporting no error and saving without complaint.

So this module defines one shape of answer - an `Observation` - and two ways to
obtain it:

* `observation_from_package` reads the XML parts, and says what the file claims.
* `observation_from_com_json` parses what Visio reported over COM, and says what
  Visio actually did.

`compare` diffs them. That is differential testing (McKeeman): two independent
implementations of "open this document", disagreeing where at least one is
wrong. It sidesteps the oracle problem rather than solving it, and it is the
only oracle available here that is stronger than our own opinion.

Three properties of this file are deliberate and worth keeping.

Judgment lives here, not in PowerShell. The COM side extracts and does not
decide. A comparison is only trustworthy if it can be run, in a test, against
inputs known to differ, and PowerShell driving a Windows-only COM server is not
a place where that is possible.

An observation is a total description, not a spot check: every page, every shape
id including group members, every connection - not counts. A count matches by
coincidence; an id set does not. Fields that vary between two honest runs of the
same file are excluded from the record entirely rather than normalised away
later, because a normaliser is a place for a real difference to hide.

Both sides produce the same type. A comparison whose two halves have different
shapes grows special cases until it only reports what its author already
suspected.

Nothing here imports `vsdx`; see the package docstring.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass
from typing import Any

__all__ = [
    "SCHEMA_VERSION",
    "ConnectObservation",
    "Difference",
    "Observation",
    "PageObservation",
    "ShapeObservation",
    "compare",
    "format_differences",
    "observation_from_com_json",
    "observation_from_package",
]

# Bumped when the JSON the COM extractor emits changes shape. A recorded
# observation carries the version it was written under, so a stale recording is
# refused rather than silently misread.
SCHEMA_VERSION = 1

_MAIN_NS = "{http://schemas.microsoft.com/office/visio/2012/main}"
_DOC_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


@dataclass(frozen=True)
class ShapeObservation:
    """One shape, identified by the id that both sides agree to use.

    Visio's `Shape.ID` is the page-scoped id written as `<Shape ID=...>`, which
    makes it the join key between the two sides. `parent_id` is the enclosing
    group's id, or None at the top level: a shape that leaves its group is a
    different bug from a shape that disappears, and flattening the tree to a set
    of ids would call them the same.
    """

    id: int
    parent_id: int | None = None
    name: str = ""

    @property
    def sort_key(self) -> tuple[int, int, str]:
        """Order shapes without comparing a group id against None.

        A generated ordering would compare `parent_id` whenever two shapes share
        an id - which is the duplicate-id case, the one thing this type exists to
        describe - and `None < 5` raises. The harness would then crash on exactly
        the file it was built to report on. -1 sorts a top-level shape first and
        cannot collide with a real id.
        """
        return (self.id, -1 if self.parent_id is None else self.parent_id, self.name)


@dataclass(frozen=True, order=True)
class ConnectObservation:
    """One glue record: which cell of which shape is glued to what."""

    from_shape: int
    from_cell: str
    to_shape: int
    to_cell: str


@dataclass(frozen=True)
class PageObservation:
    index: int
    name: str
    shapes: tuple[ShapeObservation, ...] = ()
    connects: tuple[ConnectObservation, ...] = ()
    # The page is listed but its content could not be reached: no `<Rel>`, or an
    # `r:id` that resolves to nothing. It keeps its position so the pages after
    # it keep theirs.
    unresolved: bool = False
    background: bool = False

    @property
    def shapes_by_id(self) -> dict[int, ShapeObservation]:
        return {shape.id: shape for shape in self.shapes}


@dataclass(frozen=True)
class Observation:
    """One viewer's complete account of a document.

    `label` names the side, and is not decoration: every difference has to say
    which of the two is short, because "the package promises a shape Visio never
    showed" and "Visio invented a shape" are different failures.
    """

    label: str
    pages: tuple[PageObservation, ...] = ()
    source_sha256: str = ""
    viewer_version: str = ""


@dataclass(frozen=True)
class Difference:
    kind: str
    locus: str
    detail: str


def _by_shape(shape: ShapeObservation) -> tuple[int, int, str]:
    return shape.sort_key


def compare(expected: Observation, actual: Observation) -> tuple[Difference, ...]:
    """Diff two accounts of the same document, `expected` first.

    Order matters only for the wording: the differences are symmetric, but each
    one names the side that has the item and the side that does not.
    """
    differences: list[Difference] = []
    _compare_pages(expected, actual, differences)
    return tuple(differences)


def _compare_pages(expected: Observation, actual: Observation, out: list[Difference]) -> None:
    """Align pages by ordinal and compare each pair.

    Ordinal, not name: two pages may legitimately share a name, and a page that
    has been renamed is a smaller surprise than a page that has moved. Names are
    compared as an attribute of the aligned pair instead.
    """
    by_index_expected = {page.index: page for page in expected.pages}
    by_index_actual = {page.index: page for page in actual.pages}

    for index in sorted(set(by_index_expected) | set(by_index_actual)):
        mine = by_index_expected.get(index)
        theirs = by_index_actual.get(index)
        if mine is None or theirs is None:
            present, absent = (expected, actual) if theirs is None else (actual, expected)
            page = mine if theirs is None else theirs
            out.append(
                Difference(
                    kind="page-missing",
                    locus=f"page {index}",
                    detail=(
                        f"{present.label} reports page {index} ({page.name!r}); "
                        f"{absent.label} reports no page at that position"
                    ),
                )
            )
            continue
        if mine.unresolved or theirs.unresolved:
            side = expected.label if mine.unresolved else actual.label
            out.append(
                Difference(
                    kind="page-unresolved",
                    locus=f"page {index}",
                    detail=(
                        f"{side} lists page {index} ({page_name(mine, theirs)!r}) but cannot reach its "
                        "content: the relationship naming the page part is missing or points at nothing. "
                        "The package's own relationship graph is broken, so there is nothing to compare."
                    ),
                )
            )
            continue
        if mine.background != theirs.background:
            out.append(
                Difference(
                    kind="page-background",
                    locus=f"page {index}",
                    detail=(
                        f"{expected.label} says background={mine.background}, "
                        f"{actual.label} says background={theirs.background}"
                    ),
                )
            )
        if mine.name != theirs.name:
            out.append(
                Difference(
                    kind="page-name",
                    locus=f"page {index}",
                    detail=f"{expected.label} calls it {mine.name!r}, {actual.label} calls it {theirs.name!r}",
                )
            )
        _compare_shapes(expected.label, actual.label, index, mine, theirs, out)
        _compare_connects(expected.label, actual.label, index, mine, theirs, out)


def _compare_shapes(
    expected_label: str,
    actual_label: str,
    index: int,
    expected: PageObservation,
    actual: PageObservation,
    out: list[Difference],
) -> None:
    # Before anything is joined: a page that uses one id twice cannot be joined
    # on ids at all. Visio keeps one of the two and discards the other in
    # silence, leaving both sides holding the same set of ids, so a comparison
    # that went straight to the join would call this file clean. It is the
    # failure the harness exists for; it is not allowed to pass through quietly.
    ambiguous = False
    for label, page in ((expected_label, expected), (actual_label, actual)):
        for shape_id in _repeated_ids(page):
            ambiguous = True
            out.append(
                Difference(
                    kind="shape-duplicate-id",
                    locus=f"page {index} shape {shape_id}",
                    detail=(
                        f"{label} declares shape {shape_id} more than once on this page. "
                        "Ids are page-scoped and unique; Visio keeps one and drops the rest without "
                        "an error, so the shapes on this page cannot be matched up."
                    ),
                )
            )
    if ambiguous:
        # Matching by id from here would compare whichever of the duplicates
        # happened to be read last against whichever one Visio kept, and report
        # the coincidence as if it were a finding. The glue records below are
        # still worth comparing: they are separate assertions about the file,
        # and a connector left pointing at a discarded shape is the consequence
        # worth seeing.
        return

    mine = expected.shapes_by_id
    theirs = actual.shapes_by_id
    for shape_id in sorted(set(mine) | set(theirs)):
        in_expected = mine.get(shape_id)
        in_actual = theirs.get(shape_id)
        if in_expected is None or in_actual is None:
            present_label = expected_label if in_actual is None else actual_label
            absent_label = actual_label if in_actual is None else expected_label
            out.append(
                Difference(
                    kind="shape-missing",
                    locus=f"page {index} shape {shape_id}",
                    detail=(
                        f"{present_label} reports shape {shape_id}{_named(in_expected or in_actual)}; {absent_label} does not"
                    ),
                )
            )
            continue
        if in_expected.parent_id != in_actual.parent_id:
            out.append(
                Difference(
                    kind="shape-parent",
                    locus=f"page {index} shape {shape_id}",
                    detail=(
                        f"{expected_label} puts it under {_parent_text(in_expected.parent_id)}, "
                        f"{actual_label} puts it under {_parent_text(in_actual.parent_id)}"
                    ),
                )
            )


def page_name(*candidates: PageObservation) -> str:
    for page in candidates:
        if page.name:
            return page.name
    return ""


def _repeated_ids(page: PageObservation) -> list[int]:
    seen: set[int] = set()
    repeated: set[int] = set()
    for shape in page.shapes:
        (repeated if shape.id in seen else seen).add(shape.id)
    return sorted(repeated)


def _named(shape: ShapeObservation | None) -> str:
    """Render a shape's name for a message, when it has one worth printing."""
    return f" ({shape.name})" if shape is not None and shape.name else ""


def _parent_text(parent_id: int | None) -> str:
    return "the page" if parent_id is None else f"group {parent_id}"


def _compare_connects(
    expected_label: str,
    actual_label: str,
    index: int,
    expected: PageObservation,
    actual: PageObservation,
    out: list[Difference],
) -> None:
    """Compare glue as sets.

    Visio does not preserve the order of the `Connects` collection, and the
    package's order is the order they were written, so ordering here would
    report a difference on every file that had ever been round-tripped.
    """
    # Counter, not set: a writer that emits one `<Connect>` twice leaves both
    # sides holding the same distinct records, and a set comparison calls that
    # equal. Multiplicity is part of what the file says.
    mine = Counter(expected.connects)
    theirs = Counter(actual.connects)
    for label, counts in ((expected_label, mine), (actual_label, theirs)):
        for connect, count in sorted(counts.items()):
            if count > 1:
                out.append(
                    Difference(
                        kind="connect-duplicate",
                        locus=f"page {index} connect {connect.from_shape}.{connect.from_cell}",
                        detail=(
                            f"{label} glues shape {connect.from_shape} cell {connect.from_cell} to shape "
                            f"{connect.to_shape} cell {connect.to_cell} {count} times. Visio keeps one; "
                            "the file says it twice."
                        ),
                    )
                )
    for connect in sorted(set(mine) ^ set(theirs)):
        present_label = expected_label if connect in mine else actual_label
        absent_label = actual_label if connect in mine else expected_label
        out.append(
            Difference(
                kind="connect-missing",
                locus=f"page {index} connect {connect.from_shape}.{connect.from_cell}",
                detail=(
                    f"{present_label} glues shape {connect.from_shape} cell {connect.from_cell} "
                    f"to shape {connect.to_shape} cell {connect.to_cell}; {absent_label} does not"
                ),
            )
        )


def format_differences(differences: tuple[Difference, ...], limit: int = 20) -> str:
    """Render differences for a failure message, in the order they were found."""
    if not differences:
        return "no differences"
    lines = [f"{d.locus}: {d.detail}" for d in differences[:limit]]
    if len(differences) > limit:
        lines.append(f"... and {len(differences) - limit} more")
    return "\n".join(lines)


def observation_from_package(path: str, label: str = "package") -> Observation:
    """Read the .vsdx and say what it claims to contain.

    This is the side that can be computed anywhere, including on a machine with
    no Visio, which is what makes a recorded Visio observation useful later: the
    claim is recomputed on every run, and only the truth is replayed from disk.
    """
    with zipfile.ZipFile(path) as archive:
        return _observation_from_archive(archive, label, _sha256_of(path))


def _observation_from_archive(archive: zipfile.ZipFile, label: str, digest: str) -> Observation:
    pages: list[PageObservation] = []
    for index, (name, background, part) in enumerate(_page_parts(archive), start=1):
        if part is None or part not in archive.namelist():
            pages.append(PageObservation(index=index, name=name, unresolved=True, background=background))
            continue
        contents = ET.fromstring(archive.read(part))
        shapes = tuple(sorted(_shapes_in(contents.find(f"{_MAIN_NS}Shapes"), parent_id=None), key=_by_shape))
        connects = tuple(sorted(_connects_in(contents.find(f"{_MAIN_NS}Connects"))))
        pages.append(PageObservation(index=index, name=name, shapes=shapes, connects=connects, background=background))
    if not pages:
        raise ValueError(
            "this package declares no pages at all. Either visio/pages/pages.xml is missing or it is "
            "empty; comparing it against anything would report agreement on a file with no content."
        )
    return Observation(label=label, pages=tuple(pages), source_sha256=digest)


def _page_parts(archive: zipfile.ZipFile) -> list[tuple[str, bool, str | None]]:
    """Return (page name, is background, part path or None) as `pages.xml` lists them.

    That order is what Visio numbers its pages by, so it is the order the two
    sides have to be aligned in. Resolving each page through the relationship
    part rather than guessing `page1.xml`, `page2.xml`, ... matters because the
    numbering in those filenames is not required to match the page order, and a
    package that has had a page deleted routinely has a gap.

    A page whose relationship is missing or points at nothing yields None rather
    than being left out. Leaving it out would renumber every page after it, so
    page 3 would be compared against page 2 and the broken relationship - the
    actual defect - would surface as a heap of shape differences attributed to
    the wrong page.
    """
    pages_xml = "visio/pages/pages.xml"
    if pages_xml not in archive.namelist():
        return []
    relationships = _relationships(archive, "visio/pages/_rels/pages.xml.rels")
    parts: list[tuple[str, bool, str | None]] = []
    for page in ET.fromstring(archive.read(pages_xml)):
        # Name is what Visio shows; NameU is the invariant name it falls back to
        name = page.attrib.get("Name") or page.attrib.get("NameU") or ""
        rel = page.find(f"{_MAIN_NS}Rel")
        target = None if rel is None else relationships.get(rel.attrib.get(f"{_DOC_REL_NS}id", ""))
        parts.append((name, page.attrib.get("Background") == "1", target))
    return parts


def _relationships(archive: zipfile.ZipFile, rels_part: str) -> dict[str, str]:
    """Map relationship id to the part it points at, as a package path."""
    if rels_part not in archive.namelist():
        return {}
    base = rels_part.rsplit("/_rels/", 1)[0]
    targets: dict[str, str] = {}
    for relationship in ET.fromstring(archive.read(rels_part)):
        target = relationship.attrib.get("Target", "")
        identifier = relationship.attrib.get("Id", "")
        if not target or not identifier:
            continue
        targets[identifier] = target[1:] if target.startswith("/") else f"{base}/{target}"
    return targets


def _shapes_in(container: ET.Element | None, parent_id: int | None) -> list[ShapeObservation]:
    """Walk a `<Shapes>` element, descending into groups.

    A shape carrying `Del='1'` is a deletion of an instance the master would
    otherwise contribute. Visio does not show it, so recording it here would
    report a difference on every file that has ever had a group member removed.
    """
    if container is None:
        return []
    found: list[ShapeObservation] = []
    for shape in container.findall(f"{_MAIN_NS}Shape"):
        if shape.attrib.get("Del") == "1":
            continue
        raw_id = shape.attrib.get("ID")
        if raw_id is None:
            continue
        shape_id = int(raw_id)
        found.append(ShapeObservation(id=shape_id, parent_id=parent_id, name=shape.attrib.get("NameU", "")))
        found.extend(_shapes_in(shape.find(f"{_MAIN_NS}Shapes"), parent_id=shape_id))
    return found


def _connects_in(container: ET.Element | None) -> list[ConnectObservation]:
    if container is None:
        return []
    found: list[ConnectObservation] = []
    for connect in container.findall(f"{_MAIN_NS}Connect"):
        try:
            found.append(
                ConnectObservation(
                    from_shape=int(connect.attrib["FromSheet"]),
                    from_cell=connect.attrib.get("FromCell", ""),
                    to_shape=int(connect.attrib["ToSheet"]),
                    to_cell=connect.attrib.get("ToCell", ""),
                )
            )
        except (KeyError, ValueError):
            # a Connect without resolvable endpoints is itself a finding, but it
            # belongs to the package validator, not to a comparison of two views
            continue
    return found


def _sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def observation_from_com_json(payload: str | dict[str, Any], label: str = "visio") -> Observation:
    """Parse what the COM extractor reported."""
    data = payload if isinstance(payload, dict) else json.loads(payload)
    version = data.get("schema")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"observation is schema {version!r}, this code reads schema {SCHEMA_VERSION}. "
            "Re-record it with tools/visio_observe.ps1 rather than hand-editing the JSON."
        )
    pages = []
    for page in data.get("pages", []):
        shapes = tuple(
            sorted(
                (
                    ShapeObservation(
                        id=int(shape["id"]),
                        parent_id=None if shape.get("parent_id") is None else int(shape["parent_id"]),
                        name=shape.get("name", ""),
                    )
                    for shape in page.get("shapes", [])
                ),
                key=_by_shape,
            )
        )
        connects = tuple(
            sorted(
                ConnectObservation(
                    from_shape=int(connect["from_shape"]),
                    from_cell=connect.get("from_cell", ""),
                    to_shape=int(connect["to_shape"]),
                    to_cell=connect.get("to_cell", ""),
                )
                for connect in page.get("connects", [])
            )
        )
        pages.append(
            PageObservation(
                index=int(page["index"]),
                name=page.get("name", ""),
                shapes=shapes,
                connects=connects,
                background=bool(page.get("background", False)),
            )
        )
    return Observation(
        label=label,
        pages=tuple(sorted(pages, key=lambda page: page.index)),
        source_sha256=data.get("source", {}).get("sha256", ""),
        viewer_version=data.get("viewer", {}).get("version", ""),
    )
