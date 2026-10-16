"""A master reads its own PageSheet even when a drawing page has its ID (#439)."""

from vsdxkit.document import Document


def test_a_master_sharing_a_drawing_pages_id_reads_its_own_page_sheet(vsdx_copy):
    """test4_connectors.vsdx: master "Router" and drawing page "Page-3" are both ID 7."""
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    router = next(m for m in vis.master_pages if m.name == "Router")
    page = next(p for p in vis.pages if p.name == "Page-3")
    assert router._page_id == page._page_id

    assert router.width != page.width
    router.width = 1.5
    assert router.width == 1.5
    assert page.width != 1.5


def test_a_master_without_a_unique_id_is_a_master_page(vsdx_copy):
    """test5_master.vsdx's master has no UniqueID; the lookup by it cannot say it is a master."""
    vis = Document.open(vsdx_copy("test5_master.vsdx"))
    master = vis.master_pages[0]
    assert master._master_unique_id is None

    assert master.is_master_page
    assert not vis.pages[0].is_master_page
