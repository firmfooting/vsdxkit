"""The public exception hierarchy, and the raise sites that are supposed to use it.

Two things are under test here. The first is the shape of the hierarchy: what
inherits from what, and which builtin bases survive so that code written
against the pre-hierarchy library keeps catching what it caught. The second,
and the one that matters more, is that the library actually raises these types.
A hierarchy nobody raises documents a contract the code does not keep.
"""

import os
import pathlib
import struct
import xml.etree.ElementTree as ET
import zipfile

import pytest

import vsdxkit
import vsdxkit.document
import vsdxkit.errors
import vsdxkit.package
import vsdxkit.xmlio
from vsdxkit import media
from vsdxkit.document import Document
from vsdxkit.errors import (
    InvalidOperationError,
    MalformedPackageError,
    MissingPartError,
    NotFoundError,
    PackageError,
    PackageLimitError,
    PartParseError,
    VsdxError,
)
from vsdxkit.glue import Glue
from vsdxkit.package import PackageLimits

BASEDIR = os.path.dirname(os.path.realpath(__file__))

PUBLIC_ERRORS = (
    InvalidOperationError,
    MalformedPackageError,
    MissingPartError,
    NotFoundError,
    PackageError,
    PackageLimitError,
    PartParseError,
)


def _package_with_document(source: str, destination: str, document: bytes, member: str = "visio/document.xml") -> str:
    """A copy of `source` whose `member` holds `document` instead."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as rewritten:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == member:
                data = document
            rewritten.writestr(entry, data)
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


# UTF-7 is the encoding `ET.iterparse` refuses outright: expat recognises it but
# cannot stream it, and reports `ValueError("multi-byte encodings are not
# supported")` rather than the `LookupError` an unknown codec name gets.
# Reproduced by hand: `'<?xml version="1.0" encoding="UTF-7"?><a/>'.encode("UTF-7")`
# raised exactly that ValueError from `ET.iterparse`.
REFUSED_MULTIBYTE_PART = '<?xml version="1.0" encoding="UTF-7"?><a/>'.encode("UTF-7")


@pytest.fixture
def multibyte_page_package(vsdx_copy, tmp_path) -> str:
    """A real package whose `visio/pages/page1.xml` names a multi-byte encoding the parser refuses."""
    return _package_with_document(
        vsdx_copy("test1.vsdx"),
        str(tmp_path / "multibyte-page.vsdx"),
        REFUSED_MULTIBYTE_PART,
        member="visio/pages/page1.xml",
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
    """Fails if `MissingPartError` stops deriving from `NotFoundError`.

    A required part that is absent is still something that is not there, so
    `except NotFoundError` has to cover it as well as a lookup that missed.
    """
    assert issubclass(MissingPartError, NotFoundError)


def test_package_limit_error_sits_under_package_error():
    """Fails if `PackageLimitError` stops deriving from `PackageError`.

    A load limit refuses the package, not an argument, so it belongs with the
    other failures to read a package, where `except PackageError` finds it.
    """
    assert issubclass(PackageLimitError, PackageError)


def test_package_error_is_not_a_value_error():
    """`PackageError` is about the file, not about an argument the caller passed."""
    assert not issubclass(PackageError, ValueError)


def test_package_limit_error_keeps_its_reason_slug():
    """Fails if moving `PackageLimitError` into errors.py changes its constructor.

    Callers branch on `reason` and read the message from `str()`, so both have
    to come out of the two arguments the class has always taken.
    """
    error = PackageLimitError("member_size", "too big")
    assert error.reason == "member_size"
    assert str(error) == "too big"


def test_part_parse_error_is_every_error_a_malformed_part_has_been():
    """Fails if PartParseError drops any base a caller may already catch a malformed part by."""
    import xml.etree.ElementTree as ET

    from vsdxkit import errors

    for base in (errors.MalformedPackageError, errors.PackageError, errors.VsdxError, ET.ParseError, ValueError):
        assert issubclass(errors.PartParseError, base)


# --------------------------------------------------------------------------
# required parts and elements
# --------------------------------------------------------------------------


def test_require_element_raises_missing_part_error():
    """Fails if `xmlio.require_element` reports an absent element with anything but `MissingPartError`.

    The load path uses it for elements the schema requires, so an absent one
    means an incomplete package, not a bad argument.
    """
    with pytest.raises(MissingPartError, match="Pages root"):
        vsdxkit.xmlio.require_element(None, "Pages root")


def test_require_tree_raises_missing_part_error():
    """Fails if `xmlio.require_tree` reports an absent tree with anything but `MissingPartError`.

    It guards parts the document cannot be read without, so an absent one is a
    part that is not there.
    """
    with pytest.raises(MissingPartError, match=r"pages\.xml"):
        vsdxkit.xmlio.require_tree(None, "pages.xml")


def test_store_require_xml_raises_missing_part_error(tmp_path):
    """Fails if `PackageStore.require_xml` reports an absent part with anything but `MissingPartError`.

    `require_xml` is the one way a required part is looked up, and it has to
    raise the same error for a part missing from a store that was never
    opened -- one with no parts at all -- as it does for one absent from a
    real archive.
    """
    store = vsdxkit.package.PackageStore(tmp_path / "nothing.vsdx")
    with pytest.raises(MissingPartError, match=r"/visio/document\.xml"):
        store.require_xml("/visio/document.xml")


def test_a_document_with_no_pages_part_raises_missing_part_error(vsdx_copy):
    """A document missing pages.xml is incomplete, not a caller passing a bad argument.

    The part is taken out of the store directly: since #373, `pages_xml = None`
    is refused, because it would leave the relationship and content-type
    override that name the part behind.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    vis._package.remove("/visio/pages/pages.xml")
    with pytest.raises(MissingPartError, match=r"pages\.xml"):
        page.name = "renamed"


