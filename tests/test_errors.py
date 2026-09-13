"""The public exception hierarchy, and the raise sites that are supposed to use it.

Two things are under test here. The first is the shape of the hierarchy: what
inherits from what, and which builtin bases survive so that code written
against the pre-hierarchy library keeps catching what it caught. The second,
and the one that matters more, is that the library actually raises these types.
A hierarchy nobody raises documents a contract the code does not keep.
"""

import xml.etree.ElementTree as ET
import zipfile

import pytest

import vsdxkit
from vsdxkit.errors import (
    InvalidOperationError,
    MalformedPackageError,
    MissingPartError,
    NotFoundError,
    PackageError,
    PackageLimitError,
    VisioFileNotOpen,
    VsdxError,
)

PUBLIC_ERRORS = (
    InvalidOperationError,
    MalformedPackageError,
    MissingPartError,
    NotFoundError,
    PackageError,
    PackageLimitError,
    VisioFileNotOpen,
)


def _package_with_document(source: str, destination: str, document: bytes) -> str:
    """A copy of `source` whose `visio/document.xml` holds `document` instead."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as rewritten:
        for member in original.infolist():
            data = original.read(member.filename)
            if member.filename == "visio/document.xml":
                data = document
            rewritten.writestr(member, data)
    return destination


@pytest.fixture
def broken_document_package(vsdx_copy, tmp_path) -> str:
    """A real package whose `visio/document.xml` is truncated mid-tag."""
    return _package_with_document(vsdx_copy("test1.vsdx"), str(tmp_path / "broken.vsdx"), b"<VisioDocument")


@pytest.fixture
def bad_encoding_package(vsdx_copy, tmp_path) -> str:
    """A real package whose `visio/document.xml` names an encoding nothing can decode."""
    return _package_with_document(
        vsdx_copy("test1.vsdx"),
        str(tmp_path / "bad-encoding.vsdx"),
        b'<?xml version="1.0" encoding="NOT-A-CODEC"?><VisioDocument/>',
    )


# --------------------------------------------------------------------------
# the shape of the hierarchy
# --------------------------------------------------------------------------


def test_the_lists_above_name_every_class_in_the_module():
    """A hand-written list is a list someone forgets to add to.

    The parametrised tests below only check the classes named in
    ``PUBLIC_ERRORS``, so a class added to ``vsdxkit.errors`` and left out of it
    would go untested and unexported while every test here stayed green.
    """
    defined = {
        name
        for name, value in vars(vsdxkit.errors).items()
        if isinstance(value, type) and issubclass(value, BaseException) and value.__module__ == "vsdxkit.errors"
    }
    assert defined == {error_type.__name__ for error_type in PUBLIC_ERRORS} | {"VsdxError"}


@pytest.mark.parametrize("error_type", PUBLIC_ERRORS, ids=lambda t: t.__name__)
def test_every_public_error_is_a_vsdx_error(error_type):
    """`except VsdxError` has to be the one catch-all, or it is not worth having."""
    assert issubclass(error_type, VsdxError)


@pytest.mark.parametrize(
    ("error_type", "builtin_base"),
    [
        (InvalidOperationError, ValueError),
        (NotFoundError, ValueError),
        (MissingPartError, ValueError),
        (MalformedPackageError, ValueError),
        (PackageLimitError, OSError),
    ],
    ids=lambda value: getattr(value, "__name__", value),
)
def test_builtin_bases_are_kept_for_existing_callers(error_type, builtin_base):
    """Each of these sites raised the builtin before; existing `except` clauses keep working."""
    assert issubclass(error_type, builtin_base)


def test_missing_part_is_a_kind_of_not_found():
    assert issubclass(MissingPartError, NotFoundError)


def test_package_limit_error_sits_under_package_error():
    assert issubclass(PackageLimitError, PackageError)


def test_package_error_is_not_a_value_error():
    """`PackageError` is about the file, not about an argument the caller passed."""
    assert not issubclass(PackageError, ValueError)


def test_visio_file_not_open_is_an_invalid_operation():
    assert issubclass(VisioFileNotOpen, InvalidOperationError)


def test_package_limit_error_keeps_its_reason_slug():
    error = PackageLimitError("member_size", "too big")
    assert error.reason == "member_size"
    assert str(error) == "too big"


@pytest.mark.parametrize("name", [t.__name__ for t in PUBLIC_ERRORS] + ["VsdxError"])
def test_errors_are_exported_from_the_package_root(name):
    assert name in vsdxkit.__all__
    assert getattr(vsdxkit, name) is getattr(vsdxkit.errors, name)


def test_package_limit_error_is_the_same_class_wherever_it_is_imported_from():
    """It moved to errors.py; `vsdxkit.package.PackageLimitError` must not become a second class."""
    assert vsdxkit.package.PackageLimitError is PackageLimitError
    assert vsdxkit.PackageLimitError is PackageLimitError


def test_visio_file_not_open_is_the_same_class_wherever_it_is_imported_from():
    assert vsdxkit.vsdxfile.VisioFileNotOpen is VisioFileNotOpen
    assert vsdxkit.VisioFileNotOpen is VisioFileNotOpen


# --------------------------------------------------------------------------
# required parts and elements
# --------------------------------------------------------------------------


def test_require_element_raises_missing_part_error():
    with pytest.raises(MissingPartError, match="Pages root"):
        vsdxkit.xmlio.require_element(None, "Pages root")


def test_require_tree_raises_missing_part_error():
    with pytest.raises(MissingPartError, match=r"pages\.xml"):
        vsdxkit.xmlio.require_tree(None, "pages.xml")


def test_require_xml_tree_raises_missing_part_error():
    with pytest.raises(MissingPartError, match=r"absent\.xml"):
        vsdxkit.xmlio.require_xml_tree("absent.xml", {}, "a part that is not there")


def test_store_require_xml_raises_missing_part_error(tmp_path):
    store = vsdxkit.package.PackageStore(tmp_path / "nothing.vsdx")
    with pytest.raises(MissingPartError, match=r"/visio/document\.xml"):
        store.require_xml("/visio/document.xml")


def test_a_document_with_no_pages_part_raises_missing_part_error(vsdx_copy):
    """A document missing pages.xml is incomplete, not a caller passing a bad argument."""
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        vis.pages_xml = None
        with pytest.raises(MissingPartError, match=r"pages\.xml"):
            page.name = "renamed"


# --------------------------------------------------------------------------
# malformed package content
# --------------------------------------------------------------------------


def test_promoting_a_part_that_is_not_xml_raises_malformed_package_error(tmp_path):
    store = vsdxkit.package.PackageStore(tmp_path / "nothing.vsdx")
    store.write_bytes("/visio/document.xml", b"<not-xml")
    with pytest.raises(MalformedPackageError, match="not well-formed XML"):
        store.read_xml("/visio/document.xml")


def test_opening_a_package_whose_xml_is_broken_raises_malformed_package_error(broken_document_package):
    """The public open path parses through `parse_part`, which must translate too.

    `PackageStore._promoted` was not the only way into the parser: `VisioFile`
    opens a document through `file_to_xml` -> `parse_part`, where a malformed
    part used to surface as a raw `ET.ParseError` and miss the hierarchy
    entirely (#365 review).
    """
    with pytest.raises(MalformedPackageError, match="not well-formed XML"):
        vsdxkit.VisioFile(broken_document_package)


def test_the_parse_error_is_kept_as_the_cause(broken_document_package):
    """Chained, not swallowed: `ET.ParseError.position` is how a caller finds the byte."""
    with pytest.raises(MalformedPackageError) as caught:
        vsdxkit.VisioFile(broken_document_package)
    assert isinstance(caught.value.__cause__, ET.ParseError)


@pytest.mark.allow_invalid_package("unresolved-page")
@pytest.mark.parametrize(
    ("member", "old", "expected"),
    [
        ("visio/pages/_rels/pages.xml.rels", b'Id="rId1"', "Id"),
        ("visio/pages/_rels/pages.xml.rels", b'Target="page1.xml"', "Target"),
    ],
    ids=["relationship-without-Id", "relationship-without-Target"],
)
def test_a_required_attribute_missing_on_open_raises_malformed_package_error(vsdx_copy, tmp_path, member, old, expected):
    """Well-formed XML that breaks the schema used to surface as a bare `KeyError`.

    `load_pages` indexed `rel.attrib` directly, so a package a caller could not
    have validated first reported a malformed relationship as `KeyError: 'Id'`
    and `except VsdxError` missed it (#365 review).
    """
    source = vsdx_copy("test1.vsdx")
    destination = str(tmp_path / "no-attribute.vsdx")
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as rewritten:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == member:
                assert old in data, f"the fixture has changed: {old!r} is not in {member}"
                data = data.replace(old, b"", 1)
            rewritten.writestr(entry, data)

    with pytest.raises(MalformedPackageError, match=expected):
        vsdxkit.VisioFile(destination)


def test_require_attribute_returns_the_value_when_it_is_there():
    element = ET.fromstring('<Relationship Id="rId1"/>')
    assert vsdxkit.xmlio.require_attribute(element, "Id", "Relationship") == "rId1"


def test_a_part_declaring_an_unknown_encoding_raises_malformed_package_error(bad_encoding_package):
    """`ET.iterparse` reports an unusable encoding as `LookupError`, not `ParseError`.

    Catching only `ET.ParseError` let a bare builtin out of the one function
    both load paths go through (#365 review).
    """
    with pytest.raises(MalformedPackageError, match="encoding"):
        vsdxkit.VisioFile(bad_encoding_package)


def test_malformed_shapesheet_number_raises_malformed_package_error(vsdx_copy):
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        shape = vis.pages[0].all_shapes[0]
        shape.set_cell_value("PinX", "not-a-number")
        with pytest.raises(MalformedPackageError, match="malformed numeric ShapeSheet value"):
            _ = shape.x


# --------------------------------------------------------------------------
# things that are not there
# --------------------------------------------------------------------------


def test_unknown_palette_name_raises_not_found_error(vsdx_copy):
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        with pytest.raises(NotFoundError, match="palette has no shape named"):
            vis.create_shape(vis.pages[0], "PALETTE_NOT_A_SHAPE", 1.0, 1.0)


def test_deleting_a_shape_that_is_not_on_the_page_raises_not_found_error(vsdx_copy):
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        with vsdxkit.VisioFile(vsdx_copy("test2.vsdx")) as other:
            stranger = other.pages[0].all_shapes[0]
            with pytest.raises(NotFoundError, match="is not on page"):
                vis.pages[0].delete_shape(stranger)


# --------------------------------------------------------------------------
# operations refused because of the document's state
# --------------------------------------------------------------------------


def test_saving_a_drawing_under_a_vsdm_name_raises_invalid_operation(vsdx_copy, tmp_path):
    """#90 needs exactly this type for a package kind / suffix mismatch."""
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        with pytest.raises(InvalidOperationError, match="macro-enabled"):
            vis.save_vsdx(str(tmp_path / "out.vsdm"))


def test_gluing_to_a_connection_point_a_shape_does_not_have_raises_invalid_operation(vsdx_copy):
    with vsdxkit.VisioFile(vsdx_copy("test4_connectors.vsdx")) as vis:
        page = vis.pages[0]
        a, b = page.child_shapes[0], page.child_shapes[1]
        with pytest.raises(InvalidOperationError, match="connection point"):
            page.connect_shapes(a, b, route="point", from_cp=99)


def test_a_page_with_no_container_raises_invalid_operation(vsdx_copy):
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        with pytest.raises(InvalidOperationError, match="no CFF Container"):
            vis.pages[0].add_swimlane("Lane")


def test_appending_a_shape_to_a_non_group_raises_invalid_operation(vsdx_copy):
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
        host, guest = page.child_shapes[0], page.child_shapes[1]
        with pytest.raises(InvalidOperationError, match="cannot contain shapes"):
            host.append_shape(guest)


def test_a_duplicate_geometry_row_index_raises_invalid_operation(vsdx_copy):
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        shape = vis.pages[0].all_shapes[0]
        geometry = shape.geometry
        assert geometry is not None
        existing = geometry.rows[sorted(geometry.rows)[0]]
        with pytest.raises(InvalidOperationError, match="already exists"):
            existing.create_row_xml(existing.row_type, str(existing.index))


def test_saving_an_empty_package_raises_invalid_operation(vsdx_copy, tmp_path):
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        vis.zip_file_contents.clear()
        with pytest.raises(InvalidOperationError, match="empty package"):
            vis.save_vsdx(str(tmp_path / "out.vsdx"))


def test_mutating_a_closed_document_still_raises_visio_file_not_open(vsdx_copy):
    """Reparenting `VisioFileNotOpen` must not change which operations raise it."""
    with vsdxkit.VisioFile(vsdx_copy("test1.vsdx")) as vis:
        page = vis.pages[0]
    with pytest.raises(VisioFileNotOpen):
        page.name = "renamed"


# --------------------------------------------------------------------------
# argument checks stay builtin
# --------------------------------------------------------------------------


def test_argument_checks_are_still_plain_builtin_errors():
    """Type and value checks on what a caller passed are not library conditions."""
    with pytest.raises(TypeError) as type_error:
        vsdxkit.xmlio.xml_value(None)
    assert not isinstance(type_error.value, VsdxError)

    with pytest.raises(ValueError) as value_error:
        vsdxkit.package.PackageLimits(max_members=0)
    assert not isinstance(value_error.value, VsdxError)


def test_an_unusable_part_name_is_still_a_plain_value_error(tmp_path):
    """`_checked` feeds a caught ValueError into PackageLimitError; it must stay one."""
    store = vsdxkit.package.PackageStore(tmp_path / "nothing.vsdx")
    with pytest.raises(ValueError) as caught:
        store.read_bytes("visio/document.xml")
    assert not isinstance(caught.value, VsdxError)
