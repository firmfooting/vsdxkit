"""Relations that hold for every document, so none of them needs an oracle.

Deciding whether an output is correct needs something that already knows the
answer: a Visio licence, a recording, or a hand-written expectation per fixture.
Deciding whether two outputs stand in the relation they must needs none of
those. Open a file and save it, and the structure that comes back is the
structure that went in; copy a shape and delete the copy, and the package is the
one you started with. Neither claim mentions any particular document, so both
can be asserted over the whole corpus, and over a file nobody has looked at.

That is metamorphic testing (Chen). It does not replace the COM harness, which
answers the one question the format cannot - whether Visio agrees. It needs no
Windows, no COM and no recording that can go stale, so a relation reaches the
next fixture with nothing recorded for it.

Equality is `visio_observation.compare`, which is a total account of pages,
shape ids, grouping and glue. Two things it deliberately is not:

* It is not byte equality. A save may requote an attribute or respell an empty
  element and still be the same document, so a relation stated over bytes would
  fail on drift nobody cares about. Where byte equality is the claim - saving
  twice, or an edit that undoes itself - `package_manifest` is used as well.
* It aligns shapes by id and treats glue as a multiset, so it says nothing
  about the order parts are written in. A relation here can therefore see a
  shape that was dropped, reparented or renumbered, but not one that merely
  moved within its `<Shapes>` element.

`tests/test_package_manifest.py` states the round trip at the byte and
canonical-XML level, under a recorded drift allowance. What follows is the
structural statement of the same property, plus the relations about editing -
copying, deleting, reordering - that the manifest tests say nothing about.
"""

from __future__ import annotations

import dataclasses
import os
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable

import pytest
from helpers.package_manifest import PackageManifest, manifest_differences
from helpers.visio_observation import (
    Observation,
    PageObservation,
    compare,
    format_differences,
    observation_from_package,
)

import vsdx

BASEDIR = os.path.dirname(os.path.realpath(__file__))
PACKAGE_SUFFIXES = (".vsdx", ".vsdm")

_MAIN_NS = "{http://schemas.microsoft.com/office/visio/2012/main}"
_PAGES_PART = "visio/pages/pages.xml"

# The cells a connector glues through. `Page.delete_shape` takes a connector
# with the shape it is glued to, and only on a begin/end relationship, so an
# expectation built here has to draw the same line.
_GLUE_CELLS = ("BeginX", "EndX")


def _fixture_packages() -> list[str]:
    """Every Visio package under `tests/`, as a path relative to it."""
    found = []
    for root, _, names in os.walk(BASEDIR):
        for name in names:
            if name.endswith(PACKAGE_SUFFIXES):
                found.append(os.path.relpath(os.path.join(root, name), BASEDIR))
    return sorted(found)


FIXTURE_PACKAGES = _fixture_packages()


# --------------------------------------------------------------------------
# performing the operations the relations are stated over
# --------------------------------------------------------------------------


def _saved(source: str, destination: str, edit: Callable[[vsdx.VisioFile], None] | None = None) -> str:
    """Open `source`, apply `edit` if there is one, save to `destination`.

    Every relation below is a pair of calls to this, so the only difference
    between the two sides of a comparison is the edit.
    """
    with vsdx.VisioFile(source) as vis:
        if edit is not None:
            edit(vis)
        vis.save_vsdx(destination)
    return destination


def _output(tmp_path, package_path: str, suffix: str) -> str:
    """A path in tmp_path named after the fixture it came from.

    The name matters beyond readability: conftest validates every package left
    in tmp_path and excuses defects an output inherited from its input, and it
    recognises the inheritance by the name. `test5_master.vsdx` ships with seven
    parts its relationships promise and does not contain, and an output called
    anything else would be blamed for them.
    """
    stem, extension = os.path.splitext(os.path.basename(package_path))
    return str(tmp_path / f"{stem}-{suffix}{extension}")


def _shape_ids(source: str) -> dict[int, list[int]]:
    """Every shape on each page, group members included, in the order the part lists them.

    Read through the library rather than from an observation because the two
    disagree by design: an observation drops shapes marked `Del="1"`, which the
    page still holds and `Page.all_shapes` still returns. Deleting by position
    off the shorter list would delete a different shape than the one the
    expectation was built for, so the position and the id have to come from the
    same list.
    """
    with vsdx.VisioFile(source) as vis:
        return {index: [int(shape.ID) for shape in page.all_shapes] for index, page in enumerate(vis.pages)}


