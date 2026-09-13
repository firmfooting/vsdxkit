"""What `PackageStore` promises about part names, promotion and bytes.

The expected side of every byte comparison here comes from `zipfile` reading
the fixture directly, never from the store reading it a second way. A
round-trip assertion whose two sides share a code path agrees with itself no
matter what that code path does.
"""

from __future__ import annotations

import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from helpers.broken_package import append_member, make_package

from vsdxkit.package import BytesPart, PackageLimitError, PackageLimits, PackageStore, XmlPart, canonical_hash

BASEDIR = os.path.dirname(os.path.realpath(__file__))
FIXTURE = "test1.vsdx"

PAGE_PART = "/visio/pages/page1.xml"
THUMBNAIL_PART = "/docProps/thumbnail.emf"
MARKER = "VsdxkitPromotionMarker"


def fixture_path() -> str:
    return os.path.join(BASEDIR, FIXTURE)


def members() -> dict[str, bytes]:
    """Every member of the fixture, read straight out of the archive."""
    with zipfile.ZipFile(fixture_path()) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


@pytest.fixture
def store() -> PackageStore:
    return PackageStore.open(fixture_path())


def _mutate(tree: ET.ElementTree[ET.Element]) -> ET.Element:
    root = tree.getroot()
    assert root is not None
    root.set(MARKER, "1")
    return root


# --------------------------------------------------------------------------
# part names
# --------------------------------------------------------------------------


def test_part_names_are_the_archive_members_made_absolute(store: PackageStore):
    """OPC part names carry a leading slash; archive member names do not."""
    assert store.names() == tuple(f"/{member}" for member in members())


def test_the_package_relationships_part_is_addressable(store: PackageStore):
    """`_rels/.rels` is a part name whose extension is `rels`, not a dotfile.

    `posixpath.splitext` reads it as a name with no extension, and any name
    handling built on that reads the part every package has as malformed.
    """
    assert store.read_bytes("/_rels/.rels") == members()["_rels/.rels"]


def test_the_content_types_part_is_addressable(store: PackageStore):
    """`[Content_Types].xml` is not a part, and its name is not a part name.

    OPC builds part names out of pchar, which excludes the brackets, which is
    why the specification calls this a package-level item instead. Every
    package has it and every writer has to address it, so the rules here admit
    it on purpose rather than by not having noticed.
    """
    assert store.read_bytes("/[Content_Types].xml") == members()["[Content_Types].xml"]


@pytest.mark.parametrize(
    "name",
    [
        "visio/document.xml",  # archive member name, not a part name
        "",
        "/",
        "/visio/document.xml/",
        "/visio//document.xml",
        "/visio/../evil.xml",
        "/visio/./document.xml",
        "/..",
        "/visio\\document.xml",  # would normalise onto /visio/document.xml
        "/C:/evil.xml",
    ],
)
def test_a_name_that_is_not_an_opc_part_name_is_refused(store: PackageStore, name: str):
    with pytest.raises(ValueError):
        store.read_bytes(name)


@pytest.mark.parametrize(
    "call",
    [
        lambda store, name: store.read_bytes(name),
        lambda store, name: store.read_xml(name),
        lambda store, name: store.require_xml(name),
        lambda store, name: store.write_bytes(name, b"<Doc/>"),
        lambda store, name: store.write_xml(name, ET.ElementTree(ET.Element("Doc"))),
        lambda store, name: store.part(name),
    ],
)
def test_every_way_into_the_store_checks_the_name(store: PackageStore, call):
    """A writer that skipped the check would put a part in that nothing can read."""
    with pytest.raises(ValueError):
        call(store, "visio/document.xml")


def test_an_absent_part_reads_as_none(store: PackageStore):
    assert store.read_bytes("/visio/pages/page99.xml") is None
    assert store.read_xml("/visio/pages/page99.xml") is None


def test_require_xml_names_the_part_it_could_not_find(store: PackageStore):
    with pytest.raises(ValueError, match=re.escape("/visio/pages/page99.xml")):
        store.require_xml("/visio/pages/page99.xml")


# --------------------------------------------------------------------------
# bytes
# --------------------------------------------------------------------------


def test_every_part_reads_back_byte_for_byte(store: PackageStore):
    read = {name: store.read_bytes(name) for name in store.names()}
    assert read == {f"/{member}": data for member, data in members().items()}


