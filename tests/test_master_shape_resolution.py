"""`Shape.master_shape` on a master with no shapes, or with several top-level ones (#433)."""

import copy

from vsdxkit import namespace
from vsdxkit.document import Document


def _setup(vsdx_copy):
    vis = Document.open(vsdx_copy("test5_master.vsdx"))
    instance = vis.pages[0].shapes.require_id("1")
    shapes = vis.master_pages[0].xml.getroot().find(f"{namespace}Shapes")
    return instance, shapes


def test_an_empty_master_has_no_master_shape(vsdx_copy):
    instance, shapes = _setup(vsdx_copy)
    for shape in list(shapes):
        shapes.remove(shape)

    assert instance.master_shape is None


def test_a_master_shape_under_a_later_top_level_shape_is_found(vsdx_copy):
    instance, shapes = _setup(vsdx_copy)
    second = copy.deepcopy(shapes[0])
    second.attrib["ID"] = "999"
    inner = second.find(f"{namespace}Shapes")[0]
    inner.attrib["ID"] = "996"
    shapes.append(second)
    instance.xml.attrib["MasterShape"] = "996"

    found = instance.master_shape

    assert found is not None
    assert found.ID == "996"