def _page_part_names(source: str) -> dict[int, str]:
    """The package member each page's contents live in, per zero-based page index.

    Taken from the library, which is also the thing under test, so this cannot
    say whether a page was resolved to the right part - that is what the
    reordering relation is for. It says which part an edit to a given page is
    allowed to touch, and that is enough to catch an edit that reaches across
    pages.
    """
    with vsdx.VisioFile(source) as vis:
        return {index: f"visio/pages/{os.path.basename(page.filename)}" for index, page in enumerate(vis.pages)}


def _with_pages_reordered(source: str, destination: str, order: list[int]) -> str:
    """Copy the package, listing its pages in `order`.

    The library exposes no way to reorder pages, so the permutation is applied
    to the input instead, with `zipfile` and `ElementTree` alone - the same
    independence the helpers in `tests/helpers` keep. Reordering the input and
    reordering through an API are the same metamorphic transformation; what is
    under test either way is that a saved page carries its identity in the part
    it points at rather than in where it sits.

    Only `visio/pages/pages.xml` is rewritten. That is the order of record:
    `docProps/app.xml` holds a list of page names that Visio rebuilds on save,
    and leaving it alone keeps the transformation to exactly the one part whose
    order the relation is about.

    `ET.tostring` writes the Visio namespace unprefixed because importing vsdx
    registers it process-wide. Nothing here registers a prefix of its own: that
    is a whole-process side effect, and a test has no business leaving one
    behind for whatever runs next. If that registration ever moves, this part
    comes back with generated prefixes, which changes how it is spelled and not
    what it says - everything downstream resolves namespaces by URI.
    """
    with zipfile.ZipFile(source) as archive:
        members = [(info, archive.read(info.filename)) for info in archive.infolist()]
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as out:
        for info, data in members:
            if info.filename == _PAGES_PART:
                root = ET.fromstring(data)
                # the slots the Page elements occupy, so anything else the part
                # holds keeps the position it had
                slots = [index for index, child in enumerate(root) if child.tag == f"{_MAIN_NS}Page"]
                pages = [root[slot] for slot in slots]
                for slot, source_position in zip(slots, order, strict=True):
                    root[slot] = pages[source_position]
                data = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
            out.writestr(info, data)
    return destination


# --------------------------------------------------------------------------
# building the expectations
# --------------------------------------------------------------------------


def _assert_same_structure(relation: str, package_path: str, expected: Observation, actual: Observation) -> None:
    differences = compare(expected, actual)
    assert not differences, (
        f"{relation} does not hold for {package_path}:\n{format_differences(differences)}\n\n"
        "This relation holds for any document, so the failure is about the operation, not about "
        "this fixture."
    )


def _assert_same_package(relation: str, package_path: str, expected: str, actual: str) -> None:
    differences = manifest_differences(PackageManifest.from_path(expected), PackageManifest.from_path(actual))
    assert not differences, f"{relation} does not hold for {package_path}; these parts differ: " + ", ".join(
        f"{member} ({', '.join(kinds)})" for member, kinds in differences.items()
    )


def _descendants(page: PageObservation, shape_id: int) -> set[int]:
    """A shape and everything nested inside it, however deep."""
    inside = {shape_id}
    growing = True
    while growing:
        growing = False
        for shape in page.shapes:
            if shape.parent_id in inside and shape.id not in inside:
                inside.add(shape.id)
                growing = True
    return inside


def _shapes_a_delete_takes(page: PageObservation, shape_id: int) -> set[int]:
    """Every shape that must disappear when `shape_id` is deleted, and no more.

    The shape's own subtree, plus the connectors glued to any of it - one left
    behind has nothing to glue to - plus whatever those connectors contain.

    This is a transcription of the rule `Page.delete_shape` follows, not an
    independent derivation of it: there is no second implementation to derive
    one from. So it catches a delete that does not do what the rule says -
    misses a connector, takes a bystander, forgets a record - and it cannot
    catch the rule itself being wrong. What it does have over reading the
    answer back from the output is that it is computed before the output is
    looked at, over a different reading of the package.
    """
    doomed = _descendants(page, shape_id)
    connectors = {
        connect.from_shape for connect in page.connects if connect.to_shape in doomed and connect.from_cell in _GLUE_CELLS
    }
    for connector in connectors:
        doomed |= _descendants(page, connector)
    return doomed


