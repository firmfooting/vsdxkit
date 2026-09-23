"""Every part name is derived from a part name and a relationship Target by two rules (#91)."""

import pytest

from vsdxkit.partnames import relationships_part_name, target_part_name


@pytest.mark.parametrize(
    ("part_name", "expected"),
    [
        ("/visio/pages/page1.xml", "/visio/pages/_rels/page1.xml.rels"),
        ("/visio/masters/masters.xml", "/visio/masters/_rels/masters.xml.rels"),
        ("/visio/document.xml", "/visio/_rels/document.xml.rels"),
        ("/visio/media/image1.png", "/visio/media/_rels/image1.png.rels"),
        ("/[Content_Types].xml", "/_rels/[Content_Types].xml.rels"),
    ],
)
def test_a_parts_relationships_live_in_the_rels_folder_beside_it(part_name, expected):
    """Fails if a part's relationships part is not `<folder>/_rels/<name>.rels`, whatever kind of part it is."""
    assert relationships_part_name(part_name) == expected


@pytest.mark.parametrize(
    ("source", "target", "expected"),
    [
        ("/visio/pages/pages.xml", "page1.xml", "/visio/pages/page1.xml"),
        ("/visio/masters/masters.xml", "master3.xml", "/visio/masters/master3.xml"),
        ("/visio/document.xml", "pages/pages.xml", "/visio/pages/pages.xml"),
        ("/visio/pages/page1.xml", "../media/image1.png", "/visio/pages/../media/image1.png"),
        ("/[Content_Types].xml", "visio/document.xml", "/visio/document.xml"),
    ],
)
def test_a_target_is_joined_onto_its_source_parts_folder_as_written(source, target, expected):
    """Fails if a Target is joined onto anything but its source part's folder, or is rewritten on the way.

    Joined as written, not resolved: a `..` stays for the part-name check to
    refuse, which `tests/test_errors.py` pins. Resolving it the way OPC does
    is #378, and it changes this function and this test's fourth case.
    """
    assert target_part_name(source, target) == expected
