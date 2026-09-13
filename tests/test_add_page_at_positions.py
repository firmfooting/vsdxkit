"""Relative page positions must not silently append without a reference page."""

import io
import os
import xml.etree.ElementTree as ET

import pytest

from vsdxkit import PagePosition, VisioFile

FIXTURES = os.path.dirname(os.path.realpath(__file__))


def _pages_rels_root(visio_file):
    """The Relationship element root of the loaded package's pages.xml.rels."""
    for key, content in visio_file.zip_file_contents.items():
        if key.endswith("visio/pages/_rels/pages.xml.rels"):
            return ET.parse(io.BytesIO(content.getvalue())).getroot()
    raise AssertionError("pages.xml.rels not found in package")


@pytest.mark.parametrize("position", [PagePosition.BEFORE, PagePosition.AFTER])
def test_add_page_at_rejects_relative_position_without_reference_page(vsdx_copy, tmp_path, position):
    path = os.path.join(FIXTURES, "test1.vsdx")
    copy_path = vsdx_copy("test1.vsdx")
    output = os.path.join(str(tmp_path), "out.vsdx")
    with VisioFile(path) as reference:
        names_before = [p.name for p in reference.pages]
        reference_rels = [rel for rel in _pages_rels_root(reference) if "page" in rel.attrib.get("Target", "")]
    with VisioFile(copy_path) as vis:
        with pytest.raises(ValueError, match="requires a reference page"):
            vis.add_page_at(position, "new")
        assert [p.name for p in vis.pages] == names_before  # nothing appended
        vis.save_vsdx(output)  # a rejected call must leave nothing to persist

    with VisioFile(output) as reloaded:
        assert [p.name for p in reloaded.pages] == names_before
        page_rels = [rel for rel in _pages_rels_root(reloaded) if "page" in rel.attrib.get("Target", "")]
        assert len(page_rels) == len(reference_rels)  # no dangling relationship


def test_add_page_at_integer_and_relative_positions_place_correctly(vsdx_copy):
    path = vsdx_copy("test1.vsdx")
    with VisioFile(path) as vis:
        first = vis.add_page_at(PagePosition.FIRST, "first-added")
        assert vis.pages.index(first) == 0

        at_one = vis.add_page_at(1, "at-one")
        assert vis.pages.index(at_one) == 1

        last = vis.add_page_at(PagePosition.LAST, "last-added")
        assert vis.pages.index(last) == len(vis.pages) - 1

        appended = vis.add_page("appended")
        assert vis.pages.index(appended) == len(vis.pages) - 1
