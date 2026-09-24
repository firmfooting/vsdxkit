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

from vsdxkit.errors import NotFoundError
from vsdxkit.pages import Page
from vsdxkit.shapes import Shape
from vsdxkit.vsdxfile import VisioFile

MEDIA = "media.vsdx"
PALETTE = "palette_extended.vsdx"

STRAIGHT_CONNECTOR = "STRAIGHT_CONNECTOR"
CURVED_CONNECTOR = "CURVED_CONNECTOR"

# the donors loaded so far, by filename; the lock makes the first load of
# each happen once even when several threads create shapes at the same time
_donors: dict[str, VisioFile] = {}
_loading = threading.Lock()


def media_path(filename: str) -> str:
    """Path to a bundled donor in the module-adjacent 'media' folder."""
    return str(Path(__file__).resolve().parent / "media" / filename)


def _donor(filename: str) -> VisioFile:
    """The bundled document `filename`, opened once per process."""
    with _loading:
        document = _donors.get(filename)
        if document is None:
            document = VisioFile(media_path(filename))
            _donors[filename] = document
        return document


def _sentinel(filename: str, text: str) -> Shape:
    shapes = _donor(filename).pages[0].shapes
    shape = shapes.by_text(text)
    if shape is None:
        names = ", ".join(sorted(shape.text for shape in shapes if shape.text))
        raise NotFoundError(f"{filename} has no shape named {text!r}; it has {names}")
    return shape


def copy_palette_shape(name: str, page: Page) -> Shape:
    """A copy of the palette shape `name` on `page`, through :meth:`Shape.copy`.

    `name` is one of ``PALETTE_PROCESS``, ``PALETTE_DECISION``,
    ``PALETTE_START_END``, ``PALETTE_PARALLELOGRAM`` and ``PALETTE_DATABASE``.
    The copy still carries the sentinel text.
    """
    return _sentinel(PALETTE, name).copy(page)


def copy_connector(page: Page, curved: bool = False) -> Shape:
    """A copy of the bundled dynamic connector on `page`, its master imported. It still carries the sentinel text."""
    return _sentinel(MEDIA, CURVED_CONNECTOR if curved else STRAIGHT_CONNECTOR).copy(page)


def media_style(style_id: str) -> Element | None:
    """A copy of the media document's StyleSheet with this ID, or None."""
    style = _donor(MEDIA)._get_style_by_id(style_id)
    return None if style is None else copy.deepcopy(style)
