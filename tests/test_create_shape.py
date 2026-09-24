"""Page.create_shape: a built-in kind or a prototype shape from the same document (#111)."""

import os
import zipfile

import pytest

from vsdxkit import media
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.partnames import target_part_name
from vsdxkit.shape_kind import ShapeKind

BASE = "test8_simple_connector.vsdx"
R_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _rounded(value):
    """A cell value as a number to nine places where it is one: a placed line's values are recomputed."""
    try:
        return round(float(value), 9)
    except (TypeError, ValueError):
        return value


def _geometry(shape):
    """The shape's own Geometry rows: what makes a circle a circle."""
    return [
        (row.attrib.get("T"), sorted((cell.attrib["N"], _rounded(cell.attrib.get("V"))) for cell in row))
        for section in shape.xml.findall("{http://schemas.microsoft.com/office/visio/2012/main}Section")
        if section.attrib.get("N") == "Geometry"
        for row in section
    ]


@pytest.mark.parametrize("kind", list(ShapeKind))
def test_each_kind_is_a_copy_of_its_bundled_shape(vsdx_copy, kind):
    page = Document.open(vsdx_copy(BASE)).pages[0]
    donor = media._kind_shape(kind)

    shape = page.create_shape(kind, x=4.0, y=6.0)

    assert shape.text == ""
    assert (shape.x, shape.y) == pytest.approx((4.0, 6.0))
    assert shape.xml is not donor.xml
    assert _geometry(shape) == _geometry(donor)
    assert shape in page.children


def test_size_and_text_are_set(vsdx_copy):
    path = vsdx_copy(BASE)
    vis = Document.open(path)
    shape = vis.pages[0].create_shape(ShapeKind.DECISION, x=4.0, y=6.0, width=1.5, height=1.0, text="Choose")
    assert (shape.width, shape.height) == pytest.approx((1.5, 1.0))
    assert shape.text.strip() == "Choose"
    vis.save()
    assert Document.open(path).pages[0].shapes.by_text("Choose") is not None


def _endpoints(shape):
    return (shape.begin_x, shape.begin_y, shape.end_x, shape.end_y)


def test_a_line_is_placed_by_its_endpoints(vsdx_copy):
    """Fails if a 1-D shape is placed through PinX and Width, whose formulas Visio recalculates from its ends."""
    page = Document.open(vsdx_copy(BASE)).pages[0]

    line = page.create_shape(ShapeKind.LINE, x=4.0, y=6.0, width=2.0)

    assert _endpoints(line) == pytest.approx((3.0, 6.0, 5.0, 6.0))
    assert line.cells["PinX"].formula == "(BeginX+EndX)/2"
    assert (line.x, line.y, line.width) == pytest.approx((4.0, 6.0, 2.0))
    assert float(line.cells["LocPinX"].value) == pytest.approx(1.0)
    assert float(line.geometry.rows["2"].cells["X"].value) == pytest.approx(2.0)


def test_a_line_keeps_its_length_without_a_width(vsdx_copy):
    page = Document.open(vsdx_copy(BASE)).pages[0]
    length = media._kind_shape(ShapeKind.LINE).width

    line = page.create_shape(ShapeKind.LINE, x=4.0, y=6.0)

    begin_x, begin_y, end_x, end_y = _endpoints(line)
    assert (end_x - begin_x, (begin_x + end_x) / 2, begin_y, end_y) == pytest.approx((length, 4.0, 6.0, 6.0))


def test_a_one_d_prototype_keeps_its_direction(vsdx_copy):
    page = Document.open(vsdx_copy(BASE)).pages[0]
    slanted = page.create_shape(ShapeKind.LINE, x=4.0, y=6.0)
    slanted.begin_x, slanted.begin_y, slanted.end_x, slanted.end_y = 1.0, 1.0, 4.0, 5.0

    copy = page.create_shape(slanted, x=10.0, y=10.0, width=10.0)

    assert _endpoints(copy) == pytest.approx((7.0, 6.0, 13.0, 14.0))
    assert _endpoints(slanted) == pytest.approx((1.0, 1.0, 4.0, 5.0))


