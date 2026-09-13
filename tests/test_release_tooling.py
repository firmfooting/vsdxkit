"""The release workflow's pre-publish checks.

A tag that does not match `vsdx.__version__` would publish a distribution whose
version is not the one being tagged, and PyPI accepts each version exactly once,
so the mistake is not correctable after the fact.
"""

import importlib.util
import os

import pytest

import vsdx

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
    assert check_version_tag.packaged_version() == vsdx.__version__


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
    assert capsys.readouterr().out.strip() == vsdx.__version__


def test_main_requires_a_tag_argument():
    assert check_version_tag.main([]) == 2


release_check = _load("release_check")

CHANGELOG = """# Changelog

## Unreleased

### Added

- something in flight

## 0.7.0 - 2026-10-30

### Fixed

- the thing this release fixes
- and another

## 0.6.3

- older release
"""


def test_a_released_version_has_a_section(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert release_check.section_for("0.7.0", changelog) is not None


def test_the_section_body_stops_at_the_next_release(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    body = release_check.section_for("0.7.0", changelog)
    assert "the thing this release fixes" in body
    assert "older release" not in body
    assert "something in flight" not in body


def test_an_empty_section_does_not_count_as_documented(tmp_path):
    """A heading with nothing under it would publish a release with a blank body.

    The likely route is the one CONTRIBUTING describes: after cutting a release
    candidate the Unreleased block is empty, so renaming it for the final
    release leaves a heading and no entries.
    """
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## Unreleased\n\n### Added\n\n- not moved down\n\n## 0.7.0 - 2026-10-30\n\n## 0.6.3\n\n- old\n",
        encoding="utf-8",
    )
    assert release_check.main(["0.7.0", "--changelog", str(changelog)]) == 1


def test_a_whitespace_only_section_does_not_count_as_documented(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## 0.7.0 - 2026-10-30\n\n   \n\n## 0.6.3\n\n- old\n", encoding="utf-8")
    assert release_check.main(["0.7.0", "--changelog", str(changelog)]) == 1


def test_a_version_with_no_section_is_reported(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert release_check.section_for("0.9.0", changelog) is None


def test_an_unreleased_only_entry_does_not_count_as_the_release(tmp_path):
    """Tagging before moving Unreleased into a dated section must fail."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## Unreleased\n\n- pending\n", encoding="utf-8")
    assert release_check.section_for("0.7.0", changelog) is None


def test_a_bracketed_keep_a_changelog_heading_is_accepted(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## [0.7.0] - 2026-10-30\n\n- done\n", encoding="utf-8")
    assert release_check.section_for("0.7.0", changelog) is not None


def test_main_fails_when_the_section_is_missing(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert release_check.main(["0.9.0", "--changelog", str(changelog)]) == 1
    assert "0.9.0" in capsys.readouterr().out


def test_main_prints_the_section_when_asked(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(CHANGELOG, encoding="utf-8")
    assert release_check.main(["0.7.0", "--changelog", str(changelog), "--print"]) == 0
    assert "the thing this release fixes" in capsys.readouterr().out


def test_the_projects_own_changelog_has_no_section_for_an_unreleased_version():
    """Guards the guard: the repo changelog must not already claim 99.0.0."""
    assert release_check.section_for("99.0.0") is None
