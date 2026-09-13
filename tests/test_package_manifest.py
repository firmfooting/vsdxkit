"""The package manifest oracle, and what it says about a round trip today.

Two jobs live here. The first half tests `tests/helpers/package_manifest.py`
itself -- an oracle nobody has checked is an oracle nobody should believe. The
second half points it at every fixture in the suite and asserts that opening a
package and saving it without changing anything moves nothing beyond the drift
recorded in `tests/fixtures/package_manifests/KNOWN_DRIFT.md`.

That second half is the behaviour freeze the 1.0 package rewrite is measured
against: `PackageStore` and `MasterCatalog` may reorganise how parts are held in
memory, but the bytes that reach disk must not move except where this file says
they already do.
"""

import io
import os
import zipfile

import pytest
from helpers.package_manifest import (
    CANONICALIZE_OPTIONS,
    DRAWING_CONTENT_TYPE,
    MACRO_ENABLED_CONTENT_TYPE,
    PackageManifest,
    assert_manifest_equal,
    manifest_differences,
    member_matches,
)

import vsdx

BASEDIR = os.path.dirname(os.path.realpath(__file__))
PACKAGE_SUFFIXES = (".vsdx", ".vsdm")


def _fixture_packages() -> list[str]:
    """Every Visio package in the test tree, as a path relative to `tests/`."""
    found = []
    for root, _, names in os.walk(BASEDIR):
        for name in names:
            if name.endswith(PACKAGE_SUFFIXES):
                found.append(os.path.relpath(os.path.join(root, name), BASEDIR))
    return sorted(found)


FIXTURE_PACKAGES = _fixture_packages()


# --------------------------------------------------------------------------
# building archives to compare
# --------------------------------------------------------------------------

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\
<Override PartName="/visio/document.xml" ContentType="{content_type}"/></Types>"""


def content_types(content_type: str = DRAWING_CONTENT_TYPE) -> bytes:
    return CONTENT_TYPES.format(content_type=content_type).encode("utf-8")


def package(*members: tuple[str, bytes]) -> bytes:
    """A zip archive of the given members, in the given order."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members:
            archive.writestr(name, data)
    return buffer.getvalue()


def manifest(*members: tuple[str, bytes], label: str = "") -> PackageManifest:
    return PackageManifest.from_bytes(package(*members), label=label)


# --------------------------------------------------------------------------
# the canonicalisation contract
# --------------------------------------------------------------------------


def test_the_canonicalisation_options_are_exactly_these_three():
    """Names only: each of the three values is pinned by a test below.

    `test_a_dropped_comment_is_a_difference` pins `with_comments`,
    `test_whitespace_between_elements_is_a_difference` pins `strip_text` and
    `test_a_generated_namespace_prefix_is_a_difference` pins `rewrite_prefixes`,
    each by breaking what its option protects. Retyping the values here would
    only add a second place to edit.

    What none of them can see is a fourth option. `ET.canonicalize` also takes
    `exclude_attrs` and `exclude_tags`, and either drops part of the document
    from every comparison the suite makes, with no test to fail. Read the
    comment above `CANONICALIZE_OPTIONS` before adding one.
    """
    assert set(CANONICALIZE_OPTIONS) == {"with_comments", "strip_text", "rewrite_prefixes"}


def test_a_dropped_comment_is_a_difference():
    """`with_comments=True`. ElementTree's parser discards comments on the way in."""
    with_comment = manifest(("a.xml", b"<Doc><!-- why --><Child/></Doc>"))
    without = manifest(("a.xml", b"<Doc><Child/></Doc>"))
    assert manifest_differences(with_comment, without)["a.xml"] == ("canonical", "bytes")


def test_whitespace_in_text_is_a_difference():
    """`strip_text=False`. Visio marks the parts carrying shape text `xml:space="preserve"`."""
    spaced = manifest(("a.xml", b'<Doc xml:space="preserve"> text </Doc>'))
    tight = manifest(("a.xml", b'<Doc xml:space="preserve">text</Doc>'))
    assert manifest_differences(spaced, tight)["a.xml"] == ("canonical", "bytes")


def test_whitespace_between_elements_is_a_difference():
    """`strip_text=False`, in the parts that carry no `xml:space="preserve"`.

    The test above cannot pin the option: `ET.canonicalize` honours
    `xml:space="preserve"` whatever `strip_text` says, so those two fixtures
    differ either way. The parts where `strip_text=True` really would erase a
    change are the ones without the attribute - `[Content_Types].xml`, every
    `.rels`, `docProps/*` - and one save reindenting those is exactly the drift
    the manifest is here to see.
    """
    indented = manifest(("a.xml", b'<Doc>\n  <Child V="a"/>\n  <Child V="b"/>\n</Doc>'))
    flat = manifest(("a.xml", b'<Doc><Child V="a"/><Child V="b"/></Doc>'))
    assert manifest_differences(indented, flat)["a.xml"] == ("canonical", "bytes")


