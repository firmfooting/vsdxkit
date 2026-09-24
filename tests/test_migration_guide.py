"""tools/check_migration_guide.py: every 0.8.0 name 1.0 removes is in the migration guide (#112)."""

import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_migration_guide", os.path.join(ROOT, "tools", "check_migration_guide.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = _load()


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.chdir(ROOT)
    return check.vsdxkit_modules()


def test_the_guide_names_every_removed_name(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert check.main() == 0


def test_a_removed_member_the_guide_does_not_name_is_reported(modules):
    assert check.unexplained(["vsdx.pages.Page.gone_in_one_oh"], [], modules) == ["vsdx.pages.Page.gone_in_one_oh"]


def test_a_removed_member_the_guide_names_is_accepted(modules):
    assert check.unexplained(["vsdx.pages.Page.gone_in_one_oh"], ["page.gone_in_one_oh()"], modules) == []


def test_a_name_1_0_keeps_needs_no_entry(modules):
    assert check.unexplained(["vsdx.pages.Page.name", "vsdx.shapes.Shape.text"], [], modules) == []


def test_a_renamed_class_is_looked_up_under_its_new_name(modules):
    assert check.unexplained(["vsdx.vsdxfile.VisioFile.save"], [], modules) == []
    assert check.unexplained(["vsdx.containers.Container.lanes"], [], modules) == []


def test_a_moved_class_is_named_but_its_kept_members_are_not(modules):
    names = ["vsdx.vsdxfile.PackageLimits", "vsdx.vsdxfile.PackageLimits.max_members", "vsdx.vsdxfile.PackageLimits.gone"]

    assert check.unexplained(names, ["vsdxkit.package.PackageLimits"], modules) == ["vsdx.vsdxfile.PackageLimits.gone"]


def test_a_gone_class_explains_its_members(modules):
    assert check.unexplained(["vsdx.media.Media", "vsdx.media.Media.rectangle"], ["vsdx.media.Media"], modules) == []


def test_a_root_name_needs_its_root_import(modules):
    assert check.unexplained(["vsdx.Page"], ["Page"], modules) == ["vsdx.Page (as `from vsdx import Page`)"]
    assert check.unexplained(["vsdx.Page"], ["from vsdx import Page, PagePosition"], modules) == []


def test_code_blocks_count_as_literals():
    text = "Title\n\n.. code-block:: python\n\n   vis.gone_call()\n\nProse gone_prose.\n"

    literals = check.guide_literals(text)

    assert "   vis.gone_call()" in literals
    assert not any("gone_prose" in literal for literal in literals)
