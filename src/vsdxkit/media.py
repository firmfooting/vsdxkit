"""The bundled documents new shapes and connectors are copied from.

Each donor is opened once per process, on first use, by the opener the caller
passes: :class:`vsdxkit.document.Document` passes its own ``open``. This
module sits below the document, so it cannot import it. The package is read
into memory with no file held, so a document that used a donor has nothing
to release.

Nothing here reaches a caller outside the package. The document copies a
shape or connector source before anyone else sees it, and
:func:`_style_copy` answers a copy. A caller holding a donor's own elements
could edit them, and every later creation in the process would copy the edit.

Shapes are found by their sentinel text, matched whole.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from xml.etree.ElementTree import Element

from vsdxkit.errors import NotFoundError
from vsdxkit.pages import PageCollection
from vsdxkit.shape_kind import ShapeKind
from vsdxkit.shapes import Shape

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


class _Donor(Protocol):
    """What this module reads off a bundled document."""

    @property
    def pages(self) -> PageCollection: ...

    def _get_style_by_id(self, ID: str) -> Element | None: ...


# the donors loaded so far, by filename; the lock makes the first load of
# each happen once even when several threads create shapes at the same time
_donors: dict[str, _Donor] = {}
_loading = threading.Lock()


def media_path(filename: str) -> str:
    """Path to a bundled donor in the module-adjacent 'media' folder."""
    return str(Path(__file__).resolve().parent / "media" / filename)


def _donor(filename: str, open_document: Callable[[str], _Donor]) -> _Donor:
    """The bundled document `filename`, opened with `open_document` once per process."""
    with _loading:
        document = _donors.get(filename)
        if document is None:
            document = open_document(media_path(filename))
            _donors[filename] = document
        return document


def _sentinel(filename: str, text: str, open_document: Callable[[str], _Donor]) -> Shape:
    shapes = _donor(filename, open_document).pages[0].shapes
    shape = shapes.by_text(text)
    if shape is None:
        names = ", ".join(sorted(shape.text for shape in shapes if shape.text))
        raise NotFoundError(f"{filename} has no shape named {text!r}; it has {names}")
    return shape


def _kind_shape(kind: ShapeKind, open_document: Callable[[str], _Donor]) -> Shape:
    """The bundled shape a kind is copied from. Not for handing out: see the module docstring."""
    filename, text = _KINDS[kind]
    return _sentinel(filename, text, open_document)


def _connector_shape(open_document: Callable[[str], _Donor], *, curved: bool = False) -> Shape:
    """The bundled dynamic connector. Not for handing out: see the module docstring."""
    return _sentinel(MEDIA, CURVED_CONNECTOR if curved else STRAIGHT_CONNECTOR, open_document)


def _style_copy(style_id: str, open_document: Callable[[str], _Donor]) -> Element | None:
    """A copy of the media document's StyleSheet with this ID, or None."""
    style = _donor(MEDIA, open_document)._get_style_by_id(style_id)
    return None if style is None else copy.deepcopy(style)