def test_a_glued_connector_prototype_is_copied_with_both_ends_floating(vsdx_copy):
    """Fails if the copy keeps glue formulas naming the prototype's shapes, which Visio would pull it back to."""
    page = Document.open(vsdx_copy("test4_connectors.vsdx")).pages[0]
    glued = page.shapes.require_id("6")  # glued from shape 1 to shape 2
    records = sorted((c.from_id, c.from_rel, c.to_id) for c in page.connects)
    formulas = {name: glued.cells[name].formula for name in ("BeginX", "EndX", "BegTrigger", "EndTrigger")}

    copy = page.create_shape(glued, x=10.0, y=1.0, width=2.0)

    assert all(copy.cells[name].formula is None for name in ("BeginX", "BeginY", "EndX", "EndY"))
    assert "BegTrigger" not in copy.cells and "EndTrigger" not in copy.cells
    assert (copy.begin_x + copy.end_x) / 2 == pytest.approx(10.0)
    assert (copy.begin_y + copy.end_y) / 2 == pytest.approx(1.0)
    assert copy.ID not in {c.from_id for c in page.connects}
    assert sorted((c.from_id, c.from_rel, c.to_id) for c in page.connects) == records
    assert {name: glued.cells[name].formula for name in formulas} == formulas


def test_a_prototype_whose_pin_is_a_formula_is_placed_where_asked(vsdx_copy):
    """Fails if placement writes only the cached value beside a formula Visio recalculates on open."""
    page = Document.open(vsdx_copy("test_jinja_loop_showif.vsdx")).pages[0]
    member = page.shapes.require_id("7")  # a group member: PinX is Sheet.9!Width*0.5
    assert "Sheet.9!" in member.cells["PinX"].formula

    copy = page.create_shape(member, x=3.0, y=4.0, width=1.25, height=0.75)

    for name, value in (("PinX", 3.0), ("PinY", 4.0), ("Width", 1.25), ("Height", 0.75)):
        assert copy.cells[name].formula is None, name
        assert float(copy.cells[name].value) == pytest.approx(value), name


def test_a_group_member_copied_without_a_size_keeps_no_tie_to_its_group(vsdx_copy):
    """Fails if a prototype's size formulas still name the group it was copied out of."""
    page = Document.open(vsdx_copy("test_jinja_loop_showif.vsdx")).pages[0]
    member = page.shapes.require_id("7")  # Width is Sheet.9!Width*1
    size = (member.width, member.height)

    copy = page.create_shape(member, x=3.0, y=4.0)

    assert [name for name, cell in copy.cells.items() if cell.formula and "!" in cell.formula] == []
    assert (copy.width, copy.height) == pytest.approx(size)


def test_resizing_refreshes_what_the_size_decides(vsdx_copy):
    """Fails if LocPinX (Width*0.5) keeps the old width's value, putting the copy off-centre."""
    page = Document.open(vsdx_copy(BASE)).pages[0]
    prototype = page.shapes.require_text("Shape A")

    copy = page.create_shape(prototype, x=5.0, y=2.0, width=1.0, height=0.5)

    assert float(copy.cells["LocPinX"].value) == pytest.approx(0.5)
    assert float(copy.cells["LocPinY"].value) == pytest.approx(0.25)
    left, bottom, right, top = copy.bounds
    assert ((left + right) / 2, (bottom + top) / 2) == pytest.approx((5.0, 2.0))


def test_a_prototype_on_another_page_brings_its_relationships(vsdx_copy):
    """Fails if an image's r:id is copied onto a page that has no relationship by that id."""
    path = vsdx_copy(os.path.join("fixtures", "com_reference", "s05_swimlanes_cfflow.vsdx"))
    vis = Document.open(path)
    image = vis.pages[0].shapes.require_id("79")
    (source_id,) = _relationship_ids(image)
    source_target = _target(vis.pages[0], source_id)
    page = vis.add_page("Elsewhere")

    copy = page.create_shape(image, x=2.0, y=2.0)

    (copied_id,) = _relationship_ids(copy)
    assert _target(page, copied_id) == source_target
    vis.save()
    reopened = Document.open(path).pages.require_name("Elsewhere")
    (reopened_id,) = _relationship_ids(next(iter(reopened.children)))
    assert _target(reopened, reopened_id) == source_target


