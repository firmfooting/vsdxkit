"""Tests for the fixture rewriter, and for the guard that is the point of it.

See `helpers/broken_package` for what the guard is for. This is what says it
still fires.
"""

import zipfile

import pytest
from helpers.broken_package import append_member, make_package, rewritten

pytestmark = pytest.mark.allow_invalid_package  # none of these archives is a drawing


def _members(path: str) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


@pytest.fixture
def source(tmp_path) -> str:
    # two of each substitutable string, so a replacement that is not limited to
    # the first one has somewhere to show up
    return make_package(
        str(tmp_path / "source.vsdx"),
        {"a.xml": b"<Doc V='1'><Doc V='1'/></Doc>", "b.bin": b"\xff\xfe\xff"},
    )


def test_a_substitution_that_finds_nothing_fails_rather_than_passing_quietly(source, tmp_path):
    with pytest.raises(AssertionError, match="the fixture has changed"):
        rewritten(source, str(tmp_path / "out.vsdx"), {"a.xml": ("V='2'", "V='3'")})


def test_a_substitution_applies_to_the_first_occurrence_only(source, tmp_path):
    path = rewritten(source, str(tmp_path / "out.vsdx"), {"a.xml": ("V='1'", "V='9'")})

    assert _members(path)["a.xml"] == b"<Doc V='9'><Doc V='1'/></Doc>"


def test_a_member_that_is_not_utf_8_can_be_edited_as_bytes(source, tmp_path):
    """Decoding a binary part to make a text edit would raise before the edit ran."""
    path = rewritten(source, str(tmp_path / "out.vsdx"), {"b.bin": (b"\xff", b"\x00")})

    assert _members(path)["b.bin"] == b"\x00\xfe\xff"


def test_a_bytes_substitution_that_finds_nothing_fails_too(source, tmp_path):
    """The bytes branch needs the guard as much as the text one.

    The three callers that edit as bytes are editing a relationship target and a
    content type override, which is where a fixture is most likely to be
    respelled out from under them.
    """
    with pytest.raises(AssertionError, match="the fixture has changed"):
        rewritten(source, str(tmp_path / "out.vsdx"), {"b.bin": (b"\x7f", b"\x00")})


def test_a_member_can_be_replaced_outright(source, tmp_path):
    path = rewritten(source, str(tmp_path / "out.vsdx"), {"a.xml": b"<Other/>"})

    assert _members(path)["a.xml"] == b"<Other/>"


def test_a_member_can_be_dropped(source, tmp_path):
    path = rewritten(source, str(tmp_path / "out.vsdx"), {"a.xml": None})

    assert set(_members(path)) == {"b.bin"}


def test_a_member_can_be_renamed_and_another_added(source, tmp_path):
    path = rewritten(
        source,
        str(tmp_path / "out.vsdx"),
        {},
        added={"c.xml": b"<New/>"},
        renamed={"a.xml": "a b.xml"},
    )

    members = _members(path)
    assert set(members) == {"a b.xml", "b.bin", "c.xml"}
    assert members["a b.xml"] == b"<Doc V='1'><Doc V='1'/></Doc>"


def test_a_stale_edit_key_fails_rather_than_applying_to_nothing(source, tmp_path):
    """A part that has been renamed takes its edits with it, silently."""
    with pytest.raises(AssertionError, match="not members of"):
        rewritten(source, str(tmp_path / "out.vsdx"), {"gone.xml": ("a", "b")})


def test_append_member_adds_to_an_existing_archive(source):
    append_member(source, "d.xml", b"<Late/>")

    members = _members(source)
    assert members["d.xml"] == b"<Late/>"
    assert set(members) == {"a.xml", "b.bin", "d.xml"}, "appending must not disturb what was there"