def test_dropping_xml_space_preserve_is_a_difference():
    """The attribute itself is load-bearing, not only the whitespace it protects.

    Rebinding the reserved `xml:` prefix once produced parts that would not
    parse at all, so the manifest has to see this attribute come and go.
    """
    preserved = manifest(("a.xml", b'<Doc xml:space="preserve">text</Doc>'))
    without = manifest(("a.xml", b"<Doc>text</Doc>"))
    assert manifest_differences(preserved, without)["a.xml"] == ("canonical", "bytes")


def test_a_generated_namespace_prefix_is_a_difference():
    """`rewrite_prefixes=False`, which is issue #60.

    A part that arrives under a generated `ns0:` prefix instead of its own
    default namespace is rejected by libvisio and by draw.io's importer, even
    though it is the same XML by every other measure. Canonicalising prefixes
    away would make that regression invisible here.
    """
    default_namespace = manifest(("a.xml", b"<Doc xmlns='urn:visio'><Child/></Doc>"))
    generated_prefix = manifest(("a.xml", b"<ns0:Doc xmlns:ns0='urn:visio'><ns0:Child/></ns0:Doc>"))
    assert manifest_differences(default_namespace, generated_prefix)["a.xml"] == ("namespaces", "canonical", "bytes")


# --------------------------------------------------------------------------
# what a manifest records
# --------------------------------------------------------------------------


def test_members_are_recorded_in_archive_order():
    recorded = manifest(("b.xml", b"<B/>"), ("a.xml", b"<A/>"), ("c.bin", b"\x00"))
    assert recorded.names == ("b.xml", "a.xml", "c.bin")


def test_non_xml_members_are_compared_as_bytes():
    recorded = manifest(("visio/media/image1.png", b"\x89PNG\r\n\x1a\n"))
    part = recorded.by_name()["visio/media/image1.png"]
    assert part.kind == "binary"
    assert part.canonical_sha256 is None
    assert part.byte_sha256


def test_a_binary_member_that_changes_by_one_byte_is_a_difference():
    before = manifest(("visio/vbaProject.bin", b"\x00\x01\x02"))
    after = manifest(("visio/vbaProject.bin", b"\x00\x01\x03"))
    assert manifest_differences(before, after)["visio/vbaProject.bin"] == ("bytes",)


def test_respelling_a_part_leaves_the_canonical_hash_alone():
    """Attribute order, quoting and the empty-element form are spelling, not content.

    This is the whole reason the manifest keeps two hashes. A comparison that
    used only the bytes would call these two parts different, and then every
    refactor would look like a behaviour change.
    """
    visio_style = manifest(("a.xml", b"<?xml version='1.0' encoding='utf-8' ?>\r\n<Doc a='1' b='2'><Child/></Doc>"))
    elementtree_style = manifest(("a.xml", b'<?xml version="1.0" encoding="UTF-8"?><Doc b="2" a="1"><Child /></Doc>'))
    assert manifest_differences(visio_style, elementtree_style)["a.xml"] == ("declaration", "bytes")