def _relationship_ids(shape):
    return [node.attrib[R_ID] for node in shape.xml.iter() if R_ID in node.attrib]


def _target(page, relationship_id):
    (relationship,) = [rel for rel in page.rels_xml.getroot() if rel.attrib["Id"] == relationship_id]
    return target_part_name(page.filename, relationship.attrib["Target"])


def test_a_deleted_prototype_is_refused(vsdx_copy):
    page = Document.open(vsdx_copy(BASE)).pages[0]
    prototype = page.shapes.require_text("Shape A")
    page.delete_shape(prototype)
    before = [shape.ID for shape in page.shapes]

    with pytest.raises(InvalidOperationError):
        page.create_shape(prototype, x=1.0, y=1.0)

    assert [shape.ID for shape in page.shapes] == before


def test_a_masterless_connector_keeps_what_kind_of_connector_it_is(vsdx_copy):
    """Fails if floating the copy's ends drops cells it has no master to inherit from."""
    page = Document.open(vsdx_copy("test5_master.vsdx")).pages[0]
    connector = page.shapes.require_id("5")
    assert connector.master_page_ID is None and "BeginX" in connector.cells
    kinds = {name: connector.cells[name].value for name in ("ObjType", "GlueType") if name in connector.cells}
    assert kinds.get("ObjType") == "2"

    copy = page.create_shape(connector, x=3.0, y=4.0)

    assert {name: copy.cells[name].value for name in kinds} == kinds


def test_a_prototype_is_copied_with_its_text(vsdx_copy):
    page = Document.open(vsdx_copy(BASE)).pages[0]
    prototype = page.shapes.require_text("Shape A")

    shape = page.create_shape(prototype, x=7.0, y=2.0)

    assert shape != prototype
    assert shape.text == prototype.text
    assert (shape.x, shape.y) == pytest.approx((7.0, 2.0))
    assert shape.ID != prototype.ID


def test_a_prototype_from_another_document_is_refused(vsdx_copy):
    page = Document.open(vsdx_copy(BASE)).pages[0]
    other = next(iter(Document.open(vsdx_copy("test1.vsdx")).pages[0].children))
    before = [shape.ID for shape in page.shapes]

    with pytest.raises(InvalidOperationError, match="another document"):
        page.create_shape(other, x=1.0, y=1.0)

    assert [shape.ID for shape in page.shapes] == before


def test_a_palette_name_is_refused_with_the_enum_named(vsdx_copy):
    page = Document.open(vsdx_copy(BASE)).pages[0]
    with pytest.raises(TypeError, match="ShapeKind"):
        page.create_shape("PALETTE_PROCESS", x=1.0, y=1.0)  # type: ignore[arg-type]


def test_the_position_is_keyword_only(vsdx_copy):
    page = Document.open(vsdx_copy(BASE)).pages[0]
    with pytest.raises(TypeError):
        page.create_shape(ShapeKind.PROCESS, 1.0, 1.0)  # type: ignore[misc]


def test_created_shapes_save_as_a_valid_package(vsdx_copy):
    path = vsdx_copy(BASE)
    vis = Document.open(path)
    page = vis.pages[0]
    for kind in ShapeKind:
        page.create_shape(kind, x=3.0, y=3.0, text=kind.name)
    vis.save()
    assert zipfile.ZipFile(path).testzip() is None
    reopened = Document.open(path).pages[0]
    assert {kind.name for kind in ShapeKind} <= {shape.text.strip() for shape in reopened.shapes}


def test_document_create_shape_is_gone(vsdx_copy):
    """Fails if the 0.x palette-name entry point comes back beside `Page.create_shape`."""
    assert not hasattr(Document.open(vsdx_copy(BASE)), "create_shape")