def _without(observation: Observation, page_index: int, doomed: Iterable[int]) -> Observation:
    """The same observation with `doomed` gone from one page, and nothing else moved."""
    gone = set(doomed)
    pages = []
    for page in observation.pages:
        if page.index != page_index:
            pages.append(page)
            continue
        pages.append(
            dataclasses.replace(
                page,
                shapes=tuple(shape for shape in page.shapes if shape.id not in gone),
                connects=tuple(
                    connect for connect in page.connects if connect.from_shape not in gone and connect.to_shape not in gone
                ),
            )
        )
    return Observation(label="expected", pages=tuple(pages))


def _copy_first_shape(page_index: int) -> Callable[[vsdx.VisioFile], None]:
    """Copy the first top-level shape of a page - the edit that draws on its id allocator."""

    def edit(vis: vsdx.VisioFile) -> None:
        vis.pages[page_index].child_shapes[0].copy()

    return edit


def _only(page: PageObservation, label: str) -> Observation:
    """One page on its own, for a failure message about that page alone."""
    return Observation(label=label, pages=(page,))


def _pages_with_a_top_level_shape(observation: Observation) -> list[int]:
    return [index for index, page in enumerate(observation.pages) if any(shape.parent_id is None for shape in page.shapes)]


# --------------------------------------------------------------------------
# the relations
# --------------------------------------------------------------------------


def test_the_corpus_can_exercise_every_relation():
    """Guard against relations that pass because they never ran.

    Most relations below need something of their input - a second page to
    permute, a shape to copy - and skip or loop zero times without it. A
    discovery bug, or a corpus that lost its multi-page fixtures, would turn
    them green while testing nothing.
    """
    observations = [observation_from_package(os.path.join(BASEDIR, name)) for name in FIXTURE_PACKAGES]
    assert len(FIXTURE_PACKAGES) > 20
    assert any(name.endswith(".vsdm") for name in FIXTURE_PACKAGES)
    assert sum(1 for o in observations if len(o.pages) > 1) >= 6, "no fixture left to permute"
    assert sum(1 for o in observations if any(p.connects for p in o.pages)) >= 3, "no glue left to preserve"
    assert sum(1 for o in observations if any(s.parent_id is not None for p in o.pages for s in p.shapes)) >= 6, (
        "no grouped shapes left, so no delete cascades into a subtree"
    )
    # the copy and delete relations skip a package with no shapes on page 1;
    # one stencil-only fixture in this corpus is that case
    assert sum(1 for o in observations if o.pages[0].shapes) >= 25, "nothing left to copy or delete"
    # the branch worth guarding is the one where a delete takes more than the
    # shape's own subtree; counting fixtures that have glue does not establish
    # that any of that glue reaches a shape a delete goes near
    assert any(
        _shapes_a_delete_takes(page, shape.id) != _descendants(page, shape.id)
        for observation in observations
        for page in observation.pages
        for shape in page.shapes
    ), "no delete in the corpus cascades past the shape's own subtree"


@pytest.mark.parametrize("package_path", FIXTURE_PACKAGES)
def test_a_round_trip_preserves_the_structure(package_path, vsdx_copy, tmp_path):
    """Open and save with no edits: same pages, same ids, same grouping, same glue.

    The bytes are allowed to move and `test_package_manifest.py` says by how
    much. Nothing structural is allowed to move.
    """
    source = vsdx_copy(package_path)
    saved = _saved(source, _output(tmp_path, package_path, "roundtrip"))
    _assert_same_structure(
        "round-trip preserves structure",
        package_path,
        observation_from_package(source, "input"),
        observation_from_package(saved, "output"),
    )


@pytest.mark.parametrize("package_path", FIXTURE_PACKAGES)
def test_saving_the_output_again_changes_nothing(package_path, vsdx_copy, tmp_path):
    """A second save must produce the first save's package, to the byte.

    The relation is structural; the package is compared as well, because every
    difference between two saves of the same unedited document is state that
    leaked from one save into the next, and some of that is invisible to a
    structural comparison: an element reordered, a part written twice, an id
    counter left advanced.
    """
    source = vsdx_copy(package_path)
    once = _saved(source, _output(tmp_path, package_path, "saved-once"))
    twice = _saved(once, _output(tmp_path, package_path, "saved-twice"))
    _assert_same_structure(
        "saving is idempotent",
        package_path,
        observation_from_package(once, "first save"),
        observation_from_package(twice, "second save"),
    )
    _assert_same_package("saving is idempotent", package_path, once, twice)


