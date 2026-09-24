"""`vsdxkit.shape_tree` is the one walk of a shape tree (Phase 3, #98).

Each test names the defect it pins. The walk is checked three ways: on small
hand-built trees, as a property over seeded random trees and every fixture's
pages and masters, and against what Visio itself reported about which shapes
are 1-D.
"""

import glob
import json
import os
import random
import xml.etree.ElementTree as ET
import zipfile

import pytest

from vsdxkit import namespace
from vsdxkit.shape_tree import is_connector_element, iter_children, iter_descendants, iter_edges
from vsdxkit.vsdxfile import VisioFile

BASEDIR = os.path.dirname(os.path.realpath(__file__))
SHAPE = f"{namespace}Shape"
SHAPES = f"{namespace}Shapes"
CELL = f"{namespace}Cell"


def _shape(shape_id: str, *children: ET.Element, begin_x: bool = False) -> ET.Element:
    element = ET.Element(SHAPE, ID=shape_id, Type="Group" if children else "Shape")
    if begin_x:
        ET.SubElement(element, CELL, N="BeginX", V="1")
    if children:
        ET.SubElement(element, SHAPES).extend(children)
    return element


def _page(*shapes: ET.Element) -> ET.Element:
    root = ET.Element(f"{namespace}PageContents")
    ET.SubElement(root, SHAPES).extend(shapes)
    return root


def _ids(elements) -> list[str]:
    return [element.attrib["ID"] for element in elements]


def test_a_page_s_children_are_its_top_level_shapes_only():
    """Fails if a page's children include the members of its groups."""
    page = _page(_shape("1", _shape("2")), _shape("3"))
    assert _ids(iter_children(page)) == ["1", "3"]


def test_a_group_s_children_are_its_members():
    """Fails if a group's own Shapes element is not where its children are looked for."""
    group = _shape("1", _shape("2"), _shape("3", _shape("4")))
    assert _ids(iter_children(group)) == ["2", "3"]


def test_a_shape_that_is_not_a_group_has_no_children():
    """Fails if a plain shape reports children, or the walk raises on one."""
    assert list(iter_children(_shape("1"))) == []
    assert list(iter_children(_page())) == []
    assert list(iter_children(ET.Element(f"{namespace}PageContents"))) == []


def test_a_shapes_element_s_children_are_the_shapes_it_holds():
    """Fails if the Shapes element the synthetic page wrapper holds (until #103) has no children."""
    page = _page(_shape("1"), _shape("2"))
    shapes = page.find(SHAPES)
    assert shapes is not None
    assert _ids(iter_children(shapes)) == ["1", "2"]


def test_descendants_are_in_document_order_parents_first():
    """Fails if the order of `all_shapes` changes: templating and finders rely on it."""
    page = _page(_shape("1", _shape("2", _shape("3")), _shape("4")), _shape("5"))
    assert _ids(iter_descendants(page)) == ["1", "2", "3", "4", "5"]


def test_each_edge_names_the_element_its_child_sits_under():
    """Fails if a sub-shape is reported under the wrong parent: it inherits that parent's master."""
    inner = _shape("2")
    group = _shape("1", inner)
    page = _page(group)
    assert list(iter_edges(page)) == [(page, group), (group, inner)]


def test_a_shape_with_its_own_begin_x_is_a_connector():
    """Fails if a 1-D shape is not recognised from its 1-D Endpoints cells."""
    assert is_connector_element(_shape("1", begin_x=True))
    assert not is_connector_element(_shape("1"))


def test_a_shape_that_inherits_begin_x_from_its_master_is_a_connector():
    """Fails if a connector whose endpoints live only on its master is missed, and survives its glue's deletion."""
    master = _shape("5", begin_x=True)
    assert is_connector_element(_shape("1"), master)
    assert not is_connector_element(_shape("1"), _shape("5"))


def _random_tree(rng: random.Random, next_id: list[int], depth: int) -> ET.Element:
    next_id[0] += 1
    shape_id = str(next_id[0])
    width = rng.randint(0, 4) if depth < 4 else 0
    return _shape(shape_id, *(_random_tree(rng, next_id, depth + 1) for _ in range(width)))


def _assert_walk_is_consistent(root: ET.Element) -> None:
    expected: list[ET.Element] = []
    for child in iter_children(root):
        expected.append(child)
        expected.extend(iter_descendants(child))
    assert list(iter_descendants(root)) == expected
    for parent, child in iter_edges(root):
        assert child in list(iter_children(parent))


@pytest.mark.parametrize("seed", range(50))
def test_descendants_are_children_each_followed_by_its_descendants(seed):
    """Fails if the recursion skips, repeats or reorders a shape at any depth."""
    rng = random.Random(seed)
    next_id = [0]
    page = _page(*(_random_tree(rng, next_id, 0) for _ in range(rng.randint(0, 5))))
    _assert_walk_is_consistent(page)
    assert _ids(iter_descendants(page)) == [str(n) for n in range(1, next_id[0] + 1)]


def _contents_parts():
    for path in sorted(glob.glob(os.path.join(BASEDIR, "**", "*.vs[dm]x"), recursive=True)):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith(".xml") and name.startswith(("visio/pages/page", "visio/masters/master")):
                    yield os.path.relpath(path, BASEDIR), name, archive.read(name)


@pytest.mark.parametrize(("fixture", "part", "data"), list(_contents_parts()), ids=lambda value: str(value)[:40])
def test_every_fixture_part_walks_consistently(fixture, part, data):
    """Fails if any real page or master is walked differently from its Shape elements' nesting."""
    root = ET.fromstring(data)
    _assert_walk_is_consistent(root)
    assert list(iter_descendants(root)) == list(root.iter(SHAPE))


def _com_scenarios():
    with open(os.path.join(BASEDIR, "fixtures", "com_reference", "manifest.json"), encoding="utf-8-sig") as manifest:
        return json.load(manifest)["scenarios"]


@pytest.mark.parametrize("scenario", _com_scenarios(), ids=lambda scenario: scenario["scenario"])
def test_connector_classification_agrees_with_visio(scenario):
    """Fails if any shape Visio reported as 1-D (or not) is classified the other way."""
    path = os.path.join(BASEDIR, "fixtures", "com_reference", scenario["file"])
    vis = VisioFile(path)
    shapes = {shape.ID: shape for page in vis.pages for shape in page.all_shapes}
    for expected in scenario["shapes"]:
        shape = shapes[str(expected["id"])]
        master = shape.master_shape
        one_d = is_connector_element(shape.xml, None if master is None else master.xml)
        assert one_d == (expected["one_d"] == -1), (expected["name"], expected["id"])
