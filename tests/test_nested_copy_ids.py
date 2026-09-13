"""Copying a group must renumber every shape below it, however deep it goes.

`increment_shape_ids` used to stop one level short: it stamped the group and
the group's direct children, then walked no further, so the grandchildren of a
three-level group arrived in the copy still carrying their original ids. One
`Shape.copy()` on `test10_nested_shapes.vsdx` left four duplicates, and a
duplicate id makes a `Connect` record ambiguous: a record naming shape `5` no
longer picks out one shape, and Visio offers to repair the package.

The same walk also stamped an `ID` onto the `<Shapes>` containers it recursed
through. A `<Shapes>` container is not a shape and takes no `ID` in the schema,
and the number it consumed was invisible to the high-water-mark scan, which
looks only at shapes, so a later allocation could hand that number to a real
shape.

Every assertion here reads the saved package rather than in-memory state. Both
faults land in the XML Visio reads, which is where they do their damage.
"""

import os
import xml.etree.ElementTree as ET
import zipfile

from vsdx import VisioFile, namespace

# a three-level group: 7 contains 3 and 4, which each contain a pair of leaves
NESTED = "test10_nested_shapes.vsdx"
GROUP_ID = "7"


def _page_root(vsdx_path: str) -> ET.Element:
    """Parse page1.xml straight out of the saved package."""
    with zipfile.ZipFile(vsdx_path) as package:
        return ET.fromstring(package.read("visio/pages/page1.xml"))


def _shape_ids(root: ET.Element) -> list[str]:
    return [shape.attrib["ID"] for shape in root.iter(f"{namespace}Shape") if "ID" in shape.attrib]


def _child_shapes(element: ET.Element) -> list[ET.Element]:
    """The Shape elements one level down, through any Shapes container."""
    children = []
    for child in element:
        if child.tag == f"{namespace}Shape":
            children.append(child)
        elif child.tag == f"{namespace}Shapes":
            children.extend(_child_shapes(child))
    return children


def _structure(shape: ET.Element) -> tuple:
    """The subtree below a shape, with the ids left out."""
    return tuple(_structure(child) for child in _child_shapes(shape))


def _copy_nested_group(vsdx_copy, tmp_path, out_name: str) -> str:
    """Copy the three-level group onto its own page and save."""
    out_file = os.path.join(str(tmp_path), out_name)
    with VisioFile(vsdx_copy(NESTED)) as vis:
        page = vis.pages[0]
        group = page.find_shape_by_id(GROUP_ID)
        assert group is not None, f"fixture has no shape {GROUP_ID}"
        group.copy()
        vis.save_vsdx(out_file)
    return out_file


def test_copying_a_nested_group_leaves_every_shape_id_unique(vsdx_copy, tmp_path):
    """The grandchildren kept their original ids, so the copy collided with the source."""
    out_file = _copy_nested_group(vsdx_copy, tmp_path, "unique_ids.vsdx")

    ids = _shape_ids(_page_root(out_file))
    duplicates = sorted({id for id in ids if ids.count(id) > 1})
    assert duplicates == [], f"duplicate shape ids in the saved page: {duplicates}"


def test_no_shapes_container_carries_an_id(vsdx_copy, tmp_path):
    """A `<Shapes>` container is not a shape and takes no ID in the schema."""
    out_file = _copy_nested_group(vsdx_copy, tmp_path, "no_container_id.vsdx")

    root = _page_root(out_file)
    stamped = [container.attrib["ID"] for container in root.iter(f"{namespace}Shapes") if "ID" in container.attrib]
    assert stamped == [], f"<Shapes> elements carrying an ID attribute: {stamped}"


def test_copied_subtree_matches_the_original_and_shares_no_ids_with_it(vsdx_copy, tmp_path):
    """The copy nests exactly as the original does, on ids all of its own."""
    out_file = _copy_nested_group(vsdx_copy, tmp_path, "structure.vsdx")

    root = _page_root(out_file)
    groups = [shape for shape in _child_shapes(root) if _child_shapes(shape)]
    assert len(groups) == 2, "expected the original group and its copy at the top level"
    original, copy = groups

    # 7 -> (3, 4), and 3 and 4 each hold a pair of leaves
    assert _structure(original) == (((), ()), ((), ()))
    assert _structure(copy) == _structure(original), "the copy did not keep its nesting"

    original_ids = set(_shape_ids(original))
    copy_ids = set(_shape_ids(copy))
    shared = sorted(original_ids & copy_ids)
    assert shared == [], f"the copy reused ids from the original: {shared}"


def test_formulas_referencing_a_grandchild_follow_it_to_its_new_id(vsdx_copy, tmp_path):
    """`update_ids` can only remap an id that the walk reallocated."""
    out_file = os.path.join(str(tmp_path), "grandchild_formula.vsdx")
    with VisioFile(vsdx_copy(NESTED)) as vis:
        page = vis.pages[0]
        group = page.find_shape_by_id(GROUP_ID)
        assert group is not None
        # a grandchild of the group refers to its sibling, two levels down
        grandchild = page.find_shape_by_id("5")
        assert grandchild is not None
        grandchild.get_or_create_cell("Width", f="Sheet.6!Width")

        original_ids = set(_shape_ids(page.xml.getroot()))
        group.copy()
        vis.save_vsdx(out_file)

    root = _page_root(out_file)
    # the fixture's own Width formulas all carry a `*factor`, so this picks out
    # the reference injected above and the copy's version of it
    references = [cell.attrib["F"] for cell in root.iter(f"{namespace}Cell") if cell.attrib.get("F", "").endswith("!Width")]
    assert len(references) == 2, f"expected the original reference and the copy's: {references}"
    assert references.count("Sheet.6!Width") == 1, f"the copy kept the original's id: {references}"

    copied = next(f for f in references if f != "Sheet.6!Width")
    referenced_id = copied.removeprefix("Sheet.").split("!")[0]
    assert referenced_id not in original_ids, f"the copy still points at an original shape: {copied}"
