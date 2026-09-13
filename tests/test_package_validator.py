"""Tests for the structural validator.

Each test breaks a real fixture in one specific way and asserts that exactly
that rule fires. Several of the defect kinds are reachable from more than one
rule, so the assertions pin `where` as well as `kind`: a test that only checks
the kind can pass with the rule it names deleted.
"""

import glob
import os
import zipfile

import pytest
from helpers.package_validator import Defect, _extension, describe_defects, validate_package

PAGE1 = "visio/pages/page1.xml"
PAGES = "visio/pages/pages.xml"
CONTENT_TYPES = "[Content_Types].xml"


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
