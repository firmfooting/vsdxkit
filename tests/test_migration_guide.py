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
    assert check.unexplained(["vsdx.pages.Page.gone_in_one_oh"], [], modules) == [
        "vsdx.pages.Page.gone_in_one_oh (as `Page.gone_in_one_oh`)"
    ]


def test_a_removed_member_named_on_its_owner_is_accepted(modules):
    assert check.unexplained(["vsdx.pages.Page.gone_in_one_oh"], ["page.gone_in_one_oh()"], modules) == []
    assert check.unexplained(["vsdx.pages.Page.gone_in_one_oh"], ["vis.pages[0].gone_in_one_oh"], modules) != []
    assert check.unexplained(["vsdx.pages.Page.gone_in_one_oh"], ["Page.gone_in_one_oh"], modules) == []


def test_a_member_named_bare_or_on_another_owner_is_reported(modules):
    """Fails if an entry for one owner's member stands in for another's, as `connector.retarget` did for `Connect.retarget`."""
    for literals in (["gone_in_one_oh()"], ["shape.gone_in_one_oh()"]):
        assert check.unexplained(["vsdx.pages.Page.gone_in_one_oh"], literals, modules) != []


def test_a_mixin_member_is_named_on_the_document(modules):
    assert check.unexplained(["vsdx.templating.JinjaTemplatingMixin.gone"], ["vis.gone(context)"], modules) == []


def test_a_module_level_name_is_named_with_its_module(modules):
    assert check.unexplained(["vsdx.xmlio.gone_fn"], ["gone_fn(tree)"], modules) == ["vsdx.xmlio.gone_fn (as `xmlio.gone_fn`)"]
    assert check.unexplained(["vsdx.xmlio.gone_fn"], ["vsdx.xmlio.gone_fn(tree)"], modules) == []


def test_a_name_1_0_keeps_needs_no_entry(modules):
    assert check.unexplained(["vsdx.pages.Page.name", "vsdx.shapes.Shape.text", "vsdx.namespace"], [], modules) == []


def test_a_name_a_module_only_imports_is_not_kept(modules):
    """Fails if an incidental import counts as the module keeping the name, as `vsdxkit.shapes.to_float` did."""
    assert check.unexplained(["vsdx.shapes.to_float"], [], modules) == ["vsdx.shapes.to_float (as `shapes.to_float`)"]


def test_an_attribute_assigned_on_self_is_kept(modules):
    """Fails if a member 1.0 keeps as an instance attribute is reported, or one it dropped is not."""
    assert check.unexplained(["vsdx.pages.Page.vis", "vsdx.shapes.DataProperty.label"], [], modules) == []
    assert check.unexplained(["vsdx.containers.Container.page"], [], modules) == [
        "vsdx.containers.Container.page (as `Container.page`)"
    ]


def test_a_renamed_class_is_looked_up_under_its_new_name(modules):
    assert check.unexplained(["vsdx.vsdxfile.VisioFile.save"], [], modules) == []
    assert check.unexplained(["vsdx.containers.Container.lanes"], [], modules) == []


def test_a_moved_class_is_named_but_its_kept_members_are_not(modules):
    names = ["vsdx.vsdxfile.PackageLimits", "vsdx.vsdxfile.PackageLimits.max_members", "vsdx.vsdxfile.PackageLimits.gone"]

    assert check.unexplained(names, ["vsdx.vsdxfile.PackageLimits"], modules) == [
        "vsdx.vsdxfile.PackageLimits.gone (as `PackageLimits.gone`)"
    ]


def test_each_member_of_a_gone_class_is_named(modules):
    names = ["vsdx.media.Media", "vsdx.media.Media.rectangle"]

    assert check.unexplained(names, ["vsdx.media.Media"], modules) == ["vsdx.media.Media.rectangle (as `Media.rectangle`)"]
    assert check.unexplained(names, ["vsdx.media.Media", "Media.rectangle"], modules) == []


def test_a_root_name_needs_its_root_import(modules):
    assert check.unexplained(["vsdx.Page"], ["Page"], modules) == ["vsdx.Page (as `from vsdx import Page`)"]
    assert check.unexplained(["vsdx.Page"], ["from vsdx import Page, PagePosition"], modules) == []


def test_a_value_0_8_published_under_a_new_name_is_in_the_snapshot(monkeypatch):
    """Fails if the aliases `relationships` bound with `from vsdx import x as NEW` drop out of the surface checked.

    0.8.0 chose those names, and the guide has an entry for them; without them in
    the snapshot, deleting the entry would leave the check green.
    """
    monkeypatch.chdir(ROOT)
    with open(check.SNAPSHOT, encoding="utf-8") as snapshot:
        names = set(snapshot.read().split())

    assert {"vsdx.relationships.CONTENT_TYPES_NS", "vsdx.relationships.RELATIONSHIPS_NS"} <= names
    assert check.unexplained(["vsdx.relationships.CONTENT_TYPES_NS"], [], check.vsdxkit_modules())


def test_code_blocks_count_as_literals():
    text = "Title\n\n.. code-block:: python\n\n   vis.gone_call()\n\nProse gone_prose.\n"

    literals = check.guide_literals(text)

    assert "   vis.gone_call()" in literals
    assert not any("gone_prose" in literal for literal in literals)
