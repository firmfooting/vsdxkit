"""`PageCollection`: a document's pages, and the one place pages are created, copied and deleted (Phase 3, #99).

Each test names the defect it pins. Every saved package goes through the
autouse structural validator, so a page added, copied or removed here must
also leave pages.xml, its relationships, the content types and app.xml
consistent.
"""

from collections.abc import Sequence

import pytest

from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError, NotFoundError, PackageError
from vsdxkit.pages import Page, PageCollection


def _names(vis: Document) -> list[str]:
    return [page.name for page in vis.pages]


def test_the_document_s_pages_are_a_page_collection(vsdx_copy):
    """Fails if `Document.pages` is a bare list, which callers could mutate behind the package's back."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    pages = vis.pages
    assert isinstance(pages, PageCollection)
    assert isinstance(pages, Sequence)
    assert not isinstance(pages, list)
    assert len(pages) == 3
    assert [page.name for page in pages] == ["Page-1", "Page-2", "Page-3"]
    assert pages[-1] is pages[2]
    assert pages.index(pages[1]) == 1
    assert pages[1] in pages
    assert isinstance(pages[0:2], tuple)
    with pytest.raises(IndexError):
        pages[3]


def test_a_page_is_found_by_name(vsdx_copy):
    """Fails if a lookup by name answers wrongly for a present or an absent page."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    assert vis.pages.by_name("Page-2") is vis.pages[1]
    assert vis.pages.by_name("No such page") is None
    with pytest.raises(NotFoundError, match="No such page"):
        vis.pages.require_name("No such page")


def test_two_pages_with_one_name_are_a_package_error(vsdx_copy):
    """Fails if a document holding two pages of one name answers with either: Visio keeps page names unique."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    vis.pages[2].name = "Page-1"
    with pytest.raises(PackageError, match="Page-1"):
        vis.pages.by_name("Page-1")


def test_create_appends_by_default_and_inserts_where_asked(vsdx_copy, tmp_path):
    """Fails if `create` puts a page anywhere but the end, or the index it was given."""
    saved = str(tmp_path / "test1_created.vsdx")
    vis = Document.open(vsdx_copy("test1.vsdx"))
    last = vis.pages.create("Last")
    first = vis.pages.create("First", index=0)
    end = vis.pages.create("End", index=len(vis.pages))
    assert _names(vis) == ["First", "Page-1", "Page-2", "Page-3", "Last", "End"]
    assert isinstance(last, Page) and vis.pages[0] is first and vis.pages[-1] is end
    vis.save(saved)
    reopened = Document.open(saved)
    assert _names(reopened) == ["First", "Page-1", "Page-2", "Page-3", "Last", "End"]


@pytest.mark.parametrize("index", [-1, -2, 4, 99])
def test_create_refuses_an_index_outside_the_pages(vsdx_copy, index):
    """Fails if an index past either end is accepted: -1 used to mean "before the last page", and -2 raised late."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    with pytest.raises(InvalidOperationError, match=str(index)):
        vis.pages.create("Nowhere", index=index)
    assert _names(vis) == ["Page-1", "Page-2", "Page-3"]


def test_copy_places_the_copy_after_its_page_unless_told_otherwise(vsdx_copy, tmp_path):
    """Fails if a copy lands anywhere but straight after its original, or the index it was given."""
    saved = str(tmp_path / "test1_copied.vsdx")
    vis = Document.open(vsdx_copy("test1.vsdx"))
    original = vis.pages[0]
    after = vis.pages.copy(original, name="Copy after")
    at_end = vis.pages.copy(original, name="Copy at end", index=len(vis.pages))
    assert _names(vis) == ["Page-1", "Copy after", "Page-2", "Page-3", "Copy at end"]
    assert len(after.children) == len(original.children) == len(at_end.children)
    vis.save(saved)


def test_copy_refuses_a_page_of_another_document(vsdx_copy):
    """Fails if a page from another document is copied: cross-document page copy is outside 1.0."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    other = Document.open(vsdx_copy("test2.vsdx"))
    with pytest.raises(InvalidOperationError, match="another document"):
        vis.pages.copy(other.pages[0])
    assert _names(vis) == ["Page-1", "Page-2", "Page-3"]


def test_delete_removes_the_page_and_its_parts(vsdx_copy, tmp_path):
    """Fails if a deleted page lingers in the collection or leaves its part behind."""
    saved = str(tmp_path / "test1_deleted.vsdx")
    vis = Document.open(vsdx_copy("test1.vsdx"))
    doomed = vis.pages[1]
    vis.pages.delete(doomed)
    assert _names(vis) == ["Page-1", "Page-3"]
    assert doomed not in vis.pages
    assert vis._package.part(doomed.filename) is None
    vis.save(saved)


def test_delete_refuses_a_page_this_document_does_not_hold(vsdx_copy):
    """Fails if deleting a foreign page removes whichever page of this document sits at its index."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    other = Document.open(vsdx_copy("test2.vsdx"))
    with pytest.raises(InvalidOperationError, match="Page-2"):
        vis.pages.delete(other.pages[1])
    assert _names(vis) == ["Page-1", "Page-2", "Page-3"]


def test_the_collection_is_live(vsdx_copy):
    """Fails if a collection taken before a change does not see it."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    pages = vis.pages
    vis.add_page("Added")
    assert len(pages) == 4
    assert pages.by_name("Added") is pages[-1]
