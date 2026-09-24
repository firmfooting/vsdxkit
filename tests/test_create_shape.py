"""Page.create_shape: a built-in kind or a prototype shape from the same document (#111)."""

import zipfile

import pytest

from vsdxkit import media
from vsdxkit.document import Document
from vsdxkit.errors import InvalidOperationError
from vsdxkit.shape_kind import ShapeKind

BASE = "test8_simple_connector.vsdx"


def _geometry(shape):
    """The shape's own Geometry rows: what makes a circle a circle."""
    return [
        (row.attrib.get("T"), sorted((cell.attrib["N"], cell.attrib.get("V")) for cell in row))
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
