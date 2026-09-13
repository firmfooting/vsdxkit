"""Zip-backed XML persistence helpers shared across modules."""

from __future__ import annotations

import io
import threading
import xml.etree.ElementTree as ET
from collections.abc import Generator
from contextlib import contextmanager

# Prefixes Visio itself writes. ElementTree invents `ns0:`, `ns1:`, ... for any
# namespace it has no prefix for, and consumers stricter than Visio -- libvisio
# (LibreOffice Draw) and draw.io's importer -- reject parts that arrive that
# way (upstream dave-howard/vsdx#90, #35). Every vocabulary the library can
# serialise therefore needs an entry here.
#
# Two entries may share a prefix (`vt` belongs to both docPropsVTypes and the
# Visio theme schema) because the map is applied per part, and no single part
# uses both. `_prefixes_for` resolves any collision that does occur.
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
# xml_to_file override the default per part while it writes.
_GLOBAL_PREFIXES = {
    "http://schemas.microsoft.com/office/visio/2012/main": "",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships": "r",
    "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes": "vt",
}

_registration_lock = threading.RLock()
_registered = False


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


def _prefixes_for(root: ET.Element) -> dict[str, str]:
    """Map every namespace in a part to the prefix Visio writes for it.

    The part's root vocabulary takes the default (empty) prefix, exactly as
    Visio writes it; everything else keeps its conventional prefix.
    """
    used = _namespaces_in(root) - {_XML_NAMESPACE}
    default_uri = root.tag[1:].partition("}")[0] if isinstance(root.tag, str) and root.tag.startswith("{") else None

    prefixes: dict[str, str] = {}
    taken: set[str] = {"xml", "xmlns"}
    if default_uri is not None:
        prefixes[default_uri] = ""
        taken.add("")
    for uri in sorted(used - set(prefixes)):
        prefix = NAMESPACE_PREFIXES.get(uri) or _fallback_prefix(uri)
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


def file_to_xml(filename: str, zip_file_contents: dict[str, io.BytesIO]) -> ET.ElementTree[ET.Element] | None:
    """Import a file as an ElementTree."""
    if filename in zip_file_contents:
        content: io.BytesIO = zip_file_contents[filename]
        return ET.parse(io.BytesIO(content.getvalue()))
    return None


def xml_to_file(xml: ET.ElementTree[ET.Element], filename: str, zip_file_contents: dict[str, io.BytesIO]) -> None:
    """Save an ElementTree to zip_file_contents, prefixed the way Visio writes it."""
    root = xml.getroot()
    file: io.BytesIO = io.BytesIO()
    if root is None:
        xml.write(file, xml_declaration=True, method="xml", encoding="UTF-8")
    else:
        with _serialising(root):
            xml.write(file, xml_declaration=True, method="xml", encoding="UTF-8")
    zip_file_contents[filename] = io.BytesIO(file.getvalue())


def xml_value(value: object) -> str:
    """Coerce a value before assigning it to an ElementTree attribute."""
    if value is None:
        raise TypeError("XML attribute value cannot be None")
    return str(value)


def require_tree(tree: ET.ElementTree[ET.Element] | None, description: str) -> ET.ElementTree[ET.Element]:
    """A required in-memory ElementTree (already parsed from the package)."""
    if tree is None:
        raise ValueError(f"expected document part not found: {description}")
    return tree


def require_xml_tree(filename: str, zip_file_contents: dict[str, io.BytesIO], description: str) -> ET.ElementTree[ET.Element]:
    """Parse a required XML part from the zip and return its ElementTree."""
    tree = file_to_xml(filename, zip_file_contents)
    if tree is None:
        raise ValueError(f"expected XML part not found: {description} ({filename})")
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
        raise ValueError(f"expected XML element not found: {description}")
    return element
