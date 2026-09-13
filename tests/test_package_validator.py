"""Tests for the structural validator.

Each test breaks a real fixture in one specific way and asserts that exactly
that rule fires. Several of the defect kinds are reachable from more than one
rule, so the assertions pin `where` as well as `kind`: a test that only checks
the kind can pass with the rule it names deleted.
"""

import glob
import os
import sys
import zipfile

import pytest
from helpers.package_validator import Defect, _extension, describe_defects, validate_package

PAGE1 = "visio/pages/page1.xml"
PAGE3 = "visio/pages/page3.xml"
PAGES = "visio/pages/pages.xml"
MASTERS = "visio/masters/masters.xml"
MASTER2 = "visio/masters/master2.xml"
CONTENT_TYPES = "[Content_Types].xml"
MAIN_NS = "http://schemas.microsoft.com/office/visio/2012/main"


def _rewritten(source: str, destination: str, edits: dict[str, tuple[str, str] | None]) -> str:
    """Copy a package, applying at most one edit per member."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as rewritten:
        for entry in original.infolist():
            if entry.filename in edits and edits[entry.filename] is None:
                continue  # drop the member entirely
            data = original.read(entry.filename)
            edit = edits.get(entry.filename)
            if edit is not None:
                old, new = edit
                text = data.decode("utf-8")
                assert old in text, f"{old!r} not found in {entry.filename}; the fixture has changed"
                data = text.replace(old, new, 1).encode("utf-8")
            rewritten.writestr(entry, data)
    return destination


@pytest.fixture
def broken(tmp_path, basedir):
    def _make(fixture: str, edits: dict[str, tuple[str, str] | None], name: str = "broken.vsdx") -> str:
        return _rewritten(f"{basedir}/{fixture}", str(tmp_path / name), edits)

    return _make


def _kinds(path: str) -> list[str]:
    return [defect.kind for defect in validate_package(path)]


# Fixtures that arrive non-conformant, with the count of defects each carries.
#
# `test5_master.vsdx` came in from upstream in 2021 (commit f4cc32e) and has not
# been edited since, so this is a property of the file we were given rather than
# anything this library did. It declares four relationships and three content
# type overrides for `docProps/app.xml`, `core.xml`, `custom.xml` and
# `thumbnail.emf`, none of which are in the archive. Visio opens it regardless,
# which is why nothing before this validator had cause to report it.
#
# The entry is here rather than in the validator so that the rule stays true and
# the exception stays visible. Tracked as #298; when the fixture is repaired or
# replaced, this line goes and the floor tightens by one file.
KNOWN_NON_CONFORMANT = {"test5_master.vsdx": 7}


def test_every_fixture_carries_only_the_defects_on_record(basedir):
    """The floor, and the reason the exception above is an entry and not a rule.

    A validator nobody can satisfy gets switched off, so the corpus has to be
    clean - but weakening a rule to make it clean would defeat the purpose. The
    one fixture that genuinely violates the format is named and counted rather
    than quietly excused.
    """
    fixtures = sorted(glob.glob(os.path.join(basedir, "*.vsdx")) + glob.glob(os.path.join(basedir, "*.vsdm")))
    assert fixtures, "no fixtures found"

    offenders = {}
    for path in fixtures:
        name = os.path.basename(path)
        defects = validate_package(path)
        if len(defects) != KNOWN_NON_CONFORMANT.get(name, 0):
            offenders[name] = describe_defects(defects)

    assert not offenders, "fixtures whose defects are not the ones on record:\n" + "\n".join(
        f"{name}:\n{report}" for name, report in offenders.items()
    )


@pytest.mark.allow_invalid_package
class TestShapeIdentity:
    def test_a_page_using_one_id_twice_is_a_defect(self, broken):
        """And the glue that pointed at the overwritten shape now dangles.

        Both are reported, because they are two different things to fix: one
        page has lost a shape, and one connector has lost its endpoint.
        """
        path = broken("test4_connectors.vsdx", {PAGE1: ("<Shape ID='5'", "<Shape ID='2'")})

        assert sorted(set(_kinds(path))) == ["dangling-glue", "duplicate-shape-id"]

    def test_a_group_member_colliding_with_a_top_level_shape_is_a_defect(self, broken):
        """Uniqueness is per page, not per level: ids are page-scoped."""
        path = broken("test10_nested_shapes.vsdx", {PAGE1: ("<Shape ID='1'", "<Shape ID='7'")})

        assert "duplicate-shape-id" in _kinds(path)

    def test_a_declared_maxid_below_the_largest_shape_id_is_a_defect(self, broken):
        """MaxID is what an allocator trusts; too low and it hands out a live id.

        No fixture carries the cell, so one is injected.
        """
        # page 1 carries shapes up to id 7; claim the page tops out at 3
        path = broken("test4_connectors.vsdx", {PAGES: ("</PageSheet>", "<Cell N='MaxID' V='3'/></PageSheet>")})

        assert "max-id-too-low" in _kinds(path)


@pytest.mark.allow_invalid_package
class TestGlue:
    def test_glue_naming_a_shape_that_is_not_on_the_page_is_a_defect(self, broken):
        """Visio silently rebinds one of these, so the package can be wrong and still open."""
        path = broken("test4_connectors.vsdx", {PAGE1: ("ToSheet='1'", "ToSheet='999'")})

        assert _kinds(path) == ["dangling-glue"]
        assert "999" in describe_defects(validate_package(path))


@pytest.mark.allow_invalid_package
class TestPackageStructure:
    def test_a_relationship_pointing_at_a_missing_part_is_a_defect(self, broken):
        """Pinned by `where`, because two different rules raise `missing-part`.

        Dropping a page part makes the content types part name a member that is
        gone *and* makes the page relationship dangle. Asserting on the kind
        alone passes with this rule deleted outright - the other rule covers for
        it - so the relationships part has to be named.
        """
        path = broken("test1.vsdx", {PAGE1: None})

        offenders = [d for d in validate_package(path) if d.kind == "missing-part"]
        assert any(d.where.endswith("pages.xml.rels") for d in offenders), describe_defects(tuple(offenders))

    def test_a_part_with_no_declared_content_type_is_a_defect(self, broken):
        path = broken(
            "test1.vsdx",
            {CONTENT_TYPES: ('<Default Extension="rels" ', '<Default Extension="unused" ')},
        )

        defects = validate_package(path)
        assert "undeclared-content-type" in [defect.kind for defect in defects]
        assert any("_rels/.rels" in defect.detail for defect in defects)

    def test_a_page_whose_relationship_does_not_resolve_is_a_defect(self, broken):
        path = broken("test4_connectors.vsdx", {PAGES: ("r:id='rId1'", "r:id='rIdMissing'")})

        assert "unresolved-page" in _kinds(path)


def test_a_report_names_the_part_each_defect_is_in():
    """A defect nobody can locate is barely a defect."""
    defects = (
        Defect(kind="duplicate-shape-id", where="visio/pages/page1.xml", detail="shape 2 appears twice"),
        Defect(kind="dangling-glue", where="visio/pages/page2.xml", detail="shape 999 is not here"),
    )

    report = describe_defects(defects).splitlines()

    assert len(report) == 2
    assert all(defect.where in line and defect.detail in line for defect, line in zip(defects, report, strict=True))


def test_the_opc_extension_of_a_dotfile_part_is_read_from_its_final_period():
    """`_rels/.rels` is the part this is most easily got wrong on.

    `posixpath.splitext` reads it as a name with no extension at all, which
    makes the `rels` Default stop covering it and reports every package in
    existence as missing a content type. OPC has no notion of a dotfile.
    """
    assert _extension("_rels/.rels") == "rels"
    assert _extension("visio/document.xml") == "xml"
    assert _extension("visio/pages/noextension") == ""


@pytest.mark.allow_invalid_package
class TestPackagesThatCannotBeRead:
    """An unreadable package is a defect to report, not an exception to raise.

    These run at test teardown, where an exception surfaces as a traceback into
    conftest that names neither the test nor the marker that would have silenced
    it. A package whose XML is malformed is exactly what the report is for.
    """

    def test_a_part_that_will_not_parse_is_a_defect(self, broken):
        path = broken("test1.vsdx", {PAGE1: ("<PageContents", "<not well formed")})

        assert "unreadable-part" in _kinds(path)

    def test_content_types_that_will_not_parse_is_a_defect(self, broken):
        path = broken("test1.vsdx", {CONTENT_TYPES: ("<Types ", "<nope <<")})

        assert "unreadable-part" in _kinds(path)

    def test_a_page_nested_deeper_than_the_interpreter_will_recurse_is_a_defect(self, tmp_path, basedir):
        """The walks over a shape tree recurse, and groups can nest without limit.

        `zipfile` also raises for a compression method it does not implement and
        for an encrypted member, neither of which is an OSError. Catching the
        types seen so far is how the next one gets through, so all of them are
        caught and the type is named in the report instead.
        """
        depth = sys.getrecursionlimit() * 2
        nested = "<Shape ID='1'><Shapes>" * depth + "</Shapes></Shape>" * depth
        path = str(tmp_path / "deep.vsdx")
        with zipfile.ZipFile(f"{basedir}/test1.vsdx") as original, zipfile.ZipFile(path, "w") as rewritten:
            for entry in original.infolist():
                data = original.read(entry.filename)
                if entry.filename == PAGE1:
                    data = f"<PageContents xmlns='{MAIN_NS}'><Shapes>{nested}</Shapes></PageContents>".encode()
                rewritten.writestr(entry, data)

        assert [kind for kind in _kinds(path) if kind.startswith("unreadable")]

    def test_an_archive_that_is_not_a_zip_is_a_defect(self, tmp_path):
        path = tmp_path / "notazip.vsdx"
        path.write_bytes(b"this is not a zip file")

        assert _kinds(str(path)) == ["unreadable-package"]


@pytest.mark.allow_invalid_package
class TestArchiveShape:
    def test_a_part_named_twice_is_a_defect(self, tmp_path, basedir):
        """`zipfile` reads the last entry and ignores the first, silently.

        `ZipFile.writestr` emits a duplicate name with only a warning, so a
        writer can produce this, and readers disagree about which copy counts.
        A set of member names would hide it.
        """
        path = str(tmp_path / "dupe.vsdx")
        with zipfile.ZipFile(f"{basedir}/test1.vsdx") as original, zipfile.ZipFile(path, "w") as rewritten:
            for entry in original.infolist():
                rewritten.writestr(entry, original.read(entry.filename))
            with pytest.warns(UserWarning, match="Duplicate name"):
                rewritten.writestr(PAGE1, b"<PageContents/>")

        assert "duplicate-member" in _kinds(path)


class TestNamesThatLookWrongButAreNot:
    """Valid packages the obvious implementation reports as broken."""

    def test_an_override_naming_a_part_in_another_case_is_accepted(self, broken):
        """OPC compares part names case-insensitively (ECMA-376 Part 2)."""
        path = broken(
            "test1.vsdx",
            {CONTENT_TYPES: ("/visio/pages/page1.xml", "/visio/Pages/Page1.xml")},
        )

        assert _kinds(path) == []

    def test_a_percent_encoded_relationship_target_resolves(self, tmp_path, basedir):
        """A Target is a URI reference; a zip member name is not.

        A part whose name holds a space arrives percent-encoded in the
        relationship and has to be decoded before it matches anything. Embedded
        images are where this usually turns up.
        """
        path = str(tmp_path / "encoded.vsdx")
        with zipfile.ZipFile(f"{basedir}/test1.vsdx") as original, zipfile.ZipFile(path, "w") as rewritten:
            for entry in original.infolist():
                data = original.read(entry.filename)
                if entry.filename == "visio/_rels/document.xml.rels":
                    data = data.replace(
                        b'<Relationship Id="rId1"',
                        b'<Relationship Id="rIdImage" Type="http://x" Target="media/image%201.png"/><Relationship Id="rId1"',
                        1,
                    )
                elif entry.filename == CONTENT_TYPES:
                    data = data.replace(b"<Default", b'<Default Extension="png" ContentType="image/png"/><Default', 1)
                rewritten.writestr(entry, data)
            rewritten.writestr("visio/media/image 1.png", b"\x89PNG")

        assert "missing-part" not in _kinds(path)


@pytest.mark.allow_invalid_package
class TestSheetListings:
    """`pages.xml` and `masters.xml`, checked by the one set of rules.

    Each rule is broken in whichever of the two listings is cheapest to break;
    `package_validator.py`'s section comment says why one set covers both.
    """

    def test_a_master_whose_relationship_does_not_resolve_is_a_defect(self, broken):
        path = broken("test4_connectors.vsdx", {MASTERS: ("r:id='rId1'", "r:id='rIdMissing'")})

        assert "unresolved-master" in _kinds(path)

    def test_two_pages_resolving_to_one_part_is_a_defect(self, broken):
        path = broken("test4_connectors.vsdx", {PAGES: ("<Rel r:id='rId2'/>", "<Rel r:id='rId1'/>")})

        assert "reused-page-part" in _kinds(path)

    def test_two_masters_resolving_to_one_part_is_a_defect(self, broken):
        path = broken("test4_connectors.vsdx", {MASTERS: ("<Rel r:id='rId2'/>", "<Rel r:id='rId1'/>")})

        assert "reused-master-part" in _kinds(path)

    def test_a_part_two_entries_both_name_is_reported_once(self, broken):
        """Otherwise the report says everything in it twice, under the one cause.

        `reused-page-part` already names the thing to fix, and a second copy of
        every defect in the part is what a reader has to wade through to get
        to it.
        """
        path = broken(
            "test4_connectors.vsdx",
            {PAGES: ("<Rel r:id='rId2'/>", "<Rel r:id='rId1'/>"), PAGE1: ("<Shape ID='5'", "<Shape ID='2'")},
        )

        assert _kinds(path).count("duplicate-shape-id") == 1

    def test_a_page_id_used_twice_is_a_defect(self, broken):
        """The allocator collision one level up from `duplicate-shape-id`."""
        path = broken("test4_connectors.vsdx", {PAGES: ("<Page ID='4'", "<Page ID='0'")})

        assert "duplicate-page-id" in _kinds(path)

    def test_a_master_id_used_twice_is_a_defect(self, broken):
        path = broken("test4_connectors.vsdx", {MASTERS: ("<Master ID='6'", "<Master ID='2'")})

        assert "duplicate-master-id" in _kinds(path)

    def test_a_shortcut_taking_an_id_an_earlier_master_took_is_a_defect(self, broken):
        """Ids are one space across both kinds of entry, in both directions.

        Checking the id only on the entries that own a part catches a shortcut
        colliding with a later master and misses it colliding with an earlier
        one, which is the same collision written the other way round.
        """
        path = broken("test4_connectors.vsdx", {MASTERS: ("<Master ID='6'", "<MasterShortcut ID='2'/><Master ID='6'")})

        assert "duplicate-master-id" in _kinds(path)

    def test_a_master_sheet_declaring_a_maxid_below_its_largest_shape_is_a_defect(self, broken):
        """Pinned by `where`: the page case raises the same kind.

        Masters allocate shape ids from their own sheet, so the cell is wrong
        in the same way and is reported against the listing that carries it.
        """
        # master 2's part carries shape 5; claim the master tops out at 3
        path = broken("test4_connectors.vsdx", {MASTERS: ("</PageSheet>", "<Cell N='MaxID' V='3'/></PageSheet>")})

        assert [d.where for d in validate_package(path) if d.kind == "max-id-too-low"] == [MASTERS]

    def test_a_master_part_using_one_id_twice_is_a_defect(self, broken):
        """`MasterContents` is `PageContents`, so it carries the same defects."""
        path = broken("test4_connectors.vsdx", {MASTER2: ("<Shape ID='6'", "<Shape ID='5'")})

        offenders = [d for d in validate_package(path) if d.kind == "duplicate-shape-id"]
        assert [d.where for d in offenders] == [MASTER2], describe_defects(validate_package(path))

    def test_a_master_part_that_will_not_parse_is_a_defect(self, broken):
        """Pinned by `where`, because the page parts raise `unreadable-part` too."""
        path = broken("test4_connectors.vsdx", {MASTER2: ("<MasterContents", "<not well formed")})

        offenders = [d for d in validate_package(path) if d.kind == "unreadable-part"]
        assert [d.where for d in offenders] == [MASTER2], describe_defects(validate_package(path))


@pytest.mark.allow_invalid_package
class TestMasterReferences:
    """A shape naming a master, or a shape inside one, that is not there."""

    def test_a_shape_instancing_a_master_that_is_not_declared_is_a_defect(self, broken):
        path = broken("test4_connectors.vsdx", {PAGE3: ("Master='6'", "Master='99'")})

        defects = [d for d in validate_package(path) if d.kind == "undeclared-master"]
        assert [d.where for d in defects] == [PAGE3], describe_defects(validate_package(path))
        assert "99" in defects[0].detail

    def test_a_master_instancing_a_master_that_is_not_declared_is_a_defect(self, broken):
        """Masters hold instances of other masters, so they are walked as well."""
        path = broken("test4_connectors.vsdx", {MASTER2: ("<Shape ID='6' Type=", "<Shape ID='6' Master='99' Type=")})

        defects = [d for d in validate_package(path) if d.kind == "undeclared-master"]
        assert [d.where for d in defects] == [MASTER2], describe_defects(validate_package(path))

    def test_a_mastershape_naming_no_shape_in_that_master_is_a_defect(self, broken):
        """`MasterShape` is an id inside the master the instance came from.

        Page 3 shape 2 sits under an instance of master 6, whose part carries
        shapes 5 to 9. Point it at one that is not there.
        """
        path = broken("test4_connectors.vsdx", {PAGE3: ("MasterShape='6'", "MasterShape='999'")})

        defects = [d for d in validate_package(path) if d.kind == "undeclared-master-shape"]
        assert [d.where for d in defects] == [PAGE3], describe_defects(validate_package(path))

    def test_a_master_that_is_declared_but_unresolved_is_not_also_undeclared(self, broken):
        """An unresolved master is reported once, against the listing.

        Reporting each instance of it as well would bury the one line that says
        what to fix under a line per shape that names it.
        """
        path = broken("test4_connectors.vsdx", {MASTERS: ("r:id='rId2'", "r:id='rIdMissing'")})

        assert "unresolved-master" in _kinds(path)
        assert "undeclared-master" not in _kinds(path)

    def test_a_listing_nobody_can_read_declares_nothing_and_denies_nothing(self, broken):
        """The same, for the case where the whole listing is unreadable.

        An empty set of declared ids is what "no masters" and "we could not
        find out" both look like from here, and answering from it turns one
        unreadable part into a defect per instance in the package.
        """
        path = broken("test4_connectors.vsdx", {MASTERS: ("<Masters ", "<nope <<")})

        assert _kinds(path) == ["unreadable-part"]


class TestReferencesThatLookWrongButAreNot:
    def test_a_master_shortcut_takes_an_id_without_taking_a_part(self, broken):
        """`<MasterShortcut>` stands for a master held in another document.

        It has no part in this package, so the rules about parts do not apply to
        it - but it does take an id in this package, and a shape may instance
        it. Treating the listing as nothing but `<Master>` elements would report
        both the shortcut as unresolved and every instance of it as undeclared.
        """
        path = broken(
            "test4_connectors.vsdx",
            {
                MASTERS: ("<Master ID='2'", "<MasterShortcut ID='99' NameU='Elsewhere'/><Master ID='2'"),
                PAGE3: ("Master='6'", "Master='99'"),
            },
        )

        assert _kinds(path) == []

    def test_an_id_is_compared_as_a_number_and_not_as_a_spelling(self, broken):
        """Ids are `xsd:unsignedInt`, so '06' and '6' are one id, not two.

        Comparing the text would report a package for a difference no reader
        would ever see, and would miss the collision between the two.
        """
        path = broken("test4_connectors.vsdx", {MASTERS: ("<Master ID='6'", "<Master ID='06'")})

        assert _kinds(path) == []

    def test_a_mastershape_with_no_master_in_scope_is_left_alone(self, broken):
        """Deliberately not a rule, and here so that it stays deliberate.

        There is nothing to resolve the id against, so any verdict would be a
        guess. The corpus has no example of one, and inventing a rule for it
        would mean firing on files nobody has a reason to think are wrong.
        """
        path = broken(
            "test4_connectors.vsdx",
            {PAGE1: ("<Shape ID='1' Type='Shape'", "<Shape ID='1' MasterShape='999' Type='Shape'")},
        )

        assert _kinds(path) == []

    def test_a_shape_carrying_both_master_and_mastershape_is_left_alone(self, broken):
        """The same, for the other case where the master in scope is ambiguous.

        Nothing in this corpus or in MS-VSDX settles whether such a shape's
        `MasterShape` is an id in the master it names or in the one it sits
        inside, so it is not checked either way.
        """
        path = broken(
            "test4_connectors.vsdx",
            {PAGE3: ("Type='Group' Master='6'", "Type='Group' Master='6' MasterShape='999'")},
        )

        assert _kinds(path) == []

    def test_an_id_that_is_not_a_number_is_not_a_defect(self, broken):
        """`int()`, not `str.isdigit()`: '²'.isdigit() is True and int('²') raises.

        A non-numeric id is the schema's business rather than any rule's here.
        """
        path = broken("test4_connectors.vsdx", {PAGE3: ("MasterShape='6'", "MasterShape='²'")})

        assert _kinds(path) == []