def test_a_required_part_the_store_lacks_is_a_missing_part():
    """Fails if PackageStore.require_xml reports an absent part with a plain ValueError."""
    from vsdxkit.package import PackageStore

    store = PackageStore.open(os.path.join(BASEDIR, "test1.vsdx"))
    with pytest.raises(MissingPartError):
        store.require_xml("/visio/no-such-part.xml")


def test_a_source_master_listed_but_unreadable_is_a_missing_part(vsdx_copy, monkeypatch):
    """Fails if master import reports a listed-but-unreadable donor part with a plain ValueError."""
    source = Document.open(vsdx_copy("test4_connectors.vsdx"))
    target = Document.open(vsdx_copy("test1.vsdx"))
    shape = next(shape for shape in source.pages[0].shapes if shape.xml.attrib.get("Master"))
    monkeypatch.setattr(source._package, "read_bytes", lambda name: None)
    with pytest.raises(MissingPartError, match="could not be read"):
        shape.copy(target.pages[0])


# --------------------------------------------------------------------------
# malformed package content
# --------------------------------------------------------------------------


def test_promoting_a_part_that_is_not_xml_raises_malformed_package_error(tmp_path):
    """Fails if `PackageStore.read_xml` lets the parser's error out instead of `MalformedPackageError`.

    Promoting a part parses bytes the package supplied, so bytes that are not
    well-formed XML are a malformed package, however the parser reports them.
    """
    store = vsdxkit.package.PackageStore(tmp_path / "nothing.vsdx")
    store.write_bytes("/visio/document.xml", b"<not-xml")
    with pytest.raises(MalformedPackageError, match="not well-formed XML"):
        store.read_xml("/visio/document.xml")


def test_opening_a_package_whose_xml_is_broken_raises_malformed_package_error(broken_document_package):
    """The public open path parses through `parse_part`, which must translate too.

    `PackageStore._promoted` is the one way into the parser now: `Document`
    opens a document through the store's promotion, which is `parse_part`,
    where a malformed part used to surface as a raw `ET.ParseError` and miss
    the hierarchy entirely (#365 review).
    """
    with pytest.raises(MalformedPackageError, match="not well-formed XML"):
        Document.open(broken_document_package)


