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
import math
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass
from typing import Any

__all__ = [
    "PLACEMENT_CELLS",
    "PLACEMENT_TOLERANCE",
    "SCHEMA_VERSION",
    "CellObservation",
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
#
# 2: each shape carries the cells that place it (see PLACEMENT_CELLS).
SCHEMA_VERSION = 2

# The cells that decide where a shape is, how big it is and which way round it
# faces; how a shape looks is a separate comparison. The last four exist only on
# a 1-D shape - a connector or a line - and both sides report them only for the
# shapes that have them.
PLACEMENT_CELLS = (
    "PinX",
    "PinY",
    "Width",
    "Height",
    "Angle",
    "LocPinX",
    "LocPinY",
    "FlipX",
    "FlipY",
    "BeginX",
    "BeginY",
    "EndX",
    "EndY",
)

# How far apart two constants may be and still count as the same constant, as a
# relative difference and as an absolute one in internal units, whichever is
# looser.
#
# Internal units are inches, and radians for angles. Two honest accounts of the
# same cell still differ: a drawing authored in millimetres has been through
# 1 in = 25.4 mm and back, and Visio does that arithmetic itself rather than
# handing back the number the file stored. The measured case is PinX on
# test4_connectors.vsdx - the package holds 1.332677148526936 and Visio returns
# 1.33267714852694, three parts in 1e15 apart. That error is relative, so 1e-9
# sits a few hundred thousand times above it at any magnitude a page reaches.
#
# It is also far below anything a person could mean: 1e-9 in is 25 picometres,
# and the smallest movement this is meant to catch - one millimetre - is
# 0.03937 in, forty million times larger.
#
# An exact comparison would fail on that, and a check that fails on correct
# arithmetic gets switched off.
PLACEMENT_TOLERANCE = 1e-9

# What the package side reports for a cell whose formula it could not resolve.
# It has to be something Visio cannot produce: the alternative - falling back to
# the cached `V` - looks exactly like a constant that agrees, because `V` is the
# unresolved formula already evaluated. A connector that had lost its glue would
# then be reported as a shape sitting where the connector used to be.
_UNRESOLVED_INHERIT = "<unresolved Inh>"

# A formula that is nothing but a literal: a number with an optional unit
# suffix, or a boolean. Anything else names a cell or calls a function, and two
# sides can only be compared on such a formula as text.
_LITERAL = re.compile(
    r"""
    ^(?:
        [-+]? (?: \d+\.?\d* | \.\d+ ) (?: [eE][-+]?\d+ )?   # 0, 1.25, .5, -3e-2
        \s* [A-Za-z.%"']*                                    # mm, deg, in., ", %, DL
      | TRUE
      | FALSE                                               # how Visio renders FlipX
    )$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MAIN_NS = "{http://schemas.microsoft.com/office/visio/2012/main}"
_DOC_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


@dataclass(frozen=True)
class CellObservation:
    """One ShapeSheet cell, as one side states it.

    `formula` is what the side says the cell's formula is: `Width*0.5`, or the
    constant itself. `constant` is that formula's value in internal units when
    the formula is nothing but a literal, and None when it is an expression.
    `result` is what the formula evaluates to, in internal units, and only the
    COM side can fill it in.

    `constant` is what makes the two sides comparable on a cell holding a plain
    number: they spell the same constant differently, and a literal formula
    evaluates to itself, so its result is that constant in internal units and no
    unit parser is needed. See "Formula and result" in
    tests/fixtures/visio_observations/README.md.
    """

    name: str
    formula: str = ""
    constant: float | None = None
    result: float | None = None


def _literal_constant(formula: str, internal_units_value: float | None) -> float | None:
    """The value of a formula that is nothing but a literal, in internal units.

    Both readers go through here, so both classify a formula the same way. A
    side that decided for itself which of its cells held a constant could call
    `0` a literal where the other called `FALSE` an expression, and the
    comparison would then report a difference on every shape in every file.
    """
    if internal_units_value is None or not _LITERAL.match(formula.strip()):
        return None
    return internal_units_value


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
    cells: tuple[CellObservation, ...] = ()

    @property
    def cells_by_name(self) -> dict[str, CellObservation]:
        return {cell.name: cell for cell in self.cells}

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
        _compare_cells(expected_label, actual_label, index, in_expected, in_actual, out)


def _compare_cells(
    expected_label: str,
    actual_label: str,
    index: int,
    expected: ShapeObservation,
    actual: ShapeObservation,
    out: list[Difference],
) -> None:
    """Compare the cells that place a shape.

    Three things are compared and one is not, and the one that is not is the
    point of this docstring.

    Presence, in both directions. Both sides state a cell exactly when the shape
    has one - Visio through `CellExistsU`, the package through its XML and its
    masters - so a cell on one side only means the writer dropped it or invented
    it, and either moves the shape. Measured across the recorded corpus: 1371
    cell pairs, no presence mismatch.

    Whether the cell holds a literal or an expression. Visio's renderer never
    turns one into the other, so this is a real comparison, and it catches the
    failure the issue behind these cells named: a formula replaced by the number
    it happened to evaluate to has stopped tracking what it referred to, and the
    shape moves the next time that changes. Measured across the corpus: no kind
    mismatch either.

    A literal's value, as a number in internal units, to `PLACEMENT_TOLERANCE`.
    This is where a shape that moved gets caught. 803 of the 1371 pairs.

    Not the text of an expression. `Cell.FormulaU` is Visio's rendering of a
    formula, not the text the file holds, and the two differ on correct files:
    measured against Visio 16.0, `GUARD(0DA)` comes back as `GUARD(0 deg)`,
    `Height*0.0` as `Height*0`, a 15-digit coefficient reprinted to 14, and a
    master's `Sheet.5!Width` rebound to the page instance's `Sheet.7!Width`.
    Comparing those as strings is not comparing the same pair, and normalising
    until they match would mean reimplementing Visio's formula printer from
    examples - unbounded, and every rule guessed at is a place a real difference
    could hide. So the 568 expression pairs are recorded and printed, and no
    claim is made that they agreed. See "Formula and result" in
    tests/fixtures/visio_observations/README.md.

    Results are not compared either, for a different reason: only Visio can
    produce one. See the same section.
    """
    mine = expected.cells_by_name
    theirs = actual.cells_by_name
    for name in sorted(set(mine) | set(theirs)):
        in_expected = mine.get(name)
        in_actual = theirs.get(name)
        locus = f"page {index} shape {expected.id} cell {name}"
        if in_expected is None or in_actual is None:
            present, absent = (expected_label, actual_label) if in_actual is None else (actual_label, expected_label)
            stated = in_expected or in_actual
            out.append(
                Difference(
                    kind="cell-missing",
                    locus=locus,
                    detail=(f"{present} states {name}={_cell_text(stated)}; {absent} has no such cell on this shape"),
                )
            )
            continue
        if (in_expected.constant is None) != (in_actual.constant is None):
            out.append(
                Difference(
                    kind="cell-formula",
                    locus=locus,
                    detail=(
                        f"one side states a constant and the other an expression: "
                        f"{expected_label} {_cell_text(in_expected)}, {actual_label} {_cell_text(in_actual)}. "
                        "A formula replaced by the number it happened to evaluate to stops tracking what it "
                        "referred to, and the shape moves the next time that changes."
                    ),
                )
            )
            continue
        if in_expected.constant is None:
            # Both sides hold an expression. Recorded, printed above wherever
            # this cell turns up in another difference, and deliberately not
            # compared - see the docstring.
            continue
        if not math.isclose(
            in_expected.constant,
            in_actual.constant,
            rel_tol=PLACEMENT_TOLERANCE,
            abs_tol=PLACEMENT_TOLERANCE,
        ):
            out.append(
                Difference(
                    kind="cell-value",
                    locus=locus,
                    detail=(
                        f"{expected_label} {_cell_text(in_expected)}, {actual_label} {_cell_text(in_actual)} "
                        f"(internal units, tolerance {PLACEMENT_TOLERANCE:g})"
                    ),
                )
            )


def _cell_text(cell: CellObservation) -> str:
    """Render a cell for a message: what it says, and where that puts the shape.

    The result is appended only where it adds something. A literal formula
    evaluates to itself, so printing it twice would pad every constant
    difference with the number already on the line.
    """
    said = f"{cell.formula!r}" if cell.constant is None else f"{cell.constant!r}"
    if cell.result is None or cell.result == cell.constant:
        return said
    return f"{said} (result {cell.result!r})"


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
    masters = _master_catalogue(archive)
    pages: list[PageObservation] = []
    for index, (name, background, part) in enumerate(_page_parts(archive), start=1):
        if part is None or part not in archive.namelist():
            pages.append(PageObservation(index=index, name=name, unresolved=True, background=background))
            continue
        contents = ET.fromstring(archive.read(part))
        shapes = tuple(
            sorted(
                _shapes_in(contents.find(f"{_MAIN_NS}Shapes"), parent_id=None, masters=masters, master_id=None),
                key=_by_shape,
            )
        )
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


_Master = tuple["ET.Element | None", dict[str, "ET.Element"]]


def _master_catalogue(archive: zipfile.ZipFile) -> dict[str, _Master]:
    """Every master's shapes, keyed by master id, for inheritance lookups.

    Each entry is the master's first top-level shape - what a page shape with
    `Master='n'` inherits from - and every shape in the master by id, which is
    what a group member's `MasterShape='n'` points at.
    """
    catalogue: dict[str, _Master] = {}
    masters_xml = "visio/masters/masters.xml"
    if masters_xml not in archive.namelist():
        return catalogue
    relationships = _relationships(archive, "visio/masters/_rels/masters.xml.rels")
    for master in ET.fromstring(archive.read(masters_xml)):
        identifier = master.attrib.get("ID")
        rel = master.find(f"{_MAIN_NS}Rel")
        target = None if rel is None else relationships.get(rel.attrib.get(f"{_DOC_REL_NS}id", ""))
        if identifier is None or target is None or target not in archive.namelist():
            continue
        contents = ET.fromstring(archive.read(target))
        by_id: dict[str, ET.Element] = {}
        _index_shapes(contents.find(f"{_MAIN_NS}Shapes"), by_id)
        catalogue[identifier] = (contents.find(f"{_MAIN_NS}Shapes/{_MAIN_NS}Shape"), by_id)
    return catalogue


def _index_shapes(container: ET.Element | None, into: dict[str, ET.Element]) -> None:
    if container is None:
        return
    for shape in container.findall(f"{_MAIN_NS}Shape"):
        identifier = shape.attrib.get("ID")
        if identifier is not None:
            into[identifier] = shape
        _index_shapes(shape.find(f"{_MAIN_NS}Shapes"), into)


def _shapes_in(
    container: ET.Element | None,
    parent_id: int | None,
    masters: dict[str, _Master],
    master_id: str | None,
) -> list[ShapeObservation]:
    """Walk a `<Shapes>` element, descending into groups.

    A shape carrying `Del='1'` is a deletion of an instance the master would
    otherwise contribute. Visio does not show it, so recording it here would
    report a difference on every file that has ever had a group member removed.

    `master_id` travels down the tree because only the outermost shape names the
    master; a group member names a shape *inside* that master with `MasterShape`
    and would otherwise have nothing to resolve against.
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
        inherited = shape.attrib.get("Master") or master_id
        found.append(
            ShapeObservation(
                id=shape_id,
                parent_id=parent_id,
                name=shape.attrib.get("NameU", ""),
                cells=_placement_cells_of(shape, masters, inherited),
            )
        )
        found.extend(_shapes_in(shape.find(f"{_MAIN_NS}Shapes"), parent_id=shape_id, masters=masters, master_id=inherited))
    return found


def _placement_cells_of(shape: ET.Element, masters: dict[str, _Master], master_id: str | None) -> tuple[CellObservation, ...]:
    """What this package says about where the shape is, master inheritance included.

    A cell the shape does not state itself it inherits, and a stencil shape
    states almost nothing: leaving inheritance out would report a difference
    against Visio on every instance of every master in the corpus.
    """
    sources = [shape]
    master = _master_source(shape, masters, master_id)
    if master is not None:
        sources.append(master)
    found = [cell for cell in (_resolve_cell(name, sources) for name in PLACEMENT_CELLS) if cell is not None]
    return tuple(sorted(found, key=lambda cell: cell.name))


def _master_source(shape: ET.Element, masters: dict[str, _Master], master_id: str | None) -> ET.Element | None:
    """The shape in the master that this shape inherits from, if any.

    A shape inherits only when it says so. `Master` names the master and takes
    its root shape; `MasterShape` names one shape inside the master an ancestor
    already chose. A shape carrying neither was added to the group locally and
    inherits nothing - handing it the master's root would give it the *group's*
    position and size, and the comparison would then insist Visio put it there.
    """
    if master_id is None or master_id not in masters:
        return None
    root, by_id = masters[master_id]
    master_shape = shape.attrib.get("MasterShape")
    if master_shape is not None:
        return by_id.get(master_shape)
    return root if shape.attrib.get("Master") is not None else None


def _resolve_cell(name: str, sources: list[ET.Element]) -> CellObservation | None:
    """Read one cell through the inheritance chain, or None if nobody states it.

    The rules are Visio's. A local `<Cell>` carrying an `F` wins outright. A
    local `<Cell>` carrying only a `V` also wins - stating a constant is how a
    shape overrides the master's formula - so the chain is not followed for it.
    `F='Inh'` is the one case that means "the formula is the master's", and only
    there does the lookup carry on, keeping the local `V`, which is that master
    formula already evaluated in this shape's context.

    `V` is in internal units whatever `U` beside it says: `U` records the unit
    the value was typed in, not the unit it is stored in.
    """
    # The first `V` found, which is the local one where the shape states the
    # cell: that is the formula evaluated in *this* shape's context, and the
    # master's copy was evaluated in the master's.
    evaluated: str | None = None
    inheriting = False
    for source in sources:
        cell = source.find(f"{_MAIN_NS}Cell[@N='{name}']")
        if cell is None:
            continue
        if evaluated is None:
            evaluated = cell.attrib.get("V")
        stated = cell.attrib.get("F")
        if stated is None:
            return _package_cell(name, cell.attrib.get("V", ""), evaluated)
        if stated != "Inh":
            return _package_cell(name, stated, evaluated)
        inheriting = True
    if not inheriting:
        return None
    return CellObservation(name=name, formula=_UNRESOLVED_INHERIT, constant=None, result=None)


def _package_cell(name: str, formula: str, value: str | None) -> CellObservation:
    """One cell as the package states it: a formula, and no result.

    The package has no evaluator, so `result` stays None. `constant` comes from
    `V`, which is the same quantity in internal units.
    """
    return CellObservation(
        name=name,
        formula=formula,
        constant=_literal_constant(formula, _as_float(value)),
        result=None,
    )


def _as_float(value: Any) -> float | None:
    """A cell's number, from either side, or None where that side stated none.

    `bool` is excluded deliberately: `float(True)` is 1.0, so a JSON `true` where
    a measurement belongs would be read as a shape sitting at one inch rather
    than as the malformed record it is.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except ValueError:
        return None


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


def _com_cells(records: list[dict[str, Any]]) -> tuple[CellObservation, ...]:
    """One shape's cells as Visio reported them.

    `result` is `Cell.ResultIU`, in internal units. `constant` is that same
    number, but only where `Cell.FormulaU` is a literal - the one case where the
    result is not an evaluation of anything and can stand in for the formula the
    package writes in a different unit.
    """
    cells = []
    for record in records:
        formula = str(record.get("formula", ""))
        result = _as_float(record.get("result"))
        cells.append(
            CellObservation(
                name=str(record["name"]),
                formula=formula,
                constant=_literal_constant(formula, result),
                result=result,
            )
        )
    return tuple(sorted(cells, key=lambda cell: cell.name))


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
                        cells=_com_cells(shape.get("cells", [])),
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