def test_write_bytes_appends_a_new_part_after_the_existing_ones(store: PackageStore):
    store.write_bytes("/visio/pages/page4.xml", b"<PageContents/>")
    assert store.names()[-1] == "/visio/pages/page4.xml"
    assert store.read_bytes("/visio/pages/page4.xml") == b"<PageContents/>"


def test_write_bytes_over_an_existing_part_keeps_its_position(store: PackageStore):
    before = store.names()
    store.write_bytes(PAGE_PART, b"<PageContents/>")
    assert store.names() == before
    assert store.read_bytes(PAGE_PART) == b"<PageContents/>"


def test_write_bytes_over_a_promoted_part_discards_the_tree(store: PackageStore):
    _mutate(store.require_xml(PAGE_PART))
    store.write_bytes(PAGE_PART, b"<PageContents/>")

    assert isinstance(store.part(PAGE_PART), BytesPart)
    reread = store.require_xml(PAGE_PART).getroot()
    assert reread is not None and MARKER not in reread.attrib


# --------------------------------------------------------------------------
# promotion
# --------------------------------------------------------------------------


def test_a_part_is_not_parsed_until_its_tree_is_asked_for(store: PackageStore):
    assert isinstance(store.part(PAGE_PART), BytesPart)
    store.read_bytes(PAGE_PART)
    assert isinstance(store.part(PAGE_PART), BytesPart)
    store.read_xml(PAGE_PART)
    assert isinstance(store.part(PAGE_PART), XmlPart)


def test_promotion_keeps_the_bytes_the_part_arrived_as(store: PackageStore):
    store.read_xml(PAGE_PART)
    promoted = store.part(PAGE_PART)
    assert isinstance(promoted, XmlPart)
    assert promoted.original_bytes == members()["visio/pages/page1.xml"]


def test_the_tree_is_authoritative_once_promoted(store: PackageStore):
    _mutate(store.require_xml(PAGE_PART))
    again = store.require_xml(PAGE_PART).getroot()
    assert again is not None and again.get(MARKER) == "1"


def test_a_part_that_is_not_xml_says_so_and_names_itself(store: PackageStore):
    with pytest.raises(ValueError, match=re.escape(THUMBNAIL_PART)):
        store.read_xml(THUMBNAIL_PART)


def test_a_failed_promotion_leaves_the_part_as_bytes(store: PackageStore):
    with pytest.raises(ValueError):
        store.read_xml(THUMBNAIL_PART)
    assert store.read_bytes(THUMBNAIL_PART) == members()["docProps/thumbnail.emf"]


# --------------------------------------------------------------------------
# the promotion baseline: what #89 reads to decide whether to re-serialise
# --------------------------------------------------------------------------


def test_the_baseline_is_comparable_with_a_later_canonical_hash(store: PackageStore):
    """What `read_bytes` asks of a promoted part, asked directly.

    The baseline itself never moves -- it is recorded once, on a frozen value.
    What has to hold is that `canonical_hash` of the live tree can be compared
    with it: equal while nothing has changed, different as soon as something
    has, and equal again when the change is undone.
    """
    tree = store.require_xml(PAGE_PART)
    promoted = store.part(PAGE_PART)
    assert isinstance(promoted, XmlPart)
    baseline = promoted.original_canonical_hash
    assert canonical_hash(tree) == baseline

    root = _mutate(tree)
    assert canonical_hash(tree) != baseline
    del root.attrib[MARKER]
    assert canonical_hash(tree) == baseline


def test_a_promoted_part_nobody_changed_still_reads_back_as_the_original_bytes(store: PackageStore):
    for name in store.names():
        if name.endswith((".xml", ".rels")):
            store.read_xml(name)
    assert {name: store.read_bytes(name) for name in store.names()} == {
        f"/{member}": data for member, data in members().items()
    }


def test_a_changed_part_reads_back_as_a_fresh_serialisation_and_nothing_else_moves(store: PackageStore):
    for name in store.names():
        if name.endswith((".xml", ".rels")):
            store.read_xml(name)
    _mutate(store.require_xml(PAGE_PART))

    written = store.read_bytes(PAGE_PART)
    assert written is not None and written != members()["visio/pages/page1.xml"]
    assert ET.fromstring(written).get(MARKER) == "1"
    assert {name: store.read_bytes(name) for name in store.names() if name != PAGE_PART} == {
        f"/{member}": data for member, data in members().items() if member != "visio/pages/page1.xml"
    }


