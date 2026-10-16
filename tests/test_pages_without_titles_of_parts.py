"""Page create, copy and delete work on an app.xml with no TitlesOfParts (#390)."""

from vsdxkit import ext_prop_namespace
from vsdxkit.document import Document


def _without_titles(vsdx_copy) -> Document:
    vis = Document.open(vsdx_copy("test1.vsdx"))
    root = vis._app_xml.getroot()
    root.remove(root.find(f"{ext_prop_namespace}TitlesOfParts"))
    return vis


def test_create_works_without_titles_of_parts(vsdx_copy):
    vis = _without_titles(vsdx_copy)
    vis.pages.create("New")
    assert vis.pages[-1].name == "New"


def test_copy_works_without_titles_of_parts(vsdx_copy):
    vis = _without_titles(vsdx_copy)
    count = len(vis.pages)
    vis.pages.copy(vis.pages[0], name="Copy")
    assert len(vis.pages) == count + 1


def test_delete_works_without_titles_of_parts(vsdx_copy):
    vis = _without_titles(vsdx_copy)
    count = len(vis.pages)
    assert count > 1
    vis.pages.delete(vis.pages[-1])
    assert len(vis.pages) == count - 1
