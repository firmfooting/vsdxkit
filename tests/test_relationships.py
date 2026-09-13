"""Unit tests for the relationship and content-type helpers.

The implementations these replaced disagreed only on inputs no bundled fixture
carries, which is why the cases below are built from strings rather than from a
.vsdx - an empty rels part, an id another tool spelled its own way, a part name
in a different case.
"""

import xml.etree.ElementTree as ET
import zipfile

import pytest
from helpers.package_validator import describe_defects, validate_package

import vsdx
from vsdx.relationships import (
    allocate_id,
    append_if_absent,
    ensure_override,
    find,
    remove,
    remove_override,
)

RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
PAGE_TYPE = "http://schemas.microsoft.com/visio/2010/relationships/page"
MASTER_TYPE = "http://schemas.microsoft.com/visio/2010/relationships/master"


def _rels(*relationships: str) -> ET.Element:
    inner = "".join(relationships)
    return ET.fromstring(f'<Relationships xmlns="{RELS_NS}">{inner}</Relationships>')


def _rel(identifier: str, target: str, rel_type: str = PAGE_TYPE) -> str:
    return f'<Relationship Id="{identifier}" Type="{rel_type}" Target="{target}"/>'


def _ids(rels: ET.Element) -> list[str]:
    return [r.attrib["Id"] for r in rels]


class TestAllocateId:
    def test_the_first_free_id_is_taken_not_the_next_after_the_highest(self):
        """Deriving an id from a count or a maximum collides after a removal.

        A package that has had `rId2` deleted has `rId1` and `rId3`; `max + 1`
        gives `rId4`, leaving a gap that grows every time. Worse, a package
        whose ids were renumbered elsewhere gets a collision.
        """
        rels = _rels(_rel("rId1", "page1.xml"), _rel("rId3", "page3.xml"))

        assert allocate_id(rels) == "rId2"

    def test_an_empty_rels_part_allocates_the_first_id(self):
        """One of the implementations this replaces raised `ValueError` here."""
        assert allocate_id(_rels()) == "rId1"

    def test_an_id_that_is_not_spelled_rIdN_does_not_stop_allocation(self):
        """`Id` is an arbitrary XML id by OPC; only this package's habit makes it `rIdN`.

        An implementation that did `int(id.replace("rId", ""))` raised
        `ValueError` on any package written by another tool.
        """
        rels = _rels(_rel("docRel", "document.xml"), _rel("rId1", "page1.xml"))

        assert allocate_id(rels) == "rId2"

    def test_a_duplicated_id_is_still_treated_as_in_use(self):
        """A malformed rels part must not tempt an allocator into reusing an id."""
        rels = _rels(_rel("rId1", "page1.xml"), _rel("rId1", "page2.xml"))

        assert allocate_id(rels) == "rId2"

    def test_allocation_never_returns_an_id_already_in_use(self):
        rels = _rels(*(_rel(f"rId{n}", f"page{n}.xml") for n in range(1, 12)))

        assert allocate_id(rels) not in _ids(rels)


class TestFind:
    def test_it_matches_on_type_and_target_together(self):
        """Both criteria, on a tree where either alone would pick the wrong one.

        Two relationships sharing a target and differing only by type is the
        case that tells a real conjunction from one that ignores its type.
        """
        rels = _rels(
            _rel("rId1", "shared.xml", PAGE_TYPE),
            _rel("rId2", "shared.xml", MASTER_TYPE),
        )

        assert find(rels, rel_type=MASTER_TYPE, target="shared.xml").attrib["Id"] == "rId2"
        assert find(rels, rel_type=PAGE_TYPE, target="shared.xml").attrib["Id"] == "rId1"

    def test_it_returns_the_first_match_not_the_last(self):
        """A duplicate target is malformed, but the order still has to be stated."""
        rels = _rels(_rel("rId1", "page1.xml"), _rel("rId9", "page1.xml"))

        assert find(rels, target="page1.xml").attrib["Id"] == "rId1"

    def test_no_match_is_none_rather_than_an_exception(self):
        assert find(_rels(_rel("rId1", "page1.xml")), target="missing.xml") is None


class TestAppendIfAbsent:
    def test_appending_the_same_relationship_twice_adds_one(self):
        """A duplicate `Target` is how a package ends up with two ids for one part."""
        rels = _rels()

        first = append_if_absent(rels, rel_type=PAGE_TYPE, target="page1.xml")
        second = append_if_absent(rels, rel_type=PAGE_TYPE, target="page1.xml")

        assert first is second
        assert _ids(rels) == ["rId1"]

    def test_the_same_target_under_a_different_type_is_a_different_relationship(self):
        """A part can be related two ways, and each way needs its own id."""
        rels = _rels()

        append_if_absent(rels, rel_type=PAGE_TYPE, target="shared.xml")
        append_if_absent(rels, rel_type=MASTER_TYPE, target="shared.xml")

        assert _ids(rels) == ["rId1", "rId2"]

    def test_a_different_target_gets_its_own_id(self):
        rels = _rels()

        append_if_absent(rels, rel_type=PAGE_TYPE, target="page1.xml")
        append_if_absent(rels, rel_type=PAGE_TYPE, target="page2.xml")

        assert _ids(rels) == ["rId1", "rId2"]

    def test_an_external_target_records_its_mode(self):
        rels = _rels()

        append_if_absent(rels, rel_type=PAGE_TYPE, target="http://example.test", mode="External")

        assert rels[0].attrib["TargetMode"] == "External"

    def test_an_internal_target_records_no_mode(self):
        """`TargetMode` is absent for an internal target, not `Internal`."""
        rels = _rels()

        append_if_absent(rels, rel_type=PAGE_TYPE, target="page1.xml")

        assert "TargetMode" not in rels[0].attrib


