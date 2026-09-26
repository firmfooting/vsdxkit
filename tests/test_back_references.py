"""The back-references a caller reads: `shape.page`, `shape.parent` and `page.vis` (#114).

Phase 6 made them read-only properties over the references the library
keeps. Each returns the object it returned before, and a deleted shape still
answers.
"""

import pytest

from vsdxkit.document import Document


def _no_setter(name: str, owner: object) -> str:
    """What CPython says to an assignment to a property with no setter: 3.10's wording, then 3.11's."""
    return rf"^(can't set attribute '{name}'|property '{name}' of '{type(owner).__name__}' object has no setter)$"


def test_back_references_are_the_owning_objects(vsdx_copy):
    document = Document.open(vsdx_copy("test1.vsdx"))
    page = document.pages[0]
    shape = next(iter(page.children))
    assert page.vis is document
    assert shape.page is page
    assert shape.parent is page


def test_a_deleted_shape_still_names_its_page(vsdx_copy):
    page = Document.open(vsdx_copy("test1.vsdx")).pages[0]
    shape = next(iter(page.children))
    shape.delete()
    assert shape.page is page
    assert shape.parent is page


def test_append_shape_makes_the_group_the_parent(vsdx_copy):
    page = Document.open(vsdx_copy("test2.vsdx")).pages[0]
    group = page.shapes.require_id("9")
    member = page.shapes.require_id("6")
    group.append_shape(member)
    assert member.parent is group
    assert member.page is page


def test_the_back_references_are_read_only(vsdx_copy):
    """Fails if a caller can repoint a wrapper at another owner: the XML would not follow."""
    document = Document.open(vsdx_copy("test1.vsdx"))
    page = document.pages[0]
    shape = next(iter(page.children))
    with pytest.raises(AttributeError, match=_no_setter("page", shape)):
        shape.page = page
    with pytest.raises(AttributeError, match=_no_setter("parent", shape)):
        shape.parent = page
    with pytest.raises(AttributeError, match=_no_setter("vis", page)):
        page.vis = document
