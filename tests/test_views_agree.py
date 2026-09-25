"""The public views restate their classes' API, and nothing checks that but this (#114).

`PageView` is the type of `shape.page`, and `DocumentView` the type of
`page.vis`. pyrefly checks only that `Page` and `Document` satisfy them, which
a smaller view, or one with another default, still does. `docs/classes.rst`
lists `Page`'s members by hand, a third copy.
"""

import inspect
import re
from pathlib import Path

import pytest

from vsdxkit.document import Document
from vsdxkit.pages import DocumentView, Page
from vsdxkit.shapes import PageView

CLASSES_RST = Path(__file__).resolve().parents[1] / "docs" / "classes.rst"

# what PageView's docstring says it leaves out: the members whose types are
# declared above `shapes` ...
PAGE_ONLY = {"swimlanes", "require_swimlanes", "vis"}
# ... and the page's part-level attributes. `rels_xml` is the one on the
# class; `filename`, `page_id` and the rest are set in `__init__`, so no
# class-level walk sees them
PART_LEVEL = {"rels_xml"}

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
    assert _public(Page) - _public(PageView) == PAGE_ONLY | PART_LEVEL
    assert _public(PageView) <= _public(Page)


def test_document_view_lists_what_it_says_it_does():
    """Fails if `DocumentView` drops `pages`, `save` or `render`, or lists a name `Document` lacks."""
    assert _public(DocumentView) == DOCUMENT_VIEW
    assert _public(DocumentView) <= _public(Document)


def test_each_view_member_has_the_concrete_signature():
    """Fails if a view's parameters, defaults or annotations drift from the class it restates.

    No stub narrows today: each is the concrete member's signature exactly.
    """
    for view, concrete in ((PageView, Page), (DocumentView, Document)):
        for name in sorted(_public(view)):
            is_property = isinstance(_member(view, name), property)
            assert is_property == isinstance(_member(concrete, name), property), f"{view.__name__}.{name}"
            assert _signature(view, name) == _signature(concrete, name), f"{view.__name__}.{name}"


def test_the_views_are_read_only():
    """Fails if a view's property gains a setter: a page is changed through the `Page` a caller holds."""
    for view in (PageView, DocumentView):
        setters = [name for name in _public(view) if getattr(_member(view, name), "fset", None) is not None]
        assert setters == [], view.__name__


def test_the_reference_documents_every_page_member_the_view_lists():
    """Fails if `docs/classes.rst` misses a `PageView` member, or names one `Page` no longer has."""
    if not CLASSES_RST.exists():
        pytest.skip("docs/ is not in the sdist; the checkout runs this")
    match = re.search(r"autoclass:: vsdxkit\.pages\.Page\n\s+:members: (.+)\n", CLASSES_RST.read_text(encoding="utf-8"))
    assert match is not None, "the Page autoclass has no :members: line"
    documented = {name.strip() for name in match.group(1).split(",")}
    assert documented == _public(PageView) | PAGE_ONLY
