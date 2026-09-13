"""The release workflow's pre-publish checks.

A tag that does not match `vsdxkit.__version__` would publish a distribution whose
version is not the one being tagged, and PyPI accepts each version exactly once,
so the mistake is not correctable after the fact.
"""

import importlib.util
import os

import pytest

import vsdxkit

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "tools")


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(TOOLS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_version_tag = _load("check_version_tag")


@pytest.mark.parametrize("tag", ["v1.2.3", "refs/tags/v1.2.3", "1.2.3"])
def test_matching_tag_is_accepted(tag):
    assert check_version_tag.mismatch(tag, "1.2.3") is None


def test_mismatched_tag_is_reported_with_both_values():
    message = check_version_tag.mismatch("v0.8.0", "0.7.0")
    assert message is not None
    assert "0.8.0" in message and "0.7.0" in message


def test_a_tag_that_is_not_a_version_is_rejected():
    assert check_version_tag.mismatch("nightly", "0.7.0") is not None


@pytest.mark.parametrize("version", ["1.2.3", "1.2.3rc1", "1.2.3b2", "1.2.3.post1"])
def test_release_and_prerelease_spellings_are_accepted(version):
    assert check_version_tag.mismatch(f"v{version}", version) is None


def test_the_packaged_version_is_read_from_the_module():
    """The check must read the real module, not a copy of the number."""
    assert check_version_tag.packaged_version() == vsdxkit.__version__


def test_main_exits_non_zero_on_mismatch(capsys, monkeypatch):
    monkeypatch.setattr(check_version_tag, "packaged_version", lambda: "0.7.0")
    assert check_version_tag.main(["v99.0.0"]) == 1
    assert "99.0.0" in capsys.readouterr().out


def test_main_exits_zero_on_match(monkeypatch):
    # pinned rather than read from the package, so a development version
    # spelling between releases cannot turn this red for an unrelated reason
    monkeypatch.setattr(check_version_tag, "packaged_version", lambda: "0.7.0")
    assert check_version_tag.main(["v0.7.0"]) == 0


def test_main_prints_the_packaged_version_on_request(capsys):
    """The release workflow reads the version from here rather than re-parsing it."""
    assert check_version_tag.main(["--print-version"]) == 0
    assert capsys.readouterr().out.strip() == vsdxkit.__version__


def test_main_requires_a_tag_argument():
    assert check_version_tag.main([]) == 2


release_check = _load("release_check")

# Shaped like release-please's own output: the version is a link label and the
# date is parenthesised. From 0.7.1 on, this is the only format the check sees
# on the automated path. The 0.7.0 section below it is the hand-written spelling
# the file used before, which a manual publish of an older version still meets.
CHANGELOG = """# Changelog

## [0.7.1](https://github.com/firmfooting/vsdxkit/compare/v0.7.0...v0.7.1) (2026-09-20)

### Bug Fixes

* the thing this release fixes ([#241](https://github.com/firmfooting/vsdxkit/issues/241))
* and another

## 0.7.0 - 2026-09-13

### Added

- older release
"""


def test_a_release_please_heading_is_matched(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert release_check.section_for("0.7.1", changelog) is not None


def test_the_section_body_stops_at_the_next_release(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    body = release_check.section_for("0.7.1", changelog)
    assert "the thing this release fixes" in body
    assert "older release" not in body


def test_an_empty_section_does_not_count_as_documented(tmp_path):
    """A heading with nothing under it announces a release and says nothing.

    Existence is the cheap test and it is not the one worth making: a section
    that parses but is empty publishes a version with no record of what changed,
    which is the outcome this module exists to prevent.
    """
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [0.7.1](https://example.invalid/compare) (2026-09-20)\n\n## 0.7.0 - 2026-09-13\n\n- old\n",
        encoding="utf-8",
    )
    assert release_check.main(["0.7.1", "--changelog", str(changelog)]) == 1


def test_a_whitespace_only_section_does_not_count_as_documented(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## 0.7.0 - 2026-09-13\n\n   \n\n## 0.6.3\n\n- old\n", encoding="utf-8")
    assert release_check.main(["0.7.0", "--changelog", str(changelog)]) == 1


def test_a_version_with_no_section_is_reported(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert release_check.section_for("0.9.0", changelog) is None


def test_a_prefix_of_a_released_version_is_not_a_match(tmp_path):
    """`0.7` must not borrow `0.7.1`'s section from inside the link label."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert release_check.section_for("0.7", changelog) is None


def test_the_hand_written_headings_still_parse(tmp_path):
    """Pre-0.7.1 sections are bare or Keep a Changelog; a manual publish may target one."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [0.6.3] - 2026-05-01\n\n- done\n", encoding="utf-8")
    assert release_check.section_for("0.6.3", changelog) is not None


def test_main_fails_when_the_section_is_missing(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert release_check.main(["0.9.0", "--changelog", str(changelog)]) == 1
    assert "0.9.0" in capsys.readouterr().out


def test_main_reports_the_documented_version(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert release_check.main(["0.7.1", "--changelog", str(changelog)]) == 0
    assert "0.7.1" in capsys.readouterr().out


def test_the_projects_own_changelog_has_no_section_for_an_unreleased_version():
    """Guards the guard: the repo changelog must not already claim 99.0.0."""
    assert release_check.section_for("99.0.0") is None
