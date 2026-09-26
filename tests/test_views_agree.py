"""The public views restate their classes' API, and nothing checks that but this (#114).

`PageView` is the type of `shape.page`, and `DocumentView` the type of
`page.vis`. pyrefly checks only that `Page` and `Document` satisfy them, which
a smaller view, or one with another default, still does. `docs/classes.rst`
lists `Page`'s members by hand, a third copy.
"""

import copy
import inspect
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.pages import DocumentView, Page
from vsdxkit.shapes import PageView

CLASSES_RST = Path(__file__).resolve().parents[1] / "docs" / "classes.rst"

# what PageView's docstring says it leaves out: the members whose types are
# declared above `shapes`
PAGE_ONLY = {"swimlanes", "require_swimlanes", "vis"}

# what DocumentView's docstring says it lists
DOCUMENT_VIEW = {"pages", "save", "render"}


def _public(cls: type) -> set[str]:
    return {name for name in dir(cls) if not name.startswith("_")}


def _member(cls: type, name: str) -> object:
    return inspect.getattr_static(cls, name)


def _signature(cls: type, name: str) -> inspect.Signature:
    member = _member(cls, name)
    return inspect.signature(member.fget if isinstance(member, property) else member)


def test_page_view_leaves_out_only_what_it_says_it_does():
    """Fails if `PageView` drops a page member, or `Page` gains one the view does not list."""
    assert _public(Page) - _public(PageView) == PAGE_ONLY
    assert _public(PageView) <= _public(Page)


def test_document_view_lists_what_it_says_it_does():
    """Fails if `DocumentView` drops `pages`, `save` or `render`, or lists a name `Document` lacks."""
    assert _public(DocumentView) == DOCUMENT_VIEW
    assert _public(DocumentView) <= _public(Document)


def test_each_view_member_has_the_concrete_signature():
    """Fails if a view's parameters, defaults or annotations drift from the class it restates.

    No getter or method narrows: each is the concrete member's signature
    exactly. The setters are compared below.
    """
    for view, concrete in ((PageView, Page), (DocumentView, Document)):
        for name in sorted(_public(view)):
            is_property = isinstance(_member(view, name), property)
            assert is_property == isinstance(_member(concrete, name), property), f"{view.__name__}.{name}"
            assert _signature(view, name) == _signature(concrete, name), f"{view.__name__}.{name}"


def _setters(cls: type, names: set[str]) -> set[str]:
    return {name for name in names if getattr(_member(cls, name), "fset", None) is not None}


def test_each_view_can_set_exactly_what_its_class_can():
    """Fails if a view drops one of its class's setters, or declares one the class lacks.

    Typed code writes a page through ``shape.page`` as it writes one through
    ``document.pages[0]`` (Phase 7, decision 3). ``Document`` has no public
    setter, so ``DocumentView`` has none either.
    """
    for view, concrete in ((PageView, Page), (DocumentView, Document)):
        listed = _public(view)
        assert _setters(view, listed) == _setters(concrete, listed), view.__name__
    assert _setters(PageView, _public(PageView)) == {"name", "background", "width", "height", "xml"}


def test_each_view_setter_takes_what_its_class_setter_takes():
    """Fails if a view setter's value type drifts from the class's.

    ``xml`` is the one narrowing: the view takes a ``PartTree``, and ``Page``
    also takes ``None``, only to refuse it. mypy reads ``Page``'s class-level
    ``xml: PartTree`` as the setter's type, so a view that took ``None`` too
    would stop ``Page`` satisfying it.
    """
    for name in sorted(_setters(PageView, _public(PageView))):
        view_setter = inspect.signature(_member(PageView, name).fset)
        page_setter = inspect.signature(_member(Page, name).fset)
        if name == "xml":
            assert view_setter.parameters["value"].annotation == "PartTree"
            assert page_setter.parameters["value"].annotation == "PartTree | None"
            continue
        assert view_setter == page_setter, name


def test_a_write_through_shape_page_is_a_write_to_the_page(vsdx_copy, tmp_path):
    """Fails if a setter reached through the view does anything but what `Page`'s does."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shape = next(iter(page.children))

    shape.page.name = "Through the view"
    shape.page.width = "11"
    shape.page.background = False

    assert page.name == "Through the view"
    assert page.width == 11.0
    saved = Document.open(vis.save(tmp_path / "saved.vsdx"))
    assert saved.pages[0].name == "Through the view"


def test_a_tree_assigned_through_shape_page_is_saved_and_detaches_the_shape_that_led_there(vsdx_copy, tmp_path):
    """Fails if ``shape.page.xml = tree`` does not replace the page's part, or leaves `shape` reading a tree no longer saved.

    The view is writable now (Phase 7, decision 3), so this is one typed line.
    The page's shapes are the new tree's; the shape the caller went through
    wraps an element of the old one, and says so rather than answering from it.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    shape = next(iter(page.children))
    shape_id = shape.ID
    replacement = ET.ElementTree(copy.deepcopy(page.xml.getroot()))

    shape.page.xml = replacement

    assert page.xml is replacement
    assert not shape.is_attached
    with pytest.raises(InvalidOperationError, match="no longer in the document"):
        _ = shape.text
    assert page.children.require_id(shape_id).xml is not shape.xml
    reopened = Document.open(vis.save(tmp_path / "saved.vsdx"))
    assert reopened.pages[0].children.require_id(shape_id) is not None


def test_the_reference_documents_every_page_member_the_view_lists():
    """Fails if `docs/classes.rst` misses a `PageView` member, or names one `Page` no longer has."""
    if not CLASSES_RST.exists():
        pytest.skip("docs/ is not in the sdist; the checkout runs this")
    match = re.search(r"autoclass:: vsdxkit\.pages\.Page\n\s+:members: (.+)\n", CLASSES_RST.read_text(encoding="utf-8"))
    assert match is not None, "the Page autoclass has no :members: line"
    documented = {name.strip() for name in match.group(1).split(",")}
    assert documented == _public(PageView) | PAGE_ONLY