def test_the_declaration_is_recorded_as_written():
    recorded = manifest(("a.xml", b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Doc/>'))
    declaration = recorded.by_name()["a.xml"].declaration
    assert declaration is not None
    assert declaration.text == '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    assert (declaration.version, declaration.encoding, declaration.standalone) == ("1.0", "UTF-8", "yes")
    assert declaration.byte_order_mark is False


def test_a_part_with_no_declaration_is_recorded_as_having_none():
    """`visio/masters/masters.xml` is written without one in every fixture here."""
    declaration = manifest(("a.xml", b"<Doc/>")).by_name()["a.xml"].declaration
    assert declaration is not None
    assert declaration.text is None


@pytest.mark.parametrize("body", [b"<?xml version='1.0'?><Doc/>", b"<Doc/>"])
def test_a_byte_order_mark_is_recorded_with_or_without_a_declaration(body):
    declaration = manifest(("a.xml", b"\xef\xbb\xbf" + body)).by_name()["a.xml"].declaration
    assert declaration is not None
    assert declaration.byte_order_mark is True


def test_the_declaration_of_a_utf_16_part_is_still_read():
    """A part recorded as having no declaration when it has one is a blind spot.

    A save that dropped or rewrote that part's declaration would compare equal.
    XML requires a UTF-16 entity to open with a byte order mark, which is what
    says how to decode the declaration behind it.
    """
    part = "<?xml version='1.0' encoding='utf-16'?><Doc/>".encode("utf-16")
    declaration = manifest(("a.xml", part)).by_name()["a.xml"].declaration
    assert declaration is not None
    assert declaration.encoding == "utf-16"
    assert declaration.byte_order_mark is True


def test_namespace_prefixes_are_collected_from_the_whole_part():
    """A third-party vocabulary can appear on a descendant, as Lucidchart's does."""
    recorded = manifest(("a.xml", b"<Doc xmlns='urn:visio'><lc:P xmlns:lc='urn:lucid'/></Doc>"))
    assert recorded.by_name()["a.xml"].namespaces == (("", "urn:visio"), ("lc", "urn:lucid"))


def test_the_package_kind_comes_from_the_content_types_part():
    """A .vsdm renamed to .vsdx is still macro-enabled, and the manifest must say so."""
    macro_enabled = manifest(("[Content_Types].xml", content_types(MACRO_ENABLED_CONTENT_TYPE)))
    drawing = manifest(("[Content_Types].xml", content_types(DRAWING_CONTENT_TYPE)))
    assert macro_enabled.is_macro_enabled is True
    assert drawing.is_macro_enabled is False


def test_a_malformed_part_is_reported_with_its_name():
    with pytest.raises(ValueError, match=r"'visio/pages/page1\.xml' is not well-formed"):
        manifest(("visio/pages/page1.xml", b"<Doc><Child></Doc>"))


# --------------------------------------------------------------------------
# comparing manifests
# --------------------------------------------------------------------------


def test_identical_packages_compare_equal():
    members = (("[Content_Types].xml", content_types()), ("a.xml", b"<Doc/>"), ("b.bin", b"\x00"))
    assert_manifest_equal(manifest(*members), manifest(*members))


def test_the_first_differing_member_is_named():
    before = manifest(("a.xml", b"<Doc/>"), ("b.xml", b"<Doc/>"), ("c.xml", b"<Doc/>"))
    after = manifest(("a.xml", b"<Doc/>"), ("b.xml", b"<Other/>"), ("c.xml", b"<Else/>"))
    with pytest.raises(AssertionError) as failure:
        assert_manifest_equal(before, after)
    message = str(failure.value)
    assert message.startswith("package manifest mismatch at member 'b.xml'")
    assert "1 further member(s) also differ: 'c.xml'" in message


def test_the_tally_counts_only_the_members_that_are_not_waived():
    """Waived drift in the tally would bury one real regression in eight decoys.

    In the round-trip freeze every part the library rewrites differs and is
    allowed to, so a tally taken over all differences names them all.
    """
    before = manifest(("a.xml", b"<Doc a='1'/>"), ("b.xml", b"<Doc/>"), ("c.xml", b"<Doc a='1'/>"))
    after = manifest(("a.xml", b'<Doc a="1" />'), ("b.xml", b"<Other/>"), ("c.xml", b'<Doc a="1" />'))
    with pytest.raises(AssertionError) as failure:
        assert_manifest_equal(before, after, allowed_changes={"bytes"})
    message = str(failure.value)
    assert message.startswith("package manifest mismatch at member 'b.xml'")
    assert "further member(s)" not in message


def test_the_failure_shows_a_canonical_diff():
    """A message that only says "they differ" is useless where it is read."""
    before = manifest(("a.xml", b"<Doc><Keep/><Cell N='PinX' V='1.25'/></Doc>"))
    after = manifest(("a.xml", b"<Doc><Keep/><Cell N='PinX' V='9.75'/></Doc>"))
    with pytest.raises(AssertionError) as failure:
        assert_manifest_equal(before, after)
    message = str(failure.value)
    assert '-<Cell N="PinX" V="1.25">' in message
    assert '+<Cell N="PinX" V="9.75">' in message
    assert "<Keep>" in message  # context around the change, not just the change


def test_the_failure_names_the_declaration_on_both_sides():
    before = manifest(("a.xml", b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Doc/>'))
    after = manifest(("a.xml", b"<?xml version='1.0' encoding='UTF-8'?><Doc/>"))
    with pytest.raises(AssertionError) as failure:
        assert_manifest_equal(before, after)
    message = str(failure.value)
    assert 'standalone="yes"' in message
    assert "unexpected changes: declaration, bytes" in message


def test_a_long_diff_is_truncated_rather_than_dumped():
    before = manifest(("a.xml", b"<Doc>" + b"".join(b"<C V='%d'/>" % n for n in range(200)) + b"</Doc>"))
    after = manifest(("a.xml", b"<Doc>" + b"".join(b"<C V='x%d'/>" % n for n in range(200)) + b"</Doc>"))
    with pytest.raises(AssertionError) as failure:
        assert_manifest_equal(before, after, max_diff_lines=10)
    assert "further diff lines suppressed" in str(failure.value)


def test_allowed_changes_suppress_only_the_kinds_listed():
    before = manifest(("a.xml", b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Doc/>'))
    after = manifest(("a.xml", b"<?xml version='1.0' encoding='UTF-8'?><Other/>"))
    with pytest.raises(AssertionError, match="unexpected changes: canonical"):
        assert_manifest_equal(before, after, allowed_changes={"*": ("declaration", "bytes")})


def test_allowed_changes_apply_to_the_members_their_pattern_matches():
    before = manifest(("visio/pages/page1.xml", b"<Doc a='1'/>"), ("visio/document.xml", b"<Doc a='1'/>"))
    after = manifest(("visio/pages/page1.xml", b'<Doc a="1" />'), ("visio/document.xml", b'<Doc a="1" />'))
    assert_manifest_equal(before, after, allowed_changes={"visio/*": ("bytes",)})
    with pytest.raises(AssertionError, match=r"member 'visio/document\.xml'"):
        assert_manifest_equal(before, after, allowed_changes={"visio/pages/*": ("bytes",)})


def test_the_content_types_part_can_be_named_as_a_pattern():
    """`[Content_Types].xml` is a valid fnmatch pattern that does not match itself.

    It reads as a one-character class, so an allowance written out by hand would
    silently cover nothing. Every package has this part, so the trap is not
    hypothetical.
    """
    assert member_matches("[Content_Types].xml", "[Content_Types].xml")
    before = manifest(("[Content_Types].xml", content_types()), ("a.xml", b"<Doc a='1'/>"))
    after = manifest(("[Content_Types].xml", content_types() + b"\n"), ("a.xml", b"<Doc a='1'/>"))
    assert_manifest_equal(before, after, allowed_changes={"[Content_Types].xml": ("bytes",)})


def test_a_bare_collection_of_kinds_applies_to_every_member():
    before = manifest(("a.xml", b"<Doc a='1'/>"), ("b.xml", b"<Doc a='1'/>"))
    after = manifest(("a.xml", b'<Doc a="1" />'), ("b.xml", b'<Doc a="1" />'))
    assert_manifest_equal(before, after, allowed_changes={"bytes"})


def test_an_unknown_change_kind_is_rejected():
    """A typo in an allowance would otherwise read as "allow nothing", quietly."""
    empty = manifest(("a.xml", b"<Doc/>"))
    with pytest.raises(ValueError, match="unknown change kind"):
        assert_manifest_equal(empty, empty, allowed_changes={"*": ("declarations",)})


def test_a_bare_string_is_not_taken_as_a_collection_of_kinds():
    """`allowed_changes="bytes"` would otherwise be read one letter at a time."""
    empty = manifest(("a.xml", b"<Doc/>"))
    with pytest.raises(ValueError, match="takes a collection of change kinds"):
        assert_manifest_equal(empty, empty, allowed_changes="bytes")


def test_an_added_member_is_reported():
    before = manifest(("a.xml", b"<Doc/>"))
    after = manifest(("a.xml", b"<Doc/>"), ("visio/media/image1.png", b"\x89PNG"))
    with pytest.raises(AssertionError, match=r"member 'visio/media/image1\.png'") as failure:
        assert_manifest_equal(before, after)
    assert "unexpected changes: added" in str(failure.value)


def test_a_removed_member_is_reported():
    before = manifest(("a.xml", b"<Doc/>"), ("visio/vbaProject.bin", b"\x00"))
    after = manifest(("a.xml", b"<Doc/>"))
    with pytest.raises(AssertionError, match="unexpected changes: removed"):
        assert_manifest_equal(before, after)


def test_a_reordered_member_is_reported():
    before = manifest(("a.xml", b"<Doc/>"), ("b.xml", b"<Doc/>"))
    after = manifest(("b.xml", b"<Doc/>"), ("a.xml", b"<Doc/>"))
    with pytest.raises(AssertionError) as failure:
        assert_manifest_equal(before, after)
    assert "unexpected changes: order" in str(failure.value)
    assert "position in the archive: 0 -> 1" in str(failure.value)


def test_a_changed_package_kind_is_reported_whatever_is_allowed():
    """Losing the macro-enabled content type is never re-serialisation drift."""
    before = manifest(("[Content_Types].xml", content_types(MACRO_ENABLED_CONTENT_TYPE)))
    after = manifest(("[Content_Types].xml", content_types(DRAWING_CONTENT_TYPE)))
    with pytest.raises(AssertionError, match="package kind changed"):
        assert_manifest_equal(before, after, allowed_changes={"*": ("declaration", "namespaces", "canonical", "bytes")})


# --------------------------------------------------------------------------
# round-trip fidelity: the behaviour freeze
# --------------------------------------------------------------------------

# `save_vsdx` re-serialises every part it holds as an ElementTree, and
# ElementTree writes its own XML declaration, its own attribute quoting and
# `<Cell />` where Visio wrote `<Cell/>`. None of that changes the XML, so it
# shows up as a declaration and a bytes difference with the canonical hash
# intact. Issue #89 is what drives this to nothing.
RESERIALISATION_DRIFT = ("declaration", "bytes")

# ElementTree emits only the namespace declarations a part actually uses, and
# Visio puts `xmlns:r` on the root of every content part whether it needs it or
# not. Allowed only on the parts where it has been measured: the character
# classes keep `masters.xml` and `pages.xml`, which declare nothing they do not
# use, outside the waiver.
UNUSED_NAMESPACE_DECLARATIONS = {
    "visio/document.xml": ("namespaces",),
    "visio/masters/master[0-9]*.xml": ("namespaces",),
    "visio/pages/page[0-9]*.xml": ("namespaces",),
}

# The parts `save_vsdx` writes back, and so the only ones that may differ at
# all. Everything else -- the theme, the thumbnail, `windows.xml`,
# `masters.xml`, the images, `vbaProject.bin` -- is copied out of the source
# archive and has to arrive byte for byte.
REWRITTEN_PARTS = (
    "[Content_Types].xml",
    "docProps/app.xml",
    "visio/document.xml",
    "visio/_rels/document.xml.rels",
    "visio/pages/pages.xml",
    "visio/pages/_rels/pages.xml.rels",
    "visio/pages/_rels/page[0-9]*.xml.rels",
    "visio/pages/page[0-9]*.xml",
    "visio/masters/master[0-9]*.xml",
)


@pytest.fixture(scope="session")
def round_trip(tmp_path_factory):
    """Open a fixture and save it unchanged; return the manifests either side.

    Session-scoped and memoised because the save is the expensive part and more
    than one test asks about the same package.
    """
    saved: dict[str, tuple[PackageManifest, PackageManifest]] = {}

    def _round_trip(package_path: str) -> tuple[PackageManifest, PackageManifest]:
        if package_path not in saved:
            source = os.path.join(BASEDIR, package_path)
            destination = tmp_path_factory.mktemp("round_trip") / os.path.basename(package_path)
            with vsdx.VisioFile(source) as vis:
                vis.save_vsdx(str(destination))
            saved[package_path] = (
                PackageManifest.from_path(source),
                PackageManifest.from_path(str(destination)),
            )
        return saved[package_path]

    return _round_trip


def test_the_fixture_corpus_is_not_empty():
    """A discovery bug would otherwise turn the freeze below into no test at all."""
    assert len(FIXTURE_PACKAGES) > 20
    assert any(name.endswith(".vsdm") for name in FIXTURE_PACKAGES)


@pytest.mark.parametrize("package_path", FIXTURE_PACKAGES)
def test_a_round_trip_stays_within_the_known_drift(package_path, round_trip):
    """Open, save, change nothing: the package that comes back must be the same one.

    "The same" is defined by `tests/fixtures/package_manifests/KNOWN_DRIFT.md`,
    which lists what does move today and why. Anything else -- a part added,
    removed or reordered, a canonical form changed at all -- fails here, which
    is the point: the package rewrites in v1.0.0-alpha have to leave the bytes
    where they are.
    """
    before, after = round_trip(package_path)
    allowed: dict[str, tuple[str, ...]] = {"*": RESERIALISATION_DRIFT, **UNUSED_NAMESPACE_DECLARATIONS}
    assert_manifest_equal(before, after, allowed_changes=allowed)


@pytest.mark.parametrize("package_path", FIXTURE_PACKAGES)
def test_only_the_parts_the_library_rewrites_drift_at_all(package_path, round_trip):
    """A part that starts drifting is a part the save path has started touching.

    Worth its own failure rather than folding into the allowances above, because
    what matters here is that the part was written at all, whatever changed
    inside it.
    """
    before, after = round_trip(package_path)
    drifted = sorted(manifest_differences(before, after))
    unexpected = [name for name in drifted if not any(member_matches(name, pattern) for pattern in REWRITTEN_PARTS)]
    assert unexpected == [], f"{package_path}: these parts used to be copied through unchanged"