@pytest.mark.parametrize("package_path", FIXTURE_PACKAGES)
def test_copying_a_shape_and_deleting_the_copy_restores_the_package(package_path, vsdx_copy, tmp_path):
    """Copy then delete is a no-op, down to the bytes.

    An operation and its inverse need no expectation at all: the output has to
    be the input. The package is compared part by part because the plausible
    failures here - a `Shapes` element left behind, a `Connect` record removed
    too eagerly, a blank line where the copy was - are all invisible to a
    structural comparison.
    """
    source = vsdx_copy(package_path)
    untouched = _saved(source, _output(tmp_path, package_path, "untouched"))
    pages = _shape_ids(source)
    if not pages.get(0):
        pytest.skip("page 1 holds no shape to copy")

    def copy_then_delete(vis: vsdx.VisioFile) -> None:
        page = vis.pages[0]
        copy = page.child_shapes[0].copy()
        assert int(copy.ID) not in pages[0], "the copy reused an id the page was already using"
        page.delete_shape(copy)

    restored = _saved(source, _output(tmp_path, package_path, "copy-deleted"), copy_then_delete)
    _assert_same_structure(
        "copy then delete is a no-op",
        package_path,
        observation_from_package(untouched, "untouched"),
        observation_from_package(restored, "copy then delete"),
    )
    _assert_same_package("copy then delete is a no-op", package_path, untouched, restored)


@pytest.mark.parametrize("package_path", FIXTURE_PACKAGES)
def test_deleting_a_copy_made_before_the_last_save_restores_the_package(package_path, vsdx_copy, tmp_path):
    """The same pair with a save in the middle, which is where the ids are tested.

    Inside one session the page's id high-water mark is carried in memory.
    Reopened, it has to be rebuilt from the shapes the file holds, because a
    .vsdx records no mark of its own. A mark rebuilt too low hands out an id the
    page is already using; rebuilt too high it skips one, and neither shows up
    until something else is created - so the id the next copy receives is
    asserted as well as the package, which is what the restored package means
    in the only terms a later session sees.
    """
    source = vsdx_copy(package_path)
    untouched = _saved(source, _output(tmp_path, package_path, "before-copy"))
    if not _shape_ids(source).get(0):
        pytest.skip("page 1 holds no shape to copy")

    copied_id = 0

    def copy_a_shape(vis: vsdx.VisioFile) -> None:
        nonlocal copied_id
        copied_id = int(vis.pages[0].child_shapes[0].copy().ID)

    with_copy = _saved(source, _output(tmp_path, package_path, "with-copy"), copy_a_shape)

    def delete_the_copy(vis: vsdx.VisioFile) -> None:
        page = vis.pages[0]
        reopened = [shape for shape in page.all_shapes if int(shape.ID) == copied_id]
        assert reopened, f"the copy with id {copied_id} is not on page 1 after the save"
        page.delete_shape(reopened[0])

    restored = _saved(with_copy, _output(tmp_path, package_path, "copy-deleted-later"), delete_the_copy)

    _assert_same_structure(
        "deleting a copy from an earlier session is a no-op",
        package_path,
        observation_from_package(untouched, "before the copy"),
        observation_from_package(restored, "after deleting it"),
    )
    _assert_same_package("deleting a copy from an earlier session is a no-op", package_path, untouched, restored)

    with vsdx.VisioFile(restored) as vis:
        next_id = int(vis.pages[0].child_shapes[0].copy().ID)
    assert next_id == copied_id, (
        f"the next copy on page 1 of {package_path} got id {next_id}, not the {copied_id} the deleted "
        "copy had: the id mark rebuilt from the file is not where it was"
    )