def test_the_parse_error_is_kept_as_the_cause(broken_document_package):
    """Chained, not swallowed: `ET.ParseError.position` is how a caller finds the byte."""
    with pytest.raises(MalformedPackageError) as caught:
        Document.open(broken_document_package)
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
        Document.open(destination)


@pytest.mark.allow_invalid_package
def test_a_page_part_the_relationships_name_and_the_package_lacks_raises_missing_part_error(vsdx_copy, tmp_path):
    """Fails if a page part the relationships name, and the package lacks, is not a `MissingPartError` naming it.

    #365 made `require_xml` raise `MissingPartError`. The open path then read
    its required parts through a helper of its own, which kept the old
    `ValueError` until it was fixed to match; now it reads them through
    `PackageStore.require_xml` itself, the one "read an XML part or raise"
    (#116), so the error names the part.
    """
    source = vsdx_copy("test1.vsdx")
    destination = str(tmp_path / "no-page-part.vsdx")
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as rewritten:
        assert "visio/pages/page1.xml" in original.namelist(), "the fixture has changed: no visio/pages/page1.xml"
        for entry in original.infolist():
            if entry.filename != "visio/pages/page1.xml":
                rewritten.writestr(entry, original.read(entry.filename))

    with pytest.raises(MissingPartError, match=r"^expected XML part not found: /visio/pages/page1\.xml$"):
        Document.open(destination)


@pytest.mark.allow_invalid_package
def test_a_master_relationship_without_an_id_raises_malformed_package_error(vsdx_copy, tmp_path):
    """The masters loop skipped such a relationship and `KeyError`d on the lookup after it."""
    source = vsdx_copy("test5_master.vsdx")
    destination = str(tmp_path / "no-master-rel-id.vsdx")
    member = "visio/masters/_rels/masters.xml.rels"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(destination, "w") as rewritten:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if entry.filename == member:
                assert b'Id="rId1"' in data, f'the fixture has changed: no Id="rId1" in {member}'
                data = data.replace(b'Id="rId1"', b"", 1)
            rewritten.writestr(entry, data)

    with pytest.raises(MalformedPackageError, match="Id"):
        Document.open(destination)


@pytest.mark.allow_invalid_package
@pytest.mark.parametrize(
    ("source", "member", "old_target"),
    [
        ("test1.vsdx", "visio/pages/_rels/pages.xml.rels", b'Target="page1.xml"'),
        ("test5_master.vsdx", "visio/masters/_rels/masters.xml.rels", b'Target="master1.xml"'),
    ],
    ids=["pages.xml.rels", "masters.xml.rels"],
)
@pytest.mark.parametrize(
    "new_target",
    [b"../x.xml", b"./page1.xml", b"http://x/y.xml", b"", b"sub/", b"/visio/pages/page1.xml"],
    ids=["parent", "dot", "absolute-uri", "empty", "folder", "absolute-part-name"],
)
def test_a_relationship_target_that_is_not_a_part_name_raises_malformed_package_error(
    vsdx_copy, tmp_path, source, member, old_target, new_target
):
    """Fails if the open path lets `_checked`'s plain `ValueError` escape for a relationship `Target`.

    The `Target` of a page or master relationship is package content: joined
    onto the pages or masters folder, it names the part to load, and a `Target`
    that joins into something that is not an OPC part name was reported by the
    store's argument check, as a plain `ValueError`. That missed
    `except VsdxError`, which is the promise an open makes about a malformed
    package. `load_pages` and `load_master_pages` translate that one check;
    resolving such targets properly is a separate change.
    """
    destination = str(tmp_path / "bad-target.vsdx")
    with zipfile.ZipFile(vsdx_copy(source)) as original:
        data = original.read(member)
    assert old_target in data, f"the fixture has changed: {old_target!r} is not in {member}"
    _package_with_document(
        vsdx_copy(source), destination, data.replace(old_target, b'Target="' + new_target + b'"', 1), member=member
    )

    with pytest.raises(MalformedPackageError, match="not a part name") as caught:
        Document.open(destination)
    assert isinstance(caught.value, ValueError)
    assert isinstance(caught.value.__cause__, ValueError)


