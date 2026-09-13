import os
import pprint

import pytest

from vsdxkit import Connect, VisioFile
from vsdxkit.vsdxdiff import VisioFileDiff


@pytest.mark.parametrize(("filename_a", "filename_b"), [("test1.vsdx", "test2.vsdx"), ("test1.vsdx", "test4_connectors.vsdx")])
def test_create_visiodiff(filename_a: str, filename_b: str, basedir):
    filepath_a = os.path.join(basedir, filename_a)
    filepath_b = os.path.join(basedir, filename_b)
    print(basedir)
    print(filepath_a)
    fd = VisioFileDiff(filepath_a, filepath_b)
    print(f"fd={fd}")
    print(f"Added in {filename_b} {fd.added_members()}")
    print(f"Removed in {filename_b} {fd.removed_members()}")
    for m in fd.common_members():
        print(f"\n\n{m}")
        pprint.pprint(fd.diffs.get(m))


# next test, open file, set text of shape, save as - then compare the two
@pytest.mark.parametrize(
    ("filename_a", "filename_b"),
    [
        ("test1.vsdx", "test1_outfile.vsdx"),
        ("test2.vsdx", "test2_outfile.vsdx"),
    ],
)
def test_visiodiff_before_after(filename_a: str, filename_b: str, vsdx_copy, tmp_path):
    filepath_a = vsdx_copy(filename_a)
    filepath_b = os.path.join(str(tmp_path), filename_b)
    with VisioFile(filepath_a) as vis:
        vis.save_vsdx(filepath_b)

    file_diff = VisioFileDiff(filepath_a, filepath_b)

    # a round trip must not add or remove package members
    assert file_diff.added_members() == set()
    assert file_diff.removed_members() == set()
    assert file_diff.common_members()


def test_visiodiff_detects_added_connector(vsdx_copy, tmp_path):
    """Adding a connector between two shapes must show up in the diff."""
    filepath_a = vsdx_copy("test1.vsdx")
    filepath_b = os.path.join(str(tmp_path), "with_connector.vsdx")
    with VisioFile(filepath_a) as vis:
        page = vis.pages[0]
        shapes = page.all_shapes
        assert len(shapes) >= 2
        Connect.create(page=page, from_shape=shapes[0], to_shape=shapes[1])
        vis.save_vsdx(filepath_b)

    file_diff = VisioFileDiff(filepath_a, filepath_b)
    # connector creation legitimately imports media masters and the page rels
    # part, so members are added but none are removed
    assert file_diff.removed_members() == set()
    added = file_diff.added_members()
    # non-empty first: `all()` over an empty set is True, so the shape check
    # below asserted nothing while `added_members` returned nothing
    assert added, "adding a connector added no package member"
    assert all("master" in member or "page" in member for member in added), added

    # the same two files the other way round, so `removed_members` is pinned on
    # a non-empty answer as well
    reversed_diff = VisioFileDiff(filepath_b, filepath_a)
    assert reversed_diff.removed_members() == added
    assert reversed_diff.added_members() == set()

    # the shared members exclude the ones only b has, which is what separates
    # the intersection from the union
    common = file_diff.common_members()
    assert set(common).isdisjoint(added), f"a member only file b has is not shared: {sorted(set(common) & added)}"
    assert "visio/pages/page1.xml" in common, common

    # the page part must have gained actual Connect records: inspect only the
    # added diff lines (unchanged lines carry 'ConnectorSchemeIndex' noise),
    # so an empty diff or a no-op Connect.create() cannot satisfy this
    assert file_diff.diffs, "no textual diffs at all"
    page_part_key = next((key for key in file_diff.diffs if key.endswith("page1.xml")), None)
    assert page_part_key is not None, f"page part absent from diffs: {list(file_diff.diffs)}"
    added_lines = [line[2:] for line in file_diff.diffs[page_part_key] if line.startswith("+ ")]
    # Connect records are the only added lines carrying FromSheet (namespace
    # prefixes vary, so match on the attribute, not the tag)
    connect_records = [line for line in added_lines if "FromSheet" in line]
    assert connect_records, f"no Connect records among added lines: {added_lines[:10]}"