@pytest.mark.allow_invalid_package
def test_a_promoted_part_elementtree_cannot_reproduce_still_reads_back_as_it_arrived(tmp_path):
    """The baseline is taken off the parsed tree, not off the bytes it was parsed from.

    ElementTree's parser discards comments, so a part carrying one cannot be
    serialised back into itself. A baseline read off the original bytes would
    call this untouched part changed and write the serialisation, dropping the
    comment; a baseline read off the tree calls it unchanged, and the bytes
    that arrived are the bytes that leave.
    """
    part = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Doc><!-- kept --><Child/></Doc>'
    path = make_package(os.path.join(str(tmp_path), "commented.vsdx"), {"visio/document.xml": part})

    store = PackageStore.open(path)
    store.require_xml("/visio/document.xml")
    assert store.read_bytes("/visio/document.xml") == part


def test_a_change_that_is_undone_reads_back_as_the_original_bytes(store: PackageStore):
    root = _mutate(store.require_xml(PAGE_PART))
    del root.attrib[MARKER]
    assert store.read_bytes(PAGE_PART) == members()["visio/pages/page1.xml"]


def test_a_part_written_as_a_tree_has_no_original_bytes_to_fall_back_on(store: PackageStore):
    store.write_xml(PAGE_PART, store.require_xml(PAGE_PART))
    written = store.part(PAGE_PART)
    assert isinstance(written, XmlPart)
    assert written.original_bytes is None
    assert store.read_bytes(PAGE_PART) != members()["visio/pages/page1.xml"]


def test_write_xml_appends_a_part_that_was_not_there(store: PackageStore):
    store.write_xml("/visio/pages/page4.xml", ET.ElementTree(ET.Element("PageContents")))
    assert store.names()[-1] == "/visio/pages/page4.xml"
    written = store.read_bytes("/visio/pages/page4.xml")
    assert written is not None and ET.fromstring(written).tag == "PageContents"


def test_the_store_remembers_where_it_was_opened_from(store: PackageStore):
    """Only `open` can know this, and #89's `save(target=None)` needs it."""
    assert store.source == Path(fixture_path())


# --------------------------------------------------------------------------
# limits, enforced where the archive is read
# --------------------------------------------------------------------------


def test_open_enforces_the_member_count_limit():
    with pytest.raises(PackageLimitError) as excinfo:
        PackageStore.open(fixture_path(), limits=PackageLimits(max_members=5))
    assert excinfo.value.reason == "member_count"


@pytest.mark.allow_invalid_package
def test_open_refuses_a_member_name_that_escapes_the_archive(tmp_path):
    """The pre-flight name check runs, and `open` does not swallow it.

    A member name carrying a backslash is deliberately not tested here.
    `zipfile` folds `os.sep` to `/` in `ZipInfo.__init__`, on the way in *and*
    on the way back out, so on Windows such a member cannot be written, read,
    or therefore reached -- and a version of this test parametrised over one
    failed on all five Windows runners, reporting `duplicate_member` because
    the name had already become `visio/document.xml`. The backslash rule is
    covered where it is reachable on every platform: over a part name, in
    `test_a_name_that_is_not_an_opc_part_name_is_refused`.
    """
    path = os.path.join(str(tmp_path), FIXTURE)
    shutil.copy(fixture_path(), path)
    append_member(path, "/abs/evil.bin", b"evil")
    with pytest.raises(PackageLimitError) as excinfo:
        PackageStore.open(path)
    assert excinfo.value.reason == "member_name"


@pytest.mark.allow_invalid_package
@pytest.mark.parametrize("member", ["visio/./document.xml", "visio//document.xml"])
def test_open_refuses_a_member_no_part_name_can_address(tmp_path, member: str):
    """Every name `names()` hands out has to be one `read_bytes` will take.

    These two are not caught by the pre-flight name check -- neither escapes
    the archive -- but both normalise onto `/visio/document.xml`, so a store
    that held them would list a part it could not read back.
    """
    path = make_package(os.path.join(str(tmp_path), FIXTURE), {member: b"<VisioDocument/>"})
    with pytest.raises(PackageLimitError) as excinfo:
        PackageStore.open(path)
    assert excinfo.value.reason == "member_name"


@pytest.mark.allow_invalid_package
def test_open_drops_directory_entries_rather_than_holding_them_as_parts(tmp_path):
    path = make_package(os.path.join(str(tmp_path), FIXTURE), {"visio/": b"", "visio/document.xml": b"<VisioDocument/>"})
    assert PackageStore.open(path).names() == ("/visio/document.xml",)
