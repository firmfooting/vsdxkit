"""A page created at an index lands there, and one created with none is appended."""

from vsdxkit.document import Document


def test_create_places_a_page_at_its_index_or_at_the_end(vsdx_copy):
    vis = Document.open(vsdx_copy("test1.vsdx"))
    first = vis.pages.create("first-added", index=0)
    assert vis.pages.index(first) == 0

    at_one = vis.pages.create("at-one", index=1)
    assert vis.pages.index(at_one) == 1

    at_end = vis.pages.create("at-end", index=len(vis.pages))
    assert vis.pages.index(at_end) == len(vis.pages) - 1

    appended = vis.pages.create("appended")
    assert vis.pages.index(appended) == len(vis.pages) - 1
