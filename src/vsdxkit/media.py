"""The bundled documents new shapes and connectors are copied from.

Each donor is opened once per process, on first use, and closed at once. A
closed ``VisioFile`` still reads, and a shape copies out of it as out of any
other document, but every write to it raises ``VisioFileNotOpen``: nothing a
caller does can change what the next creation copies. The package is read
into memory with no file held, so there is nothing for a document that used a
donor to release.

Shapes are found by their sentinel text, matched whole.
"""

from __future__ import annotations

import functools
from pathlib import Path
from xml.etree.ElementTree import Element

from vsdxkit.errors import NotFoundError
from vsdxkit.shapes import Shape
from vsdxkit.vsdxfile import VisioFile

MEDIA = "media.vsdx"
PALETTE = "palette_extended.vsdx"

STRAIGHT_CONNECTOR = "STRAIGHT_CONNECTOR"
CURVED_CONNECTOR = "CURVED_CONNECTOR"


def media_path(filename: str) -> str:
    """Path to a bundled donor in the module-adjacent 'media' folder."""
    return str(Path(__file__).resolve().parent / "media" / filename)


@functools.cache
def donor(filename: str) -> VisioFile:
    """The bundled document `filename`, opened once per process and closed to writes."""
    document = VisioFile(media_path(filename))
    document.close_vsdx()
    return document


def _sentinel(filename: str, text: str) -> Shape:
    shapes = donor(filename).pages[0].shapes
    shape = shapes.by_text(text)
    if shape is None:
        names = ", ".join(sorted(shape.text for shape in shapes if shape.text))
        raise NotFoundError(f"{filename} has no shape named {text!r}; it has {names}")
    return shape


def palette_shape(name: str) -> Shape:
    """The palette shape `name`.

    One of ``PALETTE_PROCESS``, ``PALETTE_DECISION``, ``PALETTE_START_END``,
    ``PALETTE_PARALLELOGRAM`` and ``PALETTE_DATABASE``.
    """
    return _sentinel(PALETTE, name)


def media_shape(sentinel: str) -> Shape:
    """The media document's shape carrying `sentinel`, such as ``RECTANGLE`` or ``CIRCLE``."""
    return _sentinel(MEDIA, sentinel)


def connector_shape(curved: bool = False) -> Shape:
    """The dynamic connector every new connector is copied from."""
    return media_shape(CURVED_CONNECTOR if curved else STRAIGHT_CONNECTOR)


def media_style(style_id: str) -> Element | None:
    """The media document's StyleSheet with this ID, or None."""
    return donor(MEDIA)._get_style_by_id(style_id)
