"""Every part name is derived from a part name and a relationship Target by two rules (#91)."""

import pytest

from vsdxkit.partnames import folder_of, relationship_target, relationships_part_name, target_part_name


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


@pytest.mark.parametrize(
    ("part_name", "expected"),
    [
        ("/visio/masters/masters.xml", "/visio/masters/"),
        ("/visio/pages/page1.xml", "/visio/pages/"),
        ("/visio/document.xml", "/visio/"),
        ("/[Content_Types].xml", "/"),
    ],
)
def test_a_parts_folder_is_a_part_name_prefix_ending_in_a_slash(part_name, expected):
    """Fails if a part's folder is not the part-name prefix it sits under, trailing slash and all.

    The slash is what keeps a sibling such as `/visio/masters-old/` from
    matching the prefix `/visio/masters/`, and a part at the package root sits
    in `/`, not in an empty folder.
    """
    assert folder_of(part_name) == expected


@pytest.mark.parametrize(
    ("source", "part_name", "expected"),
    [
        ("/visio/pages/page1.xml", "/visio/masters/master1.xml", "../masters/master1.xml"),
        ("/visio/pages/page1.xml", "/visio/masters/sub/master2.xml", "../masters/sub/master2.xml"),
        ("/visio/pages/pages.xml", "/visio/pages/page3.xml", "page3.xml"),
    ],
)
def test_a_relationship_target_is_the_part_name_relative_to_its_source_parts_folder(source, part_name, expected):
    """Fails if the Target written to reach a part drops a folder of its part name, or is not relative to the source.

    A page reaching a master in a subfolder of the masters folder has to say
    that subfolder; a Target built from the master's file name alone points at
    a part the package does not hold.
    """
    assert relationship_target(source, part_name) == expected


def test_a_written_target_names_the_part_it_was_written_for():
    """Fails if `target_part_name` does not read back the part `relationship_target` wrote a Target for.

    Checked on a Target without `..`, because `target_part_name` joins a Target
    as written and leaves a `..` in the name. Normalising it, so the round trip
    holds for every Target, is #378's job.
    """
    source, part_name = "/visio/masters/masters.xml", "/visio/masters/sub/master2.xml"
    assert target_part_name(source, relationship_target(source, part_name)) == part_name
