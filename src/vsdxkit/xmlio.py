"""Zip-backed XML persistence helpers shared across modules."""

from __future__ import annotations

import io
import re
import threading
import weakref
import xml.etree.ElementTree as ET
from collections.abc import Generator
from contextlib import contextmanager

from .errors import MalformedPackageError, MissingPartError

# Prefixes Visio itself writes. ElementTree invents `ns0:`, `ns1:`, ... for any
# namespace it has no prefix for, and consumers stricter than Visio -- libvisio
# (LibreOffice Draw) and draw.io's importer -- reject parts that arrive that
# way (upstream dave-howard/vsdx#90, #35). Every vocabulary the library
# introduces itself therefore needs an entry here.
#
# Two entries may share a prefix (`vt` belongs to both docPropsVTypes and the
# Visio theme schema) because the map is applied per part, and no single part
# uses both. `_prefixes_for` resolves any collision that does occur.
#
# A namespace that arrived already spelled is not respelled from this table: a
# part keeps the prefixes it declared, which `_declared_prefixes` records.
NAMESPACE_PREFIXES: dict[str, str] = {
    "http://schemas.microsoft.com/office/visio/2012/main": "",
    "http://schemas.microsoft.com/office/visio/2012/theme": "vt",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships": "r",
    "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes": "vt",
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties": "ep",
    "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties": "op",
    "http://schemas.openxmlformats.org/drawingml/2006/main": "a",
    "http://schemas.openxmlformats.org/package/2006/content-types": "ct",
    "http://schemas.openxmlformats.org/package/2006/relationships": "rel",
    "http://schemas.openxmlformats.org/package/2006/metadata/core-properties": "cp",
    "http://purl.org/dc/elements/1.1/": "dc",
    "http://purl.org/dc/dcmitype/": "dcmitype",
    "http://purl.org/dc/terms/": "dcterms",
    "http://www.w3.org/2001/XMLSchema-instance": "xsi",
}

# `xml:` is bound by the XML spec itself: it is never declared and never
# rebound. ElementTree recognises it only by finding it in this same table, so
# it must survive every per-part swap untouched.
_XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"

# Registering a prefix globally is a whole-process side effect, and only one
# namespace can hold the default (empty) prefix at a time: ET.register_namespace
# drops any previous holder. Claim it for the Visio main namespace, which is the
# one standalone ET.tostring() calls in this library serialise, and let
# serialise_part override the default per part while it writes.
_GLOBAL_PREFIXES = {
    "http://schemas.microsoft.com/office/visio/2012/main": "",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships": "r",
    "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes": "vt",
}

_registration_lock = threading.RLock()
_registered = False

# What each parsed part declared for itself: `{namespace uri: prefix}`, keyed by
# the root element of the tree it was parsed into. A prefix is a property of the
# document that chose it -- Lucidchart writes `lc:`, and inventing a prefix from
# its URI wrote `<xwwwlucidchartcom:Property>` where Visio wrote `<lc:Property>`
# (#282).
#
# Keyed on the root element rather than on the ElementTree because a part is
# routinely rewrapped in a fresh tree before it is written, and held weakly so
# that a part dropped from the package takes its prefixes with it.
_declared_prefixes: weakref.WeakKeyDictionary[ET.Element, dict[str, str]] = weakref.WeakKeyDictionary()

_GENERATED_PREFIX_RE = re.compile(r"ns\d+")


def register_namespaces() -> None:
    """Register the process-wide namespace prefixes. Safe to call repeatedly."""
    global _registered
    with _registration_lock:
        if _registered:
            return
        for uri, prefix in _GLOBAL_PREFIXES.items():
            ET.register_namespace(prefix, uri)
        _registered = True


def _namespaces_in(root: ET.Element) -> set[str]:
    """Every namespace URI used by an element tree's tags and attribute names."""
    found: set[str] = set()
    for element in root.iter():
        for name in (element.tag, *element.keys()):
            if isinstance(name, str) and name.startswith("{"):
                found.add(name[1:].partition("}")[0])
    return found


def _fallback_prefix(uri: str) -> str:
    """A readable, deterministic prefix for a namespace nobody registered."""
    tail = uri.rstrip("/").rpartition("/")[2]
    cleaned = "".join(character for character in tail if character.isalnum())
    # XML prefixes may not start with a digit, and `ns\d+` is ElementTree's own
    # reserved shape -- neither may leak into a part.
    return f"x{cleaned[:16]}" if cleaned else "x"


def _default_namespace_for(root: ET.Element, declared: dict[str, str], used: set[str]) -> str | None:
    """The namespace to write unprefixed, or None to prefix them all.

    Only one namespace can hold the default prefix, so a part that rebinds it on
    a descendant has to give it to whichever came first. A part that declared
    nothing about its own root vocabulary was built in memory rather than
    parsed, and that vocabulary takes the default the way Visio writes it.
    """
    for uri, prefix in declared.items():
        if prefix == "" and uri in used:
            return uri
    root_uri = root.tag[1:].partition("}")[0] if isinstance(root.tag, str) and root.tag.startswith("{") else None
    return None if root_uri in declared else root_uri


