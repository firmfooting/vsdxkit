"""The bundled documents new shapes and connectors are copied from.

Each donor is opened once per process, on first use, by the opener the caller
passes: :class:`vsdxkit.document.Document` passes its own ``open``. This
module sits below the document, so it cannot import it. The package is read
into memory with no file held, so a document that used a donor has nothing
to release.

Nothing here reaches a caller outside the package. The library copies a
shape or connector source before a caller sees it:
:meth:`vsdxkit.pages.Page.create_shape` copies a kind's source, and
:meth:`vsdxkit.document.Document._copy_connector` copies the connector.
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
"""The bundled document holding the basic shapes and the two connectors."""
PALETTE = "palette_extended.vsdx"
"""The bundled document holding the flowchart palette's shapes."""

STRAIGHT_CONNECTOR = "STRAIGHT_CONNECTOR"
"""The sentinel text of `MEDIA`'s dynamic connector, drawn as a straight line: what every new connector copies."""
CURVED_CONNECTOR = "CURVED_CONNECTOR"
"""The sentinel text of `MEDIA`'s dynamic connector drawn curved; not yet reached by any caller passing `curved=True`."""

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
"""Every built-in `ShapeKind`, to the bundled document and sentinel text `_kind_shape` copies it from."""


class _Donor(Protocol):
    """What this module reads off a bundled document."""

    @property
    def pages(self) -> PageCollection:
        """The donor's pages, the first of which holds every sentinel shape `_sentinel` looks up."""
        ...

    def _get_style_by_id(self, ID: str) -> Element | None:
        """The `StyleSheet` with this ID, for `_style_copy` to copy."""
        ...


# the donors loaded so far, by filename; the lock makes the first load of
# each happen once even when several threads create shapes at the same time
_donors: dict[str, _Donor] = {}
"""The bundled documents opened so far, by filename, so each is opened once per process."""
_loading = threading.Lock()
"""Serialises `_donor`'s check-then-open, so two threads creating shapes at once do not each open a donor."""


def media_path(filename: str) -> str:
    """Path to a bundled donor in the module-adjacent '_bundled' folder."""
    return str(Path(__file__).resolve().parent / "_bundled" / filename)


def _donor(filename: str, open_document: Callable[[str], _Donor]) -> _Donor:
    """The bundled document `filename`, opened with `open_document` once per process.

    The cache is keyed on the filename alone: `open_document` is called only
    on the first load of each file, and every later caller gets that donor,
    whatever opener it passes. A test that passes any opener but
    ``Document.open`` must give ``_donors`` a table of its own
    (``monkeypatch.setattr(_media, "_donors", {})``), or the donor it loads is
    the one every later test in the session gets.
    """
    with _loading:
        document = _donors.get(filename)
        if document is None:
            document = open_document(media_path(filename))
            _donors[filename] = document
        return document


def _sentinel(filename: str, text: str, open_document: Callable[[str], _Donor]) -> Shape:
    """The shape on `filename`'s first page whose text is exactly `text`, or a NotFoundError naming what is there instead."""
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