@pytest.mark.allow_invalid_package
@pytest.mark.parametrize(
    ("label", "payload"),
    [("not-a-zip", b"this is not a zip file"), ("truncated", None)],
)
def test_a_file_that_is_not_a_readable_archive_raises_malformed_package_error(vsdx_copy, tmp_path, label, payload):
    """`zipfile.BadZipFile` is the most basic malformed package there is.

    It escaped the hierarchy entirely, so `except VsdxError` around an open did
    not cover a file that is not a package at all (#365 review).
    """
    if payload is None:
        payload = pathlib.Path(vsdx_copy("test1.vsdx")).read_bytes()[:2048]
    destination = tmp_path / f"{label}.vsdx"
    destination.write_bytes(payload)

    with pytest.raises(MalformedPackageError, match="not a readable package"):
        Document.open(str(destination))


def test_a_malformed_page_dimension_raises_malformed_package_error(vsdx_copy):
    """Page dimensions parsed with a bare `float()` while shape cells did not.

    A ShapeSheet number that is not a number already reported
    `MalformedPackageError`; `Page.width` and `Page.height` read the same kind
    of cell and raised a plain `ValueError` (#365 review).
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    page._pagesheet_cell("PageWidth").attrib["V"] = "not-a-number"
    with pytest.raises(MalformedPackageError, match="PageWidth"):
        _ = page.width


@pytest.mark.parametrize("coordinate", ["X", "Y"])
def test_a_malformed_geometry_coordinate_raises_malformed_package_error(vsdx_copy, coordinate):
    """Geometry rows read the same ShapeSheet cells, and read them with a bare `float()`."""
    vis = Document.open(vsdx_copy("test9_rect_and_line.vsdx"))
    row = next(
        row
        for shape in vis.pages[0].shapes
        if shape.geometry is not None
        for row in shape.geometry.rows.values()
        if coordinate in row.cells
    )
    row.cells[coordinate].value = "not-a-number"
    with pytest.raises(MalformedPackageError, match=coordinate):
        getattr(row, coordinate.lower())


@pytest.mark.allow_invalid_package
def test_an_encrypted_member_raises_malformed_package_error(vsdx_copy, tmp_path):
    """`ZipFile.open` reports an encrypted member as `RuntimeError`, not `BadZipFile`.

    The encryption bit is set in the raw headers rather than through `writestr`,
    which drops a modified `flag_bits` on the way out.
    """
    raw = bytearray(pathlib.Path(vsdx_copy("test1.vsdx")).read_bytes())
    # bit 0 of the general purpose flag: offset 6 in a local file header,
    # offset 8 in a central directory entry
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        at = raw.find(signature)
        while at != -1:
            position = at + offset
            (flags,) = struct.unpack_from("<H", raw, position)
            struct.pack_into("<H", raw, position, flags | 0x1)
            at = raw.find(signature, at + 4)
    destination = tmp_path / "encrypted.vsdx"
    destination.write_bytes(bytes(raw))

    with pytest.raises(MalformedPackageError, match="cannot be read"):
        Document.open(str(destination))


@pytest.mark.allow_invalid_package
def test_a_member_needing_an_unsupported_zip_version_raises_malformed_package_error(vsdx_copy, tmp_path):
    """Fails if `read_archive_members` stops translating the `ZipFile` constructor's `NotImplementedError`.

    CPython reads the central directory in the constructor, and refuses a
    record whose "version needed to extract" is above 63 with
    `NotImplementedError("zip file version ...")`. That is a claim the package
    makes about itself, so it is a malformed package, and it escaped
    `except VsdxError` until the constructor's handler named it.
    """
    raw = bytearray(pathlib.Path(vsdx_copy("test1.vsdx")).read_bytes())
    # central directory record: signature (4), version made by (2), then the
    # version needed to extract, whose low byte is the version itself
    record = raw.find(b"PK\x01\x02")
    assert record != -1, "the fixture has changed: no central directory record"
    raw[record + 6] = 64
    destination = tmp_path / "zip-version-64.vsdx"
    destination.write_bytes(bytes(raw))

    with pytest.raises(MalformedPackageError, match="not a readable package") as caught:
        Document.open(str(destination))
    assert isinstance(caught.value.__cause__, NotImplementedError)


@pytest.mark.allow_invalid_package
def test_a_member_whose_header_lies_before_the_archive_raises_malformed_package_error(vsdx_copy, tmp_path):
    """Fails if `_member_bytes` stops refusing a negative `header_offset` before it seeks.

    `ZipFile` places each member by adding the gap between where the central
    directory is and where the end record says it is. An end record that
    overstates the directory's offset makes that gap negative, and the first
    member's header then lies before byte zero. Seeking there raised
    `OSError(EINVAL)`, which `_member_bytes` hands back untranslated because an
    errno normally means the disk failed; here the disk is fine and the
    package lies, so it has to be `MalformedPackageError`.
    """
    raw = bytearray(pathlib.Path(vsdx_copy("test1.vsdx")).read_bytes())
    # end of central directory record: the directory's offset is the 4 bytes
    # at offset 16 from the signature
    end_record = raw.rfind(b"PK\x05\x06")
    assert end_record != -1, "the fixture has changed: no end of central directory record"
    (directory_offset,) = struct.unpack_from("<I", raw, end_record + 16)
    struct.pack_into("<I", raw, end_record + 16, directory_offset + 100)
    destination = tmp_path / "negative-header-offset.vsdx"
    destination.write_bytes(bytes(raw))

    with pytest.raises(MalformedPackageError, match="before the start of the archive"):
        Document.open(str(destination))


@pytest.mark.allow_invalid_package
def test_a_corrupt_compressed_stream_raises_malformed_package_error(vsdx_copy, tmp_path):
    """A deflate stream the decompressor rejects arrives as `zlib.error`, not `BadZipFile`."""
    source = vsdx_copy("test1.vsdx")
    with zipfile.ZipFile(source) as archive:
        header_at = archive.getinfo("visio/document.xml").header_offset
    raw = bytearray(pathlib.Path(source).read_bytes())
    # local file header: 30 fixed bytes, then the name and extra fields, then
    # the compressed data. Smashing its first bytes gives an invalid block type.
    (name_length,) = struct.unpack_from("<H", raw, header_at + 26)
    (extra_length,) = struct.unpack_from("<H", raw, header_at + 28)
    data_at = header_at + 30 + name_length + extra_length
    raw[data_at : data_at + 8] = b"\xff" * 8
    destination = tmp_path / "corrupt-stream.vsdx"
    destination.write_bytes(bytes(raw))

    with pytest.raises(MalformedPackageError, match="cannot be read"):
        Document.open(str(destination))


@pytest.mark.allow_invalid_package
def test_a_corrupt_bzip2_member_raises_malformed_package_error(vsdx_copy, tmp_path):
    """`bz2` reports a stream it cannot decode as a bare `OSError`, with no errno."""
    source = vsdx_copy("test1.vsdx")
    recompressed = tmp_path / "bzip2.vsdx"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(str(recompressed), "w") as rewritten:
        for name in original.namelist():
            compression = zipfile.ZIP_BZIP2 if name == "visio/document.xml" else zipfile.ZIP_DEFLATED
            rewritten.writestr(name, original.read(name), compress_type=compression)

    with zipfile.ZipFile(str(recompressed)) as archive:
        header_at = archive.getinfo("visio/document.xml").header_offset
    raw = bytearray(recompressed.read_bytes())
    (name_length,) = struct.unpack_from("<H", raw, header_at + 26)
    (extra_length,) = struct.unpack_from("<H", raw, header_at + 28)
    data_at = header_at + 30 + name_length + extra_length
    raw[data_at + 10 : data_at + 40] = b"\xff" * 30
    destination = tmp_path / "bzip2-corrupt.vsdx"
    destination.write_bytes(bytes(raw))

    with pytest.raises(MalformedPackageError, match="cannot be read"):
        Document.open(str(destination))


@pytest.mark.allow_invalid_package
def test_a_corrupt_lzma_member_raises_malformed_package_error(vsdx_copy, tmp_path):
    """`lzma` has an error type of its own, which is neither `OSError` nor `zlib.error`.

    Enumerating codecs one at a time is what this is here to stop: the handler
    translates whatever a member read raises, so a codec added to a future
    CPython needs no change here.
    """
    source = vsdx_copy("test1.vsdx")
    recompressed = tmp_path / "lzma.vsdx"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(str(recompressed), "w") as rewritten:
        for name in original.namelist():
            compression = zipfile.ZIP_LZMA if name == "visio/document.xml" else zipfile.ZIP_DEFLATED
            rewritten.writestr(name, original.read(name), compress_type=compression)

    with zipfile.ZipFile(str(recompressed)) as archive:
        header_at = archive.getinfo("visio/document.xml").header_offset
    raw = bytearray(recompressed.read_bytes())
    (name_length,) = struct.unpack_from("<H", raw, header_at + 26)
    (extra_length,) = struct.unpack_from("<H", raw, header_at + 28)
    data_at = header_at + 30 + name_length + extra_length
    raw[data_at + 12 : data_at + 60] = b"\xff" * 48
    destination = tmp_path / "lzma-corrupt.vsdx"
    destination.write_bytes(bytes(raw))

    with pytest.raises(MalformedPackageError, match="cannot be read"):
        Document.open(str(destination))


@pytest.mark.allow_invalid_package
def test_a_member_name_that_is_not_utf_8_raises_malformed_package_error(vsdx_copy, tmp_path):
    """`ZipFile` decodes the central directory before `infolist()` is ever called."""
    source = vsdx_copy("test1.vsdx")
    raw = bytearray(pathlib.Path(source).read_bytes())
    target = b"visio/document.xml"
    for signature, name_offset, flag_offset, length_offset in (
        (b"PK\x03\x04", 30, 6, 26),
        (b"PK\x01\x02", 46, 8, 28),
    ):
        at = raw.find(signature)
        while at != -1:
            (name_length,) = struct.unpack_from("<H", raw, at + length_offset)
            name_at = at + name_offset
            if raw[name_at : name_at + name_length] == target:
                raw[name_at : name_at + name_length] = target[:-1] + b"\xff"
                (flags,) = struct.unpack_from("<H", raw, at + flag_offset)
                struct.pack_into("<H", raw, at + flag_offset, flags | 0x800)  # "the name is UTF-8"
            at = raw.find(signature, at + 4)
    destination = tmp_path / "bad-name.vsdx"
    destination.write_bytes(bytes(raw))

    with pytest.raises(MalformedPackageError, match="not a readable package"):
        Document.open(str(destination))


@pytest.mark.allow_invalid_package
def test_a_package_limit_is_not_reported_as_a_malformed_member(tmp_path):
    """`PackageLimitError` is an `OSError`, and the member handler must not swallow it.

    The handler below it translates a codec's bare `OSError`; a limit refusal
    raised from inside the same `try` has to come out as the limit it is.
    """
    package = tmp_path / "big.vsdx"
    with zipfile.ZipFile(str(package), "w") as archive:
        archive.writestr("visio/document.xml", b"x" * 4096)

    with pytest.raises(PackageLimitError) as caught:
        vsdxkit.package.read_archive_members(str(package), PackageLimits(max_member_size=16))
    assert caught.value.reason == "member_size"


def test_require_attribute_returns_the_value_when_it_is_there():
    """Fails if `xmlio.require_attribute` returns anything but the value of an attribute that is present.

    The load path reads every required attribute through it, so a helper that
    refused a present attribute, or returned something else, would break every
    open rather than only the malformed ones.
    """
    element = ET.fromstring('<Relationship Id="rId1"/>')
    assert vsdxkit.xmlio.require_attribute(element, "Id", "Relationship") == "rId1"


def test_a_part_declaring_an_unknown_encoding_raises_malformed_package_error(bad_encoding_package):
    """`ET.iterparse` reports an unusable encoding as `LookupError`, not `ParseError`.

    Catching only `ET.ParseError` let a bare builtin out of the one function
    both load paths go through (#365 review).
    """
    with pytest.raises(MalformedPackageError, match="encoding"):
        Document.open(bad_encoding_package)


def test_a_part_in_a_multibyte_encoding_the_parser_refuses_is_malformed():
    """Fails if parse_part lets expat's "multi-byte encodings are not supported" ValueError escape untranslated."""
    from vsdxkit import xmlio

    with pytest.raises(MalformedPackageError, match="encoding"):
        xmlio.parse_part(REFUSED_MULTIBYTE_PART, "/visio/pages/page1.xml")


@pytest.mark.allow_invalid_package("unreadable-part")
def test_opening_a_package_with_a_refused_multibyte_page_encoding_raises_malformed_package_error(multibyte_page_package):
    """The public open path must translate this ValueError too, not just the direct `parse_part` call above."""
    with pytest.raises(MalformedPackageError, match="encoding"):
        Document.open(multibyte_page_package)


def test_memory_exhausted_while_reading_a_member_is_not_blamed_on_the_package(monkeypatch, tmp_path):
    """Fails if _member_bytes' broad handler turns MemoryError into MalformedPackageError."""
    from vsdxkit import package

    def exhausted(*args, **kwargs):
        raise MemoryError

    monkeypatch.setattr(package, "_read_bounded", exhausted)
    with pytest.raises(MemoryError):
        package.PackageStore.open(os.path.join(BASEDIR, "test1.vsdx"))


def test_malformed_shapesheet_number_raises_malformed_package_error(vsdx_copy):
    """Fails if `xmlio.to_float` reports a cell that is not a number with a plain `ValueError`.

    The value comes from the document, not from the caller, so a cell that does
    not hold the number it has to is a malformed package.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    shape = next(iter(vis.pages[0].shapes))
    shape.set_cell_value("PinX", "not-a-number")
    with pytest.raises(MalformedPackageError, match="malformed numeric ShapeSheet value"):
        _ = shape.x


# --------------------------------------------------------------------------
# things that are not there
# --------------------------------------------------------------------------


def test_a_bundled_shape_that_is_missing_raises_not_found_error():
    """Fails if a sentinel missing from a bundled document is reported with anything but `NotFoundError`.

    Each `ShapeKind` is a lookup in a bundled document, and a lookup that
    finds nothing is what `NotFoundError` is for. It is still a `ValueError`.
    """
    with pytest.raises(NotFoundError, match=r"has no shape named 'PALETTE_NOT_A_SHAPE'"):
        media._sentinel(media.PALETTE, "PALETTE_NOT_A_SHAPE", Document.open)


def test_deleting_a_detached_shape_raises_invalid_operation_error(vsdx_copy):
    """Fails if a second `Shape.delete` reports anything but `InvalidOperationError`.

    The shape is known and no longer in its document: a refused operation, not
    a missing thing.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    shape = next(iter(vis.pages[0].children))
    shape.delete()
    with pytest.raises(InvalidOperationError, match="deleting a shape refused"):
        shape.delete()


# --------------------------------------------------------------------------
# operations refused because of the document's state
# --------------------------------------------------------------------------


def test_saving_a_drawing_under_a_vsdm_name_raises_invalid_operation(vsdx_copy, tmp_path):
    """#90 needs exactly this type for a package kind / suffix mismatch."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    with pytest.raises(InvalidOperationError, match="macro-enabled"):
        vis.save(str(tmp_path / "out.vsdm"))


def test_gluing_to_a_connection_point_a_shape_does_not_have_raises_invalid_operation(vsdx_copy):
    """Fails if `Connect.create` refuses a connection-point index past the shape's last with anything but `InvalidOperationError`.

    Whether the index is usable depends on how many connection points that
    shape has, so the refusal is about the document's state, not the index.
    """
    vis = Document.open(vsdx_copy("test4_connectors.vsdx"))
    page = vis.pages[0]
    a, b = next(iter(page.children)), list(page.children)[1]
    with pytest.raises(InvalidOperationError, match="connection point"):
        page.connect(a, b, glue=Glue.POINT, from_point=99)


def test_connecting_a_shape_with_no_pin_coordinates_raises_invalid_operation(vsdx_copy):
    """Fails if `Shape.set_start_and_finish` refuses a missing coordinate with a plain `ValueError` again.

    `Connect.create()` hands `set_start_and_finish` the two shapes'
    `center_x_y`, which a shape with no `PinX` reports as None. That is not an
    argument the caller spelled: the refusal is about the state of a shape the
    document holds, which is what `InvalidOperationError` is for, and the text
    position a few lines further on already reported the same None that way.
    It stays a `ValueError`, so code catching the old type still catches it.
    """
    vis = Document.open(vsdx_copy("test8_simple_connector.vsdx"))
    page = vis.pages[0]
    source = page.shapes.by_text("Shape A")
    target = page.shapes.by_text("Shape B")
    assert source is not None and target is not None
    pin_x = source.cells.pop("PinX")
    source.xml.remove(pin_x.xml)
    assert source.x is None, "the fixture has changed: Shape A still has a PinX"

    with pytest.raises(InvalidOperationError, match="start and finish coordinates cannot be None") as caught:
        page.connect(source, target)
    assert isinstance(caught.value, ValueError)


def test_a_page_with_no_container_raises_not_found(vsdx_copy):
    """Fails if `Page.require_swimlanes` reports a page with no CFF container with anything but `NotFoundError`.

    The diagram is looked up on the page, and a lookup that finds nothing is
    what `NotFoundError` is for; `Page.swimlanes` answers None instead.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    assert vis.pages[0].swimlanes is None
    with pytest.raises(NotFoundError, match="no CFF container"):
        vis.pages[0].require_swimlanes()


def test_appending_a_shape_to_a_non_group_raises_invalid_operation(vsdx_copy):
    """Fails if `Shape.append_shape` refuses a host that is not a group with anything but `InvalidOperationError`.

    Only a group can hold shapes, and whether the host is one is the document's
    state rather than something wrong with the shape passed in.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    page = vis.pages[0]
    host, guest = next(iter(page.children)), list(page.children)[1]
    with pytest.raises(InvalidOperationError, match="cannot contain shapes"):
        host.append_shape(guest)


def test_a_duplicate_geometry_row_index_raises_invalid_operation(vsdx_copy):
    """Fails if the geometry section refuses a row index already in use with anything but `InvalidOperationError`.

    The same index is fine in a section that does not use it yet, so the
    refusal comes from what the section already holds.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    shape = next(iter(vis.pages[0].shapes))
    geometry = shape.geometry
    assert geometry is not None
    existing = geometry.rows[sorted(geometry.rows)[0]]
    with pytest.raises(InvalidOperationError, match="already exists"):
        existing.create_row_xml(existing.row_type, str(existing.index))


def test_saving_an_empty_package_raises_invalid_operation(vsdx_copy, tmp_path):
    """Fails if `Document.save` refuses a package with no parts with anything but `InvalidOperationError`.

    Nothing is wrong with the destination path. The document has been emptied,
    and that state is why there is nothing to save.
    """
    vis = Document.open(vsdx_copy("test1.vsdx"))
    for name in vis._package.names():
        vis._package.remove(name)
    with pytest.raises(InvalidOperationError, match="empty package"):
        vis.save(str(tmp_path / "out.vsdx"))


def test_refusing_none_for_a_document_part_is_an_invalid_operation(vsdx_copy):
    """Fails if Document's document-part setters refuse None with a plain ValueError."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    with pytest.raises(InvalidOperationError):
        vis.app_xml = None


def test_refusing_none_for_a_page_part_is_an_invalid_operation(vsdx_copy):
    """Fails if Page.xml refuses None with a plain ValueError."""
    vis = Document.open(vsdx_copy("test1.vsdx"))
    with pytest.raises(InvalidOperationError):
        vis.pages[0].xml = None


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