def _prefixes_for(root: ET.Element) -> dict[str, str]:
    """Map every namespace in a part to the prefix it should be written with.

    A namespace the part declared keeps the prefix the part gave it. Anything
    else -- a vocabulary this library introduced, or a tree it built itself --
    takes its conventional prefix from `NAMESPACE_PREFIXES`.
    """
    used = _namespaces_in(root) - {_XML_NAMESPACE}
    declared = _declared_prefixes.get(root, {})
    default_uri = _default_namespace_for(root, declared, used)

    prefixes: dict[str, str] = {}
    taken: set[str] = {"xml", "xmlns"}
    if default_uri is not None:
        prefixes[default_uri] = ""
        taken.add("")
    # The part's own prefixes are claimed first, in the order it declared them.
    # Where a declared prefix and a registered one collide, one of them has to
    # be suffixed, and which one cannot be left to whichever URI sorts first.
    chosen = [uri for uri in declared if declared[uri] and uri in used and uri not in prefixes]
    for uri in [*chosen, *sorted(used - set(prefixes) - set(chosen))]:
        prefix = declared.get(uri) or NAMESPACE_PREFIXES.get(uri) or _fallback_prefix(uri)
        if not prefix or prefix in taken:
            base = prefix or _fallback_prefix(uri)
            index = 2
            while f"{base}{index}" in taken:
                index += 1
            prefix = f"{base}{index}"
        prefixes[uri] = prefix
        taken.add(prefix)
    return prefixes


def _prefix_table() -> dict[str, str]:
    """ElementTree's process-wide prefix table.

    ElementTree has resolved namespace prefixes through this module-level dict
    since 1.3 and offers no public equivalent: `register_namespace` can hold
    only one default namespace per process, which a package built from four
    vocabularies cannot use. Fail loudly if a future release moves it rather
    than silently writing `ns0:` parts again.
    """
    table = getattr(ET, "_namespace_map", None)
    if not isinstance(table, dict):  # pragma: no cover - depends on the stdlib
        raise RuntimeError("xml.etree.ElementTree no longer exposes _namespace_map; cannot control namespace prefixes")
    return table


@contextmanager
def _serialising(root: ET.Element) -> Generator[None, None, None]:
    """Install this part's prefix map for the duration of one write.

    ElementTree resolves prefixes through a single module-level table, so a
    part whose default namespace differs from the globally registered one can
    only be written correctly by swapping that table out and restoring it.
    """
    with _registration_lock:
        table = _prefix_table()
        saved = dict(table)
        table.clear()
        table.update(_prefixes_for(root))
        table[_XML_NAMESPACE] = "xml"
        try:
            yield
        finally:
            table.clear()
            table.update(saved)


# The Visio main namespace in ElementTree's `{uri}tag` form, for building
# elements rather than formatting them as strings.
_VISIO_TAG_PREFIX = "{http://schemas.microsoft.com/office/visio/2012/main}"


def make_cell_element(name: str, v: object | None = None, f: object | None = None) -> ET.Element:
    """Build a ``<Cell>`` in the Visio namespace.

    Four places formatted this XML by hand. One of them declared the namespace
    as a prefix the element did not use, so the cell it built sat outside the
    namespace and the shape could not find it again. The rest interpolated
    values straight into the markup, so a value carrying a quote, an ampersand
    or an angle bracket raised ParseError -- and Shape Data and shape text
    routinely carry all three. Setting attributes on an element escapes them on
    serialisation; building a string does not.
    """
    cell = ET.Element(f"{_VISIO_TAG_PREFIX}Cell")
    cell.attrib["N"] = name
    # coerced here, not by the caller: the callers used to interpolate into an
    # f-string, which stringified a number for free. Storing the raw object
    # instead fails much later, at save, with "cannot serialize 5 (type int)".
    if v is not None:
        cell.attrib["V"] = xml_value(v)
    if f is not None:
        cell.attrib["F"] = xml_value(f)
    return cell


