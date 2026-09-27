"""Tests for the shared fixtures in conftest.py.

`_packages_written_are_structurally_sound` is autouse, so it cannot be driven
through a normal test the way a fixture-consuming function is; the tests here
exercise the pure piece of it, `_excused_kinds`, directly, against packages a
real fixture is known to leave with defects.
"""

import os
import shutil

import conftest
import pytest
from helpers.package_validator import validate_package


def test_a_bare_marker_excuses_every_kind_for_every_file():
    """No `kinds` and no `files`: unchanged from before `files` existed."""
    marker = pytest.mark.allow_invalid_package.mark

    assert conftest._excused_kinds("a.vsdx", marker) == frozenset()
    # a bare marker is handled by the fixture's own early return, not by
    # `_excused_kinds`; see `_packages_written_are_structurally_sound`.


def test_a_marker_naming_kinds_but_no_files_excuses_them_for_every_file():
    marker = pytest.mark.allow_invalid_package("missing-part", "duplicate-shape-id").mark

    assert conftest._excused_kinds("a.vsdx", marker) == frozenset({"missing-part", "duplicate-shape-id"})
    assert conftest._excused_kinds("b.vsdx", marker) == frozenset({"missing-part", "duplicate-shape-id"})


def test_a_marker_with_files_excuses_its_kinds_only_for_the_named_files():
    marker = pytest.mark.allow_invalid_package("missing-part", files=("a.vsdx",)).mark

    assert conftest._excused_kinds("a.vsdx", marker) == frozenset({"missing-part"})
    assert conftest._excused_kinds("b.vsdx", marker) == frozenset()


def test_no_marker_excuses_nothing():
    assert conftest._excused_kinds("a.vsdx", None) == frozenset()


@pytest.mark.allow_invalid_package("missing-part")
def test_a_files_marker_excuses_a_real_defect_in_the_named_file_only(tmp_path, basedir):
    """The regression the review named: one file's exemption must not blind the check to the same defect elsewhere.

    Both copies are `test5_master.vsdx`, so both carry its seven `missing-part`
    defects (KNOWN_NON_CONFORMANT in test_package_validator.py). A marker
    naming only `named.vsdx` must leave `other.vsdx`'s copies of that same
    defect unexcused.
    """
    named = tmp_path / "named.vsdx"
    other = tmp_path / "other.vsdx"
    shutil.copy(os.path.join(basedir, "test5_master.vsdx"), named)
    shutil.copy(os.path.join(basedir, "test5_master.vsdx"), other)
    marker = pytest.mark.allow_invalid_package("missing-part", files=("named.vsdx",)).mark

    named_defects = validate_package(str(named))
    other_defects = validate_package(str(other))
    assert named_defects and other_defects  # the fixture's known defects, present in both copies

    named_excused = conftest._excused_kinds("named.vsdx", marker)
    other_excused = conftest._excused_kinds("other.vsdx", marker)

    assert all(d.kind in named_excused for d in named_defects)
    assert any(d.kind not in other_excused for d in other_defects)