class TestRemove:
    def test_removing_by_id_leaves_the_others(self):
        rels = _rels(_rel("rId1", "page1.xml"), _rel("rId2", "page2.xml"))

        assert remove(rels, "rId1") is True
        assert _ids(rels) == ["rId2"]

    def test_removing_an_absent_id_reports_that_it_did_nothing(self):
        rels = _rels(_rel("rId1", "page1.xml"))

        assert remove(rels, "rId9") is False
        assert _ids(rels) == ["rId1"]


class TestContentTypeOverrides:
    def _types(self, *overrides: str) -> ET.Element:
        inner = "".join(overrides)
        return ET.fromstring(f'<Types xmlns="{CT_NS}"><Default Extension="xml" ContentType="application/xml"/>{inner}</Types>')

    def _parts(self, types: ET.Element) -> list[str]:
        return [o.attrib["PartName"] for o in types.findall(f"{{{CT_NS}}}Override")]

    def test_declaring_the_same_part_twice_declares_it_once(self):
        """Two Overrides for one PartName is invalid OPC.

        The implementation this replaces was not idempotent: calling it twice
        for one part left the package with duplicate declarations.
        """
        types = self._types()

        ensure_override(types, "/visio/pages/page1.xml", "application/vnd.ms-visio.page+xml")
        ensure_override(types, "/visio/pages/page1.xml", "application/vnd.ms-visio.page+xml")

        assert self._parts(types) == ["/visio/pages/page1.xml"]

    def test_the_first_override_of_a_content_type_does_not_need_a_predecessor(self):
        """The implementation this replaces indexed `[-1]` of an empty list."""
        types = self._types()

        ensure_override(types, "/visio/pages/page1.xml", "application/vnd.ms-visio.page+xml")

        assert self._parts(types) == ["/visio/pages/page1.xml"]

    def test_a_new_part_is_grouped_with_others_of_its_content_type(self):
        """Visio writes them grouped, and a reader of the file expects that."""
        types = self._types()
        for name in ("page1.xml", "page2.xml"):
            ensure_override(types, f"/visio/pages/{name}", "application/vnd.ms-visio.page+xml")
        ensure_override(types, "/visio/masters/masters.xml", "application/vnd.ms-visio.masters+xml")
        ensure_override(types, "/visio/pages/page3.xml", "application/vnd.ms-visio.page+xml")

        assert self._parts(types) == [
            "/visio/pages/page1.xml",
            "/visio/pages/page2.xml",
            "/visio/pages/page3.xml",
            "/visio/masters/masters.xml",
        ]

    def test_removing_an_override_leaves_the_rest(self):
        types = self._types()
        ensure_override(types, "/visio/pages/page1.xml", "application/vnd.ms-visio.page+xml")
        ensure_override(types, "/visio/pages/page2.xml", "application/vnd.ms-visio.page+xml")

        assert remove_override(types, "/visio/pages/page1.xml") is True
        assert self._parts(types) == ["/visio/pages/page2.xml"]

    def test_an_override_is_removed_whatever_case_it_is_spelled_in(self):
        """The half of the case rule that `remove_page_by_index` depends on."""
        types = self._types('<Override PartName="/visio/Pages/Page1.xml" ContentType="application/vnd.ms-visio.page+xml"/>')

        assert remove_override(types, "/visio/pages/page1.xml") is True
        assert self._parts(types) == []

    def test_removing_an_absent_override_reports_that_it_did_nothing(self):
        assert remove_override(self._types(), "/visio/pages/nope.xml") is False

    @pytest.mark.parametrize("declared", ["/visio/Pages/Page1.xml", "/VISIO/PAGES/PAGE1.XML"])
    def test_a_part_name_is_matched_without_regard_to_case(self, declared):
        """OPC compares part names case-insensitively (ECMA-376 Part 2).

        A package whose Override differs only in case already declares the part,
        and declaring it again produces the duplicate this guards against.
        """
        types = self._types(f'<Override PartName="{declared}" ContentType="application/vnd.ms-visio.page+xml"/>')

        ensure_override(types, "/visio/pages/page1.xml", "application/vnd.ms-visio.page+xml")

        assert self._parts(types) == [declared]


class TestRemovingAPageThroughTheHelpers:
    """`remove_page_by_index` is the call site issue #92 names for `remove`."""

    def test_it_removes_an_override_spelled_in_another_case(self, tmp_path, basedir):
        """OPC part names compare without regard to case; an exact match misses.

        A package written by another tool may spell the part differently from
        the way this library builds the name. Removing the page then leaves an
        Override declaring a part that is no longer in the archive.
        """
        source = f"{basedir}/test4_connectors.vsdx"
        respelled = str(tmp_path / "respelled.vsdx")
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(respelled, "w") as rewritten:
            for entry in original.infolist():
                data = original.read(entry.filename)
                if entry.filename == "[Content_Types].xml":
                    data = data.replace(b"/visio/pages/page1.xml", b"/visio/Pages/Page1.xml")
                rewritten.writestr(entry, data)

        out = str(tmp_path / "removed.vsdx")
        with vsdx.VisioFile(respelled) as document:
            document.remove_page_by_index(0)
            document.save_vsdx(out)

        defects = validate_package(out)
        assert not defects, describe_defects(defects)