def parse_part(data: bytes, name: str = "") -> ET.ElementTree[ET.Element]:
    """Parse one package part, recording the namespace prefixes it declares.

    A parsed tree holds expanded names and nothing else: by the time `ET.parse`
    returns, which prefix stood for which namespace is gone, and the write side
    has to guess one. The bindings are visible only during the parse, so they
    are collected here and kept against the root element.

    A part that will not parse is reported here rather than at each call site.
    Both routes into the parser -- `file_to_xml`, which is how a document is
    opened, and `PackageStore`'s promotion -- come through this function, so a
    translation at one of them would leave the other raising whatever
    ElementTree raised. The original stays as the cause: `ET.ParseError` holds
    the `position` a caller needs to find the byte that broke.
    """
    subject = f"package part {name}" if name else "package part"
    root: ET.Element | None = None
    declared: dict[str, str] = {}
    try:
        for event, payload in ET.iterparse(io.BytesIO(data), events=("start-ns", "start")):
            if event == "start-ns":
                prefix, uri = payload
                # `ns0:` is ElementTree's invention, not a spelling any document
                # chose: a part carrying one was written by a vsdx older than the
                # per-part prefix fix, and keeping it would re-create #60
                if _GENERATED_PREFIX_RE.fullmatch(prefix):
                    continue
                # first binding wins: a part may bind the same namespace twice, and
                # only one spelling of it can be written back
                declared.setdefault(uri, prefix)
            elif root is None:
                root = payload
    except ET.ParseError as error:
        raise MalformedPackageError(f"{subject} is not well-formed XML: {error}") from error
    except LookupError as error:
        # A part may name any encoding it likes in its declaration, and one
        # nothing can decode arrives as LookupError rather than ParseError.
        # Nothing in the loop body looks anything up, so this catches the
        # parser and only the parser.
        raise MalformedPackageError(f"{subject} declares an encoding that cannot be decoded: {error}") from error
    if root is None:  # pragma: no cover - a part with no root element fails to parse first
        raise MalformedPackageError(f"{subject} has no root element")
    _declared_prefixes[root] = declared
    return ET.ElementTree(root)


def adopt_prefixes(root: ET.Element, source: ET.Element) -> None:
    """Give a tree rebuilt from another the prefixes that other one declared.

    Copying a page and rendering a template both serialise a part and parse the
    string back, which loses the bindings `parse_part` captured. Without this
    the copy is written with an invented prefix while its source keeps `lc:`,
    and one package spells the same vocabulary two ways.
    """
    declared = _declared_prefixes.get(source)
    if declared is not None:
        _declared_prefixes[root] = declared


def file_to_xml(filename: str, zip_file_contents: dict[str, io.BytesIO]) -> ET.ElementTree[ET.Element] | None:
    """Import a file as an ElementTree."""
    if filename in zip_file_contents:
        return parse_part(zip_file_contents[filename].getvalue(), filename)
    return None


def serialise_part(xml: ET.ElementTree[ET.Element]) -> bytes:
    """One package part as bytes, prefixed the way Visio writes it.

    Split out of `xml_to_file` so that a part written through `PackageStore`
    and one written through `xml_to_file` cannot disagree about the
    declaration, the encoding or the per-part prefix map.

    Two parts are still written without coming through here: `masters.py` and
    `pages.py` each build a tree and hand it straight to `ET.tostring`, which
    resolves prefixes from whatever the global table happens to hold. Both are
    on #91's list.
    """
    root = xml.getroot()
    file: io.BytesIO = io.BytesIO()
    if root is None:
        xml.write(file, xml_declaration=True, method="xml", encoding="UTF-8")
    else:
        with _serialising(root):
            xml.write(file, xml_declaration=True, method="xml", encoding="UTF-8")
    return file.getvalue()


def xml_to_file(xml: ET.ElementTree[ET.Element], filename: str, zip_file_contents: dict[str, io.BytesIO]) -> None:
    """Save an ElementTree to zip_file_contents, prefixed the way Visio writes it."""
    zip_file_contents[filename] = io.BytesIO(serialise_part(xml))


def xml_value(value: object) -> str:
    """Coerce a value before assigning it to an ElementTree attribute."""
    if value is None:
        raise TypeError("XML attribute value cannot be None")
    return str(value)


def require_tree(tree: ET.ElementTree[ET.Element] | None, description: str) -> ET.ElementTree[ET.Element]:
    """A required in-memory ElementTree (already parsed from the package)."""
    if tree is None:
        raise MissingPartError(f"expected document part not found: {description}")
    return tree


def require_xml_tree(filename: str, zip_file_contents: dict[str, io.BytesIO], description: str) -> ET.ElementTree[ET.Element]:
    """Parse a required XML part from the zip and return its ElementTree."""
    tree = file_to_xml(filename, zip_file_contents)
    if tree is None:
        raise MissingPartError(f"expected XML part not found: {description} ({filename})")
    return tree


def require_root(filename: str, zip_file_contents: dict[str, io.BytesIO], description: str) -> ET.Element:
    """Parse a required XML part from the zip and return its root element."""
    return require_element(require_xml_tree(filename, zip_file_contents, description).getroot(), description)


def require_element(element: ET.Element | None, description: str) -> ET.Element:
    """Return a required XML element, or raise with a description of what was expected.

    Visio parts are schema-driven: a missing Pages/Page/PageSheet/Cell element
    means the document is malformed rather than that the caller should branch.
    Fail loudly with the path instead of raising AttributeError on None.
    """
    if element is None:
        raise MissingPartError(f"expected XML element not found: {description}")
    return element
