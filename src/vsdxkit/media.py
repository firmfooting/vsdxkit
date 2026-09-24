"""The bundled documents new shapes and connectors are copied from.

Each donor is opened once per process, on first use. The package is read
into memory with no file held, so there is nothing for a document that used a
donor to release.

Nothing here hands out a donor or anything inside one: every function answers
a copy. A caller holding a donor's own elements could edit them, and every
later creation in the process would copy the edit.

Shapes are found by their sentinel text, matched whole.
"""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from xml.etree.ElementTree import Element

from vsdxkit.document import Document
from vsdxkit.errors import MalformedPackageError, NotFoundError
from vsdxkit.pages import Page
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.shapes import Connector, Shape

MEDIA = "media.vsdx"
PALETTE = "palette_extended.vsdx"

STRAIGHT_CONNECTOR = "STRAIGHT_CONNECTOR"
CURVED_CONNECTOR = "CURVED_CONNECTOR"

# each built-in kind: the bundled document it is copied from, and its sentinel text there
_KINDS: dict[ShapeKind, tuple[str, str]] = {
    ShapeKind.PROCESS: (PALETTE, "PALETTE_PROCESS"),
    ShapeKind.DECISION: (PALETTE, "PALETTE_DECISION"),
    ShapeKind.START_END: (PALETTE, "PALETTE_START_END"),
    ShapeKind.PARALLELOGRAM: (PALETTE, "PALETTE_PARALLELOGRAM"),
    ShapeKind.DATABASE: (PALETTE, "PALETTE_DATABASE"),
    ShapeKind.RECTANGLE: (MEDIA, "RECTANGLE"),
    ShapeKind.CIRCLE: (MEDIA, "CIRCLE"),
    ShapeKind.LINE: (MEDIA, "LINE"),
}

# the donors loaded so far, by filename; the lock makes the first load of
# each happen once even when several threads create shapes at the same time
_donors: dict[str, Document] = {}
_loading = threading.Lock()


def media_path(filename: str) -> str:
    """Path to a bundled donor in the module-adjacent 'media' folder."""
    return str(Path(__file__).resolve().parent / "media" / filename)


def _donor(filename: str) -> Document:
    """The bundled document `filename`, opened once per process."""
    with _loading:
        document = _donors.get(filename)
        if document is None:
            document = Document.open(media_path(filename))
            _donors[filename] = document
        return document


def _sentinel(filename: str, text: str) -> Shape:
    shapes = _donor(filename).pages[0].shapes
    shape = shapes.by_text(text)
    if shape is None:
        names = ", ".join(sorted(shape.text for shape in shapes if shape.text))
        raise NotFoundError(f"{filename} has no shape named {text!r}; it has {names}")
    return shape


def _kind_shape(kind: ShapeKind) -> Shape:
    """The bundled shape a kind is copied from. Not for handing out: see the module docstring."""
    return _sentinel(*_KINDS[kind])


def copy_kind(kind: ShapeKind, page: Page) -> Shape:
    """A copy of the built-in shape `kind` on `page`, through :meth:`Shape.copy`. It still carries the sentinel text."""
    return _kind_shape(kind).copy(page)


def copy_connector(page: Page, curved: bool = False) -> Connector:
    """A copy of the bundled dynamic connector on `page`, its master imported. It still carries the sentinel text."""
    connector = _sentinel(MEDIA, CURVED_CONNECTOR if curved else STRAIGHT_CONNECTOR).copy(page)
    if not isinstance(connector, Connector):
        raise MalformedPackageError(f"the bundled connector in {MEDIA} is not a 1-D shape")
    return connector


def media_style(style_id: str) -> Element | None:
    """A copy of the media document's StyleSheet with this ID, or None."""
    style = _donor(MEDIA)._get_style_by_id(style_id)
    return None if style is None else copy.deepcopy(style)