@pytest.mark.parametrize("package_path", FIXTURE_PACKAGES)
def test_reordering_pages_permutes_them_and_changes_nothing_within_them(package_path, vsdx_copy, tmp_path):
    """Listing the pages in a different order moves the pages and nothing else.

    An unedited save cannot settle this on its own. Every page part is written
    back where it came from, so a library that had paired pages with parts by
    position would still produce the reordered file unchanged, and the
    comparison would pass. The relation therefore edits after reordering - a
    shape copied onto the page that is now first - and asks where the copy
    landed. A part name guessed from the page number, or a relationship id
    reissued by position, puts it under another page's name.
    """
    source = vsdx_copy(package_path)
    in_order = _saved(source, _output(tmp_path, package_path, "in-order"))
    observed = observation_from_package(in_order, "in order")
    if len(observed.pages) < 2:
        pytest.skip("a permutation of one page is the identity")

    order = list(reversed(range(len(observed.pages))))
    reordered_source = _with_pages_reordered(source, _output(tmp_path, package_path, "reordered-input"), order)
    reordered = _saved(reordered_source, _output(tmp_path, package_path, "reordered"))

    expected = Observation(
        label="expected",
        pages=tuple(
            dataclasses.replace(observed.pages[source_position], index=position + 1)
            for position, source_position in enumerate(order)
        ),
    )
    _assert_same_structure(
        "page order is a permutation", package_path, expected, observation_from_package(reordered, "reordered")
    )

    if not any(shape.parent_id is None for shape in expected.pages[0].shapes):
        pytest.skip("the page now first holds no top-level shape to copy")
    edited = _saved(reordered, _output(tmp_path, package_path, "reordered-edited"), _copy_first_shape(0))
    after = observation_from_package(edited, "after editing the page now first")
    for index, (was, now) in enumerate(zip(expected.pages, after.pages, strict=True)):
        if index == 0:
            assert len(now.shapes) > len(was.shapes), (
                f"copying onto the first page of the reordered {package_path} added nothing there; "
                "the page was paired with some other page's part"
            )
            assert {shape.id for shape in was.shapes} <= {shape.id for shape in now.shapes}, (
                f"copying onto the first page of the reordered {package_path} displaced what was on it"
            )
            continue
        assert was == now, (
            f"copying onto the first page of the reordered {package_path} changed page {index + 1}:\n"
            + format_differences(compare(_only(was, "reordered"), _only(now, "after the copy")))
        )


# `Page.delete_shape` removes the Connect records naming the deleted shape but
# not the `Sheet.N!` references other shapes make to it, so deleting a swimlane
# leaves each container's `Relationships` dependency list naming a sheet that has
# gone. The `stale-sheet-reference` rule added with #328 is what made that
# visible. Repairing a formula whose subject has been deleted is a different
# change from remapping one whose subject has moved, so the single fixture that
# reaches it is named here rather than the rule being weakened for everything.
# Tracked as #334; when the delete sweep lands, this entry and the marks it
# drives go.
_DELETE_LEAVES_STALE_REFERENCES = frozenset({"fixtures/com_reference/s05_swimlanes_cfflow.vsdx"})

_DELETE_PACKAGES = [
    pytest.param(
        name,
        marks=[pytest.mark.allow_invalid_package("stale-sheet-reference")] if name in _DELETE_LEAVES_STALE_REFERENCES else [],
    )
    for name in FIXTURE_PACKAGES
]


@pytest.mark.parametrize("package_path", _DELETE_PACKAGES)
def test_deleting_a_shape_removes_exactly_it(package_path, vsdx_copy, tmp_path):
    """Every shape in the corpus, deleted in turn, takes only what belongs to it.

    What goes is the shape, what it contains, and the connectors that were glued
    to any of that. What stays is everything else, with the ids and the parents
    it had before. Only one part of the package may change, which is where a
    delete that reached across pages would be caught.

    Group members are deleted as well as top-level shapes, and are the harder
    case: a member goes with its group when the group is deleted, so the code
    that removes one on its own is reached only by deleting it directly.

    What this does not reach: no fixture in the corpus glues a connector to a
    shape inside a group, so the sweep that removes a record naming a group
    child never has anything to remove. That needs a fixture, not a relation.
    """
    source = vsdx_copy(package_path)
    untouched = _saved(source, _output(tmp_path, package_path, "before-delete"))
    before = observation_from_package(untouched, "before delete")
    # hoisted: canonicalising every part of the untouched package costs more
    # than the delete does, and it is the same package every time round
    before_manifest = PackageManifest.from_path(untouched)
    parts = _page_part_names(source)
    deleted_any = False

    for page_index, shape_ids in _shape_ids(source).items():
        page = before.pages[page_index]
        for position, shape_id in enumerate(shape_ids):
            if shape_id not in {shape.id for shape in page.shapes}:
                continue  # a shape marked Del="1": present in the part, not in the document

            def delete(vis: vsdx.VisioFile, page_index=page_index, position=position, shape_id=shape_id) -> None:
                page = vis.pages[page_index]
                target = page.all_shapes[position]
                # the position and the id were read off the same list in an
                # earlier session; if they have come apart, this deletes a shape
                # the expectation below was not built for
                assert int(target.ID) == shape_id, f"position {position} on page {page_index + 1} is not shape {shape_id}"
                page.delete_shape(target)

            after = _saved(source, _output(tmp_path, package_path, f"minus-{page_index}-{shape_id}"), delete)
            doomed = _shapes_a_delete_takes(page, shape_id)
            deleted_any = True
            _assert_same_structure(
                f"deleting shape {shape_id} from page {page_index + 1} removes exactly it",
                package_path,
                _without(before, page.index, doomed),
                observation_from_package(after, "after delete"),
            )
            changed = manifest_differences(before_manifest, PackageManifest.from_path(after))
            assert set(changed) == {parts[page_index]}, (
                f"deleting shape {shape_id} from page {page_index + 1} of {package_path} rewrote "
                f"{sorted(changed)}, not just {parts[page_index]}"
            )

    if not deleted_any:
        pytest.skip("no page holds a shape to delete")


@pytest.mark.parametrize("package_path", FIXTURE_PACKAGES)
def test_editing_one_page_leaves_every_other_page_untouched(package_path, vsdx_copy, tmp_path):
    """Adding a shape to one page renumbers nothing on any other.

    Ids are page-scoped, so an allocator that ran over the document instead of
    the page would renumber a page nobody edited, and with it the ids that
    page's own glue names. Each page in turn is the edited one, so no page is
    only ever the bystander.

    The edited page is held to the weaker half of the relation: it gained
    shapes, and how many depends on whether the copied shape was a group, but
    every shape it already had must still be there, under the same parent, with
    the same name and the same glue.
    """
    source = vsdx_copy(package_path)
    untouched = _saved(source, _output(tmp_path, package_path, "before-edit"))
    before = observation_from_package(untouched, "before edit")
    before_manifest = PackageManifest.from_path(untouched)
    parts = _page_part_names(source)
    if len(before.pages) < 2:
        pytest.skip("one page cannot be disturbed by an edit to another")

    editable = _pages_with_a_top_level_shape(before)
    if not editable:
        pytest.skip("no page holds a top-level shape to copy")

    for page_index in editable:
        after_path = _saved(source, _output(tmp_path, package_path, f"edited-{page_index}"), _copy_first_shape(page_index))
        after = observation_from_package(after_path, "after edit")
        assert len(after.pages) == len(before.pages), f"editing page {page_index + 1} changed the page count"
        for index, (was, now) in enumerate(zip(before.pages, after.pages, strict=True)):
            if index != page_index:
                assert was == now, (
                    f"editing page {page_index + 1} of {package_path} changed page {index + 1}:\n"
                    # one page against its own counterpart: diffing the whole
                    # document here would print the edited page's differences
                    # too, which are the ones this assertion just excluded
                    + format_differences(compare(_only(was, "before edit"), _only(now, "after edit")))
                )
                continue
            still_there = {shape.id: shape for shape in now.shapes}
            for shape in was.shapes:
                assert still_there.get(shape.id) == shape, (
                    f"editing page {page_index + 1} of {package_path} renumbered or moved shape {shape.id} on that same page"
                )
            # Counter, not set: `visio_observation` records a duplicated
            # `Connect` as two records, and a set would call the page that says
            # it twice the same as the page that says it once
            kept = Counter(now.connects)
            kept.subtract(Counter(was.connects))
            assert all(count >= 0 for count in kept.values()), (
                f"editing page {page_index + 1} of {package_path} dropped glue it did not touch"
            )
        changed = manifest_differences(before_manifest, PackageManifest.from_path(after_path))
        assert set(changed) == {parts[page_index]}, (
            f"copying a shape on page {page_index + 1} of {package_path} rewrote {sorted(changed)}, "
            f"not just {parts[page_index]}"
        )
